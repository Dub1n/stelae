from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from stelae_lib import bundles, config_overlays


class FakeService:
    def __init__(self, failures: set[str] | None = None, unchanged: set[str] | None = None):
        self.calls: List[str] = []
        self.failures = failures or set()
        self.unchanged = unchanged or set()
        self.default_commands: list[list[str]] = []

    def run(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert operation == "install_server"
        name = params["descriptor"]["name"]
        self.calls.append(name)
        if name in self.failures:
            return {"status": "error", "errors": ["boom"]}
        changed = name not in self.unchanged
        return {
            "status": "ok",
            "details": {
                "templateChanged": changed,
                "overridesChanged": False,
            },
        }


class FakeRunner:
    def __init__(self):
        self.commands: List[List[str]] = []

    class _Result:
        def __init__(self, command: List[str]):
            self.command = command

    def run(self, command: List[str], *, env: Dict[str, str] | None = None, dry_run: bool = False):
        cmd_list = list(command)
        self.commands.append(cmd_list)
        return self._Result(cmd_list)


def _sample_bundle() -> dict[str, Any]:
    return {
        "name": "starter",
        "servers": [
            {"name": "docs", "transport": "stdio", "command": "python"},
            {"name": "fs", "transport": "stdio", "command": "python"},
        ],
        "toolOverrides": {
            "servers": {
                "docs": {"tools": {"fetch": {"enabled": True}}},
                "fs": {"tools": {"read_file": {"enabled": True}}},
            }
        },
        "toolAggregations": {
            "schemaVersion": 1,
            "defaults": {},
            "hiddenTools": [],
            "aggregations": [{"name": "agg", "inputSchema": {"type": "object"}, "operations": []}],
        },
    }


def test_install_bundle_updates_overlays_and_runs_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    config_dir = config_overlays.config_home()
    assert config_dir == tmp_path / "config_home"
    bundle = _sample_bundle()
    service = FakeService()
    runner = FakeRunner()
    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        command_runner=runner,
    )
    assert summary["errors"] == []
    assert summary["installed"] == ["docs", "fs"]
    assert len(summary["overlays"]) == 2
    overrides_overlay = config_dir / "tool_overrides.local.json"
    aggregations_overlay = config_dir / "tool_aggregations.local.json"
    assert overrides_overlay.exists()
    assert aggregations_overlay.exists()
    data = json.loads(overrides_overlay.read_text())
    assert "docs" in data.get("servers", {})
    assert runner.commands == bundles.DEFAULT_RESTART_COMMANDS


def test_install_bundle_respects_filters_and_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    config_dir = config_overlays.config_home()
    assert config_dir == tmp_path / "config_home"
    bundle = _sample_bundle()
    service = FakeService(unchanged={"docs"}, failures={"fs"})
    summary = bundles.install_bundle(
        bundle,
        server_filter=["docs"],
        dry_run=True,
        service_factory=lambda: service,
    )
    assert summary["dryRun"] is True
    assert summary["installed"] == []
    assert summary["skipped"] == ["docs"]
    assert not summary["commands"]
    assert summary["errors"] == []
    overrides_overlay = config_dir / "tool_overrides.local.json"
    assert not overrides_overlay.exists()
