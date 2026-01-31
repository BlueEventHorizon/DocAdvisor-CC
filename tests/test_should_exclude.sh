#!/bin/bash
# Test script for should_exclude function
# Usage: ./test_should_exclude.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "should_exclude() Unit Test Suite"
echo "=================================================="
echo ""

# Test counters
PASS_COUNT=0
FAIL_COUNT=0

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

# Setup test project
cd "$TEST_PROJECT"

# Get Python path
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"
echo ""

# Create a test Python script
TEST_SCRIPT=$(cat << 'PYTHON_EOF'
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path('.claude/skills/doc-advisor/scripts').resolve()))

from toc_utils import should_exclude

def test_should_exclude():
    """Test should_exclude function"""
    root_dir = Path('/project/specs')

    tests = [
        # (filepath, exclude_patterns, expected_result, description)

        # Basic directory exclusion
        (Path('/project/specs/plan/roadmap.md'), ['plan'], True,
         "plan directory should be excluded"),
        (Path('/project/specs/main/plan/item.md'), ['plan'], True,
         "nested plan directory should be excluded"),

        # Should NOT exclude files with 'plan' in name
        (Path('/project/specs/main/requirements/planning.md'), ['plan'], False,
         "planning.md should NOT be excluded by 'plan' pattern"),
        (Path('/project/specs/main/design/deployment_plan.md'), ['plan'], False,
         "deployment_plan.md should NOT be excluded by 'plan' pattern"),
        (Path('/project/specs/main/requirements/project_plan_v2.md'), ['plan'], False,
         "project_plan_v2.md should NOT be excluded by 'plan' pattern"),

        # Pattern with slash (partial match, leading/trailing / stripped)
        (Path('/project/specs/archive/old/doc.md'), ['/archive/'], True,
         "path containing /archive/ should be excluded"),
        (Path('/project/specs/main/requirements/archived.md'), ['/archive/'], False,
         "archived.md should NOT be excluded by '/archive/' pattern"),

        # Multiple patterns
        (Path('/project/specs/plan/item.md'), ['plan', 'draft'], True,
         "file in plan dir with multiple patterns"),
        (Path('/project/specs/draft/item.md'), ['plan', 'draft'], True,
         "file in draft dir with multiple patterns"),
        (Path('/project/specs/main/requirements/auth.md'), ['plan', 'draft'], False,
         "normal file should not be excluded"),

        # Empty patterns
        (Path('/project/specs/main/requirements/auth.md'), [], False,
         "empty patterns should exclude nothing"),

        # Deep nesting
        (Path('/project/specs/a/b/c/plan/d/file.md'), ['plan'], True,
         "deeply nested plan directory"),
        (Path('/project/specs/a/b/c/planning/d/file.md'), ['plan'], False,
         "deeply nested planning directory should NOT match 'plan'"),
    ]

    results = []
    for filepath, patterns, expected, desc in tests:
        actual = should_exclude(filepath, root_dir, patterns)
        status = "PASS" if actual == expected else "FAIL"
        results.append((status, desc, expected, actual))

    return results

if __name__ == '__main__':
    results = test_should_exclude()
    for status, desc, expected, actual in results:
        print(f"{status}|{desc}|{expected}|{actual}")
PYTHON_EOF
)

# Run Python tests
echo "=================================================="
echo "Test: should_exclude directory matching"
echo "=================================================="
echo ""

RESULT=$($PYTHON_CMD -c "$TEST_SCRIPT" 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo -e "${RED}FAIL${NC}: Python script execution failed"
    echo "$RESULT"
    ((FAIL_COUNT++))
else
    # Parse results
    while IFS='|' read -r status desc expected actual; do
        if [[ "$status" == "PASS" ]]; then
            echo -e "${GREEN}PASS${NC}: $desc"
            ((PASS_COUNT++))
        else
            echo -e "${RED}FAIL${NC}: $desc (expected=$expected, actual=$actual)"
            ((FAIL_COUNT++))
        fi
    done <<< "$RESULT"
fi

echo ""
echo "=================================================="
echo "Summary"
echo "=================================================="
echo ""
echo -e "Passed: ${GREEN}${PASS_COUNT}${NC}"
echo -e "Failed: ${RED}${FAIL_COUNT}${NC}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
