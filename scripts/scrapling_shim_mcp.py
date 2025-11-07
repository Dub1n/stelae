#!/usr/bin/env python3
from __future__ import annotations

import asyncio, json, os, shlex, sys
from types import MethodType
from typing import Any, Iterable, List, Sequence

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import FastMCP

COMMAND = os.getenv("SCRAPLING_SHIM_COMMAND", os.getenv("SCRAPLING_COMMAND", "uvx"))
ARGS: Sequence[str] = shlex.split(os.getenv("SCRAPLING_SHIM_ARGS", os.getenv("SCRAPLING_ARGS", "scrapling-fetch-mcp")) or "scrapling-fetch-mcp")
TARGET_TOOLS = {"s_fetch_page", "s_fetch_pattern"}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"metadata": {"type": "object", "additionalProperties": True}, "content": {"type": "string"}},
    "required": ["metadata", "content"],
}

app = FastMCP(name="scrapling-shim", instructions="Wraps scrapling-fetch outputs with structured metadata for MCP clients.")


class ScraplingBridge:
    def __init__(self) -> None:
        self._params = StdioServerParameters(
            command=COMMAND,
            args=list(ARGS),
            env=dict(os.environ),
            cwd=os.getenv("SCRAPLING_SHIM_CWD"),
        )
        self._client_cm = None
        self._session_cm = None
        self._session: ClientSession | None = None
        self._connect_lock = asyncio.Lock()
        self._call_lock = asyncio.Lock()

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._connect_lock:
            if self._session is not None:
                return self._session
            client_cm = stdio_client(self._params)
            read_stream, write_stream = await client_cm.__aenter__()
            session_cm = ClientSession(read_stream, write_stream)
            session = await session_cm.__aenter__()
            await session.initialize()
            self._client_cm = client_cm
            self._session_cm = session_cm
            self._session = session
            return session

    async def _reset(self) -> None:
        session_cm, client_cm = self._session_cm, self._client_cm
        self._session = self._session_cm = self._client_cm = None
        if session_cm is not None:
            await session_cm.__aexit__(None, None, None)
        if client_cm is not None:
            await client_cm.__aexit__(None, None, None)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        session = await self._ensure_session()
        async with self._call_lock:
            try:
                return await session.call_tool(name, arguments)
            except Exception:
                await self._reset()
                raise

    async def list_tools(self) -> List[types.Tool]:
        session = await self._ensure_session()
        async with self._call_lock:
            try:
                result = await session.list_tools()
                return list(result.tools)
            except Exception:
                await self._reset()
                raise


BRIDGE = ScraplingBridge()


def _parse_payload(payload: str) -> dict[str, Any]:
    if payload.startswith("METADATA:"):
        body = payload[len("METADATA:") :].lstrip()
        meta_block, sep, content = body.partition("\n\n")
        try:
            metadata = json.loads(meta_block.strip() or "{}")
        except json.JSONDecodeError as exc:
            metadata = {"raw_metadata": meta_block.strip(), "parse_error": str(exc)}
        metadata.setdefault("adapter", "scrapling-shim")
        return {"metadata": metadata, "content": content if sep else ""}
    return {"metadata": {"adapter": "scrapling-shim", "note": "metadata prefix missing"}, "content": payload}


def _normalize(tool: str, result: types.CallToolResult) -> tuple[List[types.Content], dict[str, Any]]:
    content = list(result.content or [])
    structured = result.structuredContent
    if tool not in TARGET_TOOLS:
        return content, structured or {}
    if structured and {"metadata", "content"}.issubset(structured):
        metadata = dict(structured["metadata"])
        metadata.setdefault("adapter", "scrapling-shim")
        return content, {"metadata": metadata, "content": structured["content"]}
    text = ""
    for block in content:
        if isinstance(block, types.TextContent) and block.text:
            text = block.text
            break
    payload = _parse_payload(text)
    return [types.TextContent(type="text", text=payload["content"])], payload


async def _list_tools(self: FastMCP) -> List[types.Tool]:  # pragma: no cover - passthrough
    tools = []
    for tool in await BRIDGE.list_tools():
        if tool.name in TARGET_TOOLS:
            data = tool.model_dump(mode="json")
            data["outputSchema"] = OUTPUT_SCHEMA
            tools.append(types.Tool.model_validate(data))
        else:
            tools.append(tool)
    return tools


async def _call_tool(
    self: FastMCP, name: str, arguments: dict[str, Any]
) -> Iterable[types.Content] | tuple[Iterable[types.Content], dict[str, Any]]:
    content, structured = _normalize(name, await BRIDGE.call_tool(name, arguments or {}))
    if name in TARGET_TOOLS or structured:
        return content, structured
    return content

def run() -> None:
    app.list_tools = MethodType(_list_tools, app)
    app.call_tool = MethodType(_call_tool, app)
    app.run(transport=os.getenv("SCRAPLING_SHIM_TRANSPORT", "stdio"))


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(130)
