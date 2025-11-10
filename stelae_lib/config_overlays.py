from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


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
    target_dir = config_home() / relative.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / overlay_name


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

