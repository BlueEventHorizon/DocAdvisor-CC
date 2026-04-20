# Doc Advisor

[![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Doc Advisor keeps your AI's context clean by indexing documents and delivering only what's needed.

## Why ToC (Table of Contents)?

Generative AI has structural limitations:

- **Lost in the Middle**: Information in the "middle" of long contexts gets overlooked
- **Attention Dilution**: The longer the input, the more attention spreads thin

**Solution**: Don't feed everything—pass only what's needed.

Doc Advisor pre-indexes your documents and provides only the relevant files for each task.

## Overview

Doc Advisor helps you manage project documentation by automatically indexing documents and enabling AI agents to quickly identify relevant files for any task.

### Key Features

- **Automatic ToC Generation**: Analyzes document content and generates searchable structured indexes
- **Incremental Updates**: Processes only changed files using SHA-256 hash-based change detection
- **Parallel Processing**: Up to 5 concurrent subagents for faster document processing
- **Interruption Recovery**: Preserves completed work and supports resumption
- **Project-Based Setup**: All files are copied to your project, no plugin mode required

## Document Model

Doc Advisor manages two categories of documents: **rule** and **spec**.

| Category | Directory | Purpose                   | Configurable |
| -------- | --------- | ------------------------- | ------------ |
| rule     | `rules/`  | Development documentation | Yes          |
| spec     | `specs/`  | Project specifications    | Yes          |

### rule - Development Documentation

Free-form structure. Any `.md` file in any subdirectory is indexed.

| Content Type       | Examples                            |
| ------------------ | ----------------------------------- |
| Architecture rules | `rules/core/architecture.md`        |
| Coding standards   | `rules/coding/naming_convention.md` |
| Workflow guides    | `rules/workflow/review_process.md`  |

### spec - Project Specifications

The doc_type is automatically determined if the subdirectory name appears anywhere in the path.

| doc_type      | Subdirectory    | Purpose                                             | Configurable |
| ------------- | --------------- | --------------------------------------------------- | ------------ |
| `requirement` | `requirements/` | Functional requirements, use cases                  | Yes          |
| `design`      | `design/`       | Technical design, architecture decisions            | Yes          |
| `plan`        | `plan/`         | Project plans (definition only, not indexed in ToC) | -            |

Examples:

- `specs/requirements/login.md` → requirement
- `specs/main/design/architecture.md` → design
- `specs/auth/oauth/requirements/api.md` → requirement

### How ToC Generation Works

#### Search Scope

The system recursively searches under `specs/` and targets files whose path contains a `requirement` or `design` directory. There is no depth limit.

| Path Example                         | Included | Reason                  |
| ------------------------------------ | -------- | ----------------------- |
| `specs/feature1/requirements/app.md` | ✅       | Contains `requirements` |
| `specs/main/sub/design/api.md`       | ✅       | Contains `design`       |
| `specs/feature1/plan/task.md`        | ❌       | Not included            |

#### Why plan is Excluded

The `plan` directory is excluded from ToC indexing:

1. **Read in full during work**: Plans are read entirely at execution time, so partial search indexing is unnecessary
2. **Pre-defined execution plans**: requirement/design are "what to build" references; plan is the "how to build" execution plan

#### Processing Time

| Process          | Executor           | Speed    |
| ---------------- | ------------------ | -------- |
| Recursive search | Python (`os.walk`) | Fast     |
| Change detection | Python (SHA-256)   | Fast     |
| Content analysis | Claude (LLM)       | **Slow** |
| Merge            | Python             | Fast     |

The bottleneck is LLM content analysis. Incremental mode (default) optimizes by processing only changed files.

#### Symlink Support (v3.2+)

All scripts follow symbolic links when scanning directories. This allows you to include external documentation by creating symlinks:

```bash
# Example: Include external docs via symlink
ln -s /path/to/external/docs rules/external
```

- Symlink loops are detected and prevented (inode tracking)
- Duplicate files via multiple symlinks are processed only once

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

### 2. Setup target project

Run `setup.sh` with your target project path:

```bash
cd DocAdvisor-CC
./setup.sh /path/to/your-project
```

This copies all necessary files to your project:

```
your-project/
├── .doc_structure.yaml              # Document structure configuration
└── .claude/
    ├── agents/            # Worker agents (toc-updater)
    ├── skills/
    │   ├── setup-doc-structure/
    │   │   └── SKILL.md   # document directory auto-classification skill
    │   ├── query-rules/
    │   │   └── SKILL.md   # rules document search skill
    │   ├── query-specs/
    │   │   └── SKILL.md   # specs document search skill
    │   ├── create-rules-toc/
    │   │   └── SKILL.md   # rules ToC generation skill
    │   └── create-specs-toc/
    │       └── SKILL.md   # specs ToC generation skill
    └── doc-advisor/       # All resources and runtime output
        ├── docs/
        ├── scripts/
        └── toc/           # ToC files
```

If `.doc_structure.yaml` is found in the target project, document directories are auto-configured.
Otherwise, run `/setup-doc-structure` in Claude Code after setup to configure directories.

To change the agent model after setup:

```bash
bash .claude/doc-advisor/scripts/change_agent_model.sh <haiku|sonnet|opus|inherit>
```

### 3. Launch Claude Code

```bash
cd /path/to/your-project
claude
```

No `--plugin-dir` flag needed! All files are already in your project.

### Using Makefile (Alternative)

```bash
cd DocAdvisor-CC
make setup                            # Interactive mode
make setup TARGET=/path/to/your-project  # Specify target
```

## Usage

### ToC Generation Commands

```bash
# Development documentation (rules/)
/create-rules-toc          # Incremental update (changed files only)
/create-rules-toc --full   # Full rebuild

# Requirements/design documents (specs/)
/create-specs-toc          # Incremental update
/create-specs-toc --full   # Full rebuild
```

### Document Search Skills

Automatically identify documents needed for a task:

```bash
/query-rules Identify documents for implementing user authentication
/query-specs Find requirements for screen navigation
```

### Recommended CLAUDE.md Entry

Add the following to your project's `CLAUDE.md` to make Claude automatically reference documents:

```markdown
## Task Execution Flow [MANDATORY]

When receiving a work task, follow this flow:

1. Identify rule documents
   /query-rules [task description]

2. Identify requirements/design documents
   /query-specs [task description]

3. Read **all** required documents

4. Execute the task
```

## Architecture

### Configuration File

The scripts use the following configuration file:

- `.doc_structure.yaml` (project root)

### ToC Generation Flow

```
/create-*-toc
        |
        v
+-------------------------------------+
| 1. Detect changes (SHA-256 hash)    |
|    Compare checksums -> changed only |
+------------------+------------------+
                   |
                   v
+-------------------------------------+
| 2. Parallel processing (max 5)      |
|    *-toc-updater agents             |
|    Each agent: read .md -> write YAML|
+------------------+------------------+
                   |
                   v
+-------------------------------------+
| 3. Merge & Validate -> *_toc.yaml   |
+-------------------------------------+
```

### Document Search Flow

```
/query-rules or /query-specs
        |
        v
+-------------------+     +-------------------+
| Read *_toc.yaml   |---->| Find relevant     |----> Return file paths
|                   |     | documents         |
+-------------------+     +-------------------+
```

## Directory Structure

### Template Repository

```
DocAdvisor/
├── templates/
│   ├── agents/                 # Worker agent templates
│   │   └── toc-updater.md
│   ├── skills/
│   │   ├── setup-doc-structure/
│   │   │   └── SKILL.md        # document directory auto-classification skill
│   │   ├── query-rules/
│   │   │   └── SKILL.md        # rules document search skill
│   │   ├── query-specs/
│   │   │   └── SKILL.md        # specs document search skill
│   │   ├── create-rules-toc/
│   │   │   └── SKILL.md        # rules ToC generation skill
│   │   └── create-specs-toc/
│   │       └── SKILL.md        # specs ToC generation skill
│   └── doc-advisor/            # ToC generation resources
│       ├── docs/               # Orchestrator, format, workflow docs
│       └── scripts/            # Python scripts
├── setup.sh                    # Project setup script
├── Makefile                    # Build automation
├── README.md                   # Japanese README
└── README_en.md                # English README
```

### Target Project Structure (after setup)

```
your-project/
├── .claude/
│   ├── agents/
│   │   └── toc-updater.md
│   ├── skills/
│   │   ├── setup-doc-structure/
│   │   │   └── SKILL.md        # document directory auto-classification skill
│   │   ├── query-rules/
│   │   │   └── SKILL.md        # rules document search skill
│   │   ├── query-specs/
│   │   │   └── SKILL.md        # specs document search skill
│   │   ├── create-rules-toc/
│   │   │   └── SKILL.md        # rules ToC generation skill
│   │   └── create-specs-toc/
│   │       └── SKILL.md        # specs ToC generation skill
│   └── doc-advisor/            # All resources and runtime output
│       ├── docs/               # Orchestrator, format, workflow docs
│       ├── scripts/            # Python scripts
│       └── toc/                # Runtime output
│           ├── rules/          # Generated artifacts for rules
│           │   ├── rules_toc.yaml
│           │   ├── .toc_checksums.yaml
│           │   └── .toc_work/
│           └── specs/          # Generated artifacts for specs
│               ├── specs_toc.yaml
│               ├── .toc_checksums.yaml
│               └── .toc_work/
├── .doc_structure.yaml         # Document structure configuration
├── rules/                      # Rules documentation (configurable)
│   └── *.md                    # Documentation files
└── specs/                      # Specs documentation (configurable)
    ├── requirements/           # Requirement documents
    └── design/                 # Design documents
```

## Configuration

### Project Configuration

Located at `.doc_structure.yaml` in the project root:

```yaml
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/requirements/: requirement
    specs/design/: design
    specs/plan/: plan
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

Doc Advisor internal settings (toc file paths, checksums paths, work dirs, parallelism) are managed as built-in code defaults and do not appear in this file.

> **Note**: System files (`.toc_work/`, `*_toc.yaml`, `.toc_checksums.yaml`) are automatically excluded.
> **Note**: Exclude patterns are matched against directory paths only (filenames are not matched).

### Customizing Configuration

Run `/setup-doc-structure` in Claude Code to auto-detect and update `.doc_structure.yaml`, or edit it directly:

```bash
nano /path/to/your-project/.doc_structure.yaml
```

## Processing Modes

| Mode         | Description                                         |
| ------------ | --------------------------------------------------- |
| full         | Scan all files and regenerate ToC                   |
| incremental  | Process only changed files (SHA-256 hash detection) |
| continuation | Resume interrupted processing                       |

## Requirements

- Python 3 (standard library only)
- Claude Code
- Bash shell

## Troubleshooting

### Config not found error

Ensure you've run setup for your project:

```bash
./setup.sh /path/to/your-project
```

### Skills not recognized

Verify the files exist:

```bash
ls -la /path/to/your-project/.claude/skills/create-rules-toc/SKILL.md
ls -la /path/to/your-project/.claude/skills/create-specs-toc/SKILL.md
ls -la /path/to/your-project/.claude/doc-advisor/
ls -la /path/to/your-project/.claude/agents/
```

### ToC generation fails

1. Check if target directories exist in your project
2. Verify config paths are correct
3. Look for `.claude/doc-advisor/toc/{rules,specs}/.toc_work/` for recovery

## Migration from v2.0 (Plugin Mode)

If you were using the plugin mode (`--plugin-dir`), run setup.sh to upgrade:

```bash
./setup.sh /path/to/your-project
```

### What happens during upgrade

**Automatically deleted** (doc-advisor legacy files):

- `.claude/commands/create-rules_toc.md`
- `.claude/commands/create-specs_toc.md`
- `.claude/skills/doc-advisor/` (removed, replaced with split skills)
- `.claude/doc-advisor/docs/` (recreated from templates)

**Installed** (v3.8+ structure):

- `.claude/agents/toc-updater.md` (unified worker agent)
- `.claude/skills/setup-doc-structure/SKILL.md` (document directory auto-classification)
- `.claude/skills/query-rules/SKILL.md` (rules document search)
- `.claude/skills/query-specs/SKILL.md` (specs document search)
- `.claude/skills/create-rules-toc/SKILL.md` (rules ToC generation)
- `.claude/skills/create-specs-toc/SKILL.md` (specs ToC generation)
- `.claude/doc-advisor/docs/`
- `.claude/doc-advisor/scripts/`
- `.claude/doc-advisor/toc/rules/` (ToC output)
- `.claude/doc-advisor/toc/specs/` (ToC output)

**Preserved** (user's custom files):

- `.claude/commands/your-custom-command.md` (any other commands)
- `.claude/agents/your-custom-agent.md` (any non-doc-advisor agents)

### After upgrade

1. Remove the `--plugin-dir` flag when starting Claude Code - all files are now in your project.
2. Regenerate ToC files (paths have changed):
   ```bash
   /create-rules-toc --full
   /create-specs-toc --full
   ```

## License

MIT License
