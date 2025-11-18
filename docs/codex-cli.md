# Codex MCP Wrapper CLI Guide

Quick reference for running the wrapper locally via the Typer CLI.

## Prereqs
1. Python 3.11+ and Codex CLI already logged in (`codex login`).
2. From the repo root:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```
3. Create `wrapper.toml` (see `wrapper.example.toml`) with at least one worker. `state/` is created automatically and seeds each worker’s `CODEX_HOME` under `state/workers/<label>/codex-home`.

## Core Commands
- **Foreground server (stdio/SSE/HTTP)**  
  ```bash
  codex-mcp-wrapper serve --config wrapper.toml --transport sse --host 127.0.0.1 --port 4105
  ```  
  Use `--transport stdio` for MCP stdio; add `--log-level debug` for verbose logs. Include `--sync-codex-config` to copy your `~/.codex/config.toml` (or `$CODEX_HOME`) into each worker CODEX_HOME so local MCP definitions are exposed.

- **Run a mission locally** (no server needed):  
  ```bash
  codex-mcp-wrapper run-mission missions/dev-smoke.json --workspace /path/to/workspace --attach-artifacts --sync-codex-config
  ```  
  Flags like `--sandbox`, `--approval-policy`, `--env KEY=VAL`, and `--base-instructions` override mission defaults.

- **Drive a mission over SSE** (talk to the running server):  
  ```bash
  codex-mcp-wrapper sse run missions/dev-smoke.json --host 127.0.0.1 --port 4105
  ```

## Background Server Helpers
- Start detached (logs to `state/logs/serve-<port>.log`):  
  ```bash
  codex-mcp-wrapper serve start --config wrapper.toml --transport sse --host 127.0.0.1 --port 4105 --sync-codex-config
  ```
- List tracked servers: `codex-mcp-wrapper serve list`
- Stop by port: `codex-mcp-wrapper serve stop 4105`

## Inspecting Results
- Mission artifacts and run metadata: `state/missions/<mission_id>/`
- Worker-side streams from Codex/MCP (codex events + MCP logs): `state/logs/worker-<label>.log`
- Trace/error per task (when failures occur): `state/missions/<mission_id>/task-<n>-trace.log` and `task-<n>-error.log`

## Troubleshooting Tips
- **Address already in use**: a server is already running on that port; use `serve list` then `serve stop --port <port>` before restarting.
- **Timeouts with Codex output visible**: check worker logs and per-task trace/error files to confirm whether the MCP `tools/call` response finished.
- **Auth issues**: ensure `~/.codex/auth.json` exists before starting; the wrapper copies it into each worker’s `CODEX_HOME`.
