#!/usr/bin/env python3
"""Validate tool aggregation config and update overrides."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    args = parser.parse_args()

    config = load_tool_aggregation_config(args.config, schema_path=args.schema)
    if args.check_only:
        print(
            f"Validated {args.config} with {len(config.aggregations)} aggregations and {len(config.all_hidden_tools())} hidden tools."
        )
        return

    store = ToolOverridesStore(args.overrides)
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
