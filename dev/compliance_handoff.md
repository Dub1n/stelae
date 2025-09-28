# ChatGPT Connector Action Plan (Stelae)

## 0. Goal

- Bring the public Stelae MCP endpoint into alignment with the compliance reference so ChatGPT’s connector verifier continues past the 30 s /backend-api/aip/connectors/mcp check.
- Focus: trim JSON-RPC handshake to match the minimal (`search`, `fetch`) tool catalog, deliver a functional search response, and validate the handshake with the probe.

## 1. Current State Snapshot

- Manifest already rewritten at the edge (Cloudflare worker) to list only `search` and `fetch`.
- Local proxy build now restricts `initialize`/`tools/list` to the facade pair; production endpoint still exposes ≈40 tools until the proxy is redeployed.
- Search facade returns deterministic sample hits; streamable shim mirrors the same defaults.
- ChatGPT verification currently fails because production still reports the extended catalog.
- Reference document: `dev/chat_gpt_connector_compliant_reference.md`.

## 2. Implementation Steps

### Step 1 – Trim Initialize / Tools List Output

1. Updated `/home/gabri/apps/mcp-proxy/response_helpers.go`:
   - Added `fetchToolDescriptor`, `toolDescriptorFromServer`, and `mergeWithFacadeDefaults` to normalise descriptors.
   - `collectTools` now emits the facade pair only, falling back to static descriptors if upstream servers are unavailable.
2. `buildInitializeResult` and the JSON-RPC handler reuse the filtered results and continue aggregating prompts/resources/templates.
3. Tests (`TestCollectToolsFiltersToFacadeCatalog`, `TestCollectToolsProvidesFacadeFallbacks`) assert schema/required field coverage.
4. **Next action:** rebuild & restart the deployed proxy (`scripts/restart_stelae.sh`) so production matches local behaviour.

*Contingency:* Fallback descriptors ensure initialize does not fail if upstream tool inventory is slow to load.

### Step 2 – Improve Search Stub

1. Added `facade_search.go` and wired JSON-RPC `search`/`tools/call` to return deterministic hits from `buildFacadeSearchPayload`.
2. `scripts/stelae_streamable_mcp.py` exports `STATIC_SEARCH_ENABLED` and `STATIC_SEARCH_HITS`; default behaviour matches the Go facade, with tests covering static and ripgrep code paths.
3. Streamable callers can disable the static set via `STELAE_STREAMABLE_STATIC_SEARCH=0` once real search is ready.

*Contingency:* Keep static hits gated by the env flag to simplify future swap back to ripgrep output.

### Step 3 – Re-run Probe and Archive Output

1. Added `dev/debug/check_connector.py` and `make check-connector` to run the probe, validate tool catalogs/search results, and persist logs under `dev/logs/`.
2. Latest run saved `dev/logs/probe-20250928T1345.log`; validation currently fails against production because it still returns the expanded tool list.
3. After deploying the trimmed proxy, rerun `make check-connector` (override `CONNECTOR_BASE` for staging as needed) and confirm success before notifying OpenAI.

### Step 4 – Communicate with OpenAI (Optional but Recommended)

1. Once production responses match the filtered catalog, capture the session ID from `logs/mcp-proxy.err.log` and the `initialize` payload from the probe log.
2. Share the sanitized payload plus session ID with OpenAI support/community thread for expedited re-verification.

## 3. Testing & Validation Checklist

- `go test ./...`
- `gofmt -w` on modified Go files.
- `~/.venvs/stelae-bridge/bin/python -m pytest tests/test_streamable_mcp.py`
- `CONNECTOR_BASE=<target> make check-connector` (defaults to production URL).
- `curl -s https://mcp.infotopology.xyz/.well-known/mcp/manifest.json | jq` → confirm only `search`, `fetch`.
- `curl -Ns https://mcp.infotopology.xyz/mcp` → confirm `event: endpoint`.
- Optional sanity: `curl -s https://mcp.infotopology.xyz/mcp -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":"T","method":"tools/list"}' | jq` (expectation: `search`, `fetch` once redeployed).

## 4. Troubleshooting Notes

- **Go changes not visible:** run `scripts/restart_stelae.sh` to rebuild/restart proxy.
- **Search stub errors:** ensure required Python deps (e.g. httpx, pytest, trio) are present in `~/.venvs/stelae-bridge`.
- **Probe fails due to missing deps:** install with `~/.venvs/stelae-bridge/bin/pip install httpx pytest trio`.
- **Manifest cached via Cloudflare:** rerun `scripts/push_manifest_to_kv.sh` and purge KV/worker if needed.
- **Automation failures:** inspect `dev/logs/probe-*.log` and `logs/mcp-proxy.err.log` to correlate catalogue mismatches.

### Step 5 – Automate Connector Compliance Checks

1. Go unit tests enforce the filtered tool catalogue and schema requirements.
2. `make check-connector` (backed by `dev/debug/check_connector.py`) runs the JSON-RPC probe, validates outputs, and archives logs.
3. Integrate the make target plus Go/Python tests into CI or `scripts/restart_stelae.sh` before promoting releases.
4. Documentation updated (`dev/chat_gpt_connector_compliant_reference.md`) with automation instructions and failure triage notes.

## 5. Reference Backlinks

- `dev/chat_gpt_connector_compliant_reference.md` – compliance context.
- `docs/chat_gpt_connector_compliance_requirements_spec_v_0.md` – requirement spec.
- `cloudflare/worker/manifest-worker.js` – manifest normalization.
- `/home/gabri/apps/mcp-proxy/response_helpers.go` – initialize/tools logic.
- `scripts/stelae_streamable_mcp.py` – streamable shim.
- `dev/debug/check_connector.py`, `Makefile` – automation entry points.

Maintainer: Stelae Infra – update this plan if the OpenAI verifier behavior changes.
