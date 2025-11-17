import asyncio
import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import types

import scripts.stelae_streamable_mcp as hub
from tests._tool_override_test_helpers import (
    build_sample_from_schema,
    build_sample_runtime,
    get_starter_bundle_aggregation,
    get_tool_schema,
)

jsonschema = pytest.importorskip("jsonschema")


@pytest.fixture(autouse=True)
def _run_manage_tool_inline(monkeypatch):
    async def _inline_runner(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(hub, "_MANAGE_THREAD_RUNNER", _inline_runner)


@pytest.mark.anyio("asyncio")
async def test_search_returns_static_hits(monkeypatch):
    monkeypatch.setattr(hub, "STATIC_SEARCH_ENABLED", True)

    invoked = False

    async def fake_call(*args, **kwargs):
        nonlocal invoked
        invoked = True
        return hub.CallResult(content=[], structured_content=None)

    monkeypatch.setattr(hub, "_call_upstream_tool", fake_call)

    response = await hub.search("compliance")
    data = json.loads(response)
    results = data["results"]

    assert len(results) == 3

    ids = {item["id"] for item in results}
    assert ids == {
        "repo:docs/ARCHITECTURE.md",
        "repo:dev/chat_gpt_connector_compliant_reference.md",
        "repo:dev/compliance_handoff.md",
    }

    for entry in results:
        assert entry["text"]
        assert entry["metadata"]["snippet"]

    assert invoked is False


@pytest.mark.anyio("asyncio")
async def test_search_delegates_to_rg_when_static_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(hub, "STATIC_SEARCH_ENABLED", False)
    monkeypatch.setattr(hub, "SEARCH_ROOT", tmp_path)
    monkeypatch.setattr(hub, "DEFAULT_SEARCH_PATHS", (str(tmp_path),))

    sample_payload = json.dumps(
        [
            {
                "file": str(tmp_path / "notes.txt"),
                "line": "alpha",
                "line_num": 5,
            }
        ]
    )

    async def fake_call(server_name, tool_name, arguments, read_timeout=hub.SSE_READ_TIMEOUT):
        assert server_name == "rg"
        assert tool_name == "grep"
        return hub.CallResult(
            content=[types.TextContent(type="text", text=sample_payload)],
            structured_content=None,
        )

    monkeypatch.setattr(hub, "_call_upstream_tool", fake_call)

    response = await hub.search("needle")
    data = json.loads(response)
    assert data["results"], "Expected at least one result"
    first = data["results"][0]
    assert first["id"].endswith("notes.txt#L5")
    assert first["metadata"]["snippet"] == "alpha"


@pytest.mark.anyio("asyncio")
async def test_fetch_falls_back_to_raw(monkeypatch):
    responses = [
        hub.CallResult(
            content=[types.TextContent(type="text", text="Error ExtractArticle.js")],
            structured_content=None,
        ),
        hub.CallResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "id": "https://example.com",
                            "title": "Example",
                            "text": "Example body",
                            "url": "https://example.com",
                            "metadata": {},
                        }
                    ),
                )
            ],
            structured_content=None,
        ),
    ]

    async def fake_call(server_name, tool_name, arguments, read_timeout=hub.SSE_READ_TIMEOUT):
        call = responses.pop(0)
        if tool_name == "fetch" and arguments.get("raw"):
            assert "raw" in arguments and arguments["raw"] is True
        return call

    monkeypatch.setattr(hub, "_call_upstream_tool", fake_call)

    body = await hub.fetch("https://example.com", raw=False)
    data = json.loads(body)
    assert data["text"] == "Example body"
    assert data["metadata"] == {}


@pytest.mark.anyio("asyncio")
async def test_fetch_non_json_response(monkeypatch):
    async def fake_call(server_name, tool_name, arguments, read_timeout=hub.SSE_READ_TIMEOUT):
        return hub.CallResult(
            content=[types.TextContent(type="text", text="plain text output")],
            structured_content=None,
        )

    monkeypatch.setattr(hub, "_call_upstream_tool", fake_call)

    payload = await hub.fetch("https://example.com", raw=True)
    data = json.loads(payload)
    assert data["text"] == "plain text output"
    assert data["metadata"]["raw"] is True


@pytest.mark.anyio("asyncio")
async def test_proxy_mode_exposes_remote_catalog(monkeypatch):
    async def fake_proxy_jsonrpc(method, params=None, *, read_timeout=None):
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "read_file",
                        "description": "Read file contents",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                        "annotations": {
                            "readOnlyHint": True,
                        },
                    }
                ]
            }
        if method == "prompts/list":
            return {
                "prompts": [
                    {
                        "name": "documentation_sources",
                        "description": "List docs",
                        "arguments": [],
                    }
                ]
            }
        if method == "resources/list":
            return {
                "resources": [
                    {
                        "name": "grep_info",
                        "uri": "grep://info",
                        "mimeType": "text/plain",
                    }
                ]
            }
        if method == "prompts/get":
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": {"type": "text", "text": "hello"},
                    }
                ],
                "description": "List docs",
            }
        if method == "resources/read":
            return {
                "contents": [
                    {
                        "uri": "grep://info",
                        "mimeType": "text/plain",
                        "text": "grep info",
                    }
                ]
            }
        if method == "tools/call":
            return {
                "content": [
                    {"type": "text", "text": "file content"},
                ],
                "structuredContent": {"result": "ok"},
            }
        return {}

    # Activate proxy handlers with fake bridge
    hub._activate_proxy_handlers()
    hub.PROXY_MODE = True
    monkeypatch.setattr(hub, "_proxy_jsonrpc", fake_proxy_jsonrpc)

    tools = await hub.app.list_tools()
    names = [tool.name for tool in tools]
    assert "read_file" in names
    prompts = await hub.app.list_prompts()
    assert prompts and prompts[0].name == "documentation_sources"
    resources = await hub.app.list_resources()
    assert resources and str(resources[0].uri) == "grep://info"

    messages = await hub.app.get_prompt("documentation_sources", {})
    assert messages.description == "List docs"
    assert messages.messages[0].content.type == "text"

    contents = await hub.app.read_resource("grep://info")
    assert len(list(contents)) == 1

    call_result = await hub.app.call_tool("read_file", {"path": "README.md"})
    assert isinstance(call_result, tuple)
    content_blocks, structured = call_result
    assert structured == {"result": "ok"}
    assert content_blocks[0].type == "text"

@pytest.mark.anyio("asyncio")
async def test_workspace_fs_read_roundtrip(monkeypatch):
    payload = {
        "operation": "read_file",
        "path": "README.md",
        "text": "Hello from stub",
    }

    async def fake_proxy_jsonrpc(method, params=None, *, read_timeout=None):
        if method == "tools/call":
            assert params["name"] == "workspace_fs_read"
            args = params["arguments"]
            assert args["operation"] == "read_file"
            assert args["path"] == "README.md"
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload),
                    }
                ],
                "structuredContent": {"result": payload},
            }
        if method == "tools/list":
            return {"tools": []}
        return {}

    hub._activate_proxy_handlers()
    hub.PROXY_MODE = True
    monkeypatch.setattr(hub, "_proxy_jsonrpc", fake_proxy_jsonrpc)

    contents, structured = await hub.app.call_tool(
        "workspace_fs_read",
        {"operation": "read_file", "path": "README.md"},
    )

    assert structured == {"result": payload}
    text_blocks = [block for block in contents if isinstance(block, types.TextContent)]
    assert text_blocks, "expected at least one text block"
    decoded = json.loads(text_blocks[0].text)
    assert decoded == payload


def test_manage_stelae_schema_output(monkeypatch):
    schema = get_tool_schema("integrator", "manage_stelae")
    structured_sample = build_sample_from_schema(schema)
    result_payload = structured_sample.get("result", {})

    def fake_manage_operation(operation: str, params: dict[str, Any]):
        assert operation == "list_discovered_servers"
        return result_payload

    monkeypatch.setattr(hub, "_run_manage_operation", fake_manage_operation)

    async def _runner():
        contents, structured = await hub._call_manage_tool({"operation": "list_discovered_servers"})
        assert any(isinstance(block, types.TextContent) for block in contents)
        jsonschema.validate(structured, schema)
        assert structured == structured_sample

    asyncio.run(_runner())



def test_rendered_manifest_contains_only_aggregates(tmp_path: Path) -> None:
    fixture = build_sample_runtime(tmp_path)
    servers = fixture.runtime_payload["servers"]

    enabled = [
        (server, tool)
        for server, data in servers.items()
        for tool, descriptor in data["tools"].items()
        if descriptor.get("enabled", True)
    ]
    assert ("tool_aggregator", "sample_fetch_suite") in enabled
    assert ("docs", "fetch_document_links") not in enabled
    assert ("docs", "fetch_documentation_page") not in enabled

    schema = servers["tool_aggregator"]["tools"]["sample_fetch_suite"]["inputSchema"]
    assert len(schema["required"]) == len(set(schema["required"]))
    enum_values = schema["properties"]["operation"]["enum"]
    assert len(enum_values) == len(set(enum_values))
