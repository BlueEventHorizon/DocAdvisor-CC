---
name: classify-docs
description: |
  Auto-detect and classify project document directories as rules or specs.
  Updates config.yaml root_dirs based on classification results.
  Trigger:
  - After initial setup to configure document directories
  - "Classify my documents"
  - "What directories should be rules vs specs?"
allowed-tools: Bash, Read, Edit
user-invocable: true
argument-hint: "[--update]"
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

# classify-docs

Auto-detect and classify project document directories for Doc Advisor.

## Usage

```
/classify-docs [--update]
```

| Argument | Description |
|----------|-------------|
| (none) | Full classification of all markdown directories |
| `--update` | Only process directories not already in config.yaml root_dirs |

## Prerequisite

config.yaml must exist. If not, run `setup.sh` first.

## Execution Flow

### Step 1: Run classification script

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/classify_dirs.py [--update]
```

Capture the YAML output.

### Step 2: Present results to user

Display the classification results in a clear format:

```
📁 Document Directory Classification

Rules (development rules, guidelines, standards):
  ✅ rules/           [high confidence] frontmatter doc_type=rule
  ✅ guidelines/      [medium confidence] term_ranking: rule_score=15, spec_score=2

Specs (requirements, designs, plans):
  ✅ specs/            [high confidence] frontmatter doc_type=requirement
  ✅ design/          [medium confidence] dirname match

Skipped:
  ⏭️  docs/            README/CHANGELOG only

No classification:
  ❓ shared/          unclassifiable (3 md files)
```

### Step 3: Ask user for confirmation

Ask the user:
- Are the classifications correct?
- For unclassified directories: should they be rules, specs, or skipped?
- Any overrides needed?

### Step 4: Update config.yaml

After user confirmation, run the set_root_dirs script with the confirmed directories:

```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/set_root_dirs.py --rules "dir1,dir2" --specs "dir3,dir4"
```

Example:
```bash
{{PYTHON_PATH}} .claude/doc-advisor/scripts/set_root_dirs.py --rules "rules,guidelines" --specs "specs,design"
```

This updates `root_dirs` in `.claude/doc-advisor/config.yaml` for both rules and specs sections.

### Step 5: Summary

```
✅ config.yaml updated

Rules directories:
  - rules/
  - guidelines/

Specs directories:
  - specs/
  - design/

Next steps:
  - /create-rules-toc --full  (generate rules search index)
  - /create-specs-toc --full  (generate specs search index)
```

## Error Handling

- If config.yaml doesn't exist, tell user to run setup.sh first
- If no markdown directories found, report that the project has no documents to classify
- If classification script fails, report the error and ask user to proceed manually
