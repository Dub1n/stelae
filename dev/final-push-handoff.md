# stelae — mcp connector handoff

## tl;dr (what must be working)

- **facade (mcp-proxy)** listens on **:9090**, aggregates tools, serves `/mcp` (SSE + JSON-RPC).
- **cloudflared named tunnel** `stelae` runs with **config file** (`~/.cloudflared/stelae.yml` or the rendered one), carrying `/mcp` to the proxy.
- **manifest** is served by a **Cloudflare Worker + KV** at  
  `https://mcp.infotopology.xyz/.well-known/mcp/manifest.json`  
  (edge-served; not dependent on the tunnel).
- **tools** appear via `tools/list` (public `/mcp`) — expect ~**39** right now.
- **pm2** supervises: `mcp-proxy`, `cloudflared`, `strata`, `docy`, `memory`, `shell`, `watchdog`.

---

## how it is now (files + processes)

### core files you might touch

- Proxy + config
  - `stelae/config/proxy.template.json` → rendered to `stelae/config/proxy.json`
  - `stelae/scripts/render_proxy_config.py` (renderer)
- Process supervisor
  - `stelae/ecosystem.config.js` (pm2 apps: proxy, cloudflared, watchdog, etc.)
  - `stelae/scripts/restart_stelae.sh` (single-shot restart + probes)
- Cloudflared
  - `~/.cloudflared/stelae.yml` (or) `stelae/ops/cloudflared.yml` (rendered)
  - `stelae/scripts/render_cloudflared_config.py` (if using the template)
- Worker (manifest)
  - `stelae/cloudflare/worker/manifest-worker.js`
  - `stelae/cloudflare/worker/wrangler.toml`
  - `stelae/scripts/push_manifest_to_kv.sh` (fetch origin manifest → KV)
- Utility
  - `stelae/scripts/watch_public_mcp.py` (watchdog: restarts cloudflared on repeated failures)

### pm2 expected set

```list
mcp-proxy, cloudflared, strata, docy, memory, shell, watchdog
```

---

## quick architecture (flow)

```mermaid
flowchart LR
    Client["ChatGPT Connector<br/>(fetch manifest → POST /mcp)"]
    subgraph Cloudflare Edge
      WK["Worker (KV-backed) serves manifest<br/>/.well-known/mcp/manifest.json"]
      CF["Cloudflare Tunnel (stelae)"]
    end
    subgraph Host
      PX["mcp-proxy :9090<br/>/mcp (SSE + JSON-RPC)"]
      S1["fs/rg/sh/docs/mem/strata/fetch/github<br/>(stdio MCP servers)"]
      PM2["pm2 (supervision)"]
    end

    Client -->|GET manifest| WK
    Client -->|POST /mcp| CF --> PX --> S1
    PM2 --- PX
    PM2 --- CF
    PM2 --- S1
````

---

## what to check (copy/paste probes)

### 0) local origin

```bash
# proxy listening
ss -ltnp | grep :9090

# SSE head check
curl -sI http://127.0.0.1:9090/mcp | sed -n '1,8p'

# initialize (JSON-RPC, local)
curl -s http://127.0.0.1:9090/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"init","method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq .

# tools/list (local)
curl -s http://127.0.0.1:9090/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,60p'
```

### 1) worker / manifest (edge, tunnel not required)

```bash
# headers show worker + cache hints
curl -sI https://mcp.infotopology.xyz/.well-known/mcp/manifest.json \
  | egrep -i 'cache-control|x-worker|content-type|server'

# body sanity (endpoint paths)
curl -s  https://mcp.infotopology.xyz/.well-known/mcp/manifest.json \
  | jq '{name, endpoint, endpointURL}'
```

> if `name:null`, KV is empty → push the real manifest:

```bash
# fetch origin’s manifest bytes
curl -fsS http://127.0.0.1:9090/.well-known/mcp/manifest.json -o /tmp/manifest.json
# write to KV using namespace id
wrangler kv key put --namespace-id "YOUR_KV_ID" manifest_json --path /tmp/manifest.json
```

### 2) public `/mcp` tools (may occasionally 530 once; re-hit)

```bash
URL="https://mcp.infotopology.xyz/mcp"
hdrs=$(mktemp)
body=$(curl -sk -D "$hdrs" -H 'Content-Type: application/json' \
            --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' "$URL")
ctype=$(grep -i '^content-type:' "$hdrs" | head -1 | tr -d '\r' | awk '{print tolower($2)}')
echo "status: $(sed -n '1p' "$hdrs")"; rm -f "$hdrs"
if echo "$ctype" | grep -q 'application/json'; then
  echo "$body" | jq -r '.result.tools[].name' | sort | nl | sed -n '1,60p'
else
  echo "edge burp (non-JSON); re-run once"
fi
```

### 3) smoke calls (public)

```bash
# fetch
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"f","method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com","raw":true}}}' | jq '.result|keys'

# grep
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"rg","method":"tools/call","params":{"name":"grep","arguments":{"pattern":"Stelae","paths":["/home/gabri/dev/stelae"],"max_count":2,"recursive":true}}}}' | jq '.result|keys'

# shell
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"sh","method":"tools/call","params":{"name":"execute_command","arguments":{"cmd":"git","args":["status","--porcelain"]}}}}' | jq '.result|keys'
```

---

## common pain points (and the fast fix)

| symptom                                         | likely cause                                 | fix                                                                                                                                  |                                                                   |
| ----------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `HTTP/2 530` / code **1033** on public manifest | Cloudflare edge can’t reach tunnel right now | **Worker+KV** already removes this for manifest. If seen on `/mcp`, just re-hit; tunnel is sticky + watchdog will restart if needed. |                                                                   |
| `jq: parse error` after `tools/list`            | edge returned non-JSON (transient 530/502)   | retry once; our checks only `jq` when `Content-Type: application/json`.                                                              |                                                                   |
| tools missing from `tools/list`                 | a server didn’t register                     | `pm2 logs mcp-proxy --lines 200                                                                                                      | grep 'Handling requests at'`then fix command/args in`proxy.json`. |
| Worker returns 503 for manifest                 | KV key missing or wrong namespace id         | push manifest to KV via `push_manifest_to_kv.sh` or `wrangler kv key put … --namespace-id`.                                          |                                                                   |
| `cloudflared` keeps “errored” in pm2            | started without `--config` / wrong HOME      | pm2 `args`: `--no-chunked-encoding --config ~/.cloudflared/stelae.yml tunnel run stelae`.                                            |                                                                   |
| wrangler “ByteString 8230”                      | Unicode `…` pasted into env/token            | re-export tokens as pure ASCII; use `.env` and `.gitignore`.                                                                         |                                                                   |

---

## acceptance markers (call it done when…)

- **manifest**:
  `curl -sI https://mcp.infotopology.xyz/.well-known/mcp/manifest.json` → `200`, has `x-worker: stelae-manifest`, `cache-control` shows `stale-while-revalidate` + `stale-if-error`.
  `curl -s … | jq '{name, endpoint, endpointURL}'` → non-null `name`, `endpoint:"/mcp"`.

- **catalog** (public):
  `tools/list` returns **≥30** tools, including (at least)
  `grep`, `execute_command`, `read_file`, `write_file`, `list_documentation_sources_tool`, `write_note`, `read_note`, `fetch`, and any github tools (if token configured).

- **two smokes succeed** (public): e.g., `fetch` + `grep` or `execute_command`.

- **pm2**: all apps online; `watchdog` prints “ok” once per interval.
  `pm2 status` shows `online` for `cloudflared`.

---

## handy commands

```bash
# restart everything (no bridge in this architecture)
bash stelae/scripts/restart_stelae.sh

# just render + restart proxy
make render-proxy && pm2 restart mcp-proxy --update-env && pm2 save

# deploy worker (from its dir) and push fresh manifest bytes to KV
cd stelae/cloudflare/worker && wrangler deploy
bash stelae/scripts/push_manifest_to_kv.sh
```

---

## if you need to change something

- change a tool server path/args → **edit** `config/proxy.template.json` → `make render-proxy` → `pm2 restart mcp-proxy`.
- move the manifest endpoint (don’t) → keep `/mcp` stable; update behind facade instead.
- new tunnel or host → update `~/.cloudflared/stelae.yml` (or render) and pm2 `ecosystem.config.js` args for `cloudflared`.

---

## notes

- the worker serving the manifest makes first contact resilient; `/mcp` still rides the tunnel.
- keep your Cloudflare token in `.env` (gitignored):

  ```.env
  CLOUDFLARE_API_TOKEN=…
  CLOUDFLARE_ACCOUNT_ID=…
  ```

- account id and KV ids can live in `wrangler.toml` (not secrets).

- if you want real HA later, add a **second connector** on a different host/network using the same tunnel creds.
