---
name: create-specs-toc
description: |
  Update the specs search index (ToC) after modifying, creating, or deleting
  requirement or design documents such as functional requirements,
  use cases, or technical design specs.
  Trigger:
  - After editing, adding, or removing spec documents
  - "Rebuild the specs ToC"
allowed-tools: Bash, Read, Task
user-invocable: true
argument-hint: "[--full]"
---

# create-specs-toc

Generate/update specs ToC (Table of Contents) for AI-searchable document index.

## Usage

```
/doc-advisor:create-specs-toc [--full]
```

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| (none)   | Incremental update (hash-based) or resume processing  |
| `--full` | Full file scan (for initial creation or regeneration) |

## Execution Flow

1. Read `${CLAUDE_PLUGIN_ROOT}/docs/toc_orchestrator.md` for orchestrator workflow
2. Read `${CLAUDE_PLUGIN_ROOT}/docs/toc_format.md` for format definition
3. Execute the full orchestrator workflow as described in the document, with **category = specs**
   - If `$0` = `--full`: Execute in **full mode** (rebuild entire ToC)
   - Otherwise: Execute in **incremental mode** (process changes only)

## Error Handling

If a script outputs `{"status": "config_required", ...}`, use AskUserQuestion to ask the user:

- "Document directories are not configured. Run /forge:setup-doc-structure to configure?"
  - Yes → invoke `/forge:setup-doc-structure`, then restart this skill
  - No → abort

For other unexpected errors, report the error details clearly and use AskUserQuestion to ask the user how to proceed.
