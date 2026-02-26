# Changelog

All notable changes to Doc Advisor are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [4.0.0] - 2026-02-25

### Added
- **`/classify-docs` skill**: AI-driven directory classification using `classify_dirs.py` scanner and `classification_rules.md`; replaces `setup_dirs.sh`
- **Skill Pre-check**: `check_config.sh` called at the start of each skill (create-*-toc, query-*) to detect unconfigured directories and trigger `/classify-docs` first
- **`classify_dirs.py`**: Python stdlib directory scanner that outputs JSON metadata for AI classification
- **`classification_rules.md`**: Classification rules for AI to categorize directories as rules/specs with doc_type
- **`doc_type` in ToC**: Each ToC entry includes `doc_type` field auto-derived from file path via `.doc_structure.yaml`
- **Path display**: `display_path()` function replaces `$HOME` with `~` for readable terminal output

### Changed
- **setup.sh scope**: Now focuses solely on template copy and placeholder substitution; directory classification delegated to target project
- **`.doc_structure.yaml` check**: Changed from error-exit to warning + `/classify-docs` guidance
- **Version identifier**: Updated from `3.8` to `4.0` across all managed files

### Removed
- **`setup_dirs.sh`**: Replaced by `/classify-docs` skill (AI-driven classification)
- **`--skip-doc-structure` flag**: No longer needed since setup.sh doesn't perform directory classification

### Files modified (templates/)
- `skills/classify-docs/SKILL.md` - New: AI-driven directory classification skill
- `doc-advisor/scripts/check_config.sh` - New: Skill pre-check script
- `doc-advisor/scripts/classify_dirs.py` - New: Directory scanner
- `doc-advisor/docs/classification_rules.md` - New: AI classification rules

---

## [3.8.0] - 2026-02-21

### Changed
- **`doc_type` removed**: AI determines document type from content; `doc_type` field removed from all YAML schemas, pending templates, merge/validate/write scripts, and format docs
- **`Feature` removed**: Flattened directory structure (`specs/main/requirements/` → `specs/`); `target_dirs` config replaced with `target_glob: "**/*.md"`
- **`root_dirs` array support**: `root_dir` (string) → `root_dirs` (array) in config.yaml; backward compatibility: `load_config()` auto-converts old `root_dir` format
- **setup.sh simplified**: Removed 3 subdirectory prompts (requirements, design, plan); input sequence reduced from 6 to 3 values
- **Version identifier**: Updated from `3.6` to `3.8` across all managed files

### Fixed
- **`set -e` + `read` EOF crash**: Added `|| true` to CLAUDE.md `read` prompt in setup.sh to prevent exit on piped input EOF
- **Unsafe `eval` in setup.sh**: Replaced `eval echo "$TARGET_DIR"` with safe parameter expansion `${TARGET_DIR/#\~/$HOME}`

### Files modified (templates/)
- `scripts/toc_utils.py` - `root_dir` → `root_dirs`, `target_dirs` → `target_glob`, `get_default_target_dirs()` removed
- `scripts/create_checksums.py` - Multi `root_dirs` loop, `find_md_files_specs()` simplified
- `scripts/create_pending_yaml_specs.py` - `doc_type` removed, `TARGET_DIRS`/`is_target_dir()`/`get_doc_type()` removed, multi `root_dirs`
- `scripts/create_pending_yaml_rules.py` - Multi `root_dirs` loop
- `scripts/merge_specs_toc.py` - `doc_type` removed, `TARGET_DIRS`/`is_target_dir()` removed, multi `root_dirs`
- `scripts/merge_rules_toc.py` - Multi `root_dirs` loop
- `scripts/validate_specs_toc.py` - `requirements`/`designs` → unified `docs`, `doc_type` removed, multi `root_dirs`
- `scripts/validate_rules_toc.py` - Multi `root_dirs` loop
- `scripts/write_specs_pending.py` - `doc_type` output removed
- `docs/specs_toc_format.md` - `doc_type` schema/examples removed, path examples simplified
- `docs/specs_toc_update_workflow.md` - `doc_type` removed, target_dirs → glob
- `docs/specs_orchestrator.md` - `doc_type` removed, path examples simplified
- `agents/specs-toc-updater.md` - `doc_type` references removed
- `skills/query-specs/SKILL.md` - `doc_type` classification removed
- `doc-advisor/config.yaml` - `root_dir` → `root_dirs`, `target_dirs` → `target_glob`

### Files modified (project root)
- `setup.sh` - Subdirectory prompts removed, `eval` removed, `read` EOF fix

---
## [3.6.0] - 2026-02-19

### Fixed
- **`--cleanup` flag removal**: Removed broken `--cleanup` flag from merge scripts and orchestrator docs; cleanup is now a separate `rm -rf` step in Phase 3
- **Error policy contradiction**: Updater agents L18 changed from "continue to next step" to "exit immediately" to match L74/79
- **References contradiction**: specs-toc-updater now allows abstract references when explicitly mentioned in source document
- **Non-existent skill reference**: Replaced `/create-toc-checksums` with `cp` command in both workflow docs
- **Command name typo**: `create-rules_toc` → `create-rules-toc`, `create-specs_toc` → `create-specs-toc` in updater agents
- **`{feature}` placeholder notation**: Changed to `<feature>` in specs-advisor for clarity
- **Frontmatter extra `"`**: Removed trailing `"` from `doc-advisor-version-xK9XmQ` in all 12 template files
- **Validate script label**: "YAML構文検査" → "ファイル読み込み検査" (actual behavior is file read, not YAML parsing)
- **metadata.name mismatch**: Format docs now match config.yaml values
- **Pending template missing field**: Added `references: []` to specs pending YAML template
- **Docstring separator**: Updated usage examples from comma to `|||` separator in write_*_pending.py

### Changed
- **Error handling docs**: Added concrete Read → Edit steps for `_meta.status` error transition in orchestrator docs
- **Error handling workflow**: specs_toc_update_workflow.md error handling aligned with orchestrator (error → no retry)
- **Version identifier**: Updated from `3.5` to `3.6` across all managed files

### Files modified
- `merge_rules_toc.py`, `merge_specs_toc.py` - Removed `--cleanup` flag
- `rules_orchestrator.md`, `specs_orchestrator.md` - `--cleanup` removal, cleanup step, error handling steps
- `rules-toc-updater.md`, `specs-toc-updater.md` - Command name, error policy, frontmatter fix
- `specs-advisor.md` - `<feature>` notation, frontmatter fix
- `rules-advisor.md` - Frontmatter fix
- `rules_toc_format.md`, `specs_toc_format.md` - metadata.name, frontmatter fix
- `rules_toc_update_workflow.md`, `specs_toc_update_workflow.md` - Checksum command, frontmatter fix
- `create-rules-toc/SKILL.md`, `create-specs-toc/SKILL.md` - Frontmatter fix
- `validate_rules_toc.py`, `validate_specs_toc.py` - Label fix
- `create_pending_yaml_specs.py` - `references: []` addition
- `write_rules_pending.py`, `write_specs_pending.py` - Docstring separator fix
- `test_merge.sh` - `--cleanup` → manual cleanup

---

## [3.5.0] - 2026-02-11

### Changed
- **Version identifier**: Updated from `3.4` to `3.5` across all managed files

### Fixed
- **`references: []` corruption**: `parse_simple_yaml()` treated inline `[]` as string `"[]"` instead of empty list, causing `write_yaml_output()` to iterate over characters producing `"["`, `"]"` entries
  - Fixed in `toc_utils.py`, `merge_specs_toc.py`, `merge_rules_toc.py`
- **content_details comma splitting**: `parse_comma_separated()` split on all commas, breaking items containing commas (e.g., "10,000件")
  - Changed separator from `,` to `|||` in `write_specs_pending.py`, `write_rules_pending.py`
  - Updated subagent instructions (`specs-toc-updater.md`, `rules-toc-updater.md`)
- **`.toc_checksums_pending.yaml` misread**: Merge scripts' `*.yaml` glob picked up dot-prefixed files in `.toc_work/`
  - Added dot-file exclusion in `merge_specs_toc.py`, `merge_rules_toc.py`
- **references path hallucination**: Added instruction for subagent to verify file paths with Glob before including in references

### Files modified
- `toc_utils.py` - `parse_simple_yaml()`: `[]` handled as empty list
- `merge_specs_toc.py` - `load_existing_toc()`: `[]` handling, dot-file exclusion
- `merge_rules_toc.py` - `load_existing_toc()`: `[]` handling, dot-file exclusion
- `write_specs_pending.py` - Separator changed to `|||`
- `write_rules_pending.py` - Separator changed to `|||`
- `specs-toc-updater.md` - `|||` separator, references path verification
- `rules-toc-updater.md` - `|||` separator

---

## [3.4.0] - 2026-02-09

### Added
- **Phase 1 checksums snapshot**: `create_pending_yaml_rules.py` and `create_pending_yaml_specs.py` now save `.toc_checksums_pending.yaml` during Phase 1
  - Captures file hashes at the time of pending YAML generation
  - Used in Phase 3 to replace `.toc_checksums.yaml` instead of recalculating
  - Ensures files modified during Phase 2 (subagent processing) are detected as changed in the next incremental run
- **CLAUDE.md rule addition**: `setup.sh` now offers to add Doc Advisor rules to the target project's `CLAUDE.md`
  - Adds "ToC direct modification forbidden" rule with skill references
  - Uses HTML comment markers for idempotent detection (`<!-- doc-advisor-section-start -->`)
  - Skips if rules are already present

### Changed
- **Version identifier**: Updated from `3.3` to `3.4` across all managed files
- **Phase 3 checksum update**: Orchestrators now use `cp .toc_checksums_pending.yaml` instead of running `create_checksums.py`
  - Prevents the "stale ToC" problem when source files are modified during Phase 2
  - `create_checksums.py` is still used for delete-only mode
- **Batch processing**: Removed hardcoded "batch of 5" from `specs_orchestrator.md`, now uses generic "batch"
- **Version management**: Removed hardcoded version from README.md, README_ja.md, TECHNICAL_GUIDE.md, TECHNICAL_GUIDE_ja.md, Makefile, setup.sh headers
  - `setup.sh` の `DOC_ADVISOR_VERSION` が唯一のハードコード箇所に
  - Makefile, テストは `setup.sh` から動的取得
  - `update_version.py` を簡素化（対象ファイルが `setup.sh` + `CHANGELOG.md` のみに）

### Files modified
- `create_pending_yaml_rules.py` - Added `save_pending_checksums()` function
- `create_pending_yaml_specs.py` - Added `save_pending_checksums()` function
- `specs_orchestrator.md` - Phase 3 `cp` replacement, "batch" wording fix
- `rules_orchestrator.md` - Phase 3 `cp` replacement
- `setup.sh` - CLAUDE.md rule addition feature
- `test_checksums.sh` - Added pending checksums tests
- `test_setup_upgrade.sh` - Added CLAUDE.md tests (Tests 11-14)

---

## [3.3.0] - 2026-02-06

### Added
- **References field**: `specs_toc.yaml` now includes a `references` field to track document cross-references
  - Direct references only (no recursive following)
  - Supports both concrete paths and abstract references
  - Empty array `[]` allowed for documents with no references
- **Version placeholder**: Template files now use `{{DOC_ADVISOR_VERSION}}` placeholder
  - Replaced at setup time by `setup.sh`
  - Version changes now require updating only `setup.sh`

### Changed
- **Version identifier**: Updated from `3.2` to `3.3` across all managed files
- **setup.sh**: Now substitutes `{{DOC_ADVISOR_VERSION}}` in `.py` files as well as `.md` and `.yaml`

### Files modified
- `specs_toc_format.md` - Added references field to schema
- `specs_toc_update_workflow.md` - Added references to subagent processing
- `specs-toc-updater.md` - Added `--references` parameter
- `write_specs_pending.py` - Added `--references` argument
- `merge_specs_toc.py` - Added references field handling

---

## [3.2.0] - 2026-02-05

### Added
- **Symlink support**: All scripts now follow symbolic links when scanning `rules/` and `specs/` directories
  - New `rglob_follow_symlinks()` function in `toc_utils.py`
  - Inode tracking prevents infinite loops from circular symlinks
  - Duplicate detection avoids processing the same file multiple times via different symlink paths
- **Symlink tests**: New `tests/test_symlink.sh` for comprehensive symlink handling verification

### Changed
- **Version identifier**: Updated from `3.1` to `3.2` across all managed files

### Fixed
- Python's `Path.rglob()` and `Path.glob()` do not follow symlinks by default - now using `os.walk(followlinks=True)` wrapped in `rglob_follow_symlinks()`

### Scripts modified
- `create_checksums.py` - `find_md_files_rules()`, `find_md_files_specs()`
- `create_pending_yaml_rules.py` - `get_all_md_files()`
- `create_pending_yaml_specs.py` - `get_all_md_files()`
- `merge_rules_toc.py` - `get_existing_files()`
- `merge_specs_toc.py` - `get_existing_files()`

---

## [3.1.0] - 2026-02-04

### Added
- **Version identifier**: All managed files now include `doc-advisor-version: "3.1"` for future upgrade detection (REQ-002-NF-02)
- **Identifier-based protection**: Legacy cleanup now checks for `doc-advisor-version` before deletion - files with identifier are protected

### Changed
- **Skill split**: Single `doc-advisor` skill split into two independent skills:
  - `/create-rules-toc [--full]` - Generate rules ToC
  - `/create-specs-toc [--full]` - Generate specs ToC
- **Command format**:
  - `/doc-advisor make-rules-toc` → `/create-rules-toc`
  - `/doc-advisor make-specs-toc` → `/create-specs-toc`
- **Argument handling**: `--full` option now properly passed as `$0` instead of unused `$1`

### Structure (v3.1)
```
.claude/
├── agents/
│   ├── rules-advisor.md
│   ├── specs-advisor.md
│   ├── rules-toc-updater.md
│   └── specs-toc-updater.md
├── skills/
│   ├── create-rules-toc/
│   │   └── SKILL.md            # rules ToC generation
│   └── create-specs-toc/
│       └── SKILL.md            # specs ToC generation
└── doc-advisor/
    ├── config.yaml             # Configuration
    ├── docs/                   # Documentation
    ├── scripts/                # Python scripts
    └── toc/                    # Runtime output
        ├── rules/
        └── specs/
```

### Removed
- `skills/doc-advisor/` (replaced with split skills)

### Fixed
- `$1` argument (`--full` option) was not being used in the previous unified skill

---

## [3.0.0] - 2026-02-03

### Added
- **Skills integration**: doc-advisor is now a Claude Code Skill with `$ARGUMENTS` support
- **Unified command interface**: `/doc-advisor make-rules-toc [--full]` and `/doc-advisor make-specs-toc [--full]`
- **Auto-triggering**: Claude can automatically suggest ToC updates when documents change
- **Orchestrator docs**: `rules_orchestrator.md` and `specs_orchestrator.md` for skill execution flow
- **Upgrade support**: Automatic legacy file cleanup from v2.0

### Changed
- **Directory structure** (major reorganization):
  - `commands/` deprecated and removed (migrated to Skills)
  - `skills/doc-advisor/` now contains only `SKILL.md` (entry point)
  - All resources moved to `doc-advisor/`:
    - `doc-advisor/config.yaml` - configuration
    - `doc-advisor/docs/` - documentation
    - `doc-advisor/scripts/` - Python scripts
  - Runtime output reorganized:
    - `doc-advisor/rules/` → `doc-advisor/toc/rules/`
    - `doc-advisor/specs/` → `doc-advisor/toc/specs/`
- **Command format**:
  - `/create-rules_toc` → `/doc-advisor make-rules-toc`
  - `/create-specs_toc` → `/doc-advisor make-specs-toc`
- **setup.sh behavior**:
  - `agents/` now uses overwrite-only mode (preserves user's custom agents)
  - `skills/doc-advisor/` uses clean install mode (SKILL.md only)
  - `doc-advisor/` resources are copied fresh
  - Legacy files are automatically deleted (file-specific, not directory-wide)
  - `config.yaml` protection with skip/overwrite/merge options

### Structure (v3.0)
```
.claude/
├── agents/
│   ├── rules-advisor.md
│   ├── specs-advisor.md
│   ├── rules-toc-updater.md
│   └── specs-toc-updater.md
├── skills/
│   └── doc-advisor/
│       └── SKILL.md            # Entry point only
└── doc-advisor/
    ├── config.yaml             # Configuration
    ├── docs/                   # Documentation
    ├── scripts/                # Python scripts
    └── toc/                    # Runtime output
        ├── rules/
        │   ├── rules_toc.yaml
        │   ├── .toc_checksums.yaml
        │   └── .toc_work/
        └── specs/
            ├── specs_toc.yaml
            ├── .toc_checksums.yaml
            └── .toc_work/
```

### Removed
- `templates/commands/` directory

### Fixed
- User's custom agents and commands are no longer accidentally deleted during upgrade
- Legacy cleanup no longer incorrectly deletes `doc-advisor/config.yaml` on re-install (was looking for v2.0 legacy in wrong path)

---

## [2.0.0] - 2026-01-25

### Added
- **Project-based setup**: All files copied to target project (no `--plugin-dir` needed)
- **Slash commands**: `/create-rules_toc` and `/create-specs_toc`
- **Parallel processing**: Up to 5 concurrent subagents for ToC generation
- **Incremental updates**: SHA-256 hash-based change detection
- **Interruption recovery**: `.toc_work/` directory preserves partial results
- **Custom directory support**: Configurable rules/specs directory names
- **Agent model selection**: Choose opus/sonnet/haiku/inherit for subagents

### Changed
- Moved from plugin mode to project-based mode
- Configuration file location: `.claude/doc-advisor/config.yaml`
- Documentation location: `.claude/doc-advisor/docs/`

### Structure (v2.0)
```
.claude/
├── commands/
│   ├── create-rules_toc.md
│   └── create-specs_toc.md
├── doc-advisor/
│   ├── config.yaml
│   └── docs/
├── agents/
│   ├── rules-advisor.md
│   ├── specs-advisor.md
│   ├── rules-toc-updater.md
│   └── specs-toc-updater.md
└── skills/
    └── doc-advisor/
        ├── SKILL.md
        └── scripts/
```

---

## [1.0.0] - 2026-01-20

### Added
- **Initial release**
- **Plugin mode**: Run with `claude --plugin-dir /path/to/DocAdvisor-CC`
- **Basic ToC generation**: Parse `.md` files and generate YAML index
- **Document categories**: rules (development docs) and specs (requirements/design)
- **doc_type detection**: Automatic detection based on directory path
- **Advisor agents**: rules-advisor and specs-advisor for document lookup

### Structure (v1.x)
```
DocAdvisor-CC/  (plugin directory)
├── commands/
│   ├── create-rules_toc.md
│   └── create-specs_toc.md
├── agents/
│   └── ...
└── skills/
    └── doc-advisor/
        └── scripts/
```

---

## Version Comparison

| Feature | v1.x | v2.0 | v3.0 | v3.1 | v3.2 |
|---------|------|------|------|------|------|
| Installation | Plugin mode | Project-based | Project-based | Project-based | Project-based |
| Commands | `/create-*_toc` | `/create-*_toc` | `/doc-advisor make-*-toc` | `/create-rules-toc`, `/create-specs-toc` | `/create-rules-toc`, `/create-specs-toc` |
| Config location | Plugin dir | `.claude/doc-advisor/` | `.claude/doc-advisor/` | `.claude/doc-advisor/` | `.claude/doc-advisor/` |
| Docs/Scripts location | Plugin dir | `.claude/doc-advisor/` | `.claude/doc-advisor/` | `.claude/doc-advisor/` | `.claude/doc-advisor/` |
| ToC output location | Plugin dir | `.claude/doc-advisor/rules/` | `.claude/doc-advisor/toc/rules/` | `.claude/doc-advisor/toc/rules/` | `.claude/doc-advisor/toc/rules/` |
| Auto-trigger | No | No | Yes | Yes | Yes |
| Parallel processing | No | Yes | Yes | Yes | Yes |
| Incremental updates | No | Yes | Yes | Yes | Yes |
| Custom directories | No | Yes | Yes | Yes | Yes |
| Upgrade support | - | - | Yes | Yes | Yes |
| Symlink support | No | No | No | No | Yes |

---

## Upgrade Path

### v3.1 → v3.2

Run `setup.sh` on your project:

```bash
./setup.sh /path/to/your-project
```

**Automatic changes:**
- All scripts updated with symlink support
- Version identifier updated to `3.2`

**No command changes** - same commands as v3.1.

### v3.0 → v3.1

Run `setup.sh` on your project:

```bash
./setup.sh /path/to/your-project
```

**Automatic changes:**
- `skills/doc-advisor/` removed (replaced with split skills)
- New skills installed: `skills/create-rules-toc/`, `skills/create-specs-toc/`

**Command changes:**
- `/doc-advisor make-rules-toc` → `/create-rules-toc`
- `/doc-advisor make-specs-toc` → `/create-specs-toc`

### v2.0 → v3.1

Run `setup.sh` on your project:

```bash
./setup.sh /path/to/your-project
```

**Automatic changes:**
- Legacy commands deleted: `commands/create-rules_toc.md`, `commands/create-specs_toc.md`
- `skills/doc-advisor/` removed
- New skills installed: `skills/create-rules-toc/`, `skills/create-specs-toc/`
- `doc-advisor/docs/` and `doc-advisor/scripts/` updated
- ToC output moved: `doc-advisor/rules/` → `doc-advisor/toc/rules/`
- ToC output moved: `doc-advisor/specs/` → `doc-advisor/toc/specs/`

**Preserved:**
- Your custom commands in `commands/`
- Your custom agents in `agents/`
- Your `config.yaml` settings (with skip/overwrite/merge options)

**Note:** After upgrade, regenerate ToC files:
```bash
/create-rules-toc --full
/create-specs-toc --full
```

### v1.x → v3.1

1. Remove plugin mode usage (`--plugin-dir` flag)
2. Run `setup.sh` on your project
3. Regenerate ToC with new commands:
   ```bash
   /create-rules-toc --full
   /create-specs-toc --full
   ```
