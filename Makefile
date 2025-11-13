# path: stelae/Makefile
# ========= Stelae MCP Stack — Makefile =========
# quick targets:
#   make up               # render config + start services via pm2 + save
#   make down             # stop/delete core services
#   make restart-proxy    # restart mcp-proxy after config changes
#   make render-proxy     # render config/proxy.json from template
#   make logs             # tail logs
#   make status           # pm2 table
# ===============================================

WSL_HOME        ?= $(HOME)
STELAE_DIR      ?= $(WSL_HOME)/dev/stelae
APPS_DIR        ?= $(WSL_HOME)/apps
STELAE_CONFIG_HOME ?= $(HOME)/.config/stelae
STELAE_STATE_HOME ?= $(STELAE_CONFIG_HOME)/.state
PROXY_DIR       ?= $(APPS_DIR)/mcp-proxy
PROXY_BIN       ?= $(PROXY_DIR)/build/mcp-proxy
PROXY_CONFIG    ?= $(STELAE_STATE_HOME)/proxy.json
TOOL_OVERRIDES_PATH ?= $(STELAE_STATE_HOME)/tool_overrides.json
PROXY_TEMPLATE  ?= $(STELAE_DIR)/config/proxy.template.json
PROXY_RENDERER  ?= $(STELAE_DIR)/scripts/render_proxy_config.py
ENV_FILE        ?= $(STELAE_DIR)/.env
PM2_ECOSYSTEM   ?= $(STELAE_DIR)/ecosystem.config.js
PYTHON          ?= python3
PM2             ?= pm2
CF_TEMPLATE 	?= $(STELAE_DIR)/ops/cloudflared.template.yml
CF_OUTPUT   	?= $(STELAE_CONFIG_HOME)/cloudflared.yml
CF_RENDERER 	?= $(STELAE_DIR)/scripts/render_cloudflared_config.py
BRIDGE_PYTHON   ?= $(HOME)/.venvs/stelae-bridge/bin/python
CONNECTOR_PROBE ?= $(STELAE_DIR)/dev/debug/chatgpt_connector_probe.py
CONNECTOR_BASE  ?= https://mcp.infotopology.xyz/mcp
CONNECTOR_TIMEOUT ?= 20
PROBE_LOG_DIR   ?= $(STELAE_DIR)/dev/logs
CHECK_CONNECTOR_SCRIPT ?= $(STELAE_DIR)/dev/debug/check_connector.py
DISCOVER_QUERY ?=
DISCOVER_TAGS ?=
DISCOVER_PRESET ?=
DISCOVER_LIMIT ?= 10
DISCOVER_MIN_SCORE ?=
DISCOVER_APPEND ?= 1
DISCOVER_DRY_RUN ?= 0

.PHONY: render-cloudflared
render-cloudflared:
	@if [ ! -f "$(CF_TEMPLATE)" ]; then echo "ERROR: Missing $(CF_TEMPLATE)"; exit 1; fi
	$(PYTHON) "$(CF_RENDERER)" --template "$(CF_TEMPLATE)" --output "$(CF_OUTPUT)" --env-file "$(ENV_FILE)" --fallback-env "$(STELAE_DIR)/.env.example"
	@echo "Rendered $(CF_OUTPUT). Point CF_CONF to this path for pm2 cloudflared."

# convenience combo
.PHONY: up-with-tunnel
up-with-tunnel: render-proxy render-cloudflared up
	@echo "Cloudflared config ready. Ensure CF_CONF points to $(CF_OUTPUT) before pm2 start --only cloudflared."

.PHONY: up down restart-proxy logs status render-proxy help discover-servers verify-clean

help:
	@echo "Targets:"
	@echo "  up               - Render config, start services via pm2, save"
	@echo "  down             - Stop/delete core services"
	@echo "  restart-proxy    - Restart mcp-proxy"
	@echo "  render-proxy     - Render config from template"
	@echo "  logs             - Tail pm2 logs"
	@echo "  status           - Show pm2 status"
	@echo "  discover-servers - Run manage_stelae discover_servers via inline CLI"

up: render-proxy
	@if [ ! -f "$(PM2_ECOSYSTEM)" ]; then echo "ERROR: Missing $(PM2_ECOSYSTEM)"; exit 1; fi
	$(PM2) start "$(PM2_ECOSYSTEM)"
	$(PM2) save
	@echo "Tip (one-time): run 'pm2 startup systemd -u $${USER} --hp \"$${HOME}\"' to auto-start on boot."

down:
	-$(PM2) delete mcp-proxy strata docy memory shell cloudflared || true
	$(PM2) save || true

restart-proxy: render-proxy
	$(PM2) restart mcp-proxy --update-env
	$(PM2) save || true

render-proxy:
	@if [ ! -f "$(PROXY_TEMPLATE)" ]; then echo "ERROR: Missing $(PROXY_TEMPLATE)"; exit 1; fi
	$(PYTHON) "$(STELAE_DIR)/scripts/process_tool_aggregations.py"
	$(PYTHON) "$(PROXY_RENDERER)" --template "$(PROXY_TEMPLATE)" --output "$(PROXY_CONFIG)" --env-file "$(ENV_FILE)" --fallback-env "$(STELAE_DIR)/.env.example"

logs:
	$(PM2) logs --lines 120

status:
	$(PM2) status

.PHONY: check-connector
check-connector:
	@$(BRIDGE_PYTHON) "$(CHECK_CONNECTOR_SCRIPT)" \
		--server-url "$(CONNECTOR_BASE)" \
		--timeout "$(CONNECTOR_TIMEOUT)" \
		--probe "$(CONNECTOR_PROBE)" \
		--log-dir "$(PROBE_LOG_DIR)"

discover-servers:
	@DISCOVER_QUERY="$(DISCOVER_QUERY)" \
		DISCOVER_TAGS="$(DISCOVER_TAGS)" \
		DISCOVER_PRESET="$(DISCOVER_PRESET)" \
		DISCOVER_LIMIT="$(DISCOVER_LIMIT)" \
		DISCOVER_MIN_SCORE="$(DISCOVER_MIN_SCORE)" \
		DISCOVER_APPEND="$(DISCOVER_APPEND)" \
		DISCOVER_DRY_RUN="$(DISCOVER_DRY_RUN)" \
		$(PYTHON) scripts/discover_servers_cli.py

verify-clean:
	@./scripts/verify_clean_repo.sh
