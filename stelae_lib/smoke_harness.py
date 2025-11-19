#!/usr/bin/env python3
"""Utility helpers for the clone smoke-test harness."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

SMOKE_ENV_KEYS = (
    "STELAE_DIR",
    "APPS_DIR",
    "VENDOR_DIR",
    "STELAE_CONFIG_HOME",
    "STELAE_STATE_HOME",
    "STELAE_ENV_FILE",
    "PROXY_BIN",
    "PROXY_CONFIG",
    "PROXY_PORT",
    "PHOENIX_ROOT",
    "MEMORY_DIR",
    "SEARCH_ROOT",
    "SEARCH_PYTHON_BIN",
    "LOCAL_BIN",
    "FILESYSTEM_BIN",
    "RG_BIN",
    "STRATA_BIN",
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
    "STELAE_USE_INTENDED_CATALOG",
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
    state_dir = config_home / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    discovery_path = state_dir / "discovered_servers.json"
    overrides_path = state_dir / "tool_overrides.json"
    tool_schema_status_path = state_dir / "tool_schema_status.json"
    proxy_bin = apps_dir / "mcp-proxy" / "build" / "mcp-proxy"
    proxy_config = state_dir / "proxy.json"
    phoenix = phoenix_root
    mem_dir = config_home / "memory"
    playground_cache = Path.home() / ".cache" / "ms-playwright"
    env: Dict[str, str] = {
        "STELAE_DIR": str(clone_dir),
        "APPS_DIR": str(apps_dir),
        "VENDOR_DIR": str(vendor_dir),
        "STELAE_CONFIG_HOME": str(config_home),
        "STELAE_STATE_HOME": str(state_dir),
        "STELAE_ENV_FILE": str(config_home / ".env"),
        "PROXY_BIN": str(proxy_bin),
        "PROXY_CONFIG": str(proxy_config),
        "PROXY_PORT": str(proxy_port),
        "PHOENIX_ROOT": str(phoenix),
        "MEMORY_DIR": str(mem_dir),
        "SEARCH_ROOT": str(phoenix),
        "SEARCH_PYTHON_BIN": str(python_bin),
        "LOCAL_BIN": str(local_bin),
        "FILESYSTEM_BIN": str(local_bin / "rust-mcp-filesystem"),
        "RG_BIN": str(local_bin / "mcp-grep-server"),
        "STRATA_BIN": str(local_bin / "strata"),
        "MEMORY_BIN": str(local_bin / "basic-memory"),
        "NPX_BIN": "npx",
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
        "STELAE_USE_INTENDED_CATALOG": "1",
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
class MCPToolCall:
    """Structured view of a Codex JSONL MCP tool call snapshot."""

    id: str
    server: str
    tool: str
    status: str
    arguments: Any
    result: Any
    error: Any


def parse_codex_jsonl(raw: Iterable[str] | str) -> List[Dict[str, Any]]:
    """Parse a Codex `--json` stream (either text blob or line iterable)."""

    if isinstance(raw, str):
        lines = raw.splitlines()
    else:
        lines = list(raw)
    events: List[Dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            events.append(json.loads(text))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"Invalid Codex JSON line: {text}") from exc
    return events


def summarize_tool_calls(events: Iterable[Dict[str, Any]]) -> List[MCPToolCall]:
    """Collapse `item.{started,completed}` entries into final tool-call snapshots."""

    latest: Dict[str, MCPToolCall] = {}
    for payload in events:
        item = payload.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"mcp_tool_call", "tool_call"}:
            continue
        identifier = str(item.get("id") or item.get("call_id") or len(latest))
        snapshot = MCPToolCall(
            id=identifier,
            server=str(item.get("server") or ""),
            tool=str(item.get("tool") or item.get("name") or ""),
            status=str(item.get("status") or payload.get("type") or ""),
            arguments=item.get("arguments"),
            result=item.get("result"),
            error=item.get("error"),
        )
        latest[identifier] = snapshot
    return list(latest.values())
