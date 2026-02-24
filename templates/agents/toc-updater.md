---
name: toc-updater
description: Specialized agent that generates ToC entries for a single document. Processes individual YAML files in .claude/doc-advisor/toc/{target}/.toc_work/.
model: {{AGENT_MODEL}}
color: orange
tools: Read, Bash
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

## Overview

Processes a single document (`.md` file) and completes the corresponding entry YAML in `.claude/doc-advisor/toc/{target}/.toc_work/`.

**Important**: This agent processes only one file. Multiple file processing is managed by the orchestrator (create-{target}-toc command) via parallel invocation.

## EXECUTION RULES
- Exit plan mode if active. Do NOT ask for confirmation
- If a step fails, report the error and exit immediately
- Write all ToC field values in English, regardless of the source document's language. ToC is a search index for AI agents — English ensures consistent keyword matching across multilingual projects

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `target` | Yes | Target category: `rules` or `specs` |
| `entry_file` | Yes | Path to the entry YAML file to process (e.g., `.claude/doc-advisor/toc/{target}/.toc_work/xxx.yaml`) |

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/toc_format.md` - Format definition (Single Source of Truth)

## Procedure

1. Read `{entry_file}` to get `_meta.source_file`
2. Read the document using `_meta.source_file` value (resolves from project root)
3. Extract each field according to "Field Guidelines" in `toc_format.md`
4. Call the write script to save the completed entry:

### For rules target:

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/write_pending.py \
  --target rules \
  --entry-file "{entry_file}" \
  --title "{extracted title}" \
  --purpose "{extracted purpose}" \
  --content-details "{item1 ||| item2 ||| item3}" \
  --applicable-tasks "{task1 ||| task2}" \
  --keywords "{kw1 ||| kw2 ||| kw3}"
```

### For specs target:

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/write_pending.py \
  --target specs \
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
- For specs target: `--references` is required. Pass empty string `""` if no references found.
- For specs target: Verify concrete file paths exist using Glob before including them. Do NOT guess or hallucinate file paths. If the document explicitly mentions a reference but the specific path cannot be determined, record the reference as written in the source document.

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
