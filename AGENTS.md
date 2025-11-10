# Repository Guidelines

## Project Structure & Module Organization

- `scripts/` contains Python/bash automation (renderers, restart helpers, MCP servers); keep each module focused and under ~150 lines.
- `config/` stores templates (`proxy.template.json`, Cloudflare templates) and runtime data (`tool_overrides.json`, `discovered_servers.json`). Treat `.template` files as source of truth and rerender to produce `config/proxy.json` or `ops/cloudflared.yml`.
- `cloudflare/worker/` holds the manifest worker plus `wrangler.toml`. `ops/` houses operational manifests (Cloudflared templates). Diagnostics live in `dev/`, integration tests in `tests/`, logs under `logs/`, and PM2 definitions in `ecosystem.config.js`.
- The Go proxy binary resides in `~/apps/mcp-proxy`; rebuild there with `go build -o build/mcp-proxy` after proxy changes, then use this repo’s renderers to refresh configs.

## Runtime, Build, and Dev Commands

- Environment: copy `.env.example` → `.env`, update path/binary variables, then run `make render-proxy`. Keep `.env` local; renderers inject values for PM2.
- Core stack = mcp-proxy, filesystem/ripgrep controllers, the terminal controller, custom tools, the Stelae integrator, and the FastMCP bridge. The starter bundle (Docy + manager, tool aggregator, Basic Memory, Strata, Fetch, Scrapling, the 1mcp catalog helpers) lives in `config/bundles/starter_bundle.json`; install or update it via `python scripts/install_stelae_bundle.py [--server name...]` so the extras stay in `${STELAE_CONFIG_HOME}` overlays instead of git, and keep the Cloudflare tunnel/worker opt-in.
- PM2 lifecycle (`source ~/.nvm/nvm.sh` first):
  - `make up` / `make down` – start or stop the fleet described in `ecosystem.config.js`.
  - `make restart-proxy`, `make logs`, `make status` – restart, tail logs, or inspect process table.
  - `make verify-clean` – run `make render-proxy` plus `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides` and fail if tracked files changed. Use `VERIFY_CLEAN_RESTART_ARGS` or `./scripts/verify_clean_repo.sh --skip-restart` when PM2/cloudflared aren’t available locally.
  - `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` – render, rebuild, and restart the local stack without touching Cloudflare (default flow for `manage_stelae`). Append `--full` only when you need to redeploy the tunnel/worker.
- Discovery & overrides:
  - `python scripts/discover_servers_cli.py` or the MCP tool `manage_stelae` (operations: discover/install/remove/refresh/run_reconciler) manage downstream servers.
  - `python scripts/populate_tool_overrides.py --proxy-url http://127.0.0.1:9090/mcp` snapshots schemas into `${STELAE_CONFIG_HOME}/config/tool_overrides.local.json` and rewrites `${TOOL_OVERRIDES_PATH}`.
- Testing: run `pytest` from repo root; scope via `pytest tests/test_streamable_mcp.py::test_happy_path` when needed.

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

- All generated artifacts and local overrides live under `${STELAE_CONFIG_HOME}` (default `~/.config/stelae`). Automation writes `proxy.json`, merged tool overrides, discovery caches, tool schema status, and your `*.local.*` templates there so git never sees machine-specific data. Delete a `*.local.*` file to reset it to the tracked default. Run `pytest tests/test_repo_sanitized.py` before committing template changes to ensure tracked configs stay placeholder-only.
- Keep `.env` out of git; renderers (`scripts/render_proxy_config.py`, `scripts/render_cloudflared_config.py`) handle substitution. Regenerate Cloudflare configs via `make render-cloudflared`, store credentials under `~/.cloudflared`, and validate the public endpoint with the curl/JQ commands in `README.md`.
- Never manually edit `${PROXY_CONFIG}`, `${STELAE_CONFIG_HOME}/cloudflared.yml`, or `${TOOL_SCHEMA_STATUS_PATH}`; rerender or let automation update them.
- Cloudflare worker expects KV data (`scripts/push_manifest_to_kv.sh`). After pushing, deploy with `npx wrangler deploy --config cloudflare/worker/wrangler.toml`.

## Agent Workflow & Communication

- **Command Tool**: default to `["bash","-lc","…"]` for terminal operations; switch shells only when explicitly required.
- **MCP Invocation**: never assume the manifest is authoritative. Always attempt the requested MCP tool (e.g., `stelae.manage_stelae`) even if it is absent from the prompt roster, and report the exact response or error instead of substituting other mechanisms.
- **Placeholders & Mocks**: avoid introducing placeholders/mocks unless the user explicitly asks for them.
- **DRY & Modular Design**: remove duplicate logic via helpers, keep modules interchangeable, and respect manager/coordinator patterns (e.g., keep business logic out of view models).
- **TDD & Coverage**: prefer tests first, maintain ≥80% coverage, and document missing tests when encountered.
- **SOLID + Warning Signs**: watch for behavior-flipping booleans, deep inheritance, or parameter-heavy methods; refactor toward cohesive interfaces.
- **Communication**: respond concisely, mirror the user’s tone, surface risks/assumptions, and propose natural follow-up work (tests/docs) when it reinforces the change. If tooling prevents edits after three attempts, share the intended diff in chat and ask for manual application.
