#!/usr/bin/env python3
"""Automated + manual harness for the clone smoke test."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict

from stelae_lib.smoke_harness import (
    ManualContext,
    build_env_map,
    choose_proxy_port,
    format_env_lines,
    render_manual_playbook,
)


class CloneSmokeHarness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.source_repo = Path(args.source).resolve()
        if not (self.source_repo / "README.md").exists():
            raise SystemExit(f"{self.source_repo} does not look like the stelae repo")
        if args.workspace:
            workspace = Path(args.workspace).expanduser().resolve()
            if workspace.exists():
                if any(workspace.iterdir()):
                    raise SystemExit(f"workspace {workspace} already exists and is not empty")
            else:
                workspace.mkdir(parents=True, exist_ok=True)
            self.workspace = workspace
            self._ephemeral = False
        else:
            self.workspace = Path(tempfile.mkdtemp(prefix="stelae-clone-smoke-"))
            self._ephemeral = True
        self.clone_dir = self.workspace / "stelae"
        self.apps_dir = self.workspace / "apps"
        self.config_home = self.workspace / "config-home"
        self.pm2_home = self.workspace / ".pm2"
        self.manual_result_path = self.workspace / "manual_result.json"
        self.manual_playbook_path = self.workspace / "manual_playbook.md"
        self.manual_mission = Path("dev/tasks/missions/e2e_clone_smoke.json")
        self.log_path = self.workspace / "harness.log"
        self.proxy_port = args.port or choose_proxy_port()
        self.wrapper_release = Path(args.wrapper_release).expanduser().resolve() if args.wrapper_release else None
        self.wrapper_dest: Path | None = None
        self.wrapper_bin: Path | None = None
        self.wrapper_config: Path | None = None
        pm2_path = shutil.which("pm2")
        self.pm2_bin = Path(pm2_path) if pm2_path else None
        self._env = os.environ.copy()
        self._env.update(
            {
                "STELAE_DIR": str(self.clone_dir),
                "APPS_DIR": str(self.apps_dir),
                "STELAE_CONFIG_HOME": str(self.config_home),
                "PM2_HOME": str(self.pm2_home),
                "PROXY_PORT": str(self.proxy_port),
                "STELAE_PROXY_BASE": f"http://127.0.0.1:{self.proxy_port}",
                "PUBLIC_BASE_URL": f"http://127.0.0.1:{self.proxy_port}",
                "PUBLIC_SSE_URL": f"http://127.0.0.1:{self.proxy_port}/mcp",
                "GOMODCACHE": str(self.workspace / ".gomodcache"),
                "GOCACHE": str(self.workspace / ".gocache"),
            }
        )
        if self.pm2_bin:
            pm2_dir = str(self.pm2_bin.parent)
            self._env["PATH"] = os.pathsep.join([pm2_dir, self._env.get("PATH", "")])
        self._log(f"Workspace: {self.workspace}")

    # --------------------------------------------------------------------- utils
    def _log(self, message: str) -> None:
        print(message)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        display = " ".join(cmd)
        if cwd:
            display = f"(cd {cwd} && {display})"
        self._log(f"$ {display}")
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=self._env,
            text=True,
            capture_output=capture_output,
            check=check,
        )
        if capture_output:
            if result.stdout:
                self._log(result.stdout.strip())
            if result.stderr:
                self._log(result.stderr.strip())
        return result

    # -------------------------------------------------------------------- stages
    def run(self) -> None:
        success = False
        try:
            self._clone_repo()
            self._clone_proxy_repo()
            self._bootstrap_config_home()
            self._copy_wrapper_release()
            self._prepare_env_file()
            self._run_render_restart()
            self._run_manage_cycle()
            self._write_manual_assets()
            if not self.args.auto_only:
                self._await_manual_confirmation()
            success = True
            self._log("Clone smoke harness completed")
        finally:
            self._teardown_processes()
            if success and not self.args.keep_workspace:
                self._cleanup_workspace()
            elif not success:
                self._log(f"Workspace left at {self.workspace} for triage (set --keep-workspace to always retain).")

    def _clone_repo(self) -> None:
        self._log("Cloning stelae repo...")
        self._run(
            ["git", "clone", "--filter=blob:none", str(self.source_repo), str(self.clone_dir)],
        )

    def _clone_proxy_repo(self) -> None:
        source = self.args.proxy_source or "https://github.com/TBXark/mcp-proxy.git"
        dest = self.apps_dir / "mcp-proxy"
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._log(f"Cloning mcp-proxy ({source})...")
        self._run(["git", "clone", "--depth", "1", source, str(dest)])

    def _prepare_env_file(self) -> None:
        self.config_home.mkdir(parents=True, exist_ok=True)
        env_map = build_env_map(
            clone_dir=self.clone_dir,
            apps_dir=self.apps_dir,
            config_home=self.config_home,
            phoenix_root=self.workspace / "phoenix",
            local_bin=Path.home() / ".local" / "bin",
            pm2_bin=self.pm2_bin,
            python_bin=sys.executable,
            proxy_port=self.proxy_port,
            wrapper_bin=self.wrapper_bin,
            wrapper_config=self.wrapper_config,
            extra={
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "test-clone-smoke-key"),
                "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
                "PROXY_PORT": str(self.proxy_port),
            },
        )
        env_contents = format_env_lines(env_map)
        env_file = self.clone_dir / ".env"
        self._log(f"Writing sandbox .env → {env_file}")
        env_file.write_text(env_contents, encoding="utf-8")

    def _copy_wrapper_release(self) -> None:
        if not self.wrapper_release:
            self._log("No wrapper release provided; manual steps must use an existing install.")
            return
        if not self.wrapper_release.is_dir():
            raise SystemExit(f"{self.wrapper_release} is not a release directory")
        target_root = self.config_home / "codex-mcp-wrapper" / "releases"
        target_root.mkdir(parents=True, exist_ok=True)
        dest = target_root / self.wrapper_release.name
        self._log(f"Copying Codex wrapper release → {dest}")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.wrapper_release, dest)
        latest = target_root / "latest"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(dest.name)
        bin_path = dest / "venv" / "bin" / "codex-mcp-wrapper"
        config_path = dest / "wrapper.toml"
        if not bin_path.exists():
            raise SystemExit(f"wrapper binary not found at {bin_path}")
        if not config_path.exists():
            raise SystemExit(f"wrapper config not found at {config_path}")
        self.wrapper_dest = dest
        self.wrapper_bin = bin_path
        self.wrapper_config = config_path
        self._env["CODEX_WRAPPER_BIN"] = str(bin_path)
        self._env["CODEX_WRAPPER_CONFIG"] = str(config_path)

    def _bootstrap_config_home(self) -> None:
        (self.config_home / "logs").mkdir(parents=True, exist_ok=True)

    def _run_render_restart(self) -> None:
        self._log("Running make render-proxy…")
        self._run(["make", "render-proxy"], cwd=self.clone_dir)
        restart_script = self.clone_dir / "scripts" / "run_restart_stelae.sh"
        args = [str(restart_script), "--no-cloudflared"]
        self._log("Restarting stack inside sandbox…")
        self._run(args, cwd=self.clone_dir)

    def _run_manage_cycle(self) -> None:
        descriptor = self._load_descriptor("docy_manager")
        payload = {
            "descriptor": descriptor,
            "target_name": "docy_manager_smoke",
            "force": True,
        }
        self._log("Installing docy_manager via manage_stelae CLI…")
        self._run(
            [
                sys.executable,
                "scripts/stelae_integrator_server.py",
                "--cli",
                "--operation",
                "install_server",
                "--params",
                json.dumps(payload),
            ],
            cwd=self.clone_dir,
        )
        self._assert_clean_repo("post-install")
        self._log("Removing docy_manager_smoke via manage_stelae CLI…")
        self._run(
            [
                sys.executable,
                "scripts/stelae_integrator_server.py",
                "--cli",
                "--operation",
                "remove_server",
                "--params",
                json.dumps({"name": "docy_manager_smoke"}),
            ],
            cwd=self.clone_dir,
        )
        self._assert_clean_repo("post-remove")

    def _load_descriptor(self, name: str) -> Dict[str, Any]:
        bundle_path = self.clone_dir / "config" / "bundles" / "starter_bundle.json"
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        servers = data.get("servers") or []
        for entry in servers:
            if isinstance(entry, dict) and entry.get("name") == name:
                return entry
        raise SystemExit(f"Descriptor '{name}' not found in {bundle_path}")

    def _assert_clean_repo(self, label: str) -> None:
        status = self._run(["git", "status", "--porcelain"], cwd=self.clone_dir, capture_output=True).stdout.strip()
        if status:
            raise RuntimeError(f"Repo dirty {label}:\n{status}")

    def _write_manual_assets(self) -> None:
        manual_template = {
            "status": "pending",
            "install_call_id": "",
            "remove_call_id": "",
            "notes": "",
        }
        self._log(f"Writing manual result template → {self.manual_result_path}")
        self.manual_result_path.write_text(json.dumps(manual_template, indent=2), encoding="utf-8")
        ctx = ManualContext(
            sandbox_root=self.workspace,
            clone_dir=self.clone_dir,
            env_file=self.clone_dir / ".env",
            config_home=self.config_home,
            proxy_url=f"http://127.0.0.1:{self.proxy_port}/mcp",
            manual_result=self.manual_result_path,
            wrapper_bin=self.wrapper_bin,
            wrapper_config=self.wrapper_config,
            mission_file=(self.clone_dir / self.manual_mission) if (self.clone_dir / self.manual_mission).exists() else None,
        )
        playbook = render_manual_playbook(ctx)
        self._log(f"Writing manual playbook → {self.manual_playbook_path}")
        self.manual_playbook_path.write_text(playbook, encoding="utf-8")
        self._log(f"Manual instructions ready: {self.manual_playbook_path}")

    def _await_manual_confirmation(self) -> None:
        prompt = textwrap.dedent(
            f"""
            Manual phase pending.
            - Follow {self.manual_playbook_path}
            - Update {self.manual_result_path} once Codex wrapper finishes
            Press ENTER when finished to let the harness validate the outcome.
            """
        ).strip()
        input(f"{prompt}\n> ")
        result = json.loads(self.manual_result_path.read_text(encoding="utf-8"))
        status = result.get("status", "").lower()
        if status != "passed":
            raise RuntimeError(
                f"manual_result.json status is '{status}'. Please update the file to 'passed' once manual steps succeed."
            )
        self._log("Manual confirmation recorded.")

    def _teardown_processes(self) -> None:
        if shutil.which("pm2"):
            try:
                self._run(["pm2", "kill"], capture_output=True, check=False)
            except Exception:  # pragma: no cover - teardown best-effort
                pass

    def _cleanup_workspace(self) -> None:
        self._log(f"Cleaning up workspace {self.workspace}…")
        shutil.rmtree(self.workspace, ignore_errors=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the disposable clone smoke test harness")
    parser.add_argument("--source", default=".", help="Path to the source stelae repo (default: current directory)")
    parser.add_argument("--workspace", help="Optional workspace directory to reuse/keep")
    parser.add_argument("--keep-workspace", action="store_true", help="Do not delete the workspace after success")
    parser.add_argument("--proxy-source", help="Alternate git source for mcp-proxy")
    parser.add_argument("--wrapper-release", help="Path to a codex-mcp-wrapper release directory to copy into the sandbox")
    parser.add_argument("--port", type=int, help="Override the sandbox proxy port")
    parser.add_argument("--auto-only", action="store_true", help="Skip the interactive/manual phase")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    harness = CloneSmokeHarness(args)
    harness.run()


if __name__ == "__main__":
    main()
