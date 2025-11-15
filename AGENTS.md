# Repository Guidelines

## Project Structure & Module Organization

- `scripts/` contains Python/bash automation (renderers, restart helpers, MCP servers); keep each module focused and under ~150 lines.
- `config/` stores templates (`proxy.template.json`, Cloudflare templates). Treat `.template` files as source of truth and rerender to produce runtime artifacts inside `${STELAE_STATE_HOME}` (defaults to `${STELAE_CONFIG_HOME}/.state`), keeping templates clean.
- `cloudflare/worker/` holds the manifest worker plus `wrangler.toml`. `ops/` houses operational manifests (Cloudflared templates). Diagnostics live in `dev/`, integration tests in `tests/`, logs under `logs/`, and PM2 definitions in `ecosystem.config.js`.
- The Go proxy binary resides in `~/apps/mcp-proxy`; rebuild there with `go build -o build/mcp-proxy` after proxy changes, then use this repo’s renderers to refresh configs.

## Stack Snapshot & Onboarding

- Treat the README “Stack Snapshot” table as the live roster for MCP services (proxy, Docy, aggregator, integrator, custom tools, FastMCP bridge, discovery agent, etc.); each entry lists the transport, launch command, and purpose so you can immediately verify why a server is missing from `pm2 status`.
- The shipped proxy uses the `Dub1n/mcp-proxy` fork because it exposes the `/mcp` streamable facade. Override `STELAE_PROXY_SOURCE` (or `--proxy-source`) if you need to pin a different remote, then rebuild via `go build -o build/mcp-proxy` before rerendering configs.
- Local Codex/TUI clients connect through `scripts/stelae_streamable_mcp.py`; configure `~/.codex/config.toml` so `STELAE_PROXY_BASE` points at the bare origin (`http://127.0.0.1:9090`) because the bridge appends `/mcp` internally. If the proxy handshake fails the bridge drops to the fallback `search`/`fetch` catalog, so keep the base URL clean and restart `stelae-bridge` in PM2 when debugging tool gaps.

## Runtime, Build, and Dev Commands

- Environment: run `python scripts/setup_env.py`, edit `${STELAE_ENV_FILE}` (defaults to `${STELAE_CONFIG_HOME}/.env`) to update path/binary variables, then run `make render-proxy`. Keep `${STELAE_ENV_FILE}` local; renderers inject values for PM2.
- Core stack = mcp-proxy, custom tools, the Stelae integrator, the tool aggregator helper, the 1mcp stdio agent, the public 1mcp catalog bridge, and the FastMCP bridge. The starter bundle (Docy + manager, Basic Memory, Strata, Fetch, Scrapling, filesystem/ripgrep/terminal helpers) lives in `config/bundles/starter_bundle.json`; install or update it via `python scripts/install_stelae_bundle.py [--server name...]` so the extras stay in `${STELAE_CONFIG_HOME}` overlays instead of git, and keep the Cloudflare tunnel/worker opt-in. The Codex MCP wrapper is intentionally excluded from this bundle—build the release via `~/dev/codex-mcp-wrapper/scripts/build_release.py`, copy it into `${STELAE_CONFIG_HOME}/codex-mcp-wrapper/releases/<version>`, and then run the manual `manage_stelae install_server` flow documented in `README.md` when you explicitly want the wrapper.
- Overlay workflow (docs/ARCHITECTURE.md + README): whenever you touch tracked templates or aggregations run `python scripts/process_tool_aggregations.py --scope default`, then `python scripts/process_tool_aggregations.py --scope local`, followed by `make render-proxy` and `pytest tests/test_repo_sanitized.py`; wrap up with `make verify-clean` (or `./scripts/verify_clean_repo.sh --skip-restart`) to confirm render/restart automation keeps `git status` empty. The catalog layering is actively being reworked per `dev/intended-catalog-plan.md`, so expect follow-up patches that change how `tool_overrides*.json` feed into the synthesized catalog (`intended_catalog.json` / `live_catalog.json`) and treat current commands as provisional.
- PM2 lifecycle (`source ~/.nvm/nvm.sh` first):
  - `make up` / `make down` – start or stop the fleet described in `ecosystem.config.js`.
  - `make restart-proxy`, `make logs`, `make status` – restart, tail logs, or inspect process table.
  - `make verify-clean` – run `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides` and fail if tracked files changed. Use `VERIFY_CLEAN_RESTART_ARGS` or `./scripts/verify_clean_repo.sh --skip-restart` when PM2/cloudflared aren’t available locally.
  - `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` – render, rebuild, and restart the local stack without touching Cloudflare (default flow for `manage_stelae`). Append `--full` only when you need to redeploy the tunnel/worker.
- Discovery & overrides:
  - `python scripts/discover_servers_cli.py` or the MCP tool `manage_stelae` (operations: discover/install/remove/refresh/run_reconciler) manage downstream servers.
  - `python scripts/populate_tool_overrides.py --proxy-url http://127.0.0.1:9090/mcp` snapshots schemas into `${STELAE_CONFIG_HOME}/tool_overrides.local.json` and rewrites `${TOOL_OVERRIDES_PATH}`; the restart script runs this with `--skip-populate-overrides` opt-out so schema drift never lingers between restarts. The intended/live catalog proposal may fold these steps into new artifacts (`intended_catalog.json`, `live_catalog.json`), so double-check `dev/intended-catalog-plan.md` when touching overrides or schema caches.
  - Aggregated tools come from `scripts/tool_aggregator_server.py` + `config/tool_aggregations*.json`; if `tools/list` collapses to fallback `search`/`fetch`, rerun `make restart-proxy` (or `scripts/run_restart_stelae.sh --full`) to relaunch the aggregator/stdio bridge and restore the curated catalog.
- Testing: run `pytest` from repo root; scope via `pytest tests/test_streamable_mcp.py::test_happy_path` when needed.
- Clone smoke harness: `python scripts/run_e2e_clone_smoke_test.py --wrapper-release ~/dev/codex-mcp-wrapper/dist/releases/<version>` now installs the starter bundle, seeds a Codex-friendly client repo, mirrors `~/.codex`, auto-cleans any prior `stelae-smoke-workspace-*` sandboxes, runs staged pytest/`make verify-clean`, and drives `codex exec --json` through bundle/install/remove stages while asserting `git status` stays clean. Transcripts live under `<workspace>/codex-transcripts`. Pass `--codex-cli`, `--codex-home`, `--manual` (full manual playbook), `--manual-stage <stage>` (stage-specific pause/resume), `--force-workspace`/`--reuse-workspace`, or `--cleanup-only [--workspace /path]` as needed; full details live in `docs/e2e_clone_smoke_test.md`.
- Install-stage mythology: the starter bundle + render + restart portion of the harness completes in well under a minute. Extended “timeouts” at the “Installing starter bundle…” or “Restarting stack…” logs indicate a different failure (blocked subprocess, missing env, Codex/manual orchestration) and should be debugged rather than “fixed” by increasing timeouts.
- Keep tests clone-safe: assume every pytest module and make target must pass inside a fresh clone. If a diagnostic truly requires the long-lived dev workspace, mark it explicitly (pytest marker, separate target) and document why; clone smoke automation should still exercise the rest of the suite without special casing.

## Coding Style & Naming Conventions

- Python targets 3.11+, 4-space indents, type hints, and functions under ~40 lines; split modules before ~400 lines. Enforce SOLID principles, avoid god classes, and prefer composition/injected dependencies.
- Shell scripts start with `#!/usr/bin/env bash` plus `set -euo pipefail`, using kebab-case filenames.
- JSON templates use uppercase placeholders (`{{ STELAE_DIR }}`) and never hardcode secrets. Treat derived JSON as generated artifacts.
- Follow DRY: extract reusable helpers, regression-test shared code, and lean on existing CLI tooling before creating new scripts.

## Testing Guidelines

- Framework: Pytest with files named `tests/test_<feature>.py`. Maintain ≥80% coverage for touched code, exercise happy/unhappy paths, and prefer dependency-injected fakes over editing shared fixtures.
- TDD: default for new features/infrastructure; acceptable to relax for small fixes but document any uncovered areas in your summary and wait for direction before expanding scope.
- Smoke/diagnostic helpers: use `dev/debug/check_connector.py`, `dev/debug/chatgpt_connector_probe.py`, and the SSE harness examples in `README.md` to verify manifests/search/fetch behavior.

## Commit & Pull Request Guidelines

- Commit format: `<type>: <summary>` (e.g., `docs: clarify proxy renderer usage`). Summaries should list impacted services/components and reference the exact verification commands run (`pytest`, `make render-proxy`, `manage_stelae install_server …`).
- Only commit rendered artifacts when deployment behavior changes (e.g., new template variables). PR descriptions must include: overview of changes, impacted services (proxy, Cloudflare worker, scripts, etc.), manual verification steps, linked TODO/issues, and logs/screenshots for behavioral changes.

## Security & Configuration Tips

- User-editable overlays live under `${STELAE_CONFIG_HOME}` (default `~/.config/stelae`). Automation writes runtime artifacts (`proxy.json`, merged tool overrides, tool schema status, etc.) to `${STELAE_STATE_HOME}` so git never sees machine-specific data; route any new generated files there as well. Delete a `.local.*` file to reset it to the tracked default. Run `pytest tests/test_repo_sanitized.py` before committing template changes to ensure tracked configs stay placeholder-only.
- Two-layer overlays from README: `${STELAE_CONFIG_HOME}/.env` is the editable copy, `${STELAE_CONFIG_HOME}/.env.local` holds hydrated secrets/defaults, and `${STELAE_CONFIG_HOME}/*.local.json` mirrors each tracked template (`proxy.template`, `tool_aggregations`, `tool_overrides`, etc.). Renderers merge template → overlay → runtime (`${STELAE_STATE_HOME}/proxy.json`, `${TOOL_OVERRIDES_PATH}`, `${STELAE_CONFIG_HOME}/cloudflared.yml`), so deleting a `.local` file plus rerendering always reverts to the repo defaults.
- Catalog consolidation is in flight (see `dev/intended-catalog-plan.md`): when adding new generated files prefer `${STELAE_STATE_HOME}/intended_catalog.json` or `${STELAE_STATE_HOME}/live_catalog.json` in anticipation of the new flow, and note that existing `tool_overrides*.json` handling may be replaced as the plan lands.
- Keep `${STELAE_ENV_FILE}` out of git; renderers (`scripts/render_proxy_config.py`, `scripts/render_cloudflared_config.py`) handle substitution. Regenerate Cloudflare configs via `make render-cloudflared`, store credentials under `~/.cloudflared`, and validate the public endpoint with the curl/JQ commands in `README.md`.
- Never manually edit `${PROXY_CONFIG}` (or any file under `${STELAE_STATE_HOME}`), `${STELAE_CONFIG_HOME}/cloudflared.yml`, or `${TOOL_SCHEMA_STATUS_PATH}`; rerender or let automation update them.
- Cloudflare worker expects KV data (`scripts/push_manifest_to_kv.sh`). After pushing, deploy with `npx wrangler deploy --config cloudflare/worker/wrangler.toml`.

## Operational Health & Remote Access

- Validate readiness with the README commands: `curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'`, the Cloudflare equivalent (`https://mcp.infotopology.xyz`), and `curl -skI https://mcp.infotopology.xyz/stream` for SSE reachability. Missing catalog entries usually mean the aggregator or FastMCP bridge is offline.
- Keep Cloudflare managed by PM2 (`pm2 start "cloudflared tunnel run stelae" --name cloudflared`) and restart both `mcp-proxy` and `cloudflared` after updating `.env` or proxy configs. Follow the README snippet to confirm the DNS route (`cloudflared tunnel route dns stelae mcp.infotopology.xyz`) before exposing the stack publicly.
- The SSE harness and example Python snippet in README.md exercise `/rg/sse` and `/fetch/sse`; use them (or `dev/debug/chatgpt_connector_probe.py`) whenever you need to debug streamable endpoints or verify the FastMCP bridge still exposes the full catalog.
- `scripts/stelae_streamable_mcp.py` powers desktop clients; restart the `stelae-bridge` PM2 entry if Codex only sees fallback tools or if `STELAE_PROXY_BASE` changed. Pair this with `~/.codex/config.toml` edits so Codex CLI can launch the bridge without manual exports.
- The watchdog `scripts/watch_public_mcp.py` shares the PM2 ensure logic described in README—lean on it (or replicate its steps) when monitoring the tunnel/proxy from CI machines.

## Aggregation Behavior & Tooling

- The aggregator server enforces the declarative mappings described in docs/ARCHITECTURE.md: inputs flow through `argumentMappings` (null stripping + required enforcement) and outputs through `_decode_json_like` → `_convert_content_blocks`, ensuring `structuredContent` stays as native dicts while text mirrors the payload. Keep response schemas in sync via `ToolAggregationConfig.apply_overrides()` so Codex sees the transformed tuple/text behavior.
- `manage_docy_sources` is the primary aggregated tool bundled with the repo, and it bypasses FastMCP’s schema conversion so Docy manager responses return proper `TextContent` + dict payloads. When adding new aggregates, run the overlay workflow above so `${STELAE_CONFIG_HOME}` captures the optional suites (`workspace_fs_*`, `memory_suite`, `doc_fetch_suite`, `scrapling_fetch_suite`, `strata_ops_suite`) without mutating tracked JSON.
- If new generators or discovery runs create files, write them to `${STELAE_STATE_HOME}` (runtime artifacts) or `${STELAE_CONFIG_HOME}` (human-edited overlays) and never directly to tracked templates; tearing down the `.local` variant should always reset to the repo defaults. The intended/live catalog proposal means aggregated descriptors may soon be sourced from `intended_catalog.json` rather than the current runtime overrides—flag any assumptions about catalog persistence when modifying these flows.

## Agent Workflow & Communication

- **Command Tool**: default to `["bash","-lc","…"]` for terminal operations; switch shells only when explicitly required.
- **MCP Invocation**: never assume the manifest is authoritative. Always attempt the requested MCP tool (e.g., `stelae.manage_stelae`) even if it is absent from the prompt roster, and report the exact response or error instead of substituting other mechanisms.
- **Placeholders & Mocks**: avoid introducing placeholders/mocks unless the user explicitly asks for them.
- **DRY & Modular Design**: remove duplicate logic via helpers, keep modules interchangeable, and respect manager/coordinator patterns (e.g., keep business logic out of view models).
- **TDD & Coverage**: prefer tests first, maintain ≥80% coverage, and document missing tests when encountered.
- **SOLID + Warning Signs**: watch for behavior-flipping booleans, deep inheritance, or parameter-heavy methods; refactor toward cohesive interfaces.
- **Communication**: respond concisely, mirror the user’s tone, surface risks/assumptions, and propose natural follow-up work (tests/docs) when it reinforces the change. If tooling prevents edits after three attempts, share the intended diff in chat and ask for manual application.
