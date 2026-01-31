#!/bin/bash
# Test script for DocAdvisor-CC setup and scripts
# Usage: ./test.sh [--clean]

# Note: Do not use 'set -e' as we want to continue even if some tests fail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "DocAdvisor-CC Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Clean option
if [[ "$1" == "--clean" ]]; then
    echo "Cleaning up test project..."
    rm -rf "$TEST_PROJECT/.claude"
    rm -rf "$TEST_PROJECT/.last_setup"
    echo "Done."
    exit 0
fi

# Change to test project directory
cd "$TEST_PROJECT"

echo "=================================================="
echo "Test 1: Run setup.sh"
echo "=================================================="
echo ""

# Clean previous setup
rm -rf .claude
rm -f .last_setup

# Run setup.sh with test project path
echo "Running setup.sh for test project..."
# Pass explicit values: rules, specs, requirements, design, plan
echo -e "rules\nspecs\nrequirements\ndesign\nplan" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

echo ""
echo -e "${GREEN}Setup completed.${NC}"
echo ""

echo "=================================================="
echo "Test 2: Verify variable substitution"
echo "=================================================="
echo ""

# Check PYTHON_PATH substitution
PYTHON_PATH_IN_FILE=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "NOT_FOUND")

if [[ "$PYTHON_PATH_IN_FILE" == "NOT_FOUND" ]] || [[ "$PYTHON_PATH_IN_FILE" == *"{{"* ]]; then
    echo -e "${RED}FAIL: PYTHON_PATH not substituted${NC}"
    echo "  Found: $PYTHON_PATH_IN_FILE"
    exit 1
else
    echo -e "${GREEN}PASS: PYTHON_PATH substituted${NC}"
    echo "  Value: $PYTHON_PATH_IN_FILE"
fi

# Check RULES_DIR substitution
if grep -q "{{RULES_DIR}}" .claude/commands/create-rules_toc.md 2>/dev/null; then
    echo -e "${RED}FAIL: RULES_DIR not substituted${NC}"
    exit 1
else
    echo -e "${GREEN}PASS: RULES_DIR substituted${NC}"
fi

echo ""

echo "=================================================="
echo "Test 3: Run create_pending_yaml_rules.py"
echo "=================================================="
echo ""

# Get Python path from the substituted file
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")

echo "Using Python: $PYTHON_CMD"
echo ""

# Run the script
if $PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_rules.py --full; then
    echo ""
    echo -e "${GREEN}PASS: create_pending_yaml_rules.py executed successfully${NC}"
else
    echo ""
    echo -e "${RED}FAIL: create_pending_yaml_rules.py failed${NC}"
    exit 1
fi

echo ""

# Check if pending YAML was created
if ls .claude/doc-advisor/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS: Pending YAML files created${NC}"
    ls -la .claude/doc-advisor/rules/.toc_work/
else
    echo -e "${YELLOW}WARN: No pending YAML files created (may be expected if no rules)${NC}"
fi

echo ""

echo "=================================================="
echo "Test 4: Run create_pending_yaml_specs.py"
echo "=================================================="
echo ""

if $PYTHON_CMD .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py --full; then
    echo ""
    echo -e "${GREEN}PASS: create_pending_yaml_specs.py executed successfully${NC}"
else
    echo ""
    echo -e "${RED}FAIL: create_pending_yaml_specs.py failed${NC}"
    exit 1
fi

echo ""

# Check if pending YAML was created
if ls .claude/doc-advisor/specs/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS: Pending YAML files created${NC}"
    ls -la .claude/doc-advisor/specs/.toc_work/
else
    echo -e "${YELLOW}WARN: No pending YAML files created (may be expected if no specs)${NC}"
fi

echo ""

echo "=================================================="
echo "All tests completed!"
echo "=================================================="
echo ""
echo "To clean up: $0 --clean"
