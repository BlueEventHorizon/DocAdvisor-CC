# doc-advisor Detailed Guide

AI-searchable document index (ToC) generator for Claude Code. Extracts AI metadata from documents to enable task-relevant discovery of rules and specs.

## Skill Details

### setup-doc-structure

```
/doc-advisor:setup-doc-structure [--update]
```

| Argument   | Description                                                                   |
| ---------- | ----------------------------------------------------------------------------- |
| (none)     | Scan the project and interactively generate / overwrite `.doc_structure.yaml` |
| `--update` | Add only directories not yet listed in the existing `root_dirs`               |

Discover document directories under the project, classify them as rules / specs, and write `.doc_structure.yaml` to the project root after user confirmation. Required as a prerequisite before running the other skills.

### query-rules

```
/doc-advisor:query-rules task description
```

| Argument           | Description                                                 |
| ------------------ | ----------------------------------------------------------- |
| `task description` | Description of the task to find relevant rule documents for |

Search the ToC (keyword / metadata index) to identify rule documents (coding standards, architecture rules, workflow guides) relevant to a task. Returns a list of matching paths only — the calling agent decides how to read them.

### query-specs

```
/doc-advisor:query-specs task description
```

| Argument           | Description                                                 |
| ------------------ | ----------------------------------------------------------- |
| `task description` | Description of the task to find relevant spec documents for |

Search the ToC to identify specification documents (requirements, design docs) relevant to a task. Returns a list of matching paths only.

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

- `.doc_structure.yaml` in project root (generate with `/doc-advisor:setup-doc-structure` or write it by hand) — see [Document Structure Guide](guide_doc_structure.md)
