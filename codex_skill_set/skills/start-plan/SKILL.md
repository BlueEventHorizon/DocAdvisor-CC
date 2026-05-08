---
name: start-plan
description: |
  Create or update implementation plans in Codex from requirements and design documents. Use when the user asks to start planning, create a plan, or break a design into implementation tasks.
metadata:
  short-description: start plan
---

# start-plan

Create or update an implementation plan from requirements and design documents in Codex.


## Common Rules

- Resolve `$DOC_ADVISOR_CODEX_ROOT` to `${CODEX_HOME:-~/.codex}/doc-advisor`, the directory that contains `install.yaml`.
- Read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/codex_confirmation_protocol.md` before asking the user to choose or approve anything.
- Use `.doc_structure.yaml` as the source of document locations. If it is missing, use `setup-doc-structure` first or ask the user before continuing.
- Prefer project rules and existing document style over forge defaults.
- Do not run review automation, commit, cleanup, or monitor steps automatically in this Codex wrapper.
- When a source workflow mentions review, auto-fix, commit, session cleanup, monitor, or slash commands, treat those as optional follow-up steps that require explicit user confirmation.
- Write only the target document(s) needed for the user's request.

Useful references:

- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_format.md`
- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/requirement_format.md`
- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/design_format.md`
- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/plan_format.md`
- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_design_boundary_spec.md`
- `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_priorities_spec.md`


## Procedure

1. Determine the feature name and target design document. If unclear, search with `query-specs`; if still unclear, use the confirmation protocol.
2. Resolve the output location from `.doc_structure.yaml`. Prefer a plan directory. Ask before creating a new directory or overwriting an existing plan.
3. Read these references:
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/plan_format.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/plan_principles_spec.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_format.md`
4. Read the relevant requirements and design documents before task extraction.
5. Break work into tasks that are small enough to validate, but group tasks when an intermediate state would knowingly break the build.
6. For task IDs, prefer the project's existing convention. If a `TASK` sequence is needed, the helper script is available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/next-spec-id/scripts/scan_spec_ids.py" TASK
```

7. Write or update the plan in the project style. Do not start implementation unless the user explicitly asks.
8. After writing, summarize the file path, task count, dependencies, and validation assumptions. Ask before running ToC update.
