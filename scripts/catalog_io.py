#!/usr/bin/env python3
"""Shared helpers for loading and diffing intended/live catalog snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from stelae_lib.config_overlays import require_home_path, runtime_path, state_home


def _default_intended_path() -> Path:
    return Path(runtime_path("intended_catalog.json"))


def _default_live_path() -> Path:
    return Path(runtime_path("live_catalog.json"))


def _read_json(path: Path) -> Any:
    data = path.read_text(encoding="utf-8")
    return json.loads(data)


def _require_under_homes(path: Path) -> Path:
    # allow either config_home or state_home; require_home_path enforces both
    try:
        return require_home_path("CATALOG_PATH", default=path, description="Catalog snapshot", allow_config=True, allow_state=True)
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"[catalog-io] {exc}") from exc


def load_intended(path: str | Path | None = None) -> Any:
    """Load intended catalog snapshot (dict)."""
    target = Path(path) if path else _default_intended_path()
    target = _require_under_homes(target)
    return _read_json(target)


def load_live(path: str | Path | None = None) -> Any:
    """Load live catalog snapshot (dict)."""
    target = Path(path) if path else _default_live_path()
    target = _require_under_homes(target)
    return _read_json(target)


def tool_names(payload: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    tools = payload.get("tools")
    if isinstance(tools, list):
        for entry in tools:
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name")
            if isinstance(name, str):
                names.add(name)
    catalog = payload.get("catalog")
    if isinstance(catalog, Mapping):
        catalog_tools = catalog.get("tools")
        if isinstance(catalog_tools, list):
            for entry in catalog_tools:
                if not isinstance(entry, Mapping):
                    continue
                name = entry.get("name")
                if isinstance(name, str):
                    names.add(name)
    return names


def diff_catalogs(intended: Mapping[str, Any], live: Mapping[str, Any]) -> dict[str, set[str]]:
    intended_names = tool_names(intended)
    live_names = tool_names(live)
    missing = intended_names - live_names
    extra = live_names - intended_names
    return {"missing": missing, "extra": extra}


def _human_list(values: Iterable[str]) -> str:
    return ", ".join(sorted(values)) if values else "∅"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Diff intended and live catalog snapshots.")
    parser.add_argument("--intended", type=Path, default=None, help="Path to intended_catalog.json (default: state_home/intended_catalog.json)")
    parser.add_argument("--live", type=Path, default=None, help="Path to live_catalog.json (default: state_home/live_catalog.json)")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit non-zero when missing/extra tools are detected")
    args = parser.parse_args(argv)

    try:
        intended_payload = load_intended(args.intended)
    except Exception as exc:  # pragma: no cover - surfaced in CLI
        raise SystemExit(f"[diff-catalog] failed to load intended catalog: {exc}") from exc
    try:
        live_payload = load_live(args.live)
    except Exception as exc:  # pragma: no cover - surfaced in CLI
        raise SystemExit(f"[diff-catalog] failed to load live catalog: {exc}") from exc

    diff = diff_catalogs(intended_payload, live_payload)
    print(f"missing: {_human_list(diff['missing'])}")
    print(f"extra: {_human_list(diff['extra'])}")
    if args.fail_on_drift and (diff["missing"] or diff["extra"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
