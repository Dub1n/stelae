from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from stelae_lib.catalog_defaults import DEFAULT_CATALOG_FRAGMENT
from stelae_lib.config_overlays import (
    BUNDLES_DIRNAME,
    CATALOG_DIRNAME,
    config_home,
    deep_merge,
    server_enabled,
    write_json,
)
from stelae_lib.integrator.tool_aggregations import merge_aggregation_payload


def _copy_payload(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


@dataclass(frozen=True)
class CatalogFragment:
    path: Path
    kind: Literal["catalog", "bundle", "embedded-defaults", "legacy"]
    name: str
    payload: dict[str, Any]
    exists: bool = True

    def to_metadata(self, *, config_root: Path) -> dict[str, Any]:
        metadata = {
            "kind": self.kind,
            "name": self.name,
            "path": str(self.path),
            "relativePath": _relative_path(self.path, config_root),
            "exists": self.exists and self.path.exists(),
        }
        if metadata["exists"]:
            stat = self.path.stat()
            metadata["size"] = stat.st_size
            metadata["modifiedAt"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        if self.kind == "bundle":
            metadata["bundle"] = self.name
        return metadata


@dataclass
class CatalogStore:
    tool_overrides: dict[str, Any]
    tool_aggregations: dict[str, Any]
    hide_tools: list[dict[str, Any]]
    fragments: list[CatalogFragment]
    config_home: Path

    def build_intended_catalog(self, *, destination: Path, runtime_overrides: Path | None = None) -> dict[str, Any]:
        paths: dict[str, str] = {
            "intendedCatalog": str(destination),
            "configHome": str(self.config_home),
        }
        if runtime_overrides:
            paths["runtimeOverrides"] = str(runtime_overrides)
        payload = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "paths": paths,
            "fragments": [fragment.to_metadata(config_root=self.config_home) for fragment in self.fragments],
            "catalog": {
                "toolOverrides": self.tool_overrides,
                "toolAggregations": self.tool_aggregations,
                "hideTools": self.hide_tools,
            },
        }
        return payload


def write_intended_catalog(store: CatalogStore, *, destination: Path, runtime_overrides: Path | None = None) -> Path:
    payload = store.build_intended_catalog(destination=destination, runtime_overrides=runtime_overrides)
    write_json(destination, payload)
    return destination


def load_catalog_store(
    *,
    config_base: Path | None = None,
    include_bundles: bool = True,
    catalog_filenames: Sequence[str] | None = None,
) -> CatalogStore:
    home = (config_base or config_home()).expanduser()
    fragments = _discover_fragments(
        home,
        include_bundles=include_bundles,
        catalog_filter=set(name.strip() for name in catalog_filenames) if catalog_filenames else None,
    )
    overrides = _copy_payload(DEFAULT_CATALOG_FRAGMENT["tool_overrides"])
    aggregations = _copy_payload(DEFAULT_CATALOG_FRAGMENT["tool_aggregations"])
    hide_entries: list[dict[str, Any]] = []

    for fragment in fragments:
        payload = fragment.payload
        overrides_payload = payload.get("tool_overrides") or payload.get("toolOverrides")
        if isinstance(overrides_payload, Mapping):
            overrides = deep_merge(overrides, overrides_payload)

        aggregations_payload = payload.get("tool_aggregations") or payload.get("toolAggregations")
        if isinstance(aggregations_payload, Mapping):
            aggregations = merge_aggregation_payload(aggregations, aggregations_payload)

        hide_entries.extend(_normalize_hide_tools(payload.get("hide_tools") or payload.get("hideTools"), source=fragment.path))

    hidden = _dedupe_hide_tools(list(aggregations.get("hiddenTools", [])) + hide_entries)
    aggregations["hiddenTools"] = hidden

    disabled_servers = {name for name in overrides.get("servers", {}) if not server_enabled(name)}
    if disabled_servers:
        servers_block = overrides.setdefault("servers", {})
        for name in disabled_servers:
            entry = servers_block.get(name)
            if isinstance(entry, Mapping):
                entry = dict(entry)
            else:
                entry = {}
            entry["enabled"] = False
            servers_block[name] = entry

    return CatalogStore(
        tool_overrides=overrides,
        tool_aggregations=aggregations,
        hide_tools=hidden,
        fragments=fragments,
        config_home=home,
    )


def _discover_fragments(
    config_root: Path,
    *,
    include_bundles: bool,
    catalog_filter: set[str] | None,
) -> list[CatalogFragment]:
    fragments: list[CatalogFragment] = [
        CatalogFragment(
            path=config_root / CATALOG_DIRNAME / "_embedded_defaults.json",
            kind="embedded-defaults",
            name="embedded-defaults",
            payload=_copy_payload(DEFAULT_CATALOG_FRAGMENT),
            exists=True,
        )
    ]
    catalog_dir = config_root / CATALOG_DIRNAME
    if catalog_dir.exists():
        for path in sorted(catalog_dir.glob("*.json")):
            if not path.is_file():
                continue
            if catalog_filter and path.stem not in catalog_filter:
                continue
            fragments.append(_build_fragment(path, kind="catalog", name=path.stem))

    if include_bundles:
        bundle_roots = [config_root / BUNDLES_DIRNAME, config_root / CATALOG_DIRNAME / BUNDLES_DIRNAME]
        seen: set[str] = set()
        for bundle_root in bundle_roots:
            if not bundle_root.exists():
                continue
            for entry in sorted(bundle_root.iterdir()):
                if not entry.is_dir():
                    continue
                name = entry.name
                if name in seen:
                    continue
                seen.add(name)
                candidate = entry / "catalog.json"
                fragments.append(_build_fragment(candidate, kind="bundle", name=name))
    return fragments


def _build_fragment(path: Path, *, kind: Literal["catalog", "bundle"], name: str) -> CatalogFragment:
    exists = path.exists()
    payload = _load_fragment_payload(path) if exists else {}
    return CatalogFragment(path=path, kind=kind, name=name, payload=payload, exists=exists)


def _load_fragment_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in catalog fragment {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Catalog fragment {path} must contain a JSON object")
    return data


def _normalize_hide_tools(payload: Any, *, source: Path) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError(f"hide_tools entries in {source} must be a list of objects")
    normalized: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, Mapping):
            raise ValueError(f"hide_tools entry in {source} must be an object, got {type(entry)!r}")
        server = str(entry.get("server") or "").strip()
        tool = str(entry.get("tool") or "").strip()
        if not server or not tool:
            raise ValueError(f"hide_tools entry in {source} requires non-empty 'server' and 'tool'")
        reason_value = entry.get("reason")
        normalized_entry: dict[str, Any] = {"server": server, "tool": tool}
        if reason_value is not None:
            normalized_entry["reason"] = str(reason_value)
        normalized.append(normalized_entry)
    return normalized


def _dedupe_hide_tools(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        server = str(entry.get("server") or "").strip()
        tool = str(entry.get("tool") or "").strip()
        if not server or not tool:
            continue
        reason_value = entry.get("reason")
        normalized: dict[str, Any] = {"server": server, "tool": tool}
        if reason_value is not None:
            normalized["reason"] = str(reason_value)
        marker = f"{server}::{tool}"
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(normalized)
    return merged


def _relative_path(path: Path, config_root: Path) -> str | None:
    try:
        return str(path.relative_to(config_root))
    except ValueError:
        return None
