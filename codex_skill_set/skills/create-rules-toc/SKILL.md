---
name: create-rules-toc
description: |
    Update the rules search index (ToC) after modifying, creating, or deleting
    development documents such as coding standards, architecture rules,
    or workflow guides.
    Trigger:
    - After editing, adding, or removing rule documents
    - "Rebuild the rules ToC"
metadata:
  short-description: create rules toc
---

## Codex Skill Resource Root

This skill is distributed by the environment-wide Doc Advisor Codex Skill set.
Resolve `$DOC_ADVISOR_CODEX_ROOT` to `${CODEX_HOME:-~/.codex}/doc-advisor`,
the directory that contains `install.yaml`.

Run bundled Python scripts with absolute paths under
`$DOC_ADVISOR_CODEX_ROOT/resources/...` and prefix them with
`PYTHONDONTWRITEBYTECODE=1` so global resources do not accumulate runtime cache
files. Project runtime output stays under the current project's
`.codex/state/doc-advisor/`.

# create-rules-toc

Generate/update rules ToC (Table of Contents) for AI-searchable document index.

## Usage

```
create-rules-toc [--full]
```

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| (none)   | Incremental update (hash-based) or resume processing  |
| `--full` | Full file scan (for initial creation or regeneration) |

## Execution Flow

1. Read `$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/toc_orchestrator.md` for orchestrator workflow
2. Read `$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/toc_format.md` for format definition
3. Execute the full orchestrator workflow as described in the document, with **category = rules**
   - If `$0` = `--full`: Execute in **full mode** (rebuild entire ToC)
   - Otherwise: Execute in **incremental mode** (process changes only)

## Error Handling

If a script outputs `{"status": "config_required", ...}`, use user confirmation to ask the user:

- "Document directories are not configured. Run setup-doc-structure to configure?"
  - Yes → invoke `setup-doc-structure`, then restart this skill
  - No → abort

For other unexpected errors, report the error details clearly and use user confirmation to ask the user how to proceed.
