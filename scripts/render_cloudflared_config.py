#!/usr/bin/env python3
"""
Render ops/cloudflared.yml from layered templates and environment files.
- Figures out hostname from PUBLIC_BASE_URL if CF_PUBLIC_HOSTNAME is not set.
- Requires either CF_TUNNEL_UUID or CF_TUNNEL_NAME (UUID strongly preferred).
- Defaults CF_HA_CONNECTIONS=8, PUBLIC_PORT=9090.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from stelae_lib.config_overlays import config_home, overlay_path_for

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def parse_env_file(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def expand(values: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}

    def resolve(name: str, stack: set[str]) -> str:
        if name in resolved:
            return resolved[name]
        if name not in values:
            return ""  # leave empty; we’ll validate later
        if name in stack:
            raise ValueError(f"circular variable: {' -> '.join([*stack, name])}")
        raw = values[name]

        def repl(m: re.Match[str]) -> str:
            return resolve(m.group(1), stack | {name})

        s = VAR_PATTERN.sub(repl, raw)
        resolved[name] = s
        return s

    for k in list(values.keys()):
        resolve(k, set())
    return resolved


def load_env(env_file: Path, fallback: Path | None, overlay_env: Path | None) -> dict[str, str]:
    merged = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    merged.update(parse_env_file(fallback))
    merged.update(parse_env_file(env_file))
    merged.update(parse_env_file(overlay_env))
    return expand(merged)


def compute(values: dict[str, str]) -> dict[str, str]:
    v = dict(values)  # copy

    # Hostname
    host = v.get("CF_PUBLIC_HOSTNAME")
    if not host:
        p = urlparse(v.get("PUBLIC_BASE_URL", ""))
        if p.hostname:
            host = p.hostname
    if not host:
        raise SystemExit(
            "CF_PUBLIC_HOSTNAME or a parseable PUBLIC_BASE_URL is required."
        )

    # Tunnel identity
    uuid = v.get("CF_TUNNEL_UUID", "").strip()
    name = v.get("CF_TUNNEL_NAME", "").strip()
    if not uuid and not name:
        raise SystemExit(
            "Provide CF_TUNNEL_UUID (preferred) or CF_TUNNEL_NAME in .env."
        )
    if not uuid:
        # allow name, but we still need credentials-file path; user must make sure it matches tunnel name
        uuid = (
            name  # used only to build default creds path if CF_CREDENTIALS_FILE not set
        )

    # Credentials file
    cred = v.get("CF_CREDENTIALS_FILE", "").strip()
    if not cred:
        cred = str(Path.home() / f".cloudflared/{uuid}.json")

    # Port + HA
    public_port = v.get("PUBLIC_PORT", "9090").strip() or "9090"
    ha = v.get("CF_HA_CONNECTIONS", "8").strip() or "8"

    # Fill the values the template expects
    v.update(
        {
            "CF_PUBLIC_HOSTNAME": host,
            "CF_TUNNEL_UUID": v.get("CF_TUNNEL_UUID") or uuid,
            "CF_CREDENTIALS_FILE": cred,
            "PUBLIC_PORT": public_port,
            "CF_HA_CONNECTIONS": ha,
        }
    )
    return v


def render(template: str, values: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values or values[key] == "":
            raise KeyError(f"Missing value for {key}")
        return values[key]

    return TEMPLATE_PATTERN.sub(repl, template)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render ops/cloudflared.yml from template and .env"
    )
    ap.add_argument(
        "--template", default=Path("stelae/ops/cloudflared.template.yml"), type=Path
    )
    ap.add_argument(
        "--overlay-template",
        type=Path,
        help="Optional overlay template path (defaults to ~/.config/stelae mirror)",
    )
    ap.add_argument("--output", default=Path("stelae/ops/cloudflared.yml"), type=Path)
    ap.add_argument("--env-file", default=Path("stelae/.env"), type=Path)
    ap.add_argument("--fallback-env", default=Path("stelae/.env.example"), type=Path)
    ap.add_argument(
        "--overlay-env",
        type=Path,
        help="Optional overlay env file (defaults to ~/.config/stelae/.env.local)",
    )
    args = ap.parse_args()

    overlay_template = args.overlay_template or overlay_path_for(args.template)
    overlay_env = args.overlay_env or (config_home() / ".env.local")

    env_vals = load_env(args.env_file, args.fallback_env, overlay_env)
    vals = compute(env_vals)
    template_path = (
        overlay_template
        if overlay_template and overlay_template.exists()
        else args.template
    )
    tmpl = template_path.read_text(encoding="utf-8")
    out = render(tmpl, vals)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
