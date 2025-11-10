# Task: Modularize core stack & starter bundle

Related requirement: `docs/current/progress.md` → Configuration Hygiene → "Keep shipped defaults generic; let per-instance customisation live outside the repo while remaining auto-loaded."

Tags: `#infra`, `#docs`

## Checklist

- [x] Define the minimal "core" Stelae stack (proxy + integrator/self-management dependencies) and document which servers/configs are required for a functional clone.
- [x] Trim tracked templates/manifests so only the core servers ship out of the box; move Docy, tool aggregator, Memory, Strata, etc. into an optional bundle.
- [x] Create a curated starter bundle (JSON descriptors matching 1mcp output) and an installer CLI/script that feeds those descriptors to `manage_stelae install_server`.
- [x] Relocate Docy manager aggregation + non-core tool overrides into `${STELAE_CONFIG_HOME}` overlays when the starter bundle is applied; ensure existing users retain their local overlays.
- [x] Update README/AGENTS/ARCHITECTURE with a "core vs starter pack" quick-start flow, including guidance for running the installer script.
- [x] Extend repo hygiene/tests to ensure the core templates remain slim and that optional bundles stay out of git (`tests/test_repo_sanitized.py` or new coverage).
- [x] Update spec/progress/task entries with the new modular strategy.
- [x] Commit with message `infra: modularize stelae core stack` after tests.

## References

- Code: `config/proxy.template.json`, `config/tool_overrides.json`, `config/tool_aggregations.json`, `scripts/run_restart_stelae.sh`, `scripts/stelae_integrator_server.py`, potential new `scripts/install_stelae_bundle.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_stelae_integrator.py`, future bundle installer tests.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`.

## Notes

- Starter bundle file can mirror the 1mcp `discovered_servers.json` schema so the installer can pass descriptors directly to the integrator; human-readable YAML is optional because the CLI/README will describe the contents.
- Dropping Docy (and other optional MCP servers) from the tracked config should include an alternative for surfacing repo docs, or instructions for enabling Docy via the starter script.
- Ensure the installer gracefully handles already-installed servers and local overlays so contributors upgrading from the current setup do not lose data.
- If this task changes dependency graphs, regenerate the relevant JSON under `dev/tasks/*_task_dependencies.json` and attach the update when filing progress.
- Recent context (2025-11-10): README, `docs/ARCHITECTURE.md`, and `AGENTS.md` already describe "core vs optional" stacks, but the tracked templates (`config/proxy.template.json`, `ecosystem.config.js`) still launch every server by default. This task now needs to align the actual configs with the documented split.
- Hygiene guardrails: `scripts/verify_clean_repo.sh` / `make verify-clean` should remain green after any bundle install flow. Use the helper while iterating to ensure renderers + restarts keep `git status` clean.
- Env layering has been centralized in `stelae_lib.config_overlays.load_layered_env`. Reuse it if the modularization work introduces new render/install scripts so behavior matches the proxy/cloudflared renderers.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
