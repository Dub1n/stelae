import json
from pathlib import Path

from scripts.populate_tool_overrides import _extract_servers, iter_stdio_servers, record_tool
from stelae_lib.integrator.tool_overrides import ToolOverridesStore


def test_overrides_store_sets_schema_once(tmp_path: Path):
    path = tmp_path / "overrides.json"
    store = ToolOverridesStore(path)
    schema = {"type": "object", "properties": {"result": {"type": "string"}}, "required": ["result"]}

    assert store.ensure_schema("scrapling", "s_fetch_page", "outputSchema", schema)
    assert store.ensure_schema("scrapling", "s_fetch_page", "outputSchema", schema) is False

    store.write()
    reloaded = ToolOverridesStore(path)
    data = reloaded.snapshot()["servers"]["scrapling"]["tools"]["s_fetch_page"]
    assert data["outputSchema"]["required"] == ["result"]
    assert data["enabled"] is True


def test_record_tool_populates_global_block(tmp_path: Path):
    path = tmp_path / "overrides.json"
    store = ToolOverridesStore(path)
    payload = {
        "name": "fs.directory_tree",
        "outputSchema": {"type": "object", "properties": {"result": {"type": "string"}}},
    }

    assert record_tool(store, ("fs",), payload, ("outputSchema",))
    assert record_tool(store, ("fs",), payload, ("outputSchema",)) is False

    store.write()
    data = json.loads(path.read_text())
    assert data["servers"]["fs"]["tools"]["fs.directory_tree"]["outputSchema"]["type"] == "object"


def test_extract_servers_prefers_metadata():
    entry = {
        "name": "demo",
        "x-stelae": {"servers": ["scrapling", "docs"]},
        "serverName": "ignored",
    }
    servers = _extract_servers(entry)
    assert servers == ["scrapling", "docs", "ignored"]


def test_iter_stdio_servers_filters_non_stdio():
    config = {
        "mcpServers": {
            "fs": {"type": "stdio", "command": "fs-server"},
            "http_only": {"type": "http", "command": "noop"},
            "implicit_stdio": {"command": "rg-server"},
            "missing": {"type": "stdio"},
        }
    }
    servers = list(iter_stdio_servers(config))
    names = {name for name, _ in servers}
    assert names == {"fs", "implicit_stdio"}
    for _, entry in servers:
        assert entry["command"] in {"fs-server", "rg-server"}
