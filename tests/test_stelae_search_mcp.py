import asyncio
import importlib
import sys
from pathlib import Path


def _import_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("STELAE_SEARCH_ROOT", str(tmp_path))
    monkeypatch.setenv("STELAE_RG_BIN", "nonexistent-rg")
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    sys.modules.pop("scripts.stelae_search_mcp", None)
    return importlib.import_module("scripts.stelae_search_mcp")


def test_search_returns_structured_results(monkeypatch, tmp_path: Path):
    module = _import_module(monkeypatch, tmp_path)
    sample = tmp_path / "notes.txt"
    sample.write_text("alpha beta gamma\nimportant needle here\n", encoding="utf-8")

    result = asyncio.run(module.search("needle"))

    assert result.structuredContent is not None
    assert result.structuredContent["count"] == 1
    match = result.structuredContent["matches"][0]
    assert match["path"].endswith("notes.txt")
    assert match["line"] == 2
    assert not result.isError
    assert result.content, "Expected human-readable summary content"



def test_run_server_uses_stdio_transport(monkeypatch, tmp_path: Path):
    module = _import_module(monkeypatch, tmp_path)

    recorded = {}

    def fake_run(transport: str):
        recorded['transport'] = transport

    monkeypatch.setattr(module.app, 'run', fake_run)

    module.run_server()

    assert recorded['transport'] == 'stdio'
