#!/usr/bin/env python3
"""Bootstrap the active .env so it lives inside ${STELAE_CONFIG_HOME}."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.catalog_defaults import DEFAULT_CUSTOM_TOOLS
from stelae_lib.config_overlays import ensure_catalog_file, ensure_config_home_scaffold, validate_home_path, write_json

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


def _materialize_default_catalogs(*, repo_dir: Path, config_home: Path) -> None:
    raise SystemExit(
        "[setup-env] _materialize_default_catalogs requires state_root; call via bootstrap_env()"
    )


def _seed_core_catalog(*, config_home: Path) -> None:
    core_path = ensure_catalog_file(base=config_home)
    try:
        current = json.loads(core_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        current = {}
    if isinstance(current, dict) and current:
        return
    write_json(core_path, {})


def _seed_json_stub(target: Path, *, default: object, legacy_candidates: list[Path] | None = None) -> None:
    if target.exists():
        try:
            json.loads(target.read_text(encoding="utf-8"))
            return
        except json.JSONDecodeError:
            pass
    replaced = False
    if legacy_candidates:
        for legacy in legacy_candidates:
            if legacy.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                legacy.replace(target)
                replaced = True
                break
    target.parent.mkdir(parents=True, exist_ok=True)
    if replaced:
        return
    write_json(target, default)


def _resolve_home_json(
    env_var: str,
    default_path: Path,
    *,
    allow_state: bool,
) -> Path:
    override = os.environ.get(env_var)
    raw_path = Path(override).expanduser() if override else default_path
    try:
        return validate_home_path(
            raw_path,
            label=env_var,
            allow_config=True,
            allow_state=allow_state,
        )
    except ValueError as exc:
        raise SystemExit(f"[setup-env] {exc}") from exc


def _materialize_default_catalogs(*, config_home: Path, state_root: Path) -> None:
    overrides_path = _resolve_home_json(
        "STELAE_TOOL_OVERRIDES",
        config_home / "tool_overrides.json",
        allow_state=False,
    )
    aggregations_path = _resolve_home_json(
        "STELAE_TOOL_AGGREGATIONS",
        config_home / "tool_aggregations.json",
        allow_state=False,
    )
    custom_tools_path = _resolve_home_json(
        "STELAE_CUSTOM_TOOLS_CONFIG",
        config_home / "custom_tools.json",
        allow_state=False,
    )
    discovery_path = _resolve_home_json(
        "STELAE_DISCOVERY_PATH",
        state_root / "discovered_servers.json",
        allow_state=True,
    )
    runtime_overrides_path = _resolve_home_json(
        "TOOL_OVERRIDES_PATH",
        state_root / "tool_overrides.json",
        allow_state=True,
    )
    schema_status_path = _resolve_home_json(
        "TOOL_SCHEMA_STATUS_PATH",
        state_root / "tool_schema_status.json",
        allow_state=True,
    )
    intended_catalog_path = _resolve_home_json(
        "INTENDED_CATALOG_PATH",
        state_root / "intended_catalog.json",
        allow_state=True,
    )
    _seed_json_stub(
        overrides_path,
        default={},
        legacy_candidates=[config_home / "tool_overrides.local.json"],
    )
    _seed_json_stub(
        aggregations_path,
        default={},
        legacy_candidates=[config_home / "tool_aggregations.local.json"],
    )
    _seed_json_stub(custom_tools_path, default=DEFAULT_CUSTOM_TOOLS)
    _seed_json_stub(discovery_path, default=[])
    _seed_json_stub(runtime_overrides_path, default={})
    _seed_json_stub(schema_status_path, default={})
    _seed_json_stub(intended_catalog_path, default={})
    _seed_core_catalog(config_home=config_home)


def bootstrap_env(
    *,
    config_home: Path,
    repo_dir: Path,
    env_file: Path,
    example_path: Path,
    prefer_symlink: bool = True,
    materialize_defaults: bool = False,
) -> Path:
    """Ensure ${STELAE_CONFIG_HOME}/.env exists and repo/.env points to it."""
    repo_env = repo_dir / ".env"
    config_home = config_home.expanduser()
    if not config_home.is_absolute():
        raise SystemExit(f"[setup-env] STELAE_CONFIG_HOME must be absolute, got {config_home}")
    os.environ["STELAE_CONFIG_HOME"] = str(config_home)
    from stelae_lib import config_overlays as overlays

    overlays.config_home.cache_clear()
    overlays.state_home.cache_clear()
    config_home = overlays.config_home()

    state_root_candidate = Path(os.environ.get("STELAE_STATE_HOME") or (config_home / ".state")).expanduser()
    try:
        state_root = validate_home_path(state_root_candidate, label="STELAE_STATE_HOME", allow_config=True, allow_state=False)
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"[setup-env] {exc}") from exc
    os.environ["STELAE_STATE_HOME"] = str(state_root)
    overlays.state_home.cache_clear()
    state_root.mkdir(parents=True, exist_ok=True)

    env_file = env_file.expanduser()
    try:
        env_file = validate_home_path(env_file, label="STELAE_ENV_FILE", allow_config=True, allow_state=False)
    except ValueError as exc:
        raise SystemExit(f"[setup-env] {exc}") from exc
    os.environ["STELAE_ENV_FILE"] = str(env_file)

    def _finalize() -> Path:
        ensure_config_home_scaffold(base=config_home)
        if materialize_defaults:
            _materialize_default_catalogs(config_home=config_home, state_root=state_root)
        print(f"[setup-env] config_home={config_home}")
        print(f"[setup-env] state_home={state_root}")
        print(f"[setup-env] env_file={env_file}")
        return env_file

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
                return _finalize()
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
            return _finalize()
        except OSError as exc:
            print(f"[setup-env] Symlink failed ({exc}); falling back to copy.")

    _copy(env_file, repo_env)
    print(f"[setup-env] Copied {env_file} → {repo_env}")
    return _finalize()


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
    ap.add_argument(
        "--materialize-defaults",
        action="store_true",
        help="Write overlay copies of tool overrides/aggregations from embedded defaults.",
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
        materialize_defaults=args.materialize_defaults,
    )


if __name__ == "__main__":
    main()
