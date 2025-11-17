from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.catalog_defaults import DEFAULT_CUSTOM_TOOLS
from stelae_lib import config_overlays


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_env", ROOT / "scripts" / "setup_env.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_bootstrap_copies_example_and_symlinks(tmp_path: Path) -> None:
    module = _load_setup_module()
    os.environ.pop("STELAE_STATE_HOME", None)
    os.environ.pop("STELAE_CONFIG_HOME", None)
    repo = tmp_path / "repo"
    repo.mkdir()
    example = repo / ".env.example"
    example.write_text("A=1\n", encoding="utf-8")
    config_home = tmp_path / "config-home"
    env_file = config_home / ".env"

    module.bootstrap_env(
        config_home=config_home,
        repo_dir=repo,
        env_file=env_file,
        example_path=example,
    )

    repo_env = repo / ".env"
    assert env_file.exists()
    assert repo_env.exists()
    assert repo_env.is_symlink() or repo_env.read_text(encoding="utf-8") == env_file.read_text(encoding="utf-8")
    assert env_file.read_text(encoding="utf-8") == "A=1\n"
    if repo_env.is_symlink():
        assert os.path.samefile(repo_env, env_file)


def test_bootstrap_migrates_existing_repo_env(tmp_path: Path) -> None:
    module = _load_setup_module()
    os.environ.pop("STELAE_STATE_HOME", None)
    os.environ.pop("STELAE_CONFIG_HOME", None)
    repo = tmp_path / "repo"
    repo.mkdir()
    example = repo / ".env.example"
    example.write_text("EXAMPLE=1\n", encoding="utf-8")
    repo_env = repo / ".env"
    repo_env.write_text("CUSTOM=42\n", encoding="utf-8")
    config_home = tmp_path / "config-home"
    env_file = config_home / ".env"

    module.bootstrap_env(
        config_home=config_home,
        repo_dir=repo,
        env_file=env_file,
        example_path=example,
    )

    assert env_file.read_text(encoding="utf-8") == "CUSTOM=42\n"
    migrated_repo_env = repo / ".env"
    assert migrated_repo_env.exists()
    if migrated_repo_env.is_symlink():
        assert os.path.samefile(migrated_repo_env, env_file)
    else:
        assert migrated_repo_env.read_text(encoding="utf-8") == "CUSTOM=42\n"


def test_bootstrap_scaffolds_catalog_and_bundles(tmp_path: Path) -> None:
    module = _load_setup_module()
    os.environ.pop("STELAE_STATE_HOME", None)
    os.environ.pop("STELAE_CONFIG_HOME", None)
    repo = tmp_path / "repo"
    repo.mkdir()
    example = repo / ".env.example"
    example.write_text("A=1\n", encoding="utf-8")
    config_home = tmp_path / "config-home"
    env_file = config_home / ".env"

    module.bootstrap_env(
        config_home=config_home,
        repo_dir=repo,
        env_file=env_file,
        example_path=example,
    )

    catalog_core = config_home / "catalog" / "core.json"
    bundles_placeholder = config_home / "bundles" / ".placeholder.json"
    assert json.loads(catalog_core.read_text(encoding="utf-8")) == {}
    assert json.loads(bundles_placeholder.read_text(encoding="utf-8")) == {}


def test_bootstrap_materializes_embedded_defaults(tmp_path: Path) -> None:
    module = _load_setup_module()
    os.environ.pop("STELAE_STATE_HOME", None)
    os.environ.pop("STELAE_CONFIG_HOME", None)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir(parents=True)
    example = repo / ".env.example"
    example.write_text("A=1\n", encoding="utf-8")
    config_home = tmp_path / "config-home"
    env_file = config_home / ".env"

    module.bootstrap_env(
        config_home=config_home,
        repo_dir=repo,
        env_file=env_file,
        example_path=example,
        materialize_defaults=True,
    )

    overrides_path = config_home / "tool_overrides.json"
    aggregations_path = config_home / "tool_aggregations.json"
    custom_tools_path = config_home / "custom_tools.json"
    discovery_path = config_home / ".state" / "discovered_servers.json"
    runtime_overrides_path = config_home / ".state" / "tool_overrides.json"
    schema_status_path = config_home / ".state" / "tool_schema_status.json"
    intended_catalog_path = config_home / ".state" / "intended_catalog.json"
    assert overrides_path.exists()
    assert aggregations_path.exists()
    assert custom_tools_path.exists()
    assert discovery_path.exists()
    assert runtime_overrides_path.exists()
    assert schema_status_path.exists()
    assert intended_catalog_path.exists()

    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    aggregations = json.loads(aggregations_path.read_text(encoding="utf-8"))
    custom_tools = json.loads(custom_tools_path.read_text(encoding="utf-8"))
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    runtime_overrides = json.loads(runtime_overrides_path.read_text(encoding="utf-8"))
    schema_status = json.loads(schema_status_path.read_text(encoding="utf-8"))
    intended_catalog = json.loads(intended_catalog_path.read_text(encoding="utf-8"))
    assert overrides == {}
    assert aggregations == {}
    assert custom_tools == DEFAULT_CUSTOM_TOOLS
    assert discovery == []
    assert runtime_overrides == {}
    assert schema_status == {}
    assert intended_catalog == {}

    catalog_core = json.loads((config_home / "catalog" / "core.json").read_text(encoding="utf-8"))
    assert catalog_core == {}


def test_materialize_defaults_respects_env_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_setup_module()
    config_overlays.config_home.cache_clear()
    config_overlays.state_home.cache_clear()
    monkeypatch.delenv("STELAE_STATE_HOME", raising=False)
    monkeypatch.delenv("STELAE_CONFIG_HOME", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    example = repo / ".env.example"
    example.write_text("A=1\n", encoding="utf-8")

    config_home = tmp_path / "config-home"
    env_file = config_home / ".env"
    custom_overrides = config_home / "overrides" / "custom.json"
    custom_aggregations = config_home / "aggregations" / "custom.json"
    custom_tools_path = config_home / "custom" / "tools.json"
    state_home = config_home / ".state"
    discovery_path = state_home / "discover" / "servers.json"
    runtime_overrides_path = state_home / "runtime" / "tool_overrides.json"

    monkeypatch.setenv("STELAE_TOOL_OVERRIDES", str(custom_overrides))
    monkeypatch.setenv("STELAE_TOOL_AGGREGATIONS", str(custom_aggregations))
    monkeypatch.setenv("STELAE_CUSTOM_TOOLS_CONFIG", str(custom_tools_path))
    monkeypatch.setenv("STELAE_DISCOVERY_PATH", str(discovery_path))
    monkeypatch.setenv("TOOL_OVERRIDES_PATH", str(runtime_overrides_path))

    module.bootstrap_env(
        config_home=config_home,
        repo_dir=repo,
        env_file=env_file,
        example_path=example,
        materialize_defaults=True,
    )

    assert custom_overrides.exists()
    assert custom_aggregations.exists()
    assert custom_tools_path.exists()
    assert discovery_path.exists()
    assert runtime_overrides_path.exists()
    assert not (config_home / "tool_overrides.json").exists()
    assert not (config_home / "tool_aggregations.json").exists()
    assert json.loads(custom_overrides.read_text(encoding="utf-8")) == {}
    assert json.loads(custom_aggregations.read_text(encoding="utf-8")) == {}
    assert json.loads(custom_tools_path.read_text(encoding="utf-8")) == DEFAULT_CUSTOM_TOOLS
    assert json.loads(discovery_path.read_text(encoding="utf-8")) == []
    assert json.loads(runtime_overrides_path.read_text(encoding="utf-8")) == {}
