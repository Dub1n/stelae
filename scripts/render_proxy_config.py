#!/usr/bin/env python3
"""Render config/proxy.json from a template and environment variables."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


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


def expand_variables(values: dict[str, str], fallback: dict[str, str] | None = None) -> dict[str, str]:
    """Expand ${VAR} expressions defined in .env files.

    Only keys provided in *values* participate in recursive expansion so that
    inherited shell variables containing prompt escapes (e.g. powerlevel10k's
    P9K_*) do not trigger missing-variable errors. When an expanded name is not
    present in *values*, we fall back to the original process environment.
    """

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
            resolved[name] = fallback[name]
            return fallback[name]
        raise KeyError(f"Missing environment variable: {name}")

    for key in values:
        resolve(key, set())

    return resolved


def load_env(env_file: Path, fallback_file: Path | None) -> dict[str, str]:
    base_env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    merged: dict[str, str] = {}
    merged.update(parse_env_file(fallback_file))
    merged.update(parse_env_file(env_file))
    expanded = expand_variables(merged, fallback=base_env)
    merged_env = dict(base_env)
    merged_env.update(expanded)
    return merged_env


def render(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"Missing environment variable: {key}")
        return values[key]

    return TEMPLATE_PATTERN.sub(replace, template)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render proxy.json from template")
    parser.add_argument(
        "--template", default=Path("config/proxy.template.json"), type=Path
    )
    parser.add_argument("--output", default=Path("config/proxy.json"), type=Path)
    parser.add_argument("--env-file", default=Path(".env"), type=Path)
    parser.add_argument("--fallback-env", default=Path(".env.example"), type=Path)
    args = parser.parse_args()

    env_values = load_env(args.env_file, args.fallback_env)
    template_text = args.template.read_text(encoding="utf-8")
    rendered = render(template_text, env_values)

    import json

    try:
        json.loads(rendered)
    except Exception as e:
        raise SystemExit(f"Rendered JSON invalid: {e}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
