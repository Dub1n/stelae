# Stelae MCP Stack

Stelae turns a local WSL workspace into a single MCP endpoint that desktop agents, ChatGPT Connectors, and other HTTP/SSE clients can consume. The repo bundles the Go-based proxy, helper MCP servers, bundle installers, and automation for rendering configs, restarting PM2, and publishing the catalog through an optional Cloudflare tunnel—all while letting you discover/install new MCP servers without editing files by hand, and declaratively override or aggregate existing tools.

> Looking for deep operational guidance? All maintainer-focused procedures now live in [DEVELOPMENT.md](DEVELOPMENT.md). This README stays focused on the information you typically expect on a GitHub landing page: what the project is, how to try it, and where to find the rest of the docs.

---

## Highlights

- One HTTP/SSE endpoint (the `Dub1n/mcp-proxy` fork) that aggregates filesystem, ripgrep, shell, memory, fetch, and catalog-driven custom tools.
- FastMCP bridge (`scripts/stelae_streamable_mcp.py`) keeps stdio clients in sync with the proxy catalog and falls back to `search`/`fetch` when the proxy is down.
- Starter bundle installs developer-friendly MCP servers without polluting tracked configs; additional bundles drop into `${STELAE_CONFIG_HOME}/bundles/`, and upcoming releases will ship each bundle as a single portable folder that you can drop into the config home to load custom tools + servers without duplicate overlays.
- Built-in `manage_stelae` MCP tool drives discovery, install, removal, and restarts entirely through MCP requests, so you can add servers surfaced by 1mcp without touching files or shell scripts.
- Declarative overrides and aggregation fragments let you rename tools, tweak descriptions and schemas, hide duplicates, and wrap any downstream toolset into a single curated call so the catalog stays concise.
- Managed render/restart flow (`make render-proxy`, `scripts/run_restart_stelae.sh`) keeps runtime artifacts under `${STELAE_STATE_HOME}` and verifies catalog drift.
- Optional Cloudflare named tunnel exposes the same catalog to remote agents with SSE support.

## Stack Snapshot

| Component | Transport | Launch Command | Purpose |
|-----------|-----------|----------------|---------|
| mcp-proxy | HTTP/SSE (:${PROXY_PORT:-9090}) | `${PROXY_BIN}` | Aggregates downstream MCP servers plus custom tools. |
| FastMCP bridge | streamable HTTP (`/mcp`) / stdio | `python -m scripts.stelae_streamable_mcp` | Streams the proxy catalog to Codex/CLI clients. |
| Tool aggregator MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/tool_aggregator_server.py` | Publishes declarative composite tools sourced from config-home catalog fragments and bundles, including aliases, description/schema overrides, and hide rules so downstream clutter stays curated. |
| Stelae integrator MCP | stdio | `${PYTHON} ${STELAE_DIR}/scripts/stelae_integrator_server.py` | Installs/removes downstream servers via 1mcp and restarts the stack. |
| 1mcp discovery agent | stdio | `${ONE_MCP_BIN} --transport stdio` | Finds nearby MCP servers and feeds the `manage_stelae` install flow so you never touch files manually. |
| Filesystem / ripgrep / commands MCPs | stdio | `${FILESYSTEM_BIN}`, `${RG_BIN}`, `${NPX_BIN}` | Core workspace helpers available after installing the starter bundle. |
| Optional servers | varies | See starter bundle + discovery installs | Memory, Strata, Fetch, Scrapling, Cloudflared helpers, etc. |

## Quick Start

### Requirements

- Python 3.11+, Go toolchain, and Node.js via NVM.
- Cloudflare CLI (only for remote access) and standard GNU tooling (`make`, `jq`).
- WSL with write access to `${STELAE_CONFIG_HOME}` (defaults to `~/.config/stelae`).

### Setup

```bash
python scripts/setup_env.py               # seed env + catalog defaults under ~/.config/stelae
make render-proxy                         # render proxy.json + merged overrides
source ~/.nvm/nvm.sh && make up           # start pm2 services
```

Install optional MCP suites at any time with `python scripts/install_stelae_bundle.py`.

### Validate

```bash
curl -s http://localhost:${PROXY_PORT:-9090}/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
source ~/.nvm/nvm.sh && pm2 status
```

When the manifest lists the expected tools and PM2 shows the proxy, FastMCP bridge, and accessory MCP servers as `online`, you can connect Codex CLI/TUI or ChatGPT’s connector to `http://127.0.0.1:9090` (or the Cloudflare hostname once enabled).

## Usage

- **Render + restart:** Run `make render-proxy` after editing templates or catalog fragments, then `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared` to rebuild, restart, and capture catalog drift. Add `--full` when you also need to push manifests to Cloudflare and restart the tunnel/worker.
- **Start/stop services:** `make up` loads the PM2 ecosystem (proxy, bridge, MCP servers, optional cloudflared); `make down` stops them. Always `source ~/.nvm/nvm.sh` before PM2 commands.
- **Local clients:** Point Codex or other MCP clients at the FastMCP bridge (`scripts/stelae_streamable_mcp.py`) with `STELAE_PROXY_BASE=http://127.0.0.1:9090`. The bridge automatically appends `/mcp` and loads `.env` / `${STELAE_CONFIG_HOME}/.env.local`.
- **Remote access:** Configure `~/.cloudflared/config.yml` with the `stelae` tunnel, run it under PM2 (`pm2 start "cloudflared tunnel run stelae" --name cloudflared`), and verify `https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` mirrors the local catalog.
- **Discovery-driven installs:** Use the `manage_stelae` MCP tool (available through the bridge) to run `discover_servers`, `install_server`, `remove_server`, or `run_reconciler`. The CLI equivalents live in `scripts/stelae_integrator_server.py --cli ...`.

## Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) – Maintainer handbook covering environment layering, restart automation, catalog handling, bundle workflows, discovery installs, and troubleshooting.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – Deep dive into config layering, catalog flow, and the intended/live snapshot model.
- [AGENTS.md](AGENTS.md) – Operational expectations for agents working inside this repo.
- [docs/e2e_clone_smoke_test.md](docs/e2e_clone_smoke_test.md) – Clone-smoke harness and verification steps.
- [CONTRIBUTING.md](CONTRIBUTING.md) – Quickstart for contributors (env/restart/diag flags).

## Support & Troubleshooting

Most operational issues (PM2 failures, catalog drift, tunnel outages, SSE probes) are documented in [DEVELOPMENT.md](DEVELOPMENT.md). If you need only a quick reminder:

- Ensure `source ~/.nvm/nvm.sh && pm2 status` shows `online` for `mcp-proxy`, `stelae-bridge`, downstream MCP servers, and (optionally) `cloudflared`.
- Re-run `python scripts/process_tool_aggregations.py --scope local` + `make render-proxy` whenever tool metadata changes.
- Use `make verify-clean` before publishing template or bundle updates so restart automation confirms `git status` stays clean.

Happy hacking!

## Roadmap

- **Portable bundles:** In-flight work (see `dev/tasks/completed/intended-catalog-plan-untracked-configs.md`) makes every bundle a self-contained folder you drop into `${STELAE_CONFIG_HOME}/bundles/<name>/`. The folder carries its catalog fragment, custom tool metadata, and install markers so servers/scripts wire up automatically without cloning overlay data.
- **Strata integration:** TODO items track deeper Strata routing: capability-driven promotion via a reconciler, optional `make promote CAPABILITY="…" TARGET=strata` flows, and catalog hooks so rare capabilities are satisfied through Strata without bloating the core manifest or requiring proxy restarts.
