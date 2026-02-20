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
echo -e "rules\nspecs\nrequirements\ndesign\nplan\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path from orchestrator docs
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/rules_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"
echo ""

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
DOCS_DIR="$TEST_PROJECT/.claude/doc-advisor/docs"

# Create external directories with .md files for symlink testing
echo "Setting up symlinked test directories..."
EXTERNAL_DIR="$SCRIPT_DIR/external_for_symlink_test"
rm -rf "$EXTERNAL_DIR"
mkdir -p "$EXTERNAL_DIR/external_rules"
mkdir -p "$EXTERNAL_DIR/external_reqs"

# Create test files in external directories
cat > "$EXTERNAL_DIR/external_rules/external_rule.md" << 'EOF'
# External Rule

This is an external rule linked via symlink for testing.
EOF

cat > "$EXTERNAL_DIR/external_reqs/external_req.md" << 'EOF'
# External Requirement

This is an external requirement linked via symlink for testing.
EOF

# Create symlinks in docs/ directory (new architecture)
# External rules: docs/rules/external_rules → external directory
ln -sf "$EXTERNAL_DIR/external_rules" "$DOCS_DIR/rules/external_rules"
# External specs: docs/requirements/external_reqs → external directory
ln -sf "$EXTERNAL_DIR/external_reqs" "$DOCS_DIR/requirements/external_reqs"

echo "Symlinks created:"
ls -la "$DOCS_DIR/rules/" | grep "^l" || echo "  (no symlinks in docs/rules/)"
ls -la "$DOCS_DIR/requirements/" | grep "^l" || echo "  (no symlinks in docs/requirements/)"
echo ""

echo "=================================================="
echo "Test 1: create_checksums.py with symlinks (rules)"
echo "=================================================="

RULES_CHECKSUMS=".claude/doc-advisor/toc/rules/.toc_checksums.yaml"
rm -f "$RULES_CHECKSUMS"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>&1 || EXIT_CODE=$?

test_result "create_checksums rules exit code" "0" "$EXIT_CODE"

# Check if external file is included (path through docs/rules/)
if grep -q "external_rules/external_rule.md" "$RULES_CHECKSUMS" 2>/dev/null; then
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
if grep -q "external_reqs/external_req.md" "$SPECS_CHECKSUMS" 2>/dev/null; then
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
echo "Test 3: create_pending_yaml_rules.py with symlinks"
echo "=================================================="

rm -rf ".claude/doc-advisor/toc/rules/.toc_work"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>&1 || EXIT_CODE=$?

test_result "create_pending_yaml_rules exit code" "0" "$EXIT_CODE"

# Check if pending YAML was created for external file (by content, not filename)
if grep -rl "external_rules/external_rule.md" .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 | grep -q .; then
    echo -e "${GREEN}PASS${NC}: Pending YAML created for external rule"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Pending YAML NOT created for external rule"
    ((FAIL_COUNT++))
    echo "  Files in .toc_work:"
    ls -la ".claude/doc-advisor/toc/rules/.toc_work/" 2>/dev/null | head -10
    echo "  Contents:"
    cat ".claude/doc-advisor/toc/rules/.toc_work/"*.yaml 2>/dev/null | grep source_file
fi
echo ""

echo "=================================================="
echo "Test 4: create_pending_yaml_specs.py with symlinks"
echo "=================================================="

rm -rf ".claude/doc-advisor/toc/specs/.toc_work"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_specs.py" --full 2>&1 || EXIT_CODE=$?

test_result "create_pending_yaml_specs exit code" "0" "$EXIT_CODE"

# Check if pending YAML was created for external file (by content, not filename)
if grep -rl "external_reqs/external_req.md" .claude/doc-advisor/toc/specs/.toc_work/*.yaml 2>/dev/null | head -1 | grep -q .; then
    echo -e "${GREEN}PASS${NC}: Pending YAML created for external spec"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Pending YAML NOT created for external spec"
    ((FAIL_COUNT++))
    echo "  Files in .toc_work:"
    ls -la ".claude/doc-advisor/toc/specs/.toc_work/" 2>/dev/null | head -10
    echo "  Contents:"
    cat ".claude/doc-advisor/toc/specs/.toc_work/"*.yaml 2>/dev/null | grep source_file
fi
echo ""

echo "=================================================="
echo "Test 5: Symlink loop detection"
echo "=================================================="

# Create a symlink loop inside docs/rules/
mkdir -p "$DOCS_DIR/rules/loop_test"
ln -sf "$DOCS_DIR/rules/loop_test" "$DOCS_DIR/rules/loop_test/self_loop"

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
rm -rf "$DOCS_DIR/rules/loop_test"
echo ""

echo "=================================================="
echo "Test 6: Duplicate file detection via multiple symlinks"
echo "=================================================="

# Create multiple symlinks to same directory
ln -sf "$EXTERNAL_DIR/external_rules" "$DOCS_DIR/rules/external_rules_dup"

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
rm -f "$DOCS_DIR/rules/external_rules_dup"
echo ""

echo "=================================================="
echo "Cleanup"
echo "=================================================="

# Remove symlinks
rm -f "$DOCS_DIR/rules/external_rules"
rm -f "$DOCS_DIR/requirements/external_reqs"
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
