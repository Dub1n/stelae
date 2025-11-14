from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_env", ROOT / "scripts" / "setup_env.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_bootstrap_copies_example_and_symlinks(tmp_path: Path) -> None:
    module = _load_setup_module()
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
