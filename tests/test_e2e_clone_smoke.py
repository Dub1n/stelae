from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Ensure the repo root is importable when pytest runs inside the venv.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_e2e_clone_smoke_test as smoke_script

from scripts.run_e2e_clone_smoke_test import CodexStage, ToolExpectation, assert_stage_expectations
from stelae_lib.smoke_harness import MCPToolCall, build_env_map, choose_proxy_port, format_env_lines


def test_choose_proxy_port_excludes_default_range() -> None:
    port = choose_proxy_port(seed=123)
    assert 18000 <= port <= 24000
    assert port not in {8080, 9090, 9091}


def test_build_env_map_sets_wrapper_values(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    apps = tmp_path / "apps"
    config = tmp_path / "config"
    clone.mkdir()
    apps.mkdir()
    config.mkdir()
    wrapper = tmp_path / "release" / "venv" / "bin" / "codex-mcp-wrapper"
    wrapper.parent.mkdir(parents=True)
    wrapper.touch()
    cfg = tmp_path / "release" / "wrapper.toml"
    cfg.touch()
    values = build_env_map(
        clone_dir=clone,
        apps_dir=apps,
        config_home=config,
        phoenix_root=tmp_path / "phoenix",
        local_bin=tmp_path / "bin",
        pm2_bin=tmp_path / "pm2",
        python_bin="/usr/bin/python3",
        proxy_port=19333,
        wrapper_bin=wrapper,
        wrapper_config=cfg,
    )
    assert values["STELAE_DIR"] == str(clone)
    assert values["CODEX_WRAPPER_BIN"] == str(wrapper)
    assert values["PUBLIC_BASE_URL"].endswith(":19333")
    assert values["STELAE_USE_INTENDED_CATALOG"] == "1"


def test_format_env_lines_respects_key_order() -> None:
    text = format_env_lines({"B": "2", "A": "1"}, keys=("A", "B"))
    assert text.splitlines()[0] == "A=1"
    assert text.splitlines()[1] == "B=2"



def test_mark_and_cleanup_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "stelae-smoke-workspace-demo"
    workspace.mkdir()
    smoke_script.mark_workspace(workspace)
    assert smoke_script.is_smoke_workspace(workspace)
    assert smoke_script.cleanup_workspace_path(workspace)
    assert not workspace.exists()


def test_discover_smoke_workspaces_respects_prefix(tmp_path: Path) -> None:
    managed = tmp_path / f"{smoke_script.WORKSPACE_PREFIX}demo"
    managed.mkdir()
    smoke_script.mark_workspace(managed)
    unmanaged = tmp_path / "random-dir"
    unmanaged.mkdir()
    (unmanaged / smoke_script.WORKSPACE_MARKER).write_text("orphan", encoding="utf-8")
    found = smoke_script.discover_smoke_workspaces(tmp_path)
    assert managed in found
    assert unmanaged not in found


def test_upsert_env_value_appends_and_updates(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    smoke_script.upsert_env_value(env_file, "FOO", "1")
    assert env_file.read_text(encoding="utf-8") == "FOO=1\n"
    smoke_script.upsert_env_value(env_file, "BAR", "example")
    assert "BAR=example" in env_file.read_text(encoding="utf-8")
    smoke_script.upsert_env_value(env_file, "FOO", "2")
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines.count("FOO=2") == 1


def test_assert_stage_expectations_passes_with_required_calls() -> None:
    stage = CodexStage(
        name="bundle-tools",
        prompt="",
        expectations=[
            ToolExpectation(
                tool="workspace_fs_read",
                description="read file",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "read_file",
            )
        ],
    )
    calls = [
        MCPToolCall(
            id="1",
            server="stelae",
            tool="workspace_fs_read",
            status="completed",
            arguments={"operation": "read_file"},
            result=None,
            error=None,
        )
    ]
    assert_stage_expectations(stage, calls)


def test_assert_stage_expectations_raises_when_tool_missing() -> None:
    stage = CodexStage(
        name="install",
        prompt="",
        expectations=[
            ToolExpectation(
                tool="manage_stelae",
                description="install",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "install_server",
            )
        ],
    )
    calls = [
        MCPToolCall(
            id="2",
            server="stelae",
            tool="manage_stelae",
            status="completed",
            arguments={"operation": "list_discovered_servers"},
            result=None,
            error=None,
        )
    ]
    with pytest.raises(RuntimeError):
        assert_stage_expectations(stage, calls)
