import scripts.scrapling_shim_mcp as shim
from mcp import types


def _result(text: str, structured: dict | None = None) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
    )


def test_parse_payload_with_metadata():
    payload = shim._parse_payload("METADATA: {\"foo\": 1}\n\nhello")
    assert payload["metadata"]["foo"] == 1
    assert payload["metadata"]["adapter"] == "scrapling-shim"
    assert payload["content"] == "hello"


def test_normalize_uses_existing_structured_block():
    content, structured = shim._normalize(
        "s_fetch_page",
        _result(
            "ignored",
            structured={"metadata": {"percent_retrieved": 50}, "content": "body"},
        ),
    )
    assert structured["metadata"]["percent_retrieved"] == 50
    assert content[0].text == "ignored"


def test_normalize_wraps_string_payload():
    content, structured = shim._normalize("s_fetch_pattern", _result("plain result"))
    assert structured["metadata"]["note"] == "metadata prefix missing"
    assert content[0].text == "plain result"
