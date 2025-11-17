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
        self.force_flags: List[bool] = []

    def run(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        assert operation == "install_server"
        name = params["descriptor"]["name"]
        self.calls.append(name)
        self.force_flags.append(bool(params.get("force")))
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


def test_install_bundle_installs_servers_and_runs_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    config_dir = config_overlays.config_home()
    assert config_dir == tmp_path / "config_home"
    catalog_fragment = config_dir / "bundles" / "starter" / "catalog.json"
    catalog_fragment.parent.mkdir(parents=True, exist_ok=True)
    catalog_fragment.write_text(json.dumps(_sample_bundle()), encoding="utf-8")
    bundle = _sample_bundle()
    service = FakeService()
    runner = FakeRunner()
    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        command_runner=runner,
        catalog_fragment_path=catalog_fragment,
        bundle_files_changed=True,
    )
    assert summary["errors"] == []
    assert summary["installed"] == ["docs", "fs"]
    assert summary["overlays"] == []
    assert catalog_fragment.exists()
    assert service.calls == ["docs", "fs"]
    assert runner.commands == bundles.DEFAULT_RESTART_COMMANDS
    assert service.force_flags == [False, False]
    assert summary["installRefs"] == {"registered": [], "skipped": []}


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
        catalog_fragment_path=config_dir / "bundles" / "starter" / "catalog.json",
    )
    assert summary["dryRun"] is True
    assert summary["installed"] == []
    assert summary["skipped"] == ["docs"]
    assert not summary["commands"]
    assert summary["errors"] == []
    assert service.force_flags == [False]


def test_install_bundle_can_force_integrator(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    bundle = _sample_bundle()
    service = FakeService()
    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        force=True,
        restart=False,
    )
    assert summary["errors"] == []
    assert service.force_flags == [True, True]


def test_install_bundle_registers_install_refs_when_catalog_fragment_provided(tmp_path):
    install_state = bundles.InstallRefState(
        path=tmp_path / "bundle_installs.json",
        payload={"schemaVersion": 1, "installs": {}},
    )
    bundle = {
        "name": "starter",
        "servers": [
            {
                "name": "docs",
                "transport": "stdio",
                "command": "python",
                "installRef": "bundle:starter:docs",
            }
        ],
    }
    service = FakeService()
    runner = FakeRunner()
    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        install_state=install_state,
        catalog_fragment_path=tmp_path / "config" / "bundles" / "starter" / "catalog.json",
        bundle_name="starter",
        bundle_source=tmp_path / "bundle-src",
        command_runner=runner,
        restart=False,
    )
    assert summary["overlays"] == []
    assert summary["installRefs"]["registered"] == ["bundle:starter:docs"]
    assert install_state.payload["installs"]["bundle:starter:docs"]["bundle"] == "starter"
    assert summary["commands"] == []
    assert (tmp_path / "config" / "bundles" / "starter" / "catalog.json").exists()


def test_install_bundle_reuses_existing_install_refs(tmp_path):
    path = tmp_path / "bundle_installs.json"
    payload = {
        "schemaVersion": 1,
        "installs": {
            "bundle:starter:docs": {"bundle": "starter"},
        },
    }
    install_state = bundles.InstallRefState(path=path, payload=payload)
    bundle = {
        "name": "starter",
        "servers": [
            {
                "name": "docs",
                "transport": "stdio",
                "command": "python",
                "installRef": "bundle:starter:docs",
            }
        ],
    }
    service = FakeService()
    runner = FakeRunner()
    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        install_state=install_state,
        catalog_fragment_path=tmp_path / "config" / "bundles" / "starter" / "catalog.json",
        bundle_name="starter",
        command_runner=runner,
        restart=False,
    )
    assert summary["installRefs"]["registered"] == []
    assert summary["installRefs"]["skipped"] == ["bundle:starter:docs"]


def test_sync_bundle_folder_copies_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    source = tmp_path / "source"
    source.mkdir()
    (source / "catalog.json").write_text("{}", encoding="utf-8")
    result = bundles.sync_bundle_folder(source, "starter")
    assert result.changed is True
    expected = tmp_path / "config_home" / "bundles" / "starter"
    assert result.destination == expected
    assert (expected / "catalog.json").exists()
    config_overlays.config_home.cache_clear()


def test_install_bundle_writes_catalog_into_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(tmp_path / "config_home"))
    config_overlays.config_home.cache_clear()
    bundle = _sample_bundle()
    service = FakeService()
    runner = FakeRunner()

    summary = bundles.install_bundle(
        bundle,
        service_factory=lambda: service,
        command_runner=runner,
        restart=False,
    )

    fragment = tmp_path / "config_home" / "bundles" / "starter" / "catalog.json"
    assert fragment.exists()
    assert summary["errors"] == []
    assert ".local" not in fragment.name
    assert not any("local" in path.name for path in fragment.parent.glob("*.json") if path != fragment)
    config_overlays.config_home.cache_clear()
