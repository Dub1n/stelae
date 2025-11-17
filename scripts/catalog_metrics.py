#!/usr/bin/env python3
"""Emit simple catalog drift/health metrics."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts import catalog_io
from stelae_lib.config_overlays import require_home_path, runtime_path, write_json


def main() -> None:
    intended = catalog_io.load_intended()
    live = catalog_io.load_live()
    diff = catalog_io.diff_catalogs(intended, live)

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "intended_tool_count": len(catalog_io.tool_names(intended)),
        "live_tool_count": len(catalog_io.tool_names(live)),
        "missing": sorted(diff["missing"]),
        "extra": sorted(diff["extra"]),
    }
    path = runtime_path("catalog_metrics.json")
    try:
        metrics_path = require_home_path(
            "CATALOG_METRICS_PATH",
            default=Path(path),
            description="Catalog metrics",
            allow_config=False,
            allow_state=True,
            create=True,
        )
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(f"[catalog-metrics] {exc}") from exc

    write_json(str(metrics_path), metrics)
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
