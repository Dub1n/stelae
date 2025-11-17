from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
CATALOG_DIRNAME = "catalog"
BUNDLES_DIRNAME = "bundles"
BUNDLE_PLACEHOLDER = ".placeholder.json"
SERVER_FLAG_VARS = {
    "one_mcp": "STELAE_ONE_MCP_VISIBLE",
    "facade": "STELAE_FACADE_VISIBLE",
}


@lru_cache(maxsize=1)
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_under_root(target: Path, root: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def config_home() -> Path:
    env = os.getenv("STELAE_CONFIG_HOME")
    if env:
        base = Path(env).expanduser()
        if not base.is_absolute():
            raise ValueError(f"STELAE_CONFIG_HOME must be absolute, got {base}")
    else:
        xdg = os.getenv("XDG_CONFIG_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
        base = base / "stelae"
    base.mkdir(parents=True, exist_ok=True)
    return base


@lru_cache(maxsize=1)
def state_home() -> Path:
    base_env = os.getenv("STELAE_STATE_HOME")
    base = Path(base_env).expanduser() if base_env else config_home() / ".state"
    if not base.is_absolute():
        raise ValueError(f"STELAE_STATE_HOME must be absolute, got {base}")
    if not _is_under_root(base, config_home()):
        raise ValueError(f"STELAE_STATE_HOME must live under {config_home()}, got {base}")
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


def overlay_path_for(base_path: Path, *, root: Path | None = None, config_base: Path | None = None) -> Path:
    root = root or repo_root()
    home = (config_base or config_home()).expanduser()
    absolute = base_path if base_path.is_absolute() else (root / base_path)
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        relative = Path(absolute.name)
    overlay_name = _with_local_suffix(relative.name)
    destination = home / overlay_name

    legacy_path: Path | None = None
    if relative.parent != Path("."):
        legacy_candidate = home / relative.parent / overlay_name
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


def _normalize_json_name(name: str, *, default: str | None = None) -> str:
    trimmed = str(name or "").strip()
    if not trimmed and default:
        trimmed = default
    if not trimmed:
        raise ValueError("JSON filename must be non-empty")
    return trimmed if trimmed.endswith(".json") else f"{trimmed}.json"


def ensure_catalog_file(name: str = "core.json", *, base: Path | None = None) -> Path:
    home = (base or config_home()).expanduser()
    catalog_dir = home / CATALOG_DIRNAME
    catalog_dir.mkdir(parents=True, exist_ok=True)
    filename = _normalize_json_name(name, default="core.json")
    path = catalog_dir / filename
    if not path.exists():
        write_json(path, {})
    return path


def ensure_bundle_catalog(bundle_name: str, *, base: Path | None = None, filename: str = "catalog.json") -> Path:
    normalized_bundle = str(bundle_name or "").strip()
    if not normalized_bundle:
        raise ValueError("Bundle name must be non-empty")
    home = (base or config_home()).expanduser()
    bundle_dir = home / BUNDLES_DIRNAME / normalized_bundle
    bundle_dir.mkdir(parents=True, exist_ok=True)
    target = bundle_dir / _normalize_json_name(filename, default="catalog.json")
    if not target.exists():
        write_json(target, {})
    return target


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return None


def server_enabled(name: str) -> bool:
    env_var = SERVER_FLAG_VARS.get(name)
    if env_var:
        overridden = _coerce_bool(os.environ.get(env_var))
        if overridden is not None:
            return overridden
    return True


def ensure_config_home_scaffold(*, base: Path | None = None, catalog_files: Sequence[str] | None = None) -> dict[str, Path]:
    home = (base or config_home()).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    names = list(catalog_files or ["core.json"])
    first_name = names[0] if names else "core.json"
    catalog_dir = ensure_catalog_file(first_name, base=home).parent
    for name in names[1:]:
        ensure_catalog_file(name, base=home)
    bundles_dir = home / BUNDLES_DIRNAME
    bundles_dir.mkdir(parents=True, exist_ok=True)
    placeholder = bundles_dir / BUNDLE_PLACEHOLDER
    if not placeholder.exists():
        write_json(placeholder, {})
    return {"config_home": home, "catalog_dir": catalog_dir, "bundles_dir": bundles_dir, "state_home": state_home()}


def ensure_overlay_from_defaults(
    base_path: Path,
    default_payload: Mapping[str, Any],
    *,
    root: Path | None = None,
    config_base: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write an overlay file seeded from embedded defaults, if missing."""

    overlay = overlay_path_for(base_path, root=root, config_base=config_base)
    if overlay.exists() and not overwrite:
        return overlay
    ensure_parent(overlay)
    payload_copy = json.loads(json.dumps(default_payload, ensure_ascii=False))
    write_json(overlay, payload_copy)
    return overlay


def validate_home_path(
    path: Path,
    *,
    label: str | None = None,
    allow_config: bool = True,
    allow_state: bool = True,
) -> Path:
    target = path.expanduser()
    if not target.is_absolute():
        raise ValueError(f"{label or 'Path'} must be absolute, got {target}")
    allowed_roots: list[Path] = []
    if allow_config:
        allowed_roots.append(config_home())
    if allow_state:
        allowed_roots.append(state_home())
    if allowed_roots and not any(_is_under_root(target, root) or target == root for root in allowed_roots):
        roots = ", ".join(str(root) for root in allowed_roots)
        raise ValueError(f"{label or 'Path'} must live under {roots}: {target}")
    return target


def require_home_path(
    var_name: str,
    *,
    default: Path | None = None,
    allow_config: bool = True,
    allow_state: bool = True,
    description: str | None = None,
    create: bool = False,
) -> Path:
    raw_value = os.getenv(var_name)
    candidate = Path(raw_value).expanduser() if raw_value else default
    if candidate is None:
        raise ValueError(f"{description or var_name} is required; set {var_name}")
    validated = validate_home_path(candidate, label=description or var_name, allow_config=allow_config, allow_state=allow_state)
    if create:
        validated.parent.mkdir(parents=True, exist_ok=True)
    return validated


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
