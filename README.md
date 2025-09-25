# Stelae MCP Stack

A WSL-native deployment of [mcp-proxy](https://github.com/TBXark/mcp-proxy) that exposes your local Phoenix workspace to ChatGPT (and other MCP-aware agents) through a single HTTP/SSE endpoint. Everything runs on WSL, with an optional Cloudflare named tunnel for remote access.

---

## Stack Snapshot

| Component | Transport | Launch Command | Purpose |
|-----------|-----------|----------------|---------|
| mcp-proxy | HTTP/SSE (:9090) | `${PROXY_BIN}` | Aggregates tools/prompts/resources from local MCP servers into one endpoint. |
| Filesystem MCP | stdio | `${FILESYSTEM_BIN} --root ${STELAE_DIR}` | Scoped read/write access to the repo. |
| ripgrep MCP | stdio | `${RG_BIN} --stdio --root ${SEARCH_ROOT}` | Code search backend used by the canonical `search` shim. |
| Terminal Controller MCP | stdio | `${SHELL_BIN}` | Allowlisted command execution in Phoenix workspace. |
| Docy MCP | stdio | `${DOCY_BIN} --stdio` | Documentation / URL ingestion (feeds canonical `fetch`). |
| Basic Memory MCP | stdio | `${MEMORY_BIN}` | Persistent project memory. |
| Strata MCP | stdio | `${STRATA_BIN}` | Progressive discovery / intent routing. |
| 1mcp agent | stdio | `${ONE_MCP_BIN} --transport stdio` | Discovery/promotion sidecar serving capability lookups. |
| Search shim | stdio | `${SEARCH_PYTHON_BIN} ${STELAE_DIR}/scripts/stelae_search_mcp.py` | Wraps ripgrep tools and exposes canonical `search`. |
| Fetch MCP | stdio | `${LOCAL_BIN}/mcp-server-fetch` | Official MCP providing canonical `fetch`. |

Path placeholders expand from `.env`; see setup below.

---

## Prerequisites

- Windows 11 + WSL2 (Ubuntu) with systemd enabled (`/etc/wsl.conf` → `[boot]` / `systemd=true`).
- Tooling installed: Go, Node.js + npm (via NVM), `pm2`, Python 3.11+, `pipx`, `ripgrep`, `cloudflared`.
- Discovery agent: `npm install -g @1mcp/agent` (provides the `1mcp` binary).
- Cloudflare named tunnel `stelae` with DNS `mcp.infotopology.xyz` and credentials stored under `~/.cloudflared/`.

---

## Environment & Config

1. Copy `.env.example` → `.env` and update absolute paths:
   - Project roots: `STELAE_DIR`, `APPS_DIR`, `PHOENIX_ROOT`, `SEARCH_ROOT`.
   - Binaries: `FILESYSTEM_BIN`, `RG_BIN`, `SHELL_BIN`, `DOCY_BIN`, `MEMORY_BIN`, `STRATA_BIN`, `ONE_MCP_BIN`, `SEARCH_PYTHON_BIN`, `LOCAL_BIN/mcp-server-fetch`.
   - Public URLs: `PUBLIC_BASE_URL=https://mcp.infotopology.xyz`, `PUBLIC_SSE_URL=${PUBLIC_BASE_URL}/stream`.
2. Regenerate runtime config:
   \```bash
   make render-proxy
   \```
   This renders `config/proxy.json` from `config/proxy.template.json` using `.env` (with `.env.example` as fallback).
3. Ensure the `stelae-search` virtualenv contains `mcp` ≥ 0.1.0:
   \```bash
   ${SEARCH_PYTHON_BIN} -m pip install --upgrade mcp
   \```
   Install the fetch server with `pipx install mcp-server-fetch` if not already present.

---

## Running the Stack (PM2)

`pm2` lives in your NVM install. Always source NVM before using it:

\```bash
source ~/.nvm/nvm.sh
\```

- Start + persist services:
  \```bash
  make up
  pm2 startup systemd    # run once; executes printed sudo command
  \```
- Apply config changes:
  \```bash
  make render-proxy
  source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
  \```
- Check status / logs:
  \```bash
  source ~/.nvm/nvm.sh && pm2 status
  source ~/.nvm/nvm.sh && pm2 logs --lines 50
  \```
- Stop everything:
  \```bash
  make down
  \```

Logs default to `~/dev/stelae/logs/` (see `ecosystem.config.js`).

---

## Cloudflare Named Tunnel

`~/.cloudflared/config.yml`:

\```yaml
tunnel: stelae
credentials-file: ~/.cloudflared/7a74f696-46b7-4573-b575-1ac25d038899.json

ingress:

- hostname: mcp.infotopology.xyz
    service: http://localhost:9090
- service: http_status:404
\```

Operational steps:

1. Confirm DNS route:
   \```bash
   cloudflared tunnel route dns stelae mcp.infotopology.xyz
   \```
2. Manage via PM2:
   \```bash
   source ~/.nvm/nvm.sh && pm2 start "cloudflared tunnel run stelae" --name cloudflared
   source ~/.nvm/nvm.sh && pm2 save
   \```
3. After updating `.env` or proxy config, restart:
   \```bash
   make render-proxy
  source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
  source ~/.nvm/nvm.sh && pm2 restart cloudflared
   \```
4. Validate endpoints:
   \```bash
   curl -s http://localhost:9090/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq '{servers, tools: (.tools | map(.name))}'
   curl -skI https://mcp.infotopology.xyz/stream
   \```

---

## Local vs Remote Consumers

- Remote agents (e.g. ChatGPT) use the public manifest served via Cloudflare.
- Local MCP clients can connect to `http://localhost:9090`. A split-manifest approach is tracked in `TODO.md` (Further Enhancements) if you decide to differentiate responses.

---

## Validation Checklist

1. `curl -s http://localhost:9090/tools/list` confirms `search` and `fetch` are published.
2. From ChatGPT, call `search` on the Phoenix repo and `fetch` on an external URL—both should succeed.
3. `pm2 status` shows `online` for proxy, each MCP, and `cloudflared`.

---

## Maintenance

| Cadence | Action |
|---------|--------|
| Monthly | `git pull` + rebuild `mcp-proxy`; `pipx upgrade --include-apps`; `npm update -g`; redeploy via `make render-proxy` and restart services. |
| Quarterly | Audit filesystem roots, shell allowlist, Cloudflare credentials, and `.env` paths. |
| As needed | Update `.env` when binaries move; rerun `make render-proxy`; `pm2 restart mcp-proxy --update-env`. |

Keep a backup of `config/proxy.json` (or rely on git history) before large changes.

---

## Troubleshooting

- `pm2 status` shows `Permission denied` → source NVM first (`source ~/.nvm/nvm.sh`).
- `search` missing in manifest → verify the shim virtualenv has the `mcp` package and restart the `search` process.
- `fetch` missing → ensure `mcp-server-fetch` lives under `${LOCAL_BIN}` and is executable.
- `jq: parse error` → wrap the jq program in single quotes: `jq '{servers, tools: (.tools | length)}'`.
- Cloudflare 404 on `/stream` → proxy offline or tunnel disconnected; inspect `pm2 logs mcp-proxy` and `pm2 logs cloudflared`.

---

## Related Files

- `config/proxy.template.json` — template rendered into `config/proxy.json`.
- `scripts/render_proxy_config.py` — templating helper.
- `scripts/stelae_search_mcp.py` — FastMCP shim providing canonical `search`.
- `scripts/stelae_search_fetch.py` — HTTP shim (unused currently; keep for potential automation).
- `dev/server-setup-commands.md` — Cloudflare tunnel quick commands.
- `TODO.md` — backlog and future enhancements.
