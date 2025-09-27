# bring the rest of the tool surface online

> purpose: make sure the **essentials** (fs, rg, sh, docs, mem, strata, fetch, github) all appear in `tools/list` and can be called through `/mcp`.

## 0) mental model

* **/mcp** is the only public entry.
* the proxy auto-aggregates each server’s tools during startup. a tool is visible **only after** its server says “handling requests at /<name>/”.
* `tools/call` is routed by tool name → server. the proxy tries `/<server>/mcp` first, then falls back to `/<server>/`. internal dispatch sets `X-Proxy-Internal: 1` to bypass per-server auth.

## 1) confirm servers are up

```bash
pm2 status
pm2 logs mcp-proxy --lines 80
# you want to see lines like:
# <fetch> Handling requests at /fetch/
# <rg> Handling requests at /rg/
# <fs> Handling requests at /fs/
# <sh> Handling requests at /sh/
# <docs> Handling requests at /docs/
# <mem> Handling requests at /mem/
# <strata> Handling requests at /strata/
# <github> Handling requests at /github/
```

If any server is missing, check its binary path/args in `config/proxy.json` (rendered from the template). Regenerate from `.env` if needed, then restart:

```bash
make render-proxy
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```

## 2) see which tools the facade sees

```bash
curl -s https://mcp.infotopology.xyz/mcp \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' \
| jq -r '.result.tools[].name' | sort | nl | sed -n '1,200p'
```

> if a tool you expect isn’t listed, that’s a server-side thing. pop open that server’s logs.

## 3) per-tool notes + smoke tests

> tip: always use the **exact** name from `tools/list`. examples below are typical.

### filesystem (fs)

* **what it gives:** read/write file ops scoped to `STELAE_DIR` or configured root.
* **common tool names:** `read_file`, `write_file`, `list_dir`.
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"fs1","method":"tools/call","params":{"name":"read_file","arguments":{"path":"README.md"}}}' | jq .
```

* **gotchas:** ensure the filesystem server has the correct `--root` (from your template). permission errors show as JSON-RPC errors (HTTP 200).

### ripgrep (rg)

* **what it gives:** code/content search over a root.
* **common tool names:** `grep` or `search`.
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"rg1","method":"tools/call","params":{"name":"grep","arguments":{"pattern":"Stelae","paths":["/home/gabri/dev/stelae"],"max_count":3,"recursive":true}}}' | jq .
```

* **gotchas:** path root must be readable; very large trees can be slow—tune args.

### shell (sh)

* **what it gives:** allowlisted commands under a workdir.
* **common tool names:** often exposed as `exec`/`run` (check `tools/list`).
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"sh1","method":"tools/call","params":{"name":"exec","arguments":{"cmd":"git","args":["status","--porcelain"]}}}' | jq .
```

* **gotchas:** allowlist is enforced (`--allow npm,pytest,make,python,git`). disallowed → JSON-RPC error.

### docs (docy)

* **what it gives:** fetch/ingest docs; sometimes exposes a `fetch`-like or `ingest` tool.
* **smoke:** inspect schema first:

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"d1","method":"tools/list"}' | jq '.result.tools[] | select(.name|test("doc|ingest|fetch";"i"))'
```

* **gotchas:** may require extra flags; some endpoints return markdown, some raw HTML.

### memory (mem)

* **what it gives:** simple project memory KV/note storage.
* **names:** `remember`, `recall`, etc. (varies—check list).
* **smoke:** call a tiny `remember` if present; then `recall`.

### strata

* **what it gives:** routing / discovery helper; often no direct tools you need to call manually.
* **smoke:** if a tool exists, call it; otherwise ignore.

### fetch

* **what it gives:** HTTP fetch with optional simplification.
* **name:** `fetch`.
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"f1","method":"tools/call","params":{"name":"fetch","arguments":{"url":"https://example.com","raw":true}}}' | jq .
```

* **gotchas:** direct `/fetch/` is 401 (by design). via `/mcp` it’s allowed. robots messages are informational.

### github

* **what it gives:** GitHub API wrappers (search, issues, PRs, etc.).
* **names:** `search_repositories`, `create_issue`, `list_pull_requests`, …
* **smoke:**

```bash
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"gh1","method":"tools/call","params":{"name":"search_repositories","arguments":{"q":"stelae in:name"}}}' | jq .
```

* **gotchas:** requires a token in its own config/env. if you see 401 via `/mcp`, the internal bypass is only for **per-server** auth, not for third-party API auth—set the token in the GitHub MCP’s env.

## 4) if a server won’t register

* check the `config/proxy.json` entry for that server (command path + args).
* run the server binary manually once to see stderr.
* confirm it logs `Handling requests at /<name>/`.
* restart the proxy after edits:

```bash
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env
```

## 5) acceptance: “all essentials visible + callable”

```bash
# must show a healthy list (contains fetch, some github tools, ideally fs/rg/sh/mem/docs)
curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' \
--data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' | jq -r '.result.tools[].name' | sort

# at least two tool calls succeed:
# 1) fetch
# 2) one other (e.g., github search, grep, or read_file)
```

---

## small ops cookbook

* **upgrade mcp-proxy binary**

```bash
cd ~/apps/mcp-proxy
go build -trimpath -ldflags "-s -w" -o build/mcp-proxy ./...
source ~/.nvm/nvm.sh && pm2 restart mcp-proxy --update-env && pm2 save
```

* **restart tunnel**

```bash
source ~/.nvm/nvm.sh && pm2 restart cloudflared
```

* **ensure on-boot persistence**

```bash
# already set up, but if on a new host:
sudo env PATH=$PATH:/home/gabri/.nvm/versions/node/v22.19.0/bin \
  /home/gabri/.nvm/versions/node/v22.19.0/lib/node_modules/pm2/bin/pm2 \
  startup systemd -u gabri --hp "/home/gabri"
pm2 save
```
