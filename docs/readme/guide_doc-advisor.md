# doc-advisor Detailed Guide

AI-searchable document index (ToC) generator and search tool for Claude Code. Extracts AI metadata from documents to enable task-relevant discovery.

doc-advisor is a generic ToC Provider that manages document sets per `key` (an arbitrary string). It does not interpret the meaning of a `key` (rules / specs classification); it operates deterministically on the given `key` and project-root-relative `paths`. Deciding which files to index is the job of an upper layer such as forge, or the `--all` single mode (reserved key `all`).

## Skill Details

### index-docs

```
/doc-advisor:index-docs --key <key> --paths-json '["docs/a.md", "docs/b.md"]'
/doc-advisor:index-docs --key <key> --paths-file paths.json
/doc-advisor:index-docs --all
```

| Argument               | Description                                                                                               |
| ---------------------- | --------------------------------------------------------------------------------------------------------- |
| `--key <key>`          | Opaque key of the target ToC (decided by the upper layer). `all` is reserved and cannot be set freely     |
| `--paths-json '[...]'` | JSON array of project-root-relative paths that form the **complete desired state** for the key            |
| `--paths-file <path>`  | JSON file containing the paths array (alternative to `--paths-json`)                                      |
| `--all`                | Single mode. Same as omitting `--key`; resolves to reserved key `all` and targets all Markdown under root |

Generates / updates the ToC for the key as a desired state. Any path present in the previous ToC but absent from the new paths is deleted (passing a partial array drops the rest). Internally it runs the cooperative pipeline `prepare_toc.py` (diff detection) → `doc-advisor:toc-updater` custom Agent (parallel metadata fill) → `merge_toc.py` (merge).

### query-docs

```
/doc-advisor:query-docs [--key <key>] task description
```

| Argument           | Description                                                               |
| ------------------ | ------------------------------------------------------------------------- |
| `--key <key>`      | Key of the ToC to search. When omitted, searches the reserved key `all`   |
| `task description` | Keywords or a natural-language task description to find relevant docs for |

Searches the ToC (keyword / metadata index) to identify documents relevant to a task. `query-docs` runs as an inherited-context dispatcher that builds a normalized search request, and delegates the actual search to a read-only custom agent (`doc-advisor:query-worker`). The worker reads every ToC entry, decides which document paths are relevant, and returns only the matching paths — the calling agent decides how to read them.

## Requirements

- [Claude Code](https://claude.ai/code) CLI
- Python 3.9 or later (standard library only; no extra packages required)
