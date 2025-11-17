#!/usr/bin/env python3
"""Prune catalog/descriptors history files according to env limits."""

from __future__ import annotations

import os
from pathlib import Path

from stelae_lib.config_overlays import require_home_path, runtime_path


def _prune(prefix: str, keep: int) -> int:
    if keep < 0:
        return 0
    base = Path(runtime_path(prefix + ".json"))
    try:
        base = require_home_path(
            "CATALOG_HISTORY_BASE",
            default=base,
            description=prefix,
            allow_config=False,
            allow_state=True,
            create=True,
        )
    except ValueError:
        return 0
    dir_path = base.parent
    stem = base.stem + "."
    removed = 0
    history = sorted(
        p for p in dir_path.glob(f"{stem}*.json") if p.name != base.name
    )
    if len(history) <= keep:
        return 0
    for path in history[: len(history) - keep]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def main() -> None:
    live_keep = int(os.getenv("STELAE_LIVE_HISTORY_COUNT", "5") or 5)
    desc_keep = int(os.getenv("STELAE_DESCRIPTOR_HISTORY_COUNT", "3") or 3)
    removed_live = _prune("live_catalog", live_keep)
    removed_desc = _prune("live_descriptors", desc_keep)
    print(f"pruned_live={removed_live} pruned_descriptors={removed_desc}")


if __name__ == "__main__":
    main()
