import types as py_types

import pytest

import scripts.stelae_streamable_mcp as bridge


def _stub_tool(name: str) -> py_types.SimpleNamespace:
    return py_types.SimpleNamespace(name=name)


@pytest.mark.anyio("asyncio")
async def test_manage_tool_injected_when_proxy_catalog_is_empty(monkeypatch):
    async def fake_rpc(method, *_, **__):
        assert method == "tools/list"
        return {"tools": []}

    sentinel_manage = _stub_tool("manage_stelae")

    monkeypatch.setattr(bridge, "_proxy_jsonrpc", fake_rpc)
    monkeypatch.setattr(bridge, "_local_manage_tool_descriptor", lambda: sentinel_manage)
    monkeypatch.setattr(bridge, "_local_search_tool", lambda: _stub_tool("search"), raising=False)
    monkeypatch.setattr(bridge, "_local_fetch_tool", lambda: _stub_tool("fetch"), raising=False)
    bridge._MANAGE_TOOL_AVAILABLE = True

    tools = await bridge._proxy_list_tools(bridge.app)
    assert sentinel_manage in tools
    assert bridge._MANAGE_TOOL_AVAILABLE is False


@pytest.mark.anyio("asyncio")
async def test_manage_tool_detected_when_proxy_catalog_contains_entry(monkeypatch):
    async def fake_rpc(method, *_, **__):
        assert method == "tools/list"
        return {
            "tools": [
                {
                    "name": "manage_stelae",
                    "description": "Install/remove managed servers",
                    "inputSchema": {"type": "object"},
                }
            ]
        }

    monkeypatch.setattr(bridge, "_proxy_jsonrpc", fake_rpc)
    bridge._MANAGE_TOOL_AVAILABLE = False

    tools = await bridge._proxy_list_tools(bridge.app)
    names = [tool.name for tool in tools]
    assert names.count("manage_stelae") == 1
    assert bridge._MANAGE_TOOL_AVAILABLE is True


@pytest.mark.anyio("asyncio")
async def test_manage_tool_calls_short_circuit_only_when_unavailable(monkeypatch):
    async def fake_manage(arguments):
        return ([bridge.types.TextContent(type="text", text="local")], {"result": arguments})

    async def fake_rpc(method, params=None, **__):
        assert method == "tools/call"
        return {"content": [{"type": "text", "text": "proxied"}]}

    # Short-circuit path (not advertised by proxy)
    bridge._MANAGE_TOOL_AVAILABLE = False
    monkeypatch.setattr(bridge, "_call_manage_tool", fake_manage)
    monkeypatch.setattr(bridge, "_proxy_jsonrpc", fake_rpc)
    content, metadata = await bridge._proxy_call_tool(bridge.app, "manage_stelae", {"operation": "list_discovered_servers"})
    assert metadata["result"]["operation"] == "list_discovered_servers"
    assert content[0].text == "local"

    # Pass-through path (proxy advertises the tool)
    async def fail_manage(_):
        raise AssertionError("_call_manage_tool should not run when proxy has the tool")

    bridge._MANAGE_TOOL_AVAILABLE = True
    monkeypatch.setattr(bridge, "_call_manage_tool", fail_manage)
    called = {}

    async def rpc_proxy(method, params=None, **kwargs):
        assert method == "tools/call"
        called["params"] = params
        return {"content": [{"type": "text", "text": "proxied"}]}

    monkeypatch.setattr(bridge, "_proxy_jsonrpc", rpc_proxy)
    response = await bridge._proxy_call_tool(bridge.app, "manage_stelae", {"operation": "discover_servers"})
    assert called["params"]["name"] == "manage_stelae"
    assert isinstance(response, list)
    assert response[0].text == "proxied"
