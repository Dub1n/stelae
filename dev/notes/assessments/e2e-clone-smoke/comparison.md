# Assessment Comparison (Codex vs GPT Models) (2025-11-13)

| Assessment | Strengths | Gaps / Cautions |
| --- | --- | --- |
| [codex-high](./codex-high.md) | Most action-packed timeline with commit references, regression summary + positive outcomes, concrete outstanding questions and next steps; good at tying fixes to specific docs (`dev/tasks/*`, README, ARCHITECTURE). | Dense narrative repeats task-doc content, lacks an explicit architecture snapshot, and can overwhelm readers who just need the current blocker list. |
| [codex-medium](./codex-medium.md) | Balanced context + findings, clear doc consolidation plan, acknowledges overlap between harness/codex issues and documentation. | Skims over tangible wins/tests, omits instrumentation details, and relies on external docs for evidence, making it less persuasive during postmortems. |
| [codex-mini](./codex-mini.md) | Concise, easy to skim, highlights instrumentation knobs (`STELAE_STREAMABLE_DEBUG_*`, `STELAE_TOOL_AGGREGATOR_DEBUG_*`) and reiterates the starter-bundle overlay rules. | Drops nuance (typo/abrupt sentences), lacks timeline or testing evidence, and feels more like meeting notes than a full assessment. |
| [gpt-5-high](./gpt-5-high.md) | Most comprehensive structure (exec summary, architecture snapshot, recommendations, risks, commands, evidence map); ideal for onboarding stakeholders who need the full picture. | Understates unresolved Codex `workspace_fs_read` failures and documentation sprawl, so action items need supplementation from other reports to stay current. |

Use codex-high when you need a change-log style debrief, gpt-5-high for executive/architecture reviews, codex-medium for roadmap alignment, and codex-mini for quick reminders of the open blockers plus debugging switches.
