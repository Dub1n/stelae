# Task: E2E clone smoke test (Codex MCP harness)

Related requirement: `dev/progress.md` → Action Items → "Add automated/manual smoke coverage for the self-managing MCP clone".

Tags: `#infra`, `#tests`

## Checklist

- [x] Land a Codex MCP wrapper mission that can launch sandboxes with caller-provided env/layout for optional experiments. _(Delivered separately in `~/dev/codex-mcp-wrapper`; the smoke harness now runs without it, but the release remains available.)_
- [x] Build an automation harness that clones the repo into a temp workspace, points `STELAE_CONFIG_HOME`/`.env` at that sandbox, renders + restarts the stack, and drives the CLI portions of `stelae.manage_stelae` (install/remove) while asserting the git tree stays clean.
- [x] Write the companion manual playbook so testers can follow the scripted MCP interactions (install server via tool, exercise it, remove it, finish) even without automation; when desired, they can still launch the Codex MCP wrapper inside the sandbox and feed results back to the harness.
- [x] If the Codex MCP wrapper cannot be delivered in time, fall back to a documented manual MCP procedure (still using the sandbox + CLI harness) and capture the gap in the task notes. _(N/A – wrapper available; playbook references the release copy.)_
- [x] Update README/AGENTS/docs with instructions for running the smoke test (both automated portion and the human-in-the-loop MCP steps).
- [x] Update spec/progress/task files.
- [x] Commit with message `infra: add e2e clone smoke test harness` after tests.

*Historical note: early iterations referenced a separate Codex MCP wrapper “orchestrator.” The delivered harness now runs the entire workflow itself (render → restart → staged `codex exec --json --full-auto` calls), and the wrapper is strictly optional for other MCP experiments.*

## References

- Code: `scripts/install_stelae_bundle.py`, `scripts/stelae_integrator_server.py`, `scripts/run_restart_stelae.sh`, planned Codex MCP wrapper (TBD), future `tests/e2e_clone_smoke.py`.
- Tests: `tests/test_repo_sanitized.py`, `tests/test_install_stelae_bundle.py` (reference for sandbox env handling), new e2e smoke test module.
- Docs: `README.md` (core vs optional flow), `AGENTS.md`, `docs/ARCHITECTURE.md`, new smoke-test instructions page.

## Notes

- The MCP interactions must go through the actual agent transport (JSON-RPC via proxy) to validate manifests, overrides, and tool UX—CLI helpers are only for the automated portion.
- The harness should isolate state by exporting `STELAE_CONFIG_HOME=$(mktemp -d)` (or equivalent) so the smoke test never touches a real workstation’s overlays. Remember to clean up temp dirs even on failure.
- Consider staging the workflow (e.g., `setup`, `manual`, `verify`) so the manual portion slots naturally between automated steps.
- Allocate alternate ports and/or pm2 app names for the smoke-test stack so it never collides with a developer’s running instance, even if both happen to be online simultaneously.
- If this task changes prerequisites or dependency relationships, regenerate the project’s dependency map JSON (see `dev/tasks/*_task_dependencies.json`) and attach the updated file in the related progress planner.

## Outcome

- Extended `scripts/run_e2e_clone_smoke_test.py` so the harness installs the starter bundle, seeds a disposable Codex client repo, mirrors `~/.codex` (override via `--codex-home`), auto-cleans stale `stelae-smoke-workspace-*` sandboxes, and drives `codex exec --json --full-auto` through bundle verification plus `manage_stelae` install/remove cycles. Automatic runs now parse the JSONL stream, assert the expected MCP calls fired (`workspace_fs_read`, `grep`, `doc_fetch_suite`, and the `manage_stelae` install/remove payloads), and store transcripts under `<workspace>/codex-transcripts/<stage>.jsonl`.
- Added CLI flags for Codex integration and workspace/manual control (`--codex-cli`, `--codex-home`, `--manual`, `--manual-stage`, `--force-workspace`, `--reuse-workspace`, `--cleanup-only`). Manual artifacts (`manual_playbook.md`, `manual_stage_<name>.md`, `manual_result.json`) are only created when requested; otherwise the harness stays fully automated but still supports stage-specific pause/resume.
- Promoted clone hygiene: the harness now runs `pytest tests/test_repo_sanitized.py` immediately after render, executes the full pytest suite after the Codex phase, and finishes with `make verify-clean`, snapshotting `git status` after every managed install/remove.
- Expanded `stelae_lib.smoke_harness` with Codex transcript helpers plus the accompanying unit test (`tests/test_codex_exec_transcript.py`). Updated existing tests (`tests/test_e2e_clone_smoke.py`) to cover the new utilities.
- Refreshed `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/e2e_clone_smoke_test.md` to describe the automatic Codex flow, transcript expectations, and the manual fallback flag. Updated `dev/tasks/missions/e2e_clone_smoke.json` to align with the new Qdrant install/remove scenario.

## Checklist (Copy into PR or issue if needed)

- [x] Code/tests updated
- [x] Docs updated
- [x] progress.md updated
- [x] Task log updated
- [x] Checklist completed
