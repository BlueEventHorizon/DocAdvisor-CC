---
name: rules-toc-updater
description: Specialized agent that generates ToC entries for a single rule document. Processes individual YAML files in .claude/doc-advisor/toc/rules/.toc_work/.
model: {{AGENT_MODEL}}
color: orange
tools: Read, Bash
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

## Overview

Processes a single rule document (`.md` file under `{{RULES_DIR}}`) and completes the corresponding entry YAML in `.claude/doc-advisor/toc/rules/.toc_work/`.

**Important**: This agent processes only one file. Multiple file processing is managed by the orchestrator (create-rules-toc command) via parallel invocation.

## EXECUTION RULES
- Exit plan mode if active. Do NOT ask for confirmation
- If a step fails, report the error and exit immediately

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `entry_file` | Yes | Path to the entry YAML file to process (e.g., `.claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_core_architecture_rule.yaml`) |

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/rules_toc_format.md` - Format definition (Single Source of Truth)

## Procedure

1. Read `{entry_file}` to get `_meta.source_file`
2. Read the rule document using `_meta.source_file` value (resolves from project root, e.g., `{{RULES_DIR}}/core/architecture_rule.md`)
3. Extract each field according to "Field Guidelines" in `rules_toc_format.md`
4. Call the write script to save the completed entry:

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/write_rules_pending.py \
  --entry-file "{entry_file}" \
  --title "{extracted title}" \
  --purpose "{extracted purpose}" \
  --content-details "{item1 ||| item2 ||| item3}" \
  --applicable-tasks "{task1 ||| task2}" \
  --keywords "{kw1 ||| kw2 ||| kw3}"
```

**Important**: Arrays are passed as `|||`-separated strings (NOT comma-separated). This allows commas within items (e.g., "10,000件").

## Completion Response

After successfully writing the entry file, return ONLY:

```
✅ Done: {filename}
```

On error, return ONLY:

```
❌ Error: {filename}: {brief reason}
```

**Do NOT return**:
- File contents
- Extracted field values
- Detailed processing logs
- Any other information

This is critical for context management when processing many files in parallel.

## Notes

- **On error**: Do NOT attempt automatic recovery or workarounds. Report the error details and exit immediately. Let the orchestrator decide how to proceed.
