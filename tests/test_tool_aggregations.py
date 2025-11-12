import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from stelae_lib.config_overlays import overlay_path_for
from stelae_lib.integrator.tool_aggregations import (
    AggregatedToolRunner,
    ToolAggregationConfig,
    ToolAggregationError,
    load_tool_aggregation_config,
)
from stelae_lib.integrator.tool_overrides import ToolOverridesStore
from tests._tool_override_test_helpers import build_sample_runtime


@pytest.fixture()
def sample_schema_path(tmp_path: Path) -> Path:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["schemaVersion", "aggregations"],
        "properties": {
            "schemaVersion": {"const": 1},
            "aggregations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "description", "inputSchema", "operations"],
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "inputSchema": {"type": "object"},
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["value", "downstreamTool"],
                                "properties": {
                                    "value": {"type": "string"},
                                    "downstreamTool": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    path = tmp_path / "schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


def test_load_config_and_apply_overrides(tmp_path: Path, sample_schema_path: Path) -> None:
    config_payload = {
        "schemaVersion": 1,
        "hiddenTools": [{"server": "demo", "tool": "legacy"}],
        "aggregations": [
            {
                "name": "demo_aggregate",
                "description": "Sample aggregate",
                "inputSchema": {"type": "object", "properties": {"operation": {"type": "string"}}, "required": ["operation"]},
                "operations": [
                    {
                        "value": "ping",
                        "downstreamTool": "demo_tool",
                        "argumentMappings": [{"target": "operation", "value": "ping"}]
                    }
                ]
            }
        ]
    }
    config_path = tmp_path / "tool_agg.json"
    config_path.write_text(json.dumps(config_payload), encoding="utf-8")

    config = load_tool_aggregation_config(config_path, schema_path=sample_schema_path)
    store = ToolOverridesStore(tmp_path / "overrides.json")
    changed = config.apply_overrides(store)
    assert changed
    snapshot = store.snapshot()
    assert snapshot["servers"]["tool_aggregator"]["tools"]["demo_aggregate"]["enabled"] is True
    assert snapshot["servers"]["demo"]["tools"]["legacy"]["enabled"] is False


def test_runner_dispatches_and_maps_arguments() -> None:
    config_data = {
        "schemaVersion": 1,
        "aggregations": [
            {
                "name": "demo_aggregate",
                "description": "Sample aggregate",
                "inputSchema": {"type": "object", "properties": {"operation": {"type": "string"}}, "required": ["operation"]},
                "operations": [
                    {
                        "value": "ping",
                        "downstreamTool": "demo_tool",
                        "argumentMappings": [
                            {"target": "operation", "value": "ping"},
                            {"target": "params.url", "from": "url", "required": True}
                        ],
                        "responseMappings": [
                            {"target": "status", "from": "result.status"}
                        ]
                    }
                ]
            }
        ]
    }
    config = ToolAggregationConfig.from_data(config_data)
    aggregation = config.aggregations[0]
    observed: dict[str, Any] = {}

    async def fake_call(name: str, arguments: dict[str, Any], timeout: float | None):
        observed["tool"] = name
        observed["arguments"] = arguments
        observed["timeout"] = timeout
        return {"result": {"status": "ok"}}

    runner = AggregatedToolRunner(aggregation, fake_call, fallback_timeout=12.0)
    result = asyncio.run(
        runner.dispatch({"operation": "ping", "url": "https://example.com"})
    )
    assert result["status"] == "ok"
    assert observed["tool"] == "demo_tool"
    assert observed["arguments"]["params"]["url"] == "https://example.com"
    assert observed["timeout"] == aggregation.timeout_seconds


def test_require_any_of_enforced() -> None:
    config_data = {
        "schemaVersion": 1,
        "aggregations": [
            {
                "name": "demo_aggregate",
                "description": "Sample aggregate",
                "inputSchema": {"type": "object", "properties": {"operation": {"type": "string"}}, "required": ["operation"]},
                "operations": [
                    {
                        "value": "import",
                        "downstreamTool": "demo_tool",
                        "argumentMappings": [
                            {"target": "operation", "value": "import"},
                            {"target": "params.url", "from": "url", "stripIfNull": True},
                            {"target": "params.id", "from": "id", "stripIfNull": True}
                        ],
                        "requireAnyOf": [["url", "id"]]
                    }
                ]
            }
        ]
    }
    config = ToolAggregationConfig.from_data(config_data)
    aggregation = config.aggregations[0]

    async def fake_call(name: str, arguments: dict[str, Any], timeout: float | None):  # pragma: no cover - not reached
        return {}

    runner = AggregatedToolRunner(aggregation, fake_call)
    with pytest.raises(ToolAggregationError):
        asyncio.run(runner.dispatch({"operation": "import"}))


def test_aggregation_runtime_dedupes_and_hides(tmp_path: Path) -> None:
    fixture = build_sample_runtime(tmp_path)
    servers = fixture.runtime_payload["servers"]
    aggregated = servers["tool_aggregator"]["tools"]["doc_fetch_suite"]

    required_fields = aggregated["inputSchema"]["required"]
    assert required_fields == ["operation"]

    enum_values = aggregated["inputSchema"]["properties"]["operation"]["enum"]
    assert enum_values == ["fetch_document_links", "fetch_documentation_page"]

    docs_tools = servers["docs"]["tools"]
    assert all(entry["enabled"] is False for entry in docs_tools.values())


def test_overlay_only_excludes_defaults(monkeypatch, tmp_path: Path) -> None:
    base_path = tmp_path / "tool_aggregations.json"
    base_data = {
        "schemaVersion": 1,
        "defaults": {"selectorField": "operation", "serverName": "tool_aggregator"},
        "hiddenTools": [
            {"server": "docs", "tool": "fetch_document_links", "reason": "Wrapped"}
        ],
        "aggregations": [
            {
                "name": "doc_fetch_suite",
                "description": "Docs",
                "inputSchema": {"type": "object"},
                "operations": [
                    {"value": "fetch_document_links", "downstreamTool": "fetch_document_links"}
                ],
            }
        ],
    }
    base_path.write_text(json.dumps(base_data), encoding="utf-8")

    config_home = tmp_path / "config_home"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_home))
    overlay_path = overlay_path_for(base_path)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_data = {
        "hiddenTools": [
            {"server": "docs", "tool": "fetch_document_links", "reason": "Wrapped"},
            {"server": "mem", "tool": "legacy", "reason": "Custom"},
        ],
        "aggregations": [
            {
                "name": "doc_fetch_suite",
                "description": "Docs",
                "inputSchema": {"type": "object"},
                "operations": [
                    {"value": "fetch_document_links", "downstreamTool": "fetch_document_links"}
                ],
            },
            {
                "name": "custom_suite",
                "description": "Custom",
                "inputSchema": {"type": "object"},
                "operations": [
                    {"value": "ping", "downstreamTool": "custom_tool"},
                ],
            },
        ],
    }
    overlay_path.write_text(json.dumps(overlay_data), encoding="utf-8")

    config = load_tool_aggregation_config(
        base_path,
        schema_path=Path("config/tool_aggregations.schema.json"),
        overlay_only=True,
    )
    names = [agg.name for agg in config.aggregations]
    assert names == ["custom_suite"]
    hidden = config.hidden_tools
    assert len(hidden) == 1
    assert hidden[0].server == "mem"
