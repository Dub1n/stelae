import json
from pathlib import Path

from mcp import types

from scripts.mcp_output_shim import (
    GenericResultWrapper,
    OverrideManager,
    ScraplingMetadataWrapper,
    ToolStateStore,
    extract_text,
    _string_field_from_schema,
)


def test_generic_wrapper_creates_structured_payload():
    wrapper = GenericResultWrapper()
    text, structured = wrapper.wrap("hello world")
    assert text == "hello world"
    assert structured == {"result": "hello world"}
    assert "result" in wrapper.schema["properties"]


def test_scrapling_wrapper_parses_metadata_block():
    payload = "METADATA: {\"total_length\": 10}\n\ncontent here"
    wrapper = ScraplingMetadataWrapper()
    text, structured = wrapper.wrap(payload)
    assert text == "content here"
    assert structured["metadata"]["adapter"] == "scrapling-shim"
    assert structured["metadata"]["total_length"] == 10


def test_tool_state_store_round_trip(tmp_path: Path):
    store_path = tmp_path / "state.json"
    store = ToolStateStore(store_path)
    store.set_state("scrapling", "s_fetch_page", state="wrapped", wrapper="scrapling_metadata", note=None)
    reloaded = ToolStateStore(store_path)
    state = reloaded.get("scrapling", "s_fetch_page")
    assert state["state"] == "wrapped"
    assert state["wrapper"] == "scrapling_metadata"


def test_override_manager_writes_schema(tmp_path: Path):
    schema = {"type": "object", "properties": {"result": {"type": "string"}}, "required": ["result"]}
    override_path = tmp_path / "overrides.json"
    manager = OverrideManager(override_path)
    changed = manager.apply_schema("scrapling", "s_fetch_page", schema)
    assert changed is True
    second = manager.apply_schema("scrapling", "s_fetch_page", schema)
    assert second is False
    with override_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["servers"]["scrapling"]["tools"]["s_fetch_page"]["outputSchema"]["required"] == ["result"]


def test_extract_text_prefers_text_content():
    content = [
        types.TextContent(type="text", text="needle"),
        types.TextContent(type="text", text="later"),
    ]
    assert extract_text(content) == "needle"


def test_string_field_selector():
    schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }
    assert _string_field_from_schema(schema) == "result"
    assert _string_field_from_schema({"properties": {"meta": {"type": "object"}}}) is None
