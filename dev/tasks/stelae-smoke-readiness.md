# Task: Stelae smoke readiness (catalog hygiene · harness reliability · Codex orchestration)

Related requirements: consolidated from
`archive/e2e-clone-smoke-test.md`, `archive/clone-smoke-harness-stability.md`, `archive/stelae-tool-aggregation-visibility.md`, `archive/stelae-mcp-catalog-consistency.md`, and `archive/codex-manage-stelae-smoke.md`.

Tags: `#infra`, `#tests`, `#docs`

> This workbook now tracks every open item for the clone smoke initiative. The
> legacy task files listed above are archived and point back here so all notes,
> checklists, and run logs live in one place.
>
> **Note:** The legacy Docy fetch stack has been removed from the repo; any historical references are retained here only for context while the vendor-neutral `documentation_catalog` aggregate comes online.
>
> **Doc boundary:** This file is the engineering planning log for smoke readiness.
> The canonical runbook/architecture reference lives in `docs/e2e_clone_smoke_test.md`.
> Keep low-level instructions there and record action items + evidence here.

## Scope & checkpoints

| Stream | Goal | Status |
| --- | --- | --- |
| Catalog hygiene | Keep the published manifest limited to curated aggregate tools, dedupe schemas, and capture Codex catalog regressions in the harness. Intended catalog is now the default proxy input; the harness always runs with that flag so legacy fallbacks are only exercised manually via `scripts/run_restart_stelae.sh --legacy-catalog`. | `[~]` (`workspace_fs_read` JSON parsing gap still unresolved) |
| Harness + restart reliability | `scripts/run_e2e_clone_smoke_test.py` finishes clone → bundle → render → restart → Codex stages with bounded retries and diagnostics while keeping git clean. Env bootstraps now run through `scripts/setup_env.py` so `${STELAE_ENV_FILE}` lives under `${STELAE_CONFIG_HOME}` and the harness no longer writes repo-local `.env` files directly. | `[~]` (port preflight + restart probes landed, Codex stage timeouts under investigation) |
| Codex orchestration | `codex exec --json --full-auto` drives the golden-path `manage_stelae` scenario end-to-end (discover → install → remove) without any MCP wrapper entry point, and the harness captures every transcript. | `[~]` (Stage prompts + CLI automation landed; catalog consistency still blocks “tool missing” flakes.) |

## Active checklist

> For all checklist items, find the relevant workstream and ensure the work is carried out as part of it's setup. This includes performing any pre-reading and adding documentation to the appropriate places.

- [x] Prerequisite – restore `workspace_fs_read` coverage by ensuring the filesystem server/bundle entries are installed and exposed through the proxy (aggregator currently fails with `Unknown tool: read_file`). *2025-11-19 agent fix: tool aggregator now pins each workspace FS/Shell aggregation to its downstream server, so the proxy always routes calls through `fs`/`sh` even when base tools are hidden or renamed; Appendix B captures the downstream tool matrix.*
- [ ] Trials – Codex CLI harness runs (`codex exec --json --full-auto`) prove `workspace_fs_read` and `manage_stelae` register and complete without manual prompts while the documentation catalog work remains in flight. (Per the smoke-test guards, don’t “fix” regressions by editing stack sources—treat `docs/e2e_clone_smoke_test.md` as the runbook, reproduce failures via the harness, and capture the required transcripts/logs for Appendix C.)
- [ ] Harness reliability – capture a “restart succeeds under 120 s” run with `--capture-debug-tools` enabled and attach the resulting snapshots under `dev/logs/harness/`.
- [ ] Codex orchestration – rerun the full golden path (discover → dry-run install → real install → remove) after catalog fixes land and archive the transcripts under `dev/logs/harness/`.
- [ ] Intended catalog soak – now that the harness always exports `STELAE_USE_INTENDED_CATALOG=1`, record two consecutive green runs (plus at least one PM2 environment using the flag) so we can retire any lingering legacy-only docs. Capture the timestamp, workspace, and log bundle for Appendix C.
- [ ] Docs/tests – README, `docs/ARCHITECTURE.md`, and `docs/e2e_clone_smoke_test.md` now reference this consolidated task and document the overlay + harness expectations (✅ Action Plan #3).
- [ ] Documentation catalog aggregate – ensure the forthcoming replacement stays schema-compliant so Codex no longer sees “Output validation error … is not of type 'object'.”
- [ ] Automate harness dependency bootstrap so sandbox `python-site/` always has `httpx`, `anyio`, `mcp`, `fastmcp`, `trio`, etc., before pytest runs (or run tests inside the prepared venv).
- [ ] Preserve Codex evidence when the harness deletes workspaces (copy `codex-transcripts/*.jsonl` into `dev/logs/harness/` before cleanup so transcripts survive like the debug logs).
- [ ] Follow-up – once the soak criteria are met, execute the intended-catalog plan cleanup (task 8 in `dev/tasks/intended-catalog-plan-enhanced.md`) to stop auto-populating aggregates into `tool_overrides.json` and document the removal of the legacy path.

## Workstreams

### Catalog hygiene

- **Goals:** enforce a curated manifest (`documentation_catalog`, `workspace_fs_*`, `manage_stelae`, etc.), dedupe JSON Schema arrays before they hit Codex, and make the harness fail fast whenever Codex falls back to stale manifests. `STELAE_USE_INTENDED_CATALOG=1` is now the default, so catalog hygiene work must keep both the intended snapshot and live runtime in sync (legacy overrides exist only for emergency rollback via `--legacy-catalog`).
- **What’s done:**
  - `scripts/process_tool_aggregations.py --scope local` now renders aggregates into `${STELAE_CONFIG_HOME}` first, guaranteeing tracked templates stay slim and local overrides remain authoritative.
  - `ToolOverridesStore` dedupes `enum`/`required` arrays so rerunning renders can’t corrupt schemas (`tests/test_tool_aggregations.py::test_aggregation_runtime_dedupes_and_hides` + `tests/test_streamable_mcp.py::test_rendered_manifest_contains_only_aggregates` cover this).
  - FastMCP bridge passes downstream payloads verbatim through `PassthroughFuncMetadata`, preventing aggregator schema mismatches and enabling `STELAE_STREAMABLE_DEBUG_*` logging.
- **Still open:**
  - Trials that prove Codex naturally lists `workspace_fs_read` and `manage_stelae` without hard-coded prompts. Capture successes/failures via `codex-transcripts/*.jsonl` + mirrored tool-debug logs. *(See Appendix B for the current Codex CLI smoke baseline.)*
  - Confirm `scripts/run_e2e_clone_smoke_test.py` (intended catalog only) remains green so every automation run validates the consolidated catalog path now that the legacy fallback has been removed from the harness.
    - 2025‑11‑13 manual bundle-tools repro (workspace `/tmp/stelae-smoke-investigation`, artifacts `dev/logs/harness/20251113-204753-{bundle-tools.jsonl,streamable_tool_debug.log,tool_aggregator_debug.log}`) – Codex still cannot call `tools/list` directly and kept probing `mcp__stelae__strata_ops_suite` (`call_action`, `discover_server_actions`) until it gave up (`Server 'tools' not found or not connected`). When it moved on, `workspace_fs_read` returned well-formed JSON for `/tmp/stelae-smoke-investigation/client-repo/README.md`, `grep` reported the expected “No matches found,” and the now-retired documentation fetch aggregate returned an empty array. The remaining regression is `documentation_catalog.list_sources`: Codex still records “Output validation error … is not of type 'object'” because the proxy emits a JSON blob encoded as a string pointing at the documentation sources config file. Hypothesis check: this confirms the manifest drift is specifically about discovery (`tools/list`) while `workspace_fs_read` itself is healthy in this workspace.
    - 2025‑11‑14 automated rerun: pointing `.env` `PYTHON`/`SHIM_PYTHON` at `~/.venvs/stelae-bridge/bin/python` let `tool_aggregator_server.py` + `stelae_integrator_server.py` register (`tools/list` via curl now advertises 10 tools, matching the aggregate set). However, the harness’ pytest stage exposed more missing deps for `/usr/bin/python3` (`httpx`, `anyio`, `mcp`, `fastmcp`, `trio`); installing them into `python-site/` allowed the run to finish, but the workspace was auto-cleaned at the end so `codex-transcripts/*.jsonl` were removed (only `dev/logs/harness/20251114-100152-bundle-tools-streamable_tool_debug.log` remained in-repo). Follow-up: make the dependency bootstrap automatic and copy transcripts before cleanup so we keep evidence even when the workspace is wiped.
    - Follow-up analysis (same workspace) shows the proxy itself only lists `grep` because every other tool is disabled in `tool_overrides.json` unless the aggregate/management servers connect. Runtime overrides in `/tmp/stelae-smoke-investigation/config-home/.state/tool_overrides.json` contain the expected aggregate entries (`workspace_fs_read`, `documentation_catalog`, etc.), but both stdio helpers fail to start: `tool_aggregator_server.py` exits with `ModuleNotFoundError: No module named 'httpx'` and `stelae_integrator_server.py` exits with `ModuleNotFoundError: No module named 'mcp'` when invoked with the current `.env` (`PYTHON=/usr/bin/python3`). Because pm2 launches the proxy with that interpreter, neither aggregated tool nor `manage_stelae` registers, so Codex’s `tools/list` request legitimately returns only `grep`. Fix direction: either point `PYTHON` at a venv that already has `fastmcp`/`httpx` (`~/.venvs/stelae-bridge/bin/python`) or install the dependencies into the system interpreter before rerendering/restarting.
  - Update docs/README with the precise “overlay workflow & guardrails” so contributors re-run `process_tool_aggregations.py --scope default`, `process_tool_aggregations.py --scope local`, `make render-proxy`, and `pytest tests/test_repo_sanitized.py` after editing tracked templates. *(This change landed as part of Action Plan #3.)*
  - Maintain the `dev/logs/harness/*-streamable-tool-debug.log` snapshots for every harness run until `workspace_fs_read` JSON errors disappear. *(2025‑11‑13 snapshot above contains only a sentinel message because `codex exec` spoke directly to the HTTP proxy—`stelae-bridge` never received traffic, so no FastMCP payloads were written; the matching `tool_aggregator_debug.log` copy captures the same “not invoked” note.)*
  - Keep `docs/ARCHITECTURE.md`’s “Catalog Aggregation & Overrides” diagram synchronized with this pipeline. Anytime we change the code that shapes the flow (e.g., `scripts/process_tool_aggregations.py`, `ToolOverridesStore`, `render_proxy_config.py`, the Go proxy catalog builders, or `scripts/tool_aggregator_server.py`), update the diagram as part of this workstream so future diagnostics rely on an accurate map.

### Harness + restart reliability

- **Goals:** bundle install + render + restart finish in <60 s with actionable logs when they do not, randomized ports never collide with a developer’s long-lived proxy, and the harness exits (with diagnostics) whenever pm2 or downstream tools wedge.
- **What’s done:**
  - Restart helper now performs backoff probes against the JSON-RPC `initialize` call, logs the payload that finally passes, and prints the last HTTP status/body on failure.
  - Harness exposes `--restart-timeout`, `--restart-retries`, and `--heartbeat-timeout` so long stalls terminate with pm2 log tails plus `pm2 status` snapshots.
  - Port preflight kills lingering listeners on the chosen `PROXY_PORT` before pm2 starts, then re-validates that the port is clear.
  - Disposable `python-site/` bootstrap ensures `pytest` installs inside the sandbox via `pip --target` even when the host exporter enforces `PIP_REQUIRE_VIRTUALENV`.
  - Debug flags (`--capture-debug-tools`) mirror FastMCP/tool-aggregator logs into both `${WORKSPACE}/logs/` and `dev/logs/harness/` so evidence survives workspace cleanup.
- **Still open:**
  - Diagnose why Codex bundle stages still hit outer timeouts (see Appendix A: 2025‑02‑14 session). Need a reproducible JSONL transcript that demonstrates either `codex exec` stalling or the stack failing to stream responses.
  - Add guardrail tests around `probe_jsonrpc_initialize` and heartbeat timeouts (`tests/test_streamable_mcp.py` follow-up) once the manifest regression is covered.

### Codex orchestration

- **Goals:** Codex CLI (invoked via `codex exec --json --full-auto`) completes `discover → install (dry-run + real) → reconciler/remove` using only the standard CLI entry point while the harness validates catalog state and git cleanliness.
- **What’s done:**
  - `stelae_lib/integrator/catalog_overrides.py` hydrates descriptors (stdio command/env placeholders) during discovery, so installs pass schema validation.
  - FastMCP bridge handles `manage_stelae` locally, so proxy restarts during install/remove no longer sever Codex calls mid-flight.
  - Harness bundle stage script forces Codex to issue `workspace_fs_read`, `grep`, and `documentation_catalog` even when the catalog omits them, producing actionable failures instead of silent skips.
- **Still open:**
  - Track the golden-path CLI instructions, prerequisites, and verification steps in one place (see Appendix B) and keep that section updated whenever we change the scripted `codex exec` prompts.
  - Automation must archive `codex-transcripts/<stage>.jsonl` plus the mirrored debug logs for every CI/manual run so catalog regressions are obvious.
  - Once catalog hygiene stickiness is verified, add a nightly (or on-demand) harness run that uploads transcripts + `logs/streamable_tool_debug.log` as artifacts.

### Automation guardrails

- **Goals:** Bake the renderer/harness guardrails directly into automation so clone runs fail fast when manifests drift or restarts regress, and capture routine smoke artifacts without manual babysitting.
- **Recommended order:** (1) land the manifest/backoff/heartbeat tests so failures show up locally, (2) add the recurring harness run + artifact upload to keep telemetry fresh.
- **Planned work:**
  - [ ] **Preread:** `README.md` (Troubleshooting), `docs/ARCHITECTURE.md` (Catalog Aggregation & Overrides), `tests/test_repo_sanitized.py`, and `docs/e2e_clone_smoke_test.md` (Validation + Feedback) to align test design with published expectations.
  - [ ] Extend `tests/test_repo_sanitized.py` (or add a sibling test) to load a rendered manifest snapshot and assert aggregate names + schema dedupe, plus add unit coverage for `probe_jsonrpc_initialize`/heartbeat timeouts so restart regressions surface without running the full harness.
  - [ ] Schedule (or at least document) a nightly/on-demand clone-harness run that archives `codex-transcripts` and `logs/streamable_tool_debug.log` artifacts, using the existing per-stage log mirroring to simplify uploads.

### Follow-ups

- [ ] Interpreter portability – decide on a portable way to provide `fastmcp` + `httpx` for `tool_aggregator_server.py` / `stelae_integrator_server.py` (e.g., ship a venv, add a requirements installer, or relax the dependency to system packages) so `.env.example` can go back to a generic value without breaking fresh installs.

## References

- Harness code: `scripts/run_e2e_clone_smoke_test.py`, `stelae_lib/smoke_harness.py`, `scripts/run_restart_stelae.sh`.
- FastMCP bridge + aggregator: `scripts/stelae_streamable_mcp.py`, `stelae_lib/integrator/tool_aggregations.py`, `scripts/process_tool_aggregations.py`.
- Integrator flow: `scripts/stelae_integrator_server.py`, `stelae_lib/integrator/catalog_overrides.py`.
- Tests: `tests/test_streamable_mcp.py`, `tests/test_tool_aggregations.py`, `tests/test_codex_exec_transcript.py`, `tests/test_e2e_clone_smoke.py`.
- Docs: `docs/e2e_clone_smoke_test.md`, `README.md`, `docs/ARCHITECTURE.md`.

## Appendices (historical logbook)

### Appendix A – Selected harness sessions

#### 2025‑02‑14 · Restart stall deep dive

- *(Historical)* `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/0.1.0 --manual-stage install`
  - Hit the outer timeout while `run_restart_stelae.sh` waited for pm2. Workspace `/tmp/stelae-smoke-workspace-ibh51q3l` retained with `harness.log`.
  - pm2 logs: repeated `Error: write EPIPE` followed by `Failed to start server: listen tcp :9090: bind: address already in use`.
  - Harness selected randomized proxy port (`:22831`) but `mcp-proxy` still booted on `:9090`. Root cause: rendered `proxy.json` still hardcoded the default port (tracked template lacked `{{PROXY_PORT}}`), so pm2 ignored the sandbox value.
- Key findings:
  - `CloneSmokeHarness.__init__` correctly exports `PROXY_PORT`; restart script honors it for port-kill and readiness probes.
  - `ecosystem.config.js` + `config/proxy.template.json` must template `PROXY_PORT`; otherwise pm2 keeps binding to `:9090`. Renderer now patches this path, but older workspaces require regeneration.

#### 2025‑11‑12 · Pytest bootstrap + manual install checkpoint

1. *(Historical)* `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py … --manual-stage install --bootstrap-only` warmed workspace in ~6 s (starter bundle installed, pm2 home seeded).
2. *(Historical)* `timeout 120s python3 scripts/run_e2e_clone_smoke_test.py … --manual-stage install --skip-bootstrap --reuse-workspace`
   - Restart succeeded; `/mcp` probe passed; structural pytest failed because pip refused to install outside a venv. Fix: set `PIP_REQUIRE_VIRTUALENV=0` during sandbox installs and target `python-site/`.
3. Post-fix validation run reused cached install; manual assets regenerated; harness hit outer timeout while `codex exec … bundle-tools` was running—no transcript captured.
4. Extended timeout (300 s) produced identical outcome: Codex stage still running when timeout fired; restart + pytest pieces solid.

Follow-ups: profile `codex exec --json … bundle-tools`, capture raw JSONL output, and determine whether Codex or the proxy stalls. Artifacts live under `/tmp/stelae-smoke-workspace-dev3/`.

### Appendix B – Codex CLI smoke (`manage_stelae`)

Scenario: prove Codex CLI can drive `discover → install → remove` solely via `stelae.manage_stelae`.

- **Prereqs:** source virtualenv + `~/.nvm/nvm.sh`, run `python scripts/bootstrap_one_mcp.py`, ensure stack healthy (`make render-proxy && make restart-proxy` or `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --full`), launch Codex CLI profile.
- **Golden path:**
  1. `discover_servers` with `dry_run=true` (query “vector search”, tags `["search"]`, limit `5`). Expect descriptors + `files_updated[0].dryRun=true`.
  2. Dry-run `install_server` using one of the returned names; expect diff-only response.
  3. Real `install_server` streams logs while running `make render-proxy` + restart helper, then waits for proxy readiness.
  4. Optional `run_reconciler` or `remove_server` to verify cleanup.
- **Verification:** `make discover-servers` parity, `scripts/stelae_integrator_server.py --cli --operation list_discovered_servers`, curl manifest to ensure `manage_stelae` stays published.
- **Historical notes:**
  - 2025‑11‑08: descriptors lacked launch commands; installs failed validation. Fix: catalog overrides hydrate stdio command/env placeholders.
  - Install/remove originally dropped MCP responses when the proxy restarted; 2025‑11‑10 bridge change keeps calls local so Codex sees completion even while pm2 flips.
  - Current blocker: `codex exec` occasionally stalls during bundle stages and still surfaces `workspace_fs_read` “Expecting value” even though FastMCP debug logs show valid JSON; logs mirrored via `--capture-debug-tools` until resolved.
  - 2025‑11‑19: `workspace_fs_read`, `workspace_fs_write`, and `workspace_shell_control` now declare explicit `downstreamServer` targets and the aggregator passes them through `tools/call`, eliminating the `Unknown tool: read_file` failure. Downstream suites now route as follows:
    - `workspace_fs_read` → `fs` server operations: `list_allowed_directories`, `directory_tree`, `list_directory`, `list_directory_with_sizes`, `calculate_directory_size`, `get_file_info`, `head_file`, `read_file`, `read_file_lines`, `read_text_file`, `read_media_file`, `read_multiple_media_files`, `read_multiple_text_files`, `find_duplicate_files`, `find_empty_directories`, `search_files`, `search_files_content`.
    - `workspace_fs_write` → `fs` server operations: `create_directory`, `move_file`, `edit_file`, `write_file`, `delete_file_content`, `insert_file_content`, `update_file_content`, `zip_directory`, `zip_files`, `unzip_file`.
    - `workspace_shell_control` → `sh` server operation `run_command` (selectors: `execute_command`, `change_directory`, `get_current_directory`, `get_command_history`).

### Appendix C – Clone smoke harness deliverable snapshot

- 2025-11-20T12:27Z · `make smoke SMOKE_ARGS="--capture-debug-tools --workspace /tmp/stelae-smoke-auto --force-workspace --keep-workspace --restart-timeout 120 --heartbeat-timeout 300"` · workspace `/tmp/stelae-smoke-auto` · artifacts `dev/logs/harness/20251120-122712/` – setup script auto-rescued catalog/override files, starter bundle installed cleanly, restart succeeded, and Codex bundle stage now sees `grep` + `manage_stelae` (workspace_fs_read still missing via fallback).

- 2025-11-20T11:28Z · `PATH=/home/gabri/dev/stelae/.venv/bin:$PATH python3 scripts/run_e2e_clone_smoke_test.py --capture-debug-tools --workspace /tmp/stelae-smoke-investigation --keep-workspace --reuse-workspace --skip-bootstrap --restart-timeout 90 --heartbeat-timeout 240` · workspace `/tmp/stelae-smoke-investigation` · artifacts `dev/logs/harness/20251120-113428/` – restart succeeded but catalog only exposed `fetch` + `manage_stelae` because config-home lacked `catalog/core.json`. Codex stage hit repeated `fetch` fallbacks for `tools/list`/`workspace_fs_read`/`grep` and the harness stopped at `bundle-tools`.

Operational/runbook details live in `docs/e2e_clone_smoke_test.md`. Use this appendix to
record evidence from each smoke run (timestamp, command line, workspace path, and
links to `dev/logs/harness/…` plus `codex-transcripts/…`). Keep entries ordered
chronologically so it’s obvious which runs satisfy the “Intended catalog soak” or
other checklist items.

---

For new work, update this file instead of reviving the archived task docs. Keep
appendices chronological so future contributors can see exactly what was tried, what
failed, and where to resume.
