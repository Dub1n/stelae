#!/usr/bin/env python3
"""Automated + manual harness for the clone smoke test."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKSPACE_PREFIX = "stelae-smoke-workspace-"
WORKSPACE_MARKER = ".stelae_smoke_workspace"
PYTEST_REQUIREMENT = "pytest>=8.2,<9.0"


def _marker_path(workspace: Path) -> Path:
    return workspace / WORKSPACE_MARKER


def is_smoke_workspace(workspace: Path) -> bool:
    try:
        return _marker_path(workspace).is_file()
    except OSError:
        return False


def mark_workspace(workspace: Path) -> None:
    marker = _marker_path(workspace)
    marker.write_text(
        json.dumps({"created_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def discover_smoke_workspaces(base: Path | None = None) -> List[Path]:
    base = base or Path(tempfile.gettempdir())
    candidates: List[Path] = []
    try:
        for path in base.glob(f"{WORKSPACE_PREFIX}*"):
            if is_smoke_workspace(path):
                candidates.append(path)
    except FileNotFoundError:
        return []
    return candidates


def cleanup_workspace_path(path: Path) -> bool:
    if not path.exists():
        return False
    if not is_smoke_workspace(path):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def cleanup_temp_smoke_workspaces(skip: Path | None = None) -> List[Path]:
    removed: List[Path] = []
    skip = skip.resolve() if skip else None
    for path in discover_smoke_workspaces():
        if skip and path.resolve() == skip:
            continue
        if cleanup_workspace_path(path):
            removed.append(path)
    return removed


def _cleanup_entrypoint(target: Path | None) -> List[Path]:
    if target:
        return [target] if cleanup_workspace_path(target) else []
    return cleanup_temp_smoke_workspaces()

from stelae_lib.smoke_harness import (
    MCPToolCall,
    ManualContext,
    build_env_map,
    choose_proxy_port,
    format_env_lines,
    parse_codex_jsonl,
    render_manual_playbook,
    summarize_tool_calls,
)


@dataclass(frozen=True)
class ToolExpectation:
    tool: str
    description: str
    predicate: Callable[[MCPToolCall], bool] | None = None
    min_calls: int = 1

    def matches(self, call: MCPToolCall) -> bool:
        if call.tool != self.tool:
            return False
        if self.predicate and not self.predicate(call):
            return False
        return True


@dataclass(frozen=True)
class CodexStage:
    name: str
    prompt: str
    expectations: List[ToolExpectation]


class CloneSmokeHarness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.manual_mode = bool(args.manual)
        self.manual_stage_names = set(args.manual_stage or [])
        self.force_workspace = bool(args.force_workspace)
        self.reuse_workspace = bool(args.reuse_workspace)
        self.source_repo = Path(args.source).resolve()
        if not (self.source_repo / "README.md").exists():
            raise SystemExit(f"{self.source_repo} does not look like the stelae repo")
        if args.workspace:
            workspace = Path(args.workspace).expanduser().resolve()
            self.workspace = workspace
            self._ephemeral = False
            self.log_path = self.workspace / "harness.log"
            self.workspace = self._prepare_workspace_dir(self.workspace)
        else:
            workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
            self.workspace = workspace
            self._ephemeral = True
            mark_workspace(self.workspace)
            self.log_path = self.workspace / "harness.log"
        self.log_path = self.workspace / "harness.log"
        self.clone_dir = self.workspace / "stelae"
        self.apps_dir = self.workspace / "apps"
        self.config_home = self.workspace / "config-home"
        self.pm2_home = self.workspace / ".pm2"
        self.client_repo = self.workspace / "client-repo"
        self.codex_home = self.workspace / "codex-home"
        self.transcript_dir = self.workspace / "codex-transcripts"
        self.manual_result_path = self.workspace / "manual_result.json"
        self.manual_playbook_path = self.workspace / "manual_playbook.md"
        self.manual_mission = Path("dev/tasks/missions/e2e_clone_smoke.json")
        self.log_path = self.workspace / "harness.log"
        self.python_site = self.workspace / "python-site"
        self._pytest_ready = False
        self.proxy_port = args.port or choose_proxy_port()
        self.wrapper_release = Path(args.wrapper_release).expanduser().resolve() if args.wrapper_release else None
        self.wrapper_dest: Path | None = None
        self.wrapper_bin: Path | None = None
        self.wrapper_config: Path | None = None
        self.codex_cli_arg = Path(args.codex_cli).expanduser() if args.codex_cli else None
        self.codex_cli_bin: Path | None = None
        self.codex_home_source = Path(args.codex_home).expanduser() if args.codex_home else Path.home() / ".codex"
        self.codex_transcripts: Dict[str, List[MCPToolCall]] = {}
        self.external_server = "qdrant"
        self.external_target = f"{self.external_server}_smoke"
        pm2_path = shutil.which("pm2")
        self.pm2_bin = Path(pm2_path) if pm2_path else None
        self._env = os.environ.copy()
        self._env.update(
            {
                "STELAE_DIR": str(self.clone_dir),
                "APPS_DIR": str(self.apps_dir),
                "STELAE_CONFIG_HOME": str(self.config_home),
                "PM2_HOME": str(self.pm2_home),
                "GOMODCACHE": str(self.workspace / ".gomodcache"),
                "GOCACHE": str(self.workspace / ".gocache"),
                "PM2_HOME": str(self.pm2_home),
                "CODEX_HOME": str(self.codex_home),
            }
        )
        self._apply_proxy_port(self.proxy_port)
        self._env.setdefault("PYTHONUNBUFFERED", "1")
        if self.pm2_bin:
            pm2_dir = str(self.pm2_bin.parent)
            self._env["PATH"] = os.pathsep.join([pm2_dir, self._env.get("PATH", "")])
        if os.environ.get("CODEX_API_KEY"):
            self._env["CODEX_API_KEY"] = os.environ["CODEX_API_KEY"]
        self._env.setdefault("GIT_AUTHOR_NAME", "Stelae Smoke Harness")
        self._env.setdefault("GIT_AUTHOR_EMAIL", "smoke-harness@example.com")
        self._env.setdefault("GIT_COMMITTER_NAME", self._env["GIT_AUTHOR_NAME"])
        self._env.setdefault("GIT_COMMITTER_EMAIL", self._env["GIT_AUTHOR_EMAIL"])
        self._shutdown_requested = False
        self._signal_exit = False
        self._original_signal_handlers: dict[int, signal.HandlersType | None] = {}
        self._install_signal_handlers()
        self._log(f"Workspace: {self.workspace}")

    # --------------------------------------------------------------------- utils
    def _prepare_workspace_dir(self, workspace: Path) -> Path:
        if workspace.exists():
            marker = is_smoke_workspace(workspace)
            if self.force_workspace:
                self._log(f"Force-removing existing workspace {workspace}")
                shutil.rmtree(workspace, ignore_errors=True)
            elif marker and self.reuse_workspace:
                self._log(f"Reusing existing smoke workspace {workspace}")
                return workspace
            elif marker:
                self._log(f"Removing previous smoke workspace {workspace}")
                shutil.rmtree(workspace, ignore_errors=True)
            elif self.reuse_workspace:
                raise SystemExit(
                    f"workspace {workspace} exists but is not marked as a smoke workspace; use --force-workspace to overwrite"
                )
            elif any(workspace.iterdir()):
                raise SystemExit(
                    f"workspace {workspace} already exists and is not empty. Pass --force-workspace to overwrite it"
                )
        workspace.mkdir(parents=True, exist_ok=True)
        mark_workspace(workspace)
        return workspace

    def _log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"
        print(line)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _apply_proxy_port(self, port: int) -> None:
        base = f"http://127.0.0.1:{port}"
        self.proxy_port = port
        self._env["PROXY_PORT"] = str(port)
        self._env["STELAE_PROXY_BASE"] = base
        self._env["PUBLIC_BASE_URL"] = base
        self._env["PUBLIC_SSE_URL"] = f"{base}/mcp"
        self._env["PUBLIC_PORT"] = str(port)

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        check: bool = True,
        log_output: bool = True,
        log_prefix: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        display = " ".join(cmd)
        if cwd:
            display = f"(cd {cwd} && {display})"
        self._log(f"$ {display}")
        start = time.monotonic()
        completed: subprocess.CompletedProcess[str] | None = None
        prefix = log_prefix or ""
        try:
            if capture_output:
                result = subprocess.run(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    env=self._env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if log_output:
                    if result.stdout:
                        self._log(f"{prefix}{result.stdout.rstrip()}" if prefix else result.stdout.rstrip())
                    if result.stderr:
                        self._log(f"{prefix}{result.stderr.rstrip()}" if prefix else result.stderr.rstrip())
                completed = subprocess.CompletedProcess(
                    cmd, result.returncode, result.stdout, result.stderr or ""
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    env=self._env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                output_lines: list[str] = []
                try:
                    if proc.stdout:
                        for line in proc.stdout:
                            stripped = line.rstrip("\n")
                            output_lines.append(stripped)
                            if log_output and stripped:
                                self._log(f"{prefix}{stripped}" if prefix else stripped)
                finally:
                    proc.wait()
                completed = subprocess.CompletedProcess(cmd, proc.returncode, "\n".join(output_lines), "")
            if completed.returncode != 0 and check:
                raise subprocess.CalledProcessError(
                    completed.returncode, cmd, completed.stdout, completed.stderr
                )
            return completed
        finally:
            duration = time.monotonic() - start
            if completed is None:
                status = "failed (no result)"
            elif completed.returncode == 0:
                status = f"ok (rc=0)"
            else:
                status = f"rc={completed.returncode}"
            self._log(f"[cmd] {display} → {status} in {duration:.1f}s")

    # -------------------------------------------------------------------- stages
    def run(self) -> None:
        success = False
        try:
            if self.args.skip_bootstrap:
                self._assert_bootstrap_ready()
            else:
                self._clone_repo()
                self._clone_proxy_repo()
                self._bootstrap_config_home()
                self._copy_wrapper_release()
                self._prepare_env_file()
                self._install_starter_bundle()
            if self.args.bootstrap_only:
                self._log(
                    f"Bootstrap-only flag set; workspace retained at {self.workspace} (rerun without --bootstrap-only to continue)."
                )
                self._ephemeral = False
                success = True
                return
            self._run_render_restart()
            self._assert_clean_repo("post-restart")
            self._run_pytest(["tests/test_repo_sanitized.py"], label="structural")
            stages = self._codex_stages()
            manual_assets_needed = self.manual_mode or bool(self.manual_stage_names)
            if manual_assets_needed:
                self._write_manual_assets()
                if self.manual_mode and not self.manual_stage_names:
                    self._log(
                        "Manual playbook written. Complete the instructions in manual_playbook.md and rerun the harness without --manual."
                    )
                    self._ephemeral = False
                    return
            auto_stage_pending = any(stage.name not in self.manual_stage_names for stage in stages)
            if auto_stage_pending:
                self._prepare_codex_environment()
            if self._run_codex_flow(stages):
                self._ephemeral = False
                return
            self._run_pytest([], label="full-suite")
            self._run_verify_clean()
            self._assert_clean_repo("final")
            success = True
            self._log("Clone smoke harness completed")
        finally:
            self._teardown_processes()
            if success and not self.args.keep_workspace:
                self._cleanup_workspace()
            elif not success:
                if not self._signal_exit:
                    self._log(
                        f"Workspace left at {self.workspace} for triage (set --keep-workspace to always retain)."
                    )
            self._restore_signal_handlers()

    def _clone_repo(self) -> None:
        self._log("Cloning stelae repo...")
        if self.clone_dir.exists():
            if self.reuse_workspace:
                self._log(f"Clone already exists at {self.clone_dir}; skipping git clone due to --reuse-workspace")
                return
            raise SystemExit(
                f"{self.clone_dir} already exists. Use --force-workspace to recreate the sandbox or --reuse-workspace to skip cloning."
            )
        self._run(
            ["git", "clone", "--filter=blob:none", str(self.source_repo), str(self.clone_dir)],
        )

    def _resolve_proxy_source(self) -> str:
        if self.args.proxy_source:
            return self.args.proxy_source
        env_source = os.environ.get("STELAE_PROXY_SOURCE")
        if env_source:
            return env_source
        local_clone = Path.home() / "apps" / "mcp-proxy"
        if local_clone.exists():
            return str(local_clone)
        return "https://github.com/Dub1n/mcp-proxy.git"

    def _clone_proxy_repo(self) -> None:
        source = self._resolve_proxy_source()
        dest = self.apps_dir / "mcp-proxy"
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._log(f"Cloning mcp-proxy ({source})...")
        if dest.exists():
            if self.reuse_workspace:
                self._log(f"Proxy clone already exists at {dest}; skipping due to --reuse-workspace")
                return
            raise SystemExit(
                f"{dest} already exists. Use --force-workspace to recreate the sandbox or --reuse-workspace to skip cloning."
            )
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

    def _install_starter_bundle(self) -> None:
        self._log("Installing starter bundle inside sandbox (should finish in <60s; long stalls mean env/IO issues)…")
        self._run(
            [
                sys.executable,
                "scripts/install_stelae_bundle.py",
                "--bundle",
                "config/bundles/starter_bundle.json",
                "--no-restart",
            ],
            cwd=self.clone_dir,
        )

    def _assert_bootstrap_ready(self) -> None:
        self._log("Skipping bootstrap steps (--skip-bootstrap). Validating existing workspace artifacts…")
        if not is_smoke_workspace(self.workspace):
            raise SystemExit(
                f"--skip-bootstrap requires an existing smoke workspace (marker missing at {self.workspace})."
            )
        required = [
            (self.clone_dir, "cloned repo"),
            (self.clone_dir / ".env", "sandbox .env"),
            (self.apps_dir / "mcp-proxy", "mcp-proxy checkout"),
        ]
        missing = [f"{label} ({path})" for path, label in required if not path.exists()]
        if missing:
            joined = "\n  - ".join(missing)
            raise SystemExit(f"--skip-bootstrap requested but required artifacts are missing:\n  - {joined}")
        env_file = self.clone_dir / ".env"
        env_data = env_file.read_text(encoding="utf-8").splitlines()
        proxy_port_line = next(
            (line for line in env_data if line.startswith("PROXY_PORT=") or line.startswith("PUBLIC_PORT=")),
            None,
        )
        if not proxy_port_line:
            raise SystemExit("--skip-bootstrap requested but PROXY_PORT/PUBLIC_PORT not found in sandbox .env")
        _, value = proxy_port_line.split("=", 1)
        try:
            port_value = int(value.strip())
        except ValueError as exc:
            raise SystemExit(f"--skip-bootstrap requested but PROXY_PORT '{value}' is not an integer") from exc
        self._apply_proxy_port(port_value)
        self._bootstrap_config_home()
        self._log(f"Workspace ready for --skip-bootstrap (PROXY_PORT={port_value})")

    def _bootstrap_config_home(self) -> None:
        (self.config_home / "logs").mkdir(parents=True, exist_ok=True)

    def _run_render_restart(self) -> None:
        self._log("Running make render-proxy…")
        self._run(["make", "render-proxy"], cwd=self.clone_dir)
        restart_script = self.clone_dir / "scripts" / "run_restart_stelae.sh"
        args = [
            str(restart_script),
            "--no-bridge",
            "--no-cloudflared",
        ]
        self._log("Restarting stack inside sandbox (expected <60s; investigate logs instead of extending timeouts)…")
        self._run(args, cwd=self.clone_dir)

    def _ensure_pytest(self) -> None:
        if self._pytest_ready and self.python_site.exists():
            return
        target = self.python_site
        marker = target / "pytest" / "__init__.py"
        if marker.exists():
            self._log(f"Pytest already present in sandbox site-packages ({target}); reusing install")
        else:
            target.mkdir(parents=True, exist_ok=True)
            self._log(f"Installing pytest into sandbox site-packages ({target})…")
            original_pip_flag = self._env.get("PIP_REQUIRE_VIRTUALENV")
            self._env["PIP_REQUIRE_VIRTUALENV"] = "0"
            try:
                self._run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "--target",
                        str(target),
                        PYTEST_REQUIREMENT,
                    ]
                )
            finally:
                if original_pip_flag is None:
                    self._env.pop("PIP_REQUIRE_VIRTUALENV", None)
                else:
                    self._env["PIP_REQUIRE_VIRTUALENV"] = original_pip_flag
        existing = self._env.get("PYTHONPATH", "")
        paths = [p for p in existing.split(os.pathsep) if p] if existing else []
        if str(target) not in paths:
            paths.insert(0, str(target))
            self._env["PYTHONPATH"] = os.pathsep.join(paths)
        self._pytest_ready = True

    def _run_pytest(self, args: List[str], *, label: str) -> None:
        self._log(f"Running pytest ({label})…")
        self._ensure_pytest()
        cmd = [sys.executable, "-m", "pytest"]
        if args:
            cmd.extend(args)
        self._run(cmd, cwd=self.clone_dir)

    def _run_verify_clean(self) -> None:
        self._log("Running make verify-clean…")
        self._run(["make", "verify-clean"], cwd=self.clone_dir)

    def _prepare_codex_environment(self) -> None:
        cli = self._resolve_codex_cli()
        self._log(f"Codex CLI resolved to {cli}")
        self._mirror_codex_home()
        self._seed_client_repo()

    def _resolve_codex_cli(self) -> Path:
        if self.codex_cli_bin and self.codex_cli_bin.exists():
            return self.codex_cli_bin
        if self.codex_cli_arg:
            candidate = self.codex_cli_arg
        else:
            detected = shutil.which("codex")
            if not detected:
                raise SystemExit("codex CLI not found on PATH. Pass --codex-cli or install Codex before running auto mode.")
            candidate = Path(detected)
        if not candidate.exists():
            raise SystemExit(f"codex CLI not found at {candidate}")
        self.codex_cli_bin = candidate
        return candidate

    def _mirror_codex_home(self) -> None:
        dest = self.codex_home
        if dest.exists():
            shutil.rmtree(dest)
        if self.codex_home_source.exists():
            shutil.copytree(self.codex_home_source, dest, dirs_exist_ok=True)
            self._log(f"Mirrored CODEX_HOME from {self.codex_home_source} → {dest}")
        else:
            dest.mkdir(parents=True, exist_ok=True)
            self._log(f"No CODEX_HOME at {self.codex_home_source}; created empty directory {dest}")
        self._patch_codex_config()

    def _patch_codex_config(self) -> None:
        config_path = self.codex_home / "config.toml"
        if not config_path.exists():
            self._log(f"Skipping Codex config patch; {config_path} does not exist")
            return
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._log(f"Warning: unable to read {config_path} ({exc}); Codex env overrides may be stale")
            return
        base = f"http://127.0.0.1:{self.proxy_port}"
        replacements = [
            (r"(STELAE_PROXY_BASE\s*=\s*)\"[^\"]*\"", f'\\1"{base}"'),
            (r"(STELAE_SEARCH_ROOT\s*=\s*)\"[^\"]*\"", f'\\1"{self.clone_dir}"'),
        ]
        updated = text
        changed = False
        for pattern, replacement in replacements:
            updated, count = re.subn(pattern, replacement, updated, count=1, flags=re.MULTILINE)
            if count:
                changed = True
        if not changed:
            self._log(
                "Codex config already points at the sandbox proxy/search root (no env patch required)"
            )
            return
        try:
            config_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            self._log(f"Warning: unable to update {config_path} ({exc}); Codex env overrides may be stale")
            return
        self._log(
            f"Updated Codex config at {config_path} with STELAE_PROXY_BASE={base} and search root {self.clone_dir}"
        )

    def _seed_client_repo(self) -> None:
        if self.client_repo.exists():
            shutil.rmtree(self.client_repo)
        self.client_repo.mkdir(parents=True, exist_ok=True)
        self._run(["git", "init", "-b", "main"], cwd=self.client_repo)
        readme = self.client_repo / "README.md"
        readme.write_text("Codex client workspace for the Stelae clone smoke test.\n", encoding="utf-8")
        self._run(["git", "add", "README.md"], cwd=self.client_repo)
        self._run(["git", "commit", "-m", "chore: seed client repo"], cwd=self.client_repo)

    def _run_codex_flow(self, stages: List[CodexStage]) -> bool:
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        for stage in stages:
            if stage.name in self.manual_stage_names:
                self._emit_manual_stage(stage)
                return True
            events = self._execute_codex_stage(stage)
            calls = summarize_tool_calls(events)
            self._assert_stage_expectations(stage, calls)
            self.codex_transcripts[stage.name] = calls
            self._log(
                f"Codex stage '{stage.name}' captured {len(calls)} tool calls: "
                + ", ".join(sorted({call.tool for call in calls}))
            )
            self._assert_clean_repo(f"after-{stage.name}")
        return False

    def _codex_stages(self) -> List[CodexStage]:
        bundle_expectations = [
            ToolExpectation(
                tool="workspace_fs_read",
                description="Read README.md from the cloned repo",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "read_file"
                and call.arguments.get("path") == "README.md",
            ),
            ToolExpectation(
                tool="grep",
                description="Search README.md for manage_stelae",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("pattern") == "manage_stelae",
            ),
            ToolExpectation(
                tool="manage_docy_sources",
                description="List Docy sources before fetching docs",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "list_sources",
            ),
            ToolExpectation(
                tool="doc_fetch_suite",
                description="List documentation sources via docy",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "list_documentation_sources_tool",
            ),
        ]
        install_expectations = [
            ToolExpectation(
                tool="manage_stelae",
                description=f"Install {self.external_server} as {self.external_target}",
                predicate=self._build_manage_predicate("install_server", self.external_target),
            )
        ]
        remove_expectations = [
            ToolExpectation(
                tool="manage_stelae",
                description=f"Remove {self.external_target}",
                predicate=self._build_manage_predicate("remove_server", self.external_target),
            )
        ]
        return [
            CodexStage(name="bundle-tools", prompt=self._bundle_prompt(), expectations=bundle_expectations),
            CodexStage(name="install", prompt=self._install_prompt(), expectations=install_expectations),
            CodexStage(name="remove", prompt=self._remove_prompt(), expectations=remove_expectations),
        ]

    def _bundle_prompt(self) -> str:
        read_payload = json.dumps({"operation": "read_file", "path": "README.md"})
        grep_payload = json.dumps(
            {
                "pattern": "manage_stelae",
                "paths": ["README.md"],
                "recursive": False,
                "regexp": False,
                "line_number": True,
            }
        )
        docy_manage_payload = json.dumps({"operation": "list_sources"})
        doc_payload = json.dumps({"operation": "list_documentation_sources_tool"})
        return textwrap.dedent(
            f"""
            Capture the MCP behavior for this sandbox—do not run shell commands or edit files manually.

            1. Call `tools/list` once to record whatever the proxy currently advertises (note the result in your summary). This is for diagnostics only.
            2. Regardless of whether the catalog includes them, call these MCP tools in order and report their outputs or failures:
               - `workspace_fs_read` with {read_payload}
               - `grep` with {grep_payload}
               - `manage_docy_sources` with {docy_manage_payload}
               - `doc_fetch_suite` with {doc_payload}
            3. If any call fails because the tool is missing, still include the failed attempt in your notes; do not substitute shell access.

            Summarize what you observed from each MCP call and stop.
            """
        ).strip()

    def _install_prompt(self) -> str:
        install_payload = json.dumps(
            {
                "operation": "install_server",
                "params": {
                    "name": self.external_server,
                    "target_name": self.external_target,
                    "force": True,
                },
            }
        )
        verify_payload = json.dumps({"operation": "list_discovered_servers"})
        return textwrap.dedent(
            f"""
            Install the `{self.external_server}` descriptor under the alias `{self.external_target}` using only the `manage_stelae` MCP tool. The proxy already points at {self.clone_dir}; do not run shell commands.
            - Call `manage_stelae` with {install_payload} and wait for the restart to finish.
            - Once complete, call `manage_stelae` again with {verify_payload} (or another read-only verification step) to confirm the server is listed.
            - Rely on MCP responses and report the results.
            """
        ).strip()

    def _remove_prompt(self) -> str:
        remove_payload = json.dumps(
            {
                "operation": "remove_server",
                "params": {
                    "name": self.external_target,
                    "force": True,
                },
            }
        )
        return textwrap.dedent(
            f"""
            Clean up the `{self.external_target}` installation so the sandbox returns to a clean state. Operate entirely through the MCP catalog (no shell access).
            - Call `manage_stelae` with {remove_payload} and wait for the tool to confirm completion.
            - Verify the alias no longer appears in discovery (read-only checks only).
            - Summarize the outcome; do not issue shell commands.
            """
        ).strip()

    def _emit_manual_stage(self, stage: CodexStage) -> None:
        instructions = textwrap.dedent(
            f"""
            # Manual Codex stage: {stage.name}

            Workspace: `{self.clone_dir}`
            STELAE_CONFIG_HOME: `{self.config_home}`
            PM2_HOME: `{self.pm2_home}`
            Client repo (Codex working tree): `{self.client_repo}`

            Run the Codex CLI manually for this stage using the sandbox `.env` (`source {self.clone_dir / '.env'}`) and the prompt below. The harness expects you to run the same instructions it would have passed to `codex exec`:

            ```
            {stage.prompt}
            ```

            After completing the stage, rerun the harness without `--manual-stage {stage.name}` to continue. Use `python scripts/run_e2e_clone_smoke_test.py --workspace {self.workspace} --reuse-workspace ...` so the sandbox is reused.
            """
        ).strip()
        path = self.workspace / f"manual_stage_{stage.name}.md"
        path.write_text(instructions + "\n", encoding="utf-8")
        self._log(
            f"Manual stage '{stage.name}' instructions written → {path}. Complete the steps and rerun without --manual-stage {stage.name}."
        )

    def _execute_codex_stage(self, stage: CodexStage) -> List[Dict[str, Any]]:
        if not self.codex_cli_bin:
            raise RuntimeError("Codex CLI not prepared")
        transcript_path = self.transcript_dir / f"{stage.name}.jsonl"
        cmd = [
            str(self.codex_cli_bin),
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--full-auto",
            "--cd",
            str(self.client_repo),
            stage.prompt,
        ]
        result = self._run(
            cmd,
            cwd=self.client_repo,
            capture_output=False,
            log_output=True,
            log_prefix=f"[codex:{stage.name}] ",
        )
        transcript_path.write_text(result.stdout, encoding="utf-8")
        return parse_codex_jsonl(result.stdout.splitlines())

    def _assert_stage_expectations(self, stage: CodexStage, calls: Iterable[MCPToolCall]) -> None:
        for expectation in stage.expectations:
            matches = [call for call in calls if expectation.matches(call)]
            if len(matches) < expectation.min_calls:
                raise RuntimeError(
                    f"Codex stage '{stage.name}' missing tool '{expectation.tool}' – {expectation.description}."
                )

    def _build_manage_predicate(self, operation: str, alias: str) -> Callable[[MCPToolCall], bool]:
        def predicate(call: MCPToolCall) -> bool:
            if not isinstance(call.arguments, dict):
                return False
            op = str(call.arguments.get("operation") or "").lower()
            if op != operation:
                return False
            params = call.arguments.get("params")
            if not isinstance(params, dict):
                return False
            target = str(params.get("target_name") or params.get("name") or "").strip()
            if operation == "install_server":
                return target == alias or str(params.get("name") or "") == self.external_server
            return target == alias

        return predicate

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

    def _teardown_processes(self) -> None:
        if shutil.which("pm2"):
            try:
                self._run(["pm2", "kill"], capture_output=True, check=False)
            except Exception:  # pragma: no cover - teardown best-effort
                pass

    def _cleanup_workspace(self) -> None:
        if cleanup_workspace_path(self.workspace):
            self._log(f"Cleaning up workspace {self.workspace}…")

    # ---------------------------------------------------------------- signal mgmt
    def _install_signal_handlers(self) -> None:
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                previous = signal.getsignal(sig)
                self._original_signal_handlers[sig] = previous
                signal.signal(sig, self._handle_signal)
            except (ValueError, OSError, RuntimeError):
                continue

    def _restore_signal_handlers(self) -> None:
        for sig, handler in self._original_signal_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, RuntimeError):
                continue

    def _handle_signal(self, signum: int, frame: Any) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self._signal_exit = True
        try:
            sig_name = signal.Signals(signum).name
        except Exception:
            sig_name = str(signum)
        self._log(f"Received {sig_name}; tearing down sandbox processes…")
        try:
            self._teardown_processes()
        except Exception as exc:  # pragma: no cover - best effort logging
            self._log(f"Process teardown after {sig_name} failed: {exc}")
        if not self.args.keep_workspace:
            try:
                self._cleanup_workspace()
            except Exception as exc:  # pragma: no cover - best effort logging
                self._log(f"Workspace cleanup after {sig_name} failed: {exc}")
        exit_code = 130 if signum == getattr(signal, "SIGINT", signum) else 143
        raise SystemExit(exit_code)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the disposable clone smoke test harness")
    parser.add_argument("--source", default=".", help="Path to the source stelae repo (default: current directory)")
    parser.add_argument("--workspace", help="Optional workspace directory to reuse/keep")
    parser.add_argument("--keep-workspace", action="store_true", help="Do not delete the workspace after success")
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Run bootstrap/setup steps (clone, bundle install) and exit before restarting the stack",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Reuse an existing workspace and skip bootstrap steps (requires --workspace and --reuse-workspace)",
    )
    parser.add_argument("--proxy-source", help="Alternate git source for mcp-proxy")
    parser.add_argument("--wrapper-release", help="Path to a codex-mcp-wrapper release directory to copy into the sandbox")
    parser.add_argument("--port", type=int, help="Override the sandbox proxy port")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Prepare manual assets and exit instead of running codex exec automation",
    )
    parser.add_argument(
        "--manual-stage",
        action="append",
        choices=["bundle-tools", "install", "remove"],
        help="Treat the specified stage as manual/resumable; the harness emits stage instructions and exits before running it",
    )
    parser.add_argument("--codex-cli", help="Path to the codex CLI binary to run inside the sandbox")
    parser.add_argument("--codex-home", help="Optional path to mirror into CODEX_HOME inside the sandbox")
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Delete previously kept smoke workspaces (optionally the path from --workspace) and exit",
    )
    parser.add_argument(
        "--force-workspace",
        action="store_true",
        help="Delete the provided --workspace even if it already exists and was not created by the harness",
    )
    parser.add_argument(
        "--reuse-workspace",
        action="store_true",
        help="Reuse an existing smoke workspace (identified by the marker file) instead of deleting it",
    )
    args = parser.parse_args(argv)
    if args.bootstrap_only and args.skip_bootstrap:
        parser.error("--bootstrap-only and --skip-bootstrap cannot be used together")
    if args.skip_bootstrap and not (args.workspace and args.reuse_workspace):
        parser.error("--skip-bootstrap requires --workspace and --reuse-workspace")
    if args.bootstrap_only and not args.keep_workspace:
        args.keep_workspace = True
    if args.force_workspace and args.reuse_workspace:
        parser.error("--force-workspace and --reuse-workspace cannot be used together")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    if args.cleanup_only:
        target = Path(args.workspace).expanduser().resolve() if args.workspace else None
        removed = _cleanup_entrypoint(target)
        if not removed and target:
            print(f"No smoke workspace found at {target}")
        elif not removed:
            print("No prior smoke workspaces detected.")
        else:
            for path in removed:
                print(f"Removed smoke workspace: {path}")
        return
    skip_cleanup = Path(args.workspace).expanduser().resolve() if (args.workspace and args.reuse_workspace) else None
    removed_auto = cleanup_temp_smoke_workspaces(skip=skip_cleanup)
    if removed_auto:
        print("Removed stale smoke workspaces:")
        for path in removed_auto:
            print(f"  - {path}")
    harness = CloneSmokeHarness(args)
    harness.run()


if __name__ == "__main__":
    main()
