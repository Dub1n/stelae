import json
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

    assert len(result.content) == 1
    payload = json.loads(result.content[0].text)
    assert payload["results"]
    first = payload["results"][0]
    assert first["id"].endswith("notes.txt#L2")
    assert first["title"].endswith("notes.txt")
    assert first["url"].startswith("stelae://repo/notes.txt")


def test_run_server_uses_stdio_transport(monkeypatch, tmp_path: Path):
    module = _import_module(monkeypatch, tmp_path)

    recorded = {}

    def fake_run(transport: str):
        recorded['transport'] = transport

    monkeypatch.setattr(module.app, 'run', fake_run)

    module.run_server()

    assert recorded['transport'] == 'stdio'


def test_search_emits_debug_logs(monkeypatch, tmp_path: Path, caplog):
    monkeypatch.setenv("STELAE_SEARCH_DEBUG", "1")
    module = _import_module(monkeypatch, tmp_path)
    sample = tmp_path / "notes.txt"
    sample.write_text("alpha needle beta\nneedle again\n", encoding="utf-8")

    with caplog.at_level("DEBUG", logger="stelae.search"):
        asyncio.run(module.search("needle"))

    messages = [record.message for record in caplog.records if record.name == "stelae.search"]
    assert any("search start" in message for message in messages)
    assert any("search completed" in message for message in messages)


def test_fetch_returns_document(monkeypatch, tmp_path: Path):
    module = _import_module(monkeypatch, tmp_path)
    sample = tmp_path / "notes.txt"
    sample.write_text("alpha beta\nneedle line\n", encoding="utf-8")

    result = asyncio.run(module.fetch("repo:notes.txt#L2"))

    assert len(result.content) == 1
    document = json.loads(result.content[0].text)
    assert document["id"] == "repo:notes.txt#L2"
    assert document["title"] == "notes.txt"
    assert "needle line" in document["text"]
