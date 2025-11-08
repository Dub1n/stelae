#!/usr/bin/env python3
"""Environment-driven CLI wrapper for manage_stelae discover_servers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.integrator.core import StelaeIntegratorService  # noqa: E402


def _as_bool(value: str | None, default: bool) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _maybe_number(value: str | None, caster, *, label: str) -> int | float | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return caster(text)
    except ValueError:
        raise SystemExit(f"Invalid {label}: {value}")


def _build_payload() -> dict[str, object]:
    payload: dict[str, object] = {}
    query = os.environ.get("DISCOVER_QUERY", "").strip()
    if query:
        payload["query"] = query
    tags = os.environ.get("DISCOVER_TAGS", "").strip()
    if tags:
        payload["tags"] = tags
    preset = os.environ.get("DISCOVER_PRESET", "").strip()
    if preset:
        payload["preset"] = preset
    limit = _maybe_number(os.environ.get("DISCOVER_LIMIT"), int, label="DISCOVER_LIMIT")
    if limit is not None:
        payload["limit"] = max(1, limit)
    min_score = _maybe_number(
        os.environ.get("DISCOVER_MIN_SCORE"), float, label="DISCOVER_MIN_SCORE"
    )
    if min_score is not None:
        payload["min_score"] = min_score
    payload["append"] = _as_bool(os.environ.get("DISCOVER_APPEND"), True)
    payload["dry_run"] = _as_bool(os.environ.get("DISCOVER_DRY_RUN"), False)
    return payload


def main() -> None:
    payload = _build_payload()
    service = StelaeIntegratorService()
    result = service.run("discover_servers", payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
