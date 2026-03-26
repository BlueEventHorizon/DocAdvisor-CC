#!/bin/bash
# Test script for write_pending.py (rules and specs targets)
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
# Pass explicit values: rules, specs, agent_model
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path from orchestrator docs
PYTHON_CMD=python3
echo "Using Python: $PYTHON_CMD"

echo ""

# Ensure pending YAML exists
echo "Generating pending YAML files..."
if ! $PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category rules --full 2>/dev/null; then
    echo -e "${RED}ERROR: create_pending_yaml.py --category rules failed${NC}"
    exit 1
fi
if ! $PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category specs --full 2>/dev/null; then
    echo -e "${RED}ERROR: create_pending_yaml.py --category specs failed${NC}"
    exit 1
fi
echo ""

RULES_PENDING=$(ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
SPECS_PENDING=$(ls .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")

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

WRITE_RULES="$TEST_PROJECT/.claude/doc-advisor/scripts/write_pending.py"
WRITE_SPECS="$TEST_PROJECT/.claude/doc-advisor/scripts/write_pending.py"

echo "=================================================="
echo "Test 2-1: write_pending rules - Normal case"
echo "=================================================="

# Reset pending file first
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category rules --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" --category rules \
    --entry-file "$RULES_PENDING" \
    --title "Coding Standards" \
    --purpose "Define consistent coding practices for the team" \
    --content-details "Naming conventions ||| Code structure ||| Error handling ||| Testing guidelines ||| Documentation requirements" \
    --applicable-tasks "Code review ||| New development" \
    --keywords "coding ||| standards ||| naming ||| structure ||| testing" \
    --force \
    || EXIT_CODE=$?

test_result "write_pending rules normal" "0" "$EXIT_CODE"

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
echo "Test 2-2: write_pending rules - Missing argument"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category rules --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" --category rules \
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
echo "Test 2-3: write_pending rules - Insufficient keywords"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category rules --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" --category rules \
    --entry-file "$RULES_PENDING" \
    --title "Test" \
    --purpose "Test purpose" \
    --content-details "a ||| b ||| c ||| d ||| e" \
    --applicable-tasks "task1" \
    --keywords "one ||| two" \
    2>/dev/null || EXIT_CODE=$?

test_result "write_pending rules insufficient keywords" "3" "$EXIT_CODE"
echo ""

echo "=================================================="
echo "Test 2-4: write_pending specs - Normal case"
echo "=================================================="

# Reset pending file
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category specs --full 2>/dev/null || true

EXIT_CODE=0
$PYTHON_CMD "$WRITE_SPECS" --category specs \
    --entry-file "$SPECS_PENDING" \
    --title "User Authentication Requirements" \
    --purpose "Define requirements for user authentication" \
    --content-details "User login ||| Registration ||| Password reset ||| Session management ||| Security requirements" \
    --applicable-tasks "Auth implementation" \
    --keywords "auth ||| login ||| security ||| password ||| session" \
    --force \
    || EXIT_CODE=$?

test_result "write_pending specs normal" "0" "$EXIT_CODE"

# Verify doc_type is present in completed entry
if grep -q "doc_type:" "$SPECS_PENDING"; then
    echo -e "${GREEN}PASS${NC}: doc_type field present in completed entry"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: doc_type field missing in completed entry"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-5: write_pending rules - File not found"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD "$WRITE_RULES" --category rules \
    --entry-file "/nonexistent/path/file.yaml" \
    --title "Test" \
    --purpose "Test purpose" \
    --content-details "a ||| b ||| c ||| d ||| e" \
    --applicable-tasks "task1" \
    --keywords "a ||| b ||| c ||| d ||| e" \
    2>/dev/null || EXIT_CODE=$?

test_result "write_pending rules file not found" "1" "$EXIT_CODE"
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
