from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict

import pytest
from fastmcp import Client
from fastmcp.mcp_config import CanonicalMCPConfig

ROOT = Path(__file__).resolve().parents[1]


def _mission() -> Dict[str, Any]:
    return {
        "mission_id": "stelae-codex-smoke",
        "workspace_root": str(ROOT),
        "tasks": [
            {
                "prompt": "List the directories at the repo root",
                "cwd": ".",
                "sandbox": "read-only",
                "approval_policy": "never",
                "timeout_sec": 600,
            },
            {
                "prompt": "Open README.md and summarize the optional bundles section",
                "cwd": ".",
                "sandbox": "read-only",
                "approval_policy": "never",
                "timeout_sec": 600,
            },
        ],
    }


def _codex_wrapper_bin() -> Path | None:
    value = os.environ.get("CODEX_WRAPPER_BIN")
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.exists() else None


def _codex_wrapper_config() -> Path | None:
    value = os.environ.get("CODEX_WRAPPER_CONFIG")
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.exists() else None


def test_codex_wrapper_batch_smoke() -> None:
    binary = _codex_wrapper_bin()
    config_path = _codex_wrapper_config()
    if not binary or not config_path:
        pytest.skip("codex wrapper binary/config not configured")

    config = CanonicalMCPConfig(
        mcpServers={
            "codex-wrapper-smoke": {
                "command": str(binary),
                "args": ["serve", "--config", str(config_path)],
                "transport": "stdio",
                "timeout": 900,
            }
        }
    )

    async def _run() -> Dict[str, Any]:
        client = Client(config, name="codex-wrapper-smoke-test")
        await client.__aenter__()
        try:
            result = await client.call_tool("batch", {"mission": _mission()}, timeout=900)
            return result
        finally:
            await client.__aexit__(None, None, None)

    response = asyncio.run(_run())
    assert response["errors"] == []
    assert len(response["results"]) == 2
    for item in response["results"]:
        assert item["status"] == "ok"
        assert item["stdout"].strip()
