from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence


VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


@lru_cache(maxsize=1)
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def config_home() -> Path:
    env = os.getenv("STELAE_CONFIG_HOME")
    if env:
        base = Path(env).expanduser()
    else:
        xdg = os.getenv("XDG_CONFIG_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
        base = base / "stelae"
    base.mkdir(parents=True, exist_ok=True)
    return base


@lru_cache(maxsize=1)
def state_home() -> Path:
    base = config_home() / ".state"
    base.mkdir(parents=True, exist_ok=True)
    return base


def runtime_path(filename: str) -> Path:
    """Return the canonical path for runtime-generated files, migrating old copies."""
    destination = state_home() / filename
    legacy_candidates = [
        config_home() / filename,
        config_home() / "config" / filename,
        config_home() / "stelae" / "config" / filename,
    ]
    for legacy in legacy_candidates:
        if legacy == destination:
            continue
        if legacy.exists():
            ensure_parent(destination)
            if destination.exists():
                legacy.unlink(missing_ok=True)
            else:
                legacy.replace(destination)
            break
    ensure_parent(destination)
    return destination


def _with_local_suffix(filename: str) -> str:
    if filename.startswith(".") and filename.count(".") == 1:
        return f"{filename}.local"
    suffix = Path(filename).suffix
    if not suffix:
        return f"{filename}.local"
    prefix = filename[: -len(suffix)]
    if not prefix:
        return f"{filename}.local{suffix}"
    return f"{prefix}.local{suffix}"


def overlay_path_for(base_path: Path, *, root: Path | None = None) -> Path:
    root = root or repo_root()
    absolute = base_path if base_path.is_absolute() else (root / base_path)
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        relative = Path(absolute.name)
    overlay_name = _with_local_suffix(relative.name)
    destination = config_home() / overlay_name

    legacy_path: Path | None = None
    if relative.parent != Path("."):
        legacy_candidate = config_home() / relative.parent / overlay_name
        if legacy_candidate != destination:
            legacy_path = legacy_candidate
    if legacy_path and legacy_path.exists() and not destination.exists():
        ensure_parent(destination)
        legacy_path.replace(destination)
        try:
            legacy_parent = legacy_path.parent
            legacy_parent.rmdir()
        except OSError:
            pass

    ensure_parent(destination)
    return destination


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def deep_merge(dest: Any, src: Any) -> Any:
    if isinstance(dest, dict) and isinstance(src, Mapping):
        result = {key: json.loads(json.dumps(value, ensure_ascii=False)) for key, value in dest.items()}
        for key, value in src.items():
            if key in result:
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = json.loads(json.dumps(value, ensure_ascii=False)) if isinstance(value, (dict, list)) else value
        return result
    if isinstance(dest, list) and isinstance(src, list):
        return list(dest) + list(src)
    return json.loads(json.dumps(src, ensure_ascii=False))


def load_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return json.loads(json.dumps(default, ensure_ascii=False))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_env_file(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path or not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"')
    return values


def expand_env_values(
    values: Mapping[str, str],
    *,
    fallback: Mapping[str, str] | None = None,
    allow_unresolved: bool = False,
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    fallback = fallback or {}

    def resolve(name: str, stack: set[str]) -> str:
        if name in resolved:
            return resolved[name]
        if name in values:
            if name in stack:
                chain = " -> ".join(list(stack) + [name])
                raise ValueError(f"Circular variable expansion detected: {chain}")
            raw_value = values[name]

            def replace(match: re.Match[str]) -> str:
                inner = match.group(1)
                return resolve(inner, stack | {name})

            expanded = VAR_PATTERN.sub(replace, raw_value)
            resolved[name] = expanded
            return expanded
        if name in fallback:
            return fallback[name]
        if allow_unresolved:
            resolved[name] = ""
            return ""
        raise KeyError(f"Missing environment variable: {name}")

    for key in values:
        resolve(key, set())

    return resolved


def load_layered_env(
    *,
    env_file: Path | None = None,
    fallback_file: Path | None = None,
    overlay_file: Path | None = None,
    extra_files: Sequence[Path | None] | None = None,
    include_process_env: bool = True,
    base_env: Mapping[str, str] | None = None,
    allow_unresolved: bool = False,
) -> dict[str, str]:
    base: dict[str, str] = {}
    if base_env:
        for key, value in base_env.items():
            if isinstance(key, str) and isinstance(value, str):
                base[key] = value
    if include_process_env:
        for key, value in os.environ.items():
            if isinstance(key, str) and isinstance(value, str):
                base.setdefault(key, value)

    merged: dict[str, str] = {}
    for candidate in filter(None, [fallback_file, env_file, overlay_file]):
        merged.update(parse_env_file(candidate))
    if extra_files:
        for candidate in extra_files:
            merged.update(parse_env_file(candidate))

    expanded = expand_env_values(merged, fallback=base, allow_unresolved=allow_unresolved)
    merged_env = dict(base)
    merged_env.update(expanded)
    return merged_env
