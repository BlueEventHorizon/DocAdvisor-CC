# Doc Advisor (v3.0)

Doc Advisor keeps your AI's context clean by indexing documents and delivering only what's needed.

[![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

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

| Category | Directory | Purpose | Configurable |
|----------|-----------|---------|--------------|
| rule | `rules/` | Development documentation | Yes |
| spec | `specs/` | Project specifications | Yes |

### rule - Development Documentation

Free-form structure. Any `.md` file in any subdirectory is indexed.

| Content Type | Examples |
|--------------|----------|
| Architecture rules | `rules/core/architecture.md` |
| Coding standards | `rules/coding/naming_convention.md` |
| Workflow guides | `rules/workflow/review_process.md` |

### spec - Project Specifications

The doc_type is automatically determined if the subdirectory name appears anywhere in the path.

| doc_type | Subdirectory | Purpose | Configurable |
|----------|--------------|---------|--------------|
| `requirement` | `requirements/` | Functional requirements, use cases | Yes |
| `design` | `design/` | Technical design, architecture decisions | Yes |
| `plan` | `plan/` | Project plans (definition only, not indexed in ToC) | - |

Examples:
- `specs/requirements/login.md` → requirement
- `specs/main/design/architecture.md` → design
- `specs/auth/oauth/requirements/api.md` → requirement

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
your-project/.claude/
├── commands/          # Command files
├── agents/            # Agent definitions
├── skills/            # Skill modules
└── doc-advisor/
    └── config.yaml    # Project configuration
```

Setup will interactively ask for:
- Rules directory (default: `rules/`)
- Specs directory (default: `specs/`)

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
/create-rules_toc          # Incremental update (changed files only)
/create-rules_toc --full   # Full rebuild

# Requirements/design documents (specs/)
/create-specs_toc          # Incremental update
/create-specs_toc --full   # Full rebuild
```

### Advisor Agents

Automatically identify documents needed for a task:

```
Task(subagent_type: rules-advisor, prompt: "Identify documents for implementing user authentication")
Task(subagent_type: specs-advisor, prompt: "Find requirements for screen navigation")
```

## Architecture

### Configuration File

The scripts use the following configuration file:

- `.claude/doc-advisor/config.yaml`

### ToC Generation Flow

```
/create-*_toc
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

### Advisor Flow

```
Task(subagent_type: *-advisor)
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
DocAdvisor-CC/
├── templates/
│   ├── commands/               # Command templates
│   │   ├── create-rules_toc.md
│   │   └── create-specs_toc.md
│   ├── agents/                 # Agent templates
│   │   ├── rules-advisor.md
│   │   ├── specs-advisor.md
│   │   ├── rules-toc-updater.md
│   │   └── specs-toc-updater.md
│   ├── skills/                 # Skill templates
│   │   └── doc-advisor/        # ToC generation scripts
│   └── doc-advisor/
│       └── docs/               # ToC format/workflow documentation
├── setup.sh                    # Project setup script
├── Makefile                    # Build automation
└── README.md
```

### Target Project Structure (after setup)

```
your-project/
├── .claude/
│   ├── commands/
│   │   ├── create-rules_toc.md
│   │   └── create-specs_toc.md
│   ├── agents/
│   │   ├── rules-advisor.md
│   │   ├── specs-advisor.md
│   │   ├── rules-toc-updater.md
│   │   └── specs-toc-updater.md
│   ├── skills/
│   │   └── doc-advisor/        # ToC generation scripts
│   └── doc-advisor/
│       ├── config.yaml
│       ├── docs/               # ToC format/workflow documentation
│       ├── rules/              # Generated artifacts for rules
│       │   ├── rules_toc.yaml
│       │   ├── .toc_checksums.yaml
│       │   └── .toc_work/
│       └── specs/              # Generated artifacts for specs
│           ├── specs_toc.yaml
│           ├── .toc_checksums.yaml
│           └── .toc_work/
├── rules/                      # Rules documentation (configurable)
│   └── *.md                    # Documentation files
└── specs/                      # Specs documentation (configurable)
    ├── requirements/           # Requirement documents
    └── design/                 # Design documents
```

## Configuration

### Project Configuration

Located at `.claude/doc-advisor/config.yaml`:

```yaml
# === rules configuration ===
rules:
  root_dir: rules
  toc_file: .claude/doc-advisor/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/rules/.toc_work/

  patterns:
    target_glob: "**/*.md"
    exclude:
      - ".toc_work"
      - "rules_toc.yaml"
      - "reference"

  output:
    header_comment: "Development documentation search index for rules-advisor subagent"
    metadata_name: "Development Documentation Search Index"

# === specs configuration ===
specs:
  root_dir: specs
  toc_file: .claude/doc-advisor/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/specs/.toc_work/

  patterns:
    target_dirs:
      requirement: requirements
      design: design
    exclude:
      - ".toc_work"
      - ".toc_checksums.yaml"
      - "specs_toc.yaml"
      - "reference"
      - "/info/"

  output:
    header_comment: "Requirements and design document search index for specs-advisor subagent"
    metadata_name: "Requirements and Design Document Search Index"

# === common configuration ===
common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
```

### Customizing Configuration

Edit the project config file directly, or re-run setup:

```bash
# Re-run setup interactively
./setup.sh /path/to/your-project

# Or edit directly
nano /path/to/your-project/.claude/doc-advisor/config.yaml
```

## Processing Modes

| Mode | Description |
|------|-------------|
| full | Scan all files and regenerate ToC |
| incremental | Process only changed files (SHA-256 hash detection) |
| continuation | Resume interrupted processing |

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

### Commands not recognized

Verify the files exist:
```bash
ls -la /path/to/your-project/.claude/commands/
ls -la /path/to/your-project/.claude/agents/
```

### ToC generation fails

1. Check if target directories exist in your project
2. Verify config paths are correct
3. Look for `.claude/doc-advisor/{rules,specs}/.toc_work/` for recovery

## Migration from v2.0 (Plugin Mode)

If you were using the plugin mode (`--plugin-dir`), follow these steps:

1. Run setup.sh on your project to install the new files
2. Remove the `--plugin-dir` flag when starting Claude Code
3. Your existing `config.yaml` in `.claude/doc-advisor/` will be preserved

## License

MIT License
