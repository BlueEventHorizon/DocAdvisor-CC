# Document Structure Guide

`.doc_structure.yaml` is a project-level configuration file that declares where documents live and what types they are. It serves as the shared foundation for both forge and doc-advisor.

## Feature

forge can optionally manage documents per **Feature** — a grouped unit of related specifications for development. Features are not required; forge works without them.

| Development Pattern     | How Features are used                                                        |
| ----------------------- | ---------------------------------------------------------------------------- |
| Incremental development | Separate new capabilities from the existing main spec as individual Features |
| Agile development       | Develop and deliver per Feature in each iteration                            |
| Small projects          | Treat the entire project as a single Feature                                 |

When using Features, each one shares a common directory structure:

```
specs/
  {feature}/
    requirements/   # Requirements documents
    design/         # Design documents
    plan/           # Implementation plan
```

## .doc_structure.yaml

### Purpose

A file that declares where documents live and what types they are. The following tools share it:

- **forge** — Resolve review targets, detect Feature directories, locate document output paths
- **doc-advisor** — Determine ToC scan targets and doc_type classification

Place it at the project root (same level as `.git/`).

### Schema Overview

Organized into two categories: `rules` and `specs`.

```yaml
# .doc_structure.yaml
# doc_structure_version: 3.0

rules:
  root_dirs: # Directories to scan (glob supported)
    - docs/rules/
  doc_types_map: # Directory → doc_type mapping
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: [] # Directory names to exclude

specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirement/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

| Field                  | Description                                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| `root_dirs`            | Document directories. Supports `*` (one level) / `**` (any depth) glob patterns                             |
| `doc_types_map`        | Path → doc_type mapping. Recommended doc_types: `rule`, `requirement`, `design`, `plan`, `api`, `reference` |
| `patterns.target_glob` | File search pattern (default: `**/*.md`)                                                                    |
| `patterns.exclude`     | Directory names to exclude (matches at any depth in the path)                                               |

### Configuration Examples

#### Simple (No Features)

```yaml
specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
    - docs/specs/requirement/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
    docs/specs/requirement/: requirement
```

#### Feature-Based

```yaml
specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirement/": requirement
```

No `.doc_structure.yaml` changes needed when adding a Feature. Just create the `docs/specs/payment/design/` directory and it is detected automatically.

#### Nested Features (Sub-Features)

```yaml
specs:
  root_dirs:
    - "docs/specs/**/design/"
    - "docs/specs/**/plan/"
    - "docs/specs/**/requirements/"
  doc_types_map:
    "docs/specs/**/design/": design
    "docs/specs/**/plan/": plan
    "docs/specs/**/requirements/": requirement
```

Both `docs/specs/forge/design/` and `docs/specs/forge/review-PR/design/` are detected automatically.

## /forge:setup-doc-structure

```
/forge:setup-doc-structure
```

No arguments.

### What it does

- Scans the project and interactively generates or updates `.doc_structure.yaml`
- Auto-detects existing Feature directories and configures them as glob patterns
- Proposes a recommended structure (specs / rules / reference / adr) and creates missing directories with `.gitkeep`

### When to run

- First time using forge / doc-advisor in a project
- After major changes to the directory structure
- After manually adding a Feature

## Schema Reference

For the full format specification, see [doc_structure_format.md](../../plugins/forge/docs/doc_structure_format.md).
