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

from stelae_lib.config_overlays import config_home, deep_merge, load_layered_env, overlay_path_for, require_home_path

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
    parser.add_argument("--output", type=Path, help="Output path (defaults to PROXY_CONFIG env)")
    parser.add_argument("--env-file", default=_default_env_file(), type=Path)
    parser.add_argument(
        "--fallback-env",
        type=Path,
        help="Optional fallback env file (defaults to none to avoid repo fallbacks)",
    )
    parser.add_argument(
        "--overlay-env", type=Path, help="Optional overlay env file (defaults to ~/.config/stelae/.env.local)"
    )
    args = parser.parse_args()

    if not args.env_file.exists():
        raise SystemExit(f"[render-proxy] Env file not found: {args.env_file} (run scripts/setup_env.py first)")
    overlay_template = args.overlay_template or overlay_path_for(args.template)
    overlay_env = args.overlay_env or (config_home() / ".env.local")

    env_values = load_layered_env(
        env_file=args.env_file,
        fallback_file=args.fallback_env,
        overlay_file=overlay_env,
        include_process_env=True,
    )
    required_paths = [
        "STELAE_CONFIG_HOME",
        "STELAE_STATE_HOME",
        "TOOL_OVERRIDES_PATH",
        "TOOL_SCHEMA_STATUS_PATH",
        "STELAE_CUSTOM_TOOLS_CONFIG",
        "STELAE_DISCOVERY_PATH",
        "INTENDED_CATALOG_PATH",
        "LIVE_CATALOG_PATH",
    ]
    missing = [key for key in required_paths if not env_values.get(key)]
    if not env_values.get("PROXY_CONFIG") and not args.output:
        missing.append("PROXY_CONFIG")
    if missing:
        joined = ", ".join(sorted(missing))
        raise SystemExit(f"[render-proxy] Missing required env variable(s): {joined} (check {args.env_file})")
    proxy_port = env_values.get("PROXY_PORT")
    if not proxy_port:
        public_port = env_values.get("PUBLIC_PORT")
        if public_port:
            env_values["PROXY_PORT"] = public_port
        else:
            env_values["PROXY_PORT"] = "9090"

    output_candidate: Path | None = args.output
    if not output_candidate:
        env_output = env_values.get("PROXY_CONFIG")
        if not env_output:
            raise SystemExit("[render-proxy] Missing PROXY_CONFIG in env; set it or pass --output")
        output_candidate = Path(env_output)
    try:
        output_path = require_home_path(
            "PROXY_CONFIG",
            default=output_candidate,
            description="Proxy config output",
            allow_config=True,
            allow_state=True,
            create=True,
        )
    except ValueError as exc:
        raise SystemExit(f"[render-proxy] {exc}") from exc

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
        rendered_data = json.loads(rendered)
    except Exception as exc:
        raise SystemExit(f"Rendered JSON invalid: {exc}") from exc

    rendered = json.dumps(rendered_data, indent=2, ensure_ascii=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(
        "[render-proxy]"
        f" env_file={args.env_file}"
        f" overlay_env={overlay_env if overlay_env and overlay_env.exists() else 'none'}"
        f" template={args.template}"
        f" overlay={overlay_template or 'none'}"
        f" output={output_path}"
    )


if __name__ == "__main__":
    main()
