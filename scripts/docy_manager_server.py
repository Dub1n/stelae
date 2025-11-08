#!/usr/bin/env python3
"""MCP server + CLI wrapper for managing Docy documentation sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from mcp.server import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.docy_catalog import DocyCatalog

CATALOG_PATH = Path(os.getenv("STELAE_DOCY_CATALOG", ROOT / "config" / "docy_sources.json"))
URL_FILE_PATH = Path(os.getenv("STELAE_DOCY_URL_FILE", ROOT / ".docy.urls"))
OPERATIONS = {"list_sources", "add_source", "remove_source", "sync_catalog"}

app = FastMCP(
    name="docy-manager",
    instructions="Manage Docy documentation sources declaratively.",
)


def _parse_tags(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [segment.strip() for segment in value.split(",") if segment.strip()]
    raise ValueError("tags must be a list or comma-separated string")


def _execute(operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if operation not in OPERATIONS:
        raise ValueError(f"Unsupported operation '{operation}'")
    catalog = DocyCatalog.load(CATALOG_PATH)
    if operation == "list_sources":
        return {
            "sources": catalog.list_sources(),
            "catalogPath": str(CATALOG_PATH),
            "urlFile": str(URL_FILE_PATH),
        }
    if operation == "sync_catalog":
        lines = catalog.render_urls(URL_FILE_PATH)
        return {
            "status": "rendered",
            "lineCount": len(lines),
            "urlFile": str(URL_FILE_PATH),
        }

    dry_run = bool(params.get("dry_run"))

    if operation == "add_source":
        url = params.get("url")
        if not url:
            raise ValueError("add_source requires 'url'")
        entry, action = catalog.add_source(
            url=str(url),
            title=params.get("title"),
            source_id=params.get("id"),
            tags=_parse_tags(params.get("tags")),
            notes=params.get("notes"),
            enabled=params.get("enabled", True),
            refresh_hours=params.get("refresh_hours"),
            allow_update=bool(params.get("allow_update", False)),
        )
        render_info: Dict[str, Any] = {"status": "dry_run", "lineCount": 0}
        if not dry_run:
            catalog.save()
            lines = catalog.render_urls(URL_FILE_PATH)
            render_info = {"status": "rendered", "lineCount": len(lines)}
        return {
            "action": action,
            "source": entry.to_dict(),
            "dryRun": dry_run,
            "render": render_info,
        }

    if operation == "remove_source":
        identifier = params.get("id")
        url = params.get("url")
        if not identifier and not url:
            raise ValueError("remove_source requires 'id' or 'url'")
        removed = catalog.remove_source(source_id=identifier, url=url)
        render_info = {"status": "dry_run", "lineCount": 0}
        if not dry_run:
            catalog.save()
            lines = catalog.render_urls(URL_FILE_PATH)
            render_info = {"status": "rendered", "lineCount": len(lines)}
        return {
            "removed": removed.to_dict(),
            "dryRun": dry_run,
            "render": render_info,
        }

    raise ValueError(f"Unhandled operation '{operation}'")


@app.tool(name="manage_docy", description="Manage Docy documentation catalog (list/add/remove/sync).")
async def manage_docy(operation: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _execute(operation, params or {})


def _run_cli(operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
    return _execute(operation, params)


def main() -> None:
    parser = argparse.ArgumentParser(description="Docy manager MCP server / CLI")
    parser.add_argument("--cli", action="store_true", help="Run a single operation and exit instead of starting the MCP server")
    parser.add_argument("--operation", choices=sorted(OPERATIONS), help="Operation to perform (required in CLI mode)")
    parser.add_argument("--params", help="JSON blob with operation parameters")
    parser.add_argument("--params-file", type=Path, help="Path to JSON file with operation parameters")
    args = parser.parse_args()
    if args.cli:
        if not args.operation:
            parser.error("--operation is required in --cli mode")
        raw_params: Dict[str, Any] = {}
        if args.params_file:
            raw_params = json.loads(args.params_file.read_text(encoding="utf-8"))
        elif args.params:
            raw_params = json.loads(args.params)
        result = _run_cli(args.operation, raw_params)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    app.run_stdio()


if __name__ == "__main__":
    main()
