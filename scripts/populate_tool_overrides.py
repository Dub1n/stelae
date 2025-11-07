#!/usr/bin/env python3
"""Populate missing tool schemas in config/tool_overrides.json by querying MCP servers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import types

DEFAULT_PROXY_PATH = Path("config/proxy.json")
DEFAULT_OVERRIDES_PATH = Path("config/tool_overrides.json")


class OverridesStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"Override file {self.path} is invalid JSON: {exc}")
        return {}

    def ensure_schema(self, server: str, tool: str, key: str, schema: Any) -> bool:
        if not schema:
            return False
        servers = self.data.setdefault("servers", {})
        server_block = servers.setdefault(server, {})
        server_block.setdefault("enabled", True)
        tools = server_block.setdefault("tools", {})
        tool_block = tools.setdefault(tool, {"enabled": True})
        if key in tool_block:
            return False
        tool_block[key] = json.loads(json.dumps(schema))
        return True

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.path)


async def fetch_tools(command: str, args: Iterable[str], env: Dict[str, str] | None) -> list[types.Tool]:
    params = StdioServerParameters(command=command, args=list(args), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return list(result.tools)


def load_proxy_config(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"proxy config {path} not found")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"proxy config {path} invalid JSON: {exc}")


def iter_stdio_servers(config: Dict[str, Any]) -> Iterable[tuple[str, Dict[str, Any]]]:
    servers = config.get("mcpServers", {})
    for name, entry in servers.items():
        server_type = entry.get("type")
        if server_type and server_type != "stdio":
            continue
        command = entry.get("command")
        if not command:
            continue
        yield name, entry


def copy_schema(schema: Any) -> Any:
    return json.loads(json.dumps(schema))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate tool override schemas from downstream MCP servers.")
    parser.add_argument("--proxy", default=str(DEFAULT_PROXY_PATH), help="Path to rendered config/proxy.json")
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES_PATH), help="Path to config/tool_overrides.json")
    parser.add_argument("--servers", nargs="*", help="Optional subset of server names to scan")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    args = parser.parse_args()

    config = load_proxy_config(Path(args.proxy))
    overrides = OverridesStore(Path(args.overrides))
    target_servers = set(args.servers or [])

    total_updates = 0
    for name, entry in iter_stdio_servers(config):
        if target_servers and name not in target_servers:
            continue
        command = entry["command"]
        server_args = entry.get("args", [])
        try:
            tools = await fetch_tools(command, server_args, entry.get("env"))
        except Exception as exc:  # pragma: no cover - relies on external binaries
            print(f"[warn] Failed to load tools for {name}: {exc}", file=sys.stderr)
            continue
        for tool in tools:
            payload = tool.model_dump(mode="json")
            changed = False
            for key in ("inputSchema", "outputSchema"):
                changed |= overrides.ensure_schema(name, tool.name, key, payload.get(key))
            if changed:
                total_updates += 1
                print(f"[update] {name}.{tool.name} - recorded schema")

    if total_updates == 0:
        print("No schema updates required")
        return
    if args.dry_run:
        print(f"Dry-run: {total_updates} missing schemas detected; rerun without --dry-run to write")
        return
    overrides.write()
    print(f"Wrote updated overrides to {args.overrides} ({total_updates} tool entries updated)")


if __name__ == "__main__":
    asyncio.run(main())
