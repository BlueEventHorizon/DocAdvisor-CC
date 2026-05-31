---
name: toc_update_workflow
description: "Key-based toc.yaml update workflow (per-key pending entry file method)"
applicable_when:
  - Running as the doc-advisor:toc-updater custom Agent
  - Executing the /doc-advisor:index-docs skill
  - After adding, modifying, or deleting documents in a key's desired-state paths
---

# ToC Update Workflow

> **Reference**: DES-006 §6 (desired-state sync), §6.5 (backup/restore), §6.6 (continuation),
> §10 (SKILL/agent). REQ-004 FR-N02 / FR-N04 / FR-N07.

## Overview

Workflow for updating a key's ToC at `.claude/doc-advisor/toc/keys/<slug>-<hash>/toc.yaml`.
Uses the **per-key pending entry file method**: `prepare_toc.py` generates one pending YAML per
added/updated document, each is filled independently by a `doc-advisor:toc-updater` custom Agent,
then `merge_toc.py` integrates them and reflects deletions.

There is no `category` (rules/specs) and no `.doc_structure.yaml`. The document set is the `key`'s
**complete desired-state paths**, decided by an upper layer (forge etc.) or by single mode
(`--all`, reserved key `all`).

## Architecture

### Design Philosophy

- **1 file = 1 custom Agent**: Each added/updated document is processed individually via the `doc-advisor:toc-updater` custom Agent
- **Persistent artifacts**: Each custom Agent's output remains as a pending file
- **Resumable**: Completed work is preserved on interruption; resume from incomplete (per-key continuation)
- **Single Source of Truth**: Format definition consolidated in `toc_format.md`

### Store Directory Structure

```
.claude/doc-advisor/toc/keys/<slug>-<hash>/
├── meta.yaml            # original_key, created_at, schema_version
├── toc.yaml             # Final artifact (after merge)
├── .toc_checksums.yaml  # Per-key change-detection checksums
└── .toc_work/           # Pending entry YAMLs (transient; NOT gitignored — residue signals an abnormal/incomplete merge and is surfaced via git status; see DES-006 §3.2)
    ├── <sha256-of-source-path-1>.yaml
    ├── <sha256-of-source-path-2>.yaml
    └── ... (one per added/updated file)
```

Each key has its own `store_dir`. `.toc_work/` is under that `store_dir`, so concurrent keys never
collide. The concrete `store_dir` is the parent of the `toc_path` field in the `prepare_toc.py` /
`merge_toc.py` JSON output.

---

## Key Principles [MANDATORY]

- **Single Source of Truth**: `toc_format.md` is the only source for the ToC schema and pending file schema
- **All fields required**: Fill all fields in the format definition. **No omissions** (`doc_type` is removed from the schema; never extract or emit it)
- **Keyword extraction**: Actually read each file and extract keywords from content (array format)
- **YAML syntax**: Use indentation, colons, and hyphens correctly
- **Entry key format**: Project-root-relative path (e.g., `docs/architecture.md`, `src/api/login.md`)
- **Desired-state destructiveness**: `paths` are the key's complete desired state; paths absent from this run are deleted (FR-N02-2)

---

## Workflow Overview

```
/doc-advisor:index-docs execution
    ↓
Phase 0: Continuation determination (Orchestrator, per key)
    ↓
Phase 1: prepare — desired-state diff + pending generation (prepare_toc.py)
    ↓
Phase 2: Parallel fill (toc-updater custom Agents)
    ↓
Phase 3: merge — integration + deletion reflection (merge_toc.py)
         (checksums update + .toc_work/ removal happen inside merge_toc.py)
```

---

## Phase 0: Continuation determination (Orchestrator)

Check the target key's `store_dir/.toc_work/`:

```bash
test -d "{store_dir}/.toc_work" && echo "EXISTS" || echo "NOT_EXISTS"
```

| Condition                            | Processing                                                                   |
| ------------------------------------ | ---------------------------------------------------------------------------- |
| `.toc_work/` exists + pending remain | Continuation: resume Phase 2 from existing pending YAMLs (do not re-prepare) |
| `.toc_work/` exists + all completed  | Go directly to merge (Phase 3)                                               |
| `.toc_work/` does not exist          | Normal start: Phase 1 (prepare)                                              |

> To discard a corrupted `.toc_work/` and re-prepare from scratch:
> `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --clean-work-dir` (single mode: `--all`).
> Abnormal-recovery action; confirm with the user first.

---

## Phase 1: prepare (Orchestrator)

```bash
# key specified
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths_json}'
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-file "{paths_file}"
# single mode (reserved key all)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --all
# preview only (no writes)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths_json}' --dry-run
```

`prepare_toc.py` handles:

1. Path validation (reject absolute / traversal / out-of-root symlink / missing / non-Markdown; reported in `rejected_paths`)
2. Desired-state diff vs `store_dir/.toc_checksums.yaml`: categorize as added / updated / unchanged / deleted (SHA-256 content hash)
3. Pending YAML generation for added + updated files (filename = SHA-256 of the source path)

Read the single stdout JSON (`status`, `error_code`, `toc_path`, `counts`, `rejected_paths`,
`warnings`). Branch on counts per the orchestrator decision table (no-change → done; delete-only →
merge `--delete-only`; added/updated > 0 → Phase 2).

**Pending template format**: see the "Intermediate File Schema" section in
`${CLAUDE_PLUGIN_ROOT}/formats/toc_format.md`.

---

## Phase 2: Parallel fill (custom Agent)

### Step 2.1: Identify pending YAMLs

Read `store_dir/.toc_work/*.yaml` (exclude hidden `.`-prefixed files) and identify entries with
`_meta.status: pending`.

### Step 2.2: Launch custom Agents in parallel

**Parallel count**: default 5.

```
# Orchestrator calls multiple Task tools in one message
# key specified
Task(subagent_type: doc-advisor:toc-updater, prompt: "key: {key}, entry_file: .claude/doc-advisor/toc/keys/<slug>-<hash>/.toc_work/<sha256>.yaml")
... (up to 5 simultaneously)

# single mode (reserved key all): pass `all` instead of a key
Task(subagent_type: doc-advisor:toc-updater, prompt: "all (single mode), entry_file: .claude/doc-advisor/toc/keys/all-<hash>/.toc_work/<sha256>.yaml")
```

**Note**: Do not use `xargs` for file listing — it fails with long Japanese filenames.
Use `ls .toc_work/*.yaml` or `while read` loops instead.

### Step 2.3: Custom Agent processing

Each custom Agent (`doc-advisor:toc-updater`) executes:

1. Read `entry_file`
2. Get document path from `_meta.source_file`
3. Read the document (resolve from project root)
4. Extract and set fields per "Field Guidelines" in `toc_format.md`:
   - `title` — from H1
   - `purpose` — summarize in 1–2 lines
   - `content_details` — 5–10 items
   - `applicable_tasks` — 1–10 items
   - `keywords` — 5–10 words
   - (Do **not** extract or emit `doc_type` — removed from the schema)
5. Save via `write_pending.py --key {key}` (single mode: `--all`), which sets `_meta.status: completed` and `_meta.updated_at`

### Step 2.4: Repeat

Repeat Steps 2.1–2.3 until all pending YAMLs are completed (or recorded as errored pending).

---

## Phase 3: Merge (Orchestrator)

### Step 3.1: Completion check

Verify each `store_dir/.toc_work/*.yaml`:

- `_meta.status == completed`
- `title != null`
- `purpose != null`

**If incomplete**: `merge_toc.py` skips non-completed files with a warning. Errored pending
(with `_meta.error_message`) are retried on the next run.

### Step 3.2: Merge processing

```bash
# key specified
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --key "{key}"
# single mode (reserved key all)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --all
# delete-only (added/updated == 0, deleted > 0)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --key "{key}" --delete-only
```

`merge_toc.py` performs (DES-006 §6.5):

1. Backup `toc.yaml` → `toc.yaml.bak`
2. Merge completed pending entries into `docs`, reflect deletions (paths absent from desired state, and stale entries)
3. Atomic write (`os.replace`) of `toc.yaml`; transcribe `meta.yaml` `original_key` into `metadata.key`
4. Validate
5. **On success**: recompute and write `.toc_checksums.yaml` from final docs, then remove `.toc_work/`
6. **On failure**: restore from `toc.yaml.bak`, keep checksums, preserve `.toc_work/` for retry; emit `status: error`

> The checksums update and `.toc_work/` removal are done **inside** `merge_toc.py`. The orchestrator
> does **not** run `cp .../.toc_checksums_pending.yaml .toc_checksums.yaml` or `rm -rf .../.toc_work`.

### Step 3.3: Cleanup (handled internally)

There is no separate cleanup step in the normal flow. Manual cleanup is only for abnormal recovery:

```bash
# Promote pending checksums to active (maintenance, merge not used)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --promote-pending   # single mode: --all
# Discard the work directory (recovery; confirm with user — discards filled work)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --clean-work-dir     # single mode: --all
```

---

## Validation

`merge_toc.py` validates (via `validate_toc.py`) before committing the new `toc.yaml`. The validation covers:

1. **YAML syntax**: the file parses as valid YAML (indentation, colons, hyphens, quote escaping)
2. **Required per-doc fields**: each `docs` entry has non-empty `title`, `purpose` (strings) and non-empty `content_details`, `applicable_tasks`, `keywords` (arrays). `doc_type` is NOT required (removed from the schema)
3. **Entry keys**: docs keys are project-root-relative paths

On validation failure, `toc.yaml` is restored from backup, checksums are kept, and `.toc_work/` is preserved.

---

## Error Handling

### On custom Agent error

- Keep `_meta.status` as `pending` (do NOT use an `error` status)
- Record the error in `_meta.error_message` via `write_pending.py --error`
- Entry remains eligible for automatic retry on the next run
- ToC generation is idempotent, so retrying is safe

### On merge error

- `merge_toc.py` already restored `toc.yaml` from backup and preserved `.toc_work/`
- Report the error content
- Recover by re-running (the preserved `.toc_work/` enables continuation)

---

## Quality Checklist

After generation/update, verify:

- [ ] All desired-state paths for the key are listed (added/updated reflected, deleted removed)
- [ ] Each entry has required fields (`title`, `purpose`, `content_details`, `applicable_tasks`, `keywords`)
- [ ] `purpose` states "what it defines" (1–2 lines)
- [ ] `keywords` contain task-matchable terms (5–10 words)
- [ ] YAML syntax is correct (indentation, colons, hyphens)
- [ ] `metadata.generated_at` is ISO 8601 format
- [ ] `metadata.file_count` matches the actual entry count
- [ ] `metadata.key` matches the original key (from `meta.yaml`)

---

## Related Files

- `${CLAUDE_PLUGIN_ROOT}/formats/toc_format.md` - ToC schema and pending file schema (`doc_type` removed)
- `${CLAUDE_PLUGIN_ROOT}/agents/toc-updater.md` - Single-file pending-fill custom Agent definition
- `${CLAUDE_PLUGIN_ROOT}/workflows/toc_orchestrator.md` - Orchestrator workflow (prepare → fill → merge)
- `${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py` - Desired-state diff + pending generation
- `${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py` - Pending integration + deletion reflection (backup/validate/restore inside)
- `${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py` - Per-key store helper (`--promote-pending` / `--clean-work-dir`)
- `${CLAUDE_PLUGIN_ROOT}/scripts/write_pending.py` - Pending metadata fill (used by toc-updater)
