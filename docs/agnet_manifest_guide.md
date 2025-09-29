# How to generate this from your live manifest (procedural)

1. **Pull live**:

    * GET `/.well-known/mcp/manifest.json` and `/tools/list`. If `servers` is null, set `server.label` yourself (e.g., `"stelae"`) so ChatGPT can namespace tools cleanly.

2. **Copy only essentials per tool**:

    * `name`, a one-line `summary` (from description’s first sentence),
    * `input_schema` (strip defaults/verbose text; keep required/props),
    * `output_schema` (optional; omit if large),
    * `annotations` → map provider hints to `{readOnly, destructive, idempotent}`; mark `supports_dry_run` if a flag exists (e.g., `edit_file.dryRun`).
    * `category` via a simple mapping table (grep/search → `code-search`; read_* → `fs-read`; write/edit/move → `fs-write`; execute_command → `exec`; fetch/docs tools → `docs`; memory tools → `memory`).

3. **Approvals**:

    * Set `approvals.read_default = "never"` and `write_default = "always"`; override with `approval` for any safe exceptions (read tools stay “never”).

4. **Policy**:

    * If you can call `list_allowed_directories`, populate `workspace_roots` (else leave empty and let first call fill it).
    * Set `tooling_preference = "mcp_only"` for repo work to prevent accidental web/built-ins usage.

5. **Examples**:

    * Add one tiny JSON `arguments` example per tool (no prose in JSON). These act as reliable few-shot hints for the planner.

That’s it. This format is small enough to drop at session start and rich enough for the agent to plan multi-step work, dry-run before writes, and respect approvals — which matches OpenAI’s guidance and your Stelae topology (single proxy, canonical `search`/`fetch`, FS + terminal).

If you want, I can spit out a little Python that ingests your live manifest and emits this trimmed spec.
