---
name: index_toc_orchestrator
description: Orchestrator workflow for key-based toc.yaml generation (drive index_docs.py and follow its action)
applicable_when:
  - Executing the /doc-advisor:index-docs skill
  - Coordinating key-based ToC generation/update (key + project-root-relative paths)
---

# ToC Orchestrator Workflow

Canonical orchestrator workflow to generate/update a key's ToC at
`.claude/.doc-advisor/toc/<slug>/toc.yaml` from a `key` and a set of
project-root-relative `paths` (the complete desired state for that key).

> **Reference**: DES-005 §6.1 (prepare/merge 2-phase), §6.5 (backup/restore), §6.6 (continuation),
> §9 (single mode), §10 (SKILL/agent). ADR-006 (continuous dispatch). DES-008 §7.1 (transcription).
> REQ-001 FR-N02 / FR-N04 / FR-N07.

The orchestrator does **not** read `.doc_structure.yaml` and does **not** classify documents into
`rules` / `specs` categories. The document set is decided by an upper layer (forge etc.) and passed
in as `key + paths`, or resolved by single mode (`--all`, reserved key `all`).

This file is the single runtime source of truth for `/doc-advisor:index-docs`.

---

## The orchestrator's job

**Run `index_docs.py` and follow the `action` it returns.** Everything deterministic — directory
expansion, path validation, desired-state diff, frontmatter transcription, parallel-window
arithmetic, claim/lease, merge, checksums, work-dir cleanup — happens inside that one script.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --key "{key}" --dirs {dirs}
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --all
```

**Re-run the same command after each agent completes.** Initial run and resume are not
distinguished by the caller: the state lives in `store_dir/.toc_work/` and the script decides which
stage the run is in. This holds across sessions and across compaction — nothing needs to be
remembered between calls.

| `action`   | What it means                   | What the orchestrator does                                    |
| ---------- | ------------------------------- | ------------------------------------------------------------- |
| `dispatch` | there are agents to launch      | launch every element of `agents[]`, then re-run the command   |
| `wait`     | only running agents remain      | wait for a completion notification, then re-run the command   |
| `confirm`  | a human/AI decision is required | decide per `reason`, add the decision as an argument, re-run  |
| `done`     | the ToC is up to date           | report; offer write-back if `ai_extracted_paths` is non-empty |
| `error`    | the run cannot continue         | report `error_code` / `message`; ask the user                 |

`agents[]` elements carry `subagent_type` and a **ready-to-pass `prompt` string**. Launch them with
`run_in_background: true`, in a single message when there are several. Do not rebuild the prompt,
do not claim anything first (the script already claimed), and do not decide how many to launch
(the script already applied the window).

> **Why the arithmetic moved into the script**: the free-slot calculation must be
> `window − len(in_flight_groups)` (running **agent** count). Using `len(in_flight)` (entry count)
> over-subtracts, goes negative, and silently stops refilling — collapsing continuous dispatch back
> to wave batching with its mid-run tail wait (ADR-006 / Issue #29). This is exactly the kind of
> step that must not depend on an AI recomputing it correctly every round.

### Waiting for completions [MANDATORY]

Completion notifications arrive once per launched agent. **Do not re-run the command in a loop
without waiting** — the same `wait` comes back and nothing progresses.

If a notification never arrives (a killed agent, a lost notification), the claim lease expires
after its TTL (900 s by default) and the script returns that entry to `dispatch` on the next run,
so re-running recovers. If `wait` persists beyond that, treat it as abnormal: report it and ask
the user rather than looping.

### Deciding on `confirm`

| `reason`           | Material           | Decision passed back as                              |
| ------------------ | ------------------ | ---------------------------------------------------- |
| `external_symlink` | `external_pending` | `--allow-external <symlink>...` (empty = reject all) |
| `fill_error`       | `error_pending`    | `--on-fill-error retry\|merge\|abort`                |

`external_symlink` **only happens under `--all`** (a whole-root scan). Nothing was passed in as a
target there, so the scan does not leave the project root on its own. Show the **resolved real
path** and the affected file count for each entry before asking; nothing has been written yet.

**Targets given explicitly (`--dirs` / `--paths`) are indexed even when they cross the root through
a symlink** (NFR-N06 / REQ-001 §6.1a). The caller decided to index them and knows they are
symlinks; blocking them here would split that decision across layers, and an upper layer that
calls index-docs once cannot answer a question. The notice arrives as a `warning` instead — and
only on the **first** response, since the diff runs once. Surface it there or it is gone.

For `fill_error`, state the consequence plainly before asking. Merging with failed entries drops
those documents from this run's ToC, and for an **updated** document it also writes a
current-content checksum — so the next run sees "unchanged" and the revision is never indexed
again (silent staleness).

`--on-fill-error retry` clears the error state first, then puts the entry through the normal claim
path — so a second run while the retry is still in flight returns `wait` rather than dispatching the
same entry twice. Retrying a **permanent** failure (a problem in the source document) will fail
again every time; the script says so in `warnings`. Fix the document, or accept the drop with
`merge`.

---

## Store Directory Layout

Each key has its own store directory; there is no shared category directory.

```
.claude/.doc-advisor/toc/<slug>/
├── toc.yaml             # Final ToC (metadata + docs)
├── .toc_checksums.yaml  # Per-key change-detection checksums
└── .toc_work/           # pending YAMLs (transient; NOT gitignored)
```

`.toc_work/` for a key lives under that key's `store_dir`, so multiple keys never collide.

`.toc_work/` is intentionally **not** gitignored. In normal operation the merge removes it on
success. If it shows up as untracked in `git status`, that is the signal of an interrupted or
abnormal run — and re-running the same command resumes from it. Hiding it in `.gitignore` would
remove the only visible symptom.

**Do not inspect the work dir by hand.** No `ls .toc_work/*.yaml`, no reading `_meta.status`, no
counting pending files. The script's output is the single source of truth for what state the run is
in; the conversation is not.

---

## Context Management [IMPORTANT]

Subagent results accumulate in the parent conversation context. With many files this can overflow.

- Subagents return minimal responses (defined in the agent's "Completion Response" section)
- After each completion, output a brief progress line (e.g. `completed 12/29, 5 in-flight`)
- Keep orchestrator messages minimal between completions
- If context overflows mid-run, **start a new session and re-run the same command**. Completed
  entries in `store_dir/.toc_work/` are preserved, expired claim leases return to the dispatch
  pool, and the run continues from where it stopped

### Parallelism (large projects, 100+ files)

The window is **10 concurrent agents** — the verified safe range (ADR-006 案 A). One agent processes
a group of up to 3 same-directory neighbours (限定バッチング / 案 B), which cuts launch count and
規約再読 while keeping each document extracted independently (context rot 回避).

These values are constants inside `index_docs.py` and are deliberately not exposed as options: they
are not a judgement the caller makes per run. On a low API tier that hits 429 rate limits, diagnose
with the core CLIs (`toc_store.py --work-status --max-batch N`) rather than adding flags to the
wrapper.

---

## Design Philosophy

- **Transcription before fill**: pending whose source document already carries a trustworthy
  doc-advisor frontmatter are completed by transcription before the fill phase, so no agent is
  launched for them (DES-008 §7.1). When every pending can be transcribed, the run reaches `done`
  with **zero agents launched**
- **1 group = 1 custom agent**: added/updated documents are filled by the `doc-advisor:toc-updater`
  custom agent, one agent per same-directory group (ADR-006 案 B)
- **Continuous dispatch (sliding-window)**: groups are dispatched with a parallel window and
  refilled as each completes, guarded by claim/lease so no group is dispatched twice
- **Persistent artifacts**: each agent's output stays as a pending file until merge
- **Resumable**: interrupted runs resume from the preserved work dir; the caller re-runs the same
  command
- **Indexing never modifies sources**: the pipeline only writes under `.claude/`. Writing metadata
  back into a document is a separate, explicitly-approved action (`write-frontmatter`)
- **Single Source of Truth**: `formats/toc_format.md` defines the ToC and pending file schemas

---

## Key Principles for filling [MANDATORY]

These apply to the `doc-advisor:toc-updater` agent, not to the orchestrator.

- **All fields required**: fill every field in the format definition. `doc_type` is removed from the
  schema; never extract or emit it
- **Keyword extraction**: actually read each source file and extract keywords from its content
- **YAML syntax**: preserve valid indentation, colons, hyphens, and quote escaping
- **Entry key format**: project-root-relative paths, e.g. `docs/architecture.md`
- **Desired-state destructiveness**: `paths` are the key's complete desired state; paths absent from
  this run are deleted (FR-N02-2)

---

## Abnormal recovery (core CLIs)

The normal pipeline never calls the core scripts directly. Use them only for the cases below, and
confirm with the user first.

| Situation                                                                                                               | Command                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Discard `.toc_work/` and start over (corrupted pending, a permanently failing document)                                 | `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --clean-work-dir` (single mode: `--all`) |
| Return a failed entry to the normal pending pool by hand (diagnosis only; `--on-fill-error retry` does this internally) | `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --reset-error <entry...>`                |
| Inspect deletions before committing to them                                                                             | `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths}' --dry-run`      |
| Promote pending checksums without a merge (maintenance)                                                                 | `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --promote-pending`                       |

`--clean-work-dir` may discard already-filled work; that is why it needs confirmation.

---

## Validation

Before committing the new `toc.yaml`, the merge validates:

1. **YAML syntax**: the file parses as valid YAML
2. **Required per-doc fields**: each `docs` entry has non-empty `title`, `purpose`,
   `content_details`, `applicable_tasks`, `keywords`. `doc_type` is not required and must not be emitted
3. **Entry keys**: docs keys are project-root-relative paths

On failure, `toc.yaml` is restored from backup, checksums are left unchanged, and `.toc_work/` is
preserved so the run can be retried. The wrapper surfaces this as `action: error`.

---

## Error Handling

### On agent error

The `doc-advisor:toc-updater` agent writes the error into its pending YAML (status stays `pending`)
before returning `❌ Error`. The orchestrator does not edit the YAML.

```yaml
_meta:
  status: pending
  source_file: docs/architecture.md
  error_message: "Source file not found"
```

The next run surfaces these as `action: confirm` / `reason: fill_error`. If many entries fail,
report the pattern — persistent failures usually mean the source documents need fixing, and
retrying will not help.

### On unexpected error

**Do NOT attempt automatic recovery or workarounds.** Report the error details clearly, ask the
user how to proceed, and wait for instructions.

---

## Quality Checklist

After `action: done`, verify from the returned JSON and the final ToC:

- [ ] All desired-state paths for the key are listed, including added/updated files and excluding deleted files
- [ ] Each entry has required fields: `title`, `purpose`, `content_details`, `applicable_tasks`, `keywords`
- [ ] `purpose` states what the document defines
- [ ] `keywords` contain task-matchable terms
- [ ] `metadata.file_count` matches the actual entry count
- [ ] `metadata.key` matches the original key
- [ ] `store_dir/.toc_work/` is gone (its presence after `done` would indicate an incomplete merge)

---

## Completion Report

Take the values from the `done` payload verbatim; do not recount them.

```
✅ index-docs complete (key: {key | all})

[Summary]
- added / updated / deleted / unchanged: {counts}
- transcribed from frontmatter / AI-extracted: {transcribed} / {ai_extracted}
- toc_path: {toc_path}
- deleted paths: {deleted_paths} (if any)
- rejected paths / dirs: {rejected_paths} / {rejected_dirs} (if any)
- Warnings: {warnings} (if any)
```

`warnings` must not be swallowed. They can report: a frontmatter that carries the `doc-advisor`
marker but is not trustworthy (a spec violation, or metadata left behind by a body edit — that
document was AI-extracted this run); an external symlink that **was** indexed (with its resolved
target and file count — a notice, not a fault) or one that was not (rejected under `--all`);
documents dropped by merging over known fill errors; or a transcription phase that could not run.
