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

**This section is the single place that governs the language of field values.** The Field Guidelines below describe what each field must convey; any English wording they show is an example of the content, not a language rule of its own.

- **Write every field value in English, regardless of the source document's body language.** This holds for values written by the AI and for values transcribed from a document's frontmatter alike
- **No language mixing inside `toc.yaml`.** The ToC is updated by desired-state diff, so `unchanged` entries are never re-extracted. Following the body's language would leave "new/changed entries in the body's language, everything else in the previous language" permanently in place; fixing the language makes that state impossible
- **query-worker can compare every entry against one consistent basis.** Search reads the whole ToC and matches by meaning (base/FNC-002); per-entry language differences leave room for the synonym and cross-document judgements to drift
- `keywords`, the field that contributes most to search, is dominated by identifiers (class names, method names), so writing it in English loses no information
- **Staleness of a document's frontmatter is detected mechanically by `body_hash`**, so there is no need to rely on matching the body's language to keep metadata maintained

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

`extracted_by` is likewise **not** in the base template. It records how the entry was filled and is written only when an entry reaches `completed`, so the base template (still `pending`) has no value to record. It is absent on the `--error` path as well, because a failed entry was never filled.

### _meta Field Description

| Field           | Type          | Description                                                                                                                                                                                              |
| --------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `source_file`   | string        | Target document path (from project root)                                                                                                                                                                 |
| `status`        | enum          | `pending` (unprocessed) or `completed` (done)                                                                                                                                                            |
| `error_message` | string        | Error details, set only on failure by `write_pending.py --error` (`status` remains `pending`)                                                                                                            |
| `updated_at`    | datetime/null | Completion time (ISO 8601 format), `null` if incomplete                                                                                                                                                  |
| `claimed_at`    | datetime      | Optional, transient. Set by `toc_store.py --claim` for continuous-dispatch lease; absent until claimed and cleared on completion                                                                         |
| `extracted_by`  | enum          | Provenance, set on `completed`. `frontmatter` = transcribed by `fm_to_pending.py`; `ai` = extracted by `write_pending.py` via the `toc-updater` Agent. **Never emitted to `toc.yaml`** (report use only) |

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

### Character Domain (all five fields) [MANDATORY]

**Every field value is single-line plain text and carries no character that has meaning in the YAML subset this project writes.** This is not a style preference; it is a value domain, and the conversions below are applied mechanically wherever a value enters — both when writing a document's frontmatter and when an AI-written value enters the ToC pipeline.

**The rejection of `\` is checked when writing frontmatter and when transcribing out of the ToC, not when writing `toc.yaml`.** A value containing `\` can therefore reach `toc.yaml`, and such an entry stays permanently `incomplete_entry` for transcription. No check was added at that point because the case has not been observed (a scan of 1392 existing ToC values found none): adding a second place that implements the same rule causes a known harm, while this case so far causes none. Add the check when it is observed.

Characters outside the domain are handled in one of two ways, decided by whether a **meaning-preserving substitute exists**. Rejecting a value for a purely notational reason would send the document's whole metadata back through AI re-extraction, and the cause would be a symbol that does not change what the value says.

| Outside the domain                 | Handling                     | Why                                                                                                                                                 |
| ---------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `"` (double quote)                 | **converted** to `` ` ``     | The writer escapes it as `\"` and the `toc.yaml` reader strips quotes without restoring escapes. A backtick reads the same in English prose         |
| newline / CR / tab                 | **converted** to a space     | Values are single-line by definition, so collapsing whitespace preserves the meaning                                                                |
| `'` as the first or last character | **converted** to `` ` ``     | The reader strips quote characters from both ends and would delete it. Only the edges are converted; an interior `'` (`don't`) is left              |
| `\` (backslash)                    | **rejected** (no substitute) | Dropping it turns `\n handling` into `n handling`; replacing it with `/` changes an escape sequence into a path. The value does not say which it is |

Conversions are **reported**, never silent: `fm_write` returns the converted field names in `normalized_fields` and `fm_run` surfaces them in `warnings`. The value written differs from the value authored, and that fact belongs in the output.

Characters that merely force quoting are **left alone**: `:` `#`, a leading `-`, a trailing space, an interior `'`, and values that look like numbers or booleans. Quoting alone survives the round trip; only backslash-escaped content does not.

The read side still checks the full domain. A frontmatter hand-edited to contain `"` is detected as not trustworthy and routed to re-extraction, and the check doubles as the post-condition that keeps "what can be written" inside "what is trusted".

Values whose content cannot be chosen (captured exception text written to a pending `_meta.error_message`) are normalized at the point of capture, and there the backslash is dropped rather than rejected. Diagnostics tolerate a lossy normalization; data does not, which is why the two are handled differently.

### purpose

- Describe the file's role concisely (max 200 characters)
- State plainly what the document establishes and for what subject; e.g. "Defines rules for ...", "Specifies requirements for ...", "Describes design for ...". What matters is the subject, not the opening phrase

### content_details

- List **specific content items** in the file (rules/constraints/patterns/requirements/design elements)
- Detailed enough for the query SKILL / Agent to understand the overview without reading the file
- Must include important constraints/requirements
- Prioritize items **unique to this document** — generic items (e.g., "error handling", "overview") add little value
- Describe **concrete details under each heading**, not the heading itself — name the specific element defined under it, using its identifiers where they exist (e.g., not "Error handling" but "ContactContainerError enum with differentContainer, readOnlyContainer variants")
- Max 10 items

### applicable_tasks

- List **specific task types** that need this file
- Avoid vague expressions, use specific task names
- Name the action performed as well as its subject, not the subject alone; e.g. "implementation", "creation", "modification", "review" of something specific
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
