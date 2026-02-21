---
name: rules_orchestrator
description: Orchestrator workflow for rules_toc.yaml generation
applicable_when:
  - Executing /create-rules-toc skill
  - Coordinating rules ToC generation process
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

# rules_toc.yaml Orchestrator Workflow

Orchestrator workflow to generate/update `.claude/doc-advisor/toc/rules/rules_toc.yaml`.

## Options

| Option | Description |
|--------|-------------|
| (none) | Incremental update (hash-based) or resume processing |
| `--full` | Full file scan (for initial creation or regeneration) |

## Arguments

- No arguments → incremental mode (hash-based change detection) or resume processing
- `--full` → full mode with complete scan

---

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/rules_toc_format.md` - Format definition and intermediate file schema
- `.claude/doc-advisor/docs/rules_toc_update_workflow.md` - Detailed workflow

---

## Orchestrator Processing Flow

### Phase 1: Initialization

```
1. Check if .claude/doc-advisor/toc/rules/.toc_work/ exists
    ↓
[If exists] → Continue mode (jump to Phase 2)
    ↓
[If not exists]
    ↓
2. Mode determination
    - --full option → full mode
    - rules_toc.yaml doesn't exist → full mode
    - Otherwise → incremental mode
    ↓
3. Create .toc_work/ directory
    ↓
4. Identify target files and generate pending YAML templates
    ```bash
    # Full mode
    {{PYTHON_PATH}} .claude/doc-advisor/scripts/create_pending_yaml_rules.py --full

    # Incremental mode
    {{PYTHON_PATH}} .claude/doc-advisor/scripts/create_pending_yaml_rules.py
    ```
```

### Phase 2: Parallel Processing

> **⚠️ Context Management [IMPORTANT]**
>
> Subagent results accumulate in the parent conversation context.
> When processing many files, this can cause context overflow.
>
> **Rules:**
> - Subagents return minimal responses (defined in agent's "Completion Response" section)
> - After each batch completes, output a brief progress summary (e.g., "Batch 2/10 complete, 40 remaining")
> - Keep orchestrator messages minimal between batches

```
1. Identify pending status files from .claude/doc-advisor/toc/rules/.toc_work/*.yaml
    ↓
2. If no pending files → Go to Phase 3 (merge)
    ↓
3. Read common.parallel.max_workers from config.yaml, then launch up to that many subagents in parallel
    Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{filename}.yaml")
    ↓
4. Wait for completion
    ↓
5. If pending files remain → Return to step 1
```

### Phase 3: Merge, Validation & Checksum Update

```
1. Completion check (verify all YAML are completed or error)
    - If pending remain → Return to Phase 2
    - All completed/error → Proceed to merge
    ↓
2. Merge processing
    - full: Generate new rules_toc.yaml from .claude/doc-advisor/toc/rules/.toc_work/*.yaml
    - incremental: Combine existing rules_toc.yaml + .claude/doc-advisor/toc/rules/.toc_work/*.yaml + handle deletions
    - Note: Skip error status files (output warning)
    ↓
3. Run validation → **Check return value**
    - Success (exit 0) → Proceed to step 4
    - Failure (exit 1) → Restore from backup, don't update checksums, abort
    ↓
4. Update checksums **only on validation success**
    ↓
5. Cleanup (delete .claude/doc-advisor/toc/rules/.toc_work/)
    ↓
6. Report completion (list error files if any)
```

---

## Pending YAML Template Generation

Use the script to generate `.claude/doc-advisor/toc/rules/.toc_work/{filename}.yaml` for each target file.

```bash
# Full mode (all files)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/create_pending_yaml_rules.py --full

# Incremental mode (changed files only)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/create_pending_yaml_rules.py
```

The script handles:
1. File discovery and change detection (SHA-256 hash comparison)
2. Filename conversion (e.g., `{{RULES_DIR}}/core/architecture_rule.md` → `{{RULES_DIR}}_core_architecture_rule.yaml`)
3. Template generation with pending status

**Template format**: See "Intermediate File Schema" section in `.claude/doc-advisor/docs/rules_toc_format.md`

---

## Continue Mode Details

| Condition | Action |
|-----------|--------|
| `--full` + `.claude/doc-advisor/toc/rules/.toc_work/` exists | Bash: `rm -rf .claude/doc-advisor/toc/rules/.toc_work` → Start full mode |
| `.claude/doc-advisor/toc/rules/.toc_work/` exists + pending remain | Resume from pending (to Phase 2) |
| `.claude/doc-advisor/toc/rules/.toc_work/` exists + all completed | Go directly to merge phase (Phase 3) |

---

## Incremental Mode: Change Detection Steps

### Step 1: Check Checksum File

```bash
test -f .claude/doc-advisor/toc/rules/.toc_checksums.yaml && echo "EXISTS" || echo "NOT_EXISTS"
```

- If not exists → Fallback to full mode

### Step 2: Get Current File List and Hashes

```bash
# Target file list
find {{RULES_DIR}} -name "*.md" -type f | grep -v ".toc_work" | grep -v "rules_toc.yaml" | grep -v "reference" | sort

# Calculate hash for each file
shasum -a 256 {{RULES_DIR}}/core/architecture_rule.md | cut -d' ' -f1
```

### Step 3: Compare Checksums

1. Read `.claude/doc-advisor/toc/rules/.toc_checksums.yaml`
2. For each file:
   - **New**: Not in checksums → Generate pending YAML
   - **Changed**: Hash mismatch → Generate pending YAML
   - **Deleted**: In checksums but file missing → Auto-delete at merge (merge_rules_toc.py handles)
   - **Unchanged**: Hash match → Skip

### Step 4: Determine Changes and Deletions

1. **Changed file count (N)**: New + hash mismatch files
2. **Deleted file count (M)**: In checksums but file missing

```
[Decision Logic]
┌────────────────────┬────────────────────────────────────────────┐
│ Condition          │ Action                                     │
├────────────────────┼────────────────────────────────────────────┤
│ N=0 and M=0        │ End processing (no changes)                │
│ N=0 and M>0        │ Run merge script only (reflect deletions)  │
│ N>0                │ Generate pending YAML → Subagents → Merge  │
└────────────────────┴────────────────────────────────────────────┘
```

**If N=0 and M=0**:
```
✅ No changes - rules_toc.yaml is up to date
```
End processing (no need to create .claude/doc-advisor/toc/rules/.toc_work/)

**If N=0 and M>0**:
```
📁 Detected deleted files: M items
🔄 Running merge script to reflect deletions...
```
→ Run merge script (go directly to Phase 3, no .claude/doc-advisor/toc/rules/.toc_work/ needed)

---

## Subagent Launch Examples

```
# Launch 5 in parallel
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_core_architecture_rule.yaml")
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_core_coding_rule.yaml")
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_layer_ui_rule.yaml")
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_workflow_dev_task.yaml")
Task(subagent_type: rules-toc-updater, prompt: "entry_file: .claude/doc-advisor/toc/rules/.toc_work/{{RULES_DIR}}_format_spec.yaml")
```

---

## Merge Processing Details

### Full Mode

```bash
# 1. Merge
{{PYTHON_PATH}} .claude/doc-advisor/scripts/merge_rules_toc.py --mode full

# 2. Validate (check return value)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/validate_rules_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
#    Use Phase 1 snapshot instead of recalculating current hashes.
#    This ensures files modified during Phase 2 will be re-processed next time.
cp .claude/doc-advisor/toc/rules/.toc_work/.toc_checksums_pending.yaml .claude/doc-advisor/toc/rules/.toc_checksums.yaml

# 4. Cleanup
rm -rf .claude/doc-advisor/toc/rules/.toc_work
```

### Incremental Mode

```bash
# 1. Merge
{{PYTHON_PATH}} .claude/doc-advisor/scripts/merge_rules_toc.py --mode incremental

# 2. Validate (check return value)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/validate_rules_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
#    Use Phase 1 snapshot instead of recalculating current hashes.
#    This ensures files modified during Phase 2 will be re-processed next time.
cp .claude/doc-advisor/toc/rules/.toc_work/.toc_checksums_pending.yaml .claude/doc-advisor/toc/rules/.toc_checksums.yaml

# 4. Cleanup
rm -rf .claude/doc-advisor/toc/rules/.toc_work
```

### Delete-only Mode (N=0 and M>0)

```bash
# 1. Delete only (no .claude/doc-advisor/toc/rules/.toc_work/ needed)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/merge_rules_toc.py --delete-only

# 2. Validate (check return value)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/validate_rules_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
{{PYTHON_PATH}} .claude/doc-advisor/scripts/create_checksums.py --target rules
```

---

## Error Handling

### Continue Mode (when .claude/doc-advisor/toc/rules/.toc_work/ exists)

- Resume from pending files
- If all completed or error → Proceed to merge

### On Subagent Error (No Retry)

When subagent fails, **immediately change to error status without retry**:

1. Read the entry YAML file to get its current content
2. Edit `_meta.status` from `pending` to `error` in the YAML
3. Add `_meta.error_message` with the error details from the subagent response
4. Exclude from processing (skip at merge)
5. List error files in completion report

**Concrete steps** (orchestrator uses Edit tool):
```
# 1. Read the failed entry file
Read(".claude/doc-advisor/toc/rules/.toc_work/{filename}.yaml")

# 2. Edit _meta.status and add error_message
Edit: change "status: pending" → "status: error"
Edit: add "error_message: {error details from subagent}"
```

```yaml
# Example of error status YAML (after Edit)
_meta:
  status: error
  source_file: {{RULES_DIR}}/core/architecture_rule.md
  error_message: "Subagent processing failed: File read error"
```

**Important**: To prevent infinite loops, don't leave as pending. Error files require manual review.

### On Merge Error

- Don't delete `.toc_work/`
- Report error content
- Can recover by re-running

### On Unexpected Error

**Do NOT attempt automatic recovery or workarounds.**

When encountering unexpected errors (e.g., sandbox restrictions, permission errors, environment issues):

1. Report the error details clearly
2. Ask the user how to proceed
3. Wait for user instructions before taking any action

---

## Completion Report

```
✅ rules_toc.yaml has been updated

[Summary]
- Mode: {full | incremental | continue}
- Files processed: {N}

[Cleanup]
- Deleted .claude/doc-advisor/toc/rules/.toc_work/
```
