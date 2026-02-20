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
# Format: rules_dir, specs_dir, requirement_dir_name, design_dir_name, plan_dir_name, agent_model
echo -e "guidelines\ndocuments\nreqs\narch\nroadmap\nsonnet" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

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
    # root_dir is now fixed in the new architecture
    # Check that rules root_dir points to docs/rules
    if grep -q "root_dir: .claude/doc-advisor/docs/rules" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: rules root_dir is '.claude/doc-advisor/docs/rules'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: rules root_dir not set correctly"
        ((FAIL_COUNT++))
    fi

    # Check that specs root_dir points to docs
    if grep -q "root_dir: .claude/doc-advisor/docs$" "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: specs root_dir is '.claude/doc-advisor/docs'"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: specs root_dir not set correctly"
        ((FAIL_COUNT++))
    fi

    # Check custom target_dirs
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
echo "Test 3-2b: Verify symlinks use custom names"
echo "=================================================="

# Check that symlinks were created with custom directory names
if [[ -L ".claude/doc-advisor/docs/rules/guidelines" ]]; then
    echo -e "${GREEN}PASS${NC}: rules symlink uses 'guidelines' name"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: rules symlink 'guidelines' not found"
    ((FAIL_COUNT++))
    echo "  Contents of docs/rules/:"
    ls -la .claude/doc-advisor/docs/rules/ 2>/dev/null
fi

if [[ -L ".claude/doc-advisor/docs/reqs/documents" ]]; then
    echo -e "${GREEN}PASS${NC}: requirements symlink uses 'documents' name"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: requirements symlink 'documents' not found"
    ((FAIL_COUNT++))
    echo "  Contents of docs/reqs/:"
    ls -la .claude/doc-advisor/docs/reqs/ 2>/dev/null
fi

if [[ -L ".claude/doc-advisor/docs/arch/documents" ]]; then
    echo -e "${GREEN}PASS${NC}: design symlink uses 'documents' name"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: design symlink 'documents' not found"
    ((FAIL_COUNT++))
    echo "  Contents of docs/arch/:"
    ls -la .claude/doc-advisor/docs/arch/ 2>/dev/null
fi
echo ""

echo "=================================================="
echo "Test 3-3: Run create_pending_yaml_rules.py with custom dir"
echo "=================================================="

# Get Python path from orchestrator docs
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/rules_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"

EXIT_CODE=0
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml_rules.py --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_rules (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Rules pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name in docs path
    if grep -q "source_file: .claude/doc-advisor/docs/rules/guidelines/" .claude/doc-advisor/toc/rules/.toc_work/*.yaml; then
        echo -e "${GREEN}PASS${NC}: source_file uses 'guidelines/' in path"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: source_file does not use 'guidelines/' in path"
        ((FAIL_COUNT++))
        echo "  Actual source_file values:"
        grep "source_file:" .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null
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
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_specs (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/specs/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Specs pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name
    if grep -q "source_file: .claude/doc-advisor/docs/" .claude/doc-advisor/toc/specs/.toc_work/*.yaml; then
        echo -e "${GREEN}PASS${NC}: source_file uses docs/ prefix"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: source_file does not use docs/ prefix"
        ((FAIL_COUNT++))
        echo "  Actual source_file values:"
        grep "source_file:" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null
    fi

    # Verify doc_type is correctly detected with custom dir names
    # reqs/ should map to requirement
    if grep -q "doc_type: requirement" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: doc_type 'requirement' detected for reqs/"
        ((PASS_COUNT++))
    else
        echo -e "${YELLOW}WARN${NC}: Could not verify requirement doc_type"
    fi

    # arch/ should map to design
    if grep -q "doc_type: design" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null; then
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
mkdir -p .claude/doc-advisor/docs/roadmap
echo "# Test Roadmap" > .claude/doc-advisor/docs/roadmap/test_plan.md

# Regenerate
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml_specs.py --full 2>/dev/null || true

# Check that roadmap files are NOT included (search by content)
if grep -rl "roadmap/test_plan.md" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null | head -1 | grep -q .; then
    echo -e "${RED}FAIL${NC}: roadmap/ files should be excluded"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: roadmap/ files correctly excluded"
    ((PASS_COUNT++))
fi

# Cleanup
rm -rf .claude/doc-advisor/docs/roadmap
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
