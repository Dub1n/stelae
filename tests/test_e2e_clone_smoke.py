from __future__ import annotations

from pathlib import Path
import sys

# Ensure the repo root is importable when pytest runs inside the venv.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_e2e_clone_smoke_test as smoke_script

from stelae_lib.smoke_harness import (
    ManualContext,
    build_env_map,
    choose_proxy_port,
    format_env_lines,
    render_manual_playbook,
)


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


def test_render_manual_playbook_mentions_manual_paths(tmp_path: Path) -> None:
    ctx = ManualContext(
        sandbox_root=tmp_path,
        clone_dir=tmp_path / "clone",
        env_file=tmp_path / ".env",
        config_home=tmp_path / "config",
        proxy_url="http://127.0.0.1:9999/mcp",
        manual_result=tmp_path / "manual_result.json",
        wrapper_bin=tmp_path / "bin" / "codex-mcp-wrapper",
        wrapper_config=tmp_path / "cfg" / "wrapper.toml",
        mission_file=tmp_path / "clone" / "dev" / "tasks" / "missions" / "e2e_clone_smoke.json",
    )
    text = render_manual_playbook(ctx)
    assert str(ctx.manual_result) in text
    assert "codex-mcp-wrapper" in text
    assert "manage_stelae" in text


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


def test_parse_args_accepts_catalog_mode() -> None:
    args = smoke_script.parse_args(["--catalog-mode", "both"])
    assert args.catalog_mode == "both"
