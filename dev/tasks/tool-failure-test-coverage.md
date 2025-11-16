# Task: Extend tool failure test coverage for aggregator responses

Related requirement: `docs/templates/progress.md` → Testing Reliability → "Aggregated MCP responses must stay compliant with advertised schemas."

Tags: `#infra`

## Checklist

- [ ] Land schema-aware fixtures for aggregated/stelae tools.
- [ ] Ensure `jsonschema`-based assertions cover new tests.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: short summary` after tests.

## References

- Code: `tests/_tool_override_test_helpers.py`, `tests/test_tool_aggregations.py`, `tests/test_streamable_mcp.py`
- Tests: `source .venv/bin/activate && python -m pytest tests/test_tool_aggregations.py::test_manage_docy_sources_decodes_structured_payload_to_match_schema tests/test_streamable_mcp.py::test_manage_stelae_schema_output tests/test_streamable_mcp.py::test_manage_docy_sources_roundtrip_validates_schema`
- Docs: `dev/stelae-tool-invocation-log.md`, `README.md`, `docs/ARCHITECTURE.md`

## Notes

- Goal is to prevent regressions where proxy/MCP responses stop matching the schema enforced by `config/tool_overrides.json` (recently observed via the invocation log).
- Added helpers in `tests/_tool_override_test_helpers.py` to:
  - Load the canonical overrides and locate each tool’s `inputSchema`/`outputSchema`.
  - Generate representative sample payloads from the schema so tests can assert exact structured results.
- Extended `tests/test_tool_aggregations.py` with `jsonschema`-driven coverage that simulates double-encoded downstream payloads for `manage_docy_sources`. The new test ensures `_decode_json_like` plus response mappings return objects indistinguishable from the overrides.
- Expanded `tests/test_streamable_mcp.py` to import the schema helpers, validate `manage_stelae` outputs, and ensure the FastMCP bridge surfaces `structuredContent` that matches `tool_aggregator.manage_docy_sources`.
- Running these new tests currently hangs before completion because every `asyncio.to_thread(...)` call blocks forever in this WSL sandbox. The minimal reproducer is:

  ```bash
  source .venv/bin/activate && python - <<'PY'
  import asyncio

  async def runner():
      result = await asyncio.to_thread(lambda: "ok")
      print(result)

  asyncio.run(runner())
  PY
  ```

  (`asyncio.to_thread` never resolves and pytest cases stall when they reach `_call_manage_tool`, which wraps `_run_manage_operation` in `asyncio.to_thread`.)
- Next steps for a fresh session:
  1. Fix/replace the blocking `asyncio.to_thread` usage in tests (e.g., monkeypatch `asyncio.to_thread` to run synchronously, or refactor `_call_manage_tool` to accept an injectable executor during tests). Once the helper returns, rerun the targeted pytest subset listed above.
  2. After the schema-aware tests pass, consider broadening coverage to other aggregates listed in `dev/stelae-tool-invocation-log.md` (workspace_fs_read/write, memory_suite, etc.) so every tool with a customized `outputSchema` is asserted in CI.
  3. Update the progress tracker plus run the repo’s overlay workflow before landing.
- Keep this doc open until the blocking `asyncio.to_thread` behavior is resolved and all schema-aware tests pass. Once unblocked, move the checklist items to `[x]` and close out via the usual task log process.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
