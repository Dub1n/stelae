#!/usr/bin/env python3
"""Bootstrap the active .env so it lives inside ${STELAE_CONFIG_HOME}."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def repo_root() -> Path:
    return ROOT


def default_config_home() -> Path:
    value = os.environ.get("STELAE_CONFIG_HOME")
    if value:
        return Path(value).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "stelae"
    return Path.home() / ".config" / "stelae"


def default_env_file(config_home: Path) -> Path:
    value = os.environ.get("STELAE_ENV_FILE")
    if value:
        return Path(value).expanduser()
    return config_home / ".env"


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except FileNotFoundError:
        return path


def _files_match(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    try:
        return os.path.samefile(a, b)
    except FileNotFoundError:
        return False
    except OSError:
        return _resolve(a) == _resolve(b)


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _move(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dest)


def bootstrap_env(
    *,
    config_home: Path,
    repo_dir: Path,
    env_file: Path,
    example_path: Path,
    prefer_symlink: bool = True,
) -> Path:
    """Ensure ${STELAE_CONFIG_HOME}/.env exists and repo/.env points to it."""
    repo_env = repo_dir / ".env"
    config_home.mkdir(parents=True, exist_ok=True)
    env_file = env_file.expanduser()
    if not example_path.exists():
        raise FileNotFoundError(f"Template not found: {example_path}")

    # Seed config-home env if missing.
    if not env_file.exists():
        if repo_env.exists() and not repo_env.is_symlink():
            print(f"[setup-env] Moving existing {repo_env} → {env_file}")
            _move(repo_env, env_file)
        else:
            print(f"[setup-env] Copying template {example_path} → {env_file}")
            _copy(example_path, env_file)

    # Ensure repo/.env mirrors the config-home file.
    if repo_env.is_symlink():
        try:
            if os.path.samefile(repo_env, env_file):
                return env_file
        except FileNotFoundError:
            pass
        repo_env.unlink()
    elif repo_env.exists() and not _files_match(repo_env, env_file):
        backup = repo_env.with_suffix(repo_env.suffix + ".backup")
        print(f"[setup-env] Backing up existing {repo_env} → {backup}")
        if backup.exists():
            backup.unlink()
        repo_env.rename(backup)

    if prefer_symlink:
        try:
            if repo_env.exists():
                repo_env.unlink()
            repo_env.symlink_to(env_file)
            print(f"[setup-env] Symlinked {repo_env} → {env_file}")
            return env_file
        except OSError as exc:
            print(f"[setup-env] Symlink failed ({exc}); falling back to copy.")

    _copy(env_file, repo_env)
    print(f"[setup-env] Copied {env_file} → {repo_env}")
    return env_file


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Copy .env.example → ${STELAE_CONFIG_HOME}/.env and keep repo/.env synced."
    )
    ap.add_argument("--config-home", type=Path, help="Override config home (default ${STELAE_CONFIG_HOME})")
    ap.add_argument("--repo-root", type=Path, help="Path to the repo that should expose ./.env")
    ap.add_argument("--env-file", type=Path, help="Override the target env file path")
    ap.add_argument("--example", type=Path, help="Path to the template env file (defaults to repo/.env.example)")
    ap.add_argument(
        "--copy",
        action="store_true",
        help="Copy instead of symlink repo/.env (symlinks are attempted by default)",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    config_home = (args.config_home or default_config_home()).expanduser()
    repo_dir = (args.repo_root or repo_root()).expanduser()
    env_file = (args.env_file or default_env_file(config_home)).expanduser()
    example_path = (args.example or (repo_dir / ".env.example")).expanduser()
    bootstrap_env(
        config_home=config_home,
        repo_dir=repo_dir,
        env_file=env_file,
        example_path=example_path,
        prefer_symlink=not args.copy,
    )


if __name__ == "__main__":
    main()
