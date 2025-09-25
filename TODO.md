Awesome—here’s a complete, implementation-ready tasklist in “task decomposition” style, from clean machine → running system → validation → maintenance. I’ve included test items (unit + integration + security) and explicit acceptance criteria so you can tick things off confidently.

# Phase 0 — Prep & Conventions

- [x] **Enable systemd in WSL**

  - Edit `/etc/wsl.conf` →

     ```conf
     [boot]
     systemd=true
     ```

     `wsl --shutdown` (from Windows), re-enter WSL
  - ✅ *Acceptance:* `systemctl is-system-running` returns not `offline`

- [x] **Create base dirs**

  - `mkdir -p ~/dev/stelae/{config,reconciler,logs} ~/apps/{mcp-proxy,vendor}`
  - ✅ *Acceptance:* folders exist and are writable by your user

- [x] **Install dependencies**

  - `sudo apt-get update && sudo apt-get install -y golang python3-pip python3-venv ripgrep make`
  - Node/NPM: install latest (nvm or distro); `npm -v` ok
  - `pipx ensurepath && hash -r` (if using pipx)
  - `npm i -g pm2`
  - `cloudflared` installed (package or binary)
  - ✅ *Acceptance:* `go version`, `node -v`, `pm2 -v`, `cloudflared --version` succeed

---

# Phase 1 — Core Orchestrator (mcp-proxy)

- [x] **Clone & build `mcp-proxy`**

  - `cd ~/apps && git clone https://github.com/TBXark/mcp-proxy.git`
  - `cd ~/apps/mcp-proxy && make build`
  - ✅ *Acceptance:* `~/apps/mcp-proxy/build/mcp-proxy` is executable

- [x] **Create proxy config (templated)**

  - Maintain `config/proxy.template.json` with placeholders sourced from `.env`
  - Render concrete JSON via `make render-proxy`
  - ✅ *Acceptance:* Generated `config/proxy.json` matches current environment values

- [x] **First boot (manual)**

  - `~/apps/mcp-proxy/build/mcp-proxy --config ~/dev/stelae/config/proxy.json`
  - ✅ *Acceptance:* process starts; logs show connected clients; `curl localhost:9090/health` (if available) or observe startup log

---

# Phase 2 — Essential MCPs

- [x] **Install essential servers**

  - Filesystem MCP (choice you selected) → `npm i -g <package>` or build per README
  - ripgrep MCP → `npm i -g mcp-grep` **used: `pip install mcp-grep`**
  - Shell MCP → **pick one**:

    - `pipx install terminal-controller-mcp` **(recommended)**, or
    - build/install `mcp-shell`
  - Docs → `npm i -g mcp-server-docy`
  - Memory → `pipx install basic-memory` (and/or `pipx install mcp-pif`)
  - Strata → `pipx install strata-mcp`
  - *(Tasks MCP deferred; schedule via 1mcp promotion once baseline stack is stable)*
  - ✅ *Acceptance:* each tool responds to `--help` or starts in a terminal and prints a startup banner
  - [ ] Capture the banner/`--help` output for each installed MCP and stash the command list for troubleshooting

- [x] **Wire proxy clients to essentials**

  - Ensure each client stanza in `proxy.json` matches the binary name + args
  - ✅ *Acceptance:* Start proxy; logs show each client (minus deferred tasks MCP) initialized without error

---

# Phase 3 — Process Management (pm2)

- [x] **Drop `ecosystem.config.js`**

  - Place the file you generated at `~/dev/stelae/ecosystem.config.js`
  - Ensure log dir exists: `mkdir -p ~/dev/stelae/logs`
  - ✅ *Acceptance:* `node -e "require('./ecosystem.config.js')"` runs without error (from that folder)

- [x] **Start & persist**

  - [x] `pm2 start ~/dev/stelae/ecosystem.config.js`
  - [x] `pm2 save`
  - [x] `pm2 startup systemd` → run the printed command once (requires sudo password)
  - ✅ *Acceptance:* `pm2 status` shows all services online; `reboot` WSL → services auto-start
  - [x] Record `pm2 status` and tail key logs (`pm2 logs --lines 50`) to confirm each service stays up for >60s

---

# Phase 4 — Single Public URL (Tunnel)

- [x] **Run cloudflared**

- `cloudflared tunnel --url http://localhost:9090`
- Copy the HTTPS URL
- ✅ *Acceptance:* URL is accessible from a browser (will error without auth, but endpoint should respond)

- [ ] **Add ChatGPT connector**

- ChatGPT → Settings → Connectors → Add → paste the tunnel URL
- Start a new chat and enable the connector
- ✅ *Acceptance:* In the chat, the agent can list available tools (fs/rg/sh/docs/memory/strata) and call a simple one (e.g., read a file); tasks will be promoted later

---

# Phase 5 — Discovery/Install Sidecar (1mcp agent)

- [ ] **Install globally**

- `npm install -g @1mcp/agent`
- ✅ *Acceptance:* `1mcp --version` succeeds from a new shell

- [ ] **Add to pm2**

- Ensure `ecosystem.config.js` launches the binary via stdio (e.g. `script: "1mcp"`, `args: "--transport stdio"`)
- `pm2 restart 1mcp`
- ✅ *Acceptance:* `pm2 logs 1mcp` stays quiet (stdio idle) and `pm2 describe 1mcp` points to the npm binary

---

# Phase 6 — Reconciler (promotion automation)

- [ ] **Create reconciler skeleton**

- File: `~/dev/stelae/reconciler/reconcile.py`
- Responsibilities:

  - Accept `--capability` and `--target core|strata`
  - Query 1mcp for candidates (capability → servers)
  - Resolve connection: `stdio` (command/args) or `sse/http` (url)
  - **If core:** append a `clients[]` stanza to `proxy.json`
   -*If strata:** register under Strata (method: either tell Strata to include it or keep it external—doc note in code)
  - Write back `proxy.json` atomically (tmp file → move)
- ✅ *Acceptance:* `python3 reconcile.py --help` prints usage; dry run prints plan (no write)

- [ ] **Integrate with Makefile**

- Ensure `make promote CAPABILITY="…" TARGET=core|strata` calls the reconciler
- **Core**: after reconcile, `pm2 restart mcp-proxy`
- **Strata**: no proxy restart required
- ✅ *Acceptance:* `make promote CAPABILITY="browser automation" TARGET=core` updates `proxy.json` with a new client and restarts proxy

- [ ] **Reintroduce tasks MCP via promotion**

- First successful promotion should target `tasks` via 1mcp (core surface)
- ✅ *Acceptance:* `make promote CAPABILITY="task manager" TARGET=core` adds the tasks MCP stanza and restarts the proxy cleanly

---

# Phase 7 — Testing (Unit, Integration, Security)

- [ ] **Unit tests (reconciler)**

- Add `~/dev/stelae/reconciler/tests/test_reconcile.py`
- Test cases:

  - Parses and validates `--capability` & `--target`
  - Maps 1mcp response → correct client stanza (stdio vs http/sse)
  - Writes JSON atomically; preserves formatting; rejects duplicates
  - Idempotency: promoting the same tool twice doesn’t duplicate
  - Error handling: bad server data raises clear exceptions
- Use `pytest` and fixtures for a fake `proxy.json`
- ✅ *Acceptance:* `pytest -q` passes locally

- [ ] **Integration tests (local)**

- **Smoke:** With proxy running, call a read-only tool (e.g., `fs.read_file`) from a tiny script or via ChatGPT; expect 200 and JSON result
- **Promotion:** Run `make promote` for a known MCP (e.g., a small CLI tool); confirm it appears in `tools/list` and runs
- **Strata path:** Ask for a rare capability; ensure agent flows through Strata successfully
- ✅ *Acceptance:* All 3 scenarios succeed end-to-end

- [ ] **Security tests**

- **FS scoping:** Attempt write outside repo path → must be denied
- **Shell allowlist:** Try disallowed commands (e.g., `curl`, `wget`) → blocked with clear error
- **Secrets:** Confirm `.env`, `.git`, and similar are ignored or read-only
- **Destructive ops:** Confirm `confirm: true` or explicit approval required (by policy / tool design)
- ✅ *Acceptance:* All negative tests are blocked & logged

- [ ] **Performance sanity**

- Measure cold start of proxy; record typical tool call latency (fs read, grep)
- Promote 1–2 tools; confirm proxy reload is quick (< a few seconds) and tools are available immediately after
- ✅ *Acceptance:* Latency/availability acceptable for your workflow

---

# Phase 8 — Documentation & Dev Ergonomics

- [ ] **README update (stelae)**

  - [x] Document `.env.example` workflow and refresh pm2 launch example
  - [ ] Reconcile remaining sections (promotion workflow, rollback) before GA
  - ✅ *Acceptance:* A new dev can bootstrap the stack following the README only

- [ ] **Makefile finishing touches**

- Ensure targets: `up`, `down`, `status`, `logs`, `restart-proxy`, `tunnel`, `promote`
- Add `help` target lists all with brief descriptions
- ✅ *Acceptance:* `make help` prints clean usage

- [ ] **Optional: Blue/Green**

- Add `GREEN_PORT`/`GREEN_CONFIG` and `start-green`/`swap-green` in Makefile
- Configure ingress swap (Cloudflare tunnel or local reverse proxy) if you want zero-downtime promotions
- ✅ *Acceptance:* You can flip between two proxy configs without interrupting the public URL

---

# Phase 9 — Acceptance in ChatGPT

- [ ] **Connector verification**

- New chat → enable connector → “List available tools” → call `mem.list` and `rg.search` on Phoenix *(add `tasks.list` after promoting the tasks MCP)*
- ✅ *Acceptance:* Tools are visible and working

- [ ] **Real Phoenix workflow**

- Ask the agent to: scan TODOs, propose a refactor plan, run tests, and create a branch
- ✅ *Acceptance:* Shell MCP runs the commands; diffs/changes reviewed & committed via approvals

- [ ] **Promotion live test**

- “I need Playwright to smoke test the UI” → run `make promote CAPABILITY="playwright" TARGET=strata` (or core if you prefer) → have the agent run the new tool
- ✅ *Acceptance:* Tool appears and executes successfully, without destabilizing the stack

---

# Phase 10 — Maintenance & Evolution

- [ ] **Update cadence**

- Monthly: `git pull && make build` for `mcp-proxy`; `pipx upgrade` and `npm -g update` for MCPs; `pm2 restart all`
- Quarterly: review allowlists, remove stale MCPs, snapshot `.ai` data
- ✅ *Acceptance:* Upgrades don’t break startup; rollback plan documented

- [ ] **Rollback**

- Keep `proxy.json.bak` and a `proxy.json.prev` snapshot on each promotion
- Rollback = copy prev → `proxy.json`, `make restart-proxy`
- ✅ *Acceptance:* Tool surface returns to prior state cleanly

---

## Further Enhancements

- [ ] Serve distinct manifests for local versus remote clients to avoid duplicating endpoints in a single response.

  - Remote: keep `/.well-known/mcp/manifest.json` on `mcp.infotopology.xyz` with public SSE URLs only.
  - Local: expose a second manifest (e.g. `http://localhost:9090/.well-known/mcp/local-manifest.json`) that lists loopback endpoints, so desktop agents can autodiscover without seeing tunnel hosts.
  - Requires host-aware routing in `http.go` and an extra renderer toggle in the template, but trims manifest size and removes duplicated entries once implemented.

---

## Optional Enhancements

- **Controller MCP for dynamic tools:** implement MCP `tools.listChanged`/promotion so the proxy can grow its tool list without restarting (only if your client handles it well)
- **Inspector/observability:** add MCP Inspector (local) to view calls live
- **Policy MCP:** centralize approvals/HITL prompts

---

### Final sanity checklist

- [ ] Proxy runs on boot; single public URL works
- [ ] Essentials available & tested on Phoenix
- [ ] Reconciler promotes tools (core & strata paths) with tests passing
- [ ] Security guardrails enforced (FS/shell)
- [ ] Docs/Makefile/PM2 ecosystem up to date
- [ ] You can complete a real Phoenix task end-to-end inside ChatGPT

If you want, I can generate a minimal `reconciler/reconcile.py` skeleton + unit tests next, so you can `make promote` immediately and iterate from there.
