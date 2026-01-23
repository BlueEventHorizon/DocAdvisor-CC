---
description: Generate AI-searchable structured ToC from requirements and design documents ({{SPECS_DIR}})
---

# Generate AI-searchable structured ToC from requirements and design documents

Orchestrator command to generate/update `.claude/doc-advisor/specs/specs_toc.yaml`.

## Options

| Option | Description |
|--------|-------------|
| (none) | Incremental update (hash-based) or resume processing |
| `--full` | Full file scan (for initial creation or regeneration) |

## Arguments

**Arguments**: $ARGUMENTS

- No arguments → incremental mode (hash-based change detection) or resume processing
- `--full` → full mode with complete scan

---

## Required Reference Documents [MANDATORY]

Read the following before processing:
- `.claude/doc-advisor/docs/specs_toc_format.md` - Format definition (Single Source of Truth)
- `.claude/doc-advisor/docs/specs_toc_update_workflow.md` - Detailed workflow

---

## Orchestrator Processing Flow

### Phase 1: Initialization

```
1. Check if .toc_work/ exists
    ↓
[If exists] → Continue mode (jump to Phase 2)
    ↓
[If not exists]
    ↓
2. Mode determination
    - --full option → full mode
    - specs_toc.yaml doesn't exist → full mode
    - Otherwise → incremental mode
    ↓
3. Create .toc_work/ directory
    ↓
4. Identify target files
    - full: Get all files with Glob
    - incremental: Detect changed files with hash method (deletions auto-detected at merge)
    ↓
5. Generate pending YAML templates
```

### Phase 2: Parallel Processing

```
1. Identify pending status files from .toc_work/*.yaml
    ↓
2. If no pending files → Go to Phase 3 (merge)
    ↓
3. Select up to 5 files and launch subagents in parallel
    Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{filename}.yaml")
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
    - full: Generate new specs_toc.yaml from .toc_work/*.yaml
    - incremental: Combine existing specs_toc.yaml + .toc_work/*.yaml + auto-detect deleted files
    - Note: Skip error status files (output warning)
    ↓
3. Run validation → **Check return value**
    - Success (exit 0) → Proceed to step 4
    - Failure (exit 1) → Restore from backup, don't update checksums, abort
    ↓
4. Update checksums **only on validation success**
    ↓
5. Cleanup (delete .toc_work/)
    ↓
6. Report completion (list error files if any)
```

---

## Pending YAML Template Generation

Generate `.toc_work/{filename}.yaml` for each target file.

1. Convert file path to work filename (e.g., `{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/login.md` → `{{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_login.yaml`)
2. Determine doc_type from path (`{{REQUIREMENT_DIR_NAME}}/` → `requirement`, `{{DESIGN_DIR_NAME}}/` → `design`)
3. Generate template and save with Write

**Filename conversion rule**: `/` → `_`, `.md` → `.yaml`

**Template format**: See "Intermediate File Schema" section in `.claude/doc-advisor/docs/specs_toc_format.md`

---

## Continue Mode Details

| Condition | Action |
|-----------|--------|
| `--full` + `.toc_work/` exists | Bash: `rm -rf .claude/doc-advisor/specs/.toc_work` → Start full mode |
| `.toc_work/` exists + pending remain | Resume from pending (to Phase 2) |
| `.toc_work/` exists + all completed | Go directly to merge phase (Phase 3) |

---

## Incremental Mode: Change Detection Steps

### Step 1: Check Checksum File

```bash
test -f .claude/doc-advisor/specs/.toc_checksums.yaml && echo "EXISTS" || echo "NOT_EXISTS"
```

- If not exists → Fallback to full mode

### Step 2: Get Current File List and Hashes

```bash
# Target file list ({{REQUIREMENT_DIR_NAME}}/ and {{DESIGN_DIR_NAME}}/ subdirectories only)
find {{SPECS_DIR}} \( -path "*/{{REQUIREMENT_DIR_NAME}}/*.md" -o -path "*/{{DESIGN_DIR_NAME}}/*.md" \) | grep -v ".toc_work" | grep -v "reference" | grep -v "/info/" | sort

# Calculate hash for each file
shasum -a 256 {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md | cut -d' ' -f1
```

### Step 3: Compare Checksums

1. Read `.claude/doc-advisor/specs/.toc_checksums.yaml`
2. For each file:
   - **New**: Not in checksums → Generate pending YAML
   - **Changed**: Hash mismatch → Generate pending YAML
   - **Deleted**: In checksums but file missing → Auto-delete at merge (merge_specs_toc.py handles)
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
✅ No changes - specs_toc.yaml is up to date
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
# Launch 5 in parallel
Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_login.yaml")
Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_user_profile.yaml")
Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{{SPECS_DIR}}_main_{{DESIGN_DIR_NAME}}_login_screen.yaml")
Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{{SPECS_DIR}}_main_{{DESIGN_DIR_NAME}}_api_design.yaml")
Task(subagent_type: specs-toc-updater, prompt: "entry_file: .claude/doc-advisor/specs/.toc_work/{{SPECS_DIR}}_auth_{{REQUIREMENT_DIR_NAME}}_oauth.yaml")
```

---

## Merge Processing Details

### Full Mode

```bash
# 1. Merge
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --mode full --cleanup

# 2. Validate (check return value)
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
python3 .claude/skills/doc-advisor/scripts/create_checksums.py --target specs
```

### Incremental Mode

```bash
# 1. Merge
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --mode incremental --cleanup

# 2. Validate (check return value)
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
python3 .claude/skills/doc-advisor/scripts/create_checksums.py --target specs
```

### Delete-only Mode (N=0 and M>0)

```bash
# 1. Delete only (no .toc_work/ needed)
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --delete-only

# 2. Validate (check return value)
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py
# → exit 0: Validation success, proceed
# → exit 1: Validation failed, restore from backup and abort

# 3. Update checksums (only on validation success)
python3 .claude/skills/doc-advisor/scripts/create_checksums.py --target specs
```

---

## Error Handling

### Continue Mode (when .toc_work/ exists)

- Resume from pending files
- If all completed or error → Proceed to merge

### On Subagent Error (No Retry)

When subagent fails, **immediately change to error status without retry**:

1. Change `_meta.status` to `error` in the YAML
2. Record error content in `_meta.error_message`
3. Exclude from processing (skip at merge)
4. List error files in completion report

```yaml
# Example of error status YAML
_meta:
  status: error
  source_file: {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/screens/login_screen.md
  error_message: "Subagent processing failed: File read error"
```

**Important**: To prevent infinite loops, don't leave as pending. Error files require manual review.

### On Merge Error

- Don't delete `.toc_work/`
- Report error content
- Can recover by re-running

---

## Completion Report

```
✅ specs_toc.yaml has been updated

[Summary]
- Mode: {full | incremental | continue}
- Files processed: {N}
- specs: {N}
- designs: {N}

[Cleanup]
- Deleted .toc_work/
```
