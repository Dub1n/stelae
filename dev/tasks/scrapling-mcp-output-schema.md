# Task: Scrapling MCP integration – output schema mismatch and connectivity

## Summary

Invocations of Scrapling MCP tools `s_fetch_page` and `s_fetch_pattern` return the error:

- “Output validation error: outputSchema defined but no structured output returned”

Additionally, attempting to invoke via a named server produced:

- “Server 'scrapling-fetch' not found or not connected” (intermittent, resolved after enabling the server)

Root cause: the Scrapling MCP server (scrapling-fetch-mcp) returns a single string payload ("METADATA: {json}\n\n[content]") rather than a structured object. Our Go MCP proxy expects tool outputs to satisfy a structured `outputSchema`, hence it rejects plain strings.

**Implementation note (2025-02-15):** we are proceeding with a shim-style fix inside the Stelae repo, leaving the upstream Scrapling MCP server untouched for now. If this approach fails to resolve the issue, we will revisit the upstream adjustment option.

### Status update (2025-11-10)

- ✅ The Go proxy now handles schema adaptation inline, so the production config points Scrapling straight at `uvx scrapling-fetch-mcp --stdio` again (`config/proxy.template.json:110-138`, README.md:21). No auxiliary shim process runs under pm2.
- ✅ Scrapling’s latest release returns structured `{metadata, content}` payloads, and the proxy records them as pass-through calls (`config/tool_schema_status.json:35-44` shows `last_adapter: "pass_through"` for both tools).
- ✅ `config/tool_overrides.json` now records the canonical `{metadata, content}` schema for `s_fetch_page` and `s_fetch_pattern`, and both README.md + `docs/ARCHITECTURE.md` call out that file as the single source of truth.
- ✅ The FastMCP bridge exposes a dedicated `per_m2_price` helper tool that calls Scrapling, parses matches, and surfaces currency/value/snippet metadata so downstream docs can quote per‑m² figures without ad-hoc scripts. Tests live in `tests/test_per_m2_price_tool.py`.
- ✅ Call-path failures now include Scrapling bootstrap guidance (run `uv tool install …` then `uvx --from scrapling-fetch-mcp scrapling install`) and have regression coverage for the missing-browser path.
- ✅ The legacy Python shim (`scripts/mcp_output_shim.py`) and its tests were removed entirely; the Go adapter + overrides cover every server, so the shim is no longer referenced anywhere in docs or templates.
  Remaining work (tracked elsewhere): keep monitoring runtime telemetry in `config/tool_schema_status.json` for unexpected regressions.

### Current Status (Shim V1) *(historical record; superseded by the adapter above)*

- [x] Added `scripts/mcp_output_shim.py`, a FastMCP adapter that launches `scrapling-fetch-mcp`, rewrites `s_fetch_page` / `s_fetch_pattern` descriptors to advertise a `{metadata, content}` schema, and normalizes raw `METADATA: {...}\n\n<body>` strings into structured payloads.
- [x] Updated `config/proxy.template.json` (rendered into `config/proxy.json`) so the `scrapling` entry now invokes the shim via `python3 scripts/mcp_output_shim.py`.
- [x] Added unit coverage in `tests/test_scrapling_shim.py` to lock parsing behaviour before generalizing the adapter.
- [x] Upstream Go proxy now supports schema overrides (input/output) via `config/tool_overrides.json`, so once a tool is flagged as wrapped we can advertise the correct schema without bespoke code.
- [x] General-purpose fallback: expanded the shim + proxy overrides so any MCP server can be auto-detected, wrapped once, and have its schema advertised via overrides without touching upstream code. State is persisted in `config/tool_schema_status.json`, and overrides are patched automatically (with log guidance to rerun `make render-proxy` so manifests catch up).

## Environment

- Agent: Codex CLI (danger-full-access; network enabled)
- MCP proxy: Go-based, flattens tool names (`s_fetch_page`, `s_fetch_pattern`) and enforces output schema
- Scrapling server: https://github.com/cyberchitta/scrapling-fetch-mcp (Python FastMCP)
- Verified code refs:
  - `src/scrapling_fetch_mcp/mcp.py`: tools return `str`
  - `src/scrapling_fetch_mcp/_fetcher.py`: returns string with `METADATA: {json}\n\n…`

## Reproduction

1) With server enabled, call either tool (any URL) and get schema error:

    - `s_fetch_page { url: "https://example.com", mode: "basic", format: "markdown", max_length: 5000 }`
    - `s_fetch_pattern { url: "https://roundwood.com/decking/...", search_pattern: "£\\s?\\d+[\\d,.]*.*?(?:per\\s*m²|per\\s*m2|per\\s*m)" }`

    Observed: “Output validation error: outputSchema defined but no structured output returned”.

2) Before the server was enabled, the proxy returned: “Server 'scrapling-fetch' not found or not connected”. After enabling, the schema error persists.

## Impact

- Blocks use of Scrapling tools for dynamic price capture and pattern extraction (e.g., Ipe/Cumaru/Garapa pricing per m²) needed for `docs/timber-options.md` updates.

## Root Cause Analysis

- Scrapling tool outputs are plain strings, e.g. `METADATA: {json}\n\n[content]`.
- Our proxy enforces structured tool outputs (object/JSON) per registered `outputSchema`.
- Mismatch leads to validation failure.

### Additional observations from the current stack

- The manifest published by the Go proxy (`http://127.0.0.1:9090/.well-known/mcp/manifest.json`) shows that FastMCP auto-generated an `outputSchema` requiring an **object with a `result` string property** for both tools:

  ```json
  {
    "name": "s_fetch_page",
    "outputSchema": {
      "type": "object",
      "properties": {
        "result": { "title": "Result", "type": "string" }
      },
      "required": ["result"]
    }
  }
  ```

  Returning a raw string therefore violates the schema and triggers `outputSchema defined but no structured output returned`.
- We already load Scrapling through the proxy (`config/proxy.template.json:68`), so connectivity issues appear only when the pm2 process is down. The recent `run_restart_stelae.sh` change ensures `cloudflared` restarts automatically, reducing the “Server not found” symptom for external clients.

## Remediation Options

A) Update Scrapling MCP to return structured JSON

- Change both tools’ return values from `str` to an object of shape:

  {
    "metadata": {
      "total_length": int,
      "retrieved_length": int,
      "is_truncated": bool,
      "percent_retrieved": float,
      "start_index": int?,
      "match_count": int?
    },
    "content": "..."
  }

- Minimal code changes:
  - In `_fetcher.py`, replace string assembly with a dict return (parse the existing metadata values directly without stringifying then re-parsing).
  - In `mcp.py`, keep signatures the same but return `dict` instead of `str`.
  - Version bump + changelog indicating output format change.

- Pros: Aligns with proxy expectations; portable; explicit metadata.
- Cons: Upstream change required; small breaking change for clients relying on the string format.

B) Relax proxy schema for Scrapling tools (accept `string` or mark FREEFORM)

- Configure the Go MCP proxy to treat `s_fetch_page` and `s_fetch_pattern` as freeform/text outputs.
- Pros: No server change; fastest path.
- Cons: Special-casing in proxy; less structured handling downstream.

  Implementation sketch (if chosen):
  - In `apps/mcp-proxy/http.go`, detect tool descriptors where `outputSchema.type == "string"` or a trivial `{result:string}` object and enable a reusable adapter.
  - Dispatch flow (pseudocode):

    ```go
    result, err := client.callTool(...)
    if schemaErr(err) && isStringCandidate(toolDescriptor) {
        if wrapped := wrapStringResult(result); wrapped != nil {
            rememberAdapter(tool)
            return wrapped, nil
        }
    }
    return result, err
    ```

  - `wrapStringResult` first checks for the `METADATA:` prefix. If present, it parses the JSON metadata and returns `{ "metadata": parsed, "content": body }`. Otherwise it falls back to `{ "result": raw }`.
  - `rememberAdapter` stores a flag (e.g., in `ToolOverrideSet` or an in-memory map) so the adapter runs immediately on subsequent invocations without re-triggering the error path.

C) Adapter shim in proxy (generalized from `scripts/mcp_output_shim.py`)

- Extend the shim so it can wrap any downstream tool, defaulting to the generic `{ "result": "..." }` shape while still supporting specialized parsers (e.g., Scrapling’s `{metadata, content}`) when configured.
- Teach the Go proxy overrides to accept `outputSchema` (and `inputSchema`) entries, letting us advertise the wrapped shape via `config/tool_overrides.json` once a tool is known to require it. [x]
- Add a persistence file (`config/tool_schema_status.json`) recording per-tool states (`unknown`, `pass_through`, `wrapped`, `failed`). [x]
- Runtime flow (implemented in `scripts/mcp_output_shim.py`):
  - On first call (`unknown`): run tool normally. If the downstream server already provides structured content, mark `pass_through`. Otherwise wrap the raw text using the configured wrapper (default `{ "result": "..." }`, Scrapling keeps `{metadata, content}`), retry the response, and persist `wrapped`.
  - On shim success: update overrides with the new schema and log that a restart (`make render-proxy` + `scripts/run_restart_stelae.sh --full`) is required to advertise the change. Future calls go straight through the shim with no extra detection.
  - On repeated failure: persist `failed` and surface the upstream error (with guidance to reset/remove the state entry once the root cause is fixed).
- Pros: Transparent to clients; once a tool is classified the manifest + `tools/list` always advertise the correct schema. No upstream edits required.
- Cons: Requires changes to the Go proxy (override support + result capture) and a new persistence workflow.

## Recommended Fix (A)

Implement structured JSON return in scrapling-fetch-mcp.

Additionally, generalize the newly landed `scripts/mcp_output_shim.py` so the Go proxy (or the FastMCP bridge) can delegate any offending server to it on demand. The adapter should activate automatically when a call fails with the schema error, replay the call through the shim to produce the configured wrapper (generic `{result: ...}` by default, `{metadata, content}` for Scrapling), remember that the tool now requires wrapping, and skip the extra work once that server emits compliant JSON on its own.

### Patch outline (upstream)

- File: `src/scrapling_fetch_mcp/_fetcher.py`

  Replace string return with dict:

  ```python
  # after computing metadata fields
  metadata = {
      "total_length": total_length,
      "retrieved_length": len(truncated_content),
      "is_truncated": is_truncated,
      "percent_retrieved": round((len(truncated_content) / total_length) * 100, 2) if total_length else 100,
      "start_index": start_index,
  }
  return {"metadata": metadata, "content": truncated_content}
  ```

  And for pattern:

  ```python
  metadata = {
      "total_length": original_length,
      "retrieved_length": len(truncated_content),
      "is_truncated": is_truncated,
      "percent_retrieved": round((len(truncated_content) / original_length) * 100, 2) if original_length else 100,
      "match_count": match_count,
  }
  return {"metadata": metadata, "content": truncated_content}
  ```

- File: `src/scrapling_fetch_mcp/mcp.py`

  Keep tool signatures; they can return dict. No consumer code changes beyond return type.
- After the change, re-run `uv tool install --upgrade scrapling-fetch-mcp` on the host and restart the proxy (`scripts/run_restart_stelae.sh --full`) so pm2 picks up the new binary.
- Guard against legacy clients: if both upstream JSON and the proxy adapter are deployed, the adapter should detect that the downstream result is already an object and no longer wrap it.

### Acceptance Criteria

- Calling `s_fetch_page` returns an object with `metadata` and `content` keys; no validation errors in the proxy.
- `metadata.percent_retrieved` reflects `content` size vs total.
- `s_fetch_pattern` returns `match_count` and matched snippets in `content` (still chunked with positions or simplified text—either is fine if documented).
- Works across modes: `basic`, `stealth`, `max-stealth`.
- Proxy adapter persists per tool after first successful fallback (e.g., map keyed by tool name) so subsequent calls bypass the detection step.
- Generic fallback uses `{ "result": "..." }` wrapping unless a per-tool override specifies a richer structure (e.g., Scrapling keeps `{metadata, content}`).
- Once the general-purpose shim is in place, tools that succeed on the first attempt are marked “pass-through” so they avoid unnecessary wrapping, while tools that fail once are permanently routed through the shim until they emit valid structured output again (and the override schema/manifest stay in sync).

## Validation Plan

- Smoke tests (through proxy):
  - `s_fetch_page` on `https://example.com` (basic, markdown) → object returned.
  - `s_fetch_pattern` on a known page with prices (regex for `£ … per m²`), e.g. Round Wood Ipe/Garapa pages.
- Large pages: verify `max_length` truncation + `start_index` pagination.
- HTML vs markdown switch: format toggles content mode; markdown strips scripts/styles.

## Operational Checks

- Ensure Scrapling browsers are installed (first-time cost):
  - `uv tool install scrapling-fetch-mcp`
  - `uvx --from scrapling-fetch-mcp scrapling install`
- MCP config wiring (Claude Desktop example):

  ```json
  {
    "mcpServers": {
      "scrapling-fetch": {
        "command": "uvx",
        "args": ["scrapling-fetch-mcp"]
      }
    }
  }
  ```

- Restart host app after config changes.

## Rollout

1) Implement upstream JSON return + bump version → 0.2.1.
2) Update proxy allowlist/metadata if needed (names unchanged: `s_fetch_page`, `s_fetch_pattern`).
3) Validate in this environment (Codex CLI + Go proxy) against 3 target merchant pages.
4) Document new output in internal usage notes (Stelae tools catalog).

## Follow‑ups (status)

- [x] Add small JSON schema doc to `README.md` (metadata fields, content semantics). *Documented the override location + helper flow in README.md and `docs/ARCHITECTURE.md`.*
- [x] Optional: expose a dedicated `per_m2_price` helper tool later (stretch). *Shipped via the FastMCP bridge with regression coverage.*
- [x] Add tests for install-not-ready conditions (browser bootstrap), ensuring friendly errors. *`tests/test_per_m2_price_tool.py` asserts we emit human-readable instructions when Scrapling fails to start.*

## Owners & Timeline

- Proposed owner: Integrations / MCP tooling
- ETA: 0.5 day for code + tests; 0.5 day validation; total 1 day.

## Links

- Repo: https://github.com/cyberchitta/scrapling-fetch-mcp
- Code references:
  - `src/scrapling_fetch_mcp/mcp.py`
  - `src/scrapling_fetch_mcp/_fetcher.py`
  - `src/scrapling_fetch_mcp/_scrapling.py` (browser client)
