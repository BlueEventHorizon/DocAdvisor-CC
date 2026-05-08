---
name: start-design
description: |
  Create or update design documents in Codex from requirements and existing implementation context. Use when the user asks to start design, create a design document, or turn requirements into a design.
metadata:
  short-description: start design
---

# start-design

Create or update a design document from requirements in Codex.


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

1. Determine the feature name and target requirement document. If either is unclear, search with `query-specs`; if still unclear, use the confirmation protocol.
2. Resolve the output location from `.doc_structure.yaml`. Prefer a design directory. Ask before creating a new directory or overwriting an existing design document.
3. Read these references:
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/design_format.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/design_principles_spec.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_design_boundary_spec.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_priorities_spec.md`
   - `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_format.md`
4. Read the target requirements thoroughly. Also inspect relevant existing implementation when the design should reuse current components.
5. If requirements are ambiguous or conflict with existing behavior, stop and ask using the confirmation protocol before designing.
6. Write the design document in the project style. Include reused components and the reason for any major non-reuse decision.
7. After writing, summarize the file path, key decisions, and unresolved risks. Ask before running ToC update.
