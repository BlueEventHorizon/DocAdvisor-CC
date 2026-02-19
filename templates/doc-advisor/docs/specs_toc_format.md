---
name: specs_toc_format
description: Format definition for specs_toc.yaml (Single Source of Truth)
applicable_when:
  - Creating or updating specs ToC entries
  - Validating specs_toc.yaml structure
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

# specs_toc.yaml Format Definition

## Purpose

`.claude/doc-advisor/toc/specs/specs_toc.yaml` is the **single source of truth** for the **specs-advisor Subagent** to identify requirement and design documents needed for tasks.

The quality of this file determines task execution success. **Missing information is not acceptable.**

**This file serves as the Single Source of Truth for format definition and intermediate file schema.**

---

## Key Principles [MANDATORY]

- Include all requirement and design documents without omission
- Support task matching through keywords
- When in doubt, include it (never miss documents)
- **Key format**: With `{{SPECS_DIR}}/` prefix (e.g., `{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md`)

### YAML Formatting Rules

- **Indentation**: 2 spaces (no tabs)
- **After colon**: Always one space (`key: value`)
- **Arrays**: Hyphen + space (`- item`)
- **No null**: All fields must be filled
- **No empty arrays**: `[]` is not allowed (minimum 1 item), except for `references`
- **No inline arrays**: Do not use `[a, b]` format. Always use list format
- **No multiline**: Do not use `|` or `>`. Write in single line

---

## Intermediate File Schema [Single Source of Truth]

Structure definition for work files used in individual entry file method.

### File Layout

```
.claude/doc-advisor/toc/specs/.toc_work/        # Work directory (.gitignore target)
├── {{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_app_overview.yaml
├── {{SPECS_DIR}}_main_{{DESIGN_DIR_NAME}}_list_screen_design.yaml
└── ... (for each target file)
```

### Filename Generation Rule

Generate YAML filename from document path (including `{{SPECS_DIR}}/` prefix):

```
{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md → {{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_app_overview.yaml
{{SPECS_DIR}}/main/{{DESIGN_DIR_NAME}}/list_screen_design.md → {{SPECS_DIR}}_main_{{DESIGN_DIR_NAME}}_list_screen_design.yaml
{{SPECS_DIR}}/feature/{{REQUIREMENT_DIR_NAME}}/screens/login.md → {{SPECS_DIR}}_feature_{{REQUIREMENT_DIR_NAME}}_screens_login.yaml
```

Conversion rule: `/` → `_`, `.md` → `.yaml`

### Entry YAML Structure

```yaml
# .claude/doc-advisor/toc/specs/.toc_work/{{SPECS_DIR}}_main_{{REQUIREMENT_DIR_NAME}}_app_overview.yaml

_meta:
  source_file: {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md  # Path from project root
  doc_type: requirement                             # requirement | design
  status: pending                                  # pending | completed
  updated_at: null                                 # Completion time (ISO 8601)

# Below: specs_toc.yaml entry format (key uses source_file value)
title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
references: []
```

### _meta Field Description

| Field | Type | Description |
|-------|------|-------------|
| `source_file` | string | Target document path (from project root, e.g., `{{SPECS_DIR}}/main/...`) |
| `doc_type` | enum | `requirement` (requirement) or `design` (design document) |
| `status` | enum | `pending` (unprocessed) or `completed` (done) |
| `updated_at` | datetime/null | Completion time (ISO 8601), `null` if incomplete |

### doc_type Determination Rule

Determine doc_type from path:

| Path Pattern | doc_type |
|--------------|----------|
| `{{SPECS_DIR}}/{feature}/{{REQUIREMENT_DIR_NAME}}/**/*.md` | requirement |
| `{{SPECS_DIR}}/{feature}/{{DESIGN_DIR_NAME}}/**/*.md` | design |

---

## YAML Schema Definition (Final Output)

### Top-level Structure

```yaml
metadata:
  name: string              # Index name (fixed: "Requirements and Design Document Search Index")
  generated_at: datetime    # Generation time (ISO 8601 format)
  file_count: integer       # Total target file count

docs: object                # Document entries (key: file path)
```

---

### docs (Document Entries)

```yaml
docs:
  <file_path>:                   # Path from project root (e.g., "{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md")
    doc_type: string             # Document type ("requirement" | "design")
    title: string                # Title (extracted from H1)
    purpose: string              # Purpose (1-2 lines, what it defines)
    content_details: array[string] # Content details (5+ items, main requirements/design content)
    applicable_tasks: array[string] # Applicable tasks (task types that need this file)
    keywords: array[string]       # Keywords (matching terms for task descriptions, 5-10 words)
    references: array[string]     # Referenced documents (direct references only, empty array allowed)
```

**Example**:
```yaml
docs:
  {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md:
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
    references: []

  {{SPECS_DIR}}/main/{{DESIGN_DIR_NAME}}/list_screen_design.md:
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
    references:
      - {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md
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

### references

- List documents **directly referenced** in this file
- Do NOT follow references (only record what this document mentions)
- Prefer concrete paths (e.g., `{{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/auth.md`)
- Abstract references are allowed if specific path is unknown (e.g., "authentication design document")
- Empty array `[]` is allowed if no references found
- Do NOT include self-reference

---

## Complete Example

```yaml
# .claude/doc-advisor/toc/specs/specs_toc.yaml

metadata:
  name: Requirements and Design Document Search Index
  generated_at: 2026-01-11T12:00:00Z
  file_count: 25

docs:
  {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/app_overview.md:
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
    references: []

  {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/screens/login_screen.md:
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
    references:
      - {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/auth/authentication.md
      - error handling design document

  {{SPECS_DIR}}/main/{{DESIGN_DIR_NAME}}/login_screen_design.md:
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
    references:
      - {{SPECS_DIR}}/main/{{REQUIREMENT_DIR_NAME}}/screens/login_screen.md
```
