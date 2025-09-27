# ========= Stelae MCP Stack — Makefile =========

WSL_HOME          ?= $(HOME)
STELAE_DIR        ?= $(WSL_HOME)/dev/stelae
APPS_DIR          ?= $(WSL_HOME)/apps
PROXY_DIR         ?= $(APPS_DIR)/mcp-proxy
PROXY_BIN         ?= $(PROXY_DIR)/build/mcp-proxy
PROXY_CONFIG      ?= $(STELAE_DIR)/config/proxy.json
PROXY_TEMPLATE    ?= $(STELAE_DIR)/config/proxy.template.json
PROXY_RENDERER    ?= $(STELAE_DIR)/scripts/render_proxy_config.py
ENV_FILE          ?= $(STELAE_DIR)/.env
ENV_EXAMPLE       ?= $(STELAE_DIR)/.env.example
PM2_ECOSYSTEM     ?= $(STELAE_DIR)/ecosystem.config.js
PYTHON            ?= python3
PM2               ?= pm2

.PHONY: up down restart-proxy logs status render-proxy kill-bridge help

help:
	@echo "Targets:"
	@echo "  render-proxy     - Render config/proxy.json from template using .env"
	@echo "  up               - Start facade + servers via pm2 and save"
	@echo "  restart-proxy    - Restart mcp-proxy"
	@echo "  kill-bridge      - Remove legacy mcp-bridge process (if any)"
	@echo "  logs             - Tail pm2 logs for mcp-proxy"
	@echo "  status           - Show pm2 status"
	@echo "  down             - Stop/delete mcp-proxy and servers"

render-proxy:
	@test -f "$(PROXY_TEMPLATE)" || (echo "ERROR: Missing $(PROXY_TEMPLATE)"; exit 1)
	@test -f "$(PROXY_RENDERER)"  || (echo "ERROR: Missing $(PROXY_RENDERER)"; exit 1)
	$(PYTHON) "$(PROXY_RENDERER)" \
	  --template "$(PROXY_TEMPLATE)" \
	  --output   "$(PROXY_CONFIG)" \
	  --env-file "$(ENV_FILE)" \
	  --fallback-env "$(ENV_EXAMPLE)"

up: render-proxy
	@test -f "$(PM2_ECOSYSTEM)" || (echo "ERROR: Missing $(PM2_ECOSYSTEM)"; exit 1)
	$(PM2) start "$(PM2_ECOSYSTEM)"
	$(PM2) save
	@echo "Tip (one-time): pm2 startup systemd -u $$USER --hp $$HOME && pm2 save"

restart-proxy:
	$(PM2) restart mcp-proxy --update-env
	$(PM2) save

kill-bridge:
	-$(PM2) delete mcp-bridge

logs:
	$(PM2) logs mcp-proxy --lines 150

status:
	$(PM2) status

down:
	-$(PM2) delete mcp-proxy strata docy memory shell fetch github
	$(PM2) save
