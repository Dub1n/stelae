# Agent Guidelines

## Stelae

### Project Structure & Module Organization

The root expects a local `.env`; rendered artifacts land in `config/proxy.json` via the Python renderers in `scripts/`. `scripts/` houses Python and bash automation—keep every module narrow and under 150 lines. Operational manifests live in `ops/`, Cloudflare worker code in `cloudflare/worker/`, and diagnostics in `dev/`. Integration tests stay in `tests/`, runtime logs under `logs/`, and the top-level `Makefile` is the authoritative interface to PM2 workflows.

### Runtime Topology & Responsibilities

- PM2 orchestrates four long-lived processes defined in `ecosystem.config.js`: the Go proxy on `:9090`, the Python streamable bridge (`scripts/stelae_streamable_mcp.py`), the Cloudflared tunnel, and the watchdog that restarts Cloudflared when the public probe fails. Always run `source ~/.nvm/nvm.sh` before `make up/down/status/logs` so PM2 sees the Node toolchain.
- The Go proxy binary lives outside this repo in `~/apps/mcp-proxy` (fork of `TBXark/mcp-proxy`). `ecosystem.config.js` points to that tree’s `build/mcp-proxy` artifact. Rebuild in that directory with `go build -o build/mcp-proxy` after Go changes.
- Downstream MCP servers (filesystem, ripgrep, shell, docs, memory, fetch, strata, etc.) are declared under `mcpServers` in the rendered `config/proxy.json`. Most run via stdio; fetch is HTTP. The bridge process keeps a streamable/stdio shim hot for local IDE clients.

### Configuration & Rendering Workflow

- Treat `config/proxy.json` as generated—edit `config/proxy.template.json` and run `make render-proxy` to refresh. The renderer pulls values from `.env` variables like `PUBLIC_BASE_URL`, `FILESYSTEM_BIN`, and `STELAE_DIR`.
- Manifest metadata (`manifest.*`) feeds both the proxy and Cloudflare worker. Key fields: `publicBaseURL` (external host), `serverName` (slug that remote clients reference), and optional resources array.
- Other templates: Cloudflare tunnel configuration under `ops/`, and diagnostic manifests in `dev/`.

### Manifest Pipeline (Local & Remote)

- Local manifest source: `http://localhost:9090/.well-known/mcp/manifest.json` served directly by the Go proxy (`http.go`). We extend `buildManifestDocument` and `manifestServerEntries` there. The manifest must include `endpointURL`, `servers` (single `stelae` entry with `transport` + `version`), tools, prompts, and resources.
- Public manifest: a Cloudflare Worker in `cloudflare/worker/manifest-worker.js` reads the origin manifest from KV and rewrites fields to enforce `https://mcp.infotopology.xyz/mcp`, normalize the server slug to `stelae`, and guarantee `transport/version`. Update KV via `scripts/push_manifest_to_kv.sh` (fetches localhost manifest) before deploying with `npx wrangler deploy --config cloudflare/worker/wrangler.toml`.
- When investigating manifest bugs, inspect both the Go proxy (for base document) and the worker (for edge rewrites). Verify with `curl -s http://localhost:9090/...` and `curl -sk https://mcp.infotopology.xyz/...`.

### Companion Repos & Cross-Repo Contracts

- `~/apps/mcp-proxy`: Go code for the proxy. Key files: `http.go` (HTTP server + manifest), `config.go` (config schema, including `ManifestConfig.ServerName`), and tests under `http_test.go`. Run `go test ./...` before rebuilding. Avoid editing `config.json` in that repo; Stelae renders its own config.
- The proxy expects manifest-aware fields like `manifest.serverName` and uses them when complementing manifest responses. Changes to schema require updates in both this repo and the Go fork.
- Cloudflare worker relies on KV data (namespace `stelae-manifest`). Ensure `scripts/push_manifest_to_kv.sh` succeeds before redeploying the worker; otherwise it falls back to a minimal manifest.

### Operational Playbook & Verification

- Typical workflow: edit template or Go source → `make render-proxy` (if template) → rebuild Go binary in `~/apps/mcp-proxy` → `make down` / `make up` to restart PM2 → `make status` to confirm processes → run curls in README (`jq '{servers, tools: (.tools|map(.name))}'`).
- Logs live under `logs/`; `make logs` tails all PM2 outputs. Individual logs: `logs/mcp-proxy.out.log`, `logs/cloudflared.err.log`, etc.
- Public availability requires Cloudflared: start/restart with `pm2 restart cloudflared` or the Makefile. If `curl -sk https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` returns CF 1033, the tunnel is down.

### Common Gotchas

- Do not hand-edit `config/proxy.json`; rerender from the template to avoid drift. The renderer injects paths for local binaries (filesystem/rg/etc.).
- Remember the manifest split: remote clients only see the single `stelae` server (streamable HTTP). We intentionally hide individual downstream servers to keep ChatGPT’s connector list clean.
- Some scripts (`scripts/restart_stelae.sh`, `dev/debug/*`) expect `.env` variables to be set and may fail silently if required keys are missing.
- The repo may contain pending docs (e.g., `docs/agnet_manifest_*`). Check `git status` before making large edits and avoid stomping user-authored drafts.

### Build, Test, and Development Commands

Run `make render-proxy` after touching `.env` or template files, then `make up` to start the PM2 stack defined by `ecosystem.config.js`; `make down` tears it back to a clean slate. Inspect process state with `make status` and follow rolling output with `make logs`. Always `source ~/.nvm/nvm.sh` before any PM2 interaction. Debug endpoints with helpers in `dev/`, for example `python dev/debug/check_connector.py --help`.

### Coding Style & Naming Conventions

Target Python 3.11+, 4-space indentation, and type-hinted, intention-revealing names such as `render_proxy_config`. Keep functions under 40 lines and split files before they reach 400 lines to preserve single responsibility. Shell scripts adopt `set -euo pipefail` and kebab-case filenames. JSON templates use uppercase placeholders like `{{ STELAE_DIR }}`; never embed secrets—let the renderer pull them from the environment.

### Testing Guidelines

Pytest is standard; add suites in `tests/` using `test_<feature>.py` modules and scenario-focused test functions. Run the full suite with `pytest` or scope with commands such as `pytest tests/test_streamable_mcp.py::test_happy_path`. Uphold ≥80% coverage for touched code and exercise both success and failure paths. When mocking external dependencies, prefer dependency-injected fakes instead of editing shared fixtures.

### Commit & Pull Request Guidelines

Write imperative commit subjects following `<type>: <summary>` (e.g., `docs: clarify proxy renderer usage`). Commit rendered outputs only when the deployment experience changes. Pull requests must describe the change, list impacted services, and record manual verification steps like `pytest` or `make render-proxy`, while linking issues or TODO items. Attach logs or screenshots for behavioral shifts and flag migrations or secret rotations explicitly.

### Security & Configuration Tips

Keep secrets out of git: `.env` stays local and values flow through PM2 environment variables. Regenerate Cloudflare configs via `make render-cloudflared` and retain results under `ops/`. Validate public endpoints with the curl checks in `README.md` before promoting configuration changes. Add new MCP servers through the template renderer rather than editing `config/proxy.json` manually to avoid drift.

## Agent

### Shared Agent Practices

- Default to bash commands via `["bash","-lc", …]` and only switch shells when the task explicitly requires it; never introduce mocks or placeholders unless requested.
- Eliminate duplicate logic by extracting reusable helpers and regression-testing shared code; design changes with SOLID guardrails—treat ~400 lines as the cue to split files, keep functions under ~40 lines, prefer composition, and watch for red flags like god classes or behavior-flipping boolean flags.
- Prefer TDD for new features and infrastructure while relaxing it for small fixes when speed matters; target ≥80% coverage, exercise both success and failure paths, and document any missing tests you uncover before waiting for user direction.
- Keep modules interchangeable and isolated, separating UI, business logic, and flow control (e.g., ViewModel/Manager/Coordinator) and check for existing CLI tooling before adding new scripts.

### Collaboration & Autonomy

- Handle natural follow-up work—tests, docs, quick fixes—without extra prompting, but confirm before taking on large or risky changes.
- Communicate concisely: skip emojis and filler, stay directive, and reinforce the user’s reasoning; when confusion appears, add a compact teaching note that explains the approach and relevant systems.

### Troubleshooting Discipline

- After three failed edit attempts due to tooling issues, share the intended contents (or any diff over 100 lines) in chat and ask the user to apply it.

## Integration Note

- This document blends repo-specific guidance with the shared cross-repo standards; when regenerating it, import only the applicable parts of the global rules, summarize instead of duplicating entire sections, and keep the result concise so future updates stay manageable.
