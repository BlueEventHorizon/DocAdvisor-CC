# DocAdvisor-CC Test Suite

This directory contains tests for DocAdvisor-CC setup and scripts.

## Directory Structure

```
tests/
├── run_all_tests.sh           # Run all test suites
├── test.sh                    # Phase 1: Basic setup test
├── test_write_pending.sh      # Phase 2: write_*_pending.py tests
├── test_merge.sh              # Phase 2: merge_*_toc.py tests
├── test_checksums.sh          # Phase 2: create_checksums.py tests
├── test_custom_dirs.sh        # Phase 3: Custom directory names
├── test_edge_cases.sh         # Phase 4: Edge cases
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

# Phase 3: Custom directory names
./test_custom_dirs.sh

# Phase 4: Edge cases
./test_edge_cases.sh
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

### Phase 2: Script Unit Tests

| Test | Script | Description |
|------|--------|-------------|
| 2-1 | write_rules_pending.py | Normal case (all args) |
| 2-2 | write_rules_pending.py | Missing arguments |
| 2-3 | write_rules_pending.py | Insufficient keywords |
| 2-4 | write_specs_pending.py | doc_type preservation |
| 2-5 | merge_rules_toc.py | Full mode |
| 2-6 | merge_rules_toc.py | Incremental mode |
| 2-7 | create_checksums.py | Hash generation |

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
