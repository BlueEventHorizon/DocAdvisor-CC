# Document Structure Guide

`.doc_structure.yaml` is a project-level configuration file that declares where documents live and what types they are. `doc-advisor` skills (`query-rules` / `query-specs` / `create-rules-toc` / `create-specs-toc`) read this file.

## Feature

When you split specifications into **Feature units** under `docs/specs/{feature}/...`, give each Feature the same directory structure:

```
docs/
  specs/
    {feature}/
      requirements/   # Requirements documents
      design/         # Design documents
      plan/           # Implementation plan
```

Feature splitting is optional. A small project can treat the whole repository as a single Feature.

## .doc_structure.yaml

### Purpose

A file that declares where documents live and what types they are. `doc-advisor` reads it to discover files to scan and to assign each file a `doc_type`.

Place it at the project root (same level as `.git/`).

### Schema Overview

Two top-level categories: `rules` and `specs`.

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
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirements/": requirement
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

> **YAML note**: When a `doc_types_map` key contains `*` or `**`, **quote it** as `"..."`. Quoting glob entries in `root_dirs` is also safer.

### Configuration Examples

#### Simple (No Features)

```yaml
specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
    - docs/specs/requirements/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
    docs/specs/requirements/: requirement
```

#### Feature-Based

```yaml
specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirements/": requirement
```

No `.doc_structure.yaml` changes are needed when you add a Feature. Just create the `docs/specs/payment/design/` directory and it is detected automatically.

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

Both `docs/specs/auth/design/` and `docs/specs/auth/social-login/design/` are detected automatically.

## /doc-advisor:setup-doc-structure

```
/doc-advisor:setup-doc-structure [--update]
```

### What it does

- Scans the project and **interactively** generates or updates `.doc_structure.yaml`
- Discovers existing directories and classifies them as rules / specs
- Writes `.doc_structure.yaml` after user confirmation

With `--update`, it only adds directories not yet listed in `root_dirs` of the existing `.doc_structure.yaml`.

### When to run

- First time using `doc-advisor` in a project
- After major changes to the directory structure
- After manually adding a new Feature

### Writing it by hand

You can also create `.doc_structure.yaml` manually at the project root using the schema and examples above.
