# Task: Automate 1mcp Discovery → Stelae Stack Integration

Related requirement: `dev/progress.md` → Requirement Group A → “Hook 1mcp discovery into the stack so newly found servers auto-merge into config + overrides”.

Tags: `#automation`, `#infra`, `#mcp`

## Goal

Ship a single MCP server (`stelae-integrator`, exposing one `manage_stelae` tool) that can turn 1mcp discovery output into a fully wired Stelae configuration. Instead of registering many tiny tools, this server accepts an `operation` enum and delegates internally, keeping the manifest lean while still enabling rich automation. After discover→install, the new downstream server should:

- be present in `config/proxy.template.json` with the right transport/args/env;
- have `config/tool_overrides.json` seeded with default tool names/descriptions (leveraging the override pre-population task);
- trigger render + restart (`make render-proxy`, `scripts/run_restart_stelae.sh --full`), republishing the manifest;
- return a report so operators know what changed.

The workflow should also cover manual JSON blobs and provide guardrails (dry-run, validation, failure recovery). This supersedes the earlier “override automation” task; that functionality becomes a sub-step here (with a fallback CLI in case someone adds servers manually).

## Checklist

- [x] Define the interface for discovery ingestion (JSON schema sourced from 1mcp, stored under `${STELAE_DISCOVERY_PATH}`).
- [x] Implement the MCP server:
  - Expose a single tool, `manage_stelae`, with an `operation` enum (`list_discovered_servers`, `install_server`, `refresh_discovery`, `run_reconciler`, etc.) and operation-specific `params` validated via a discriminated union schema.
  - Optional operations cover `remove_server`, `dry_run_install`, or future reconciler automation.
- [x] Normalise discovery descriptors:
  - Map transports (`stdio`, `http`, `streamable-http`).
  - Capture command/args/env or URL headers.
  - Persist display metadata for overrides (`description`, upstream repo).
- [x] Update `config/proxy.template.json` programmatically:
  - Merge entries alphabetically to keep diffs neat.
  - Ensure `.env` keys exist and binaries are resolvable; surface actionable errors.
- [x] Seed `config/tool_overrides.json` for new tools:
  - Reuse the “prepopulate defaults” logic now implemented by `scripts/populate_tool_overrides.py`.
  - Provide a command-line fallback (e.g., `scripts/populate_tool_overrides.py --servers <name> --dry-run`) in case servers are added manually or discovery is disabled.
- [x] Execute `make render-proxy` and `scripts/run_restart_stelae.sh --full` inside the tool, streaming logs and catching failures (fail fast with clear messaging).
- [x] Add regression tests:
  - Unit tests for config merge/sanitisation.
  - Integration test spinning the MCP server in-process (simulate discovery JSON → verify config edits + restart command invocation via mock).
- [x] Document the workflow:
  - README section (“Installing servers discovered by 1mcp”).
  - Task instructions referencing how this replaces `override-automation`.
  - Notes on dry-run, auth handling, and failure fallbacks.
- [x] Update progress tracker/task log once the automation lands.

## Implementation Notes

### Discovery Cache

- Expect 1mcp to write `${STELAE_DISCOVERY_PATH}` (one array of entries).
- Each entry should include: `name`, `transport`, `command` or `url`, optional `args`, `env`, `description`, `source` (Git repo / manifest URL), `tools` (names/descriptions if known), `requiresAuth` flag.
- The integrator should gracefully handle missing fields and mark entries as “incomplete”.

### Config Update Workflow

1. Load discovery cache → validate selected entry.
2. Update template:
   - For stdio, set `type: "stdio"` and fill `command` & `args`.
   - For HTTP/streamable servers, set `type: "http"` or `"streamable-http"` and the endpoint URL/headers.
   - Allow optional `options` block (panicIfInvalid/logEnabled/toolFilter/authTokens).
3. Update overrides:
   - Insert master-level entries for each exposed tool if not present, using discovered descriptions.
   - Preserve `servers.*` blocks for per-server hints.
4. Persist files (ensure trailing newline, sorted keys to minimise churn).
5. Run render + restart; capture output for the user.
6. Return a JSON response with `status`, `files_updated`, `commands_run`, and any warnings.

### Guardrails & Recovery

- Support `dryRun` → emit proposed diffs (maybe via unified diff) without applying.
- Detect existing entries: if a server already exists, either skip, update, or prompt the caller (configurable) and report that state in the JSON response.
- Validate binaries via `shutil.which` (Python) or `os.stat`; if missing, abort with instructions.
- If restart fails, surface the error, include captured stdout/stderr, and return the commands the user can run manually.
- Provide a CLI alias (e.g., `python -m stelae_integrator --operation install_server --dry-run`) that reuses the same dispatcher for non-MCP flows (CI, manual maintenance).

### Admin Tool Schema & Dispatch

- **Input schema:** top-level object with `operation` (enum) and optional `params`. Use `oneOf` on `params`, keyed by `operation`, so `list_discovered_servers` needs no extra fields, `install_server` requires `slug` or full descriptor, `run_reconciler` requires `capability` + `target`, etc.
- **Output schema:** consistent envelope containing `status`, `details`, `files_updated`, `commands_run`, `warnings`, and `errors`. Every operation returns the same envelope so clients can parse results uniformly.
- **Dispatch:** map each `operation` to a helper inside the server. Helpers call the shared libraries this task introduces (config merge, overrides seeding, restart orchestration, reconciler integration, 1mcp discovery) rather than shelling out unless necessary. Centralise locking, dry-run diffing, and logging in the dispatcher to keep behavior identical whether invoked via MCP or CLI.

### Reference: Documentation Catalog Pattern

- The documentation source manager demonstrates the per-server approach: keep a declarative JSON catalog under `config/`, render any generated artifacts via a Python renderer, and expose a single MCP/CLI tool with an `operation` enum for list/add/remove/sync tasks.
- Reuse that pattern for the integrator: treat each managed surface (documentation catalog, custom tools, discovered servers) as data + renderer combos, and have the MCP tool orchestrate updates plus any follow-up commands (renderers, restarts) while keeping manifests free of extra tool entries.

### Testing Strategy

- Unit tests for JSON merge functions (no file I/O, pure data transforms).
- Mock-based tests for subprocess invocation (ensure correct command order & args).
- End-to-end test using a temp workspace: write a discovery stub, run `install_server`, assert config + overrides + manifest outputs updated.
- Harness should avoid hitting real binaries; use environment variables to point to fixture scripts.

### Rollout Steps

1. Implement and test the MCP server + CLI helpers.
2. Document usage and add task log entry.
3. Update `make render-proxy` / `run_restart_stelae.sh` docs to mention the new automation.
4. Consider adding a `make install-server NAME=...` wrapper that calls the MCP tool for non-agent workflows.

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] Progress tracker updated
- [x] Task log updated
- [x] Checklist completed

## Status

- `scripts/stelae_integrator_server.py` exposes the `manage_stelae` MCP/CLI tool backed by `stelae_lib.integrator.*` helpers (discovery store, proxy template merger, tool override seeder, command runner).
- Discovery descriptors now live in `${STELAE_DISCOVERY_PATH}`; installs validate transports, binaries, and `.env` placeholders before editing templates.
- The integrator seeds overrides, writes sorted template entries, and reruns `make render-proxy` + `scripts/run_restart_stelae.sh --full`, returning diffs and command transcripts (with dry-run previews).
- Regression coverage: `tests/test_stelae_integrator.py` exercises list/install/remove/refresh flows plus the mock command runner.
- README + `docs/ARCHITECTURE.md` describe the workflow (“Installing servers discovered by 1mcp” + “Discovery & Auto-Loading Pipeline”), and `dev/progress.md` marks the requirement complete.

## Follow-on Tasks

- [x] **Managed 1mcp discovery operation** – `discover_servers` now lives inside `StelaeIntegratorService`, feeds `details.servers[*].descriptor`, and has regression coverage in `tests/test_stelae_integrator.py`.
- [x] **Self-contained 1mcp bootstrap** – `scripts/bootstrap_one_mcp.py` clones/syncs `~/apps/vendor/1mcpserver`, seeds `${STELAE_DISCOVERY_PATH}`, and writes `~/.config/1mcp/mcp.json`. README documents the workflow.
- [x] **CI/automation hooks** – `make discover-servers` shells into `scripts/discover_servers_cli.py`, allowing env-driven queries (`DISCOVER_QUERY`, `DISCOVER_TAGS`, etc.) without leaving the terminal. The target doubles as the dry-run smoke test when you set `DISCOVER_DRY_RUN=1`.
- [x] **Codex CLI end-to-end smoke test** – `dev/tasks/stelae-smoke-readiness.md#codex-orchestration` captures the full golden path (discover → dry-run install → install → reconciler) with ready-to-paste payloads plus validation commands (`curl` + CLI fallbacks).

## Progress Report 1 (2025-11-08)

### 1. What’s done

- `StelaeIntegratorService` now exposes `run()` so MCP + CLI callers share the same structured responses and error envelopes.
- Restart orchestration runs `make render-proxy` followed by `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`, capturing command transcripts and blocking on a JSON-RPC `tools/list` probe to avoid disconnecting Codex mid-install.
- Discovery/search UX now accepts `tags`, `preset`, `limit`, `min_score`, and returns a single response containing both the catalog delta and the install-ready descriptors (`details.servers[*]`), eliminating the “discover → list” shuffle.
- README + docs updated to highlight the enforced `stelae.manage_stelae` payload, restart flags, and the new smoke-test flow; `tests/test_stelae_integrator.py` expanded with readiness/diff coverage (`PYTHONPATH=. .venv/bin/pytest tests/test_stelae_integrator.py`).
- The streamable bridge injects a synthetic `manage_stelae` tool into `tools/list` and routes invocations through the integrator service using `asyncio.to_thread`, so local connectors can stay in-band.

### 1. Status review (2025-11-10)

- ✅ The Go proxy once again publishes `manage_stelae`. `config/tool_schema_status.json:17-26` now records healthy call-path telemetry for `integrator.manage_stelae`, and `README.md:182-205` documents that the tool is advertised in the manifest after restarts.
- ✅ Codex smoke testing against the public endpoint now succeeds; see the updated transcript in `dev/tasks/stelae-smoke-readiness.md#appendix-b--codex-cli-smoke-manage_stelae` and the verification commands that hit both localhost and `https://mcp.infotopology.xyz/mcp`.
- ✅ The local bridge smoke test uses the SSE flow implemented in `dev/debug/chatgpt_connector_probe.py:1-135`, eliminating the previous 400/406 errors.
- ✅ `discover_servers` has integration coverage (`tests/test_stelae_integrator.py:147-214`) that exercises append/overwrite, catalog hydration, and qdrant overrides rather than relying only on dry-run paths.
- ✅ `scripts/run_restart_stelae.sh --no-bridge --full` was re-run end-to-end on `2025-11-09T01:23:21Z`. The helper rebuilt `~/apps/mcp-proxy`, rewrote `config/proxy.json`, restarted pm2 (cloudflared + watchdog + mcp-proxy), republished the Cloudflare worker, and verified both the local JSON-RPC probe and the public manifest (`https://mcp.infotopology.xyz/.well-known/mcp/manifest.json`).

## Progress Report 2 (2025-11-09)

### 2. What’s done

- Added `scripts/bootstrap_one_mcp.py` so new checkouts can clone/sync the vendored repo, seed the discovery cache, and emit `~/.config/1mcp/mcp.json` without hand-editing upstream files. README now references the workflow and sample config.
- Introduced `scripts/discover_servers_cli.py` plus the `make discover-servers` target. Operators can drive `discover_servers` from the terminal via env knobs (`DISCOVER_QUERY`, `DISCOVER_LIMIT`, `DISCOVER_DRY_RUN`, etc.), which doubles as the CLI smoke test.
- Authored the Codex CLI golden path now preserved under `dev/tasks/stelae-smoke-readiness.md#codex-orchestration`, capturing the payloads plus validation commands requested in item 4.5.

### 2. Next up

- Fold the new restart transcript into `dev/tasks/stelae-smoke-readiness.md#codex-orchestration` (tool counts + server names) so the Codex checklist references a known-good run.
- Decide whether we need a `--keep-pm2` safe path that doesn’t depend on pm2 residual state (the recent run required letting the script own pm2 entirely).

### 2. Next session checklist

1. Update the Codex smoke log with the restart verification notes and final server names.
2. Evaluate if `scripts/run_restart_stelae.sh` needs a friendlier fallback for hosts where pm2 refuses to restart stopped apps when `--keep-pm2` is set.

### 2. Follow-ups logged 2025-11-10

- [x] **Restart helper observability polish** – `ensure_pm2_app` now prints single-line summaries such as `status=absent -> start` or `status=errored -> delete+start`, so Codex transcripts record how each pm2 app was recovered.
- [x] **Watchdog self-healing parity** – `scripts/watch_public_mcp.py` reuses the same pm2 inspection logic (with the matching log format) to delete+start missing Cloudflared processes instead of looping on `pm2 restart`.
