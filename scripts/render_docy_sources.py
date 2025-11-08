#!/usr/bin/env python3
"""Render config/docy_sources.json into the .docy.urls file Docy consumes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.docy_catalog import DocyCatalog

DEFAULT_CATALOG = ROOT / "config" / "docy_sources.json"
DEFAULT_OUTPUT = ROOT / ".docy.urls"


def render(catalog_path: Path, output_path: Path) -> int:
    catalog = DocyCatalog.load(catalog_path)
    lines = catalog.render_urls(output_path)
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Docy catalog into .docy.urls")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Path to config/docy_sources.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to .docy.urls")
    args = parser.parse_args()
    count = render(args.catalog, args.output)
    print(f"Rendered Docy catalog to {args.output} ({count} lines)")


if __name__ == "__main__":
    main()
