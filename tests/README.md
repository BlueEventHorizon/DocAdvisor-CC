# DocAdvisor-CC Test Suite

This directory contains tests for DocAdvisor-CC setup and scripts.

## Directory Structure

```
tests/
├── run_all_tests.sh           # Run all test suites
├── test.sh                    # Phase 1: Basic setup test
├── test_write_pending.sh      # Phase 2a: write_pending.py tests
├── test_merge.sh              # Phase 2b: merge_toc.py tests
├── test_checksums.sh          # Phase 2c: create_checksums.py tests
├── test_should_exclude.sh     # Phase 2d: should_exclude() tests
├── test_symlink.sh            # Phase 2e: Symlink support tests
├── test_custom_dirs.sh        # Phase 3: Custom directory names
├── test_edge_cases.sh         # Phase 4: Edge cases
├── test_setup_upgrade.sh      # Phase 5: Setup upgrade scenarios
├── test_project/              # Default config test project
│   ├── rules/
│   │   └── coding_standards.md
│   └── specs/
│       └── main/
│           ├── requirements/
│           │   └── user_authentication.md
│           └── design/
│               └── authentication_api.md
├── test_project_custom/       # Custom directory names project
│   ├── guidelines/            # Instead of "rules"
│   │   └── coding.md
│   └── documents/             # Instead of "specs"
│       └── main/
│           ├── reqs/          # Instead of "requirements"
│           │   └── auth.md
│           └── arch/          # Instead of "design"
│               └── api.md
├── test_project_edge/         # Edge cases project
│   ├── rules/
│   │   ├── a/b/c/d/e/deep_rule.md    # Deep nesting (5 levels)
│   │   └── 日本語ルール.md           # Japanese filename
│   └── specs/
│       └── main/
│           ├── requirements/
│           │   └── special_chars.md   # Special characters
│           └── design/
│               └── .gitkeep           # Empty directory
└── README.md
```

## Running Tests

### Prerequisites

- Bash shell
- Python 3.x

### Important Note

**Tests must be run from a terminal, not through Claude Code.**

Claude Code has sandbox restrictions that prevent `setup.sh` from writing files. Run the tests manually from your terminal.

### Run All Tests

```bash
cd tests
chmod +x *.sh
./run_all_tests.sh
```

### Run Individual Test Suites

```bash
# Phase 1: Basic setup
./test.sh

# Phase 2: Script unit tests
./test_write_pending.sh
./test_merge.sh
./test_checksums.sh
./test_should_exclude.sh
./test_symlink.sh

# Phase 3: Custom directory names
./test_custom_dirs.sh

# Phase 4: Edge cases
./test_edge_cases.sh

# Phase 5: Setup upgrade scenarios
./test_setup_upgrade.sh
```

### Clean Up Test Environment

```bash
./test.sh --clean
```

## Test Coverage

### Phase 1: Basic Setup

| Test | Description |
|------|-------------|
| 1-1 | setup.sh execution |
| 1-2 | `{{PYTHON_PATH}}` substitution |
| 1-3 | `{{RULES_DIR}}` substitution |
| 1-4 | create_pending_yaml_rules.py --full |
| 1-5 | create_pending_yaml_specs.py --full |

### Phase 2a: write_pending.py

| Test | Description |
|------|-------------|
| 2-1 | Normal case (all args) |
| 2-2 | Missing arguments |
| 2-3 | Insufficient keywords |
| 2-4 | doc_type preservation (specs) |

### Phase 2b: merge_toc.py

| Test | Description |
|------|-------------|
| 2-5 | Full mode |
| 2-6 | Incremental mode |
| 2-7 | Cleanup after merge |
| 2-8 | --delete-only mode |
| 2-9 | Checksum integration |

### Phase 2c: create_checksums.py

| Test | Description |
|------|-------------|
| 2-10 | Hash generation |

### Phase 2d: should_exclude()

| Test | Description |
|------|-------------|
| 2-11 | Exclude pattern matching |

### Phase 2e: Symlink Support

| Test | Description |
|------|-------------|
| 2-12 | create_checksums.py with symlinks (rules) |
| 2-13 | create_checksums.py with symlinks (specs) |
| 2-14 | create_pending_yaml.py with symlinks (rules) |
| 2-15 | create_pending_yaml.py with symlinks (specs) |
| 2-16 | Symlink loop detection |
| 2-17 | Duplicate file detection via multiple symlinks |

### Phase 3: Custom Directory Names

| Test | Description |
|------|-------------|
| 3-1 | Setup with custom directory names |
| 3-2 | config.yaml contains custom values |
| 3-3 | rules scanning with custom dir |
| 3-4 | specs scanning with custom dirs |
| 3-5 | exclude with custom plan dir name |

### Phase 4: Edge Cases

| Test | Description |
|------|-------------|
| 4-1 | Deep nested files (5 levels) |
| 4-2 | Japanese filename |
| 4-3 | Empty directory handling |
| 4-4 | Special characters in content |
| 4-5 | File count verification |

### Phase 5: Setup Upgrade

| Test | Description |
|------|-------------|
| 1 | Clean install (no existing .claude) |
| 2 | Legacy commands/ auto-deleted (file-specific) |
| 3 | v3.2 structure verification (split skills) |
| 4 | config.yaml skip (preserve existing) |
| 5 | config.yaml overwrite with backup |
| 6 | v3.0 skills/doc-advisor/ removed on upgrade to v3.1 |
| 7 | agents/ custom agent preserved |
| 8 | Repeated setup preserves toc/ directory structure |
| 9 | Version-based protection (current version protected) |
| 10 | Old version deleted, current version protected |
| 11 | Advisor agent deletion (T-008) |
| 12 | query-* skill installation (T-009) |
| 13 | setup-config skill installed |
| 14 | v3.8 unified scripts (old scripts removed) |
| 15 | v3.8 unified agents (old agents removed) |
| 16 | config.yaml root_dirs imported from .doc_structure.yaml |
| 16b | import_doc_structure.py - multiple doc_types and paths |
| 16c | import_doc_structure.py - no .doc_structure.yaml |
| 16d | import_doc_structure.py - rules only |
| 17 | classify_dirs.py installed from template |
| 18 | v3.9 set_root_dirs.py legacy cleanup |
| 19 | config.yaml root_dirs manual override |
| 20 | config.yaml exclude patterns (empty defaults) |
| 21 | No skip/exclude (empty input) |
| 22 | v3.9 full legacy cleanup (all removed files) |
| 23 | check_config.sh installed with exec permission (T-011) |
| 24 | Skill Pre-check sections (T-012) |
| 25 | check_config.sh behavior (FR-08) incl. specs & cross-category |
| 26 | config.yaml merge option (REQ-002-03 [m]) |
| 27 | validate_rules_toc.py abnormal input handling |

## Adding New Tests

To add new tests, create a new test script following the pattern:

```bash
#!/bin/bash
# Test script for [feature]
# Usage: ./test_[feature].sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

# Test helper
test_result() {
    local name="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$expected" == "$actual" ]]; then
        echo -e "${GREEN}PASS${NC}: $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $name (expected=$expected, actual=$actual)"
        ((FAIL_COUNT++))
    fi
}

# Your tests here...

# Summary
echo ""
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"

[[ $FAIL_COUNT -eq 0 ]] && exit 0 || exit 1
```

## Troubleshooting

### PYTHON_PATH not found

If the test fails with "PYTHON_PATH not substituted", check:

1. `setup.sh` correctly detects Python path
2. The sed substitution includes `{{PYTHON_PATH}}`

### Script execution fails

If Python scripts fail to execute:

1. Check the detected Python path is valid
2. Verify Python 3 is installed
3. Check for sandbox restrictions (safe-chain, etc.)

### Japanese filename issues

If Japanese filenames cause errors:

1. Ensure your terminal supports UTF-8
2. Check file system encoding
3. Verify `LC_ALL` and `LANG` environment variables
