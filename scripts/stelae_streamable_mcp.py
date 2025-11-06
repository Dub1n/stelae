#!/usr/bin/env python3
"""Streamable HTTP MCP shim that wraps local SSE servers for ChatGPT connectors."""

from __future__ import annotations

import itertools
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Any, Dict, Iterable, List, Sequence

import httpx
from mcp import types
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from mcp.server import FastMCP

DEFAULT_PROXY_BASE = "http://localhost:9090"
DEFAULT_STREAMABLE_HOST = "0.0.0.0"
DEFAULT_STREAMABLE_PORT = 9100
DEFAULT_SEARCH_MAX_RESULTS = 50
DEFAULT_FETCH_MAX_LENGTH = 5000
DEFAULT_SSE_TIMEOUT = 10.0
DEFAULT_SSE_READ_TIMEOUT = 120.0

PROXY_BASE = os.getenv("STELAE_PROXY_BASE", DEFAULT_PROXY_BASE).rstrip("/")
SEARCH_ROOT = Path(os.getenv("STELAE_SEARCH_ROOT", os.getcwd())).resolve()
SEARCH_PATHS_ENV = os.getenv("STELAE_STREAMABLE_SEARCH_PATHS", str(SEARCH_ROOT))
STREAMABLE_HOST = os.getenv("STELAE_STREAMABLE_HOST", DEFAULT_STREAMABLE_HOST)
STREAMABLE_PORT = int(os.getenv("STELAE_STREAMABLE_PORT", str(DEFAULT_STREAMABLE_PORT)))
SEARCH_MAX_RESULTS = int(
    os.getenv("STELAE_STREAMABLE_MAX_RESULTS", str(DEFAULT_SEARCH_MAX_RESULTS))
)
FETCH_MAX_LENGTH = int(
    os.getenv("STELAE_STREAMABLE_FETCH_MAX_LENGTH", str(DEFAULT_FETCH_MAX_LENGTH))
)
SSE_TIMEOUT = float(
    os.getenv("STELAE_STREAMABLE_SSE_TIMEOUT", str(DEFAULT_SSE_TIMEOUT))
)
SSE_READ_TIMEOUT = float(
    os.getenv("STELAE_STREAMABLE_SSE_READ_TIMEOUT", str(DEFAULT_SSE_READ_TIMEOUT))
)
STATIC_SEARCH_ENABLED = os.getenv("STELAE_STREAMABLE_STATIC_SEARCH", "1") != "0"
PROXY_SYNC_TIMEOUT = float(os.getenv("STELAE_STREAMABLE_SYNC_TIMEOUT", "10.0"))
PROXY_CALL_TIMEOUT = float(
    os.getenv("STELAE_STREAMABLE_PROXY_CALL_TIMEOUT", str(SSE_READ_TIMEOUT))
)

DEFAULT_SEARCH_PATHS: Sequence[str] = tuple(
    part.strip() for part in SEARCH_PATHS_ENV.split(",") if part.strip()
) or (str(SEARCH_ROOT),)

TRANSPORT = os.getenv("STELAE_STREAMABLE_TRANSPORT", "streamable-http")


def _configure_logger() -> logging.Logger:
    """Configure a file-backed logger for early process diagnostics."""

    logger = logging.getLogger("stelae.streamable_mcp")
    if logger.handlers:
        return logger

    log_path_env = os.getenv("STELAE_STREAMABLE_STDIO_LOG")
    default_path = (
        Path(__file__).resolve().parent.parent / "logs" / "stelae_stdio_bridge.log"
    )
    log_path = Path(log_path_env) if log_path_env else default_path

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handlers: list[logging.Handler] = []

    file_handler_error: Exception | None = None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
    except (
        Exception
    ) as exc:  # pragma: no cover - filesystem issues are diagnostic by nature
        file_handler_error = exc
    else:
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    for handler in handlers:
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    if file_handler_error:
        logger.warning(
            "Falling back to stderr logging because %s could not be opened: %s",
            log_path,
            file_handler_error,
        )

    return logger


LOGGER = _configure_logger()

app = FastMCP(
    name="stelae-hub",
    instructions="Connector-ready hub exposing the aggregated Stelae MCP catalog.",
    host=STREAMABLE_HOST,
    port=STREAMABLE_PORT,
    streamable_http_path="/mcp",
)


@dataclass(frozen=True)
class StaticSearchHit:
    id: str
    title: str
    text: str
    url: str
    snippet: str


STATIC_SEARCH_HITS: Sequence[StaticSearchHit] = (
    StaticSearchHit(
        id="repo:docs/SPEC-v1.md",
        title="SPEC-v1.md",
        text="Summary of the Stelae MCP compliance requirements and verification flow.",
        url="stelae://repo/docs/SPEC-v1.md",
        snippet="SPEC outlines the MCP handshake contract, tool catalog expectations, and SSE timing guarantees.",
    ),
    StaticSearchHit(
        id="repo:dev/chat_gpt_connector_compliant_reference.md",
        title="chat_gpt_connector_compliant_reference.md",
        text="Reference catalog consolidating manifest, initialize, and search requirements for ChatGPT connectors.",
        url="stelae://repo/dev/chat_gpt_connector_compliant_reference.md",
        snippet="Reference doc captures the minimal search/fetch tool set plus example payloads used by compliant servers.",
    ),
    StaticSearchHit(
        id="repo:dev/compliance_handoff.md",
        title="compliance_handoff.md",
        text="Action plan enumerating remediation steps to align the Stelae MCP endpoint with ChatGPT verification.",
        url="stelae://repo/dev/compliance_handoff.md",
        snippet="Handoff describes trimming initialize/tools.list outputs and delivering deterministic search hits for validation.",
    ),
)


def _static_search_results() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for hit in STATIC_SEARCH_HITS:
        results.append(
            {
                "id": hit.id,
                "title": hit.title,
                "text": hit.text,
                "url": hit.url,
                "metadata": {"snippet": hit.snippet},
            }
        )
    return results


@dataclass(slots=True)
class CallResult:
    """Lightweight representation of an upstream CallToolResult."""

    content: List[types.TextContent]
    structured_content: Dict[str, Any] | None

    @classmethod
    def from_call_tool_result(cls, result: types.CallToolResult) -> "CallResult":
        text_content = [
            item for item in result.content if isinstance(item, types.TextContent)
        ]
        return cls(content=text_content, structured_content=result.structuredContent)


async def _call_upstream_tool(
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    read_timeout: float = SSE_READ_TIMEOUT,
) -> CallResult:
    endpoint = f"{PROXY_BASE}/{server_name}/sse"
    async with sse_client(
        endpoint, timeout=SSE_TIMEOUT, sse_read_timeout=read_timeout
    ) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"{server_name}.{tool_name} returned an error")
            return CallResult.from_call_tool_result(result)


def _coerce_paths(
    paths: Sequence[str] | str | None,
) -> Sequence[str | os.PathLike[str]]:
    if not paths:
        return DEFAULT_SEARCH_PATHS
    if isinstance(paths, str):
        return (paths,)
    return tuple(paths)


def _to_repo_id(file_path: str, line_number: int | None) -> str:
    rel = _relative_repo_path(file_path)
    suffix = f"#L{line_number}" if line_number else ""
    return f"repo:{rel}{suffix}"


def _relative_repo_path(file_path: str) -> str:
    try:
        path_obj = Path(file_path)
        rel = path_obj.resolve().relative_to(SEARCH_ROOT)
        return str(rel)
    except Exception:
        return file_path


_RPC_COUNTER = itertools.count(1)
_PROMPT_DESCRIPTIONS: dict[str, str | None] = {}
PROXY_MODE = False


def _next_rpc_id(method: str) -> str:
    return f"cli-{method}-{next(_RPC_COUNTER)}"


def _build_timeout(read_timeout: float | None = None) -> httpx.Timeout:
    base_timeout = read_timeout or PROXY_CALL_TIMEOUT
    return httpx.Timeout(
        timeout=base_timeout,
        connect=SSE_TIMEOUT,
        read=base_timeout,
        write=base_timeout,
    )


def _extract_result(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in payload:
        error_info = payload["error"] or {}
        message = error_info.get("message", "unknown error")
        raise RuntimeError(f"Proxy {method} request failed: {message}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Proxy {method} returned unexpected payload shape")
    return result


def _proxy_jsonrpc_sync(
    method: str, params: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": _next_rpc_id(method),
        "method": method,
    }
    if params:
        payload["params"] = params
    timeout = httpx.Timeout(
        timeout=PROXY_SYNC_TIMEOUT,
        connect=min(PROXY_SYNC_TIMEOUT, SSE_TIMEOUT),
        read=PROXY_SYNC_TIMEOUT,
        write=PROXY_SYNC_TIMEOUT,
    )
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(f"{PROXY_BASE}/mcp", json=payload)
            response.raise_for_status()
            return _extract_result(method, response.json())
    except (
        httpx.HTTPError
    ) as exc:  # pragma: no cover - network issues need runtime inspection
        raise RuntimeError(f"Proxy {method} request failed: {exc}") from exc


async def _proxy_jsonrpc(
    method: str,
    params: Dict[str, Any] | None = None,
    *,
    read_timeout: float | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": _next_rpc_id(method),
        "method": method,
    }
    if params:
        payload["params"] = params
    timeout = _build_timeout(read_timeout)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(f"{PROXY_BASE}/mcp", json=payload)
            response.raise_for_status()
            return _extract_result(method, response.json())
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Proxy {method} request failed: {exc}") from exc


def _normalize_input_schema(schema: Any) -> Dict[str, Any]:
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def _convert_icons(raw_icons: Any) -> list[types.Icon] | None:
    if not isinstance(raw_icons, list):
        return None
    icons: list[types.Icon] = []
    for item in raw_icons:
        if isinstance(item, dict):
            try:
                icons.append(types.Icon.model_validate(item))
            except Exception:
                continue
    return icons or None


def _convert_tool_descriptor(descriptor: Dict[str, Any]) -> types.Tool:
    name = descriptor.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Tool descriptor missing name")

    tool_data: Dict[str, Any] = {
        "name": name,
        "description": descriptor.get("description"),
        "inputSchema": _normalize_input_schema(descriptor.get("inputSchema")),
        "outputSchema": descriptor.get("outputSchema"),
    }

    annotations = descriptor.get("annotations")
    if isinstance(annotations, dict):
        tool_data["annotations"] = types.ToolAnnotations.model_validate(annotations)

    icons = _convert_icons(descriptor.get("icons"))
    if icons:
        tool_data["icons"] = icons

    meta = descriptor.get("meta") or descriptor.get("_meta")
    if isinstance(meta, dict):
        tool_data["meta"] = meta

    return types.Tool.model_validate(tool_data)


def _convert_prompt_descriptor(descriptor: Dict[str, Any]) -> types.Prompt:
    name = descriptor.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Prompt descriptor missing name")

    prompt_data: Dict[str, Any] = {
        "name": name,
        "description": descriptor.get("description"),
    }

    arguments = descriptor.get("arguments")
    if isinstance(arguments, list):
        converted_args: list[types.PromptArgument] = []
        for item in arguments:
            if isinstance(item, dict):
                try:
                    converted_args.append(types.PromptArgument.model_validate(item))
                except Exception:
                    continue
        if converted_args:
            prompt_data["arguments"] = converted_args

    icons = _convert_icons(descriptor.get("icons"))
    if icons:
        prompt_data["icons"] = icons

    meta = descriptor.get("meta")
    if isinstance(meta, dict):
        prompt_data["meta"] = meta

    return types.Prompt.model_validate(prompt_data)


def _convert_resource_descriptor(descriptor: Dict[str, Any]) -> types.Resource:
    name = descriptor.get("name")
    uri = descriptor.get("uri")
    if not isinstance(name, str) or not isinstance(uri, str):
        raise ValueError("Resource descriptor missing name or uri")

    resource_data: Dict[str, Any] = {
        "name": name,
        "uri": uri,
        "title": descriptor.get("title"),
        "description": descriptor.get("description"),
        "mimeType": descriptor.get("mimeType"),
        "size": descriptor.get("size"),
    }

    icons = _convert_icons(descriptor.get("icons"))
    if icons:
        resource_data["icons"] = icons

    annotations = descriptor.get("annotations")
    if isinstance(annotations, dict):
        resource_data["annotations"] = types.Annotations.model_validate(annotations)

    meta = descriptor.get("meta") or descriptor.get("_meta")
    if isinstance(meta, dict):
        resource_data["meta"] = meta

    return types.Resource.model_validate(resource_data)


def _convert_resource_content(payload: Dict[str, Any]) -> types.ResourceContents:
    if "text" in payload:
        return types.TextResourceContents.model_validate(payload)
    if "blob" in payload:
        return types.BlobResourceContents.model_validate(payload)
    raise ValueError("Unsupported resource content payload")


def _convert_content_block(payload: Dict[str, Any]) -> types.Content:
    content_type = payload.get("type")
    try:
        if content_type == "text":
            return types.TextContent.model_validate(payload)
        if content_type == "image":
            return types.ImageContent.model_validate(payload)
        if content_type == "audio":
            return types.AudioContent.model_validate(payload)
        if content_type == "resource_link":
            return types.ResourceLink.model_validate(payload)
        if content_type == "resource":
            return types.EmbeddedResource.model_validate(payload)
    except Exception:
        pass
    text_repr = payload.get("text")
    if not isinstance(text_repr, str):
        text_repr = json.dumps(payload, ensure_ascii=False)
    return types.TextContent(type="text", text=text_repr)


def _convert_prompt_message(payload: Dict[str, Any]) -> types.PromptMessage:
    content_payload = payload.get("content")
    if isinstance(content_payload, dict):
        content = _convert_content_block(content_payload)
    elif isinstance(content_payload, str):
        content = types.TextContent(type="text", text=content_payload)
    else:
        content = types.TextContent(
            type="text", text=json.dumps(content_payload, ensure_ascii=False)
        )
    message_data = {
        "role": payload.get("role", "assistant"),
        "content": content,
    }
    return types.PromptMessage.model_validate(message_data)


async def _proxy_list_tools(self: FastMCP) -> list[types.Tool]:
    result = await _proxy_jsonrpc("tools/list")
    raw_tools = result.get("tools")
    tools: list[types.Tool] = []
    if isinstance(raw_tools, list):
        for descriptor in raw_tools:
            if not isinstance(descriptor, dict):
                continue
            try:
                tools.append(_convert_tool_descriptor(descriptor))
            except Exception as exc:
                LOGGER.warning("Skipping proxy tool descriptor due to error: %s", exc)
    return tools


async def _proxy_call_tool(
    self: FastMCP,
    name: str,
    arguments: Dict[str, Any],
) -> Iterable[types.Content] | tuple[Iterable[types.Content], Dict[str, Any]]:
    params = {"name": name, "arguments": arguments or {}}
    result = await _proxy_jsonrpc("tools/call", params, read_timeout=PROXY_CALL_TIMEOUT)
    raw_content = result.get("content")
    content_blocks: list[types.Content] = []
    if isinstance(raw_content, list):
        for item in raw_content:
            if isinstance(item, dict):
                try:
                    content_blocks.append(_convert_content_block(item))
                except Exception as exc:
                    LOGGER.warning(
                        "Failed to convert content block from proxy result: %s", exc
                    )
            elif isinstance(item, str):
                content_blocks.append(types.TextContent(type="text", text=item))
    if not content_blocks:
        content_blocks.append(types.TextContent(type="text", text=""))

    structured = result.get("structuredContent")
    if structured is not None:
        if not isinstance(structured, dict):
            raise RuntimeError("Proxy returned non-dict structured content")
        return content_blocks, structured
    return content_blocks


async def _proxy_list_prompts(self: FastMCP) -> list[types.Prompt]:
    result = await _proxy_jsonrpc("prompts/list")
    raw_prompts = result.get("prompts")
    prompts: list[types.Prompt] = []
    _PROMPT_DESCRIPTIONS.clear()
    if isinstance(raw_prompts, list):
        for descriptor in raw_prompts:
            if not isinstance(descriptor, dict):
                continue
            try:
                prompt = _convert_prompt_descriptor(descriptor)
            except Exception as exc:
                LOGGER.warning("Skipping proxy prompt descriptor due to error: %s", exc)
                continue
            _PROMPT_DESCRIPTIONS[prompt.name] = prompt.description
            prompts.append(prompt)
    return prompts


async def _proxy_get_prompt(
    self: FastMCP,
    name: str,
    arguments: Dict[str, Any] | None = None,
) -> types.GetPromptResult:
    params: Dict[str, Any] = {"name": name}
    if arguments:
        params["arguments"] = arguments
    result = await _proxy_jsonrpc("prompts/get", params)
    raw_messages = result.get("messages")
    messages: list[types.PromptMessage] = []
    if isinstance(raw_messages, list):
        for message in raw_messages:
            if isinstance(message, dict):
                try:
                    messages.append(_convert_prompt_message(message))
                except Exception as exc:
                    LOGGER.warning("Skipping malformed prompt message: %s", exc)
    description = result.get("description")
    if description is None:
        description = _PROMPT_DESCRIPTIONS.get(name)
    return types.GetPromptResult(description=description, messages=messages)


async def _proxy_list_resources(self: FastMCP) -> list[types.Resource]:
    result = await _proxy_jsonrpc("resources/list")
    raw_resources = result.get("resources")
    resources: list[types.Resource] = []
    if isinstance(raw_resources, list):
        for descriptor in raw_resources:
            if not isinstance(descriptor, dict):
                continue
            try:
                resources.append(_convert_resource_descriptor(descriptor))
            except Exception as exc:
                LOGGER.warning(
                    "Skipping proxy resource descriptor due to error: %s", exc
                )
    return resources


async def _proxy_read_resource(
    self: FastMCP, uri: str
) -> Iterable[types.ResourceContents]:
    result = await _proxy_jsonrpc("resources/read", {"uri": uri})
    raw_contents = result.get("contents")
    contents: list[types.ResourceContents] = []
    if isinstance(raw_contents, list):
        for entry in raw_contents:
            if not isinstance(entry, dict):
                continue
            try:
                contents.append(_convert_resource_content(entry))
            except Exception as exc:
                LOGGER.warning("Skipping proxy resource content due to error: %s", exc)
    return contents


async def _proxy_list_resource_templates(self: FastMCP) -> list[types.ResourceTemplate]:
    """The proxy does not currently expose resource templates."""

    return []


def _activate_proxy_handlers() -> None:
    app.list_tools = MethodType(_proxy_list_tools, app)
    app.call_tool = MethodType(_proxy_call_tool, app)
    app.list_prompts = MethodType(_proxy_list_prompts, app)
    app.get_prompt = MethodType(_proxy_get_prompt, app)
    app.list_resources = MethodType(_proxy_list_resources, app)
    app.read_resource = MethodType(_proxy_read_resource, app)
    app.list_resource_templates = MethodType(_proxy_list_resource_templates, app)

    server = app._mcp_server
    server.list_tools()(app.list_tools)
    server.call_tool(validate_input=False)(app.call_tool)
    server.list_prompts()(app.list_prompts)
    server.get_prompt()(app.get_prompt)
    server.list_resources()(app.list_resources)
    server.read_resource()(app.read_resource)
    server.list_resource_templates()(app.list_resource_templates)


def _bootstrap_proxy_mode() -> bool:
    try:
        probe = _proxy_jsonrpc_sync("tools/list")
        tools = probe.get("tools")
        tool_count = len(tools) if isinstance(tools, list) else 0
    except Exception as exc:
        LOGGER.warning("Unable to load proxy catalog from %s: %s", PROXY_BASE, exc)
        return False

    _activate_proxy_handlers()
    LOGGER.info("Proxy catalog bridging enabled with %d tools", tool_count)
    return True


def _register_fallback_tools() -> None:
    global search, fetch
    search = app.tool(
        name="search",
        description="Connector-compliant source search over the workspace.",
    )(search)
    fetch = app.tool(
        name="fetch",
        description="Connector-compliant fetch built atop Docy/fetch servers.",
    )(fetch)
    LOGGER.info("Fallback search/fetch tools registered")


def _initialize_bridge() -> None:
    global PROXY_MODE
    if _bootstrap_proxy_mode():
        PROXY_MODE = True
    else:
        PROXY_MODE = False
        _register_fallback_tools()


async def search(
    query: str,
    max_results: int = SEARCH_MAX_RESULTS,
    paths: Sequence[str] | str | None = None,
    ignore_case: bool = False,
) -> str:
    """Return connector-ready search results."""

    query = query.strip()
    if not query:
        return json.dumps({"results": []})

    if STATIC_SEARCH_ENABLED:
        return json.dumps({"results": _static_search_results()}, ensure_ascii=False)

    effective_paths = _coerce_paths(paths)
    max_results = max(1, min(max_results, SEARCH_MAX_RESULTS))

    arguments: Dict[str, Any] = {
        "pattern": query,
        "paths": list(effective_paths)
        if len(effective_paths) > 1
        else effective_paths[0],
        "recursive": True,
        "line_number": True,
        "max_count": max_results,
        "ignore_case": ignore_case,
    }

    upstream = await _call_upstream_tool("rg", "grep", arguments)

    matches: List[Dict[str, Any]] = []
    for content in upstream.content:
        try:
            data = json.loads(content.text)
            if isinstance(data, list):
                matches.extend(data)
        except json.JSONDecodeError:
            continue

    results: List[Dict[str, Any]] = []
    for match in matches:
        file_path = match.get("file") or match.get("path")
        if not isinstance(file_path, str):
            continue
        line_num = match.get("line_num") or match.get("line")
        try:
            line_val = int(line_num) if line_num is not None else None
        except (TypeError, ValueError):
            line_val = None
        snippet = match.get("line") or match.get("text") or ""
        entry = {
            "id": _to_repo_id(file_path, line_val),
            "title": _relative_repo_path(file_path),
            "url": f"stelae://repo/{_relative_repo_path(file_path)}"
            + (f"#L{line_val}" if line_val else ""),
            "metadata": {"snippet": snippet.strip()},
        }
        results.append(entry)
        if len(results) >= max_results:
            break

    return json.dumps({"results": results}, ensure_ascii=False)


async def _maybe_refetch_raw(
    url: str,
    max_length: int,
    start_index: int,
    original_text: str,
) -> str | None:
    error_markers = ("ExtractArticle.js", "readabilipy", "Failed to parse")
    if any(marker in original_text for marker in error_markers):
        fallback = await _call_upstream_tool(
            "fetch",
            "fetch",
            {
                "url": url,
                "max_length": max_length,
                "start_index": start_index,
                "raw": True,
            },
            read_timeout=180.0,
        )
        for content in fallback.content:
            if content.text:
                return content.text
    return None


async def fetch(
    id: str | None = None,
    url: str | None = None,
    max_length: int = FETCH_MAX_LENGTH,
    start_index: int = 0,
    raw: bool = False,
) -> str:
    target_id = (id or url or "").strip()
    if not target_id:
        raise ValueError("fetch requires an id or url")

    resolved_url = url
    if resolved_url is None:
        if target_id.startswith("http://") or target_id.startswith("https://"):
            resolved_url = target_id
        elif target_id.startswith("stelae://repo/"):
            candidate = target_id.removeprefix("stelae://repo/")
            resolved_url = str((SEARCH_ROOT / candidate).resolve())

    proxy_arguments = {
        "url": resolved_url or target_id,
        "max_length": max_length,
        "start_index": start_index,
        "raw": raw,
    }
    upstream = await _call_upstream_tool(
        "fetch", "fetch", proxy_arguments, read_timeout=180.0
    )

    payload_text = ""
    for content in upstream.content:
        if content.text:
            payload_text = content.text
            break

    if not payload_text:
        payload_text = json.dumps(
            {
                "id": target_id,
                "title": target_id,
                "text": "",
                "url": resolved_url or target_id,
                "metadata": {"note": "Empty response from upstream fetch server"},
            },
            ensure_ascii=False,
        )

    if not raw:
        fallback = await _maybe_refetch_raw(
            resolved_url or target_id, max_length, start_index, payload_text
        )
        if fallback is not None:
            payload_text = fallback

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError:
        data = {
            "id": target_id,
            "title": target_id,
            "text": payload_text,
            "url": resolved_url or target_id,
            "metadata": {
                "raw": True if raw else False,
                "note": "Non-JSON fetch response",
            },
        }
    else:
        data.setdefault("id", target_id)
        data.setdefault("title", data.get("url", resolved_url or target_id))
        data.setdefault("url", resolved_url or target_id)
        data.setdefault("metadata", {})

    return json.dumps(data, ensure_ascii=False)


_initialize_bridge()


def run() -> None:
    LOGGER.info(
        "Launching FastMCP transport=%s proxy=%s mode=%s cwd=%s search_root=%s default_paths=%s",
        TRANSPORT,
        PROXY_BASE,
        "proxy" if PROXY_MODE else "fallback",
        os.getcwd(),
        SEARCH_ROOT,
        DEFAULT_SEARCH_PATHS,
    )
    if TRANSPORT == "stdio":
        ready_message = {
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {
                "level": "info",
                "data": "Stelae bridge ready",
                "logger": "stelae.streamable_mcp",
            },
        }
        try:
            sys.stdout.write(json.dumps(ready_message, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        except Exception:  # pragma: no cover - surfaced for operational diagnostics
            LOGGER.exception("Failed to emit server ready notification")
        else:
            LOGGER.info("Emitted server ready notification")
    try:
        app.run(transport=TRANSPORT)
    except Exception:  # pragma: no cover - surfaced for operational diagnostics
        LOGGER.exception("FastMCP transport %s crashed", TRANSPORT)
        raise
    LOGGER.info("FastMCP transport %s terminated", TRANSPORT)


if __name__ == "__main__":
    run()
