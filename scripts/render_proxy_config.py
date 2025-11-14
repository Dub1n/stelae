#!/usr/bin/env python3
"""Render the proxy config from layered templates and environment variables."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import config_home, deep_merge, load_layered_env, overlay_path_for

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


def _default_env_file() -> Path:
    candidate = os.environ.get("STELAE_ENV_FILE")
    if candidate:
        return Path(candidate).expanduser()
    return config_home() / ".env"


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
    parser.add_argument(
        "--overlay-template", type=Path, help="Optional overlay template path (defaults to ~/.config/stelae mirror)"
    )
    parser.add_argument("--output", default=Path("config/proxy.json"), type=Path)
    parser.add_argument("--env-file", default=_default_env_file(), type=Path)
    parser.add_argument("--fallback-env", default=Path(".env.example"), type=Path)
    parser.add_argument(
        "--overlay-env", type=Path, help="Optional overlay env file (defaults to ~/.config/stelae/.env.local)"
    )
    args = parser.parse_args()

    overlay_template = args.overlay_template or overlay_path_for(args.template)
    overlay_env = args.overlay_env or (config_home() / ".env.local")

    env_values = load_layered_env(
        env_file=args.env_file,
        fallback_file=args.fallback_env,
        overlay_file=overlay_env,
        include_process_env=True,
    )
    proxy_port = env_values.get("PROXY_PORT")
    if not proxy_port:
        public_port = env_values.get("PUBLIC_PORT")
        if public_port:
            env_values["PROXY_PORT"] = public_port
        else:
            env_values["PROXY_PORT"] = "9090"

    try:
        base_template = json.loads(args.template.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Template {args.template} invalid JSON: {exc}") from exc

    merged_template = base_template
    if overlay_template and overlay_template.exists():
        try:
            overlay_data = json.loads(overlay_template.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Overlay template {overlay_template} invalid JSON: {exc}") from exc
        merged_template = deep_merge(base_template, overlay_data)

    template_text = json.dumps(merged_template, indent=2, ensure_ascii=False)
    rendered = render(template_text, env_values)

    try:
        json.loads(rendered)
    except Exception as exc:
        raise SystemExit(f"Rendered JSON invalid: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
