#!/usr/bin/env python3
"""Validate tool aggregation config and update overrides."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import config_home, overlay_path_for
from stelae_lib.integrator.tool_aggregations import load_tool_aggregation_config
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate tool aggregation config and update overrides")
    parser.add_argument(
        "--config",
        default=ROOT / "config" / "tool_aggregations.json",
        type=Path,
        help="Path to tool aggregation config",
    )
    parser.add_argument(
        "--schema",
        default=None,
        type=Path,
        help="Optional explicit schema path (defaults to config/tool_aggregations.schema.json)",
    )
    parser.add_argument(
        "--overrides",
        default=ROOT / "config" / "tool_overrides.json",
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
        help="Merged overrides destination (defaults to ${TOOL_OVERRIDES_PATH} or ~/.config/stelae/tool_overrides.json)",
    )
    parser.add_argument(
        "--persist-overlay",
        action="store_true",
        help="Write aggregation results into the overlay file (used when refreshing tracked data)",
    )
    args = parser.parse_args()

    config = load_tool_aggregation_config(args.config, schema_path=args.schema)
    if args.check_only:
        print(
            f"Validated {args.config} with {len(config.aggregations)} aggregations and {len(config.all_hidden_tools())} hidden tools."
        )
        return

    runtime_default = args.output or os.getenv("TOOL_OVERRIDES_PATH") or (config_home() / "tool_overrides.json")
    target_mode = "overlay" if args.persist_overlay else "runtime"
    store = ToolOverridesStore(
        args.overrides,
        overlay_path=overlay_path_for(args.overrides),
        runtime_path=Path(runtime_default),
        target=target_mode,
    )
    changed = config.apply_overrides(store)
    if changed:
        store.write()
        print(
            f"Applied aggregation overrides for {len(config.aggregations)} tools and {len(config.all_hidden_tools())} hidden entries."
        )
    else:
        print("Aggregation overrides already up to date.")


if __name__ == "__main__":
    main()
