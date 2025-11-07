# Task: Scrapling MCP integration – output schema mismatch and connectivity

## Summary

Invocations of Scrapling MCP tools `s_fetch_page` and `s_fetch_pattern` return the error:

- “Output validation error: outputSchema defined but no structured output returned”

Additionally, attempting to invoke via a named server produced:

- “Server 'scrapling-fetch' not found or not connected” (intermittent, resolved after enabling the server)

Root cause: the Scrapling MCP server (scrapling-fetch-mcp) returns a single string payload ("METADATA: {json}\n\n[content]") rather than a structured object. Our Go MCP proxy expects tool outputs to satisfy a structured `outputSchema`, hence it rejects plain strings.

**Implementation note (2025-02-15):** we are proceeding with a shim-style fix inside the Stelae repo, leaving the upstream Scrapling MCP server untouched for now. If this approach fails to resolve the issue, we will revisit the upstream adjustment option.

### Current Status (Shim V1)

- ✅ Added `scripts/scrapling_shim_mcp.py`, a FastMCP adapter that launches `scrapling-fetch-mcp`, rewrites `s_fetch_page` / `s_fetch_pattern` descriptors to advertise a `{metadata, content}` schema, and normalizes raw `METADATA: {...}\n\n<body>` strings into structured payloads.
- ✅ Updated `config/proxy.template.json` (rendered into `config/proxy.json`) so the `scrapling` entry now invokes the shim via `python3 scripts/scrapling_shim_mcp.py`.
- ✅ Added unit coverage in `tests/test_scrapling_shim.py` to lock parsing behaviour before generalizing the adapter.
- 🔜 General-purpose fallback: reuse the shim runtime by parameterizing target tools and activation flow so any downstream server that fails schema validation can be routed through the same wrapper without per-server code.

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
- We already load Scrapling through the proxy (`config/proxy.template.json:68`), so connectivity issues appear only when the pm2 process is down. The recent `restart_stelae.sh` change ensures `cloudflared` restarts automatically, reducing the “Server not found” symptom for external clients.

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

C) Adapter shim in proxy (generalized from `scripts/scrapling_shim_mcp.py`)

- Reuse the existing shim runtime by parameterizing which servers/tools it watches (e.g., env vars `SHIM_SERVER`, `SHIM_TOOLS`, metadata prefix hints).
- When the proxy reports `outputSchema defined but no structured output returned`, reroute that tool through the shim and record the decision so future calls go straight through the adapter without another failure.
- When a tool successfully emits structured data directly (either because the upstream server was fixed or never needed wrapping), flag it as “clean” so the shim can bypass parsing entirely and reduce overhead.
- Pros: Transparent to clients; no per-server code once the shim is configurable.
- Cons: Adds bookkeeping to record first-failure / first-success transitions.

## Recommended Fix (A)

Implement structured JSON return in scrapling-fetch-mcp.

Additionally, generalize the newly landed `scripts/scrapling_shim_mcp.py` so the Go proxy (or the FastMCP bridge) can delegate any offending server to it on demand. The adapter should activate automatically when a call fails with the schema error, replay the call through the shim to produce `{ metadata, content }`, remember that the tool now requires wrapping, and skip the extra work once that server emits compliant JSON on its own.

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
- After the change, re-run `uv tool install --upgrade scrapling-fetch-mcp` on the host and restart the proxy (`scripts/restart_stelae.sh --full`) so pm2 picks up the new binary.
- Guard against legacy clients: if both upstream JSON and the proxy adapter are deployed, the adapter should detect that the downstream result is already an object and no longer wrap it.

### Acceptance Criteria

- Calling `s_fetch_page` returns an object with `metadata` and `content` keys; no validation errors in the proxy.
- `metadata.percent_retrieved` reflects `content` size vs total.
- `s_fetch_pattern` returns `match_count` and matched snippets in `content` (still chunked with positions or simplified text—either is fine if documented).
- Works across modes: `basic`, `stealth`, `max-stealth`.
- Proxy adapter persists per tool after first successful fallback (e.g., map keyed by tool name) so subsequent calls bypass the detection step.
- Once the general-purpose shim is in place, tools that succeed on the first attempt are marked “pass-through” so they avoid unnecessary wrapping, while tools that fail once are permanently routed through the shim until they emit valid structured output again.

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

## Follow‑ups

- Add small JSON schema doc to `README.md` (metadata fields, content semantics).
- Optional: expose a dedicated `per_m2_price` helper tool later (stretch).
- Add tests for install-not-ready conditions (browser bootstrap), ensuring friendly errors.

## Owners & Timeline

- Proposed owner: Integrations / MCP tooling
- ETA: 0.5 day for code + tests; 0.5 day validation; total 1 day.

## Links

- Repo: https://github.com/cyberchitta/scrapling-fetch-mcp
- Code references:
  - `src/scrapling_fetch_mcp/mcp.py`
  - `src/scrapling_fetch_mcp/_fetcher.py`
  - `src/scrapling_fetch_mcp/_scrapling.py` (browser client)
