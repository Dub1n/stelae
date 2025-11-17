#!/usr/bin/env python3
"""Bootstrap the local 1mcp CLI/config using repo defaults."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = Path(os.getenv("ONE_MCP_DIR", Path.home() / "apps" / "vendor" / "1mcpserver"))
DEFAULT_CONFIG = Path(os.getenv("ONE_MCP_CONFIG", Path.home() / ".config" / "1mcp" / "mcp.json"))
DEFAULT_STATE_HOME = Path(
    os.getenv("STELAE_STATE_HOME")
    or Path(os.getenv("STELAE_CONFIG_HOME", Path.home() / ".config" / "stelae")) / ".state"
)
DEFAULT_STATE_HOME.mkdir(parents=True, exist_ok=True)
DEFAULT_DISCOVERY = Path(
    os.getenv("STELAE_DISCOVERY_PATH")
    or (DEFAULT_STATE_HOME / "discovered_servers.json")
)
DEFAULT_UV = os.getenv("ONE_MCP_BIN", "uv")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stelae_lib.integrator.discovery import seed_discovery_cache  # noqa: E402


def _run(command: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(command)
    if cwd:
        printable = f"(cd {cwd} && {printable})"
    print(f"[cmd] {printable}")
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise SystemExit(f"Command not found: {command[0]}") from exc


def _ensure_repo(path: Path, repo_url: str, *, update: bool) -> str:
    git_dir = path / ".git"
    if git_dir.exists():
        if update:
            _run(["git", "-C", str(path), "pull", "--ff-only"])
            return "updated"
        return "exists"
    if path.exists():
        raise SystemExit(f"Target {path} exists but is not a git repo; move it and retry")
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", repo_url, str(path)])
    return "cloned"


def _uv_sync(path: Path, uv_bin: str, *, skip: bool) -> bool:
    if skip:
        return False
    _run([uv_bin, "sync"], cwd=path)
    return True


def _ensure_discovery(path: Path) -> bool:
    return seed_discovery_cache(path)


def _write_config(path: Path, uv_bin: str, repo: Path, discovery: Path) -> bool:
    config = {
        "mcpServers": {
            "one_mcp": {
                "command": uv_bin,
                "args": ["--directory", str(repo), "run", "server.py", "--local"],
            }
        },
        "discovery": {
            "cachePath": str(discovery),
        },
    }
    rendered = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the 1mcp CLI for Stelae")
    parser.add_argument("--repo-url", default=os.getenv("ONE_MCP_REPO", "https://github.com/Dub1n/stelae-1mcpserver.git"))
    parser.add_argument("--target", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--uv-bin", default=DEFAULT_UV)
    parser.add_argument("--discovery", type=Path, default=DEFAULT_DISCOVERY)
    parser.add_argument("--skip-update", action="store_true", help="Skip git pull when repo already exists")
    parser.add_argument("--skip-sync", action="store_true", help="Skip running 'uv sync' inside the repo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_status = _ensure_repo(args.target, args.repo_url, update=not args.skip_update)
    sync_ran = _uv_sync(args.target, args.uv_bin, skip=args.skip_sync)
    discovery_created = _ensure_discovery(args.discovery)
    config_written = _write_config(args.config, args.uv_bin, args.target, args.discovery)

    summary = {
        "repo": str(args.target),
        "repo_status": repo_status,
        "uv_synced": sync_ran,
        "discovery_created": discovery_created,
        "config_path": str(args.config),
        "config_updated": config_written,
        "discovery_path": str(args.discovery),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:  # pragma: no cover - surface command errors
        raise SystemExit(f"Command failed (exit {exc.returncode})") from exc
