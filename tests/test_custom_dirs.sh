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
# Format: agent_model (setup.sh now only asks for model name)
echo "sonnet" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

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
echo "Test 3-2: Verify .doc_structure.yaml and config.yaml"
echo "=================================================="

CONFIG_FILE=".claude/doc-advisor/config.yaml"
DOC_STRUCTURE=".doc_structure.yaml"

if [[ -f "$DOC_STRUCTURE" ]]; then
    # Check .doc_structure.yaml has custom paths
    if grep -q "guidelines" "$DOC_STRUCTURE"; then
        echo -e "${GREEN}PASS${NC}: .doc_structure.yaml has 'guidelines' path"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: .doc_structure.yaml missing 'guidelines' path"
        ((FAIL_COUNT++))
    fi

    if grep -q "documents" "$DOC_STRUCTURE"; then
        echo -e "${GREEN}PASS${NC}: .doc_structure.yaml has 'documents' path"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: .doc_structure.yaml missing 'documents' path"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: .doc_structure.yaml not found"
    ((FAIL_COUNT++))
fi

if [[ -f "$CONFIG_FILE" ]]; then
    # Check target_glob is set
    if grep -q 'target_glob:' "$CONFIG_FILE"; then
        echo -e "${GREEN}PASS${NC}: target_glob is configured"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: target_glob not found in config"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: config.yaml not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3-3: Run create_pending_yaml rules with custom dir"
echo "=================================================="

# Get Python path from orchestrator docs
PYTHON_CMD=python3
echo "Using Python: $PYTHON_CMD"

EXIT_CODE=0
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --target rules --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml rules (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Rules pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name
    if grep -q "source_file: guidelines/" .claude/doc-advisor/toc/rules/.toc_work/*.yaml; then
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
echo "Test 3-4: Run create_pending_yaml specs with custom dirs"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --target specs --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml specs (custom)" "0" "$EXIT_CODE"

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/specs/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Specs pending YAML created"
    ((PASS_COUNT++))

    # Verify source_file path uses custom dir name
    if grep -q "source_file: documents/" .claude/doc-advisor/toc/specs/.toc_work/*.yaml; then
        echo -e "${GREEN}PASS${NC}: source_file uses 'documents/' prefix"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: source_file does not use 'documents/' prefix"
        ((FAIL_COUNT++))
    fi

    # Verify doc_type is present in _meta section
    if grep -q "doc_type:" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: doc_type field present in pending YAML"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: doc_type field missing in pending YAML"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: No specs pending YAML created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3-5: Verify exclude with config pattern"
echo "=================================================="

# Create a directory that we will exclude via config
mkdir -p documents/archive
echo "# Archived Doc" > documents/archive/old_doc.md

# Add exclude pattern to config (replace inline empty array with multi-line format)
$PYTHON_CMD -c "
content = open('.claude/doc-advisor/config.yaml').read()
content = content.replace('    exclude: []    # Additional excludes (merged with .doc_structure.yaml)', '    exclude:\n      - archive')
open('.claude/doc-advisor/config.yaml', 'w').write(content)
"

# Regenerate
rm -rf .claude/doc-advisor/toc/specs/.toc_work
$PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --target specs --full 2>/dev/null || true

# Check that archive files are NOT included
if ls .claude/doc-advisor/toc/specs/.toc_work/*archive*.yaml 1>/dev/null 2>&1; then
    echo -e "${RED}FAIL${NC}: archive/ files should be excluded"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: archive/ files correctly excluded"
    ((PASS_COUNT++))
fi

# Cleanup
rm -rf documents/archive
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
