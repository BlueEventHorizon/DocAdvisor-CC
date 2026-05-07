# Doc Advisor

English | [日本語](README.md)

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

### Claude Code

1. Clone the repository (with submodules)

```bash
git clone --recursive https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

> If you already cloned without `--recursive`, run `git submodule update --init`.

2. Run setup for your target project

```bash
cd DocAdvisor-CC
./setup.sh /path/to/your-project
```

3. Launch Claude Code

```bash
cd /path/to/your-project
claude
```

4. Configure document directories

If `setup.sh` detected `.doc_structure.yaml`, directories are auto-configured.
Otherwise, run the classification skill:

```bash
/setup-doc-structure
```

5. Generate initial ToC files

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

### Codex

For Codex, this repository installs the pre-generated and reviewed `codex_skill_set/` into the target project as a project-local bridge.
It does not write to Codex's global skill directory.

1. Clone the repository (with submodules)

```bash
git clone --recursive https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

> If you already cloned without `--recursive`, run `git submodule update --init`.

2. Install the Codex bridge into your target project

```bash
cd DocAdvisor-CC
./setup_for_codex.sh /path/to/your-project
```

3. Launch Codex in the target project

```bash
cd /path/to/your-project
codex
```

4. Available bridge functions

`setup_for_codex.sh` adds a managed Doc Advisor bridge section to the target project's `AGENTS.md`.
Codex uses that table to find the project-local skills.

| Function | Path |
| -------- | ---- |
| rules ToC generation | `.codex/doc-advisor/skills/create-rules-toc/SKILL.md` |
| specs ToC generation | `.codex/doc-advisor/skills/create-specs-toc/SKILL.md` |
| rules search | `.codex/doc-advisor/skills/query-rules/SKILL.md` |
| specs search | `.codex/doc-advisor/skills/query-specs/SKILL.md` |
| document structure setup | `.codex/doc-advisor/skills/setup-doc-structure/SKILL.md` |

Codex ToC and index outputs are written under `.codex/doc-advisor/toc/` and `.codex/doc-advisor/index/`.
They are separate from Claude Code's `.claude/` files.

## Usage

### Claude Code

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

### Codex

In Codex, use natural-language requests instead of slash commands.
Codex will refer to the Doc Advisor bridge section in `AGENTS.md` and the relevant `.codex/doc-advisor/skills/.../SKILL.md` file.

Examples:

```text
Regenerate the full rules ToC.
Incrementally update the specs ToC.
Find the rules needed to implement authentication.
Find specs related to screen navigation.
Configure the document structure.
```

## Configuration

Config file: `.doc_structure.yaml` (project root)

- Customize `rules` / `specs` root directories and doc_type mappings
- Add user-defined exclude patterns as needed
- Doc Advisor internal settings (toc paths, parallelism) are built-in defaults

## Documentation

- Japanese: [TECHNICAL_GUIDE_ja.md](TECHNICAL_GUIDE_ja.md)
- English: [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md)

## Requirements

- Python 3 (standard library only)
- Claude Code
- Codex (when using the Codex bridge)
- Bash shell

## Codex Install Profile

`setup_for_codex.sh` installs only when the source version, commit, layout hash, and `codex_skill_set` hash match `codex_install_profiles/doc-advisor/current.yaml`.

When the `bw-cc-plugins` plugin layout or version changes, regenerate and review the Codex skill set and install profile first.

```bash
./analyze_codex_install_profile.sh
./generate_codex_skill_set.sh
./setup_for_codex.sh /path/to/your-project
```

List available profiles with:

```bash
./setup_for_codex.sh --list-profiles
```

## License

MIT License
