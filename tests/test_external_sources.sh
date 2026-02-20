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
echo "Test 5: sync_external_sources.py with local source"
echo "=================================================="

# Create external local directory
EXTERNAL_LOCAL="$SCRIPT_DIR/external_local_test"
rm -rf "$EXTERNAL_LOCAL"
mkdir -p "$EXTERNAL_LOCAL/team_rules"
echo "# Team Coding Standard" > "$EXTERNAL_LOCAL/team_rules/coding.md"
echo "# Team Architecture" > "$EXTERNAL_LOCAL/team_rules/architecture.md"

# Add external_sources to config.yaml
cat >> .claude/doc-advisor/config.yaml << EXTEOF

external_sources:
  rules:
    - name: team-rules
      type: local
      path: $EXTERNAL_LOCAL/team_rules
EXTEOF

# Run sync
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" 2>&1 || EXIT_CODE=$?
test_result "sync_external_sources.py with local source exits 0" "0" "$EXIT_CODE"

# Verify symlink was created
if [[ -L "$DOCS_DIR/rules/team-rules" ]]; then
    echo -e "${GREEN}PASS${NC}: Local source symlink created"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Local source symlink not created"
    ((FAIL_COUNT++))
fi

# Verify files accessible
if [[ -f "$DOCS_DIR/rules/team-rules/coding.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Local source files accessible via symlink"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Local source files not accessible"
    ((FAIL_COUNT++))
fi

# Verify link_list.md updated
if grep -q "team-rules" "$DOCS_DIR/link_list.md"; then
    echo -e "${GREEN}PASS${NC}: link_list.md updated with local source"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: link_list.md not updated with local source"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 6: sync_external_sources.py --status"
echo "=================================================="

STATUS_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" --status 2>&1)

if echo "$STATUS_OUTPUT" | grep -q "team-rules"; then
    echo -e "${GREEN}PASS${NC}: --status shows team-rules"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: --status does not show team-rules"
    ((FAIL_COUNT++))
    echo "  Output: $STATUS_OUTPUT"
fi

if echo "$STATUS_OUTPUT" | grep -q "linked"; then
    echo -e "${GREEN}PASS${NC}: --status shows linked status"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: --status does not show linked status"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 7: sync idempotency (re-sync local source)"
echo "=================================================="

RESYNC_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" 2>&1)

if echo "$RESYNC_OUTPUT" | grep -q "skipped"; then
    echo -e "${GREEN}PASS${NC}: Re-sync skips existing local source"
    ((PASS_COUNT++))
else
    # Already linked is also acceptable
    if echo "$RESYNC_OUTPUT" | grep -q "Already linked\|Already exists"; then
        echo -e "${GREEN}PASS${NC}: Re-sync recognizes existing local source"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Re-sync did not skip existing source"
        ((FAIL_COUNT++))
        echo "  Output: $RESYNC_OUTPUT"
    fi
fi
echo ""

echo "=================================================="
echo "Test 8: sync with git submodule"
echo "=================================================="

# Initialize test_project as git repo (required for git submodule)
cd "$TEST_PROJECT"
NEED_GIT_CLEANUP=0
if [[ ! -d ".git" ]]; then
    git init -b main >/dev/null 2>&1
    git add -A >/dev/null 2>&1
    git commit -m "init" >/dev/null 2>&1
    NEED_GIT_CLEANUP=1
fi

# Allow local file:// transport (required for git submodule with local bare repos)
# Environment variables ensure the setting propagates to git subcommands
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=protocol.file.allow
export GIT_CONFIG_VALUE_0=always

# Create test bare repo
BARE_REPO="$SCRIPT_DIR/test_bare_repo.git"
TEMP_CLONE="$SCRIPT_DIR/temp_clone_for_test"
rm -rf "$BARE_REPO" "$TEMP_CLONE"

git init --bare --initial-branch=main "$BARE_REPO" >/dev/null 2>&1
git clone "$BARE_REPO" "$TEMP_CLONE" >/dev/null 2>&1
mkdir -p "$TEMP_CLONE/rules"
echo "# External Standard" > "$TEMP_CLONE/rules/external_standard.md"
cd "$TEMP_CLONE" && git add -A >/dev/null 2>&1 && git commit -m "init" >/dev/null 2>&1 && git push -u origin main >/dev/null 2>&1
cd "$TEST_PROJECT"
rm -rf "$TEMP_CLONE"

# Remove previous external_sources and add git source
# First, remove the local source config added in Test 5
$PYTHON_CMD -c "
import sys
lines = open('.claude/doc-advisor/config.yaml').readlines()
# Find and remove external_sources section
result = []
in_external = False
for line in lines:
    stripped = line.strip()
    indent = len(line) - len(line.lstrip())
    if indent == 0 and stripped == 'external_sources:':
        in_external = True
        continue
    if in_external:
        if indent == 0 and stripped and not stripped.startswith('#'):
            in_external = False
            result.append(line)
        continue
    result.append(line)
with open('.claude/doc-advisor/config.yaml', 'w') as f:
    f.writelines(result)
"

# Add git source to config
cat >> .claude/doc-advisor/config.yaml << GITEOF

external_sources:
  rules:
    - name: team-rules
      type: local
      path: $EXTERNAL_LOCAL/team_rules
    - name: ext-standards
      type: git
      url: $BARE_REPO
GITEOF

# Run sync
SYNC_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" 2>&1)
EXIT_CODE=$?

# Check if git submodule was added
if [[ -f "$DOCS_DIR/rules/ext-standards/rules/external_standard.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Git submodule content accessible"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Git submodule content not accessible"
    ((FAIL_COUNT++))
    echo "  Sync output: $SYNC_OUTPUT"
    ls -la "$DOCS_DIR/rules/ext-standards/" 2>/dev/null || echo "  Directory does not exist"
fi

# Check .gitmodules
if [[ -f "$TEST_PROJECT/.gitmodules" ]]; then
    if grep -q "ext-standards" "$TEST_PROJECT/.gitmodules"; then
        echo -e "${GREEN}PASS${NC}: .gitmodules contains ext-standards"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: .gitmodules does not contain ext-standards"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: .gitmodules not created"
    ((FAIL_COUNT++))
fi

# Verify submodule is registered
if git -C "$TEST_PROJECT" submodule status 2>/dev/null | grep -q "ext-standards"; then
    echo -e "${GREEN}PASS${NC}: Git submodule registered"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Git submodule not registered"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 9: sync with sparse_path"
echo "=================================================="

# Create bare repo with subdirectory structure
SPARSE_BARE="$SCRIPT_DIR/test_sparse_bare.git"
SPARSE_CLONE="$SCRIPT_DIR/temp_sparse_clone"
rm -rf "$SPARSE_BARE" "$SPARSE_CLONE"

git init --bare --initial-branch=main "$SPARSE_BARE" >/dev/null 2>&1
git clone "$SPARSE_BARE" "$SPARSE_CLONE" >/dev/null 2>&1
mkdir -p "$SPARSE_CLONE/docs/requirements" "$SPARSE_CLONE/docs/design" "$SPARSE_CLONE/other"
echo "# Partner Requirement" > "$SPARSE_CLONE/docs/requirements/partner_req.md"
echo "# Partner Design" > "$SPARSE_CLONE/docs/design/partner_design.md"
echo "# Other file" > "$SPARSE_CLONE/other/ignore.md"
cd "$SPARSE_CLONE" && git add -A >/dev/null 2>&1 && git commit -m "init" >/dev/null 2>&1 && git push -u origin main >/dev/null 2>&1
cd "$TEST_PROJECT"
rm -rf "$SPARSE_CLONE"

# Remove previous external_sources and add sparse config
$PYTHON_CMD -c "
lines = open('.claude/doc-advisor/config.yaml').readlines()
result = []
in_external = False
for line in lines:
    stripped = line.strip()
    indent = len(line) - len(line.lstrip())
    if indent == 0 and stripped == 'external_sources:':
        in_external = True
        continue
    if in_external:
        if indent == 0 and stripped and not stripped.startswith('#'):
            in_external = False
            result.append(line)
        continue
    result.append(line)
with open('.claude/doc-advisor/config.yaml', 'w') as f:
    f.writelines(result)
"

cat >> .claude/doc-advisor/config.yaml << SPARSEEOF

external_sources:
  requirements:
    - name: partner-reqs
      type: git
      url: $SPARSE_BARE
      sparse_path: docs/requirements
SPARSEEOF

# Run sync
SYNC_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" 2>&1)

# Check .submodules directory
if [[ -d ".claude/doc-advisor/.submodules/partner-reqs" ]]; then
    echo -e "${GREEN}PASS${NC}: Sparse submodule in .submodules/"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Sparse submodule not in .submodules/"
    ((FAIL_COUNT++))
    echo "  Sync output: $SYNC_OUTPUT"
fi

# Check symlink from docs/requirements/partner-reqs
if [[ -L "$DOCS_DIR/requirements/partner-reqs" ]]; then
    echo -e "${GREEN}PASS${NC}: Sparse symlink created in docs/"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Sparse symlink not created"
    ((FAIL_COUNT++))
fi

# Check file accessible via sparse path
if [[ -f "$DOCS_DIR/requirements/partner-reqs/partner_req.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Sparse path file accessible"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Sparse path file not accessible"
    ((FAIL_COUNT++))
    echo "  Expected: $DOCS_DIR/requirements/partner-reqs/partner_req.md"
    ls -la "$DOCS_DIR/requirements/partner-reqs/" 2>/dev/null || echo "  Symlink target missing"
fi

# Ensure other files are NOT directly accessible via docs/
if [[ ! -f "$DOCS_DIR/requirements/partner-reqs/partner_design.md" ]]; then
    echo -e "${GREEN}PASS${NC}: Non-sparse files not in docs/"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Non-sparse files leaked into docs/"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 10: orphan detection"
echo "=================================================="

# Remove external_sources from config but leave submodules/symlinks on disk
$PYTHON_CMD -c "
lines = open('.claude/doc-advisor/config.yaml').readlines()
result = []
in_external = False
for line in lines:
    stripped = line.strip()
    indent = len(line) - len(line.lstrip())
    if indent == 0 and stripped == 'external_sources:':
        in_external = True
        continue
    if in_external:
        if indent == 0 and stripped and not stripped.startswith('#'):
            in_external = False
            result.append(line)
        continue
    result.append(line)
with open('.claude/doc-advisor/config.yaml', 'w') as f:
    f.writelines(result)
"

STATUS_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" --status 2>&1)

if echo "$STATUS_OUTPUT" | grep -qi "orphan"; then
    echo -e "${GREEN}PASS${NC}: Orphans detected in status"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Orphans not detected"
    ((FAIL_COUNT++))
    echo "  Status output: $STATUS_OUTPUT"
fi
echo ""

echo "=================================================="
echo "Test 11: error handling (invalid source)"
echo "=================================================="

# Add invalid source to config
cat >> .claude/doc-advisor/config.yaml << ERREOF

external_sources:
  rules:
    - name: bad-source
      type: git
      url: /nonexistent/repo.git
    - name: good-source
      type: local
      path: $EXTERNAL_LOCAL/team_rules
ERREOF

SYNC_OUTPUT=$($PYTHON_CMD "$SCRIPTS_DIR/sync_external_sources.py" 2>&1)
EXIT_CODE=$?

# Should exit non-zero (has failures)
if [[ $EXIT_CODE -ne 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Non-zero exit on failure"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Should exit non-zero with failed sources"
    ((FAIL_COUNT++))
fi

# Good source should still be processed
if [[ -L "$DOCS_DIR/rules/good-source" ]]; then
    echo -e "${GREEN}PASS${NC}: Good source processed despite bad source"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Good source not processed"
    ((FAIL_COUNT++))
    echo "  Output: $SYNC_OUTPUT"
fi

if echo "$SYNC_OUTPUT" | grep -q "failed"; then
    echo -e "${GREEN}PASS${NC}: Failure reported in summary"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Failure not reported"
    ((FAIL_COUNT++))
fi
echo ""

# =============================================================================
# Cleanup
# =============================================================================

echo "Cleaning up..."

# Remove git submodules and .git from test_project
cd "$TEST_PROJECT"
if [[ -f ".gitmodules" ]]; then
    # Deinit all submodules
    git submodule deinit --all -f >/dev/null 2>&1
    git rm -f --cached .claude/doc-advisor/docs/rules/ext-standards >/dev/null 2>&1
    git rm -f --cached .claude/doc-advisor/.submodules/partner-reqs >/dev/null 2>&1
    rm -f .gitmodules
fi

if [[ $NEED_GIT_CLEANUP -eq 1 ]]; then
    rm -rf "$TEST_PROJECT/.git"
fi

rm -rf "$BARE_REPO" "$SPARSE_BARE"
rm -rf "$EXTERNAL_LOCAL"
rm -rf "$TEST_PROJECT/.claude/doc-advisor/.submodules"
rm -rf "$DOCS_DIR/rules/team-rules"
rm -rf "$DOCS_DIR/rules/good-source"
rm -rf "$DOCS_DIR/rules/ext-standards"
rm -rf "$DOCS_DIR/requirements/partner-reqs"
rm -rf "$TEST_PROJECT/.git/modules" 2>/dev/null

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
