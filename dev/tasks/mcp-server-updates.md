# Task: Refresh downstream MCP servers

Related requirement: `dev/progress.md` → Action Items → "Keep integrated MCP servers in sync with upstream changes."

Tags: `#infra`, `#maintenance`

## Checklist

- [ ] Inventory every MCP server we install (core template + starter bundle) and record current commit/version.
- [ ] Fetch upstream updates for each server repo (filesystem, ripgrep, shell controller, Docy, Docy manager, tool aggregator, 1mcp agent/catalog bridge, Fetch, Scrapling, Memory, Strata, etc.).
- [ ] Validate compatibility both ways: ensure newer servers still work with our proxy/overrides, and our overrides/manifests remain accurate (schemas, annotations, hidden tools).
- [ ] Update `config/*` templates/overrides as needed (placeholder values only) and re-run automation (`make render-proxy`, restart scripts) to confirm no tracked drift.
- [ ] Document any upstream changes that require operator action (new env vars, binary rebuilds) in README/AGENTS.
- [ ] Update spec/progress/task entries.
- [ ] Commit with message `infra: refresh mcp server deps` after tests.

## References

- Code: `config/bundles/starter_bundle.json`, `config/proxy.template.json`, `config/tool_overrides.json`, `scripts/install_stelae_bundle.py`, `scripts/stelae_integrator_server.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_install_stelae_bundle.py`, relevant server-specific tests (e.g., Docy manager, integrator).
- Docs: `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md` (call out any behavioral changes).

## Notes

- Aim to refresh *every* server we ship—core template entries and optional bundle entries—so the stack stays in sync with upstream fixes/features.
- If a server update regresses compatibility, capture the findings and decide whether to pin, patch, or temporarily skip it; log the decision in this task’s notes.
- Run the clone smoke test (once available) after updates to ensure the ecosystem still self-manages cleanly.
- If dependency relationships change, regenerate `dev/tasks/*_task_dependencies.json`.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
