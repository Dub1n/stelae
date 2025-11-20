# Task: Portable bundle drop-ins

Related requirement: `dev/progress.md` → portable-bundles → "Ship drop-in bundle folders that encapsulate catalog fragments, install metadata, and helper scripts so users can add/remove optional tool suites without touching overlays or tracked configs."

Tags: `#feature` `#infra` `#docs`

## Checklist

- [ ] Finalize the bundle folder contract (mandatory `catalog.json`, optional `install.json`/scripts, installRef metadata) per `dev/tasks/completed/intended-catalog-plan-untracked-configs.md` and codify it in docs + schema validation.
- [ ] Update bundle installers (`scripts/install_stelae_bundle.py`, prospective `stelae bundle install`) to copy folders verbatim into `${STELAE_CONFIG_HOME}/bundles/<name>/`, register install refs, and reuse existing installs when refs match.
- [ ] Teach renderers (`scripts/process_tool_aggregations.py`) and restart helpers to rely solely on bundle folders + user catalogs so runtime merges pull from the drop-in structure without overlay duplication; add regression tests around removal/uninstall.
- [ ] Extend `manage_stelae`/CLI surfaces to surface bundle health (missing `installRef`, failed step, version drift) and optionally re-run bundle installers when dependencies go stale.
- [ ] Document the workflow (README, DEVELOPMENT, AGENTS, bundle authoring guide) and add examples/tests to ensure new bundles remain portable across machines.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `project: finalize portable bundles` after tests.

## References

- Code: `scripts/install_stelae_bundle.py`, `scripts/process_tool_aggregations.py`, bundle loaders in `stelae_lib/bundles.py`.
- Tests: `tests/test_install_stelae_bundle.py`, `tests/test_tool_aggregations.py` (bundle coverage), future regressions for drop-in installs.
- Docs: `dev/tasks/completed/intended-catalog-plan-untracked-configs.md` (§4 Bundle Packaging & Installation, §7 Follow-up Work), README Roadmap, DEVELOPMENT.md (bundle workflow), `dev/tasks/mcp-server-updates.md` (bundle maintenance context).

## Notes

- Bundle folders must be self-contained: dropping a folder into `${STELAE_CONFIG_HOME}/bundles/<name>/` activates it, deleting removes it. No tracked overlay edits are allowed.
- Install refs (Git repo, package name, etc.) live alongside bundle metadata so multiple bundles referencing the same server reuse prior installs rather than duplicating binaries.
- Install hooks may ship as `install.json` or scripts within the folder; orchestration must run them relative to the bundle path and persist success markers inside config-home state.
- Render/restart tooling already reads bundle catalog fragments; this task ensures tracked JSON never reappears, adds validation, and documents the workflow so bundle authors can contribute new suites safely.
- Remember to regenerate dependency maps if bundle orchestration introduces or removes cross-task requirements.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
