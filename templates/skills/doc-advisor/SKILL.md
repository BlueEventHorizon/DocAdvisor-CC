---
name: doc-advisor
description: ToC auto-generation toolkit for rules_toc.yaml and specs_toc.yaml. Provides scripts for pending YAML generation, merge processing, validation, and checksum management.
allowed-tools: Bash, Read
user-invocable: true
---

# doc-advisor

Provides all scripts needed for the ToC (Table of Contents) auto-generation system, including pending YAML generation, merge processing, validation, and checksum management for both rules and specs.

## Overview

This skill consolidates all ToC-related functionality:

- **rules_toc.yaml** - Development document search index
- **specs_toc.yaml** - Requirement & design document search index

## Script List

| Script | Purpose |
|--------|---------|
| `toc_utils.py` | Common utility functions |
| `create_checksums.py` | Checksum file generation |
| `create_pending_yaml_rules.py` | Phase 1: Generate pending YAML templates for rules |
| `create_pending_yaml_specs.py` | Phase 1: Generate pending YAML templates for specs |
| `merge_rules_toc.py` | Phase 3: Merge processing for rules |
| `merge_specs_toc.py` | Phase 3: Merge processing for specs |
| `validate_rules_toc.py` | Phase 3: Validation for rules |
| `validate_specs_toc.py` | Phase 3: Validation for specs |

## Commands

### Checksum Generation

```bash
# For rules
python3 .claude/skills/doc-advisor/scripts/create_checksums.py --target rules

# For specs
python3 .claude/skills/doc-advisor/scripts/create_checksums.py --target specs
```

### rules_toc.yaml Generation

#### Phase 1: Pending YAML Generation

```bash
# Full mode (all files)
python3 .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full

# Incremental mode (changed files only)
python3 .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py
```

#### Phase 3: Merge & Validation

```bash
# Full mode (new generation)
python3 .claude/skills/doc-advisor/scripts/merge_rules_toc.py --mode full --cleanup
python3 .claude/skills/doc-advisor/scripts/validate_rules_toc.py

# Incremental mode (differential merge)
python3 .claude/skills/doc-advisor/scripts/merge_rules_toc.py --mode incremental --cleanup
python3 .claude/skills/doc-advisor/scripts/validate_rules_toc.py

# Delete-only mode (deletions only, no .claude/doc-advisor/rules/.toc_work/ needed)
python3 .claude/skills/doc-advisor/scripts/merge_rules_toc.py --delete-only
python3 .claude/skills/doc-advisor/scripts/validate_rules_toc.py
```

### specs_toc.yaml Generation

#### Phase 1: Pending YAML Generation

```bash
# Full mode (all files)
python3 .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full

# Incremental mode (changed files only)
python3 .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py
```

#### Phase 3: Merge & Validation

```bash
# Full mode (new generation)
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --mode full --cleanup
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py

# Incremental mode (differential merge)
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --mode incremental --cleanup
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py

# Delete-only mode (deletions only, no .claude/doc-advisor/specs/.toc_work/ needed)
python3 .claude/skills/doc-advisor/scripts/merge_specs_toc.py --delete-only
python3 .claude/skills/doc-advisor/scripts/validate_specs_toc.py
```

## Options

| Option | Description |
|--------|-------------|
| `--full` | Process all files (for pending YAML generation) |
| `--mode full` | Generate all entries from scratch (default) |
| `--mode incremental` | Differential merge into existing ToC file |
| `--delete-only` | Execute deletions only (no `.claude/doc-advisor/<target>/.toc_work/` needed) |
| `--cleanup` | Delete `.claude/doc-advisor/<target>/.toc_work/` directory after successful merge |
| `--target rules/specs` | Specify target for checksum generation |

## Script Behavior

### Checksum Generation

1. Load configuration based on specified `--target` (rules/specs)
2. Search all `.md` files under target directory (applying exclude patterns)
3. Calculate SHA-256 hash for each file
4. Generate checksum file with relative path as key

### Full Mode (Default)

1. Read `.claude/doc-advisor/<target>/.toc_work/*.yaml`
2. Remove `_meta` section from each file
3. Extract only entries with `status: completed`
4. Merge using `source_file` as key
5. Generate ToC YAML file

### Incremental Mode

1. Read existing ToC file
2. Detect deleted files via checksum comparison and remove corresponding entries
3. Overwrite/add entries from `.claude/doc-advisor/<target>/.toc_work/*.yaml`
4. Write updated ToC file

### Delete-only Mode

1. Read existing ToC file
2. Detect deleted files via checksum comparison
3. Remove corresponding entries
4. Write updated ToC file

※ `.claude/doc-advisor/<target>/.toc_work/` directory is not required

## Output Files

### Checksum Files

- `.claude/doc-advisor/rules/.toc_checksums.yaml`
- `.claude/doc-advisor/specs/.toc_checksums.yaml`

```yaml
# Checksum file for *_toc.yaml
# Auto-generated - DO NOT EDIT MANUALLY
generated_at: 2026-01-16T12:00:00Z
file_count: 30
checksums:
  rules/core/architecture_rule.md: a1b2c3d4e5f6...
  ...
```

## Prerequisites

- Python 3 must be available (uses standard library only)
- `.claude/doc-advisor/config.yaml` should exist (defaults are used if missing)
- **Full/Incremental Mode**: YAML files with completed status must exist in `.claude/doc-advisor/<target>/.toc_work/`
- **Delete-only Mode**: `.claude/doc-advisor/<target>/.toc_checksums.yaml` must exist
