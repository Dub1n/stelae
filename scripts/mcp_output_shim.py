#!/usr/bin/env python3
"""Generic stdio shim that enforces structured MCP outputs."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import MethodType
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server import FastMCP

DEFAULT_WRAPPER_MAP: dict[str, str] = {}

GENERIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
    },
    "required": ["result"],
}

SCRAPLING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "metadata": {"type": "object", "additionalProperties": True},
        "content": {"type": "string"},
    },
    "required": ["metadata", "content"],
}

LOGGER = logging.getLogger("stelae.shim")

# Timeouts (seconds) to avoid hangs when upstream servers fail to start/handshake.
CONNECT_TIMEOUT = float(os.getenv("MCP_SHIM_CONNECT_TIMEOUT", "10.0"))
LIST_TIMEOUT = float(os.getenv("MCP_SHIM_LIST_TIMEOUT", "15.0"))
CALL_TIMEOUT = float(os.getenv("MCP_SHIM_CALL_TIMEOUT", "30.0"))
GENERIC_PROMOTE_THRESHOLD = int(os.getenv("MCP_SHIM_GENERIC_PROMOTE_THRESHOLD", "2"))


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        if not name:
            continue
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _setup_logger() -> None:
    level = os.getenv("SHIM_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(asctime)s [%(levelname)s] %(message)s")


def _default_root() -> Path:
    env_root = os.getenv("STELAE_DIR")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ShimConfig:
    server_name: str
    command: str
    args: Sequence[str]
    transport: str
    status_path: Path
    override_path: Path
    default_wrapper: str
    tool_wrappers: Mapping[str, str]


class ToolStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
                if isinstance(payload, dict):
                    return payload
        except json.JSONDecodeError as exc:
            LOGGER.warning("Failed to parse %s: %s", self.path, exc)
        return {}

    def get(self, server: str, tool: str) -> dict[str, Any] | None:
        return self._data.get(server, {}).get(tool)

    def set_state(
        self,
        server: str,
        tool: str,
        *,
        state: str,
        wrapper: str | None = None,
        note: str | None = None,
        consecutive_generic: int | None = None,
        last_adapter: str | None = None,
    ) -> None:
        if server not in self._data:
            self._data[server] = {}
        entry = self._data[server].get(tool, {})
        entry.update({
            "state": state,
            "wrapper": wrapper,
            "note": note,
            "updated_at": time.time(),
        })
        if consecutive_generic is not None:
            entry["consecutive_generic_count"] = int(consecutive_generic)
        if last_adapter is not None:
            entry["last_adapter"] = last_adapter
        self._data[server][tool] = entry
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        tmp.replace(self.path)


class OverrideManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> MutableMapping[str, Any]:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        return data
            except json.JSONDecodeError as exc:
                LOGGER.warning("Failed to parse overrides %s: %s", self.path, exc)
        return {}

    def _write(self, data: MutableMapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        tmp.replace(self.path)

    def apply_schema(self, server: str, tool: str, schema: Mapping[str, Any]) -> bool:
        data = self._load()
        servers = data.setdefault("servers", {})
        server_block = servers.setdefault(server, {})
        server_block.setdefault("enabled", True)
        tools = server_block.setdefault("tools", {})
        tool_block = tools.setdefault(tool, {"enabled": True})
        existing = tool_block.get("outputSchema")
        if _schemas_equal(existing, schema):
            return False
        tool_block["outputSchema"] = json.loads(json.dumps(schema))
        self._write(data)
        return True


def _schemas_equal(first: Any, second: Any) -> bool:
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class GenericResultWrapper:
    name = "generic-shim"
    schema = GENERIC_OUTPUT_SCHEMA

    def wrap(self, text: str) -> tuple[str, dict[str, Any]]:
        return text, {"result": text}


class ScraplingMetadataWrapper:
    name = "scrapling-shim"
    schema = SCRAPLING_OUTPUT_SCHEMA

    def wrap(self, text: str) -> tuple[str, dict[str, Any]]:
        if text.startswith("METADATA:"):
            body = text[len("METADATA:") :].lstrip()
            meta_block, sep, content = body.partition("\n\n")
            try:
                metadata = json.loads(meta_block.strip() or "{}")
            except json.JSONDecodeError as exc:
                metadata = {"raw_metadata": meta_block.strip(), "parse_error": str(exc)}
            metadata.setdefault("adapter", self.name)
            payload = {"metadata": metadata, "content": content if sep else ""}
            return payload["content"], payload
        payload = {
            "metadata": {"adapter": self.name, "note": "metadata prefix missing"},
            "content": text,
        }
        return text, payload


class DeclaredFieldWrapper:
    def __init__(self, schema: Mapping[str, Any], field: str) -> None:
        self.schema = json.loads(json.dumps(schema))
        self.field = field
        self.name = f"declared:{field}"

    def wrap(self, text: str) -> tuple[str, dict[str, Any]]:
        return text, {self.field: text}


WRAPPERS: dict[str, Any] = {
    "generic_result": GenericResultWrapper(),
    "scrapling_metadata": ScraplingMetadataWrapper(),
}


class SchemaCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            LOGGER.warning("Failed to parse overrides for schema catalog %s: %s", self.path, exc)
            return {}

    def output_schema(self, server: str, tool: str) -> Mapping[str, Any] | None:
        return (
            self.data.get("servers", {})
            .get(server, {})
            .get("tools", {})
            .get(tool, {})
            .get("outputSchema")
        )

    def list_declared_tools(self, server: str) -> list[tuple[str, Mapping[str, Any]]]:
        servers = self.data.get("servers", {})
        server_block = servers.get(server, {})
        tools = server_block.get("tools", {})
        result: list[tuple[str, Mapping[str, Any]]] = []
        if isinstance(tools, dict):
            for name, block in tools.items():
                if isinstance(name, str) and isinstance(block, Mapping):
                    result.append((name, block))
        return result


class UpstreamBridge:
    def __init__(self, command: str, args: Sequence[str]) -> None:
        cwd = _env("MCP_SHIM_CWD", "SHIM_CWD", "SCRAPLING_SHIM_CWD")
        self._params = StdioServerParameters(command=command, args=list(args), env=dict(os.environ), cwd=cwd)
        self._client_cm = None
        self._session_cm = None
        self._session: ClientSession | None = None
        self._connect_lock = asyncio.Lock()
        self._call_lock = asyncio.Lock()
        # Snap effective env hints for diagnostics
        try:
            LOGGER.info(
                "Shim upstream launch plan: cmd=%s args=%s cwd=%s PATH=%s",
                command,
                " ".join(args),
                cwd or os.getcwd(),
                (self._params.env or {}).get("PATH", os.getenv("PATH", ""))[:200],
            )
        except Exception:
            # best-effort logging; never block startup
            pass

    async def _ensure_session(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._connect_lock:
            if self._session is not None:
                return self._session
            client_cm = stdio_client(self._params)
            try:
                read_stream, write_stream = await asyncio.wait_for(
                    client_cm.__aenter__(), timeout=CONNECT_TIMEOUT
                )
                session_cm = ClientSession(read_stream, write_stream)
                session = await asyncio.wait_for(
                    session_cm.__aenter__(), timeout=CONNECT_TIMEOUT
                )
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
            except (asyncio.TimeoutError, FileNotFoundError) as exc:
                # Emit targeted diagnostics for PATH/command issues and timeouts
                LOGGER.error(
                    "Failed to start upstream server (timeout or missing command). cmd=%s args=%s cwd=%s err=%s",
                    self._params.command,
                    " ".join(self._params.args or ()),
                    self._params.cwd,
                    exc,
                )
                # Ensure contexts are closed if partially opened
                try:
                    await client_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                raise
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

    async def list_tools(self) -> List[types.Tool]:
        session = await self._ensure_session()
        async with self._call_lock:
            for attempt in (1, 2):
                try:
                    result = await asyncio.wait_for(session.list_tools(), timeout=LIST_TIMEOUT)
                    return list(result.tools)
                except Exception as exc:
                    LOGGER.warning("list_tools attempt %d failed: %s", attempt, exc)
                    await self._reset()
                    if attempt == 2:
                        raise
                    session = await self._ensure_session()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        session = await self._ensure_session()
        async with self._call_lock:
            for attempt in (1, 2):
                try:
                    return await asyncio.wait_for(session.call_tool(name, arguments), timeout=CALL_TIMEOUT)
                except Exception as exc:
                    LOGGER.warning("call_tool %s attempt %d failed: %s", name, attempt, exc)
                    await self._reset()
                    if attempt == 2:
                        raise
                    session = await self._ensure_session()


class ShimController:
    def __init__(self, config: ShimConfig) -> None:
        self.config = config
        self.bridge = UpstreamBridge(config.command, config.args)
        self.state_store = ToolStateStore(config.status_path)
        self.override_manager = OverrideManager(config.override_path)
        self.schema_catalog = SchemaCatalog(config.override_path)

    def install(self, app: FastMCP) -> None:
        controller = self

        async def _list_tools(_: FastMCP) -> List[types.Tool]:
            return await controller._list_tools_impl()

        async def _call_tool(
            __: FastMCP, name: str, arguments: dict[str, Any]
        ) -> Iterable[types.Content] | tuple[Iterable[types.Content], dict[str, Any]]:
            return await controller._call_tool_impl(name, arguments)

        app.list_tools = MethodType(_list_tools, app)
        app.call_tool = MethodType(_call_tool, app)

    def _select_wrapper_name(self, tool: str) -> str:
        return self.config.tool_wrappers.get(tool, self.config.default_wrapper)

    def _wrapper_for(self, tool: str) -> tuple[str, Any]:
        name = self._select_wrapper_name(tool)
        wrapper = WRAPPERS.get(name)
        if wrapper is None:
            LOGGER.warning("Unknown wrapper %s for tool %s; falling back to generic", name, tool)
            name = "generic_result"
            wrapper = WRAPPERS[name]
        return name, wrapper

    async def _list_tools_impl(self) -> List[types.Tool]:
        # Fast-path: try a very short upstream list, then fall back immediately
        try:
            upstream = await asyncio.wait_for(self.bridge.list_tools(), timeout=1.5)
        except Exception as exc:
            LOGGER.warning(
                "Upstream list_tools unavailable for %s; serving fallback: %s",
                self.config.server_name,
                exc,
            )
            return self._fallback_tools_from_overrides()

        tools: List[types.Tool] = []
        for tool in upstream:
            data = tool.model_dump(mode="json")
            state = self.state_store.get(self.config.server_name, tool.name)
            if state and state.get("state") == "wrapped":
                wrapper = self._wrapper_for(tool.name)
                data["outputSchema"] = wrapper.schema
            tools.append(types.Tool.model_validate(data))
        return tools

    def _fallback_tools_from_overrides(self) -> List[types.Tool]:
        """Synthesize a minimal tool list when upstream is unavailable.

        Preference order for each tool's schema:
        - outputSchema from overrides (if present and valid)
        - wrapper default schema (if known)
        - omit outputSchema
        Input schema defaults to an empty object if not provided.
        """
        # Tool names declared in overrides plus well-known defaults for this server
        declared = dict(self.schema_catalog.list_declared_tools(self.config.server_name))
        names = set(declared.keys())

        synthesized: List[types.Tool] = []
        for name in sorted(names):
            block = declared.get(name) or {}
            # sanitize schemas
            input_schema = block.get("inputSchema") if isinstance(block, Mapping) else None
            if not isinstance(input_schema, Mapping):
                input_schema = {"type": "object", "properties": {}}
            output_schema = block.get("outputSchema") if isinstance(block, Mapping) else None
            if not isinstance(output_schema, Mapping):
                # fall back to wrapper schema if known
                _, wrapper = self._wrapper_for(name)
                output_schema = getattr(wrapper, "schema", None)

            descriptor: Dict[str, Any] = {
                "name": name,
                "description": block.get("description") if isinstance(block, Mapping) else None,
                "inputSchema": input_schema,
            }
            if isinstance(output_schema, Mapping):
                descriptor["outputSchema"] = output_schema
            try:
                synthesized.append(types.Tool.model_validate(descriptor))
            except Exception as exc:
                LOGGER.warning("Skipping synthesized tool %s due to validation error: %s", name, exc)
        return synthesized

    async def _call_tool_impl(
        self, name: str, arguments: dict[str, Any]
    ) -> Iterable[types.Content] | tuple[Iterable[types.Content], dict[str, Any]]:
        state = self.state_store.get(self.config.server_name, name)
        if state and state.get("state") == "failed":
            raise RuntimeError(state.get("note") or f"tool {name} previously failed schema adaptation")
        upstream = await self.bridge.call_tool(name, arguments or {})
        if state and state.get("state") == "wrapped":
            return self._wrap_and_return(name, upstream, state.get("wrapper"))
        if not isinstance(upstream.structuredContent, dict):
            declared = self._wrap_with_declared_schema(name, upstream)
            if declared is not None:
                return declared
            return self._wrap_and_record(name, upstream)
        if not state or state.get("state") != "pass_through":
            self.state_store.set_state(
                self.config.server_name,
                name,
                state="pass_through",
                wrapper=None,
                note=None,
                consecutive_generic=0,
                last_adapter="pass_through",
            )
        if upstream.structuredContent:
            return list(upstream.content or []), upstream.structuredContent
        return list(upstream.content or [])

    def _wrap_and_record(self, name: str, upstream: types.CallToolResult) -> tuple[Iterable[types.Content], dict[str, Any]]:
        wrapper_name, wrapper = self._wrapper_for(name)
        wrapped = self._wrap_result(name, wrapper, upstream)
        server = self.config.server_name
        # Persistence rules for generic fallback
        if wrapper_name == "generic_result":
            declared_schema = self.schema_catalog.output_schema(server, name)
            prior = self.state_store.get(server, name) or {}
            prior_count = int(prior.get("consecutive_generic_count") or 0)
            new_count = prior_count + 1
            # Record state + counters
            self.state_store.set_state(
                server,
                name,
                state="wrapped",
                wrapper=wrapper_name,
                note=None,
                consecutive_generic=new_count,
                last_adapter="generic",
            )
            # Apply override immediately when no declared schema exists; otherwise after threshold
            should_apply = declared_schema is None or new_count >= GENERIC_PROMOTE_THRESHOLD
            if should_apply and self.override_manager.apply_schema(server, name, wrapper.schema):
                LOGGER.info(
                    "Applied generic schema override for %s.%s; rerun make render-proxy && scripts/restart_stelae.sh",
                    server,
                    name,
                )
        else:
            # Non-generic wrapper: treat as declared/specific; reset counters
            self.state_store.set_state(
                server,
                name,
                state="wrapped",
                wrapper=wrapper_name,
                note=None,
                consecutive_generic=0,
                last_adapter="declared",
            )
            if self.override_manager.apply_schema(server, name, wrapper.schema):
                LOGGER.info(
                    "Applied schema override for %s.%s; rerun make render-proxy && scripts/restart_stelae.sh to advertise it",
                    server,
                    name,
                )
        return wrapped

    def _wrap_and_return(
        self, name: str, upstream: types.CallToolResult, override_wrapper: str | None
    ) -> tuple[Iterable[types.Content], dict[str, Any]]:
        wrapper = WRAPPERS.get(override_wrapper or self._select_wrapper_name(name)) or WRAPPERS["generic_result"]
        return self._wrap_result(name, wrapper, upstream)

    def _wrap_result(
        self, tool_name: str, wrapper: Any, upstream: types.CallToolResult
    ) -> tuple[Iterable[types.Content], dict[str, Any]]:
        text = extract_text(upstream.content)
        try:
            body_text, structured = wrapper.wrap(text)
        except Exception as exc:
            self.state_store.set_state(
                self.config.server_name,
                tool_name,
                state="failed",
                wrapper=self._select_wrapper_name(tool_name),
                note=str(exc),
            )
            raise
        content = [types.TextContent(type="text", text=body_text)]
        return content, structured

    def _wrap_with_declared_schema(
        self, name: str, upstream: types.CallToolResult
    ) -> tuple[Iterable[types.Content], dict[str, Any]] | None:
        schema = self.schema_catalog.output_schema(self.config.server_name, name)
        if not schema:
            return None
        # Heuristic: if declared schema expects {metadata: object, content: string},
        # use the ScraplingMetadataWrapper inline under the declared step
        if _schema_is_metadata_content(schema):
            wrapper = WRAPPERS.get("scrapling_metadata") or ScraplingMetadataWrapper()
            WRAPPERS["scrapling_metadata"] = wrapper
            wrapped = self._wrap_result(name, wrapper, upstream)
            # Treat as declared mapping and reset counters
            self._set_state(name, "scrapling_metadata")
            return wrapped
        # Heuristic: single-string field mapping
        wrapper_name = self._ensure_declared_wrapper(name, schema)
        if not wrapper_name:
            return None
        wrapper = WRAPPERS.get(wrapper_name)
        if wrapper is None:
            return None
        wrapped = self._wrap_result(name, wrapper, upstream)
        self._set_state(name, wrapper_name)
        return wrapped

    def _ensure_declared_wrapper(self, tool: str, schema: Mapping[str, Any]) -> str | None:
        wrapper_name = f"declared:{self.config.server_name}:{tool}"
        if wrapper_name in WRAPPERS:
            return wrapper_name
        field = _string_field_from_schema(schema)
        if not field:
            return None
        WRAPPERS[wrapper_name] = DeclaredFieldWrapper(schema, field)
        return wrapper_name

    def _set_state(self, tool: str, wrapper_name: str) -> None:
        # Convenience for declared-success path
        self.state_store.set_state(
            self.config.server_name,
            tool,
            state="wrapped",
            wrapper=wrapper_name,
            note=None,
            consecutive_generic=0,
            last_adapter="declared",
        )


def extract_text(blocks: Sequence[types.Content] | None) -> str:
    if not blocks:
        return ""
    for block in blocks:
        if isinstance(block, types.TextContent) and block.text:
            return block.text
    return ""


def _string_field_from_schema(schema: Mapping[str, Any]) -> str | None:
    if not isinstance(schema, Mapping):
        return None
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return None
    required = schema.get("required")
    required_list = required if isinstance(required, list) else []
    for field, desc in props.items():
        if isinstance(desc, Mapping) and desc.get("type") == "string":
            extra_required = [r for r in required_list if r != field]
            if extra_required:
                continue
            return field
    return None


def _schema_is_metadata_content(schema: Mapping[str, Any]) -> bool:
    if not isinstance(schema, Mapping):
        return False
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return False
    meta = props.get("metadata")
    content = props.get("content")
    if not (isinstance(meta, Mapping) and isinstance(content, Mapping)):
        return False
    if meta.get("type") != "object" or content.get("type") != "string":
        return False
    required = schema.get("required")
    if isinstance(required, list):
        return "metadata" in required and "content" in required
    return True


def parse_args() -> ShimConfig:
    root = _default_root()
    parser = argparse.ArgumentParser(description="Shim MCP outputs into structured JSON")
    parser.add_argument("--server-name", default=_env("MCP_SHIM_SERVER_NAME", "SHIM_SERVER_NAME", "SCRAPLING_SERVER_NAME", default="scrapling"))
    parser.add_argument("--command", default=_env("MCP_SHIM_COMMAND", "SHIM_COMMAND", "SCRAPLING_SHIM_COMMAND", "SCRAPLING_COMMAND", default="uvx"))
    parser.add_argument(
        "--args",
        nargs="*",
        default=shlex.split(_env("MCP_SHIM_ARGS", "SHIM_ARGS", "SCRAPLING_SHIM_ARGS", "SCRAPLING_ARGS", default="scrapling-fetch-mcp") or "scrapling-fetch-mcp"),
    )
    parser.add_argument("--transport", default=_env("MCP_SHIM_TRANSPORT", "SHIM_TRANSPORT", "SCRAPLING_SHIM_TRANSPORT", default="stdio"))
    parser.add_argument("--status-file", default=_env("MCP_SHIM_STATUS_PATH", "SHIM_STATUS_PATH", default=str(root / "config/tool_schema_status.json")))
    parser.add_argument("--override-file", default=_env("MCP_SHIM_OVERRIDE_PATH", "SHIM_OVERRIDE_PATH", default=str(root / "config/tool_overrides.json")))
    parser.add_argument("--default-wrapper", default=_env("MCP_SHIM_DEFAULT_WRAPPER", "SHIM_DEFAULT_WRAPPER", "SCRAPLING_DEFAULT_WRAPPER", default="generic_result"))
    parser.add_argument("--tool-wrappers", default=_env("MCP_SHIM_TOOL_WRAPPERS", "SHIM_TOOL_WRAPPERS", "SCRAPLING_TOOL_WRAPPERS", default=""))
    args = parser.parse_args()

    wrapper_map = dict(DEFAULT_WRAPPER_MAP)
    if args.tool_wrappers:
        try:
            override_map = json.loads(args.tool_wrappers)
            if isinstance(override_map, dict):
                for key, value in override_map.items():
                    if isinstance(key, str) and isinstance(value, str):
                        wrapper_map[key] = value
        except json.JSONDecodeError as exc:
            LOGGER.warning("Failed to parse MCP_SHIM_TOOL_WRAPPERS: %s", exc)

    return ShimConfig(
        server_name=args.server_name,
        command=args.command,
        args=args.args,
        transport=args.transport,
        status_path=Path(args.status_file).expanduser().resolve(),
        override_path=Path(args.override_file).expanduser().resolve(),
        default_wrapper=args.default_wrapper,
        tool_wrappers=wrapper_map,
    )


def run() -> None:
    _setup_logger()
    config = parse_args()
    # Guard against libraries printing to stdout (which corrupts stdio protocol).
    # Route bare print() calls to stderr while leaving sys.stdout for JSON-RPC only.
    try:
        import builtins as _builtins  # type: ignore

        _orig_print = _builtins.print  # type: ignore[attr-defined]

        def _stderr_print(*args: Any, **kwargs: Any) -> None:  # type: ignore[misc]
            kwargs.setdefault("file", sys.stderr)
            _orig_print(*args, **kwargs)

        _builtins.print = _stderr_print  # type: ignore[attr-defined]
    except Exception:
        # Non-fatal if monkey patching fails; proceed
        pass
    app = FastMCP(
        name=f"{config.server_name}-shim",
        instructions="Normalizes downstream MCP tool outputs into schema-compliant payloads.",
    )
    controller = ShimController(config)
    controller.install(app)
    server = app._mcp_server
    server.list_tools()(app.list_tools)
    server.call_tool(validate_input=False)(app.call_tool)
    LOGGER.info(
        "Starting shim for server=%s command=%s args=%s status=%s overrides=%s",
        config.server_name,
        config.command,
        " ".join(config.args),
        config.status_path,
        config.override_path,
    )
    app.run(transport=config.transport)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(130)
