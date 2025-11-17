import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from mcp import types
jsonschema = pytest.importorskip("jsonschema")

from stelae_lib.config_overlays import config_home, overlay_path_for, state_home
from stelae_lib.integrator.tool_aggregations import (
    AggregatedToolRunner,
    ToolAggregationConfig,
    ToolAggregationError,
    load_tool_aggregation_config,
)
from stelae_lib.integrator.tool_overrides import ToolOverridesStore
from tests._tool_override_test_helpers import (
    build_sample_from_schema,
    build_sample_runtime,
    get_starter_bundle_aggregation,
    get_tool_schema,
)


def _load_process_tool_aggregations_module():
    spec = importlib.util.spec_from_file_location("process_tool_aggregations", ROOT / "scripts" / "process_tool_aggregations.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


STARTER_AGGREGATION_CASES = [
    ("workspace_fs_read", {"operation": "list_allowed_directories"}),
    ("workspace_fs_write", {"operation": "create_directory", "path": "docs/new-directory"}),
    ("workspace_shell_control", {"operation": "get_current_directory"}),
    ("memory_suite", {"operation": "list_memory_projects"}),
    ("scrapling_fetch_suite", {"operation": "s_fetch_page", "url": "https://example.com/docs"}),
    (
        "strata_ops_suite",
        {
            "operation": "discover_server_actions",
            "server_names": ["docs"],
            "user_query": "status",
        },
    ),
]


def test_tool_overrides_store_embedded_defaults(tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.json"
    store = ToolOverridesStore(
        tmp_path / "tool_overrides.json",
        runtime_path=runtime_path,
        target="runtime",
    )
    snapshot = store.snapshot()
    integrator = snapshot["servers"]["integrator"]["tools"]["manage_stelae"]
    assert integrator["enabled"] is True
    catalog_tools = snapshot["servers"]["public_mcp_catalog"]["tools"]
    assert catalog_tools["deep_search"]["enabled"] is True
    assert "tool_aggregator" not in snapshot["servers"]


def test_process_tool_aggregations_uses_embedded_defaults(monkeypatch, tmp_path: Path) -> None:
    module = _load_process_tool_aggregations_module()
    config_root = tmp_path / "config-home"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    config_home.cache_clear()
    state_home.cache_clear()


def test_process_tool_aggregations_writes_intended_catalog(monkeypatch, tmp_path: Path) -> None:
    module = _load_process_tool_aggregations_module()
    config_root = tmp_path / "config-home"
    catalog_dir = config_root / "catalog"
    catalog_dir.mkdir(parents=True)
    catalog_path = catalog_dir / "core.json"
    catalog_path.write_text(
        json.dumps(
            {
                "tool_overrides": {"servers": {"demo": {"tools": {"alpha": {"enabled": False}}}}},
                "tool_aggregations": {
                    "aggregations": [
                        {
                            "name": "wrapped_tool",
                            "description": "Wrapped",
                            "inputSchema": {"type": "object"},
                            "operations": [
                                {
                                    "value": "status",
                                    "downstreamTool": "alpha_status",
                                    "argumentMappings": [{"target": "operation", "value": "status"}],
                                }
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    overrides_path = tmp_path / "overrides.json"
    runtime_path = tmp_path / "runtime.json"

    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    config_home.cache_clear()
    state_home.cache_clear()

    argv = [
        "process_tool_aggregations.py",
        "--overrides",
        str(overrides_path),
        "--output",
        str(runtime_path),
        "--scope",
        "local",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    module.main()

    intended_path = state_home() / "intended_catalog.json"
    assert intended_path.exists()
    payload = json.loads(intended_path.read_text(encoding="utf-8"))
    overrides = payload["catalog"]["toolOverrides"]
    assert overrides["servers"]["demo"]["tools"]["alpha"]["enabled"] is False
    assert any(fragment["kind"] == "catalog" for fragment in payload["fragments"])

    config_home.cache_clear()
    state_home.cache_clear()


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
    assert isinstance(result, tuple)
    content_blocks, structured = result
    assert structured["status"] == "ok"
    assert len(content_blocks) == 1
    assert isinstance(content_blocks[0], types.TextContent)
    assert "ok" in content_blocks[0].text
    assert observed["tool"] == "demo_tool"
    assert observed["arguments"]["params"]["url"] == "https://example.com"
    assert observed["timeout"] == aggregation.timeout_seconds


def test_runner_decodes_structured_json_payloads() -> None:
    config_data = {
        "schemaVersion": 1,
        "aggregations": [
            {
                "name": "demo_aggregate",
                "description": "Sample aggregate",
                "inputSchema": {
                    "type": "object",
                    "properties": {"operation": {"type": "string"}},
                    "required": ["operation"],
                },
                "operations": [
                    {
                        "value": "ping",
                        "downstreamTool": "demo_tool",
                        "argumentMappings": [
                            {"target": "operation", "value": "ping"},
                        ],
                    }
                ],
            }
        ],
    }
    config = ToolAggregationConfig.from_data(config_data)
    aggregation = config.aggregations[0]

    async def fake_call(name: str, arguments: dict[str, Any], timeout: float | None):
        return {
            "content": [{"type": "text", "text": "payload"}],
            "structuredContent": {"result": '{"status": "ok", "entries": [1]}'},
        }

    runner = AggregatedToolRunner(aggregation, fake_call)
    result = asyncio.run(runner.dispatch({"operation": "ping"}))
    assert isinstance(result, tuple)
    content_blocks, structured = result
    assert isinstance(content_blocks[0], types.TextContent)
    assert structured["result"]["entries"] == [1]
    assert structured["result"]["status"] == "ok"


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
    aggregated = servers["tool_aggregator"]["tools"]["sample_fetch_suite"]

    required_fields = aggregated["inputSchema"]["required"]
    assert required_fields == ["operation"]

    enum_values = aggregated["inputSchema"]["properties"]["operation"]["enum"]
    assert {"fetch_document_links", "fetch_documentation_page"}.issubset(set(enum_values))

    docs_tools = servers["docs"]["tools"]
    for tool_name in ("fetch_document_links", "fetch_documentation_page"):
        assert tool_name in docs_tools
        assert docs_tools[tool_name]["enabled"] is False


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
                "name": "docs_suite",
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
                "name": "docs_suite",
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



def test_process_tool_aggregations_handles_missing_overrides(monkeypatch, tmp_path: Path) -> None:
    module = _load_process_tool_aggregations_module()
    config_root = tmp_path / "config-home"
    catalog_dir = config_root / "catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "core.json").write_text(
        json.dumps(
            {
                "tool_aggregations": {
                    "aggregations": [
                        {
                            "name": "docs_suite",
                            "description": "Docs",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"operation": {"type": "string"}},
                                "required": ["operation"],
                            },
                            "operations": [
                                {"value": "fetch", "downstreamTool": "docs.fetch"},
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    overrides_path = tmp_path / "tool_overrides.json"
    runtime_path = tmp_path / "runtime.json"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    config_home.cache_clear()
    state_home.cache_clear()

    argv = [
        "process_tool_aggregations",
        "--overrides",
        str(overrides_path),
        "--output",
        str(runtime_path),
        "--scope",
        "local",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    module.main()

    runtime_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    aggregator_tools = runtime_payload["servers"]["tool_aggregator"]["tools"]
    assert "docs_suite" in aggregator_tools

    config_home.cache_clear()
    state_home.cache_clear()



@pytest.mark.parametrize(("aggregation_name", "arguments"), STARTER_AGGREGATION_CASES)
def test_starter_bundle_aggregations_roundtrip_structured_payloads(
    aggregation_name: str, arguments: dict[str, Any]
) -> None:
    target = get_starter_bundle_aggregation(aggregation_name)
    schema = target.output_schema
    if not isinstance(schema, dict):
        pytest.skip(f"Starter bundle aggregation {aggregation_name} does not declare an output schema")
    structured_sample = build_sample_from_schema(schema)
    serialized = json.dumps(structured_sample, ensure_ascii=False)

    async def fake_call(name: str, params: dict[str, Any], timeout: float | None):
        # Aggregator should decode double-encoded payloads and leave structured content intact.
        return {
            "content": [{"type": "text", "text": serialized}],
            "structuredContent": serialized,
        }

    runner = AggregatedToolRunner(target, fake_call, fallback_timeout=20.0)
    result = asyncio.run(runner.dispatch(arguments))
    assert isinstance(result, tuple)
    contents, structured = result
    assert any(isinstance(block, types.TextContent) for block in contents), aggregation_name
    assert structured == structured_sample
    jsonschema.validate(structured, schema)
