# Making the CLI Serve the Full Tool Catalogue

With the proxy now advertising the complete tool catalogue to remote clients, the CLI shim running on WSL still exposes only the two facade tools (`search`, `fetch`) backed by `scripts/stelae_streamable_mcp.py`. The notes below outline what must change if we want the CLI to surface the same rich catalog locally.

## 1. Decide on Fetch Contract

There are two ways to align the CLI fetch behaviour with the remote proxy:

- **Option A – Adopt the ID-based `fetch` contract**
  - Update the CLI shim to expose the same schema as the remote facade: `inputSchema` requiring `id` and returning deterministic fallback content when the id matches the static search catalogue.
  - Adjust `_call_upstream_tool` wiring so CLI-level `fetch` RPC calls translate the incoming `id` to the appropriate upstream invocation (for repositories with local copies of the documents we show in search).
  - Update any consumer code/scripts that still expect `url` to be the parameter.

- **Option B – Preserve `url` based fetch but translate server-side**
  - Keep the CLI contract unchanged (`url` argument) to maintain compatibility with existing workflows.
  - Inject a thin adapter in the CLI shim so if a downstream component expects `id`, the CLI will resolve the id to a URL where possible (e.g., mapping `stelae://` ids to local file paths) before calling upstream `fetch`.
  - Document that CLI usage diverges from the remote contract and may break external connectors that assume the ID-based schema.

## 2. Enumerate Available Tools

Regardless of the fetch strategy, the CLI needs to enumerate all tools seen by the proxy:

- Extend `scripts/stelae_streamable_mcp.py` so that after the shim connects to `PROXY_BASE`, it records every tool name and schema returned by the proxy (or by a new `tools/list` endpoint).
- When defining the CLI `FastMCP` server (`app = FastMCP(...)`), create a corresponding `@app.tool` for each upstream tool, either proxying calls directly or providing stubs where the CLI cannot implement behaviour locally.
- For tools the CLI cannot support (e.g., those requiring network or privileged operations not available in WSL), mark them with appropriate annotations or keep them omitted, but document the gap.

## 3. Proxy Calls from CLI to Upstream

Each CLI-exposed tool that is simply a pass-through to the Go proxy must:

- Serialize incoming arguments and forward them via `_call_upstream_tool(server_name, tool_name, arguments)`.
- Handle streaming responses and error propagation consistent with the MCP spec.
- Ensure HTTP/SSE timeouts in `_call_upstream_tool` reflect the larger catalogue (some tools may take longer than the current defaults).

## 4. Update CLI Manifest and tests

- Regenerate the CLI manifest by running the shim locally and capturing `/.well-known/mcp/manifest.json`. Ensure it matches the remote catalog (or document known deltas).
- Add tests (unit or functional) for the shim to confirm:
  - All upstream tools appear in the CLI manifest.
  - `tools/list` results from the CLI include search/fetch and any other proxies.
  - Fetch contract behaves as decided in step 1.

## 5. Communication and Documentation

- Update CLI user documentation so developers know which tools are available locally and how the fetch semantics work.
- If Option A (ID-based fetch) is adopted, provide a migration guide for CLI scripts that currently call `fetch(url=...)`.

## Summary Checklist

- [ ] Choose fetch contract alignment strategy (ID-based vs. legacy URL adapter).
- [ ] Modify `scripts/stelae_streamable_mcp.py` to enumerate and expose the full tool catalogue via FastMCP decorators or dynamic registration.
- [ ] Update `_call_upstream_tool` routing and timeouts to handle the expanded set.
- [ ] Regenerate CLI manifest/tests to ensure catalogue parity.
- [ ] Document new behaviour for CLI users.
