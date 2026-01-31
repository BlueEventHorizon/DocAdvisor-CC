---
name: specs_toc_update_workflow
description: specs_toc.yaml update workflow (individual entry file method)
applicable_when:
  - Running as specs-toc-updater Agent
  - Executing /create-specs_toc command
  - After adding, modifying, or deleting requirement/design documents
---

# specs_toc.yaml Update Workflow

## Overview

Workflow for updating `.claude/doc-advisor/specs/specs_toc.yaml`. Uses **individual entry file method** with interruption tolerance, processing each requirement/design document in parallel.

## Architecture

### Design Philosophy

1. **1 file = 1 subagent**: Process each requirement/design document individually
2. **Persistent artifacts**: Each subagent's output remains as a file
3. **Resumable**: Completed work is preserved on interruption, resume from incomplete
4. **Single Source of Truth**: Format definition consolidated in `specs_toc_format.md`

### Directory Structure

```
.claude/doc-advisor/specs/
├── specs_toc.yaml              # Final artifact (after merge)
├── .toc_checksums.yaml         # Change detection checksums
└── .toc_work/                  # Work directory (.gitignore target)
    ├── specs_main_requirements_app_overview.yaml
    ├── specs_main_design_list_screen_design.yaml
    └── ... (for each target file)
```

---

## Key Principles [MANDATORY]

- **Format definition**: Follow `specs_toc_format.md` (includes intermediate file schema, doc_type determination rules)
- **All fields required**: Fill all fields in format definition. **No omissions**
- **Keyword extraction**: Actually read each file and extract keywords from content (5-10 words)
- **YAML syntax**: Use indentation, colons, and hyphens correctly

---

## Workflow Overview

```
/create-specs_toc execution
    ↓
Check .claude/doc-advisor/specs/.toc_work/ existence
    ↓
[If not exists] New processing
    ├─ full: Generate pending YAML for all files
    └─ incremental: Generate pending YAML for changed files (hash comparison)
    ↓
[If exists] Continue processing
    └─ Identify existing pending YAMLs and continue
    ↓
Subagent parallel processing (5 parallel)
    ↓
Merge after all complete
    ├─ full: Generate specs_toc.yaml from .toc_work/*.yaml
    └─ incremental: Merge existing specs_toc.yaml + .toc_work/*.yaml + deletions
    ↓
Delete .toc_work/ (cleanup)
```

---

## Phase 1: Initialization (Orchestrator)

### Step 1.1: Check .claude/doc-advisor/specs/.toc_work/ existence

```bash
test -d .claude/doc-advisor/specs/.toc_work && echo "EXISTS" || echo "NOT_EXISTS"
```

### Step 1.2: Processing when not exists

#### Mode Determination

| Condition | Mode | Processing |
|-----------|------|------------|
| `--full` option specified | full | Scan all files |
| specs_toc.yaml doesn't exist | full | Scan all files |
| Otherwise | incremental | Process changed files only |

#### full mode initialization

1. Create `.toc_work/` directory
2. Get target files with Glob:
   ```
   specs/{feature}/requirements/**/*.md
   specs/{feature}/design/**/*.md
   ```
3. Generate pending YAML template for each file

#### incremental mode initialization (hash method)

1. Create `.toc_work/` directory
2. Detect changed files using hash method
3. Changed/new files → Generate pending YAML template
4. Deleted files → Auto-detected during merge (merge_specs_toc.py detects via checksum comparison)

### Step 1.3: Processing when exists (continue mode)

1. Identify files with `_meta.status == pending` from `.toc_work/*.yaml`
2. If incomplete files exist, continue processing
3. If all completed, proceed to merge phase

---

## Phase 2: Parallel Processing (Subagent)

### Processing Unit

**One subagent handles one YAML file**

### Parallel Count

**5 parallel** (Orchestrator calls 5 Task tools in one message)

### Subagent Processing

1. Read target YAML (get `_meta.source_file`)
2. Read requirement/design document file
3. Extract and set fields according to format definition:
   - `doc_type`: Use `_meta.doc_type` value
   - `title`: Extract from H1
   - `purpose`: Summarize in 1-2 lines
   - `content_details`: Content details (5-10 items)
   - `applicable_tasks`: Applicable tasks
   - `keywords`: 5-10 words
4. Set `_meta.status: completed` and `_meta.updated_at`
5. Write and save

### Repeat Processing

Continue launching subagents (5 parallel) while pending files remain

---

## Phase 3: Merge

### Step 3.1: Completion Check

Verify each YAML meets:
- `_meta.status == completed`
- `title`, `purpose`, `content_details`, `applicable_tasks`, `keywords` are not null

Output warning if incomplete (processing continues)

### Step 3.2: Merge Processing

#### full mode

1. Read all `.claude/doc-advisor/specs/.toc_work/*.yaml`
2. Aggregate into `docs` section (key: file path with `specs/` prefix)
3. Set metadata:
   - `name`: "Requirement & Design Document Search Index"
   - `generated_at`: Current time (ISO 8601 format)
   - `file_count`: Total count
4. Write to `.claude/doc-advisor/specs/specs_toc.yaml`

#### incremental mode

1. Read existing `.claude/doc-advisor/specs/specs_toc.yaml`
2. Detect deleted files via checksum comparison and remove corresponding entries
3. Overwrite/add entries from `.toc_work/*.yaml`
4. Update metadata
5. Write to `.claude/doc-advisor/specs/specs_toc.yaml`
6. Update `.claude/doc-advisor/specs/.toc_checksums.yaml` (run `/create-toc-checksums` skill)

### Step 3.3: Cleanup

Delete `.toc_work/` directory:
```bash
rm -rf .claude/doc-advisor/specs/.toc_work
```

---

## Pending YAML Template Generation

- Input: File path (e.g., `specs/main/requirements/app_overview.md`)
- Output: `.claude/doc-advisor/specs/.toc_work/specs_main_requirements_app_overview.yaml`

Filename conversion rule: `/` → `_`, `.md` → `.yaml` (including `specs/` prefix)

---

## Validation

Check before merge:

1. **YAML syntax check**:
   - Accuracy of indentation, colons, hyphens
   - Quote escaping

2. **Required field check**:
   - metadata: name, generated_at, file_count
   - docs: Each entry has doc_type, title, purpose, content_details, applicable_tasks, keywords

3. **File existence check**:
   - All files listed in docs actually exist

---

## Error Handling

### On subagent error

- Log error information
- `_meta.status` remains `pending`
- Retry in next batch

### On merge error

- Do not delete `.claude/doc-advisor/specs/.toc_work/` (can re-run)
- Report error content
- Prompt manual intervention

---

## Quality Checklist

After generation/update, verify:

- [ ] All requirements/ and design/ files are listed
- [ ] Each entry has required fields (doc_type, title, purpose, content_details, applicable_tasks, keywords)
- [ ] purpose contains "what it defines" (1-2 lines)
- [ ] keywords contain task-matchable terms (5-10 words)
- [ ] YAML syntax is correct (indentation, colons, hyphens)
- [ ] Generated time (metadata.generated_at) is ISO 8601 format
- [ ] File count (metadata.file_count) matches actual file count

---

## Related Files

- `specs_toc_format.md` - Format definition (Single Source of Truth)
- `agents/specs-toc-updater.md` - Single file processing subagent
- `commands/create-specs_toc.md` - Orchestrator command
- `agents/specs-advisor.md` - Search subagent
