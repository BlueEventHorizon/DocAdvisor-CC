---
name: sync-docs
description: |
  Synchronize external document sources defined in config.yaml.
  Adds git submodules and creates symlinks for external rules,
  requirements, and design documents.
  Trigger:
  - After editing external_sources in config.yaml
  - "Sync external document sources"
  - "Update external docs"
allowed-tools: Bash, Read
user-invocable: true
argument-hint: "[--force] [--status] [--cleanup]"
doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
---

# sync-docs

Synchronize external document sources to the doc-advisor document aggregation directory.

## Usage

```
/sync-docs                  # Sync all external sources
/sync-docs --status         # Show current sync status
/sync-docs --force          # Force re-sync even if already synced
/sync-docs --cleanup        # Remove orphaned sources not in config
```

| Argument | Description |
|----------|-------------|
| (none) | Sync new/updated external sources |
| `--force` | Force re-add even if source already exists |
| `--status` | Show status of all external sources |
| `--cleanup` | Remove orphaned sources not in config |

## Execution Flow

1. Read `.claude/doc-advisor/config.yaml` to check for `external_sources` section
2. Run the sync script:
   ```bash
   {{PYTHON_PATH}} .claude/doc-advisor/scripts/sync_external_sources.py $0
   ```
3. Report results to user
4. If git submodules were added/modified, remind user to commit changes:
   ```bash
   git add .gitmodules .claude/doc-advisor/
   git commit -m "Add external document sources"
   ```

## After Sync

After syncing external sources, regenerate ToC files to index new documents:

```
/create-rules-toc --full
/create-specs-toc --full
```

## Error Handling

If sync fails for a specific source, the script continues with remaining sources.
Report all errors at the end and suggest fixes (e.g., check URL, verify authentication with `gh auth status`).
