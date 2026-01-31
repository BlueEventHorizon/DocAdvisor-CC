# specs_toc.yaml Format Definition

## Purpose

`.claude/doc-advisor/specs/specs_toc.yaml` is the **single source of truth** for the **specs-advisor Subagent** to identify requirement and design documents needed for tasks.

The quality of this file determines task execution success. **Missing information is not acceptable.**

**This file serves as the Single Source of Truth for format definition and intermediate file schema.**

---

## Key Principles [MANDATORY]

- Include all requirement and design documents without omission
- Support task matching through keywords
- When in doubt, include it (never miss documents)
- **Key format**: With `specs/` prefix (e.g., `specs/main/requirements/app_overview.md`)

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
specs/{feature}/requirements/**/*.md
specs/{feature}/design/**/*.md
```

**Exclusions**:
- `.claude/doc-advisor/specs/specs_toc.yaml` (self)
- `.claude/doc-advisor/specs/.toc_work/` (work directory)
- `specs/**/reference/` (reference materials)

---

## Change Detection Method [Single Source of Truth]

In incremental mode, file content hashes are recorded for change detection.

### Checksum File

```yaml
# .claude/doc-advisor/specs/.toc_checksums.yaml (Git tracked)
checksums:
  specs/main/requirements/app_overview.md: a1b2c3d4e5f6...
  specs/main/design/list_screen_design.md: b2c3d4e5f6a1...
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
.claude/doc-advisor/specs/.toc_work/        # Work directory (.gitignore target)
├── specs_main_requirements_app_overview.yaml
├── specs_main_design_list_screen_design.yaml
└── ... (for each target file)
```

### Filename Generation Rule

Generate YAML filename from document path (including `specs/` prefix):

```
specs/main/requirements/app_overview.md → specs_main_requirements_app_overview.yaml
specs/main/design/list_screen_design.md → specs_main_design_list_screen_design.yaml
specs/feature/requirements/screens/login.md → specs_feature_requirements_screens_login.yaml
```

Conversion rule: `/` → `_`, `.md` → `.yaml`

### Entry YAML Structure

```yaml
# .claude/doc-advisor/specs/.toc_work/specs_main_requirements_app_overview.yaml

_meta:
  source_file: specs/main/requirements/app_overview.md  # Path from project root
  doc_type: requirement                             # requirement | design
  status: pending                                  # pending | completed
  updated_at: null                                 # Completion time (ISO 8601)

# Below: specs_toc.yaml entry format (key uses source_file value)
title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
```

### _meta Field Description

| Field | Type | Description |
|-------|------|-------------|
| `source_file` | string | Target document path (from project root, e.g., `specs/main/...`) |
| `doc_type` | enum | `requirement` (requirement) or `design` (design document) |
| `status` | enum | `pending` (unprocessed) or `completed` (done) |
| `updated_at` | datetime/null | Completion time (ISO 8601), `null` if incomplete |

### doc_type Determination Rule

Determine doc_type from path:

| Path Pattern | doc_type |
|--------------|----------|
| `specs/{feature}/requirements/**/*.md` | requirement |
| `specs/{feature}/design/**/*.md` | design |

---

## YAML Schema Definition (Final Output)

### Top-level Structure

```yaml
metadata:
  name: string              # Index name (fixed: "Requirement & Design Document Search Index")
  generated_at: datetime    # Generation time (ISO 8601 format)
  file_count: integer       # Total target file count

docs: object                # Document entries (key: file path)
```

---

### docs (Document Entries)

```yaml
docs:
  <file_path>:                   # Path from project root (e.g., "specs/main/requirements/app_overview.md")
    doc_type: string             # Document type ("requirement" | "design")
    title: string                # Title (extracted from H1)
    purpose: string              # Purpose (1-2 lines, what it defines)
    content_details: array[string] # Content details (5+ items, main requirements/design content)
    applicable_tasks: array[string] # Applicable tasks (task types that need this file)
    keywords: array[string]       # Keywords (matching terms for task descriptions, 5-10 words)
```

**Example**:
```yaml
docs:
  specs/main/requirements/app_overview.md:
    doc_type: requirement
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

  specs/main/design/list_screen_design.md:
    doc_type: design
    title: List Screen Design
    purpose: Defines UI design, state management, and data flow for the list screen
    content_details:
      - Screen layout
      - ViewModel design
      - State management pattern
      - Data fetching flow
      - Error handling
    applicable_tasks:
      - List screen implementation
      - UI layer design review
      - ViewModel implementation
    keywords:
      - list screen
      - ViewModel
      - SwiftUI
      - state management
      - AsyncStream
```

---

## Field Guidelines

### purpose

- Describe the file's role concisely in 1-2 sentences
- Use phrases like "Defines requirements for...", "Specifies design for..."

### content_details

- List **specific requirements/design content** in the file
- Detailed enough for subagent to understand overview without reading the file
- Must include important requirements/constraints
- 5-10 items

### applicable_tasks

- List **specific task types** that need this file
- Avoid vague expressions, use specific task names
- Include actions like "implementation", "creation", "modification"

### keywords

- **Matching terms** for task descriptions
- Include technical terms, concept names, feature names
- 5-10 words

---

## Complete Example

```yaml
# .claude/doc-advisor/specs/specs_toc.yaml

metadata:
  name: Requirement & Design Document Search Index
  generated_at: 2026-01-11T12:00:00Z
  file_count: 25

docs:
  specs/main/requirements/app_overview.md:
    doc_type: requirement
    title: Application Overview Specification
    purpose: Defines overall requirements and feature scope for the application
    content_details:
      - Application overview
      - Main feature list
      - Use case definitions
      - Screen navigation overview
    applicable_tasks:
      - New feature implementation planning
      - Feature scope confirmation
    keywords:
      - application
      - requirements
      - feature list

  specs/main/requirements/screens/login_screen.md:
    doc_type: requirement
    title: Login Screen Requirements
    purpose: Defines functional requirements, input validation, and error handling for the login screen
    content_details:
      - Login form specification
      - Input validation rules
      - Error message specification
      - Authentication flow
    applicable_tasks:
      - Login screen implementation
      - Authentication feature implementation
    keywords:
      - login
      - authentication
      - validation
      - screen

  specs/main/design/login_screen_design.md:
    doc_type: design
    title: Login Screen Design
    purpose: Defines UI design, ViewModel, and state management for the login screen
    content_details:
      - Screen layout
      - ViewModel design
      - State transitions
      - Authentication service integration
    applicable_tasks:
      - Login screen implementation
      - UI layer design review
    keywords:
      - login
      - ViewModel
      - SwiftUI
      - authentication
```
