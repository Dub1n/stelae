import json

import pytest
from mcp import types

import scripts.stelae_streamable_mcp as bridge


@pytest.mark.anyio("asyncio")
async def test_per_m2_price_extracts_matches(monkeypatch):
    text = "Ipe decking for £54.90 per m2 including VAT. Cumaru premium £72 per m²."
    fake_result = bridge.CallResult(
        content=[types.TextContent(type="text", text=text)],
        structured_content={"content": text, "metadata": {"mode": "basic"}},
    )

    async def fake_call(server, tool, arguments, **_kwargs):
        assert server == "scrapling"
        assert tool == "s_fetch_page"
        assert arguments["url"] == "https://example.com"
        return fake_result

    monkeypatch.setattr(bridge, "_call_upstream_tool", fake_call)
    content, metadata = await bridge._call_per_m2_tool({"url": "https://example.com", "limit": 1})
    payload = metadata["result"]
    assert payload["matches"], "should detect at least one price"
    match = payload["matches"][0]
    assert match["currency"] == "£"
    assert match["value"] == pytest.approx(54.90)
    assert "per m²" == match["unit"]
    # ensure response content mirrors metadata
    assert json.loads(content[0].text)["matches"][0]["value"] == pytest.approx(54.90)


@pytest.mark.anyio("asyncio")
async def test_per_m2_price_hints_when_scrapling_missing(monkeypatch):
    async def fake_call(*_args, **_kwargs):
        raise RuntimeError("Playwright browsers missing")

    monkeypatch.setattr(bridge, "_call_upstream_tool", fake_call)
    with pytest.raises(RuntimeError) as excinfo:
        await bridge._call_per_m2_tool({"url": "https://example.com"})
    assert "scrapling" in excinfo.value.args[0].lower()


def test_extract_per_m2_matches_supports_comma_decimal():
    regex = bridge._build_per_m2_regex(None, None)
    matches = bridge._extract_per_m2_matches("€45,50 per m2 intro offer", regex, limit=1, context_chars=40)
    assert matches[0]["currency"].lower() == "€"
    assert matches[0]["value"] == pytest.approx(45.5)
