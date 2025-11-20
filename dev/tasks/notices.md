# Task: Stelae notice queue

Related requirement: `dev/progress.md` → notice-delivery → "Deliver a one-shot notice queue so MCP tools can summarize bootstrap fixes or bundle warnings without spamming users."

Tags: `#infra`

## Checklist

- [ ] Detect when bootstrap helpers recreate/move required config/state files and record a concise notice entry.
- [ ] Persist notices under `${STELAE_STATE_HOME}` (e.g., `notices.json`) with enough metadata for grouping yet easy truncation.
- [ ] Teach `manage_stelae` (and future MCP control tools) to prepend + clear pending notices in their first response.
- [ ] Document the notice flow in README/docs so users know why a message appears only once.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: add MCP notice queue` after tests.

## References

- Code: `scripts/setup_env.py`, `scripts/run_restart_stelae.sh`, `scripts/stelae_integrator_server.py`, `stelae_lib/*` (notice helpers TBD)
- Tests: `tests/test_streamable_mcp.py`, `tests/test_tool_aggregations.py`, new unit coverage for notice persistence/consumption
- Docs: README.md, docs/e2e_clone_smoke_test.md, docs/ARCHITECTURE.md

## Notes

- Notices should be extremely brief (one-line) and only emitted once per change; queue can drop entries that exceed a small cap.
- Bundle installer and future automation can reuse the same notice helper to report relocations or skipped steps.
- Consider redacting sensitive paths before storing notices since the queue may be surfaced to remote MCP clients.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
