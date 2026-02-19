# Doc Advisor

[![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Introduction

Generative AI can miss important specs even when you say “read the docs.”
Doc Advisor is built on that constraint to ensure the AI reads only what it truly needs.

## Premise

This project builds on the ideas in:
[Why generative AI doesn't read documents even when asked — Context Engineering and Doc Advisor](https://zenn.dev/k2moons/articles/ff6399ee33346e)

Key limitations highlighted there:

- Context Rot: Information in the middle of long contexts is missed
- Attention Budget: Attention is finite and degrades with excessive input
- Satisficing: The model stops early with a “good-enough” answer

## Goals and Features

Doc Advisor’s goal is to identify the right documents quickly and reliably.
Key features:

- **Document categories**: Separate rules and specs
- **doc_type management**: requirement / design / plan
- **Automatic ToC generation**: Parse `.md`, extract metadata, output YAML
- **Incremental updates**: SHA-256 change detection
- **Parallel processing**: Up to 5 concurrent workers
- **Interruption recovery**: Preserve completed work and resume
- **Symlink support**: Include external documentation via symbolic links (v3.2+)
- **Multi-source aggregation**: Add external directories or git repos via symlinks under `.claude/doc-advisor/docs/` (v3.7+)

For full details, see [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md).

## Design Intent (Highlights)

- **rules / specs separation**: Reduce search cost and ambiguity
- **plan excluded from ToC**: Plans are read in full during work
- **Path-based doc_type detection**: Stable detection without filename constraints
- **File path as identifier**: Avoid forced IDs and keep references consistent
- **Incremental processing**: Only reprocess what changed
- **Interruption-first**: `.toc_work/` keeps artifacts for safe resumption

## Typical Use Cases

- Large document sets: Retrieve only what matters
- Frequent updates: Reprocess deltas only
- Interruptions: Resume from pending entries
- Deletions: Apply delete-only updates via checksums
- Parallel failures: Fall back to serial processing

## Quick Start

1) Clone the repository

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

2) Run setup for your target project

```bash
cd DocAdvisor-CC
./setup.sh /path/to/your-project
```

3) Launch Claude Code

```bash
cd /path/to/your-project
claude
```

4) Generate initial ToC files

```bash
/create-rules-toc --full
/create-specs-toc --full
```

> Using the Makefile:
>
> ```bash
> make setup
> make setup TARGET=/path/to/your-project
> ```

## Usage

### ToC generation commands

```bash
/create-rules-toc          # Incremental update
/create-rules-toc --full   # Full rebuild

/create-specs-toc          # Incremental update
/create-specs-toc --full   # Full rebuild
```

### Document search skills

```bash
/query-rules Identify documents for implementing authentication
/query-specs Find requirements for screen navigation
```

## Configuration

Config file: `.claude/doc-advisor/config.yaml`

- Customize `rules` / `specs` root directories and doc_type directory names
- Add user-defined exclude patterns as needed
- System files (`.toc_work/`, `*_toc.yaml`, `.toc_checksums.yaml`) are always excluded

## Documentation

- Japanese: [TECHNICAL_GUIDE_ja.md](TECHNICAL_GUIDE_ja.md)
- English: [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md)

## Requirements

- Python 3 (standard library only)
- Claude Code
- Bash shell

## License

MIT License
