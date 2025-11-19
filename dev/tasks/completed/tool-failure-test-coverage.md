# Task: Extend tool failure test coverage for aggregator responses

Related requirement: `docs/templates/progress.md` → Testing Reliability → "Aggregated MCP responses must stay compliant with advertised schemas."

Tags: `#infra`

## Checklist

- [x] Land schema-aware fixtures for aggregated/stelae tools.
- [x] Ensure `jsonschema`-based assertions cover new tests.
- [x] Update spec/progress/task file.
- [ ] Commit with message `project: short summary` after tests.

## References

- Code: `tests/_tool_override_test_helpers.py`, `tests/test_tool_aggregations.py`, `tests/test_streamable_mcp.py`
- Tests: `source .venv/bin/activate && python -m pytest tests/test_tool_aggregations.py tests/test_streamable_mcp.py`
- Docs: `dev/stelae-tool-invocation-log.md`, `README.md`, `docs/ARCHITECTURE.md`

## Notes

- Goal is to prevent regressions where proxy/MCP responses stop matching the schema enforced by `config/tool_overrides.json` (recently observed via the invocation log).
- Added helpers in `tests/_tool_override_test_helpers.py` to:
  - Load the canonical overrides and locate each tool’s `inputSchema`/`outputSchema`.
  - Generate representative sample payloads from the schema so tests can assert exact structured results.
- Extended `tests/test_tool_aggregations.py` with `jsonschema`-driven coverage that simulates double-encoded downstream payloads for aggregated tools such as `workspace_fs_read`. The new tests ensure `_decode_json_like` plus response mappings return objects indistinguishable from the overrides.
- Expanded `tests/test_streamable_mcp.py` to import the schema helpers, validate `manage_stelae` outputs, and ensure the FastMCP bridge surfaces `structuredContent` that matches the tracked aggregate definitions.
- Running these new tests previously hung because every `asyncio.to_thread(...)` call blocked in this WSL sandbox. The helper hook (`_MANAGE_THREAD_RUNNER`) plus the autouse fixture in `tests/test_streamable_mcp.py` keep the runtime async behavior intact while letting tests bypass the deadlock. The minimal reproducer below now completes when pointed at the helper instead of `asyncio.to_thread`:

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
  - [x] Fix/replace the blocking `asyncio.to_thread` usage in tests (done by introducing `_MANAGE_THREAD_RUNNER` in `scripts/stelae_streamable_mcp.py` plus an autouse fixture in `tests/test_streamable_mcp.py` that forces synchronous execution so schema-aware cases no longer hang).
  - [x] After the schema-aware tests pass, consider broadening coverage to other aggregates listed in `dev/stelae-tool-invocation-log.md` (workspace_fs_read/write, memory_suite, etc.) so every tool with a customized `outputSchema` is asserted in CI. We deferred the new parameterized test until the intended/live catalog work lands (`dev/intended-catalog-plan.md`), because that flow will materialize downstream schemas into `intended_catalog.json`. Once the config realignment is complete, add coverage that reads from the intended catalog instead of duplicating schemas directly in the aggregate descriptors.
  - [x] Update the progress tracker plus run the repo’s overlay workflow before landing. (Default + local scopes rerun on 2025-11-16 followed by `scripts/run_restart_stelae.sh --keep-pm2 --no-bridge --no-cloudflared --skip-populate-overrides`.)
- Keep this doc open until the schema-aware tests execute cleanly and the remaining aggregate coverage additions land. The future documentation catalog aggregate will land in the starter bundle overlays; tests load descriptors from `bundles/starter/catalog.json` so a bare clone without the optional bundle still exercises the schemas that remain.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
