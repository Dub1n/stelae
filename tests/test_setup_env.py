from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.catalog_defaults import DEFAULT_CATALOG_FRAGMENT, DEFAULT_TOOL_AGGREGATIONS, DEFAULT_TOOL_OVERRIDES


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
    assert overrides_path.exists()
    assert aggregations_path.exists()

    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    aggregations = json.loads(aggregations_path.read_text(encoding="utf-8"))
    assert overrides == DEFAULT_TOOL_OVERRIDES
    assert aggregations == DEFAULT_TOOL_AGGREGATIONS

    catalog_core = json.loads((config_home / "catalog" / "core.json").read_text(encoding="utf-8"))
    assert catalog_core == DEFAULT_CATALOG_FRAGMENT
