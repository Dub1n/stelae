# Task: Expand Tool Overrides to Support Rich Descriptors

Related requirement: `dev/progress.md` → Requirement Group A → “Support richer proxy tool overrides…”.

Tags: `#feature`, `#infra`

## Checklist

- [x] Analyse current Go proxy override handling and identify insertion points for new fields.
- [x] Implement new fields (description/title/name) in `~/apps/mcp-proxy`; block master overrides from renaming tools and warn when master text overrides fire.
- [x] Ensure `tool_overrides.go`/`response_helpers.go` propagate string overrides with correct precedence (per-tool > server > master) and surface warnings during startup/scripts.
- [x] Add/extend Go unit tests (`tool_overrides_test.go`, `http_test.go`) covering string merge behaviour, rename guardrails, and warning emission.
- [x] Add integration coverage in Stelae repo (pytest) that exercises overrides end-to-end against rendered manifest/initialize responses.
- [x] Update `config/tool_overrides.json` examples and relevant docs (`docs/SPEC-v1.md`, `README.md`) with the richer override schema and warning semantics.
- [x] Regenerate `config/proxy.json`, restart stack, and republish manifest (local + Cloudflare) to validate public + local outputs.
- [x] Update spec/progress/task file.
- [ ] Commit with message `feature: expand proxy tool overrides` after tests.

## References

- Code: `~/apps/mcp-proxy/tool_overrides.go`, `response_helpers.go`, `config.go`
- Tests: `~/apps/mcp-proxy/tool_overrides_test.go`, add coverage for new fields
- Docs: `docs/SPEC-v1.md`, `README.md` override section

## Notes

- Ensure backward compatibility with existing override files; new fields must be optional.
- Decide precedence when multiple servers define the same tool (prefer explicit per-tool overrides over master/default text).
- Reject master-level renames but log a warning when master sets description/title so operators know it affected global copy.
- After implementation, publish sample overrides demonstrating customised descriptions.
- If schema changes require consumer updates, coordinate with any external repos depending on the proxy format.

## Checklist (Copy into PR or issue if needed)

- [ ] Code/tests updated
- [ ] Docs updated
- [ ] Progress tracker updated
- [ ] Task log updated
- [ ] Checklist completed
