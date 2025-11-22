#!/usr/bin/env python3
"""Targeted checks for the smoke harness guardrails (plan-only, mount guard)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_harness(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "scripts/run_e2e_clone_smoke_test.py", *args]
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=env or os.environ.copy(),
    )


def test_plan_only_prints_plan_and_exits(tmp_path: Path) -> None:
    workspace = tmp_path / "ws-plan"
    result = run_harness(
        [
            "--plan-only",
            "--workspace",
            str(workspace),
            "--restart-retries",
            "0",
            "--heartbeat-timeout",
            "1",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert "Plan-only mode" in result.stdout
    assert f"[plan] workspace: {workspace}" in result.stdout
    # Plan-only should not create the marker file.
    assert not (workspace / ".stelae_smoke_workspace").exists()


def test_plan_only_refuses_windows_mount(monkeypatch: "pytest.MonkeyPatch") -> None:
    env = os.environ.copy()
    env["TMPDIR"] = "/mnt/c/tmp"
    result = run_harness(["--plan-only"], env=env)
    assert result.returncode != 0
    assert "/mnt" in (result.stdout + result.stderr)
