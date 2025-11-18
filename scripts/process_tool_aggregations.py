#!/usr/bin/env python3
"""Validate tool aggregation config, update overrides, and emit the intended catalog."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.catalog.store import load_catalog_store
from stelae_lib.config_overlays import ensure_config_home_scaffold, require_home_path, runtime_path, write_json
from stelae_lib.integrator.tool_aggregations import ToolAggregationConfig, validate_aggregation_schema
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


DEFAULT_SUCCESS_THRESHOLD = int(os.getenv("SCHEMA_SUCCESS_THRESHOLD", os.getenv("STELAE_SCHEMA_SUCCESS_THRESHOLD", "2")))
DEFAULT_STABLE_PRUNE_THRESHOLD = int(os.getenv("STELAE_SCHEMA_STABLE_RETENTION", "10"))
DEFAULT_DRIFT_LOG_MAX = int(os.getenv("STELAE_DRIFT_LOG_MAX", "200"))


class DescriptorLoadError(RuntimeError):
    """Raised when live descriptors are missing or stale."""


def _coerce_bool(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - surfaced for CLI
        raise DescriptorLoadError(f"Invalid JSON in {path}: {exc}") from exc


def _schema_hash(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return None


def _collect_descriptor_index(payload: Any) -> dict[tuple[str, str], dict[str, Any]]:
    servers: dict[str, Mapping[str, Any]] = {}
    if isinstance(payload, Mapping) and isinstance(payload.get("servers"), Mapping):
        servers = {name: fragment for name, fragment in payload["servers"].items() if isinstance(fragment, Mapping)}
    elif isinstance(payload, Mapping) and isinstance(payload.get("catalog"), Mapping):
        catalog_payload = payload["catalog"]
        if isinstance(catalog_payload, Mapping) and isinstance(catalog_payload.get("servers"), Mapping):
            servers = {name: fragment for name, fragment in catalog_payload["servers"].items() if isinstance(fragment, Mapping)}
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for server_name, fragment in servers.items():
        tools = fragment.get("tools")
        if not isinstance(tools, Mapping):
            continue
        for tool_name, descriptor in tools.items():
            if not isinstance(descriptor, Mapping):
                continue
            index[(server_name, tool_name)] = dict(descriptor)
    return index


def _load_live_descriptors(path: Path, *, baseline_mtime: float) -> tuple[dict[tuple[str, str], dict[str, Any]], float]:
    if not path.exists():
        raise DescriptorLoadError(f"live descriptors missing at {path}")
    data = _load_json(path)
    index = _collect_descriptor_index(data)
    if not index:
        raise DescriptorLoadError(f"live descriptor snapshot at {path} did not contain any servers/tools")
    mtime = path.stat().st_mtime
    if mtime < baseline_mtime:
        raise DescriptorLoadError(f"live descriptors at {path} are older than catalog fragments")
    return index, mtime


def _descriptor_index_from_overrides(payload: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return _collect_descriptor_index({"servers": payload.get("servers") or {}})


def _annotate_schema_refs(
    aggregations_payload: Mapping[str, Any],
    config: ToolAggregationConfig,
    descriptors: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    annotated = json.loads(json.dumps(aggregations_payload, ensure_ascii=False))
    aggregations = annotated.get("aggregations")
    if not isinstance(aggregations, list):
        return annotated
    config_lookup = {agg.name: agg for agg in config.aggregations}
    for entry in aggregations:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        config_entry = config_lookup.get(name)
        if not config_entry:
            continue
        if not isinstance(entry.get("operations"), list):
            continue
        operation_lookup = {op.value: op for op in config_entry.operations}
        for op_entry in entry["operations"]:
            if not isinstance(op_entry, Mapping):
                continue
            op_value = str(op_entry.get("value") or "").strip()
            config_op = operation_lookup.get(op_value)
            if not config_op or config_op.response_rules:
                continue
            matches = []
            if config_op.downstream_server:
                key = (config_op.downstream_server, config_op.downstream_tool)
                descriptor = descriptors.get(key)
                if descriptor:
                    matches.append((config_op.downstream_server, descriptor))
            else:
                matches = [(server, desc) for (server, tool), desc in descriptors.items() if tool == config_op.downstream_tool]
            if len(matches) != 1:
                continue
            server_name, descriptor = matches[0]
            schema_hash = descriptor.get("schemaHash") or _schema_hash(descriptor.get("outputSchema"))
            if not schema_hash:
                continue
            if "downstreamSchemaRef" not in op_entry:
                op_entry["downstreamSchemaRef"] = {
                    "tool": config_op.downstream_tool,
                    "server": server_name,
                    "schemaHash": schema_hash,
                }
    return annotated


def _find_missing_descriptors(config: ToolAggregationConfig, descriptors: Mapping[tuple[str, str], Mapping[str, Any]]) -> list[str]:
    missing: list[str] = []
    for aggregation in config.aggregations:
        for operation in aggregation.operations:
            matches: list[tuple[str, str]] = []
            if operation.downstream_server:
                key = (operation.downstream_server, operation.downstream_tool)
                if key in descriptors:
                    matches.append(key)
            else:
                matches = [(server, tool) for (server, tool) in descriptors if tool == operation.downstream_tool]
            if not matches:
                missing.append(f"{aggregation.name}:{operation.value}->{operation.downstream_tool}")
    return missing


def _enabled_tools(tool_overrides: Mapping[str, Any], hidden: list[Mapping[str, Any]]) -> set[str]:
    hidden_markers = {f"{item.get('server')}::{item.get('tool')}" for item in hidden if isinstance(item, Mapping)}
    servers = tool_overrides.get("servers")
    if not isinstance(servers, Mapping):
        return set()
    entries: set[str] = set()
    for server_name, fragment in servers.items():
        if not isinstance(fragment, Mapping) or fragment.get("enabled") is False:
            continue
        tools = fragment.get("tools")
        if not isinstance(tools, Mapping):
            continue
        for tool_name, descriptor in tools.items():
            if not isinstance(descriptor, Mapping) or descriptor.get("enabled") is False:
                continue
            marker = f"{server_name}::{tool_name}"
            if marker not in hidden_markers:
                entries.add(marker)
    return entries


def _extract_live_tools(live_catalog_path: Path) -> set[str]:
    if not live_catalog_path.exists():
        return set()
    try:
        data = json.loads(live_catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, Mapping) and "toolOverrides" in data:
        overrides_payload = data.get("toolOverrides")
        if isinstance(overrides_payload, Mapping):
            return _enabled_tools(overrides_payload, [])
    if isinstance(data, Mapping) and "catalog" in data and isinstance(data["catalog"], Mapping):
        catalog_payload = data["catalog"]
        if isinstance(catalog_payload, Mapping):
            overrides_payload = catalog_payload.get("toolOverrides")
            hide_payload = catalog_payload.get("hideTools") or []
            if isinstance(overrides_payload, Mapping):
                hidden = hide_payload if isinstance(hide_payload, list) else []
                return _enabled_tools(overrides_payload, hidden)
    servers = data.get("servers") if isinstance(data, Mapping) else None
    tool_set: set[str] = set()
    if isinstance(servers, Mapping):
        for server_name, fragment in servers.items():
            if not isinstance(fragment, Mapping):
                continue
            tools = fragment.get("tools")
            if not isinstance(tools, Mapping):
                continue
            for tool_name, descriptor in tools.items():
                if isinstance(descriptor, Mapping) and descriptor.get("enabled", True):
                    tool_set.add(f"{server_name}::{tool_name}")
    tools_list = data.get("tools") if isinstance(data, Mapping) else None
    if isinstance(tools_list, list):
        for entry in tools_list:
            if not isinstance(entry, Mapping):
                continue
            server = entry.get("server") or entry.get("serverName")
            tool = entry.get("name")
            if isinstance(server, str) and isinstance(tool, str):
                tool_set.add(f"{server}::{tool}")
    return tool_set


def _append_drift_log(path: Path, summary: str) -> None:
    lines: list[str] = []
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    timestamp = datetime.now(timezone.utc).isoformat()
    lines.append(f"{timestamp} {summary}")
    if DEFAULT_DRIFT_LOG_MAX and len(lines) > DEFAULT_DRIFT_LOG_MAX:
        lines = lines[-DEFAULT_DRIFT_LOG_MAX :]
    write_json(path, lines)


def _load_schema_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": 1, "tools": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schemaVersion": 1, "tools": {}}
    if not isinstance(data, Mapping):
        return {"schemaVersion": 1, "tools": {}}
    tools = data.get("tools")
    return {"schemaVersion": 1, "tools": tools if isinstance(tools, Mapping) else {}}


def _update_schema_status(
    status_path: Path,
    descriptor_index: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    failed_tools: set[str],
) -> None:
    status = _load_schema_status(status_path)
    tools: dict[str, Any] = {}
    success_threshold = DEFAULT_SUCCESS_THRESHOLD
    stable_threshold = DEFAULT_STABLE_PRUNE_THRESHOLD
    now = datetime.now(timezone.utc).isoformat()
    for (server_name, tool_name), descriptor in descriptor_index.items():
        marker = f"{server_name}::{tool_name}"
        schema_hash = descriptor.get("schemaHash") or _schema_hash(descriptor.get("outputSchema"))
        entry = status["tools"].get(marker, {}) if isinstance(status.get("tools"), Mapping) else {}
        state = entry.get("state") or "pending"
        success_count = int(entry.get("successCount", 0) or 0)
        failure_count = int(entry.get("failureCount", 0) or 0)
        stable_renders = int(entry.get("stableRenders", 0) or 0)
        previous_hash = entry.get("schemaHash")
        if schema_hash and schema_hash != previous_hash:
            state = "pending"
            success_count = 0
            failure_count = 0
            stable_renders = 0
        elif schema_hash and schema_hash == previous_hash:
            if state == "pending":
                success_count += 1
                if success_count >= success_threshold:
                    state = "validated"
                    stable_renders = 0
            elif state == "validated":
                stable_renders += 1
        if marker in failed_tools:
            failure_count += 1
            state = "failed"
            stable_renders = 0
        tools[marker] = {
            "state": state,
            "schemaHash": schema_hash,
            "successCount": success_count,
            "failureCount": failure_count,
            "stableRenders": stable_renders,
            "updatedAt": now,
        }
    pruned: dict[str, Any] = {}
    for tool_id, entry in tools.items():
        if entry.get("state") == "validated" and entry.get("stableRenders", 0) >= stable_threshold:
            continue
        pruned[tool_id] = entry
    status["tools"] = pruned
    write_json(status_path, status)


def _write_with_history(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        suffix = ".prev.json" if path.suffix else ".prev"
        backup = path.with_suffix(suffix)
        try:
            path.replace(backup)
        except OSError:
            pass
    history_flag = os.getenv("STELAE_INTENDED_HISTORY", "").strip().lower() == "keep"
    write_json(path, payload)
    if history_flag:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        history_copy = path.with_name(f"{path.stem}.{timestamp}{path.suffix}")
        write_json(history_copy, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tool aggregation config and update overrides")
    parser.add_argument(
        "--schema",
        default=None,
        type=Path,
        help="Optional explicit schema path (defaults to config/tool_aggregations.schema.json)",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="Path to tool overrides file that should receive aggregation entries",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only validate the aggregation config; do not modify overrides",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Merged overrides destination (defaults to ${TOOL_OVERRIDES_PATH} or ~/.config/stelae/.state/tool_overrides.json)",
    )
    parser.add_argument(
        "--scope",
        choices=("local", "default"),
        default="local",
        help="Which aggregation layer to process (local overlays or tracked defaults)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Fail when live catalog drift or schema reference issues are detected",
    )
    parser.add_argument(
        "--allow-stale-descriptors",
        action="store_true",
        help="Allow falling back to tracked overrides when live_descriptors.json is missing or stale",
    )
    parser.add_argument(
        "--live-descriptors",
        type=Path,
        help="Optional path to live_descriptors.json (defaults to ${STELAE_STATE_HOME}/live_descriptors.json)",
    )
    parser.add_argument(
        "--live-catalog",
        type=Path,
        help="Optional path to live_catalog.json for drift detection (defaults to ${STELAE_STATE_HOME}/live_catalog.json)",
    )
    parser.add_argument(
        "--schema-status",
        type=Path,
        help="Optional path to tool_schema_status.json (defaults to ${STELAE_STATE_HOME}/tool_schema_status.json)",
    )
    args = parser.parse_args()

    ensure_config_home_scaffold()

    overrides_base = args.overrides or Path(os.getenv("STELAE_TOOL_OVERRIDES") or (ensure_config_home_scaffold()["config_home"] / "tool_overrides.json"))
    try:
        overrides_base = require_home_path(
            "STELAE_TOOL_OVERRIDES",
            default=overrides_base,
            description="Tool overrides template",
            allow_config=True,
            allow_state=False,
            create=True,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    runtime_default = args.output or os.getenv("TOOL_OVERRIDES_PATH") or runtime_path("tool_overrides.json")
    try:
        runtime_path_value = require_home_path(
            "TOOL_OVERRIDES_PATH",
            default=Path(runtime_default),
            description="Tool overrides runtime output",
            allow_config=False,
            allow_state=True,
            create=True,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    schema_path = args.schema or (ROOT / "config" / "tool_aggregations.schema.json")
    catalog_filter = ["core"] if args.scope == "default" else None
    include_bundles = args.scope != "default"
    catalog_store = load_catalog_store(catalog_filenames=catalog_filter, include_bundles=include_bundles)
    validate_aggregation_schema(catalog_store.tool_aggregations, schema_path)
    config = ToolAggregationConfig.from_data(catalog_store.tool_aggregations)
    target = "base" if args.scope == "default" else "overlay"

    baseline_paths = [overrides_base] + [fragment.path for fragment in catalog_store.fragments if fragment.exists]
    baseline_mtime = max((path.stat().st_mtime for path in baseline_paths if path.exists()), default=0.0)

    allow_stale = args.allow_stale_descriptors or _coerce_bool(os.getenv("STELAE_ALLOW_STALE_DESCRIPTORS"))

    live_descriptors_path = args.live_descriptors or Path(os.getenv("LIVE_DESCRIPTORS_PATH") or runtime_path("live_descriptors.json"))
    try:
        live_descriptors_path = require_home_path(
            "LIVE_DESCRIPTORS_PATH",
            default=live_descriptors_path,
            description="Live descriptors snapshot",
            allow_config=False,
            allow_state=True,
            create=False,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    live_catalog_path = args.live_catalog or Path(os.getenv("LIVE_CATALOG_PATH") or runtime_path("live_catalog.json"))
    try:
        live_catalog_path = require_home_path(
            "LIVE_CATALOG_PATH",
            default=live_catalog_path,
            description="Live catalog snapshot",
            allow_config=False,
            allow_state=True,
            create=False,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    schema_status_path = args.schema_status or Path(
        os.getenv("TOOL_SCHEMA_STATUS_PATH") or runtime_path("tool_schema_status.json")
    )
    try:
        schema_status_path = require_home_path(
            "TOOL_SCHEMA_STATUS_PATH",
            default=schema_status_path,
            description="Tool schema status path",
            allow_config=False,
            allow_state=True,
            create=True,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    drift_log_path = runtime_path("live_catalog_drift.log")
    try:
        drift_log_path = require_home_path(
            "LIVE_CATALOG_DRIFT_LOG",
            default=drift_log_path,
            description="Live catalog drift log",
            allow_config=False,
            allow_state=True,
            create=True,
        )
    except ValueError as exc:
        raise SystemExit(f"[process-tool-aggregations] {exc}") from exc

    store = ToolOverridesStore(
        overrides_base,
        overlay_path=overrides_base,
        runtime_path=runtime_path_value,
        target=target,
    )
    changed = config.apply_overrides(store)

    descriptor_index: dict[tuple[str, str], dict[str, Any]] | None = None
    descriptor_source = "live_descriptors"
    descriptor_warning: str | None = None
    if live_descriptors_path.exists():
        try:
            descriptor_index, _ = _load_live_descriptors(live_descriptors_path, baseline_mtime=baseline_mtime)
        except DescriptorLoadError as exc:
            descriptor_warning = str(exc)
            descriptor_source = "overrides"
            descriptor_index = _descriptor_index_from_overrides(store.merged_snapshot())
            if args.verify and not allow_stale:
                verification_errors.append(f"Live descriptors stale or invalid: {descriptor_warning}")
    else:
        descriptor_warning = f"live descriptors missing at {live_descriptors_path}"
        descriptor_source = "overrides"
        descriptor_index = _descriptor_index_from_overrides(store.merged_snapshot())

    runtime_snapshot = store.merged_snapshot()
    catalog_store.tool_aggregations = _annotate_schema_refs(
        catalog_store.tool_aggregations,
        config,
        descriptor_index,
    )

    intended_metadata = {"descriptorSource": descriptor_source}
    if descriptor_source != "live_descriptors" and descriptor_warning:
        intended_metadata["descriptorWarning"] = descriptor_warning

    intended_tools = _enabled_tools(runtime_snapshot, catalog_store.hide_tools)
    live_catalog_exists = live_catalog_path.exists()
    live_tools = _extract_live_tools(live_catalog_path) if live_catalog_exists else set()
    drift_missing = intended_tools - live_tools if live_catalog_exists else set()
    drift_extra = live_tools - intended_tools if live_catalog_exists else set()
    if not live_catalog_exists and descriptor_source == "live_descriptors":
        drift_missing = intended_tools

    verification_errors: list[str] = []
    if args.verify:
        missing_refs = _find_missing_descriptors(config, descriptor_index)
        if missing_refs:
            verification_errors.append(f"Downstream descriptors missing: {', '.join(sorted(missing_refs))}")
        if not live_catalog_exists and descriptor_source == "live_descriptors":
            verification_errors.append(f"Live catalog missing at {live_catalog_path}")
        if (drift_missing or drift_extra) and not _coerce_bool(os.getenv("STELAE_ALLOW_LIVE_DRIFT")):
            parts: list[str] = []
            if drift_missing:
                parts.append(f"missing={sorted(drift_missing)}")
            if drift_extra:
                parts.append(f"extra={sorted(drift_extra)}")
            verification_errors.append(f"Live catalog drift detected ({'; '.join(parts)})")

    if args.check_only:
        fragment_count = len(catalog_store.fragments)
        extra = f" descriptor_source={descriptor_source}"
        print(
            f"Validated merged catalog from {fragment_count} fragment(s) with {len(config.aggregations)} aggregations and {len(config.all_hidden_tools())} hidden tools.{extra}"
        )
        if args.verify and descriptor_source != "live_descriptors" and not allow_stale:
            raise SystemExit("[process-tool-aggregations] --verify requires live_descriptors.json unless --allow-stale-descriptors is set")
        if verification_errors:
            raise SystemExit(f"[process-tool-aggregations] {'; '.join(verification_errors)}")
        return

    if changed:
        store.write()
        print(
            f"Applied aggregation overrides for {len(config.aggregations)} tools and {len(config.all_hidden_tools())} hidden entries."
        )
    else:
        print("Aggregation overrides already up to date.")
        if target != "runtime":
            store.export_runtime()

    if args.scope == "local":
        intended_default = os.getenv("INTENDED_CATALOG_PATH") or runtime_path("intended_catalog.json")
        try:
            intended_path = require_home_path(
                "INTENDED_CATALOG_PATH",
                default=Path(intended_default),
                description="Intended catalog path",
                allow_config=False,
                allow_state=True,
                create=True,
            )
        except ValueError as exc:
            raise SystemExit(f"[process-tool-aggregations] {exc}") from exc
        payload = catalog_store.build_intended_catalog(destination=intended_path, runtime_overrides=runtime_path_value)
        payload["metadata"] = intended_metadata
        _write_with_history(intended_path, payload)
        print(
            f"[process-tool-aggregations] overrides_base={overrides_base} runtime={runtime_path_value} intended={intended_path} fragments={len(catalog_store.fragments)} descriptor_source={descriptor_source}"
        )

    if drift_missing or drift_extra:
        summary_parts = []
        if drift_missing:
            summary_parts.append(f"missing={sorted(drift_missing)}")
        if drift_extra:
            summary_parts.append(f"extra={sorted(drift_extra)}")
        _append_drift_log(drift_log_path, "; ".join(summary_parts))

    if descriptor_source == "live_descriptors":
        _update_schema_status(schema_status_path, descriptor_index, failed_tools=drift_missing)

    if args.verify and verification_errors:
        raise SystemExit(f"[process-tool-aggregations] {'; '.join(verification_errors)}")


if __name__ == "__main__":
    main()
