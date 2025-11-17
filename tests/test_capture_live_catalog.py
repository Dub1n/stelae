import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_live_catalog as capture


def test_capture_live_catalog_writes_payload(tmp_path: Path) -> None:
    sample_response = {
        "jsonrpc": "2.0",
        "result": {
            "tools": [
                {"name": "foo"},
                {"name": "bar"},
            ]
        },
    }
    called = {}

    def fake_fetch(base: str, timeout: float) -> dict:
        called["base"] = base
        called["timeout"] = timeout
        return sample_response

    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    output_path = tmp_path / "live_catalog.json"
    result = capture.capture_live_catalog(
        proxy_base="http://proxy:9090",
        output_path=output_path,
        fetch_fn=fake_fetch,
        timestamp=ts,
        timeout=3.0,
    )

    assert called["base"] == "http://proxy:9090"
    assert called["timeout"] == pytest.approx(3.0)
    assert result.tool_count == 2
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["proxy_base"] == "http://proxy:9090"
    assert data["captured_at"] == "2024-01-01T00:00:00Z"
    assert data["tool_count"] == 2
    assert data["tools_list"] == sample_response


def test_fetch_tools_list_success(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps({"jsonrpc": "2.0", "result": {"tools": [{"name": "alpha"}]}}).encode(
        "utf-8"
    )
    observed = SimpleNamespace(url=None, headers={})

    class FakeResponse:
        status = 200

        def read(self) -> bytes:
            return body

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(req, timeout: float):
        observed.url = req.full_url
        observed.headers = dict(req.header_items())
        return FakeResponse()

    monkeypatch.setattr(capture.request, "urlopen", fake_urlopen)

    payload = capture.fetch_tools_list("http://localhost:9999", timeout=5.0)

    assert payload["result"]["tools"][0]["name"] == "alpha"
    assert observed.url == "http://localhost:9999/mcp"
    assert observed.headers.get("Content-Type") == "application/json" or observed.headers.get(
        "Content-type"
    ) == "application/json"
