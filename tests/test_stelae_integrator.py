import json
from pathlib import Path

import pytest

import stelae_lib.integrator.core as core_module
from stelae_lib.config_overlays import overlay_path_for
from stelae_lib.integrator.core import StelaeIntegratorService
from stelae_lib.integrator.one_mcp import DiscoveryResult
from stelae_lib.integrator.runner import CommandResult


SAMPLE_DISCOVERY = {
    "name": "demo_server",
    "transport": "stdio",
    "command": "echo",
    "args": ["demo"],
    "tools": [
        {"name": "demo_tool", "description": "Demo helper"},
    ],
    "description": "Demo server",
    "source": "https://example.com/demo",
}


class FakeRunner:
    def __init__(self) -> None:
        self.invocations: list[list[list[str]]] = []

    def sequence(self, commands):
        self.invocations.append([list(cmd) for cmd in commands])
        return [
            CommandResult(command=list(cmd), status="ok", output="", returncode=0)
            for cmd in commands
        ]


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def integrator_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    template_path = config_dir / "proxy.template.json"
    overrides_path = config_dir / "tool_overrides.json"
    discovery_path = config_dir / "discovered_servers.json"
    _write_json(template_path, {"mcpServers": {}})
    _write_json(
        overrides_path,
        {
            "schemaVersion": 2,
            "master": {"tools": {"*": {"annotations": {}}}},
            "servers": {},
        },
    )
    _write_json(discovery_path, [SAMPLE_DISCOVERY])
    env_file = tmp_path / ".env"
    (tmp_path / "one_mcp").mkdir()
    _write_json(tmp_path / "one_mcp" / "discovered_servers.json", [SAMPLE_DISCOVERY | {"name": "refreshed"}])
    env_file.write_text(f"ONE_MCP_DIR={tmp_path / 'one_mcp'}\n", encoding="utf-8")
    config_home = tmp_path / ".stelae-config"
    monkeypatch.setenv("STELAE_CONFIG_HOME", str(config_home))
    return {
        "root": tmp_path,
        "template": template_path,
        "overrides": overrides_path,
        "discovery": discovery_path,
        "env": env_file,
        "config_home": config_home,
    }


def _service(workspace, runner=None, readiness_probe=None):
    return StelaeIntegratorService(
        root=workspace["root"],
        discovery_path=workspace["discovery"],
        template_path=workspace["template"],
        overrides_path=workspace["overrides"],
        env_files=[workspace["env"]],
        command_runner=runner or FakeRunner(),
        readiness_probe=readiness_probe or (lambda: True),
    )


def _service_with_defaults(workspace, runner=None, readiness_probe=None):
    return StelaeIntegratorService(
        root=workspace["root"],
        env_files=[workspace["env"]],
        command_runner=runner or FakeRunner(),
        readiness_probe=readiness_probe or (lambda: True),
    )


class DummyDiscovery:
    def __init__(self, results):
        self._results = results

    def search(self, query, limit=25, min_score=None):
        return self._results


def test_list_discovered_servers(integrator_workspace):
    service = _service(integrator_workspace)
    response = service.dispatch("list_discovered_servers", {})
    assert response["status"] == "ok"
    servers = response["details"]["servers"]
    assert servers[0]["name"] == "demo_server"


def test_install_server_dry_run_keeps_files(integrator_workspace):
    runner = FakeRunner()
    service = _service(integrator_workspace, runner)
    before_template = integrator_workspace["template"].read_text(encoding="utf-8")
    response = service.dispatch("install_server", {"name": "demo_server", "dry_run": True})
    assert response["status"] == "ok"
    assert response["details"]["dryRun"] is True
    assert integrator_workspace["template"].read_text(encoding="utf-8") == before_template
    assert runner.invocations == []


def test_install_server_applies_changes(integrator_workspace):
    runner = FakeRunner()
    service = _service(integrator_workspace, runner)
    response = service.dispatch("install_server", {"name": "demo_server"})
    assert response["status"] == "ok"
    data = json.loads(integrator_workspace["template"].read_text(encoding="utf-8"))
    assert "demo_server" in data["mcpServers"]
    overrides = json.loads(integrator_workspace["overrides"].read_text(encoding="utf-8"))
    assert "demo_tool" in overrides["servers"]["demo_server"]["tools"]
    assert runner.invocations, "commands should run"


def test_install_server_writes_overlay_when_not_overridden(integrator_workspace):
    runner = FakeRunner()
    service = _service_with_defaults(integrator_workspace, runner)
    response = service.dispatch("install_server", {"name": "demo_server"})
    assert response["status"] == "ok"
    base_template = json.loads(integrator_workspace["template"].read_text(encoding="utf-8"))
    assert "demo_server" not in base_template["mcpServers"]
    overlay_template_path = overlay_path_for(integrator_workspace["template"])
    overlay_data = json.loads(overlay_template_path.read_text(encoding="utf-8"))
    assert "demo_server" in overlay_data["mcpServers"]
    base_overrides = json.loads(integrator_workspace["overrides"].read_text(encoding="utf-8"))
    assert "demo_server" not in base_overrides["servers"]
    overlay_overrides_path = overlay_path_for(integrator_workspace["overrides"])
    overlay_overrides = json.loads(overlay_overrides_path.read_text(encoding="utf-8"))
    assert "demo_server" in overlay_overrides["servers"]


def test_install_server_waits_for_readiness(integrator_workspace):
    runner = FakeRunner()
    probes = {"count": 0}

    def _probe():
        probes["count"] += 1
        return probes["count"] >= 2

    service = _service(integrator_workspace, runner, readiness_probe=_probe)
    service.dispatch("install_server", {"name": "demo_server"})
    assert probes["count"] >= 2


def test_refresh_discovery_uses_one_mcp_dir(integrator_workspace):
    service = _service(integrator_workspace)
    response = service.dispatch("refresh_discovery", {})
    assert response["status"] == "ok"
    data = json.loads(integrator_workspace["discovery"].read_text(encoding="utf-8"))
    assert data[0]["name"] == "refreshed"


def test_remove_server(integrator_workspace):
    runner = FakeRunner()
    service = _service(integrator_workspace, runner)
    service.dispatch("install_server", {"name": "demo_server"})
    response = service.dispatch("remove_server", {"name": "demo_server"})
    assert response["status"] == "ok"
    data = json.loads(integrator_workspace["template"].read_text(encoding="utf-8"))
    assert "demo_server" not in data["mcpServers"]
    assert runner.invocations, "remove should trigger restart"


def test_discover_servers_appends_metadata(monkeypatch, integrator_workspace):
    results = [
        DiscoveryResult(name="DuckSearch", description="Search", url="https://github.com/foo", score=0.9),
        DiscoveryResult(name="DocsFetcher", description="Docs", url="https://github.com/bar", score=0.8),
    ]

    def _factory(*_args, **_kwargs):
        return DummyDiscovery(results)

    monkeypatch.setattr(core_module, "OneMCPDiscovery", _factory)
    service = _service(integrator_workspace)
    response = service.dispatch("discover_servers", {"query": "search"})
    assert response["status"] == "ok"
    servers = response["details"]["servers"]
    assert len(servers) == 2
    assert {server["status"] for server in servers} == {"added"}
    assert all("descriptor" in server for server in servers)
    data = json.loads(integrator_workspace["discovery"].read_text(encoding="utf-8"))
    names = {entry["name"] for entry in data}
    assert "ducksearch" in names
    assert "docsfetcher" in names
    duck = next(entry for entry in data if entry["name"] == "ducksearch")
    assert duck["transport"] == "metadata"


def test_discover_servers_hydrates_qdrant(monkeypatch, integrator_workspace):
    results = [
        DiscoveryResult(
            name="Qdrant",
            description="Vector search engine",
            url="https://github.com/qdrant/mcp-server-qdrant/",
            score=0.5,
        )
    ]

    def _factory(*_args, **_kwargs):
        return DummyDiscovery(results)

    monkeypatch.setattr(core_module, "OneMCPDiscovery", _factory)
    service = _service(integrator_workspace)
    response = service.dispatch("discover_servers", {"query": "vector"})
    assert response["status"] == "ok"
    entries = json.loads(integrator_workspace["discovery"].read_text(encoding="utf-8"))
    entry = next(item for item in entries if item["name"] == "qdrant")
    assert entry["transport"] == "stdio"
    assert entry["command"] == "uvx"
    assert entry["args"] == ["mcp-server-qdrant", "--transport", "stdio"]
    assert entry["env"]["COLLECTION_NAME"] == "{{QDRANT_COLLECTION_NAME}}"
    assert entry["options"]["hydrated"] is True
    env_text = integrator_workspace["env"].read_text(encoding="utf-8")
    assert "QDRANT_LOCAL_PATH=${STELAE_DIR}/var/qdrant" in env_text
    assert "QDRANT_COLLECTION_NAME=your-qdrant-collection" in env_text

def test_discover_servers_overwrite(monkeypatch, integrator_workspace):
    results = [
        DiscoveryResult(name="NewServer", description="Desc", url="https://github.com/new", score=0.95)
    ]

    def _factory(*_args, **_kwargs):
        return DummyDiscovery(results)

    monkeypatch.setattr(core_module, "OneMCPDiscovery", _factory)
    service = _service(integrator_workspace)
    response = service.dispatch("discover_servers", {"append": False})
    assert response["details"]["added"] == 1
    summary = response["details"]["servers"][0]
    assert summary["status"] == "added"
    data = json.loads(integrator_workspace["discovery"].read_text(encoding="utf-8"))
    assert [entry["name"] for entry in data] == ["newserver"]


def test_run_wraps_errors(integrator_workspace):
    service = _service(integrator_workspace)
    response = service.run("unknown_op", {})
    assert response["status"] == "error"
    assert response["details"]["operation"] == "unknown_op"
