---
name: create-specs-toc
description: Update specs search index (ToC) after modifying, creating, or deleting markdown files in specs/ directories.
allowed-tools: Bash, Read, Task
user-invocable: true
argument-hint: "[--full]"
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

# create-specs-toc

Generate/update specs ToC (Table of Contents) for AI-searchable document index.

## Usage

```
/create-specs-toc [--full]
```

| Argument | Description |
|----------|-------------|
| (none) | Incremental update (hash-based) or resume processing |
| `--full` | Full file scan (for initial creation or regeneration) |

## Execution Flow

1. Read `.claude/doc-advisor/docs/specs_orchestrator.md` for orchestrator workflow
2. Read `.claude/doc-advisor/docs/specs_toc_format.md` for format definition
3. Execute Phase 1-3 as described in the orchestrator document
   - If `$0` = `--full`: Execute in **full mode** (rebuild entire ToC)
   - Otherwise: Execute in **incremental mode** (process changes only)

## Error Handling

If an unexpected error occurs during processing, report the error details clearly and ask the user how to proceed.
