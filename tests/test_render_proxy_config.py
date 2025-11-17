from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def test_render_proxy_config_disables_servers(tmp_path, monkeypatch) -> None:
    config_home = tmp_path / "config-home"
    config_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("STELAE_STATE_HOME", str(config_home / ".state"))
    monkeypatch.setenv("STELAE_ONE_MCP_VISIBLE", "false")
    monkeypatch.setenv("STELAE_FACADE_VISIBLE", "0")

    overlay_env = tmp_path / "overlay.env"
    overlay_env.write_text(
        f"STELAE_CONFIG_HOME={config_home}\nSTELAE_STATE_HOME={config_home}/.state\n",
        encoding="utf-8",
    )
    output = config_home / ".state" / "proxy.json"

    env = os.environ.copy()
    env["STELAE_CONFIG_HOME"] = str(config_home)
    env["STELAE_STATE_HOME"] = str(config_home / ".state")
    env["PROXY_CONFIG"] = str(output)
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_proxy_config.py"),
            "--template",
            str(ROOT / "config" / "proxy.template.json"),
            "--output",
            str(output),
            "--env-file",
            str(ROOT / ".env.example"),
            "--fallback-env",
            str(ROOT / ".env.example"),
            "--overlay-env",
            str(overlay_env),
        ],
        cwd=ROOT,
        env=env,
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    assert isinstance(servers, dict)
    assert "custom" in servers
