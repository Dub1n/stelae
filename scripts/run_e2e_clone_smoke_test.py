#!/usr/bin/env python3
"""Automated harness for the clone smoke test."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import threading
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import deque
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


def _is_windows_mount(path: Path) -> bool:
    """Best-effort detection of WSL Windows-backed mounts (/mnt/<drive>/…)."""

    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    parts = resolved.parts
    return len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1


def upsert_env_value(env_file: Path, key: str, value: str) -> None:
    """Ensure the config-home .env persists the requested key/value pair."""

    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    updated = False
    for idx, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[idx] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

from stelae_lib.smoke_harness import (
    MCPToolCall,
    build_env_map,
    choose_proxy_port,
    format_env_lines,
    parse_codex_jsonl,
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


def assert_stage_expectations(stage: CodexStage, calls: Iterable[MCPToolCall]) -> None:
    """Ensure every expected tool call appears at least ``min_calls`` times."""

    for expectation in stage.expectations:
        matches = [call for call in calls if expectation.matches(call)]
        if len(matches) < expectation.min_calls:
            raise RuntimeError(
                f"Codex stage '{stage.name}' missing tool '{expectation.tool}' – {expectation.description}."
            )


class CloneSmokeHarness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.force_workspace = bool(args.force_workspace)
        self.reuse_workspace = bool(args.reuse_workspace)
        self.force_outdated = bool(args.force_outdated)
        self.force_bootstrap = bool(args.force_bootstrap)
        self.plan_only = bool(args.plan_only)
        self.go_flags = args.go_flags if args.go_flags is not None else ""
        self.gomaxprocs = args.gomaxprocs if args.gomaxprocs is not None else ""
        self.skip_pm2_kill = bool(args.no_pm2_kill)
        self.skip_port_kill = bool(args.no_port_kill)
        self.pytest_scope = args.pytest_scope
        self.capture_diag_logs = bool(args.capture_diag_logs)
        self.force_no_logs = bool(args.force_no_logs)
        self.source_repo = Path(args.source).resolve()
        if not (self.source_repo / "README.md").exists():
            raise SystemExit(f"{self.source_repo} does not look like the stelae repo")
        if args.workspace:
            workspace = Path(args.workspace).expanduser().resolve()
            if _is_windows_mount(workspace):
                raise SystemExit(
                    f"Workspace path {workspace} appears to live on a Windows-backed mount; "
                    "use a WSL/ext4 path (e.g., under your home directory) instead."
                )
            workspace_existed = workspace.exists()
            self.workspace = workspace
            self._ephemeral = False
            self.log_path = self.workspace / "harness.log"
            if not self.plan_only:
                self.workspace = self._prepare_workspace_dir(self.workspace)
                if workspace_existed and self.reuse_workspace and not self.force_bootstrap and not args.skip_bootstrap:
                    # Reuse assumes prior bootstrap; skip heavy setup unless explicitly requested.
                    self._log("Reusing existing workspace; skipping bootstrap steps (pass --force-bootstrap to redo).")
                    args.skip_bootstrap = True
        else:
            suggested = Path(tempfile.gettempdir()) / f"{WORKSPACE_PREFIX}plan" if self.plan_only else Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
            if _is_windows_mount(suggested):
                raise SystemExit(
                    f"Temporary workspace {suggested} resolved under /mnt; set TMPDIR to a WSL/ext4 path (e.g., ~/tmp) and retry."
                )
            self.workspace = suggested
            self._ephemeral = True
            self.log_path = self.workspace / "harness.log"
            if not self.plan_only:
                mark_workspace(self.workspace)
        self.log_path = self.workspace / "harness.log"
        self.clone_dir = self.workspace / "stelae"
        self.apps_dir = self.workspace / "apps"
        self.config_home = self.workspace / "config-home"
        self.pm2_home = self.workspace / ".pm2"
        self.client_repo = self.workspace / "client-repo"
        self.codex_home = self.workspace / "codex-home"
        self.transcript_dir = self.workspace / "codex-transcripts"
        self.log_path = self.workspace / "harness.log"
        self.python_site = self.workspace / "python-site"
        self._pytest_ready = False
        self.run_label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.capture_debug_tools = bool(args.capture_debug_tools)
        self.restart_timeout = float(args.restart_timeout)
        self.restart_retries = max(0, int(args.restart_retries))
        self.debug_log_dir = self.workspace / "logs"
        self.streamable_debug_log = self.debug_log_dir / "streamable_tool_debug.log"
        self.aggregator_debug_log = self.debug_log_dir / "tool_aggregator_debug.log"
        self.repo_debug_dir = self.source_repo / "dev" / "logs" / "harness"
        self.repo_smoke_root = self.source_repo / "logs" / "e2e-smoke"
        self.repo_smoke_run_dir = self.repo_smoke_root / self.run_label
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
        self.python_bin = self._resolve_python_bin(args.python_bin)
        self._env = os.environ.copy()
        self._env.update(
            {
                "STELAE_DIR": str(self.clone_dir),
                "APPS_DIR": str(self.apps_dir),
                "STELAE_CONFIG_HOME": str(self.config_home),
                "STELAE_ENV_FILE": str(self.config_home / ".env"),
                "PM2_HOME": str(self.pm2_home),
                "GOMODCACHE": str(self.workspace / ".gomodcache"),
                "GOCACHE": str(self.workspace / ".gocache"),
                "PM2_HOME": str(self.pm2_home),
                "CODEX_HOME": str(self.codex_home),
                "STELAE_USE_INTENDED_CATALOG": "1",
            }
        )
        if self.go_flags:
            self._env["GOFLAGS"] = self.go_flags
        if self.gomaxprocs:
            self._env["GOMAXPROCS"] = self.gomaxprocs
        self._env["PYTHON"] = self.python_bin
        self._env["SHIM_PYTHON"] = self.python_bin
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
        if self.capture_debug_tools:
            self._configure_debug_env()
        self.heartbeat_timeout = float(args.heartbeat_timeout)
        self._last_heartbeat = time.monotonic()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_triggered = False
        self._shutdown_requested = False
        self._signal_exit = False
        self._original_signal_handlers: dict[int, signal.HandlersType | None] = {}
        if not self.plan_only:
            self._install_signal_handlers()
            if self.heartbeat_timeout > 0:
                self._start_heartbeat_monitor()
        if self.capture_diag_logs and self.plan_only:
            self._log("Diag logging requested, but plan-only mode skips execution; no diag logs will be started.")
        self._log(f"Workspace: {self.workspace}")
        self._log(f"Using Python interpreter {self.python_bin}")
        self._diag_procs: list[subprocess.Popen[str]] = []
        self._diag_root: Path | None = None

    # --------------------------------------------------------------------- utils
    def _resolve_python_bin(self, override: str | None) -> str:
        if override:
            candidate = Path(override).expanduser()
            if not candidate.exists():
                raise SystemExit(f"--python-bin points to a non-existent path: {candidate}")
            return str(candidate)
        candidates = []
        for name in ("python3", "python"):
            venv_candidate = self.source_repo / ".venv" / "bin" / name
            candidates.append(venv_candidate)
        candidates.append(Path(sys.executable))
        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)
        return sys.executable

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
        self._last_heartbeat = time.monotonic()

    def _apply_proxy_port(self, port: int) -> None:
        base = f"http://127.0.0.1:{port}"
        self.proxy_port = port
        self._env["PROXY_PORT"] = str(port)
        self._env["STELAE_PROXY_BASE"] = base
        self._env["PUBLIC_BASE_URL"] = base
        self._env["PUBLIC_SSE_URL"] = f"{base}/mcp"
        self._env["PUBLIC_PORT"] = str(port)

    def _configure_debug_env(self) -> None:
        self.debug_log_dir.mkdir(parents=True, exist_ok=True)
        self.repo_debug_dir.mkdir(parents=True, exist_ok=True)
        self._env["STELAE_STREAMABLE_DEBUG_TOOLS"] = "workspace_fs_read,manage_stelae"
        self._env["STELAE_STREAMABLE_DEBUG_LOG"] = str(self.streamable_debug_log)
        self._env["STELAE_TOOL_AGGREGATOR_DEBUG_TOOLS"] = "workspace_fs_read"
        self._env["STELAE_TOOL_AGGREGATOR_DEBUG_LOG"] = str(self.aggregator_debug_log)

    def _start_heartbeat_monitor(self) -> None:
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="smoke-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_monitor(self) -> None:
        if self._heartbeat_thread is None:
            return
        self._heartbeat_stop.set()
        self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    def _start_diag_logs(self) -> None:
        """Best-effort diag capture (dmesg/syslog/top/vmstat/free/pm2 logs) to repo logs/diag/."""

        self._diag_root = self.source_repo / "logs" / "diag"
        self._diag_root.mkdir(parents=True, exist_ok=True)
        commands: list[tuple[list[str], Path, bool]] = []
        # dmesg (may require sudo) – required unless forced off
        commands.append((["dmesg", "-wT", "--level=err,warn"], self._diag_root / "dmesg.log", True))
        # syslog tail (best effort) – required unless forced off
        commands.append((["tail", "-F", "/var/log/syslog"], self._diag_root / "syslog.log", True))
        # top batch mode, bounded iterations
        commands.append((["top", "-b", "-d", "5", "-n", "120"], self._diag_root / "top.log", False))
        # vmstat snapshot
        commands.append((["vmstat", "1", "30"], self._diag_root / "vmstat.log", False))
        env = self._env.copy()
        required_started = 0
        required_requested = 0
        for cmd, log_path, required in commands:
            if required:
                required_requested += 1
            try:
                handle = log_path.open("w", encoding="utf-8")
                proc = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True)
                self._diag_procs.append(proc)
                self._log(f"[diag] started {' '.join(cmd)} → {log_path}")
                if required:
                    required_started += 1
            except FileNotFoundError:
                self._log(f"[diag] skipping {' '.join(cmd)} (command not found)")
            except PermissionError:
                self._log(f"[diag] skipping {' '.join(cmd)} (permission denied)")
            except Exception as exc:  # pragma: no cover - defensive
                self._log(f"[diag] failed to start {' '.join(cmd)}: {exc}")
        # pm2 logs tail (best effort, non-blocking)
        pm2_log = self._diag_root / "pm2.log"
        try:
            with pm2_log.open("w", encoding="utf-8") as handle:
                proc = subprocess.Popen(
                    ["pm2", "logs", "--lines", "50", "--nostream"],
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                self._diag_procs.append(proc)
                self._log(f"[diag] started pm2 logs snapshot → {pm2_log}")
        except Exception as exc:  # pragma: no cover - best effort
            self._log(f"[diag] skipping pm2 logs snapshot: {exc}")
        # free -h snapshots
        for label in ("before",):
            try:
                output = subprocess.check_output(["free", "-h"], text=True)
                (self._diag_root / f"free-{label}.log").write_text(output, encoding="utf-8")
                self._log(f"[diag] captured free -h ({label})")
            except Exception as exc:  # pragma: no cover - best effort
                self._log(f"[diag] skipping free -h ({label}): {exc}")

        if required_requested and required_started == 0 and not self.force_no_logs:
            raise SystemExit(
                "Diag logging requested but dmesg/syslog could not be started. "
                "Rerun with --force-no-logs to proceed without them."
            )
        if required_started == 0:
            self._log("[diag] required loggers not running; continuing due to --force-no-logs")

    def _stop_diag_logs(self) -> None:
        # free -h after run
        if self._diag_root:
            try:
                output = subprocess.check_output(["free", "-h"], text=True)
                (self._diag_root / "free-after.log").write_text(output, encoding="utf-8")
                self._log("[diag] captured free -h (after)")
            except Exception:
                pass
        for proc in self._diag_procs:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._diag_procs = []

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(timeout=1):
            if self.heartbeat_timeout <= 0:
                continue
            if self._heartbeat_triggered:
                return
            if time.monotonic() - self._last_heartbeat > self.heartbeat_timeout:
                self._heartbeat_triggered = True
                self._log(
                    f"Heartbeat timeout exceeded ({self.heartbeat_timeout}s without new log output); sending SIGTERM to self."
                )
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception:
                    os._exit(1)
                return

    def _list_port_listeners(self, port: int) -> list[tuple[int, str]]:
        listeners: list[tuple[int, str]] = []
        seen: set[int] = set()
        ss_bin = shutil.which("ss")
        if ss_bin:
            result = subprocess.run(
                [ss_bin, "-ltnp", f"( sport = :{port} )"],
                env=self._env,
                text=True,
                capture_output=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                for match in re.finditer(r"pid=(\d+)", line):
                    pid = int(match.group(1))
                    if pid in seen:
                        continue
                    seen.add(pid)
                    listeners.append((pid, line.strip()))
        if listeners:
            return listeners
        lsof_bin = shutil.which("lsof")
        if not lsof_bin:
            return []
        result = subprocess.run(
            [lsof_bin, "-ti", f"tcp:{port}"],
            env=self._env,
            text=True,
            capture_output=True,
            check=False,
        )
        for raw in result.stdout.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                pid = int(raw)
            except ValueError:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            listeners.append((pid, f"{lsof_bin} tcp:{port}"))
        return listeners

    def _preflight_proxy_port(self) -> None:
        listeners = self._list_port_listeners(self.proxy_port)
        if not listeners:
            self._log(f"Port preflight: :{self.proxy_port} already free.")
            return
        kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
        self._log(f"Port preflight: killing {len(listeners)} listener(s) on :{self.proxy_port} before restart.")
        for pid, desc in listeners:
            try:
                os.kill(pid, kill_signal)
                self._log(f"Port preflight: killed pid {pid} ({desc})")
            except ProcessLookupError:
                self._log(f"Port preflight: pid {pid} already exited")
            except PermissionError as exc:
                self._log(f"Port preflight: permission denied killing pid {pid}: {exc}")
        remaining = self._list_port_listeners(self.proxy_port)
        if remaining:
            self._log(
                f"Port preflight: listeners still present on :{self.proxy_port}; restart script will attempt a force kill."
            )
        else:
            self._log(f"Port preflight: confirmed :{self.proxy_port} is clear before restart.")
    def _check_workspace_revision(self) -> None:
        """Reject stale clones unless explicitly forced."""

        if not self.reuse_workspace:
            return
        if not (self.clone_dir / ".git").exists():
            return
        try:
            source_head = (
                subprocess.check_output(["git", "-C", str(self.source_repo), "rev-parse", "HEAD"], text=True)
                .strip()
            )
            workspace_head = (
                subprocess.check_output(["git", "-C", str(self.clone_dir), "rev-parse", "HEAD"], text=True)
                .strip()
            )
            behind_count_raw = subprocess.check_output(
                ["git", "-C", str(self.clone_dir), "rev-list", "--count", f"{workspace_head}..{source_head}"],
                text=True,
            )
            behind = int(behind_count_raw.strip() or "0")
        except (subprocess.SubprocessError, ValueError, OSError):
            return
        if behind > 0 and not self.force_outdated:
            raise SystemExit(
                f"Workspace clone is {behind} commit(s) behind source. "
                "Use --force-outdated to proceed or omit --reuse-workspace to rebuild."
            )
        if behind > 0:
            self._log(f"Warning: workspace clone is {behind} commit(s) behind source (proceeding due to --force-outdated).")
        elif behind == 0:
            self._log("Workspace clone matches source HEAD; proceeding with reuse.")

    def _emit_plan(self) -> None:
        """Print a dry-run summary and exit."""

        self._log("Plan-only mode: no commands will be executed.")
        summary = {
            "workspace": str(self.workspace),
            "reuse_workspace": self.reuse_workspace,
            "force_outdated": self.force_outdated,
            "force_bootstrap": self.force_bootstrap,
            "ephemeral": self._ephemeral,
            "clone_dir": str(self.clone_dir),
            "apps_dir": str(self.apps_dir),
            "config_home": str(self.config_home),
            "state_home": str(self.config_home / '.state'),
            "pm2_home": str(self.pm2_home),
            "client_repo": str(self.client_repo),
            "codex_home": str(self.codex_home),
            "proxy_port": self.proxy_port,
            "python_bin": self.python_bin,
            "skip_bootstrap": self.args.skip_bootstrap,
            "restart_timeout": self.restart_timeout,
            "restart_retries": self.restart_retries,
            "heartbeat_timeout": self.heartbeat_timeout,
            "capture_debug_tools": self.capture_debug_tools,
            "go_flags": self.go_flags or "<default>",
            "gomaxprocs": self.gomaxprocs or "<default>",
            "skip_pm2_kill": self.skip_pm2_kill,
            "skip_port_kill": self.skip_port_kill,
            "pytest_scope": self.pytest_scope,
            "capture_diag_logs": self.capture_diag_logs,
            "force_no_logs": self.force_no_logs,
        }
        for key, value in summary.items():
            self._log(f"[plan] {key}: {value}")
        self._log("Planned stages: clone (if needed) → proxy clone (if needed) → env bootstrap → bundle install → render/restart → pytest → Codex stages → verify-clean")
        if self.capture_diag_logs:
            self._log("[plan] diag logs would be captured to repo logs/diag/")

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        capture_output: bool = False,
        check: bool = True,
        log_output: bool = True,
        log_prefix: str | None = None,
        timeout: float | None = None,
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
                try:
                    result = subprocess.run(
                        cmd,
                        cwd=str(cwd) if cwd else None,
                        env=self._env,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=timeout,
                    )
                except subprocess.TimeoutExpired as exc:
                    self._log(f"Command timed out after {timeout}s: {display}")
                    raise
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
                timeout_triggered = False
                timer: threading.Timer | None = None
                if timeout is not None:

                    def _timeout_handler() -> None:
                        nonlocal timeout_triggered
                        if proc.poll() is not None:
                            return
                        timeout_triggered = True
                        try:
                            proc.terminate()
                            proc.wait(5)
                        except subprocess.TimeoutExpired:
                            proc.kill()

                    timer = threading.Timer(timeout, _timeout_handler)
                    timer.start()
                try:
                    if proc.stdout:
                        for line in proc.stdout:
                            stripped = line.rstrip("\n")
                            output_lines.append(stripped)
                            if log_output and stripped:
                                self._log(f"{prefix}{stripped}" if prefix else stripped)
                finally:
                    if timer:
                        timer.cancel()
                    proc.wait()
                completed = subprocess.CompletedProcess(cmd, proc.returncode, "\n".join(output_lines), "")
                if timeout_triggered:
                    self._log(f"Command timed out after {timeout}s: {display}")
                    raise subprocess.TimeoutExpired(cmd, timeout or 0, output=completed.stdout, stderr=completed.stderr)
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

    def _capture_debug_logs(self, stage_name: str) -> None:
        if not self.capture_debug_tools:
            return
        stage_slug = stage_name.replace(" ", "_")
        artifacts = (
            (self.streamable_debug_log, "streamable_tool_debug.log"),
            (self.aggregator_debug_log, "tool_aggregator_debug.log"),
        )
        self.debug_log_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.repo_debug_dir.mkdir(parents=True, exist_ok=True)
        self.repo_smoke_run_dir.mkdir(parents=True, exist_ok=True)
        for source, base_name in artifacts:
            if not source.exists():
                continue
            workspace_copy = self.debug_log_dir / f"{stage_slug}-{base_name}"
            transcript_copy = self.transcript_dir / f"{stage_slug}-{base_name}"
            repo_copy = self.repo_debug_dir / f"{self.run_label}-{stage_slug}-{base_name}"
            smoke_copy = self.repo_smoke_run_dir / f"{stage_slug}-{base_name}"
            shutil.copy2(source, workspace_copy)
            shutil.copy2(source, transcript_copy)
            shutil.copy2(source, repo_copy)
            shutil.copy2(source, smoke_copy)
            source.unlink(missing_ok=True)
            self._log(
                "Captured debug log %s for stage %s → %s (mirrored to %s, %s, and %s)"
                % (base_name, stage_name, workspace_copy, transcript_copy, repo_copy, smoke_copy)
            )

    def _mirror_transcript_to_repo(self, stage_name: str) -> None:
        transcript_path = self.transcript_dir / f"{stage_name}.jsonl"
        if not transcript_path.exists():
            return
        try:
            self.repo_smoke_run_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._log(f"Warning: unable to create smoke log directory {self.repo_smoke_run_dir}: {exc}")
            return
        dest = self.repo_smoke_run_dir / f"{stage_name}.jsonl"
        shutil.copy2(transcript_path, dest)
        self._log(f"Mirrored Codex transcript for stage {stage_name} → {dest}")

    # -------------------------------------------------------------------- stages
    def run(self) -> None:
        if self.plan_only:
            self._emit_plan()
            return
        success = False
        try:
            if self.capture_diag_logs:
                self._start_diag_logs()
            if self.args.skip_bootstrap:
                self._check_workspace_revision()
                self._assert_bootstrap_ready()
            else:
                self._clone_repo()
                self._clone_proxy_repo()
                if self.reuse_workspace:
                    self._check_workspace_revision()
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
            self._log("Catalog restart cycle 1/1 (intended)")
            self._run_render_restart()
            self._assert_clean_repo("post-restart[intended]")
            if self.pytest_scope in ("structural", "full"):
                self._run_pytest(["tests/test_repo_sanitized.py"], label="structural")
            stages = self._codex_stages()
            self._prepare_codex_environment()
            self._run_codex_flow(stages)
            if self.pytest_scope == "full":
                self._run_pytest([], label="full-suite")
            self._run_verify_clean()
            self._assert_clean_repo("final")
            success = True
            self._log("Clone smoke harness completed")
        finally:
            self._stop_heartbeat_monitor()
            self._teardown_processes()
            if success and not self.args.keep_workspace:
                self._cleanup_workspace()
            elif not success:
                if not self._signal_exit:
                    self._log(
                        f"Workspace left at {self.workspace} for triage (set --keep-workspace to always retain)."
                    )
            self._stop_diag_logs()
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
            python_bin=self.python_bin,
            proxy_port=self.proxy_port,
            wrapper_bin=self.wrapper_bin,
            wrapper_config=self.wrapper_config,
            extra={
                "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "test-clone-smoke-key"),
                "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
            },
        )
        env_contents = format_env_lines(env_map)
        env_file = self.config_home / ".env"
        self._log(f"Writing sandbox env → {env_file}")
        env_file.write_text(env_contents, encoding="utf-8")
        self._run(
            [
                self.python_bin,
                "scripts/setup_env.py",
                "--config-home",
                str(self.config_home),
                "--repo-root",
                str(self.clone_dir),
                "--env-file",
                str(env_file),
                "--materialize-defaults",
            ],
            cwd=self.clone_dir,
        )

    def _copy_wrapper_release(self) -> None:
        if not self.wrapper_release:
            self._log("No wrapper release provided; using any existing installation on disk.")
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
                self.python_bin,
                "scripts/install_stelae_bundle.py",
                "--bundle",
                "bundles/starter",
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
        repo_env = self.clone_dir / ".env"
        config_env = self.config_home / ".env"
        required = [
            (self.clone_dir, "cloned repo"),
            (repo_env, "repo .env"),
            (config_env, "config-home .env"),
            (self.apps_dir / "mcp-proxy", "mcp-proxy checkout"),
        ]
        missing = [f"{label} ({path})" for path, label in required if not path.exists()]
        if missing:
            joined = "\n  - ".join(missing)
            raise SystemExit(f"--skip-bootstrap requested but required artifacts are missing:\n  - {joined}")
        env_file = config_env
        env_data = env_file.read_text(encoding="utf-8").splitlines()
        proxy_port_line = next(
            (line for line in env_data if line.startswith("PROXY_PORT=") or line.startswith("PUBLIC_PORT=")),
            None,
        )
        if not proxy_port_line:
            raise SystemExit("--skip-bootstrap requested but PROXY_PORT/PUBLIC_PORT not found in config-home .env")
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
        if not self.skip_port_kill:
            self._preflight_proxy_port()
        restart_script = self.clone_dir / "scripts" / "run_restart_stelae.sh"
        args = [
            str(restart_script),
            "--no-bridge",
            "--no-cloudflared",
        ]
        if self.skip_pm2_kill:
            args.append("--no-pm2-kill")
        if self.skip_port_kill:
            args.append("--no-port-kill")
        self._log("Restarting stack inside sandbox (expected <60s; investigate logs instead of extending timeouts)…")
        self._run_restart_with_retry(args)
        self._log("Restart script finished successfully.")

    def _run_restart_with_retry(self, args: list[str]) -> None:
        attempts = max(1, self.restart_retries + 1)
        for attempt in range(1, attempts + 1):
            try:
                self._log(f"Restart attempt {attempt}/{attempts} (timeout {self.restart_timeout}s)")
                self._run(args, cwd=self.clone_dir, timeout=self.restart_timeout)
                return
            except subprocess.TimeoutExpired:
                self._collect_restart_diagnostics(attempt)
                if attempt >= attempts:
                    raise
                self._log(f"Retrying restart script ({attempt + 1}/{attempts}) after timeout…")

    def _collect_restart_diagnostics(self, attempt: int) -> None:
        self._log(
            f"Restart attempt {attempt} exceeded {self.restart_timeout}s; collecting pm2 status and recent log snippets…"
        )
        if self.pm2_bin:
            try:
                self._run(["pm2", "status"], capture_output=True, check=False, log_prefix="[diag] ")
            except Exception as exc:
                self._log(f"[diag] pm2 status failed: {exc}")
        else:
            self._log("[diag] pm2 binary not found; skipping status dump")
        log_dir = self.pm2_home / "logs"
        targets = [
            ("mcp-proxy-out", log_dir / "mcp-proxy-out.log", 80),
            ("mcp-proxy-error", log_dir / "mcp-proxy-error.log", 80),
            ("stelae-bridge-out", log_dir / "stelae-bridge-out.log", 60),
            ("stelae-bridge-error", log_dir / "stelae-bridge-error.log", 60),
        ]
        for label, path, max_lines in targets:
            if not path.exists():
                continue
            tail_lines: deque[str] = deque(maxlen=max_lines)
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for raw in handle:
                        tail_lines.append(raw.rstrip("\n"))
            except OSError as exc:
                self._log(f"[diag] Unable to read {path}: {exc}")
                continue
            if not tail_lines:
                continue
            self._log(f"[diag] tail -n{max_lines} {path}")
            for line in tail_lines:
                if not line:
                    continue
                self._log(f"[diag] {label}: {line}")

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
                        self.python_bin,
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
        cmd = [self.python_bin, "-m", "pytest"]
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

    def _run_codex_flow(self, stages: List[CodexStage]) -> None:
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        for stage in stages:
            try:
                events = self._execute_codex_stage(stage)
                calls = summarize_tool_calls(events)
                assert_stage_expectations(stage, calls)
                self.codex_transcripts[stage.name] = calls
                self._log(
                    f"Codex stage '{stage.name}' captured {len(calls)} tool calls: "
                    + ", ".join(sorted({call.tool for call in calls}))
                )
            finally:
                self._capture_debug_logs(stage.name)
                self._mirror_transcript_to_repo(stage.name)
            self._assert_clean_repo(f"after-{stage.name}")

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
                tool="manage_stelae",
                description="List discovered servers",
                predicate=lambda call: isinstance(call.arguments, dict)
                and call.arguments.get("operation") == "list_discovered_servers",
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
        list_discovered_payload = json.dumps({"operation": "list_discovered_servers"})
        return textwrap.dedent(
            f"""
            Capture the MCP behavior for this sandbox—do not run shell commands or edit files manually.

            1. Call `tools/list` once to record whatever the proxy currently advertises (note the result in your summary). This is for diagnostics only.
            2. Regardless of whether the catalog includes them, call these MCP tools in order and report their outputs or failures:
               - `workspace_fs_read` with {read_payload}
               - `grep` with {grep_payload}
               - `manage_stelae` with {list_discovered_payload}
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
                    "dry_run": True,
                    "force": True,
                },
            }
        )
        verify_payload = json.dumps({"operation": "list_discovered_servers"})
        return textwrap.dedent(
            f"""
            Install the `{self.external_server}` descriptor under the alias `{self.external_target}` using only the `manage_stelae` MCP tool. The proxy already points at {self.clone_dir}; do not run shell commands.
            - Call `manage_stelae` with {install_payload} (dry-run to avoid restarting the stack during this harness).
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
                    "dry_run": True,
                    "force": True,
                },
            }
        )
        return textwrap.dedent(
            f"""
            Clean up the `{self.external_target}` installation so the sandbox returns to a clean state. Operate entirely through the MCP catalog (no shell access).
            - Call `manage_stelae` with {remove_payload} (dry-run) and wait for the tool to confirm completion.
            - Verify the alias no longer appears in discovery (read-only checks only).
            - Summarize the outcome; do not issue shell commands.
            """
        ).strip()

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
        self._stop_heartbeat_monitor()
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
    parser.add_argument("--python-bin", help="Preferred Python interpreter for sandbox automation (default: repo .venv or current python)")
    parser.add_argument("--codex-cli", help="Path to the codex CLI binary to run inside the sandbox")
    parser.add_argument("--codex-home", help="Optional path to mirror into CODEX_HOME inside the sandbox")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Show planned steps, paths, and env without executing commands (dry run)",
    )
    parser.add_argument(
        "--capture-diag-logs",
        action="store_true",
        help="Capture lightweight diag logs (dmesg/syslog/top) to logs/diag/ during the run (best-effort; may require sudo)",
    )
    parser.add_argument(
        "--force-no-logs",
        action="store_true",
        help="Proceed even if diag logging cannot start (bypasses dmesg/syslog guard)",
    )
    parser.add_argument(
        "--go-flags",
        default="-p=1",
        help="GOFLAGS value to use for proxy builds (default: -p=1 to throttle parallelism; set empty to use Go default)",
    )
    parser.add_argument(
        "--gomaxprocs",
        default="1",
        help="GOMAXPROCS value to use during proxy builds (default: 1; set empty to use Go default)",
    )
    parser.add_argument(
        "--capture-debug-tools",
        action="store_true",
        help="Enable FastMCP + tool_aggregator debug logs and persist per-stage snapshots alongside Codex transcripts",
    )
    parser.add_argument(
        "--restart-timeout",
        type=int,
        default=90,
        help="Seconds to wait for run_restart_stelae.sh before collecting diagnostics (default: 90)",
    )
    parser.add_argument(
        "--restart-retries",
        type=int,
        default=0,
        help="Number of additional restart attempts after a timeout (default: 0)",
    )
    parser.add_argument(
        "--heartbeat-timeout",
        type=int,
        default=240,
        help="Abort the harness if no log output is produced for N seconds (0 disables; default: 240)",
    )
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
        default=True,
        help="Reuse an existing smoke workspace (identified by the marker file) instead of deleting it (default: on when --workspace is set)",
    )
    parser.add_argument(
        "--no-reuse-workspace",
        action="store_false",
        dest="reuse_workspace",
        help="Do not reuse an existing workspace; recreate it even if present",
    )
    parser.add_argument(
        "--force-outdated",
        action="store_true",
        help="Proceed even if the reused workspace's clone is behind the source repo",
    )
    parser.add_argument(
        "--force-bootstrap",
        action="store_true",
        help="Redo bootstrap steps (clone/install/bundle) even when reusing a workspace",
    )
    parser.add_argument(
        "--no-pm2-kill",
        action="store_true",
        default=True,
        help="Skip pm2 kill during restart; only restart managed apps (default)",
    )
    parser.add_argument(
        "--pm2-kill",
        action="store_false",
        dest="no_pm2_kill",
        help="Allow pm2 kill during restart (reverts to previous aggressive behavior)",
    )
    parser.add_argument(
        "--no-port-kill",
        action="store_true",
        help="Skip aggressive pre-kill of listeners on the proxy port during restart",
    )
    parser.add_argument(
        "--pytest-scope",
        choices=["none", "structural", "full"],
        default="structural",
        help="Which pytest scope to run after restart (default: structural)",
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
    if args.restart_timeout <= 0:
        parser.error("--restart-timeout must be greater than zero")
    if args.restart_retries < 0:
        parser.error("--restart-retries cannot be negative")
    if args.heartbeat_timeout < 0:
        parser.error("--heartbeat-timeout cannot be negative")
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
