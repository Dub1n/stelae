# Stelae ↔ Codex MCP Diagnosis Log

## 2025-11-06 – Initial Context Review

- Confirmed from `README.md` and `docs/SPEC-v1.md` that Codex connects through the FastMCP bridge (`scripts/stelae_streamable_mcp.py`) in STDIO mode, which forwards everything to the Go facade on `http://127.0.0.1:9090`. Any Codex failure likely stems from the facade manifest/catalog rather than the bridge exposing a reduced tool list.
- Cloudflare worker only normalises manifest metadata; local Codex should see the raw facade manifest. This implies discrepancies between ChatGPT (public) and Codex (local) more likely originate from local facade config (`config/proxy.json` + overrides) than edge rewrites.
- Diagnostic workflow will require comparing current `config/proxy.json` / `config/tool_overrides.json` with earlier commits where Codex succeeded, then validating via `make check-connector` and Codex’s STDIO launch path (`~/.codex/config.toml`).

## 2025-11-06 – Current Config Snapshot

- `config/proxy.json` now includes the `one_mcp` stdio server alongside the original catalogue. That binary is launched via `/home/gabri/.local/bin/uv`, which will fail noisily if the `1mcp` virtualenv isn’t present; need to confirm whether pm2 is tolerating (or choking on) that process during Codex startup.
- Manifest overrides file currently holds only annotation hints (`readOnlyHint`, `openWorldHint`) but no `enabled` toggles. During the earlier “two tool” testing phase the overrides explicitly set `enabled` flags, so reverting to bare annotations means every downstream server will surface again once the proxy refreshes.
- Codex config at `C:\Users\gabri\.codex\config.toml` still launches the bridge in STDIO mode pointing at `http://127.0.0.1:9090`, so any handshake failure must originate after the bridge starts (either upstream proxy rejection or a server spawn error).

## 2025-11-06 – Reproduction

- With the stack running (`make up`), `codex exec --json` connects but reports “aggregated 4 tools from 2 servers” even though the bridge logs “Proxy catalog bridging enabled with 67 tools”. Output parity mismatch confirms Codex is still seeing the pared-down catalogue.
- Directly querying the bridge via `mcp.client.stdio` shows `list_tools` returning zero entries while the proxy’s `tools/list` endpoint returns 67. The bridge also logs a burst of “Failed to validate notification” warnings for the custom `notifications/server/ready` message, but the session otherwise stays healthy—implying the issue is in tool forwarding rather than transport setup.

## 2025-11-06 – Fix

- `_activate_proxy_handlers` only monkey-patched `FastMCP.list_tools`/`call_tool`/etc., but never re-registered those handlers with `app._mcp_server`. Because the MCP server captured the original methods during `FastMCP.__init__`, `tools/list` still hit the empty `_tool_manager` registry. Rebinding the methods and re-registering them (`server.list_tools()(app.list_tools)` etc.) restores the proxy-backed catalogue.
- After patching, the standalone STDIO probe reports 67 tools (first sample includes `change_directory`, `deep_search_planning`, `delete_file_content`, …) and `codex exec` now logs “aggregated 71 tools from 2 servers,” matching expectations. Remaining warning about `notifications/server/ready` is benign but noted for future cleanup.
- `make check-connector` still passes, so exposing the full tool list to Codex did not regress the public manifest path.

## 2025-11-06 – Ready Notification Cleanup

- Replaced the ad-hoc `notifications/server/ready` payload with a standards-compliant `notifications/message` (level=info, logger=`stelae.streamable_mcp`). MCP clients now treat the readiness hint as a normal log message, eliminating the validation warnings on stderr.
- Verified via the local stdio probe and `codex exec --json` that startup logs are warning-free and the bridge still surfaces 67/71 tools respectively.
