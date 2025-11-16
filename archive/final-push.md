# bring the rest of the tool surface online

> purpose: make sure the **essentials** (fs, rg, sh, docs, mem, strata, fetch, github) all appear in `tools/list` and can be called through `/mcp`. also, handle Cloudflare wobble cleanly.

## 0) mental model

* **/mcp** is the only public entry.
* the proxy auto-aggregates each server’s tools during startup. a tool is visible **only after** its server says “Handling requests at /<name>/”.
* `tools/call` is routed by tool name → server. the proxy tries `/<server>/mcp` first, then falls back to `/<server>/`. internal dispatch sets `X-Proxy-Internal: 1` to bypass per-server auth.

## 1) confirm servers are up

```bash
pm2 status
pm2 logs mcp-proxy --lines 120 | egrep 'Handling requests at|Successfully listed|Adding tool' | sed -n '1,120p'
# expect lines like:
# <fs> Handling requests at /fs/
# <rg> Handling requests at /rg/
# <sh> Handling requests at /sh/
# <docs> Handling requests at /docs/
# <mem> Handling requests at /mem/
# <strata> Handling requests at /strata/
# <fetch> Handling requests at /fetch/
# <github> Handling requests at /github/
````

`pm2 status` should show `mcp-proxy`, `stelae-bridge`, `cloudflared`, and `watchdog` as `online`. The individual tool servers are managed by the proxy itself and only appear in the proxy logs.

If any server is missing, check its binary path/args in `config/proxy.json` (rendered from the template). Regenerate from `.env` if needed, then restart:

```bash
make render-proxy
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```

## 2) see which tools the facade sees

> Cloudflare sometimes returns non-JSON on first hit (HTTP 530 / code 1033). Use a retry that only `jq`s when content-type is JSON.

```bash
URL="https://mcp.infotopology.xyz/mcp"
for i in 1 2 3; do
  hdrs=$(mktemp)
  body=$(curl -sk -D "$hdrs" -H 'Content-Type: application/json' \
              --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' "$URL")
  ctype=$(grep -i '^content-type:' "$hdrs" | head -1 | tr -d '\r' | awk '{print tolower($2)}')
  status=$(sed -n '1p' "$hdrs")
  echo "$status"
  if echo "$ctype" | grep -q 'application/json'; then
    echo "$body" | jq -r '.result.tools[].name' | sort | nl | sed -n '1,200p'
    rm -f "$hdrs"; break
  else
    echo "--- non-JSON body (Cloudflare wobble), retrying ---"
    echo "$body" | head -c 200; echo
    rm -f "$hdrs"; sleep 1
  fi
done
```

> if a tool you expect isn’t listed once you get JSON, that’s a server-side thing. pop open that server’s logs.

## 3) per-tool notes + smoke tests

### filesystem (fs)

* **what it gives:** read/write file ops scoped to `STELAE_DIR` or configured root.
* **common tool names:** `read_file`, `write_file`, `list_directory` (exact names vary by server; check `tools/list`).
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"fs1","method":"tools/call","params":{"name":"read_file","arguments":{"path":"README.md"}}}' | jq .
```

### ripgrep (rg)

* **names:** usually `grep`.
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"rg1","method":"tools/call","params":{"name":"grep","arguments":{"pattern":"Stelae","paths":["/home/gabri/dev/stelae"],"max_count":3,"recursive":true}}}' | jq .
```

### shell (sh)

* **names:** `execute_command`, `get_command_history`, etc. (this server also exposes file helpers).
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"sh1","method":"tools/call","params":{"name":"execute_command","arguments":{"cmd":"git","args":["status","--porcelain"]}}}' | jq .
```

### docs (documentation catalog)

* **inspect schema first:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"d1","method":"tools/list"}' \
| jq '.result.tools[] | select(.name|test("doc|ingest|fetch";"i"))'
```

### memory (mem)

* **names:** `write_note`, `read_note`, `search_notes`, etc.
* **smoke:** write then read a small note.

### strata

* **names:** `discover_server_actions`, `execute_action`, `search_documentation`, etc.

### fetch

* **name:** `fetch`.
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"f1","method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com","raw":true}}}' | jq .
```

### github

* **names:** `search_repositories`, `list_pull_requests`, etc. Requires a token in the GitHub MCP’s env.

## 4) if a server won’t register

* check `config/proxy.json` (command path + args).
* run the server binary once to see stderr.
* confirm it logs `Handling requests at /<name>/`.
* restart the proxy after edits:

```bash
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```

## 5) acceptance: “all essentials visible + callable”

Run this one-liner to verify the catalog contains the core set and show what’s missing:

```bash
URL="https://mcp.infotopology.xyz/mcp"
NEED="fetch github grep execute_command write_note read_note list_documentation_sources_tool"
hdrs=$(mktemp)
body=$(curl -sk -D "$hdrs" -H 'Content-Type: application/json' \
            --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' "$URL")
ctype=$(grep -i '^content-type:' "$hdrs" | head -1 | awk '{print tolower($2)}'); rm -f "$hdrs"
if echo "$ctype" | grep -q 'application/json'; then
  have=$(echo "$body" | jq -r '.result.tools[].name')
  missing=()
  for t in $NEED; do echo "$have" | grep -qx "$t" || missing+=("$t"); done
  if [ "${#missing[@]}" -eq 0 ]; then echo "✅ essentials present"; else echo "⚠️ missing: ${missing[*]}"; fi
else
  echo "⚠️ non-JSON from Cloudflare; retry the call once more."
fi
```

Also ensure at least two tool calls succeed (e.g., `fetch` + one of `grep`/`execute_command`/`read_file`).

---

## small ops cookbook

* **restart everything (no bridge in this architecture)**

```bash
pm2 restart mcp-proxy stelae-bridge cloudflared watchdog --update-env
pm2 save
```

* **logs**

```bash
pm2 logs mcp-proxy --lines 120
pm2 logs cloudflared --lines 80
```

* **cloudflared sanity**

```bash
cloudflared tunnel info stelae | sed -n '1,80p'
curl -skI https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | sed -n '1,12p'
```

---

## failure modes → quick fixes

| symptom you see                                | likely cause                                      | fast fix                                                                                       |                                    |
| ---------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------- |
| `jq: parse error` right after `tools/list`     | Cloudflare returned non-JSON (530 / code 1033)    | retry once; use the retry snippet in §2 that only `jq`s if content-type is JSON.               |                                    |
| `HTTP/2 530` on manifest or `tools/list`       | tunnel briefly not advertising, or CF edge hiccup | check `pm2 logs cloudflared`; `cloudflared tunnel info stelae`; then retry the call.           |                                    |
| `tools/list` missing expected tool(s)          | corresponding MCP process not registered          | `pm2 logs <name>`; look for “Handling requests at /<name>/”; fix command/path in `proxy.json`. |                                    |
| direct `POST /fetch/` returns `401`            | per-server auth enabled (expected)                | call via `/mcp` only; the facade sets `X-Proxy-Internal: 1`.                                   |                                    |
| `/mcp` GET returns plain text “page not found” | old binary                                        | rebuild `mcp-proxy`, restart; `ss -ltnp                                                        | grep :9090` should show the proxy. |
| `HTTP 502` sporadically on `tools/list`        | CF connection churn while origin is fine          | just re-hit; your origin is stateless JSON-RPC.                                                |                                    |

**core sanity loop (run these in order):**

```bash
# 1) local port up
ss -ltnp | grep :9090

# 2) initialize (local)
curl -s http://127.0.0.1:9090/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq .

# 3) public manifest (may occasionally 530; retry once)
curl -skI https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | sed -n '1,12p'

# 4) tool catalog (public, with retry)
# use the script block in §2; expect >= 30 tools and names from fs/rg/sh/docs/mem/strata/fetch/github.

# 5) a tool call (public)
curl -sk https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com","raw":true}}}' \
| jq .
```
