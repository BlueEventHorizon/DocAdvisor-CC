# bw-cc-plugins

Claude Code plugins for **Spec-Driven Development** — write specs first, then let AI implement and review with full context.

**Marketplace version: 0.1.25**

The marketplace ships **4 plugins** (forge, anvil, doc-advisor, **doc-db**). **doc-db** complements rule/spec discovery with heading-level Hybrid search (Embedding + Lexical) and LLM Rerank. It is **not a superset of doc-advisor**; the two are designed to be used together, sharing the same `.doc_structure.yaml`.

[Japanese README (README.md)](README.md)

## What is Spec-Driven Development?

Spec-Driven Development is a workflow where every code change traces back to a written specification. **forge** guides you through five stages — requirements, design, plan, implement, and review — so that AI always works from explicit, reviewable intent rather than ad-hoc instructions. Each stage produces a document; each document feeds the next stage. The result is traceable, auditable delivery: you can always answer _why_ a piece of code exists.

## The Role of doc-advisor

Large projects accumulate rules, standards, and design documents that AI cannot use if it cannot find them. **doc-advisor** indexes these documents (via ToC keyword search and OpenAI Embedding semantic search) and automatically supplies the relevant ones to forge at the moments that matter:

- **During implementation** — project-specific coding rules and related specs are collected before a single line is written.
- **During review** — applicable rules are added as review perspectives, so reviews check against your actual standards, not generic best practices.

This eliminates context gaps: AI implements and reviews with the same knowledge a senior team member would have.

## Workflow

```mermaid
flowchart LR
    subgraph forge
        R([Requirements]) --> D([Design]) --> P([Plan]) --> I([Implement]) --> RF([Review / Fix])
    end
    RF --> DL([Delivery])
    DA[doc-advisor] -. find context .-> forge
    DB[doc-db] -. chunk Hybrid search .-> forge
    AV[anvil] -- commit & PR --> DL
```

## Plugins

| Plugin          | Version | Description                                                                                                                                                                                  |
| --------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **forge**       | 0.1.1   | AI-powered document lifecycle tool. Create, review, and auto-fix requirements/design/plan docs and code.                                                                                     |
| **anvil**       | 0.0.8   | GitHub operations toolkit. Create PRs, manage issues, and automate GitHub workflows.                                                                                                         |
| **doc-advisor** | 0.3.0   | AI-searchable document index with dual search — keyword (ToC) and semantic (OpenAI Embedding). Auto-discovers relevant rules and specs for any task.                                         |
| **doc-db**      | 0.0.2   | Heading-chunk Hybrid search (Embedding + Lexical) with LLM Rerank. Grep results for IDs / proper nouns are merged in to reduce misses (used together with and complementary to doc-advisor). |

## Skills

### forge

> For Feature management and document structure details, see the [Document Structure Guide](docs/readme/guide_doc_structure.md).

#### Pipeline

```mermaid
flowchart LR
    REQ["start-requirements<br/>(what to build)"]
    UXUI["start-uxui-design<br/>(how it looks)"]
    DES["start-design<br/>(how to build)"]
    PLAN["start-plan<br/>(when)"]
    IMPL["start-implement<br/>(build)"]

    REQ --> UXUI -.->|optional| DES --> PLAN --> IMPL

    REV["review<br/>(available at every stage)"]
    REQ & DES & PLAN & IMPL -.->|anytime| REV
```

| Stage          | Skill              | Input                        | Output                       |
| -------------- | ------------------ | ---------------------------- | ---------------------------- |
| Requirements   | start-requirements | Dialog / source code / Figma | Requirements docs (Markdown) |
| UXUI Design    | start-uxui-design  | ASCII art from requirements  | Design tokens + UI specs     |
| Design         | start-design       | Requirements docs            | Design docs (Markdown)       |
| Plan           | start-plan         | Design docs                  | Plan (YAML)                  |
| Implementation | start-implement    | Plan                         | Code + progress updates      |
| Review         | review             | Code / documents             | Findings + fixes             |

#### Getting Started

```bash
# 1. Project setup (first time only)
/forge:setup-doc-structure

# 2. Requirements through implementation
/forge:start-requirements my-feature --mode interactive --new
/forge:start-design my-feature
/forge:start-plan my-feature
/forge:start-implement my-feature

# 3. Review (anytime)
/forge:review code src/ --auto
```

#### Skills

| Skill                                                                                  | Description                                                                                                                      | Trigger                        |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| [**review**](docs/readme/forge/guide_review.md)                                        | Review code & docs with 🔴🟡🟢 severity. Auto-fix with `--auto N`                                                                | `"review"`                     |
| [**start-requirements**](docs/readme/forge/guide_create_docs.md#start-requirements)    | Create requirements via dialog, reverse-engineering, or Figma                                                                    | `"requirements"`               |
| [**start-design**](docs/readme/forge/guide_create_docs.md#start-design)                | Create design docs from requirements. Prioritizes asset reuse                                                                    | `"start design"`               |
| [**start-plan**](docs/readme/forge/guide_create_docs.md#start-plan)                    | Extract tasks from design docs into a YAML plan                                                                                  | `"start plan"`                 |
| [**start-implement**](docs/readme/forge/guide_implement.md)                            | Select tasks from plan, implement, review, and update                                                                            | `"start implement"`            |
| [**start-uxui-design**](docs/readme/forge/guide_uxui_design.md)                        | Create design tokens & UI specs with UX evaluation                                                                               | `"UXUI design"`                |
| **merge-specs**                                                                        | Merge two spec DIRs (base / additional) at content granularity. Additional is canonical; base is revised; pure-new parts migrate | `"merge spec"`                 |
| [**setup-doc-structure**](docs/readme/guide_doc_structure.md#forgesetup-doc-structure) | Generate `.doc_structure.yaml` + scaffold directories                                                                            | `"setup"`                      |
| [**setup-version-config**](docs/readme/forge/guide_setup.md#setup-version-config)      | Generate/update `.version-config.yaml`                                                                                           | `"version config"`             |
| [**update-version**](docs/readme/forge/guide_setup.md#update-version)                  | Bump version across files. patch/minor/major/direct                                                                              | `"version bump"`               |
| [**clean-rules**](docs/readme/forge/guide_setup.md#clean-rules)                        | Analyze and reorganize rules/ based on taxonomy                                                                                  | `"clean rules"`                |
| [**help**](docs/readme/forge/guide_setup.md#help)                                      | Interactive help wizard                                                                                                          | `"help"`                       |
| [_reviewer_](docs/readme/forge/guide_review.md#execution-flow)                         | Evaluate P1/P2/P3 in check order from criteria (single-launch principle)                                                         | ※ Called by review             |
| [_evaluator_](docs/readme/forge/guide_review.md#execution-flow)                        | Scrutinize review findings and determine fix/skip/confirm                                                                        | ※ Called by review             |
| [_fixer_](docs/readme/forge/guide_review.md#execution-flow)                            | Fix issues based on review findings                                                                                              | ※ Called by review             |
| [_present-findings_](docs/readme/forge/guide_review.md#execution-flow)                 | Present review findings interactively, one item at a time                                                                        | ※ Called by review             |
| [_doc-structure_](docs/readme/guide_doc_structure.md)                                  | Parse and resolve paths from `.doc_structure.yaml`                                                                               | ※ Called by orchestrators      |
| [_next-spec-id_](docs/readme/forge/guide_create_docs.md)                               | Scan all branches for spec IDs and return the next available number                                                              | ※ Called by start-requirements |

### anvil

> [Detailed Guide](docs/readme/guide_anvil.md) — Usage and examples

| Skill                                                 | Description                                                                                         | Trigger             |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------- |
| [**commit**](docs/readme/guide_anvil.md#commit)       | Generate commit message from changes, commit & push                                                 | `"commit"`          |
| [**create-pr**](docs/readme/guide_anvil.md#create-pr) | Create a GitHub draft PR with auto-generated title/body                                             | `"create-pr"`       |
| **create-issue**                                      | Organize problem, background, and root cause into a GitHub Issue (resolution handled by impl-issue) | `"create issue"`    |
| **impl-issue**                                        | Run end-to-end from a GitHub Issue: plan, branch, implement, PR (UI Issue supported)                | `"implement issue"` |

### doc-advisor

> [Detailed Guide](docs/readme/guide_doc-advisor.md) — Usage and examples

| Skill                                                                     | Description                                                        | Trigger               |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------ | --------------------- |
| [**query-rules**](docs/readme/guide_doc-advisor.md#query-rules)           | Search rules with ToC (keyword), Index (semantic), or hybrid mode  | `"query rules"`       |
| [**query-specs**](docs/readme/guide_doc-advisor.md#query-specs)           | Search specs with ToC (keyword), Index (semantic), or hybrid mode  | `"query specs"`       |
| [**create-rules-toc**](docs/readme/guide_doc-advisor.md#create-rules-toc) | Update the rules search index (ToC) after modifying rule documents | `"rebuild rules ToC"` |
| [**create-specs-toc**](docs/readme/guide_doc-advisor.md#create-specs-toc) | Update the specs search index (ToC) after modifying spec documents | `"rebuild specs ToC"` |

### doc-db

> Detailed Guide: [Japanese](docs/readme/guide_doc-db_ja.md) (en TBD) — Usage, examples, and how it complements doc-advisor

| Skill                                                         | Description                                                             | Trigger           |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- | ----------------- |
| [**build-index**](docs/readme/guide_doc-db_ja.md#build-index) | Build/update the heading-chunk Index (rules / specs, `--full`, etc.)    | `"build doc-db"`  |
| [**query**](docs/readme/guide_doc-db_ja.md#query)             | Hybrid / Rerank search. Optionally augments results with full-text grep | `"search doc-db"` |

> **Bold** = user-invocable, _Italic_ = AI-only (called internally by other skills)

## Installation

### Option A: Marketplace (persistent)

Inside a Claude Code session:

```
/plugin marketplace add BlueEventHorizon/bw-cc-plugins
/plugin install forge@bw-cc-plugins
/plugin install anvil@bw-cc-plugins
/plugin install doc-advisor@bw-cc-plugins
/plugin install doc-db@bw-cc-plugins
```

To re-enable a disabled plugin, from your terminal:

```bash
claude plugin enable forge@bw-cc-plugins
```

`marketplace add` registers the GitHub repo as a plugin source (once per user). Once installed, the plugin is always available.

### Option B: Local directory (per session)

```bash
git clone https://github.com/BlueEventHorizon/bw-cc-plugins.git
claude --plugin-dir ./bw-cc-plugins/plugins/forge
```

> **Note**: `--plugin-dir` is session-only. You must specify it every time you start Claude Code. To unload, simply start without the flag.

### Update

From your terminal:

```bash
claude plugin update forge@bw-cc-plugins --scope local
```

## Document Structure (.doc_structure.yaml)

`.doc_structure.yaml` declares where documents live and what types they are. Both forge and doc-advisor reference this file. Generate it with `/forge:setup-doc-structure`.
→ [Document Structure Guide](docs/readme/guide_doc_structure.md) | [Schema reference](plugins/forge/docs/doc_structure_format.md)

## Git Information Cache (.git_information.yaml)

On first run, `/anvil:create-pr` detects your GitHub repo from `git remote` and offers to save the settings to `.git_information.yaml` for future use.

## Requirements

- [Claude Code](https://claude.ai/code) CLI
- Python 3 (for setup scan)
- [Codex CLI](https://github.com/openai/codex) (optional, for Codex engine; falls back to Claude if unavailable)
- OpenAI API key (for doc-advisor embedding features; `OPENAI_API_DOCDB_KEY` recommended, falls back to `OPENAI_API_KEY` if unset; per DES-007 unified spec)
- OpenAI API key (for doc-db index build / search / rerank; `OPENAI_API_DOCDB_KEY` recommended, falls back to `OPENAI_API_KEY` if unset; per DES-007 unified spec)
- [gh CLI](https://cli.github.com/) (for anvil, authenticated)

## License

[MIT](LICENSE)
