# Changelog

All notable changes to Doc Advisor are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Codex environment Skill installer**: Added `setup_for_codex.sh` to install the reviewed Codex-native Doc Advisor skill set as ordinary environment-wide Codex Skills under `${CODEX_HOME:-~/.codex}/skills`.
	  - Installs shared resources under `${CODEX_HOME:-~/.codex}/doc-advisor/resources`
	  - Supports optional `--project PROJECT_DIR` initialization for `.codex/state/doc-advisor/` and an idempotent managed `AGENTS.md` section
	  - Preserves target project content outside the managed Doc Advisor section when `--project` is used
	  - Removes legacy project-local Doc Advisor managed paths when `--project` is used to avoid stale duplicate skills
	  - Keeps ToC/index runtime state project-local and prevents global resources from accumulating Python cache files during Codex Skill script execution
	  - Validates source plugin version, forge version, source commit, layout hash, `codex_skill_set` hash, and `reviewed: true` profile status before install
  - Records project install metadata in `.codex/installs/doc-advisor.yaml` when `--project` is used
  - Supports `--source`, `--profile`, `--codex-set`, `--codex-home`, `--project`, and `--list-profiles`
- **Codex-native skill set**: Added `codex_skill_set/` with Codex-compatible `SKILL.md` files and bundled resources.
  - Included Doc Advisor skills: `create-rules-toc`, `create-specs-toc`, `query-rules`, `query-specs`
  - Included forge setup skill: `setup-doc-structure`
  - Included forge authoring wrappers: `start-requirements`, `start-design`, `start-plan`
  - Included resources: doc-advisor docs/scripts, `toc-updater` reference, forge `doc_structure` docs/scripts, forge format/principle docs, requirements workflow docs, and `next-spec-id` helper resources
  - Disabled: `create-code-index`, `query-code`
  - Excluded: forge localhost monitor, review automation, version update, and cleanup
- **Codex confirmation protocol**: Added `codex_confirmation_protocol.md` for chat-based user confirmation in Codex forge wrappers.
- **Codex install profiles**: Added `codex_install_profiles/doc-advisor/current.yaml` and a versioned profile keyed by source version, source commit, and layout hash.
- **Codex generation tools**:
  - `generate_codex_skill_set.sh`: Generates the reviewed Codex-native skill set and profile from read-only `bw-cc-plugins` sources
  - `analyze_codex_install_profile.sh`: Reports source version, forge version, branch, commit, dirty status, and layout hash
- **Codex local tests**:
  - `tests/test_codex_skill_set.sh`
  - `tests/test_setup_for_codex.sh`
  - `tests/test_codex_scenario.sh`
  - `tests/codex_test_project/`

### Changed
- **README / README_en**: Added Codex quick start, natural-language usage examples, environment Skill layout, and install profile regeneration guidance.
- **Codex design**: Documented the project-local bridge as a non-official migration/experiment pattern and removed its active `AGENTS.md` usage from this project.
- **Full test suite**: Added Phase 7 for Codex skill set, setup, and deterministic local scenario validation.
- **Codex design spec**: Updated `DES-CODEX-001_setup_for_codex.md` to match the implemented combined Doc Advisor + supported forge profile model.

### Tests
- `bash tests/run_all_tests.sh` passes all phases, including the new Codex Phase 7 suites.

---




## [5.2.0] - 2026-04-25

### Added
- **Optional plugins**: `--with-anvil` and `--with-xcode` flags install additional skills alongside doc-advisor.
  - `--with-anvil`: GitHub commit / create-pr skills from `bw-cc-plugins/plugins/anvil`
  - `--with-xcode`: iOS/macOS build / test skills from `bw-cc-plugins/plugins/xcode`
  - Interactive mode (no `TARGET_DIR` argument) prompts `[y/N]` for each optional plugin
  - Layout: SKILL.md → `.claude/skills/<skill>/`, sub-resources (scripts) → `.claude/<plugin>/`
  - Transforms: `${CLAUDE_PLUGIN_ROOT}/` → `.claude/<plugin>/`, `/<plugin>:xxx` → `/xxx`
  - Missing source handled gracefully (warning + skip, core install still succeeds)
  - Per-plugin `.source_version` file records plugin name, version, and install timestamp
- **`tests/test_optional_plugins.sh`**: Phase 6 test suite (54 checks) covering default-off behavior, `--with-anvil` only, `--with-xcode` only, both-at-once, transform correctness, executable bit, `.source_version` metadata, and graceful handling of missing plugin sources

### Changed
- **Architecture overhaul**: Abolished `templates/` directory; Doc Advisor now installs by reading sources directly from the `bw-cc-plugins` submodule and applying path/name transforms at install time. The repository becomes a thin installer that mediates between `bw-cc-plugins` (read-only) and target projects.
  - Added `bw-cc-plugins` as a git submodule — `git clone --recursive` (or `git submodule update --init`) is now required
  - `setup.sh` rewritten with `--source <path>` argument (default: submodule path); applies three sed transforms during install:
    - `${CLAUDE_PLUGIN_ROOT}/` → `.claude/doc-advisor/`
    - `/doc-advisor:` → `/`
    - `/forge:setup-doc-structure` → `/setup-doc-structure`
  - Auto-copies `setup-doc-structure` SKILL and `doc_structure/` scripts from the `forge` plugin
  - Reads source `plugin.json` version, validates against `KNOWN_VERSIONS`, records `.source_version` in target
- **`check_doc_structure.sh` abolished**: Validation logic merged into Python error handling across `create_checksums.py`, `create_pending_yaml.py`, `merge_toc.py`, `validate_toc.py`, and `toc_utils.py` — eliminates the standalone shell pre-check
- **`{{AGENT_MODEL}}` placeholder removed**: `toc-updater` agent now hardcodes `haiku`; model switching delegated to a separate `change_agent_model.sh` script
- **README split**: `README.md` is now Japanese (primary); English version moved to `README_en.md`. `TECHNICAL_GUIDE.md` / `TECHNICAL_GUIDE_ja.md` updated accordingly

### Removed
- `templates/` directory and all 19 source files (agents, skills, docs, scripts) — now sourced from `bw-cc-plugins`
- Stale `.claude/` artifacts checked into the repo: legacy commands (`create-pr`, `read-conversation`, `read-docs`, `save-conversation`), unused agents (`task-executor`, old `toc-updater`), obsolete skills (`classify-docs`, `docadvisor-dev`), and superseded `config.yaml{,.bak,.old}` files

### Fixed
- **Code review findings (12 items)** addressed across docs and scripts:
  - `validate_toc.py`: stale `{target}` comment, inline `[]` array handling, `expand_root_dir_globs()` call in `init_config()`
  - `create_checksums.py`: migrated from `sys.argv` to `argparse`, introduced `init_config()` pattern, merged duplicate `find_md_files`
  - `SKILL.md` (create-rules/specs-toc): residual "target = rules/specs" text
  - `DES-004` / `DES-005`: output defaults aligned with `_get_default_config()`, `--category` arg added to component list
  - `classify_dirs.py`: version tag placeholder added
- **target → category rename**: residual occurrences fixed in `toc_utils.py` and doc templates not covered by 5.1.0
- **`check_config.sh` → `check_doc_structure.sh`**: rename aligned with the `.doc_structure.yaml` migration (later abolished entirely; see Changed)

### Tests
- Added Test 40–49 covering: sed transform verification, `--source` argument, source validation, forge detection / absence, `.source_version` recording, v0.2.1 legacy cleanup, dynamic skill detection, `__pycache__` exclusion
- Fixed pre-existing path mismatches (Test 17/22), removed `templates/` references (Test 32), separated stderr (M-09)

### Migration
- Existing installations: re-run `./setup.sh <target>` after `git submodule update --init`. The setup script's v0.2.1 legacy cleanup removes obsolete `.claude/doc-advisor/` artifacts from prior versions automatically.

---
## [5.1.0] - 2026-03-26

### Changed
- **CLI argument rename**: `--target` → `--category` across all Python scripts (5 files), Markdown templates (4 files), and test scripts (8 files) to align with REQ-001 terminology
- **Custom doc_type support**: `doc_types_map` now officially supports custom type identifiers (e.g., `adr`) in addition to built-in 7 types. No code changes required — `validate_toc.py` already accepts any non-empty string
- **Version identifier**: Updated from `5.0` to `5.1` across all managed files

### Docs
- Updated REQ-001 (FR-01-5, terminology definitions), DES-004 (doc_type list with custom type spec), DES-005 (component list with --category, validate_toc.py name fix)

---
## [5.0.0] - 2026-03-15

### Added
- **REQ-003**: Generic versioned migration requirements (`specs/requirements/REQ-003_versioned_migration.md`)
- **v1.0 backward compatibility**: `_migrate_v1_to_v2()` auto-converts legacy `.doc_structure.yaml` format (in-memory only)
- **`.doc_structure.yaml` schema spec**: Full schema definition added to DES-004 (field definitions, doc_type list, merge logic)

### Changed
- **config.yaml abolished**: Replaced by `.doc_structure.yaml` (document structure) + code defaults (`toc_utils.py`)
- **`load_config()`**: Now reads `.doc_structure.yaml` directly and merges with `_get_default_config()` via `_deep_merge()`
- **`check_config.sh`**: Validates `.doc_structure.yaml` instead of config.yaml; supports v1.0 `paths:` detection
- **`setup.sh`**: Removed config.yaml handling (skip/overwrite/merge/import); added v5.0 legacy cleanup
- **`doc_structure_version`**: Bumped from 2.0 to 3.0 (structure-only format, no internal fields)
- **All SKILL.md / docs**: Updated references from config.yaml to `.doc_structure.yaml`
- **Specs revised**: REQ-001 (FR-08), DES-001, DES-002 (abolished), DES-004, DES-005
- **`/setup-config` renamed to `/setup-doc-structure`**: Aligned with forge plugin naming convention
- **Version identifier**: Updated from `4.5` to `5.0` across all managed files

### Removed
- `templates/doc-advisor/config.yaml` — replaced by `.doc_structure.yaml` + code defaults
- `templates/doc-advisor/scripts/import_doc_structure.py` — direct reading eliminates import step
- `templates/doc-advisor/scripts/merge_config.py` — config.yaml no longer exists
- `rules/claude_code_shell_wrapper.md` — outdated `/usr/bin/which python3` recommendations

---
## [4.5.0] - 2026-03-13

### Added
- **ToC staleness check**: `create_pending_yaml.py --check` flag for detecting stale ToC without creating files
- **Query skill pre-check**: `/query-rules` and `/query-specs` now warn users when ToC is outdated before returning results

### Changed
- **Python path simplified**: Removed 2-phase Python path detection (`shell-snapshots` + full path embedding); all scripts now use `python3` directly
- **`{{PYTHON_PATH}}` placeholder removed**: Templates hardcode `python3` instead of using setup-time substitution
- **`setup.sh` simplified**: Removed `PYTHON_PATH` variable, `esc_python` escaping, and `PYTHON_WRAPPED` detection logic
- **Test scripts simplified**: All 9 test suites replaced `grep/eval` Python path detection with `PYTHON_CMD=python3`
- **`rules/python_detection.md` rewritten**: Documents that `python3` works correctly via Claude Code's `wrapSafeChainCommand`; old 2-phase design deprecated
- **Version identifier**: Updated from `4.4` to `4.5` across all managed files

---
## [4.4.0] - 2026-03-07

### Added

- **`merge_config.py`**: New script (`templates/doc-advisor/scripts/`) for automatic config.yaml merging — preserves `root_dirs`, `doc_types_map`, `exclude` patterns, and custom `output`/`parallel` settings when re-running setup
- **Version-aware migration registry**: `MIGRATIONS` dict in `merge_config.py` enables sequential structural migrations across major version upgrades (currently empty for v4.x; add entries when config structure changes in future major releases)

### Changed

- **`setup.sh` Merge option**: `[m]` option renamed from "Merge manually (show diff after setup)" to "Merge (auto) - carry over your settings to new template" — now auto-applies user settings instead of requiring manual diffing
- **`rules/project_rule.md`**: Added rule 6.5 — config.yaml structure changes must be accompanied by a major version bump (X in X.Y), with corresponding `MIGRATIONS` entry and DES-001 documentation

### Fixed

- **`tests/test_setup_upgrade.sh` Test 26b**: Fixed `grep -c "- rules/"` to use `grep -c -- "- rules/"` — macOS BSD grep treated leading `-` in pattern as a flag option

---
## [4.3.0] - 2026-03-05

### Changed
- **`/classify-docs` → `/setup-config`**: Renamed for clarity — "setup config" better describes the post-setup configuration step
- **`yaml_escape()` precision**: Fixed over-quoting in `toc_utils.py` — commas, colons without trailing space, and brackets in middle of strings no longer trigger unnecessary double-quoting (YAML 1.2 block plain scalar compliant)
- **`toc-updater.md` command example**: Unified `--target rules` to `--target {target}` — specs target was broken after references section removal
- **README.md / README_ja.md**: Added `/setup-config` step to Quick Start (step 4) for projects without `.doc_structure.yaml`

### Fixed
- **`yaml_escape()` comments**: Updated `references: []` example to `keywords: []` in `merge_toc.py` and `toc_utils.py`
- **`tests/test_setup_upgrade.sh` Test 22**: Added `classify-docs/` legacy directory creation and deletion verification — the v4.3 migration cleanup in `setup.sh` was not previously tested
- **`specs/requirements/REQ-002_upgrade_v2_to_v3.md`**: Added "(旧名 classify-docs)" note to REQ-002-07 title — clarifies that v4.0 introduced the skill under the old name
- **`setup.sh` comment**: Fixed `# v4.2:` → `# v4.3:` on classify-docs migration block

### Security
- **`validate_path_within_base()`**: Added to `toc_utils.py` — shared utility to prevent `../` path traversal (CWE-22) via `Path.resolve()` + prefix check
- **`validate_rules_toc.py` / `validate_specs_toc.py`**: Validate YAML-extracted file paths and `--file` CLI arg against `PROJECT_ROOT` before file access
- **`write_pending.py`**: Validate `--entry-file` CLI arg against project root before file access
- **`import_doc_structure.py`**: Validate both CLI args (`doc_structure_path`, `config_yaml_path`) against `cwd` before file access
---

## [4.2.0] - 2026-03-05

### Added

- **`toc_format_compact.md`**: New compact format definition for large projects (100+ documents) with tighter field limits (purpose ~100 chars, content_details 5, applicable_tasks 5, keywords 8)
- **`toc-updater` `format_doc` parameter**: Agent now accepts optional format definition file path, enabling format switching
- **Orchestrator format selection**: Phase 1 auto-selects compact or full format based on pending file count (threshold: 100)

### Changed

- **`toc_format.md`**: Added explicit upper limits (purpose max 200 chars, content_details max 10, applicable_tasks max 10, keywords max 10)
- **`toc_orchestrator.md`**: Added format selection step in Phase 1, updated agent prompt and examples with `format_doc` parameter
- **Field quality guidelines**: Added "unique to this document" priority, "no heading copy" rule, and "class/method names first" keyword guidance to both full and compact formats
- **Version identifier**: Updated from `4.1` to `4.2` across all managed files

### Removed

- **`references` field**: Removed from specs ToC entries — unused by query-specs, 50% empty, caused path hallucination bugs. Affected: `write_pending.py`, `merge_toc.py`, `create_pending_yaml.py`, `toc-updater.md`, `toc_format.md`, `toc_format_compact.md`, `toc_update_workflow.md`

---
## [4.1.0] - 2026-03-01

### Added
- **`import_doc_structure.py`**: New script that imports `.doc_structure.yaml` into `config.yaml` at setup time (Route A in DES-005)
- **Setup-time config import**: `setup.sh` now calls `import_doc_structure.py` to populate `root_dirs` and `doc_types_map` during installation
- **Test coverage**: Expanded `test_setup_upgrade.sh` with comprehensive import and upgrade scenario tests

### Changed
- **Document directory configuration**: Moved from runtime `.doc_structure.yaml` derivation to setup-time import into `config.yaml`
- **`toc_utils.py`**: Removed runtime `.doc_structure.yaml` parsing; now reads only from `config.yaml`
- **`check_config.sh`**: Updated validation for new setup-time configuration approach
- **Header comments**: Renamed "subagent" terminology to "query-rules/query-specs skill" in `config.yaml` template
- **Design docs**: Updated DES-001, DES-005 to reflect setup-time import architecture
- **Version identifier**: Updated from `4.0` to `4.1` across all managed files

### Fixed
- **Code quality**: Various improvements from `/simplify` review (classify_dirs.py, check_config.sh, toc_utils.py)
- **Silent failure patterns**: Replaced in `test_write_pending.sh` and `test_merge.sh` with explicit failure handling
---

## [4.0.0] - 2026-02-25

### Added

- **`/classify-docs` skill**: AI-driven directory classification using `classify_dirs.py` scanner and `classification_rules.md`; replaces `setup_dirs.sh`
- **Skill Pre-check**: `check_config.sh` called at the start of each skill (create-_-toc, query-_) to detect unconfigured directories and trigger `/classify-docs` first
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

| Feature               | v1.x            | v2.0                         | v3.0                             | v3.1                                     | v3.2                                     |
| --------------------- | --------------- | ---------------------------- | -------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Installation          | Plugin mode     | Project-based                | Project-based                    | Project-based                            | Project-based                            |
| Commands              | `/create-*_toc` | `/create-*_toc`              | `/doc-advisor make-*-toc`        | `/create-rules-toc`, `/create-specs-toc` | `/create-rules-toc`, `/create-specs-toc` |
| Config location       | Plugin dir      | `.claude/doc-advisor/`       | `.claude/doc-advisor/`           | `.claude/doc-advisor/`                   | `.claude/doc-advisor/`                   |
| Docs/Scripts location | Plugin dir      | `.claude/doc-advisor/`       | `.claude/doc-advisor/`           | `.claude/doc-advisor/`                   | `.claude/doc-advisor/`                   |
| ToC output location   | Plugin dir      | `.claude/doc-advisor/rules/` | `.claude/doc-advisor/toc/rules/` | `.claude/doc-advisor/toc/rules/`         | `.claude/doc-advisor/toc/rules/`         |
| Auto-trigger          | No              | No                           | Yes                              | Yes                                      | Yes                                      |
| Parallel processing   | No              | Yes                          | Yes                              | Yes                                      | Yes                                      |
| Incremental updates   | No              | Yes                          | Yes                              | Yes                                      | Yes                                      |
| Custom directories    | No              | Yes                          | Yes                              | Yes                                      | Yes                                      |
| Upgrade support       | -               | -                            | Yes                              | Yes                                      | Yes                                      |
| Symlink support       | No              | No                           | No                               | No                                       | Yes                                      |

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
