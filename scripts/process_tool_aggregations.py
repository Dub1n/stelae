#!/usr/bin/env python3
"""Validate tool aggregation config, update overrides, and emit the intended catalog."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.catalog.store import load_catalog_store, write_intended_catalog
from stelae_lib.config_overlays import ensure_config_home_scaffold, require_home_path, runtime_path
from stelae_lib.integrator.tool_aggregations import ToolAggregationConfig, validate_aggregation_schema
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


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

    if args.check_only:
        fragment_count = len(catalog_store.fragments)
        print(
            f"Validated merged catalog from {fragment_count} fragment(s) with {len(config.aggregations)} aggregations and {len(config.all_hidden_tools())} hidden tools."
        )
        return

    store = ToolOverridesStore(
        overrides_base,
        overlay_path=overrides_base,
        runtime_path=runtime_path_value,
        target=target,
    )
    changed = config.apply_overrides(store)
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
        write_intended_catalog(
            catalog_store,
            destination=intended_path,
            runtime_overrides=runtime_path_value,
        )
        print(f"[process-tool-aggregations] overrides_base={overrides_base} runtime={runtime_path_value} intended={intended_path} fragments={len(catalog_store.fragments)}")


if __name__ == "__main__":
    main()
