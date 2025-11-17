#!/usr/bin/env python3
"""
Capture the live MCP catalog from the running proxy and store it under
${STELAE_STATE_HOME}/live_catalog.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict
from urllib import request, error

DEFAULT_PROXY_BASE = os.environ.get("STELAE_PROXY_BASE", "http://127.0.0.1:9090")
_DEFAULT_CONFIG_HOME = Path(
    os.environ.get("STELAE_CONFIG_HOME", Path.home() / ".config" / "stelae")
)
DEFAULT_STATE_HOME = Path(
    os.environ.get("STELAE_STATE_HOME", _DEFAULT_CONFIG_HOME / ".state")
)
DEFAULT_OUTPUT = Path(os.environ.get("LIVE_CATALOG_PATH", DEFAULT_STATE_HOME / "live_catalog.json"))
DEFAULT_TIMEOUT = float(os.environ.get("STELAE_LIVE_CAPTURE_TIMEOUT", "20"))

JsonType = Dict[str, Any]
FetchFn = Callable[[str, float], JsonType]


def _isoformat(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_tools_list(proxy_base: str, timeout: float = DEFAULT_TIMEOUT) -> JsonType:
    """
    Invoke tools/list against the proxy's /mcp endpoint.
    """
    endpoint = proxy_base.rstrip("/") + "/mcp"
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": "live-catalog", "method": "tools/list"}
    ).encode("utf-8")
    req = request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # type: ignore[arg-type]
            status = getattr(resp, "status", 200)
            body = resp.read()
    except error.URLError as exc:  # pragma: no cover - wrapped for clarity
        raise RuntimeError(f"Failed to reach {endpoint}: {exc}") from exc
    if status != 200:
        raise RuntimeError(f"Proxy responded with HTTP {status} for tools/list")
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - unlikely but guarded
        raise RuntimeError("Proxy returned invalid JSON while capturing live catalog") from exc
    return parsed


@dataclass
class CaptureResult:
    output_path: Path
    tool_count: int


def capture_live_catalog(
    proxy_base: str,
    output_path: Path | None = None,
    *,
    fetch_fn: FetchFn = fetch_tools_list,
    timestamp: datetime | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> CaptureResult:
    """
    Fetch tools/list and persist the snapshot.
    """
    target = Path(output_path) if output_path else DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    captured_at = timestamp or datetime.now(timezone.utc)
    response = fetch_fn(proxy_base, timeout)
    tools = response.get("result", {}).get("tools", []) if isinstance(response, dict) else []
    tool_count = len(tools) if isinstance(tools, list) else 0
    payload = {
        "captured_at": _isoformat(captured_at),
        "proxy_base": proxy_base.rstrip("/"),
        "tool_count": tool_count,
        "tools_list": response,
    }
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(target)
    return CaptureResult(output_path=target, tool_count=tool_count)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture the live MCP catalog snapshot.")
    parser.add_argument(
        "--proxy-base",
        default=DEFAULT_PROXY_BASE,
        help="Base URL for the proxy (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to write live_catalog.json (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = capture_live_catalog(
            proxy_base=args.proxy_base,
            output_path=Path(args.output),
            timeout=args.timeout,
        )
    except Exception as exc:  # pragma: no cover - CLI integration
        print(f"[capture_live_catalog] ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"[capture_live_catalog] Wrote {result.tool_count} tools to {result.output_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
