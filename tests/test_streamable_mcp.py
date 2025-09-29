import json
from pathlib import Path

import anyio
import pytest
from mcp import types

import scripts.stelae_streamable_mcp as hub


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
        "repo:docs/SPEC-v1.md",
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
    assert tools and tools[0].name == "read_file"
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
