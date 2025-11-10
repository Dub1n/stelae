#!/usr/bin/env python3
"""Run 1mcp catalogue searches and optionally seed discovered_servers.json."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from stelae_lib.fileio import atomic_write
from stelae_lib.integrator.one_mcp import OneMCPDiscovery, OneMCPDiscoveryError

DEFAULT_OUTPUT = Path(
    os.getenv("STELAE_DISCOVERY_PATH")
    or (Path(os.getenv("STELAE_CONFIG_HOME", Path.home() / ".config" / "stelae")) / "discovered_servers.json")
)


def load_existing(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - user data
        raise SystemExit(f"Existing discovery file {path} contains invalid JSON: {exc}")


def persist(path: Path, data: List[Dict[str, Any]]) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the 1mcp catalogue and update discovery cache")
    parser.add_argument("query", nargs="?", default="", help="Free-text query (defaults to 'mcp')")
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of results to record")
    parser.add_argument("--min-score", type=float, help="Minimum score filter")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Discovery cache path")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing entries instead of merging")
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing to disk")
    args = parser.parse_args()

    try:
        discovery = OneMCPDiscovery()
    except OneMCPDiscoveryError as exc:  # pragma: no cover - environment check
        raise SystemExit(str(exc))

    results = discovery.search(args.query, limit=args.limit, min_score=args.min_score)
    if not results:
        print("No results")
        return

    base = [] if args.overwrite else load_existing(args.output)
    by_name: Dict[str, Dict[str, Any]] = {}
    for entry in base:
        if isinstance(entry, dict) and entry.get("name"):
            by_name[entry["name"]] = entry
    added = 0
    for result in results:
        payload = result.to_entry(args.query or None)
        current = by_name.get(payload["name"])
        if current and current.get("transport") != "metadata":
            continue
        by_name[payload["name"]] = payload
        added += 1
        print(f"[result] {payload['name']}: {payload.get('description','')}")
    ordered = sorted(by_name.values(), key=lambda item: item.get("name", ""))
    if args.dry_run:
        print(f"Dry-run: {added} entries would be written to {args.output}")
        return
    persist(args.output, ordered)
    print(f"Wrote {len(ordered)} entries ({added} updated) to {args.output}")


if __name__ == "__main__":
    main()
