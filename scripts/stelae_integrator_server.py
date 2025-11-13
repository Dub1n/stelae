#!/usr/bin/env python3
"""MCP server / CLI that installs discovered MCP servers into the Stelae stack."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from mcp.server import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.integrator import StelaeIntegratorService  # noqa: E402

app = FastMCP(
    name="stelae-integrator",
    instructions="Install and reconcile MCP servers discovered by 1mcp.",
)


def _build_service() -> StelaeIntegratorService:
    discovery_path = Path(
        os.getenv("STELAE_DISCOVERY_PATH")
        or (Path(os.getenv("STELAE_CONFIG_HOME", Path.home() / ".config" / "stelae")) / "discovered_servers.local.json")
    )
    template_path = Path(os.getenv("STELAE_PROXY_TEMPLATE", ROOT / "config" / "proxy.template.json"))
    overrides_path = Path(os.getenv("STELAE_TOOL_OVERRIDES", ROOT / "config" / "tool_overrides.json"))
    return StelaeIntegratorService(
        root=ROOT,
        discovery_path=discovery_path,
        template_path=template_path,
        overrides_path=overrides_path,
    )


def _execute(operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
    service = _build_service()
    return service.run(operation, params)


@app.tool(name="manage_stelae", description="Install/remove MCP servers discovered by 1mcp or manual JSON blobs.")
async def manage_stelae(operation: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _execute(operation, params or {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Stelae integrator MCP server / CLI dispatcher")
    parser.add_argument("--cli", action="store_true", help="Run a one-shot operation and exit")
    parser.add_argument("--operation", help="Operation to run (required with --cli)")
    parser.add_argument("--params", help="Inline JSON parameters for the operation")
    parser.add_argument("--params-file", type=Path, help="Path to JSON file with params")
    args = parser.parse_args()
    if args.cli:
        if not args.operation:
            parser.error("--operation is required when using --cli")
        payload: Dict[str, Any] = {}
        if args.params_file:
            payload = json.loads(args.params_file.read_text(encoding="utf-8"))
        elif args.params:
            payload = json.loads(args.params)
        result = _execute(args.operation, payload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    # FastMCP auto-selects stdio when run without extra transport flags, matching
    # how every other local server launches under the proxy.
    app.run()


if __name__ == "__main__":
    main()
