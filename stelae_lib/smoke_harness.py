#!/usr/bin/env python3
"""Utility helpers for the clone smoke-test harness."""

from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping

SMOKE_ENV_KEYS = (
    "STELAE_DIR",
    "APPS_DIR",
    "VENDOR_DIR",
    "STELAE_CONFIG_HOME",
    "PROXY_BIN",
    "PROXY_CONFIG",
    "PHOENIX_ROOT",
    "MEMORY_DIR",
    "SEARCH_ROOT",
    "SEARCH_PYTHON_BIN",
    "LOCAL_BIN",
    "FILESYSTEM_BIN",
    "RG_BIN",
    "STRATA_BIN",
    "DOCY_BIN",
    "MEMORY_BIN",
    "SHELL_BIN",
    "PLAYWRIGHT_BROWSERS_PATH",
    "CODEX_WRAPPER_BIN",
    "CODEX_WRAPPER_CONFIG",
    "PM2",
    "ONE_MCP_BIN",
    "ONE_MCP_DIR",
    "STELAE_DISCOVERY_PATH",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "PYTHON",
    "SHIM_PYTHON",
    "CLOUDFLARED",
    "CF_TUNNEL_NAME",
    "TOOL_OVERRIDES_PATH",
    "TOOL_SCHEMA_STATUS_PATH",
    "PUBLIC_PORT",
    "PUBLIC_BASE_URL",
    "PUBLIC_SSE_URL",
    "BASIC_MEMORY_PROJECT",
)


def choose_proxy_port(*, seed: int | None = None) -> int:
    """Pick a deterministic-but-random high port that avoids the defaults."""
    rng = random.Random(seed if seed is not None else random.SystemRandom().randint(0, 2**31))
    while True:
        candidate = rng.randint(18000, 24000)
        if candidate not in (8080, 9090, 9091):
            return candidate


def build_env_map(
    *,
    clone_dir: Path,
    apps_dir: Path,
    config_home: Path,
    phoenix_root: Path,
    local_bin: Path,
    pm2_bin: Path | None,
    python_bin: str,
    proxy_port: int,
    wrapper_bin: Path | None,
    wrapper_config: Path | None,
    extra: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """Generate the `.env` key/value map for the sandbox."""
    vendor_dir = apps_dir / "vendor"
    discovery_path = config_home / "discovered_servers.json"
    overrides_path = config_home / "tool_overrides.json"
    tool_schema_status_path = config_home / "tool_schema_status.json"
    proxy_bin = apps_dir / "mcp-proxy" / "build" / "mcp-proxy"
    proxy_config = config_home / "proxy.json"
    phoenix = phoenix_root
    mem_dir = phoenix / ".ai" / "memory"
    playground_cache = Path.home() / ".cache" / "ms-playwright"
    env: Dict[str, str] = {
        "STELAE_DIR": str(clone_dir),
        "APPS_DIR": str(apps_dir),
        "VENDOR_DIR": str(vendor_dir),
        "STELAE_CONFIG_HOME": str(config_home),
        "PROXY_BIN": str(proxy_bin),
        "PROXY_CONFIG": str(proxy_config),
        "PHOENIX_ROOT": str(phoenix),
        "MEMORY_DIR": str(mem_dir),
        "SEARCH_ROOT": str(phoenix),
        "SEARCH_PYTHON_BIN": str(python_bin),
        "LOCAL_BIN": str(local_bin),
        "FILESYSTEM_BIN": str(local_bin / "rust-mcp-filesystem"),
        "RG_BIN": str(local_bin / "mcp-grep-server"),
        "STRATA_BIN": str(local_bin / "strata"),
        "DOCY_BIN": str(local_bin / "mcp-server-docy"),
        "MEMORY_BIN": str(local_bin / "basic-memory"),
        "SHELL_BIN": str(local_bin / "terminal_controller"),
        "PLAYWRIGHT_BROWSERS_PATH": str(playground_cache),
        "CODEX_WRAPPER_BIN": str(wrapper_bin) if wrapper_bin else "",
        "CODEX_WRAPPER_CONFIG": str(wrapper_config) if wrapper_config else "",
        "PM2": str(pm2_bin) if pm2_bin else "pm2",
        "ONE_MCP_BIN": str(local_bin / "uv"),
        "ONE_MCP_DIR": str(vendor_dir / "1mcpserver"),
        "STELAE_DISCOVERY_PATH": str(discovery_path),
        "OPENAI_API_KEY": "test-clone-smoke-key",
        "GITHUB_TOKEN": "",
        "PYTHON": python_bin,
        "SHIM_PYTHON": python_bin,
        "CLOUDFLARED": "cloudflared",
        "CF_TUNNEL_NAME": "stelae-smoke",
        "TOOL_OVERRIDES_PATH": str(overrides_path),
        "TOOL_SCHEMA_STATUS_PATH": str(tool_schema_status_path),
        "PUBLIC_PORT": str(proxy_port),
        "PUBLIC_BASE_URL": f"http://127.0.0.1:{proxy_port}",
        "PUBLIC_SSE_URL": f"http://127.0.0.1:{proxy_port}/mcp",
        "BASIC_MEMORY_PROJECT": "stelae-smoke",
    }
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def format_env_lines(values: Mapping[str, str], *, keys: Iterable[str] = SMOKE_ENV_KEYS) -> str:
    """Render the env map to `key=value` lines preserving the template order."""
    lines: list[str] = []
    seen = set()
    for key in keys:
        seen.add(key)
        value = values.get(key, "")
        lines.append(f"{key}={value}")
    for key, value in values.items():
        if key in seen:
            continue
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ManualContext:
    sandbox_root: Path
    clone_dir: Path
    env_file: Path
    config_home: Path
    proxy_url: str
    manual_result: Path
    wrapper_bin: Path | None = None
    wrapper_config: Path | None = None
    mission_file: Path | None = None


def render_manual_playbook(ctx: ManualContext) -> str:
    """Return the markdown playbook testers should follow for manual steps."""
    if ctx.wrapper_bin:
        mission_arg = ctx.mission_file or Path("dev/tasks/missions/e2e_clone_smoke.json")
        config_arg = f"--config {ctx.wrapper_config}" if ctx.wrapper_config else ""
        cmd = f"{ctx.wrapper_bin} run-mission {mission_arg} --workspace {ctx.clone_dir}"
        if config_arg:
            cmd = f"{cmd} {config_arg}"
        wrapper_hint = f"Run `{cmd}` after exporting `STELAE_CONFIG_HOME={ctx.config_home}`."
    else:
        wrapper_hint = "Launch your Codex MCP wrapper (set `STELAE_CONFIG_HOME` to the sandbox) before continuing."
    mission_hint = (
        f"Mission file: `{ctx.mission_file}`" if ctx.mission_file else "Mission file: dev/tasks/missions/e2e_clone_smoke.json"
    )
    return textwrap.dedent(
        f"""
        # Codex MCP manual smoke instructions

        1. Open a new terminal and `cd {ctx.clone_dir}`.
        2. Export `STELAE_CONFIG_HOME={ctx.config_home}` and `PM2_HOME={ctx.sandbox_root / '.pm2'}` so Codex reuses the sandbox.
        3. Start the Codex MCP wrapper using the sandbox `.env` (`source {ctx.env_file}` or pass `--env-file`).
        4. Connect to the sandbox proxy: `{ctx.proxy_url}`. Verify `manage_stelae` appears via `tools/list`.
        5. Call `manage_stelae` with `{{"operation":"install_server","params":{{"name":"docy_manager","target_name":"docy_manager_smoke"}}}}`.
        6. Once the install completes, call `manage_stelae` again with `{{"operation":"remove_server","params":{{"name":"docy_manager_smoke"}}}}`.
        7. Update `{ctx.manual_result}` with `status="passed"` (or `failed`) plus any notes and include the call IDs reported by Codex.

        {wrapper_hint}

        {mission_hint}
        """
    ).strip() + "\n"
