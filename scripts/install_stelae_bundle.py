#!/usr/bin/env python3
"""Install optional Stelae bundles (Docy, Memory, aggregator, etc.)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.bundles import install_bundle, load_bundle  # noqa: E402


def _log_progress(message: str) -> None:
    print(message, flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install optional Stelae bundle descriptors")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=ROOT / "config" / "bundles" / "starter_bundle.json",
        help="Path to the bundle JSON (default: config/bundles/starter_bundle.json)",
    )
    parser.add_argument(
        "--server",
        action="append",
        dest="servers",
        help="Limit installation to the provided server name (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing overlays or restarting")
    parser.add_argument("--no-restart", action="store_true", help="Skip render/restart even if files change")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing servers without requiring a manual manage_stelae run",
    )
    return parser.parse_args()


def _print_list(label: str, items: Sequence[str]) -> None:
    if not items:
        return
    joined = ", ".join(items)
    print(f"{label}: {joined}")


def main() -> None:
    args = _parse_args()
    bundle_path = args.bundle if args.bundle.is_absolute() else (ROOT / args.bundle)
    bundle = load_bundle(bundle_path)
    summary = install_bundle(
        bundle,
        server_filter=args.servers,
        dry_run=args.dry_run,
        restart=not args.no_restart,
        force=args.force,
        log=_log_progress,
    )
    print(f"Bundle '{bundle.get('name', bundle_path.name)}' ({bundle_path})")
    if args.servers:
        _print_list("Filtered servers", [srv for srv in args.servers if srv])
    _print_list("Installed", summary["installed"])
    _print_list("Skipped", summary["skipped"])
    if summary["overlays"]:
        overlay_paths = [entry["path"] for entry in summary["overlays"]]
        prefix = "Would update" if summary["dryRun"] else "Updated"
        _print_list(f"{prefix} overlays", overlay_paths)
    if summary["commands"]:
        _print_list("Ran commands", [" ".join(cmd) for cmd in summary["commands"]])
    if summary["errors"]:
        print("Errors:")
        for err in summary["errors"]:
            print(f"  - {err.get('name')}: {err.get('error')}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
