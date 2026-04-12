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
# Pass values: rules_dir, done, specs_dir, done, agent_model
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"

echo ""
echo -e "${GREEN}Setup completed.${NC}"
echo ""

echo "=================================================="
echo "Test 2: Verify sed transformations from source"
echo "=================================================="
echo ""

# Check: ${CLAUDE_PLUGIN_ROOT}/ must not remain in any installed file
if grep -rq '\${CLAUDE_PLUGIN_ROOT}/' .claude/ 2>/dev/null; then
    echo -e "${RED}FAIL: \${CLAUDE_PLUGIN_ROOT}/ reference remains in .claude/${NC}"
    grep -r '\${CLAUDE_PLUGIN_ROOT}/' .claude/ 2>/dev/null
    exit 1
else
    echo -e "${GREEN}PASS: No \${CLAUDE_PLUGIN_ROOT}/ references in .claude/${NC}"
fi

# Check: /doc-advisor: prefix must not remain (should be converted to /)
if grep -rq '/doc-advisor:' .claude/ 2>/dev/null; then
    echo -e "${RED}FAIL: /doc-advisor: prefix remains in .claude/${NC}"
    grep -r '/doc-advisor:' .claude/ 2>/dev/null
    exit 1
else
    echo -e "${GREEN}PASS: No /doc-advisor: prefixes in .claude/${NC}"
fi

# Check: /forge:setup-doc-structure must not remain
if grep -rq '/forge:setup-doc-structure' .claude/ 2>/dev/null; then
    echo -e "${RED}FAIL: /forge:setup-doc-structure remains in .claude/${NC}"
    grep -r '/forge:setup-doc-structure' .claude/ 2>/dev/null
    exit 1
else
    echo -e "${GREEN}PASS: No /forge:setup-doc-structure references in .claude/${NC}"
fi

# Check: .claude/doc-advisor/ path references exist (proof that substitution happened)
if grep -rq '\.claude/doc-advisor/' .claude/skills/ .claude/agents/ .claude/doc-advisor/docs/ 2>/dev/null; then
    echo -e "${GREEN}PASS: .claude/doc-advisor/ references found (substitution applied)${NC}"
else
    echo -e "${RED}FAIL: No .claude/doc-advisor/ references found — substitution may not have run${NC}"
    exit 1
fi

echo ""

echo "=================================================="
echo "Test 3: Run create_pending_yaml.py --category rules"
echo "=================================================="
echo ""

PYTHON_CMD=python3

echo "Using Python: $PYTHON_CMD"
echo ""

# Run the script
if $PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category rules --full; then
    echo ""
    echo -e "${GREEN}PASS: create_pending_yaml.py --category rules executed successfully${NC}"
else
    echo ""
    echo -e "${RED}FAIL: create_pending_yaml.py --category rules failed${NC}"
    exit 1
fi

echo ""

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS: Pending YAML files created${NC}"
    ls -la .claude/doc-advisor/toc/rules/.toc_work/
else
    echo -e "${YELLOW}WARN: No pending YAML files created (may be expected if no rules)${NC}"
fi

echo ""

echo "=================================================="
echo "Test 4: Run create_pending_yaml.py --category specs"
echo "=================================================="
echo ""

if $PYTHON_CMD .claude/doc-advisor/scripts/create_pending_yaml.py --category specs --full; then
    echo ""
    echo -e "${GREEN}PASS: create_pending_yaml.py --category specs executed successfully${NC}"
else
    echo ""
    echo -e "${RED}FAIL: create_pending_yaml.py --category specs failed${NC}"
    exit 1
fi

echo ""

# Check if pending YAML was created
if ls .claude/doc-advisor/toc/specs/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS: Pending YAML files created${NC}"
    ls -la .claude/doc-advisor/toc/specs/.toc_work/
else
    echo -e "${YELLOW}WARN: No pending YAML files created (may be expected if no specs)${NC}"
fi

echo ""

echo "=================================================="
echo "All tests completed!"
echo "=================================================="
echo ""
echo "To clean up: $0 --clean"
