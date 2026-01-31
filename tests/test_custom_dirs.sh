#!/bin/bash
# Test script for custom directory names
# Usage: ./test_custom_dirs.sh

# Note: Do not use 'set -e' as some tests expect failures

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project_custom"

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
echo "Custom Directory Names Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Check test project exists
if [[ ! -d "$TEST_PROJECT/guidelines" ]]; then
    echo -e "${RED}ERROR: test_project_custom/guidelines not found${NC}"
    exit 1
fi

if [[ ! -d "$TEST_PROJECT/documents" ]]; then
    echo -e "${RED}ERROR: test_project_custom/documents not found${NC}"
    exit 1
fi

cd "$TEST_PROJECT"

echo "=================================================="
echo "Test 3-1: Setup with custom directory names"
echo "=================================================="

# Clean previous setup
rm -rf .claude .last_setup

# Run setup with custom values
# Format: rules_dir, specs_dir, requirement_dir_name, design_dir_name, plan_dir_name
echo -e "guidelines\ndocuments\nreqs\narch\nroadmap" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

# Verify .claude directory created
if [[ -d ".claude" ]]; then
    echo -e "${GREEN}PASS${NC}: .claude directory created"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: .claude directory not created"
    ((FAIL_COUNT++))
    exit 1
fi
echo ""

echo "=================================================="
echo "Test 3-2: Verify config.yaml has custom values"
echo "=================================================="

CONFIG_FILE=".claude/doc-advisor/config.yaml"

if [[ -f "$CONFIG_FILE" ]]; then
    # Check rules_dir
    if grep -q "root_dir: guidelines" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: rules root_dir is 'guidelines'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: rules root_dir not set to 'guidelines'"
        ((FAIL_COUNT++))
    fi

    # Check specs_dir
    if grep -q "root_dir: documents" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: specs root_dir is 'documents'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: specs root_dir not set to 'documents'"
        ((FAIL_COUNT++))
    fi

    # Check target_dirs
    if grep -q "requirement: reqs" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: requirement dir is 'reqs'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: requirement dir not set to 'reqs'"
        ((FAIL_COUNT++))
    fi

    if grep -q "design: arch" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: design dir is 'arch'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: design dir not set to 'arch'"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: config.yaml not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3-3: Run create_pending_yaml_rules.py with custom dir"
echo "=================================================="

# Get Python path
PYTHON_CMD=$(grep -o '/[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
echo "Using Python: $PYTHON_CMD"

EXIT_CODE=0
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_rules (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Rules pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name
    if grep -q "source_file: guidelines/" .claude/doc-advisor/rules/.toc_work/*.yaml; then
        echo -e "${GREEN}PASS${NC}: source_file uses 'guidelines/' prefix"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: source_file does not use 'guidelines/' prefix"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: No rules pending YAML created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3-4: Run create_pending_yaml_specs.py with custom dirs"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_specs (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/specs/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Specs pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name
    if grep -q "source_file: documents/" .claude/doc-advisor/specs/.toc_work/*.yaml; then
        echo -e "${GREEN}PASS${NC}: source_file uses 'documents/' prefix"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: source_file does not use 'documents/' prefix"
        ((FAIL_COUNT++))
    fi

    # Verify doc_type is correctly detected with custom dir names
    # reqs/ should map to requirement
    if grep -q "doc_type: requirement" .claude/doc-advisor/specs/.toc_work/*reqs*.yaml 2>/dev/null || \
       grep -q "doc_type: requirement" .claude/doc-advisor/specs/.toc_work/*auth*.yaml 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: doc_type 'requirement' detected for reqs/"
        ((PASS_COUNT++))
    else
        echo -e "${YELLOW}WARN${NC}: Could not verify requirement doc_type"
    fi

    # arch/ should map to design
    if grep -q "doc_type: design" .claude/doc-advisor/specs/.toc_work/*arch*.yaml 2>/dev/null || \
       grep -q "doc_type: design" .claude/doc-advisor/specs/.toc_work/*api*.yaml 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: doc_type 'design' detected for arch/"
        ((PASS_COUNT++))
    else
        echo -e "${YELLOW}WARN${NC}: Could not verify design doc_type"
    fi
else
    echo -e "${RED}FAIL${NC}: No specs pending YAML created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3-5: Verify exclude with custom plan dir name"
echo "=================================================="

# Create a plan file that should be excluded
mkdir -p documents/main/roadmap
echo "# Test Roadmap" > documents/main/roadmap/test_plan.md

# Regenerate
$PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || true

# Check that roadmap files are NOT included
if ls .claude/doc-advisor/specs/.toc_work/*roadmap*.yaml 1>/dev/null 2>&1; then
    echo -e "${RED}FAIL${NC}: roadmap/ files should be excluded"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: roadmap/ files correctly excluded"
    ((PASS_COUNT++))
fi

# Cleanup
rm -rf documents/main/roadmap
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
