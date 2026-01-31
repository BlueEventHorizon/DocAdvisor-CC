#!/bin/bash
# Test script for write_rules_pending.py and write_specs_pending.py
# Usage: ./test_write_pending.sh

# Note: Do not use 'set -e' as some tests expect failures

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

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
echo "write_pending.py Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Ensure test project is set up with correct settings
echo "Setting up test project..."
cd "$TEST_PROJECT"
rm -rf .claude .last_setup
# Pass explicit values: rules, specs, requirements, design, plan
echo -e "rules\nspecs\nrequirements\ndesign\nplan" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path
PYTHON_CMD=$(grep -o '/[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
echo "Using Python: $PYTHON_CMD"
echo ""

# Ensure pending YAML exists
echo "Generating pending YAML files..."
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || true
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || true
echo ""

RULES_PENDING=$(ls .claude/doc-advisor/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
SPECS_PENDING=$(ls .claude/doc-advisor/specs/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")

if [[ -z "$RULES_PENDING" ]]; then
    echo -e "${RED}ERROR: No rules pending YAML found${NC}"
    exit 1
fi

if [[ -z "$SPECS_PENDING" ]]; then
    echo -e "${RED}ERROR: No specs pending YAML found${NC}"
    exit 1
fi

echo "Rules pending: $RULES_PENDING"
echo "Specs pending: $SPECS_PENDING"
echo ""

WRITE_RULES="$TEST_PROJECT/.claude/skills/doc-advisor/scripts/write_rules_pending.py"
WRITE_SPECS="$TEST_PROJECT/.claude/skills/doc-advisor/scripts/write_specs_pending.py"

echo "=================================================="
echo "Test 2-1: write_rules_pending.py - Normal case"
echo "=================================================="

# Reset pending file first
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" \
    --entry-file "$RULES_PENDING" \
    --title "Coding Standards" \
    --purpose "Define consistent coding practices for the team" \
    --content-details "Naming conventions,Code structure,Error handling,Testing guidelines,Documentation requirements" \
    --applicable-tasks "Code review,New development" \
    --keywords "coding,standards,naming,structure,testing" \
    --force \
    || EXIT_CODE=$?

test_result "write_rules_pending normal" "0" "$EXIT_CODE"

# Verify status changed to completed
if grep -q "status: completed" "$RULES_PENDING"; then
    echo -e "${GREEN}PASS${NC}: status changed to completed"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: status not changed to completed"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-2: write_rules_pending.py - Missing argument"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" \
    --entry-file "$RULES_PENDING" \
    --title "Test" \
    2>/dev/null || EXIT_CODE=$?

# Missing required arguments should cause argparse error (exit code 2)
if [[ "$EXIT_CODE" -ne 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Missing arguments detected (exit=$EXIT_CODE)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Should have failed with missing arguments"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-3: write_rules_pending.py - Insufficient keywords"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" \
    --entry-file "$RULES_PENDING" \
    --title "Test" \
    --purpose "Test purpose" \
    --content-details "a,b,c,d,e" \
    --applicable-tasks "task1" \
    --keywords "one,two" \
    2>/dev/null || EXIT_CODE=$?

test_result "write_rules_pending insufficient keywords" "3" "$EXIT_CODE"
echo ""

echo "=================================================="
echo "Test 2-4: write_specs_pending.py - Normal case with doc_type"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_SPECS" \
    --entry-file "$SPECS_PENDING" \
    --title "User Authentication Requirements" \
    --purpose "Define requirements for user authentication" \
    --content-details "User login,Registration,Password reset,Session management,Security requirements" \
    --applicable-tasks "Auth implementation" \
    --keywords "auth,login,security,password,session" \
    --force \
    || EXIT_CODE=$?

test_result "write_specs_pending normal" "0" "$EXIT_CODE"

# Verify doc_type is preserved
if grep -q "doc_type:" "$SPECS_PENDING"; then
    echo -e "${GREEN}PASS${NC}: doc_type field preserved"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: doc_type field not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-5: write_rules_pending.py - File not found"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" \
    --entry-file "/nonexistent/path/file.yaml" \
    --title "Test" \
    --purpose "Test purpose" \
    --content-details "a,b,c,d,e" \
    --applicable-tasks "task1" \
    --keywords "a,b,c,d,e" \
    2>/dev/null || EXIT_CODE=$?

test_result "write_rules_pending file not found" "1" "$EXIT_CODE"
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
