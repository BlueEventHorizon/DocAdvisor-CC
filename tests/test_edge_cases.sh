#!/bin/bash
# Test script for edge cases
# Usage: ./test_edge_cases.sh

# Note: Do not use 'set -e' as some tests expect failures

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project_edge"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

# Test result helper
test_result() {
    local name="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$expected" == "$actual" ]]; then
        echo -e "${GREEN}PASS${NC}: $name (expected=$expected, actual=$actual)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $name (expected=$expected, actual=$actual)"
        ((FAIL_COUNT++))
    fi
}

echo "=================================================="
echo "Edge Cases Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Check test project exists
if [[ ! -d "$TEST_PROJECT/rules" ]]; then
    echo -e "${RED}ERROR: test_project_edge/rules not found${NC}"
    exit 1
fi

cd "$TEST_PROJECT"

echo "=================================================="
echo "Setup test project"
echo "=================================================="

# Clean previous setup
rm -rf .claude .last_setup

# Run setup with explicit values: rules, specs, requirements, design, plan
echo -e "rules\nspecs\nrequirements\ndesign\nplan" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

if [[ ! -d ".claude" ]]; then
    echo -e "${RED}ERROR: Setup failed${NC}"
    exit 1
fi

# Get Python path
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"
echo ""

SCRIPTS_DIR="$TEST_PROJECT/.claude/skills/doc-advisor/scripts"

echo "=================================================="
echo "Test 4-1: Deep nested files (5 levels)"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_rules (deep)" "0" "$EXIT_CODE"

# Check if deep file was found
if ls .claude/doc-advisor/rules/.toc_work/*deep*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Deep nested file found"
    ((PASS_COUNT++))

    # Verify path is correct
    if grep -q "source_file: rules/a/b/c/d/e/deep_rule.md" .claude/doc-advisor/rules/.toc_work/*deep*.yaml; then
        echo -e "${GREEN}PASS${NC}: Deep path correctly captured"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Deep path not correctly captured"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: Deep nested file not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 4-2: Japanese filename"
echo "=================================================="

# Check if Japanese filename was found
if ls .claude/doc-advisor/rules/.toc_work/*日本語*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Japanese filename found"
    ((PASS_COUNT++))

    # Verify path is correct
    if grep -q "日本語" .claude/doc-advisor/rules/.toc_work/*日本語*.yaml; then
        echo -e "${GREEN}PASS${NC}: Japanese characters in YAML"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Japanese characters not in YAML"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: Japanese filename not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 4-3: Empty directory handling"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_specs.py" --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_specs (empty dir)" "0" "$EXIT_CODE"

# design/ is empty (only .gitkeep), should not create YAML for .gitkeep
if ls .claude/doc-advisor/specs/.toc_work/*gitkeep*.yaml 1>/dev/null 2>&1; then
    echo -e "${RED}FAIL${NC}: .gitkeep should not create YAML"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: .gitkeep correctly ignored"
    ((PASS_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 4-4: Special characters in content"
echo "=================================================="

# Check if special_chars file was processed
if ls .claude/doc-advisor/specs/.toc_work/*special*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Special chars file processed"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Special chars file not processed"
    ((FAIL_COUNT++))
fi

# Test write_specs_pending with special characters
SPECS_PENDING=$(ls .claude/doc-advisor/specs/.toc_work/*special*.yaml 2>/dev/null | head -1 || echo "")

if [[ -n "$SPECS_PENDING" ]]; then
    EXIT_CODE=0
    $PYTHON_CMD "$SCRIPTS_DIR/write_specs_pending.py" \
        --entry-file "$SPECS_PENDING" \
        --title "Special: \"quotes\" & ampersand" \
        --purpose "Test YAML escaping for special characters" \
        --content-details "Single 'quotes',Double \"quotes\",Ampersand &,Colon: value,Pipe | char" \
        --applicable-tasks "YAML escaping test" \
        --keywords "special,chars,yaml,escape,test" \
        --force \
        2>/dev/null || EXIT_CODE=$?

    test_result "write_specs_pending (special chars)" "0" "$EXIT_CODE"

    # Verify YAML is valid (can be parsed)
    if $PYTHON_CMD -c "
import sys
sys.path.insert(0, '$SCRIPTS_DIR')
from toc_utils import load_entry_file
try:
    load_entry_file('$SPECS_PENDING')
    print('YAML valid')
    sys.exit(0)
except Exception as e:
    print(f'YAML invalid: {e}')
    sys.exit(1)
" 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: YAML with special chars is valid"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: YAML with special chars is invalid"
        ((FAIL_COUNT++))
    fi
fi
echo ""

echo "=================================================="
echo "Test 4-5: File count verification"
echo "=================================================="

# Count rules pending files
RULES_COUNT=$(ls -1 .claude/doc-advisor/rules/.toc_work/*.yaml 2>/dev/null | wc -l | tr -d ' ')
echo "Rules pending files: $RULES_COUNT"

# Should have 2 files: deep_rule.md and 日本語ルール.md
if [[ "$RULES_COUNT" -eq 2 ]]; then
    echo -e "${GREEN}PASS${NC}: Correct number of rules files ($RULES_COUNT)"
    ((PASS_COUNT++))
else
    echo -e "${YELLOW}WARN${NC}: Expected 2 rules files, got $RULES_COUNT"
fi

# Count specs pending files
SPECS_COUNT=$(ls -1 .claude/doc-advisor/specs/.toc_work/*.yaml 2>/dev/null | wc -l | tr -d ' ')
echo "Specs pending files: $SPECS_COUNT"

# Should have 1 file: special_chars.md (design/ is empty)
if [[ "$SPECS_COUNT" -eq 1 ]]; then
    echo -e "${GREEN}PASS${NC}: Correct number of specs files ($SPECS_COUNT)"
    ((PASS_COUNT++))
else
    echo -e "${YELLOW}WARN${NC}: Expected 1 specs file, got $SPECS_COUNT"
fi
echo ""

echo "=================================================="
echo "Summary"
echo "=================================================="
echo ""
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
