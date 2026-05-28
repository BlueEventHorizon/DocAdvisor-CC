---
name: toc_orchestrator
description: Orchestrator workflow for {category}_toc.yaml generation
applicable_when:
  - Executing /doc-advisor:create-rules-toc or /doc-advisor:create-specs-toc skill
  - Coordinating ToC generation process
---

# ToC Orchestrator Workflow

Orchestrator workflow to generate/update `.claude/doc-advisor/toc/{category}/{category}_toc.yaml`.

> **Note**: `{category}` is either `rules` or `specs`, determined by the invoking SKILL.

## Options

| Option   | Description                                           |
| -------- | ----------------------------------------------------- |
| (none)   | Incremental update (hash-based) or resume processing  |
| `--full` | Full file scan (for initial creation or regeneration) |

## Arguments

- No arguments → incremental mode (hash-based change detection) or resume processing
- `--full` → full mode with complete scan

---

## Required Reference Documents [MANDATORY]

Read the following before processing:

- `${CLAUDE_PLUGIN_ROOT}/docs/toc_format.md` - Format definition and intermediate file schema
- `${CLAUDE_PLUGIN_ROOT}/docs/toc_update_workflow.md` - Detailed workflow

---

## Orchestrator Processing Flow

### Phase 1: Initialization

> **Note**: `init_common_config()` validates that `root_dirs` is configured for the category. If `.doc_structure.yaml` is missing or the category is not configured, scripts output `{"status": "config_required", ...}`. The skill's Error Handling section directs the user to run `/forge:setup-doc-structure`.

````
1. Check if .claude/doc-advisor/toc/{category}/.toc_work/ exists
    ↓
[If exists] → Continue mode (jump to Phase 2)
    ↓
[If not exists]
    ↓
2. Mode determination
    - --full option → full mode
    - {category}_toc.yaml doesn't exist → full mode
    - Otherwise → incremental mode
    ↓
3. Create .toc_work/ directory
    ↓
4. Identify target files and generate pending YAML templates
    ```bash
    # Full mode
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category {category} --full

    # Incremental mode
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category {category}
    ```
````

### Phase 2: Parallel Processing

> **⚠️ Context Management [IMPORTANT]**
>
> Subagent results accumulate in the parent conversation context.
> When processing many files, this can cause context overflow.
>
> **Rules:**
>
> - Subagents return minimal responses (defined in agent's "Completion Response" section)
> - After each batch completes, output a brief progress summary (e.g., "Batch 2/10 complete, 40 remaining")
> - Keep orchestrator messages minimal between batches
> - **Do NOT use `run_in_background: true`** — it breaks the Phase 2 loop
>   (pending check races with task completion, causing duplicate processing)
>
> **For large projects (100+ files):**
>
> - Consider reducing parallel batch size to 3 to lower API load and context growth
> - If context overflows mid-session, start a new session and re-run the same command.
>   `.toc_work/` with completed entries is preserved; Continue Mode automatically
>   resumes from pending files only (Phase 1 detects existing `.toc_work/`)

**Note**: Do not use `xargs` for file listing — it fails with long Japanese filenames.
Use `ls .toc_work/*.yaml` or `while read` loops instead.

```
1. Identify pending status files from .claude/doc-advisor/toc/{category}/.toc_work/*.yaml
    ↓
2. If no pending files → Go to Phase 3 (merge)
    ↓
3. Use max_workers = 5 (default defined in toc_utils.py)
    CRITICAL: Launch up to N Task tool calls in a SINGLE assistant message.
    Do NOT launch them one at a time in separate messages — this defeats parallelism.
    Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/{filename}.yaml")
    ↓
4. Wait for all N tasks to complete
    ↓
5. If pending files remain → Return to step 1
```

### Phase 3: Merge, Validation & Checksum Update

```
1. Completion check (verify all YAML are completed)
    - If pending remain → Return to Phase 2
    - All completed → Proceed to merge
    ↓
2. Merge processing
    - full: Generate new {category}_toc.yaml from .toc_work/*.yaml
    - incremental: Combine existing {category}_toc.yaml + .toc_work/*.yaml + handle deletions
    - Note: Skip non-completed files (output warning)
    ↓
3. Run validation → **Check return value**
    - Success (exit 0) → Proceed to step 4
    - Failure (exit 1) → Restore from backup, don't update checksums, abort
    ↓
4. Update checksums **only on validation success**
    ↓
5. Cleanup (delete .claude/doc-advisor/toc/{category}/.toc_work/)
    ↓
6. Report completion
    - List pending files with error_message (from YAML _meta) if any
    - If pending files with errors exist, inform the user:
      "N files remain pending (with errors). They will be retried on next run.
       To fix persistent failures, review the source files."
```

---

## Pending YAML Template Generation

Use the script to generate `.claude/doc-advisor/toc/{category}/.toc_work/{filename}.yaml` for each target file.

```bash
# Full mode (all files)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category {category} --full

# Incremental mode (changed files only)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category {category}
```

The script handles:

1. File discovery and change detection (SHA-256 content hash comparison)
2. Filename generation using SHA-256 hash of the source path (e.g., `rules/core/architecture_rule.md` → `a1b2c3d4e5f67890.yaml`)
3. Template generation with pending status

**Template format**: See "Intermediate File Schema" section in `${CLAUDE_PLUGIN_ROOT}/docs/toc_format.md`

---

## Continue Mode Details

| Condition                            | Action                                                                        |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| `--full` + `.toc_work/` exists       | Bash: `rm -rf .claude/doc-advisor/toc/{category}/.toc_work` → Start full mode |
| `.toc_work/` exists + pending remain | Resume from pending (to Phase 2)                                              |
| `.toc_work/` exists + all completed  | Go directly to merge phase (Phase 3)                                          |

---

## Incremental Mode: Change Detection Steps

### Step 1: Check Checksum File

```bash
test -f .claude/doc-advisor/toc/{category}/.toc_checksums.yaml && echo "EXISTS" || echo "NOT_EXISTS"
```

- If not exists → Fallback to full mode

### Step 2-3: Detect Changes

The `create_pending_yaml.py --category {category}` script handles:

1. Reading current file list and computing hashes
2. Comparing with `.toc_checksums.yaml`
3. Categorizing files as New/Changed/Deleted/Unchanged
4. Generating pending YAMLs for New/Changed files

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
✅ No changes - {category}_toc.yaml is up to date
```

End processing (no need to create .toc_work/)

**If N=0 and M>0**:

```
📁 Detected deleted files: M items
🔄 Running merge script to reflect deletions...
```

→ Run merge script (go directly to Phase 3, no .toc_work/ needed)

---

## Subagent Launch Examples

```
# Launch 5 in parallel (filenames are SHA256 hashes of source paths)
Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/a1b2c3d4e5f67890.yaml")
Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/1234567890abcdef.yaml")
Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/fedcba0987654321.yaml")
Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/0123456789abcdef.yaml")
Task(subagent_type: doc-advisor:toc-updater, prompt: "category: {category}, entry_file: .claude/doc-advisor/toc/{category}/.toc_work/abcdef0123456789.yaml")
```

---

## Merge Processing Details

### Full Mode

```bash
# 1. Merge
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --category {category} --mode full

# 2. Validate (check return value)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_toc.py --category {category}
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
#    Use Phase 1 snapshot instead of recalculating current hashes.
#    This ensures files modified during Phase 2 will be re-processed next time.
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_checksums.py --category {category} --promote-pending

# 4. Cleanup
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_checksums.py --category {category} --clean-work-dir
```

### Incremental Mode

```bash
# 1. Merge
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --category {category} --mode incremental

# 2. Validate (check return value)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_toc.py --category {category}
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_checksums.py --category {category} --promote-pending

# 4. Cleanup
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_checksums.py --category {category} --clean-work-dir
```

### Delete-only Mode (N=0 and M>0)

```bash
# 1. Delete only (no .toc_work/ needed)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --category {category} --delete-only

# 2. Validate (check return value)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_toc.py --category {category}
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_checksums.py --category {category}
```

---

## Error Handling

### Continue Mode (when .toc_work/ exists)

- Resume from pending files
- If all completed → Proceed to merge

### On Custom Agent Error

The `doc-advisor:toc-updater` custom Agent writes error information to the YAML file (status remains `pending`) before returning `❌ Error`.
The orchestrator does NOT need to edit the YAML — just log the error and continue.

1. Log the error file in the completion report
2. Continue processing remaining files
3. Pending files with `error_message` will be retried on next run

```yaml
# Example of error YAML (written by doc-advisor:toc-updater via write_pending.py --error)
_meta:
  status: pending
  source_file: rules/core/architecture_rule.md
  error_message: "Source file not found"
```

**Important**: If many errors occur, report the pattern to the user. Persistent failures may require source file fixes.

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
✅ {category}_toc.yaml has been updated

[Summary]
- Mode: {full | incremental | continue}
- Files processed: {N}
- Errors: {E} (if any)

[Errors] (only if E > 0)
- {source_file}: {error_message}
- {source_file}: {error_message}
→ To retry: fix the source files and run incremental mode.

[Cleanup]
- Deleted .claude/doc-advisor/toc/{category}/.toc_work/
```
