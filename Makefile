# ========= Phoenix MCP Stack — Makefile (WSL-native, pm2-based) =========
# Usage:
#   make up              # start all services via pm2
#   make down            # stop services
#   make restart-proxy   # restart mcp-proxy after config changes
#   make logs            # tail all logs
#   make status          # pm2 status table
#   make tunnel          # quick public URL for ChatGPT (cloudflared)
#   make promote CAPABILITY="browser automation" TARGET=core
#                        # promote a new MCP via reconciler into mcp-proxy (core) or strata (peripheral)
#
# Notes:
#  - Requires pm2 installed globally: `npm i -g pm2`
#  - Requires cloudflared for `make tunnel` (optional)
#  - Reconciler is a small Python script that uses 1mcpserver to discover/install and then edits the proxy config.
#    You can wire your own script; this Makefile assumes one exists at $(RECONCILER)
# ========================================================================

# ---- Paths (adjust to your environment) ----

# home dir
WSL_HOME        ?= $(HOME)

# your orchestration project (WIP, configs, reconciler, etc.)
STELAE_DIR      ?= $(WSL_HOME)/dev/stelae

# third-party source/binaries you don’t actively dev
APPS_DIR        ?= $(WSL_HOME)/apps
VENDOR_DIR      ?= $(APPS_DIR)/vendor

# mcp-proxy: binary comes from vendor, config lives in stelae
PROXY_DIR       ?= $(APPS_DIR)/mcp-proxy
PROXY_BIN       ?= $(PROXY_DIR)/build/mcp-proxy
PROXY_CONFIG    ?= $(STELAE_DIR)/config/proxy.json
PROXY_TEMPLATE  ?= $(STELAE_DIR)/config/proxy.template.json
PROXY_RENDERER  ?= $(STELAE_DIR)/scripts/render_proxy_config.py
PROXY_FALLBACK_ENV ?= $(STELAE_DIR)/.env.example
ENV_FILE        ?= $(STELAE_DIR)/.env

# pm2 ecosystem file (alongside Makefile in stelae)
PM2_ECOSYSTEM   ?= $(STELAE_DIR)/ecosystem.config.js

# reconciler (your own glue code)
RECONCILER      ?= $(STELAE_DIR)/reconciler/reconcile.py
PYTHON          ?= python3

# optional: cloudflared tunnel
CLOUDFLARED     ?= cloudflared
PUBLIC_PORT     ?= 9090

# pm2 binary + service list (must match ecosystem.config.js names)
PM2             ?= pm2
PM2_SERVICES_CORE ?= mcp-proxy strata docy memory shell 1mcp

# ---- Defaults for promote target ----
# CAPABILITY = the semantic capability to search (e.g., "playwright", "browser automation", "sql client")
# TARGET     = core | strata   (where to promote the new MCP)
TARGET              ?= core

# =========================================================================
# Phony targets
# =========================================================================
.PHONY: up down restart-proxy logs status tunnel promote help render-proxy

help:
	@echo "Targets:"
	@echo "  make up                 - Start all services via pm2 and save the process list"
	@echo "  make down               - Stop all managed services"
	@echo "  make restart-proxy      - Restart mcp-proxy (after config.json changes)"
	@echo "  make logs               - Tail all pm2 logs"
	@echo "  make status             - Show pm2 status table"
	@echo "  make tunnel             - Start a Cloudflare quick tunnel to http://localhost:$(PUBLIC_PORT)"
	@echo "  make promote CAPABILITY=\"<capability>\" TARGET=core|strata"
	@echo "                         - Discover & install a new MCP and promote it into mcp-proxy (core) or under Strata"
	@echo ""
	@echo "Variables you can override:"
	@echo "  PROXY_CONFIG=$(PROXY_CONFIG)"
	@echo "  PM2_ECOSYSTEM=$(PM2_ECOSYSTEM)"
	@echo "  RECONCILER=$(RECONCILER)"
	@echo "  PUBLIC_PORT=$(PUBLIC_PORT)"

# Start everything and persist across WSL reboots (requires systemd enabled, then 'pm2 startup systemd' one-time)
.PHONY: up down restart-proxy logs status tunnel promote help render-proxy

up: render-proxy
	@if [ ! -f "$(PM2_ECOSYSTEM)" ]; then echo "ERROR: Missing $(PM2_ECOSYSTEM)"; exit 1; fi
	$(PM2) start "$(PM2_ECOSYSTEM)"
	$(PM2) save
	@echo "Tip (one-time): run 'pm2 startup systemd' and follow instructions to auto-start on boot."

render-proxy:
	@if [ ! -f "$(PROXY_TEMPLATE)" ]; then echo "ERROR: Missing $(PROXY_TEMPLATE)"; exit 1; fi
	$(PYTHON) "$(PROXY_RENDERER)" \
	  --template "$(PROXY_TEMPLATE)" \
	  --output "$(PROXY_CONFIG)" \
	  --env-file "$(ENV_FILE)" \
	  --fallback-env "$(PROXY_FALLBACK_ENV)"

down:
	-$(PM2) stop $(PM2_SERVICES_CORE) || true
	-$(PM2) delete $(PM2_SERVICES_CORE) || true

restart-proxy:
	@if [ ! -f "$(PROXY_CONFIG)" ]; then echo "ERROR: Missing $(PROXY_CONFIG)"; exit 1; fi
	$(PM2) restart mcp-proxy

logs:
	$(PM2) logs

status:
	$(PM2) status

tunnel:
	$(CLOUDFLARED) tunnel --url http://localhost:$(PUBLIC_PORT)

# Promote a new MCP into the system (core => mcp-proxy; strata => under Strata MCP)
# Requires: CAPABILITY="some capability string"
promote:
	@if [ -z "$(CAPABILITY)" ]; then echo "ERROR: provide CAPABILITY=\"...\""; exit 1; fi
	@if [ "$(TARGET)" != "core" ] && [ "$(TARGET)" != "strata" ]; then echo "ERROR: TARGET must be 'core' or 'strata'"; exit 1; fi
	@if [ ! -f "$(RECONCILER)" ]; then echo "ERROR: Reconciler not found at $(RECONCILER)"; exit 1; fi
	@echo ">> Discovering & installing MCP for capability: '$(CAPABILITY)' (target=$(TARGET))"
	$(PYTHON) "$(RECONCILER)" \
	  --capability "$(CAPABILITY)" \
	  --target "$(TARGET)" \
	  --proxy-config "$(PROXY_CONFIG)" \
	  --phoenix-root "$(WSL_HOME)/dev/Phoenix"
	@if [ "$(TARGET)" = "core" ]; then \
	  echo ">> Restarting mcp-proxy to load updated clients[]"; \
	  $(PM2) restart mcp-proxy; \
	else \
	  echo ">> Promoted under Strata (no proxy restart required)."; \
	fi

render-proxy:
	@if [ ! -f "$(PROXY_TEMPLATE)" ]; then echo "ERROR: Missing $(PROXY_TEMPLATE)"; exit 1; fi
	$(PYTHON) "$(PROXY_RENDERER)" --template "$(PROXY_TEMPLATE)" --output "$(PROXY_CONFIG)" --env-file "$(ENV_FILE)"

# =========================================================================
# Optional: Blue/Green deployment helpers for zero-downtime proxy swaps
# (Uncomment and wire to your ingress if you want this pattern)
# =========================================================================
# GREEN_PORT ?= 9191
# GREEN_CONFIG ?= $(PROXY_DIR)/config.green.json
# start-green:
# 	@if [ ! -f "$(GREEN_CONFIG)" ]; then echo "ERROR: Missing $(GREEN_CONFIG)"; exit 1; fi
# 	$(PM2) start --name mcp-proxy-green -- \
# 	  "$(PROXY_BIN)" --config "$(GREEN_CONFIG)"
#
# swap-green:
# 	@echo ">> TODO: wire your ingress (cloudflared/nginx) to point to :$(GREEN_PORT)"
# 	@echo ">> After swap: pm2 delete mcp-proxy && pm2 restart mcp-proxy-green --name mcp-proxy"
