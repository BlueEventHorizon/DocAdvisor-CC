# doc-advisor Detailed Guide

AI-searchable document index (ToC) generator for Claude Code. Extracts AI metadata from documents to enable task-relevant discovery of rules and specs.

## Skill Details

### query-rules

```
/doc-advisor:query-rules [--toc|--index] task description
```

| Argument           | Description                                                 |
| ------------------ | ----------------------------------------------------------- |
| `--toc`            | Force ToC (keyword) search only                             |
| `--index`          | Force Embedding (semantic) search only                      |
| (none)             | Hybrid auto-select (default)                                |
| `task description` | Description of the task to find relevant rule documents for |

Search document indexes to identify rule documents (coding standards, architecture rules, workflow guides) relevant to a task. Default hybrid mode combines ToC keyword search and Embedding semantic search, returning the union of both results.

### query-specs

```
/doc-advisor:query-specs [--toc|--index] task description
```

| Argument           | Description                                                 |
| ------------------ | ----------------------------------------------------------- |
| `--toc`            | Force ToC (keyword) search only                             |
| `--index`          | Force Embedding (semantic) search only                      |
| (none)             | Hybrid auto-select (default)                                |
| `task description` | Description of the task to find relevant spec documents for |

Search document indexes to identify specification documents (requirements, design docs) relevant to a task. Default hybrid mode combines ToC keyword search and Embedding semantic search.

### create-rules-toc

```
/doc-advisor:create-rules-toc [--full]
```

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| (none)   | Incremental update (hash-based) or resume processing  |
| `--full` | Full file scan (for initial creation or regeneration) |

Update the rules search index (ToC) after modifying, creating, or deleting rule documents.

### create-specs-toc

```
/doc-advisor:create-specs-toc [--full]
```

| Argument | Description                                           |
| -------- | ----------------------------------------------------- |
| (none)   | Incremental update (hash-based) or resume processing  |
| `--full` | Full file scan (for initial creation or regeneration) |

Update the specs search index (ToC) after modifying, creating, or deleting spec documents.

## Requirements

- `.doc_structure.yaml` in project root (generate with `/forge:setup-doc-structure`) — see [Document Structure Guide](guide_doc_structure.md)
