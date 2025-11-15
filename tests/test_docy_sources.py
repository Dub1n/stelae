import json
from pathlib import Path


def test_docy_sources_seeded() -> None:
    data = json.loads(Path("config/docy_sources.json").read_text(encoding="utf-8"))
    sources = data.get("sources") or []
    ids = {entry.get("id") for entry in sources}
    assert {"stelae-readme", "stelae-architecture"}.issubset(ids)
