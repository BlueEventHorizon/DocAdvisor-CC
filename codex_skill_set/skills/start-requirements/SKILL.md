---
name: start-requirements
description: |
  Create or update requirements documents in Codex using forge's requirements formats and a chat-based confirmation protocol. Use when the user asks to start requirements, create requirements, derive requirements from code, or write a feature requirements document.
metadata:
  short-description: start requirements
---

# start-requirements

Create or update a requirements document for a feature in Codex.


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

1. Determine the feature name. If it is not clear from the user request, use the confirmation protocol.
2. Determine the mode:
   - `interactive`: clarify the product behavior with the user and write requirements.
   - `reverse-engineering`: inspect the existing implementation and derive requirements.
   - `from-figma`: only use when the user provides usable Figma/design context; otherwise ask for the missing input.
3. Resolve the output location from `.doc_structure.yaml`. Prefer a requirements directory. If no location is clear, ask before creating one.
4. Read the relevant references:
   - Always read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/requirement_format.md`.
   - For added features, read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/additive_development_spec.md`.
   - For interactive mode, read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/start-requirements/docs/requirements_interactive_workflow.md`.
   - For reverse-engineering mode, read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/start-requirements/docs/requirements_reverse_engineering_workflow.md`.
   - For from-figma mode, read `$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/start-requirements/docs/requirements_from_figma_workflow.md`.
5. Gather only the context needed for the selected mode. Use `query-rules` and `query-specs` when they help identify relevant documents.
6. Draft the requirements document using the project language and existing naming style.
7. Before creating a new directory or overwriting an existing requirements document, use the confirmation protocol unless the user explicitly requested that exact action.
8. After writing, summarize the file path and any unresolved assumptions. Ask before running ToC update.
