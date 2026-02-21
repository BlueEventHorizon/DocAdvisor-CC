#!/bin/bash
# Test script for create_checksums.py
# Usage: ./test_checksums.sh

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
echo "create_checksums.py Test Suite"
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
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path from orchestrator docs
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/rules_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
echo "Using Python: $PYTHON_CMD"
echo ""

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
RULES_CHECKSUMS=".claude/doc-advisor/toc/rules/.toc_checksums.yaml"
SPECS_CHECKSUMS=".claude/doc-advisor/toc/specs/.toc_checksums.yaml"

echo "=================================================="
echo "Test 2-7a: create_checksums.py - Rules target"
echo "=================================================="

# Clean existing checksums
rm -f "$RULES_CHECKSUMS"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>/dev/null || EXIT_CODE=$?

test_result "create_checksums rules" "0" "$EXIT_CODE"

# Verify checksums file created
if [[ -f "$RULES_CHECKSUMS" ]]; then
    echo -e "${GREEN}PASS${NC}: Rules checksums file created"
    ((PASS_COUNT++))

    # Verify format
    if grep -q "checksums:" "$RULES_CHECKSUMS"; then
        echo -e "${GREEN}PASS${NC}: Checksums file has correct format"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Checksums file missing checksums section"
        ((FAIL_COUNT++))
    fi

    # Verify hash format (SHA-256 = 64 hex chars)
    if grep -E '[a-f0-9]{64}' "$RULES_CHECKSUMS" >/dev/null; then
        echo -e "${GREEN}PASS${NC}: Checksums contain valid SHA-256 hashes"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: No valid SHA-256 hashes found"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: Rules checksums file not created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-7b: create_checksums.py - Specs target"
echo "=================================================="

# Clean existing checksums
rm -f "$SPECS_CHECKSUMS"

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target specs 2>/dev/null || EXIT_CODE=$?

test_result "create_checksums specs" "0" "$EXIT_CODE"

# Verify checksums file created
if [[ -f "$SPECS_CHECKSUMS" ]]; then
    echo -e "${GREEN}PASS${NC}: Specs checksums file created"
    ((PASS_COUNT++))

    # Count entries (should have 2 spec files)
    ENTRY_COUNT=$(grep -c '^  ' "$SPECS_CHECKSUMS" 2>/dev/null || echo "0")
    if [[ "$ENTRY_COUNT" -ge 2 ]]; then
        echo -e "${GREEN}PASS${NC}: Multiple spec files hashed ($ENTRY_COUNT entries)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Expected 2+ entries, got $ENTRY_COUNT"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: Specs checksums file not created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test: Checksums change detection"
echo "=================================================="

# Get current checksum
ORIGINAL_HASH=$(grep "coding_standards" "$RULES_CHECKSUMS" 2>/dev/null | grep -oE '[a-f0-9]{64}' || echo "")

if [[ -n "$ORIGINAL_HASH" ]]; then
    # Modify file
    echo "" >> rules/coding_standards.md

    # Regenerate checksums
    $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>/dev/null || true

    # Get new checksum
    NEW_HASH=$(grep "coding_standards" "$RULES_CHECKSUMS" 2>/dev/null | grep -oE '[a-f0-9]{64}' || echo "")

    if [[ "$ORIGINAL_HASH" != "$NEW_HASH" ]]; then
        echo -e "${GREEN}PASS${NC}: Checksum changed after file modification"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Checksum did not change after modification"
        ((FAIL_COUNT++))
    fi

    # Restore file (remove added newline) - use sed '$d' for macOS/Linux compatibility
    sed '$d' rules/coding_standards.md > rules/coding_standards.md.tmp
    mv rules/coding_standards.md.tmp rules/coding_standards.md
else
    echo -e "${RED}FAIL${NC}: Could not extract original hash for comparison"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test: Invalid target"
echo "=================================================="

EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target invalid 2>/dev/null || EXIT_CODE=$?

if [[ "$EXIT_CODE" -ne 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Invalid target rejected (exit=$EXIT_CODE)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Invalid target should have been rejected"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test: Pending checksums generated by create_pending_yaml (rules)"
echo "=================================================="

# Clean .toc_work and checksums
rm -rf .claude/doc-advisor/toc/rules/.toc_work
rm -f "$RULES_CHECKSUMS"

# First create checksums (needed for incremental detection base)
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>/dev/null || true

# Run create_pending_yaml_rules.py in full mode
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || EXIT_CODE=$?

PENDING_CHECKSUMS=".claude/doc-advisor/toc/rules/.toc_work/.toc_checksums_pending.yaml"

if [[ -f "$PENDING_CHECKSUMS" ]]; then
    echo -e "${GREEN}PASS${NC}: .toc_checksums_pending.yaml created (rules)"
    ((PASS_COUNT++))

    # Verify format matches .toc_checksums.yaml
    if grep -q "checksums:" "$PENDING_CHECKSUMS"; then
        echo -e "${GREEN}PASS${NC}: Pending checksums has correct format"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Pending checksums missing checksums section"
        ((FAIL_COUNT++))
    fi

    # Verify all target files are included (not just changed ones)
    PENDING_ENTRY_COUNT=$(grep -c '^  ' "$PENDING_CHECKSUMS" 2>/dev/null || echo "0")
    RULES_FILE_COUNT=$(find rules -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
    test_result "Pending checksums includes all files" "$RULES_FILE_COUNT" "$PENDING_ENTRY_COUNT"
else
    echo -e "${RED}FAIL${NC}: .toc_checksums_pending.yaml not created (rules)"
    ((FAIL_COUNT++))
fi

# Clean up
rm -rf .claude/doc-advisor/toc/rules/.toc_work
echo ""

echo "=================================================="
echo "Test: Pending checksums generated by create_pending_yaml (specs)"
echo "=================================================="

# Clean .toc_work and checksums
rm -rf .claude/doc-advisor/toc/specs/.toc_work
rm -f "$SPECS_CHECKSUMS"

# First create checksums (needed for incremental detection base)
$PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target specs 2>/dev/null || true

# Run create_pending_yaml_specs.py in full mode
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_specs.py" --full 2>/dev/null || EXIT_CODE=$?

PENDING_CHECKSUMS_SPECS=".claude/doc-advisor/toc/specs/.toc_work/.toc_checksums_pending.yaml"

if [[ -f "$PENDING_CHECKSUMS_SPECS" ]]; then
    echo -e "${GREEN}PASS${NC}: .toc_checksums_pending.yaml created (specs)"
    ((PASS_COUNT++))

    # Verify SHA-256 hashes present
    if grep -E '[a-f0-9]{64}' "$PENDING_CHECKSUMS_SPECS" >/dev/null; then
        echo -e "${GREEN}PASS${NC}: Pending checksums contain valid SHA-256 hashes"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: No valid SHA-256 hashes in pending checksums"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: .toc_checksums_pending.yaml not created (specs)"
    ((FAIL_COUNT++))
fi

# Clean up
rm -rf .claude/doc-advisor/toc/specs/.toc_work
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
