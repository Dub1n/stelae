# Task: Automate Tool Override Baseline Sync

Related requirement: `dev/progress.md` → Requirement Group A → "Automate syncing new tools into the overrides file".

Tags: `#automation`, `#infra`

## Checklist

- [ ] Capture manifest/initialize catalog from the running proxy (local + public) and normalise tool descriptors.
- [ ] Generate/update master-level entries in `config/tool_overrides.json` with default `name` and `description` for any tools missing overrides.
- [ ] Avoid clobbering per-server overrides or custom descriptions; only fill gaps or update stale defaults when user opts in.
- [ ] Provide a CLI entry point (Python or Make target) that operators can run after new tools appear.
- [ ] Add regression tests covering the sync script (fixture manifest → updated overrides file).
- [ ] Document the workflow in `README.md` / `docs/` and link from `dev/tasks/override-expansion.md` for future reference.
- [ ] Update progress tracker/task log once automation ships.

## References

- Code: `config/tool_overrides.json`, `scripts/render_proxy_config.py`, new automation script (TBD).
- Docs: `README.md` override section, `docs/SPEC-v1.md` catalog exposure notes.
- Tests: new pytest module validating override sync behaviour.

## Notes

- Target idempotency: running the automation twice without upstream changes should produce zero diff.
- Consider optionally fetching public manifest to ensure Cloudflare worker stays aligned.
- Highlight any manual steps (e.g., restarting proxy) the script cannot perform automatically.
- Build on the existing override expansion work so terminology & warnings stay consistent.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] Progress tracker updated
- [ ] Task log updated
- [ ] Checklist completed
