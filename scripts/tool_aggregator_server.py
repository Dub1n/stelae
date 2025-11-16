#!/usr/bin/env python3
"""StdIO helper that exposes declarative tool aggregations via the proxy."""

from __future__ import annotations

import itertools
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping

import httpx
from mcp.server import FastMCP
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.integrator.stateful_runner import StatefulAggregatedToolRunner
from stelae_lib.integrator.tool_aggregations import (
    AggregatedToolDefinition,
    AggregatedToolRunner,
    ToolAggregationError,
    ToolAggregationConfig,
    load_tool_aggregation_config,
)

LOGGER = logging.getLogger("stelae.tool_aggregator")
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False

app = FastMCP(
    name="tool-aggregator",
    instructions="Expose composite MCP tools backed by downstream proxy calls.",
)

_CONFIG_PATH = Path(os.getenv("STELAE_TOOL_AGGREGATIONS", ROOT / "config" / "tool_aggregations.json"))
_SCHEMA_PATH = Path(
    os.getenv("STELAE_TOOL_AGGREGATIONS_SCHEMA", _CONFIG_PATH.with_name("tool_aggregations.schema.json"))
)
_PROXY_BASE_ENV = os.getenv("STELAE_PROXY_BASE")
_DEFAULT_PROXY = "http://127.0.0.1:9090"
_WORKSPACE_ROOT = Path(os.getenv("STELAE_DIR", ROOT)).resolve()
_STATE_HOME = Path(
    os.getenv("STELAE_STATE_HOME", Path.home() / ".config" / "stelae" / ".state")
).resolve()
_STATE_CONTEXT = {
    "STELAE_DIR": str(_WORKSPACE_ROOT),
    "STELAE_STATE_HOME": str(_STATE_HOME),
}


class PassthroughFuncMetadata(FuncMetadata):
    async def call_fn_with_arg_validation(
        self,
        fn,
        fn_is_async: bool,
        arguments_to_validate: Dict[str, Any],
        arguments_to_pass_directly: Dict[str, Any] | None,
    ) -> Any:
        """Skip validation and forward arguments as-is."""

        payload = dict(arguments_to_validate)
        if arguments_to_pass_directly:
            payload |= arguments_to_pass_directly
        if fn_is_async:
            return await fn(**payload)
        return fn(**payload)

    def convert_result(self, result: Any) -> Any:
        """Return tool results without FastMCP post-processing."""

        return result


class ProxyCaller:
    def __init__(self, base_url: str) -> None:
        endpoint = base_url.strip()
        if not endpoint:
            endpoint = _DEFAULT_PROXY
        if endpoint.endswith("/mcp"):
            self.endpoint = endpoint
        else:
            self.endpoint = endpoint.rstrip("/") + "/mcp"
        self._counter = itertools.count(1)

    async def __call__(self, tool_name: str, arguments: Dict[str, Any], timeout: float | None) -> Dict[str, Any]:
        request_id = f"agg-{next(self._counter)}"
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        timeout_value = timeout or 60.0
        http_timeout = httpx.Timeout(
            timeout=timeout_value,
            connect=min(timeout_value, 10.0),
            read=timeout_value,
            write=timeout_value,
        )
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                response = await client.post(self.endpoint, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:  # pragma: no cover - network edge cases
            raise ToolAggregationError(f"Proxy call failed for {tool_name}: {exc}") from exc
        if "error" in body:
            raise ToolAggregationError(
                f"Proxy reported error for {tool_name}: {json.dumps(body['error'])}"
            )
        return body.get("result", {})




def _load_config() -> ToolAggregationConfig:
    if not _CONFIG_PATH.exists():
        raise SystemExit(f"Aggregation config not found: {_CONFIG_PATH}")
    return load_tool_aggregation_config(_CONFIG_PATH, schema_path=_SCHEMA_PATH)


def _proxy_base_for(aggregation_base: str | None, config: ToolAggregationConfig) -> str:
    return aggregation_base or config.proxy_url or _PROXY_BASE_ENV or _DEFAULT_PROXY


def _register_aggregations(config: ToolAggregationConfig) -> None:
    LOGGER.info(
        "Registering %s aggregated tool(s) from %s", len(config.aggregations), _CONFIG_PATH
    )
    for aggregation in config.aggregations:
        proxy_base = _proxy_base_for(aggregation.proxy_url, config)
        proxy_caller = ProxyCaller(proxy_base)
        if aggregation.state:
            runner = StatefulAggregatedToolRunner(
                aggregation,
                proxy_caller,
                fallback_timeout=config.defaults.timeout_seconds,
                context=_STATE_CONTEXT,
                workspace_root=_WORKSPACE_ROOT,
                state_root=_STATE_HOME,
            )
        else:
            runner = AggregatedToolRunner(
                aggregation,
                proxy_caller,
                fallback_timeout=config.defaults.timeout_seconds,
            )

        @app.tool(name=aggregation.name, description=aggregation.description)
        async def handler(runner=runner, **payload):  # type: ignore[misc]
            return await runner.dispatch(dict(payload))

        tool = app._tool_manager.get_tool(aggregation.name)
        if tool:
            tool.fn_metadata = PassthroughFuncMetadata(
                arg_model=tool.fn_metadata.arg_model,
                output_schema=tool.fn_metadata.output_schema,
                output_model=tool.fn_metadata.output_model,
                wrap_output=tool.fn_metadata.wrap_output,
            )

        LOGGER.info(
            "Aggregated tool '%s' → %s (operations=%s)",
            aggregation.name,
            proxy_base,
            ", ".join(op.value for op in aggregation.operations),
        )


def main() -> None:
    try:
        config = _load_config()
        _register_aggregations(config)
    except ToolAggregationError as exc:
        raise SystemExit(f"Failed to load tool aggregations: {exc}") from exc
    app.run()


if __name__ == "__main__":  # pragma: no cover - script entry
    main()
