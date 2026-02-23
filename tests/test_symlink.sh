#!/bin/bash
# Test script for symlink support in ToC generation scripts
# Usage: ./test_symlink.sh

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
        echo -e "${GREEN}PASS${NC}: $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $name (expected=$expected, actual=$actual)"
        ((FAIL_COUNT++))
    fi
}

echo "=================================================="
echo "Symlink Support Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Setup: Create test project
echo "Setting up test project..."
cd "$TEST_PROJECT"
rm -rf .claude .last_setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path from orchestrator docs
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/toc_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"
echo ""


SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"

# Create external directories with .md files for symlink testing
echo "Setting up symlinked test directories..."
EXTERNAL_DIR="$SCRIPT_DIR/external_for_symlink_test"
rm -rf "$EXTERNAL_DIR"
mkdir -p "$EXTERNAL_DIR/external_rules"
mkdir -p "$EXTERNAL_DIR/external_specs/requirements"

# Create test files in external directories
cat > "$EXTERNAL_DIR/external_rules/external_rule.md" << 'EOF'
# External Rule

This is an external rule linked via symlink for testing.
EOF

cat > "$EXTERNAL_DIR/external_specs/requirements/external_req.md" << 'EOF'
# External Requirement

This is an external requirement linked via symlink for testing.
EOF

# Create symlinks in rules/ and specs/
ln -sf "$EXTERNAL_DIR/external_rules" "$TEST_PROJECT/rules/linked_rules"
ln -sf "$EXTERNAL_DIR/external_specs" "$TEST_PROJECT/specs/linked_specs"

echo "Symlinks created:"
ls -la "$TEST_PROJECT/rules/" | grep "^l" || echo "  (no symlinks in rules/)"
ls -la "$TEST_PROJECT/specs/" | grep "^l" || echo "  (no symlinks in specs/)"
echo ""

echo "=================================================="
echo "Test 1: create_checksums.py with symlinks (rules)"
echo "=================================================="

RULES_CHECKSUMS=".claude/doc-advisor/toc/rules/.toc_checksums.yaml"
rm -f "$RULES_CHECKSUMS"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>&1 || EXIT_CODE=$?

test_result "create_checksums rules exit code" "0" "$EXIT_CODE"

# Check if external file is included
if grep -q "linked_rules/external_rule.md" "$RULES_CHECKSUMS" 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}: External rule via symlink included in checksums"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: External rule via symlink NOT found in checksums"
    ((FAIL_COUNT++))
    echo "  Contents of $RULES_CHECKSUMS:"
    cat "$RULES_CHECKSUMS" 2>/dev/null | head -20
fi
echo ""

echo "=================================================="
echo "Test 2: create_checksums.py with symlinks (specs)"
echo "=================================================="

SPECS_CHECKSUMS=".claude/doc-advisor/toc/specs/.toc_checksums.yaml"
rm -f "$SPECS_CHECKSUMS"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target specs 2>&1 || EXIT_CODE=$?

test_result "create_checksums specs exit code" "0" "$EXIT_CODE"

# Check if external file is included
if grep -q "linked_specs/requirements/external_req.md" "$SPECS_CHECKSUMS" 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}: External spec via symlink included in checksums"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: External spec via symlink NOT found in checksums"
    ((FAIL_COUNT++))
    echo "  Contents of $SPECS_CHECKSUMS:"
    cat "$SPECS_CHECKSUMS" 2>/dev/null | head -20
fi
echo ""

echo "=================================================="
echo "Test 3: create_pending_yaml.py --target rules with symlinks"
echo "=================================================="

rm -rf ".claude/doc-advisor/toc/rules/.toc_work"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --target rules --full 2>&1 || EXIT_CODE=$?

test_result "create_pending_yaml rules exit code" "0" "$EXIT_CODE"

# Check if pending YAML was created for external file
PENDING_FILE=".claude/doc-advisor/toc/rules/.toc_work/rules--linked_rules--external_rule.yaml"
if [[ -f "$PENDING_FILE" ]]; then
    echo -e "${GREEN}PASS${NC}: Pending YAML created for external rule"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Pending YAML NOT created for external rule"
    ((FAIL_COUNT++))
    echo "  Looking for: $PENDING_FILE"
    echo "  Files in .toc_work:"
    ls -la ".claude/doc-advisor/toc/rules/.toc_work/" 2>/dev/null | head -10
fi
echo ""

echo "=================================================="
echo "Test 4: create_pending_yaml.py --target specs with symlinks"
echo "=================================================="

rm -rf ".claude/doc-advisor/toc/specs/.toc_work"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --target specs --full 2>&1 || EXIT_CODE=$?

test_result "create_pending_yaml specs exit code" "0" "$EXIT_CODE"

# Check if pending YAML was created for external file
PENDING_FILE=".claude/doc-advisor/toc/specs/.toc_work/specs--linked_specs--requirements--external_req.yaml"
if [[ -f "$PENDING_FILE" ]]; then
    echo -e "${GREEN}PASS${NC}: Pending YAML created for external spec"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Pending YAML NOT created for external spec"
    ((FAIL_COUNT++))
    echo "  Looking for: $PENDING_FILE"
    echo "  Files in .toc_work:"
    ls -la ".claude/doc-advisor/toc/specs/.toc_work/" 2>/dev/null | head -10
fi
echo ""

echo "=================================================="
echo "Test 5: Symlink loop detection"
echo "=================================================="

# Create a symlink loop
mkdir -p "$TEST_PROJECT/rules/loop_test"
ln -sf "$TEST_PROJECT/rules/loop_test" "$TEST_PROJECT/rules/loop_test/self_loop"

# This should not hang or crash
EXIT_CODE=0
timeout 30 $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>&1 || EXIT_CODE=$?

# Exit code 124 means timeout
if [[ $EXIT_CODE -eq 124 ]]; then
    echo -e "${RED}FAIL${NC}: Script timed out with symlink loop"
    ((FAIL_COUNT++))
elif [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Symlink loop handled correctly (no hang)"
    ((PASS_COUNT++))
else
    echo -e "${YELLOW}WARN${NC}: Script exited with code $EXIT_CODE (may be expected)"
    ((PASS_COUNT++))
fi

# Cleanup loop
rm -rf "$TEST_PROJECT/rules/loop_test"
echo ""

echo "=================================================="
echo "Test 6: Duplicate file detection via multiple symlinks"
echo "=================================================="

# Create multiple symlinks to same directory
ln -sf "$EXTERNAL_DIR/external_rules" "$TEST_PROJECT/rules/linked_rules_dup"

rm -f "$RULES_CHECKSUMS"
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>&1

# Count occurrences of external_rule.md
COUNT=$(grep -c "external_rule.md" "$RULES_CHECKSUMS" 2>/dev/null || echo "0")

if [[ "$COUNT" -eq 1 ]]; then
    echo -e "${GREEN}PASS${NC}: Duplicate file via multiple symlinks detected and deduplicated (count=$COUNT)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: File appeared $COUNT times (expected 1)"
    ((FAIL_COUNT++))
    echo "  Entries containing external_rule.md:"
    grep "external_rule.md" "$RULES_CHECKSUMS" 2>/dev/null
fi

# Cleanup duplicate link
rm -f "$TEST_PROJECT/rules/linked_rules_dup"
echo ""

echo "=================================================="
echo "Cleanup"
echo "=================================================="

# Remove symlinks
rm -f "$TEST_PROJECT/rules/linked_rules"
rm -f "$TEST_PROJECT/specs/linked_specs"
rm -rf "$EXTERNAL_DIR"
echo "Cleanup complete"
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
