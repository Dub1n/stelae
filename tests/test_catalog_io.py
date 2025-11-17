import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import config_home, state_home
from scripts import catalog_io


def _write_catalog(tmp_path: Path, tools: list[dict]) -> Path:
    path = tmp_path / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tools": tools}, ensure_ascii=False), encoding="utf-8")
    return path


def test_diff_catalogs_detects_missing_and_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_root = tmp_path / "config"
    state_root = config_root / ".state"
    state_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("STELAE_STATE_HOME", str(state_root))
    config_home.cache_clear()
    state_home.cache_clear()

    intended = _write_catalog(state_root / "a", [{"name": "one"}, {"name": "two"}])
    live = _write_catalog(state_root / "b", [{"name": "two"}, {"name": "three"}])

    intended_data = catalog_io.load_intended(intended)
    live_data = catalog_io.load_live(live)
    diff = catalog_io.diff_catalogs(intended_data, live_data)

    assert diff["missing"] == {"one"}
    assert diff["extra"] == {"three"}


def test_tool_names_handles_catalog_wrapper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_root = tmp_path / "config"
    state_root = config_root / ".state"
    state_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("STELAE_STATE_HOME", str(state_root))
    config_home.cache_clear()
    state_home.cache_clear()

    payload = {
        "catalog": {
            "tools": [
                {"name": "alpha"},
            ]
        },
        "tools": [
            {"name": "beta"},
        ],
    }
    intended = state_root / "intended.json"
    intended.write_text(json.dumps(payload), encoding="utf-8")

    data = catalog_io.load_intended(intended)
    diff = catalog_io.diff_catalogs(data, data)
    assert diff["missing"] == set()
    assert diff["extra"] == set()
