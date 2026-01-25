# rules_toc.yaml Format Definition

## Purpose

`.claude/doc-advisor/rules/rules_toc.yaml` is the **single source of truth** for the **rules-advisor Subagent** to identify documents needed for tasks.

The quality of this file determines task execution success. **Missing information is not acceptable.**

**This file serves as the Single Source of Truth for format definition and intermediate file schema.**

---

## Key Principles [MANDATORY]

- Include all rules, workflows, and format documents without omission
- Support task matching through keywords
- When in doubt, include it (never miss documents)
- **Key format**: With `{{RULES_DIR}}/` prefix (e.g., `{{RULES_DIR}}/core/architecture_rule.md`)

### YAML Formatting Rules

- **Indentation**: 2 spaces (no tabs)
- **After colon**: Always one space (`key: value`)
- **Arrays**: Hyphen + space (`- item`)
- **No null**: All fields must be filled
- **No empty arrays**: `[]` is not allowed (minimum 1 item)
- **No inline arrays**: Do not use `[a, b]` format. Always use list format
- **No multiline**: Do not use `|` or `>`. Write in single line

---

## Scan Targets [Single Source of Truth]

```
{{RULES_DIR}}/**/*.md
```

**Exclusions**:
- `.claude/doc-advisor/rules/rules_toc.yaml` (self)
- `.claude/doc-advisor/rules/.toc_work/` (work directory)
- `{{RULES_DIR}}/**/reference/` (reference materials)

---

## Change Detection Method [Single Source of Truth]

In incremental mode, file content hashes are recorded for change detection.

### Checksum File

```yaml
# .claude/doc-advisor/rules/.toc_checksums.yaml (Git tracked)
checksums:
  {{RULES_DIR}}/core/architecture_rule.md: a1b2c3d4e5f6...
  {{RULES_DIR}}/core/coding_rule.md: b2c3d4e5f6a1...
  # ... all target files
```

### Processing Flow

```
1. Scan target files (Glob)
2. Calculate hash for each file (shasum -a 256)
3. Compare with existing .toc_checksums.yaml:
   - Hash mismatch → changed → generate pending YAML
   - New file → added → generate pending YAML
   - In checksums but file missing → deleted
4. Process with subagents
5. After merge, update .toc_checksums.yaml
```

### Benefits

- Accurate change detection (no false positives/negatives)
- Git-independent (not affected by commit state)
- `.toc_checksums.yaml` is Git tracked (incremental detection works across machines)

---

## Intermediate File Schema [Single Source of Truth]

Structure definition for work files used in individual entry file method.

### File Layout

```
.claude/doc-advisor/rules/.toc_work/   # Work directory (.gitignore target)
├── {{RULES_DIR}}_core_architecture_rule.yaml
├── {{RULES_DIR}}_core_coding_rule.yaml
├── {{RULES_DIR}}_layer_domain_domain_core.yaml
└── ... (for each target file)
```

### Filename Generation Rule

Generate YAML filename from rule document path (including `{{RULES_DIR}}/` prefix):

```
{{RULES_DIR}}/core/architecture_rule.md → {{RULES_DIR}}_core_architecture_rule.yaml
{{RULES_DIR}}/layer/domain/domain_core.md → {{RULES_DIR}}_layer_domain_domain_core.yaml
{{RULES_DIR}}/workflow/plan/design_workflow.md → {{RULES_DIR}}_workflow_plan_design_workflow.yaml
```

Conversion rule: `/` → `_`, `.md` → `.yaml`

### Entry YAML Structure

```yaml
# .claude/doc-advisor/rules/.toc_work/{{RULES_DIR}}_core_architecture_rule.yaml

_meta:
  source_file: {{RULES_DIR}}/core/architecture_rule.md    # Path from project root
  status: pending                                          # pending | completed
  updated_at: null                                         # Completion time (ISO 8601 format)

# Below: rules_toc.yaml entry format (key uses source_file value)
title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
```

### _meta Field Description

| Field | Type | Description |
|-------|------|-------------|
| `source_file` | string | Target document path (from project root, e.g., `{{RULES_DIR}}/core/...`) |
| `status` | enum | `pending` (unprocessed) or `completed` (done) |
| `updated_at` | datetime/null | Completion time (ISO 8601 format), `null` if incomplete |

---

## YAML Schema Definition (Final Output)

### Top-level Structure

```yaml
metadata:
  name: string              # Index name (fixed: "Development Document Search Index")
  generated_at: datetime    # Generation time (ISO 8601 format)
  file_count: integer       # Total target file count

docs: object                # Document entries (key: file path)
```

---

### docs (Document Entries)

```yaml
docs:
  <file_path>:                 # Path from project root (e.g., "{{RULES_DIR}}/core/architecture_rule.md")
    title: string                # Title (extracted from H1)
    purpose: string              # Purpose (1-2 lines, what it defines)
    content_details: array[string] # Content details (5+ items, main rules/constraints/patterns)
    applicable_tasks: array[string] # Applicable tasks (task types that need this file)
    keywords: array[string]       # Keywords (matching terms for task descriptions, 5-10 words)
```

**Example**:
```yaml
docs:
  {{RULES_DIR}}/core/architecture_rule.md:
    title: Architecture Rules
    purpose: Defines overall architecture structure, layer design, and inter-layer communication
    content_details:
      - Directory structure
      - Layer dependencies
      - App/Domain/Infrastructure/DI/Tools/Library layer responsibilities
      - Inter-layer communication patterns
      - Factory flow
      - Data flow design
      - AsyncStream design principles
    applicable_tasks:
      - Architecture review
      - Layer violation detection
      - New layer introduction
      - Overall design review
      - Existing code understanding
    keywords:
      - architecture
      - layer
      - Clean Architecture
      - DI
      - Factory
      - Protocol-based
      - AsyncStream
      - StreamManager
```

---

## Field Guidelines

### purpose

- Describe the file's role concisely in 1-2 sentences
- Use phrases like "Defines rules for...", "Specifies workflow for..."

### content_details

- List **specific rules/constraints/patterns** in the file
- Detailed enough for subagent to understand overview without reading the file
- Must include important constraints
- 5-10 items

### applicable_tasks

- List **specific task types** that need this file
- Avoid vague expressions, use specific task names
- Include actions like "implementation", "creation", "modification"

### keywords

- **Matching terms** for task descriptions
- Include technical terms, concept names, abbreviations
- 5-10 words

---

## Complete Example

```yaml
# .claude/doc-advisor/rules/rules_toc.yaml

metadata:
  name: Development Document Search Index
  generated_at: 2026-01-11T12:00:00Z
  file_count: 25

docs:
  {{RULES_DIR}}/core/architecture_rule.md:
    title: Architecture Rules
    purpose: Defines overall architecture structure, layer design, and inter-layer communication
    content_details:
      - Directory structure
      - Layer dependencies
      - App/Domain/Infrastructure/DI/Tools/Library layer responsibilities
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

  {{RULES_DIR}}/layer/infrastructure/repository_rule.md:
    title: Repository Implementation Rules
    purpose: Defines Repository implementation's immediate response + eventual sync pattern
    content_details:
      - Repository layer responsibilities
      - Immediate response + eventual sync pattern
      - Application method for Create/Update/Delete
      - Anti-patterns
    applicable_tasks:
      - Repository implementation
      - Infrastructure layer implementation
      - CRUD operation implementation
    keywords:
      - Repository
      - immediate response
      - eventual sync
      - cache update
      - forceBroadcast
```
