import importlib
import json
import os
import sys
from pathlib import Path

import pytest

import stelae_lib.config_overlays as config_overlays
from stelae_lib.catalog_defaults import DEFAULT_CUSTOM_TOOLS


def _reload_server(monkeypatch: pytest.MonkeyPatch, config_home: Path) -> object:
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_home))
    config_overlays.config_home.cache_clear()
    config_overlays.state_home.cache_clear()
    sys.modules.pop("scripts.custom_tools_server", None)
    return importlib.import_module("scripts.custom_tools_server")


def test_seeds_config_home_with_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_home = tmp_path / "config-home"
    server = _reload_server(monkeypatch, config_home)
    config_path = server._config_path()
    assert config_path == config_home / "custom_tools.json"
    assert config_path.exists()
    assert json.loads(config_path.read_text(encoding="utf-8")) == DEFAULT_CUSTOM_TOOLS


def test_migrates_legacy_local_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_home = tmp_path / "config-home"
    legacy = config_home / "custom_tools.local.json"
    payload = {"tools": [{"name": "ping", "description": "Ping", "command": "echo"}]}
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps(payload), encoding="utf-8")
    server = _reload_server(monkeypatch, config_home)
    config_path = server._config_path()
    assert config_path.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")


def test_env_override_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom_path = tmp_path / "custom.json"
    payload = {"tools": [{"name": "hello", "description": "Hello", "command": "echo"}]}
    custom_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("STELAE_CUSTOM_TOOLS_CONFIG", str(custom_path))
    server = _reload_server(monkeypatch, tmp_path / "config-home")
    config_path = server._config_path()
    assert config_path == custom_path
    config_home_copy = Path(os.environ["STELAE_CONFIG_HOME"]) / "custom_tools.json"
    assert not config_home_copy.exists()
    loaded_path, specs = server._load_specs()
    assert loaded_path == custom_path
    assert len(specs) == 1
