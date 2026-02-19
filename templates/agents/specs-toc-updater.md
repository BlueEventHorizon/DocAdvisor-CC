---
name: specs-toc-updater
description: Specialized agent that generates ToC entries for a single requirement/design document. Processes individual YAML files in .claude/doc-advisor/toc/specs/.toc_work/.
model: {{AGENT_MODEL}}
tools: Read, Bash
color: cyan
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

## Overview

Processes a single requirement/design document and completes the corresponding entry YAML in `.claude/doc-advisor/toc/specs/.toc_work/`.

**Important**: This agent processes only one file. Multiple file processing is managed by the orchestrator (create-specs-toc command) via parallel invocation.

## EXECUTION RULES
- Exit plan mode if active. Do NOT ask for confirmation
- If a step fails, report the error and exit immediately

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `entry_file` | Yes | Path to the entry YAML file to process (e.g., `.claude/doc-advisor/toc/specs/.toc_work/{{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_login.yaml`) |

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/specs_toc_format.md` - Format definition (Single Source of Truth)

## Procedure

1. Read `{entry_file}` to get `_meta.source_file`
2. Read the requirement/design document using `_meta.source_file` value (resolves from project root, e.g., `{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/login.md`)
3. Extract each field according to "Field Guidelines" in `specs_toc_format.md`
   - For `references`: Extract documents directly referenced in the text. Prefer concrete paths. Use empty string if no references found.
4. Call the write script to save the completed entry:

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/write_specs_pending.py \
  --entry-file "{entry_file}" \
  --title "{extracted title}" \
  --purpose "{extracted purpose}" \
  --content-details "{item1 ||| item2 ||| item3}" \
  --applicable-tasks "{task1 ||| task2}" \
  --keywords "{kw1 ||| kw2 ||| kw3}" \
  --references "{ref1 ||| ref2 or empty}"
```

**Important**:
- Arrays are passed as `|||`-separated strings (NOT comma-separated). This allows commas within items (e.g., "10,000件").
- For `--references`, pass empty string `""` if no references found.
- For `--references`, verify concrete file paths exist using Glob before including them. Do NOT guess or hallucinate file paths. If the document explicitly mentions a reference but the specific path cannot be determined, record the reference as written in the source document.

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
