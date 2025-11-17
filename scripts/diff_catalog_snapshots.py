#!/usr/bin/env python3
"""CLI wrapper for catalog_io.diff_catalogs."""

from __future__ import annotations

import argparse
import sys

from scripts.catalog_io import diff_catalogs, load_intended, load_live, _human_list


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Diff intended and live catalog snapshots.")
    parser.add_argument("--intended", help="Path to intended_catalog.json (default: state_home/intended_catalog.json)")
    parser.add_argument("--live", help="Path to live_catalog.json (default: state_home/live_catalog.json)")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit non-zero when missing/extra tools are detected")
    args = parser.parse_args(argv)

    intended_payload = load_intended(args.intended)
    live_payload = load_live(args.live)
    diff = diff_catalogs(intended_payload, live_payload)

    print(f"missing: {_human_list(diff['missing'])}")
    print(f"extra: {_human_list(diff['extra'])}")

    if args.fail_on_drift and (diff["missing"] or diff["extra"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
