import json
from pathlib import Path

import anyio
import pytest
from mcp import types

import scripts.stelae_streamable_mcp as hub


@pytest.mark.anyio
async def test_search_formats_results(monkeypatch, tmp_path):
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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
