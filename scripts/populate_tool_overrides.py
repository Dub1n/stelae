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
from stelae_lib.integrator.tool_overrides import ToolOverridesStore

DEFAULT_PROXY_PATH = Path("config/proxy.json")
DEFAULT_OVERRIDES_PATH = Path("config/tool_overrides.json")
DEFAULT_PROXY_TIMEOUT = 15.0


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


def _extract_servers(tool_payload: Mapping[str, Any]) -> list[str]:
    meta = tool_payload.get("x-stelae")
    servers: list[str] = []
    if isinstance(meta, Mapping):
        raw = meta.get("servers")
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, str) and entry:
                    servers.append(entry)
    server_field = tool_payload.get("server") or tool_payload.get("serverName")
    if isinstance(server_field, str) and server_field:
        if server_field not in servers:
            servers.append(server_field)
    return servers


def record_tool(
    overrides: ToolOverridesStore,
    servers: Sequence[str],
    tool_payload: Mapping[str, Any],
    keys: Sequence[str],
) -> bool:
    name = tool_payload.get("name")
    if not isinstance(name, str) or not name or not servers:
        return False
    changed = False
    for server in servers:
        for key in keys:
            changed |= overrides.ensure_schema(server, name, key, tool_payload.get(key))
    return changed


async def populate_from_stdio(
    config: Dict[str, Any],
    overrides: OverridesStore,
    target_servers: set[str],
    keys: Sequence[str],
    quiet: bool,
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
            if record_tool(overrides, (name,), payload, keys):
                total_updates += 1
                if not quiet:
                    print(f"[update] {name}.{tool.name} - recorded schema")
    return total_updates


async def populate_from_proxy_url(
    proxy_url: str,
    overrides: OverridesStore,
    keys: Sequence[str],
    timeout: float,
    quiet: bool,
) -> int:
    tools = await fetch_tools_via_proxy(proxy_url, timeout)
    total_updates = 0
    for entry in tools:
        servers = _extract_servers(entry)
        if not servers:
            print(f"[warn] tools/list entry {entry.get('name')} missing x-stelae server metadata", file=sys.stderr)
            continue
        if record_tool(overrides, servers, entry, keys):
            total_updates += 1
            if not quiet:
                joined = ",".join(servers)
                print(f"[update] proxy://{entry.get('name')} ({joined}) - recorded schema")
    return total_updates


async def main() -> None:
    parser = argparse.ArgumentParser(description="Populate tool override schemas from downstream MCP servers.")
    parser.add_argument("--proxy", default=str(DEFAULT_PROXY_PATH), help="Path to rendered config/proxy.json")
    parser.add_argument("--proxy-url", help="Optional MCP endpoint (e.g. http://127.0.0.1:9090/mcp) to reuse an existing tools/list result")
    parser.add_argument("--proxy-timeout", type=float, default=DEFAULT_PROXY_TIMEOUT, help="Timeout (seconds) for proxy HTTP requests")
    parser.add_argument("--overrides", default=str(DEFAULT_OVERRIDES_PATH), help="Path to config/tool_overrides.json")
    parser.add_argument("--servers", nargs="*", help="Optional subset of server names to scan")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-tool update logs; still prints the final summary")
    args = parser.parse_args()

    overrides = ToolOverridesStore(Path(args.overrides))
    keys: Sequence[str] = ("inputSchema", "outputSchema")

    if args.proxy_url:
        if args.servers:
            parser.error("--servers cannot be combined with --proxy-url")
        total_updates = await populate_from_proxy_url(args.proxy_url, overrides, keys, args.proxy_timeout, args.quiet)
    else:
        config = load_proxy_config(Path(args.proxy))
        target_servers = set(args.servers or [])
        total_updates = await populate_from_stdio(config, overrides, target_servers, keys, args.quiet)

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
