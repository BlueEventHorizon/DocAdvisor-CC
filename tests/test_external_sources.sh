#!/bin/bash
# Test script for external source support (symlink architecture)
# Tests: symlink structure, link_list.md, broken symlink handling
# Usage: ./test_external_sources.sh

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
echo "External Sources Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Setup
echo "Setting up test project..."
cd "$TEST_PROJECT"
rm -rf .claude .last_setup
rm -f rules/new_rule.md
echo -e "rules\nspecs\nrequirements\ndesign\nplan\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"
DOCS_DIR=".claude/doc-advisor/docs"

echo "=================================================="
echo "Test 1: Symlink structure after setup"
echo "=================================================="

# Check docs directory structure
if [[ -d "$DOCS_DIR/rules" ]]; then
    echo -e "${GREEN}PASS${NC}: docs/rules/ exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: docs/rules/ not found"
    ((FAIL_COUNT++))
fi

if [[ -d "$DOCS_DIR/requirements" ]]; then
    echo -e "${GREEN}PASS${NC}: docs/requirements/ exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: docs/requirements/ not found"
    ((FAIL_COUNT++))
fi

if [[ -d "$DOCS_DIR/design" ]]; then
    echo -e "${GREEN}PASS${NC}: docs/design/ exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: docs/design/ not found"
    ((FAIL_COUNT++))
fi

# Check primary symlinks
if [[ -L "$DOCS_DIR/rules/rules" ]]; then
    echo -e "${GREEN}PASS${NC}: Primary rules symlink exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Primary rules symlink not found"
    ((FAIL_COUNT++))
fi

if [[ -L "$DOCS_DIR/requirements/specs" ]]; then
    echo -e "${GREEN}PASS${NC}: Primary requirements symlink exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Primary requirements symlink not found"
    ((FAIL_COUNT++))
fi

if [[ -L "$DOCS_DIR/design/specs" ]]; then
    echo -e "${GREEN}PASS${NC}: Primary design symlink exists"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Primary design symlink not found"
    ((FAIL_COUNT++))
fi

# Verify symlinks resolve correctly
if [[ -f "$DOCS_DIR/rules/rules/coding_standards.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Rules symlink resolves to actual files"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Rules symlink does not resolve"
    ((FAIL_COUNT++))
fi

if [[ -f "$DOCS_DIR/requirements/specs/user_authentication.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Requirements symlink resolves to actual files"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Requirements symlink does not resolve"
    ((FAIL_COUNT++))
fi

if [[ -f "$DOCS_DIR/design/specs/authentication_api.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Design symlink resolves to actual files"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Design symlink does not resolve"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2: link_list.md generation"
echo "=================================================="

LINK_LIST="$DOCS_DIR/link_list.md"

if [[ -f "$LINK_LIST" ]]; then
    echo -e "${GREEN}PASS${NC}: link_list.md exists"
    ((PASS_COUNT++))

    # Verify content structure
    if grep -q "# Document Sources" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has header"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing header"
        ((FAIL_COUNT++))
    fi

    if grep -q "## rules" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has rules section"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing rules section"
        ((FAIL_COUNT++))
    fi

    if grep -q "## requirements" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has requirements section"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing requirements section"
        ((FAIL_COUNT++))
    fi

    if grep -q "## design" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has design section"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing design section"
        ((FAIL_COUNT++))
    fi

    # Verify source entries
    if grep -q "| rules | symlink |" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has rules symlink entry"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing rules symlink entry"
        ((FAIL_COUNT++))
    fi

    if grep -q "| specs | symlink |" "$LINK_LIST"; then
        echo -e "${GREEN}PASS${NC}: link_list.md has specs symlink entry"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: link_list.md missing specs symlink entry"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: link_list.md not found"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 3: Broken symlink handling"
echo "=================================================="

# Get Python path
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/rules_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"

# Create a broken symlink in docs/rules/
ln -sf "/nonexistent/path/to/rules" "$DOCS_DIR/rules/broken_link"

# Scripts should not crash with broken symlinks
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || EXIT_CODE=$?

test_result "create_pending_yaml_rules with broken symlink" "0" "$EXIT_CODE"

# Verify valid files are still processed
if ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 1>/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}: Valid files still processed despite broken symlink"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: No files processed with broken symlink present"
    ((FAIL_COUNT++))
fi

# Clean broken symlink
rm -f "$DOCS_DIR/rules/broken_link"
echo ""

echo "=================================================="
echo "Test 4: Re-setup preserves existing symlinks"
echo "=================================================="

# Add an extra symlink (simulating user adding external source)
EXTERNAL_DIR="$SCRIPT_DIR/external_for_sources_test"
rm -rf "$EXTERNAL_DIR"
mkdir -p "$EXTERNAL_DIR/org_rules"
echo "# Org Rule" > "$EXTERNAL_DIR/org_rules/org_standard.md"
ln -sf "$EXTERNAL_DIR/org_rules" "$DOCS_DIR/rules/org_rules"

# Verify extra symlink works
if [[ -f "$DOCS_DIR/rules/org_rules/org_standard.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Extra symlink created and resolves"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Extra symlink not working"
    ((FAIL_COUNT++))
fi

# Re-run setup (should not destroy extra symlinks)
echo -e "rules\nspecs\nrequirements\ndesign\nplan\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" >/dev/null 2>&1

# Check if extra symlink still exists
if [[ -L "$DOCS_DIR/rules/org_rules" ]]; then
    echo -e "${GREEN}PASS${NC}: Extra symlink preserved after re-setup"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Extra symlink lost after re-setup"
    ((FAIL_COUNT++))
fi

# Verify files accessible through extra symlink
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || EXIT_CODE=$?
test_result "create_pending_yaml_rules with extra source" "0" "$EXIT_CODE"

# Check if extra source files are in pending
if grep -rl "org_rules/org_standard.md" .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 | grep -q .; then
    echo -e "${GREEN}PASS${NC}: Extra source files detected in pending"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Extra source files not in pending"
    ((FAIL_COUNT++))
    echo "  Contents:"
    grep "source_file:" .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null
fi

# Cleanup
rm -f "$DOCS_DIR/rules/org_rules"
rm -rf "$EXTERNAL_DIR"
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
