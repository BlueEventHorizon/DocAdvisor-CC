---
name: rules_toc_update_workflow
description: rules_toc.yaml update workflow (individual entry file method)
applicable_when:
  - Running as rules-toc-updater Agent
  - Executing /create-rules_toc command
  - After adding, modifying, or deleting rule/workflow/format documents
---

# rules_toc.yaml Update Workflow

## Overview

Workflow for updating `.claude/doc-advisor/rules/rules_toc.yaml`. Uses **individual entry file method**, processing each rule document with independent subagents.

## Architecture

### Design Philosophy

- **1 file = 1 subagent**: Process each rule document individually
- **Persistent artifacts**: Each subagent's output remains as a file
- **Resumable**: Completed work is preserved on interruption, resume from incomplete

### Directory Structure

```
.claude/doc-advisor/rules/
├── rules_toc.yaml              # Final artifact (after merge)
├── .toc_checksums.yaml         # Change detection checksums
└── .toc_work/                  # Work directory (.gitignore target)
    ├── guidelines_core_architecture_rule.yaml
    ├── guidelines_core_coding_rule.yaml
    └── ... (for each target file)
```

---

## Key Principles [MANDATORY]

- **Single Source of Truth**: `rules_toc_format.md` is the only source for format definition and intermediate file schema
- **All fields required**: Fill all fields in format definition. **No omissions**
- **Keyword extraction**: Actually read each file and extract keywords from content (array format)
- **YAML syntax**: Use indentation, colons, and hyphens correctly
- **Key format**: With `guidelines/` prefix (e.g., `guidelines/core/architecture_rule.md`)

---

## Workflow Overview

```
/create-rules_toc execution
    ↓
Phase 1: Initialization (Orchestrator)
    ↓
Phase 2: Processing (Parallel Subagents)
    ↓
Phase 3: Merge (Orchestrator)
    ↓
Cleanup
```

---

## Phase 1: Initialization (Orchestrator)

### Step 1.1: Check .claude/doc-advisor/rules/.toc_work/ status

```bash
test -d .claude/doc-advisor/rules/.toc_work && echo "EXISTS" || echo "NOT_EXISTS"
```

### Step 1.2: Mode determination and branching

| Condition | Processing |
|-----------|------------|
| `--full` option specified | Delete .claude/doc-advisor/rules/.toc_work/ → New processing in full mode |
| .claude/doc-advisor/rules/.toc_work/ exists | Continue mode (process existing pending YAMLs) |
| .claude/doc-advisor/rules/.toc_work/ doesn't exist + rules_toc.yaml doesn't exist | New processing in full mode |
| .claude/doc-advisor/rules/.toc_work/ doesn't exist + rules_toc.yaml exists | incremental mode |

### Step 1.3: Identify target files

- **full mode**: Get all files in scan targets
- **incremental mode**: Detect changed files using hash method

### Step 1.4: Generate pending YAML templates

Generate templates in `.claude/doc-advisor/rules/.toc_work/` for each target file.

---

## Phase 2: Parallel Processing (Subagent)

### Step 2.1: Identify pending YAMLs

Read `.claude/doc-advisor/rules/.toc_work/*.yaml` and identify files with `_meta.status: pending`

### Step 2.2: Launch subagents in parallel

**Parallel count**: 5 parallel

```
# Orchestrator calls multiple Task tools in one message
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/rules/.toc_work/xxx.yaml")
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/rules/.toc_work/yyy.yaml")
... (up to 5 simultaneous)
```

### Step 2.3: Subagent processing

Each subagent (rules-toc-updater) executes:

1. Read `entry_file`
2. Get rule document path from `_meta.source_file` (e.g., `guidelines/core/architecture_rule.md`)
3. Read rule document (resolve from project root)
4. Extract information and set fields according to "Field Guidelines" in `rules_toc_format.md`
5. Set `_meta.status: completed` and `_meta.updated_at`
6. Write and save

### Step 2.4: Repeat

Repeat Steps 2.1-2.3 until all pending YAMLs are completed

---

## Phase 3: Merge

### Step 3.1: Completion check

Verify each `.claude/doc-advisor/rules/.toc_work/*.yaml` meets:
- `_meta.status == completed`
- `title != null`
- `purpose != null`

**If incomplete**: Output warning and confirm with user

### Step 3.2: Merge processing

**full mode**:
1. Read all `.claude/doc-advisor/rules/.toc_work/*.yaml`
2. Exclude `_meta` and convert to `docs` section
3. Set `metadata` (generated_at, file_count)
4. Write to `.claude/doc-advisor/rules/rules_toc.yaml`

**incremental mode**:
1. Read existing `.claude/doc-advisor/rules/rules_toc.yaml`
2. Delete entries recorded in `.toc_checksums.yaml` but file doesn't exist
3. Overwrite/add entries from `.claude/doc-advisor/rules/.toc_work/*.yaml` (exclude `_meta`)
4. Update `metadata.generated_at`, `metadata.file_count`
5. Write to `.claude/doc-advisor/rules/rules_toc.yaml`
6. Update `.claude/doc-advisor/rules/.toc_checksums.yaml` (run `/create-toc-checksums` skill)

### Step 3.3: Cleanup

```bash
rm -rf .claude/doc-advisor/rules/.toc_work
```

---

## Validation

Check before merge:

1. **YAML syntax check**:
   - Accuracy of indentation, colons, hyphens
   - Quote escaping

2. **Required field check**:
   - metadata: name, generated_at, file_count
   - docs: Each entry has title, purpose, content_details, applicable_tasks, keywords

3. **File existence check**:
   - All files listed in docs actually exist

---

## Related Files

- `rules_toc_format.md` - Format definition (YAML schema)
- `agents/rules-toc-updater.md` - Single file processing subagent
- `commands/create-rules_toc.md` - Orchestrator command
- `agents/rules-advisor.md` - Search subagent
