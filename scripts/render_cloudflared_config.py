#!/usr/bin/env python3
"""
Render ops/cloudflared.yml from layered templates and environment files.
- Figures out hostname from PUBLIC_BASE_URL if CF_PUBLIC_HOSTNAME is not set.
- Requires either CF_TUNNEL_UUID or CF_TUNNEL_NAME (UUID strongly preferred).
- Defaults CF_HA_CONNECTIONS=8, PUBLIC_PORT=9090.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.config_overlays import config_home, load_layered_env, overlay_path_for

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


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

    env_vals = load_layered_env(
        env_file=args.env_file,
        fallback_file=args.fallback_env,
        overlay_file=overlay_env,
        include_process_env=True,
        allow_unresolved=True,
    )
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
