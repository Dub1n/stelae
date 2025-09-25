#!/usr/bin/env python3
"""Shim MCP server that exposes canonical  and  tools."""

import asyncio
import os
from typing import List, Optional

import httpx
from mcp import Server, tool, types

MCP_PROXY_BASE = os.getenv("STELAE_MCP_PROXY_BASE", "http://localhost:9090")
MCP_GREP_PATH = os.getenv("STELAE_MCP_GREP_PATH", "/rg/mcp")
DOCY_PATH = os.getenv("STELAE_DOCY_PATH", "/docs/mcp")
SEARCH_ROOT = os.getenv("STELAE_SEARCH_ROOT", ".")
MAX_BYTES = int(os.getenv("STELAE_MAX_BYTES", "1048576"))

server = Server("stelae-search-fetch")

async def _call_mcp(path: str, tool_name: str, arguments: dict) -> dict:
    url = f"{MCP_PROXY_BASE.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "type": "callTool",
            "toolName": tool_name,
            "arguments": arguments,
        }
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

@tool(
    name="search",
    description="Search repository text/code via mcp-grep.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "globs": {"type": "array", "items": {"type": "string"}},
            "max_results": {"type": "integer", "default": 50},
        },
        "required": ["query"],
    },
)
async def search(query: str, globs: Optional[List[str]] = None, max_results: int = 50):
    arguments = {
        "query": query,
        "paths": [SEARCH_ROOT],
        "globs": globs or [],
        "max_results": max_results,
    }
    data = await _call_mcp(MCP_GREP_PATH, "search", arguments)
    return types.JsonContent(type="json", data=data)

@tool(
    name="fetch",
    description="Fetch documentation or remote content via Docy.",
    input_schema={
        "type": "object",
        "properties": {
            "target": {"type": "string"},
            "format": {"type": "string", "enum": ["markdown", "html", "raw"], "default": "markdown"},
        },
        "required": ["target"],
    },
)
async def fetch(target: str, format: str = "markdown"):
    arguments = {"url": target, "format": format, "max_bytes": MAX_BYTES}
    data = await _call_mcp(DOCY_PATH, "fetch_document", arguments)
    return types.JsonContent(type="json", data=data)

async def main():
    await server.run_stdio()

if __name__ == "__main__":
    asyncio.run(main())
