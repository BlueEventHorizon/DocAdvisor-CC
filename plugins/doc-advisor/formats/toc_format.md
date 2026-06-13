---
name: toc_format
description: Format definition for the per-key toc.yaml (Single Source of Truth)
applicable_when:
  - Creating or updating ToC entries
  - Validating a key's toc.yaml structure
---

# ToC YAML Format Definition

## Purpose

`.claude/.doc-advisor/toc/{slug}/toc.yaml` is the **single source of truth** for the `query-docs` search SKILL to identify documents needed for tasks.

ToC is managed per opaque `key` (decided by the upper layer, or the reserved key `all` in single mode). doc-advisor does not interpret the meaning of a key (e.g., rules / specs). There is no `category` concept and no `doc_type` field.

The quality of this file determines task execution success. **Missing information is not acceptable.**

**This file serves as the Single Source of Truth for both the final ToC schema and the intermediate (pending) file schema.**

---

## Key Principles [MANDATORY]

- Include all target documents without omission
- Support task matching through keywords
- When in doubt, include it (never miss documents)
- **docs key format**: Project-root-relative path (e.g., `docs/rules/architecture_rule.md`, `docs/specs/app_overview.md`)
- **No `doc_type`**: The schema has no `doc_type` field. Never extract or emit it. Search relies on `title` / `purpose` / `keywords` that the AI reads, so removing `doc_type` has **no impact** on search behavior (base/FNC-002 continued)

### Language Rule

- **All field values must be written in English**, regardless of the source document's language
- ToC is a search index for AI agents — English ensures consistent keyword matching across multilingual projects

### YAML Formatting Rules

- **Indentation**: 2 spaces (no tabs)
- **After colon**: Always one space (`key: value`)
- **Arrays**: Hyphen + space (`- item`)
- **No null**: All fields must be filled
- **No empty arrays**: `[]` is not allowed (minimum 1 item)
- **No inline arrays**: Do not use `[a, b]` format. Always use list format
- **No multiline**: Do not use `|` or `>`. Write in single line

---

## Intermediate File Schema [Single Source of Truth]

Structure definition for the pending work files generated per entry by `prepare_toc.py` and filled by the `toc-updater` agent (via `write_pending.py`).

### File Layout

```
.claude/.doc-advisor/toc/{slug}/.toc_work/   # Work directory (per-key, removed by merge_toc.py on success)
├── {sha256_hash_16chars}.yaml
└── ... (for each target file)
```

The `.toc_work/` directory lives under each key's store directory, so multiple keys never collide. It is removed by `merge_toc.py` on a successful merge; a leftover `.toc_work/` is an abnormal signal (incomplete merge) and is intentionally left untracked so `git status` surfaces it.

### Filename Generation Rule

Generate the YAML filename using the SHA256 hash of the source file path:

```python
hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:16] + ".yaml"
```

```
docs/rules/architecture_rule.md → a1b2c3d4e5f67890.yaml
docs/specs/app_overview.md      → 1234567890abcdef.yaml
```

The original path is preserved in `_meta.source_file` inside each YAML file.
Hash-based naming avoids filename length limits, case-insensitive collisions, and special character issues.

### Entry YAML Structure

```yaml
_meta:
  source_file: docs/path/to/document.md # Path from project root
  status: pending # pending | completed
  updated_at: null # Completion time (ISO 8601 format)

# Below: toc.yaml entry format (docs key uses the source_file value)
title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
```

`error_message` is **not** part of the base pending template. It is written by `write_pending.py --error` only when processing a source file fails; `status` then remains `pending` so the entry is retried on the next run.

`claimed_at` is likewise **not** in the base template. In continuous-dispatch fill (ADR-006 / Issue #29) `toc_store.py --claim` stamps it into `_meta` right before a `toc-updater` Agent is launched, so `--work-status` can exclude in-flight entries from `pending` (prevents double-dispatch). It is a transient runtime marker: `write_pending.py` rebuilds `_meta` on `completed` / `error`, so it disappears once the entry is filled; a stale `claimed_at` (older than the lease TTL) is treated as un-claimed and re-dispatched.

### _meta Field Description

| Field           | Type          | Description                                                                                                                      |
| --------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `source_file`   | string        | Target document path (from project root)                                                                                         |
| `status`        | enum          | `pending` (unprocessed) or `completed` (done)                                                                                    |
| `error_message` | string        | Error details, set only on failure by `write_pending.py --error` (`status` remains `pending`)                                    |
| `updated_at`    | datetime/null | Completion time (ISO 8601 format), `null` if incomplete                                                                          |
| `claimed_at`    | datetime      | Optional, transient. Set by `toc_store.py --claim` for continuous-dispatch lease; absent until claimed and cleared on completion |

---

## YAML Schema Definition (Final Output)

### Top-level Structure

```yaml
metadata:
  name: string # Index name (derived from the key)
  key: string # Original key (written from the --key argument)
  generated_at: datetime # Generation time (ISO 8601 format)
  file_count: integer # Total target file count

docs: object # Document entries (key: project-root-relative file path)
```

The `metadata.key` field holds the **original key** so the ToC is self-contained for consumers. `merge_toc.py` writes the `--key` argument value into `metadata.key` when writing `toc.yaml`.

---

### docs (Document Entries)

```yaml
docs:
  <file_path>: # Path from project root
    title: string # Title (extracted from H1)
    purpose: string # Purpose (max 200 chars)
    content_details: array[string] # Content details (max 10 items)
    applicable_tasks: array[string] # Applicable tasks (max 10 items)
    keywords: array[string] # Keywords (max 10 words)
```

**Rules Example**:

```yaml
docs:
  docs/rules/architecture_rule.md:
    title: Architecture Rules
    purpose: Defines overall architecture structure, layer design, and inter-layer communication
    content_details:
      - Directory structure
      - Layer dependencies
      - Inter-layer communication patterns
      - Data flow design
      - AsyncStream design principles
    applicable_tasks:
      - Architecture review
      - Layer violation detection
      - Overall design review
    keywords:
      - architecture
      - layer
      - Clean Architecture
      - DI
      - Factory
```

**Specs Example**:

```yaml
docs:
  docs/specs/app_overview.md:
    title: Application Overview Specification
    purpose: Defines overall requirements, feature scope, and use cases for the application
    content_details:
      - Application overview
      - Main feature list
      - Use case definitions
      - Screen navigation overview
      - Data requirements
    applicable_tasks:
      - New feature implementation planning
      - Feature scope confirmation
      - Overall design understanding
    keywords:
      - application
      - requirements
      - feature list
      - use case
      - screen navigation
```

---

## Field Guidelines

### purpose

- Describe the file's role concisely (max 200 characters)
- Use phrases like "Defines rules for...", "Specifies requirements for...", "Describes design for..."

### content_details

- List **specific content items** in the file (rules/constraints/patterns/requirements/design elements)
- Detailed enough for the query SKILL / Agent to understand the overview without reading the file
- Must include important constraints/requirements
- Prioritize items **unique to this document** — generic items (e.g., "error handling", "overview") add little value
- Describe **concrete details under each heading**, not the heading itself (e.g., not "Error handling" but "ContactContainerError enum with differentContainer, readOnlyContainer variants")
- Max 10 items

### applicable_tasks

- List **specific task types** that need this file
- Avoid vague expressions, use specific task names
- Include actions like "implementation", "creation", "modification", "review"
- Prioritize the most specific and distinguishing tasks
- Max 10 items

### keywords

- **Matching terms** for task descriptions
- Prioritize **class names, method names, and domain-specific terms** (e.g., `ContactListViewModel`, `canAddToGroup`, `debounce`)
- Include technical terms, concept names, abbreviations, feature names
- Avoid category labels (e.g., "workflow", "document") — prefer terms unique to this document
- Max 10 words

---

## Notes on the final file

The per-doc entries follow the `docs` schema and examples above. The top-level `metadata` block
(`name` / `key` / `generated_at` / `file_count`) is written by `merge_toc.py` from the `--key`
argument and the final doc set — the `toc-updater` agent does **not** produce it. A complete file
is simply the `metadata` block followed by one `docs` entry per indexed document.
