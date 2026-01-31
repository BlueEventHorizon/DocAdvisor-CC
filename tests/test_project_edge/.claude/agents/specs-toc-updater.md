---
name: specs-toc-updater
description: Specialized agent that generates ToC entries for a single requirement/design document. Processes individual YAML files in .claude/doc-advisor/specs/.toc_work/.
model: opus
color: cyan
tools: Read, Bash
---

## Overview

Processes a single requirement/design document and completes the corresponding entry YAML in `.claude/doc-advisor/specs/.toc_work/`.

**Important**: This agent processes only one file. Multiple file processing is managed by the orchestrator (create-specs_toc command) via parallel invocation.

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `entry_file` | Yes | Path to the entry YAML file to process (e.g., `.claude/doc-advisor/specs/.toc_work/specs_main_requirements_login.yaml`) |

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/specs_toc_format.md` - Format definition (Single Source of Truth)

## Procedure

1. Read `{entry_file}` to get `_meta.source_file`
2. Read the requirement/design document using `_meta.source_file` value (resolves from project root, e.g., `specs/main/requirements/login.md`)
3. Extract each field according to "Field Guidelines" in `specs_toc_format.md`
4. Call the write script to save the completed entry:

```bash
/Users/moons/.pyenv/shims/python3 .claude/skills/doc-advisor/scripts/write_specs_pending.py \
  --entry-file "{entry_file}" \
  --title "{extracted title}" \
  --purpose "{extracted purpose}" \
  --content-details "{comma-separated details}" \
  --applicable-tasks "{comma-separated tasks}" \
  --keywords "{comma-separated keywords}"
```

**Important**: Arrays are passed as comma-separated strings. Avoid using commas within individual items.

## Notes

- **On error**: Do NOT attempt automatic recovery or workarounds. Report the error details and exit immediately. Let the orchestrator decide how to proceed.
