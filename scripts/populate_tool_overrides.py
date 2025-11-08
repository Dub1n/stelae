#!/usr/bin/env python3
"""Populate missing tool schemas in config/tool_overrides.json by querying MCP servers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import httpx
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

DEFAULT_PROXY_PATH = Path("config/proxy.json")
DEFAULT_OVERRIDES_PATH = Path("config/tool_overrides.json")
DEFAULT_PROXY_TIMEOUT = 15.0


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

    def ensure_schema(self, server: str | None, tool: str, key: str, schema: Any) -> bool:
        if not schema or not tool:
            return False
        payload = json.loads(json.dumps(schema))
        if server:
            servers = self.data.setdefault("servers", {})
            server_block = servers.setdefault(server, {})
            server_block.setdefault("enabled", True)
            tools = server_block.setdefault("tools", {})
            tool_block = tools.setdefault(tool, {"enabled": True})
        else:
            tools = self.data.setdefault("tools", {})
            tool_block = tools.setdefault(tool, {"enabled": True})
        if key in tool_block:
            return False
        tool_block[key] = payload
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


async def fetch_tools_via_proxy(proxy_url: str, timeout: float) -> list[Mapping[str, Any]]:
    payload = {"jsonrpc": "2.0", "id": "populate", "method": "tools/list"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(proxy_url, json=payload)
        response.raise_for_status()
    data = response.json()
    try:
        tools = data["result"]["tools"]
    except KeyError as exc:
        raise SystemExit(f"Proxy at {proxy_url} did not return tools/list payload: missing {exc}")
    if not isinstance(tools, list):
        raise SystemExit(f"Proxy at {proxy_url} returned malformed tools list")
    normalized: list[Mapping[str, Any]] = []
    for entry in tools:
        if isinstance(entry, Mapping):
            normalized.append(entry)
    return normalized


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


def record_tool(overrides: OverridesStore, server: str | None, tool_payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    name = tool_payload.get("name")
    if not isinstance(name, str) or not name:
        return False
    changed = False
    for key in keys:
        changed |= overrides.ensure_schema(server, name, key, tool_payload.get(key))
    return changed


async def populate_from_stdio(
    config: Dict[str, Any],
    overrides: OverridesStore,
    target_servers: set[str],
    keys: Sequence[str],
) -> int:
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
            if record_tool(overrides, name, payload, keys):
                total_updates += 1
                print(f"[update] {name}.{tool.name} - recorded schema")
    return total_updates


async def populate_from_proxy_url(
    proxy_url: str,
    overrides: OverridesStore,
    keys: Sequence[str],
    timeout: float,
) -> int:
    tools = await fetch_tools_via_proxy(proxy_url, timeout)
    total_updates = 0
    for entry in tools:
        if record_tool(overrides, None, entry, keys):
            total_updates += 1
            print(f"[update] proxy://{entry.get('name')} - recorded schema")
    return total_updates


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate tool override schemas from downstream MCP servers.")
    parser.add_argument("--proxy", default=str(DEFAULT_PROXY_PATH), help="Path to rendered config/proxy.json")
    parser.add_argument("--proxy-url", help="Optional MCP endpoint (e.g. http://127.0.0.1:9090/mcp) to reuse an existing tools/list result")
    parser.add_argument("--proxy-timeout", type=float, default=DEFAULT_PROXY_TIMEOUT, help="Timeout (seconds) for proxy HTTP requests")
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES_PATH), help="Path to config/tool_overrides.json")
    parser.add_argument("--servers", nargs="*", help="Optional subset of server names to scan")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    args = parser.parse_args()

    overrides = OverridesStore(Path(args.overrides))
    keys: Sequence[str] = ("inputSchema", "outputSchema")

    if args.proxy_url:
        if args.servers:
            parser.error("--servers cannot be combined with --proxy-url")
        total_updates = await populate_from_proxy_url(args.proxy_url, overrides, keys, args.proxy_timeout)
    else:
        config = load_proxy_config(Path(args.proxy))
        target_servers = set(args.servers or [])
        total_updates = await populate_from_stdio(config, overrides, target_servers, keys)

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
