# Task: user-config overlays for repo hygiene

Related requirement: `docs/current/progress.md` → Configuration Hygiene → “Keep shipped defaults generic; let per-instance customisation live outside the repo while remaining auto-loaded.”

Tags: `#infra`

## Checklist

- [ ] Inventory every file/script that reads/writes config (proxy renderer, integrator, tool overrides, cloudflared helpers) and document where local overlays should hook in.
- [ ] Implement support for `~/.config/stelae/…` overlays (e.g. `tool_overrides.local.json`, `proxy.template.local.json`, `cloudflared.local.yml`) with clear merge semantics.
- [ ] Ensure `manage_stelae` writes MCP-specific env/config deltas into the overlay paths (NEVER into tracked files), including append-only `.env` behaviour.
- [ ] Update docs (README, AGENTS, ARCHITECTURE) + templates to explain the two-layer config model and how to reset/inspect local overlays.
- [ ] Add regression tests (unit + integration) that fail if tracked defaults contain localised values or if overlays aren’t picked up.
- [ ] Update spec/progress/task file.
- [ ] Commit with message `infra: add stelae config overlay system` after tests.

## References

- Code:
  - `scripts/render_proxy_config.py` – env loading & rendering entrypoint.
  - `stelae_lib/integrator/core.py` – manage_stelae operations, env writes.
  - `config/tool_overrides.json` & usage in `ToolOverridesStore`.
  - `ops/cloudflared.template.yml` + render pipeline.
- Tests:
  - `tests/test_stelae_integrator.py`
  - `tests/test_repo_sanitized.py`
  - (Add new overlay regression tests)
- Docs:
  - `docs/ARCHITECTURE.md`
  - `README.md`
  - `AGENTS.md`

## Notes

- Current pain: tracked `config/…` files end up with user-specific entries (disabled tools, custom env placeholders). We need a clean separation: repo defaults stay generic; user customizations live under XDG (`~/.config/stelae/…`) or other ignored paths.
- Requirements:
  - **Two-layer merge**: template/overrides/proxy configs should load `config/*.json` then overlay any files found under `~/.config/stelae/<same-name>.local.json`.
  - **Auto-seeding**: when `manage_stelae` injects hydrated descriptors or env vars, it must write to the overlay layer (local `.env` or overlay JSON), not the tracked base.
  - **Backwards compatibility**: existing deployments should continue working; new layer should be optional (if no overlay exists, behaviour matches today).
  - **CLI ergonomics**: provide helper commands/scripts to diff/clear overlays, and document how to sync them when sharing configs between environments.
  - **Git hygiene**: add ignore rules (if needed) for overlay locations, and ensure tests assert no absolute paths/domains leak into tracked files.
- Edge cases to consider:
  - Overlay removal while services are running (need reload instructions or auto-reload hooks).
  - Conflicting keys between base + overlay (define precedence; likely overlay wins).
  - Interaction with `scripts/bootstrap_one_mcp.py` and other bootstrap routines—should seed overlay directories if missing.
  - Windows/macOS paths (XDG fallback) for cross-platform contributors.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] progress.md updated
- [ ] Task log updated
- [ ] Checklist completed
