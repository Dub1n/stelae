import json
from pathlib import Path

from scripts.populate_tool_overrides import OverridesStore, iter_stdio_servers, record_tool


def test_overrides_store_sets_schema_once(tmp_path: Path):
    path = tmp_path / "overrides.json"
    store = OverridesStore(path)
    schema = {"type": "object", "properties": {"result": {"type": "string"}}, "required": ["result"]}

    assert store.ensure_schema("scrapling", "s_fetch_page", "outputSchema", schema)
    assert store.ensure_schema("scrapling", "s_fetch_page", "outputSchema", schema) is False

    store.write()
    reloaded = OverridesStore(path)
    data = reloaded.data["servers"]["scrapling"]["tools"]["s_fetch_page"]
    assert data["outputSchema"]["required"] == ["result"]
    assert data["enabled"] is True


def test_record_tool_populates_global_block(tmp_path: Path):
    path = tmp_path / "overrides.json"
    store = OverridesStore(path)
    payload = {
        "name": "fs.directory_tree",
        "outputSchema": {"type": "object", "properties": {"result": {"type": "string"}}},
    }

    assert record_tool(store, None, payload, ("outputSchema",))
    assert record_tool(store, None, payload, ("outputSchema",)) is False

    store.write()
    data = json.loads(path.read_text())
    assert data["tools"]["fs.directory_tree"]["outputSchema"]["type"] == "object"


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
