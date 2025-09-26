# ========= Stelae MCP Stack — Makefile =========
# quick targets:
#   make up               # start services via pm2 + save
#   make down             # stop/delete core services
#   make restart-proxy    # restart mcp-proxy after config changes
#   make logs             # tail logs
#   make status           # pm2 table
#   make render-proxy     # render config/proxy.json from template
#   make bridge-venv      # create venv + install bridge deps
#   make bridge-up        # start the streamable http bridge
#   make bridge-down      # stop the bridge
# ===============================================

WSL_HOME        ?= $(HOME)
STELAE_DIR      ?= $(WSL_HOME)/dev/stelae
APPS_DIR        ?= $(WSL_HOME)/apps
PROXY_DIR       ?= $(APPS_DIR)/mcp-proxy
PROXY_BIN       ?= $(PROXY_DIR)/build/mcp-proxy
PROXY_CONFIG    ?= $(STELAE_DIR)/config/proxy.json
PROXY_TEMPLATE  ?= $(STELAE_DIR)/config/proxy.template.json
PROXY_RENDERER  ?= $(STELAE_DIR)/scripts/render_proxy_config.py
ENV_FILE        ?= $(STELAE_DIR)/.env
PM2_ECOSYSTEM   ?= $(STELAE_DIR)/ecosystem.config.js
PYTHON          ?= python3
PM2             ?= pm2
PUBLIC_PORT     ?= 9090
PM2_SERVICES_CORE ?= mcp-bridge mcp-proxy strata docy memory shell 1mcp

BRIDGE_VENV     ?= $(HOME)/.venvs/stelae-bridge
BRIDGE_PY       ?= $(BRIDGE_VENV)/bin/python

.PHONY: up down restart-proxy logs status render-proxy bridge-venv bridge-up bridge-down help

help:
	@echo "Targets:"
	@echo "  up               - Start all services via pm2 and save"
	@echo "  down             - Stop/delete core services"
	@echo "  restart-proxy    - Restart mcp-proxy"
	@echo "  render-proxy     - Render config from template"
	@echo "  bridge-venv      - Create venv + install bridge deps"
	@echo "  bridge-up        - Start the HTTP bridge"
	@echo "  bridge-down      - Stop the HTTP bridge"
	@echo "  logs             - Tail pm2 logs"
	@echo "  status           - Show pm2 status"

up: render-proxy
	@if [ ! -f "$(PM2_ECOSYSTEM)" ]; then echo "ERROR: Missing $(PM2_ECOSYSTEM)"; exit 1; fi
	$(PM2) start "$(PM2_ECOSYSTEM)"
	$(PM2) save
	@echo "Tip (one-time): run 'pm2 startup systemd' to auto-start on boot."

render-proxy:
	@if [ ! -f "$(PROXY_TEMPLATE)" ]; then echo "ERROR: Missing $(PROXY_TEMPLATE)"; exit 1; fi
	$(PYTHON) "$
