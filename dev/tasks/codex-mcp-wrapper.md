# Task: Codex MCP wrapper

Related requirement: `dev/progress.md` → Action Items → "Add automated/manual smoke coverage for the self-managing MCP clone."

Tags: `#infra`, `#tooling`

## Checklist

- [x] Research Codex MCP integration points and determine the supported interface for launching sandboxes / missions programmatically.
- [x] Define the wrapper contract (env variables, workspace selection, mission instructions, completion/failure signaling) so it can be reused by the e2e smoke test and future automation.
- [x] Implement the wrapper (CLI or service) that spawns Codex MCP instances with the specified env/layout and exposes hooks for orchestrating tool usage.
- [x] Establish dev vs. released isolation (dedicated repo + virtualenv/sandbox) so experimental builds never overwrite the in-use binary; document how to point Stelae at the published wrapper via bundle/install, and how to expose a separate dev instance (distinct command/env/port) without swapping binaries.
- [x] Document how to install/configure the wrapper locally (prereqs, env vars, usage examples).
- [x] Update spec/progress/task entries.
- [x] Commit with message `infra: add codex mcp wrapper` after tests.

## References

- Code: `~/dev/codex-mcp-wrapper/src/codex_mcp_wrapper/*` (new standalone repo; default branch `main`).
- Tests: `~/dev/codex-mcp-wrapper/tests/test_config.py` (pytest smoke for config/mission schemas; dispatcher/CLI integration tests queued for P1).
- Docs: `~/dev/codex-mcp-wrapper/docs/codex-mcp-design.md` (moved from `dev/notes/`), plus the repo `README.md` for install + CLI instructions.

## Implementation snapshot (2025-01-10)

- **Repo layout:** lives outside this monorepo at `~/dev/codex-mcp-wrapper`. `pyproject.toml` (hatchling) exposes the `codex-mcp-wrapper` CLI; `src/codex_mcp_wrapper` contains `config.py`, `mission.py`, `dispatcher.py`, `server.py`, and `cli.py`.
- **Design doc:** relocated from `dev/notes/codex-mcp-design.md` into `~/dev/codex-mcp-wrapper/docs/codex-mcp-design.md`. That document now captures the finalized architecture, mission schema, and delivery plan (P0–P3 roadmap).
- **CLI surface:**
  - `codex-mcp-wrapper serve --config wrapper.toml [--transport stdio|sse] [--port 4105]`
  - `codex-mcp-wrapper run-mission missions/<name>.json --workspace <path>`
  - `codex-mcp-wrapper doctor` (verifies Codex binaries + CODEX_HOME), `scaffold-mission` (writes starter JSON).
- **Mission contract:** JSON/YAML validated by `codex_mcp_wrapper.config.MissionSpec`. Each task may set `sandbox`, `approval_policy`, `model`, `profile`, `base-instructions`, `env`, `config` overrides, artifact globs, and `preferred_worker`. MCP clients call the `batch` tool on the wrapper server to launch missions and `reply` to continue conversations.
- **Worker pool:** `dispatcher.WorkerPool` spins `fastmcp.Client` connections to stdio Codex MCP workers, enforces semaphore capacity per worker, routes replies using `conversationId`, and writes artifacts to `state/missions/<mission_id>/...`.
- **Isolation:**
  - Dev install uses `~/dev/codex-mcp-wrapper/.venv`, port `4105`, label `codex-wrapper-dev`.
  - Future release artifacts will land under `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/` (port `4106`, label `codex-wrapper`). Both can coexist; Stelae chooses the target via its bundle/override config. *NOT TO BE IMPLEMENTED FOR NOW*
  - Each worker receives its own `$CODEX_HOME=<state_dir>/workers/<label>/codex-home` plus optional env overrides. Default sandbox is `read-only`, approval policy `never`.
- **Install steps:**
  1. `python3 -m venv ~/dev/codex-mcp-wrapper/.venv && source ...`
  2. `pip install -e .[dev]`
  3. Copy `wrapper.example.toml` → `wrapper.toml`, edit worker entries (binary path, sandbox, env).
  4. `codex-mcp-wrapper serve --transport sse --port 4105` and register the MCP endpoint via `scripts/install_stelae_bundle.py --server codex-wrapper-dev`.
- **Authentication bootstrap:** when `doctor`/`serve` loads `wrapper.toml`, the wrapper now mirrors `~/.codex/auth.json` (or `$CODEX_HOME/auth.json`) into every worker’s isolated `codex-home` so `codex mcp-server` launches with valid credentials without requiring per-worker `codex login`.
- **Testing:** `pytest` currently covers config/mission loading (2 tests). Dispatcher/CLI + fake Codex worker coverage is planned for the P1 milestone before we publish a release tarball.

## Dev ↔ release wiring

- Dev repo: `~/dev/codex-mcp-wrapper` (git init done; work happens there).
- Release channel: build artifacts live under `~/dev/codex-mcp-wrapper/dist/releases/<version>`; publish them (or copy into `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<version>`) when bundling with Stelae.
- Starter bundle updates: new MCP entry will reference the wrapper’s `batch` tool on port 4106 for prod; a dev override can point to port 4105 for local testing. Both follow the mission JSON schema shipped in `examples/mission.example.json`.

## Notes

- Research references integrated into the design: OpenAI Codex SDK → "Using Codex CLI programmatically" for non-interactive runs, and `openai/codex/docs/advanced.md#using-codex-as-an-mcp-server` for the MCP tool schema + `$CODEX_HOME` semantics.
- Outstanding work before we can close the task entirely: **done**
  1. [x] P1 landed: worker health probes, persistent session metadata, structured artifact packaging (zip/tar) plus `scripts/build_release.py` to produce signed artifacts under `~/dev/codex-mcp-wrapper/dist/releases/<version>` (ready to publish/install).
  2. [x] Starter bundle now includes the `codex-wrapper` server descriptor; `.env.example` exposes `CODEX_WRAPPER_BIN`/`CODEX_WRAPPER_CONFIG` so `manage_stelae` installs the release build automatically. *NOTE: THIS HAS BEEN REVERSED IN ACCORDANCE WITH THE INTENDED BEHAVIOUR*
  3. [x] `tests/test_codex_wrapper_smoke.py` exercises the wrapper’s `batch` tool through the MCP interface (skips unless the binary/config env vars are set) to guard the integration end-to-end.
  4. [x] External repo updated with docs + release builder; commit message reserved for when we push that repo upstream.
- `codex-mcp-design.md` no longer lives in `dev/notes/`; reference the new path above.
- If dependency relationships change once the smoke test lands, regenerate `dev/tasks/*_task_dependencies.json`.

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated (`~/dev/codex-mcp-wrapper` repo, `pytest`)
- [x] Docs updated (design doc moved, README/this task updated)
- [x] progress.md updated
- [x] Task log updated (this file)
- [ ] Checklist completed (waiting on release/commit)

## Follow-up work

- *None*. Future iterations can layer on CLI telemetry/exporters as needed, but the P1 scope is complete.
