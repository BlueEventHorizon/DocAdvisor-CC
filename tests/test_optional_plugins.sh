#!/bin/bash
# Test: Optional plugin installation (--with-anvil / --with-xcode)
# Usage: ./test_optional_plugins.sh

# Note: Do not use 'set -e' — we want to continue even if individual checks fail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
CURRENT_TEST=""

start() {
    CURRENT_TEST="$1"
    echo ""
    echo "=================================================="
    echo "Test: $CURRENT_TEST"
    echo "=================================================="
}

pass() {
    echo -e "  ${GREEN}PASS${NC}: $1"
    ((PASS++))
}

fail() {
    echo -e "  ${RED}FAIL${NC}: $1"
    ((FAIL++))
}

check_file_exists() {
    local path="$1" label="$2"
    if [[ -f "$path" ]]; then
        pass "$label exists"
    else
        fail "$label missing: $path"
    fi
}

check_file_absent() {
    local path="$1" label="$2"
    if [[ ! -e "$path" ]]; then
        pass "$label is absent (as expected)"
    else
        fail "$label should not exist: $path"
    fi
}

check_grep_absent() {
    local pattern="$1" path="$2" label="$3"
    if grep -rq "$pattern" "$path" 2>/dev/null; then
        fail "$label: pattern '$pattern' still present in $path"
    else
        pass "$label: no leftover '$pattern'"
    fi
}

check_grep_present() {
    local pattern="$1" path="$2" label="$3"
    if grep -rq "$pattern" "$path" 2>/dev/null; then
        pass "$label: found '$pattern'"
    else
        fail "$label: expected '$pattern' not found in $path"
    fi
}

clean_target() {
    rm -rf "$TEST_PROJECT/.claude"
    rm -f "$TEST_PROJECT/.last_setup"
}

echo "=================================================="
echo "DocAdvisor-CC Optional Plugins Test Suite"
echo "=================================================="
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"

# --------------------------------------------------------------------
# Test 1: Default (no flags) — anvil/xcode NOT installed
# --------------------------------------------------------------------
start "1. Default install (no optional plugins)"
clean_target
"$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" >/dev/null 2>&1
check_file_exists "$TEST_PROJECT/.claude/doc-advisor/.source_version" "doc-advisor core"
check_file_absent "$TEST_PROJECT/.claude/anvil" "anvil dir"
check_file_absent "$TEST_PROJECT/.claude/xcode" "xcode dir"
check_file_absent "$TEST_PROJECT/.claude/skills/commit" "skills/commit"
check_file_absent "$TEST_PROJECT/.claude/skills/create-pr" "skills/create-pr"
check_file_absent "$TEST_PROJECT/.claude/skills/build" "skills/build"
check_file_absent "$TEST_PROJECT/.claude/skills/test" "skills/test"

# --------------------------------------------------------------------
# Test 2: --with-anvil installs anvil only
# --------------------------------------------------------------------
start "2. --with-anvil installs anvil, not xcode"
clean_target
"$PROJECT_ROOT/setup.sh" --with-anvil "$TEST_PROJECT" >/dev/null 2>&1
check_file_exists "$TEST_PROJECT/.claude/anvil/.source_version" "anvil .source_version"
check_file_exists "$TEST_PROJECT/.claude/skills/commit/SKILL.md" "anvil commit SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/skills/create-pr/SKILL.md" "anvil create-pr SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/anvil/scripts/check_hook.sh" "anvil check_hook.sh"
check_file_exists "$TEST_PROJECT/.claude/anvil/scripts/extract_issue_ref.sh" "anvil extract_issue_ref.sh"
check_file_absent "$TEST_PROJECT/.claude/xcode" "xcode dir"
check_file_absent "$TEST_PROJECT/.claude/skills/build" "skills/build"
check_file_absent "$TEST_PROJECT/.claude/skills/test" "skills/test"

# --------------------------------------------------------------------
# Test 3: --with-xcode installs xcode only
# --------------------------------------------------------------------
start "3. --with-xcode installs xcode, not anvil"
clean_target
"$PROJECT_ROOT/setup.sh" --with-xcode "$TEST_PROJECT" >/dev/null 2>&1
check_file_exists "$TEST_PROJECT/.claude/xcode/.source_version" "xcode .source_version"
check_file_exists "$TEST_PROJECT/.claude/skills/build/SKILL.md" "xcode build SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/skills/test/SKILL.md" "xcode test SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/xcode/skills/build/scripts/build.sh" "xcode build.sh"
check_file_exists "$TEST_PROJECT/.claude/xcode/skills/test/scripts/test.sh" "xcode test.sh"
check_file_exists "$TEST_PROJECT/.claude/xcode/skills/test/scripts/resolve_simulator.sh" "xcode resolve_simulator.sh"
check_file_absent "$TEST_PROJECT/.claude/anvil" "anvil dir"
check_file_absent "$TEST_PROJECT/.claude/skills/commit" "skills/commit"

# --------------------------------------------------------------------
# Test 4: Both --with-anvil --with-xcode
# --------------------------------------------------------------------
start "4. --with-anvil --with-xcode installs both"
clean_target
"$PROJECT_ROOT/setup.sh" --with-anvil --with-xcode "$TEST_PROJECT" >/dev/null 2>&1
check_file_exists "$TEST_PROJECT/.claude/anvil/.source_version" "anvil .source_version"
check_file_exists "$TEST_PROJECT/.claude/xcode/.source_version" "xcode .source_version"
check_file_exists "$TEST_PROJECT/.claude/skills/commit/SKILL.md" "commit SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/skills/test/SKILL.md" "test SKILL.md"
check_file_exists "$TEST_PROJECT/.claude/doc-advisor/.source_version" "doc-advisor still installed"

# --------------------------------------------------------------------
# Test 5: Transform correctness — no leftover placeholders
# --------------------------------------------------------------------
start "5. No leftover placeholders in transformed SKILL.md / scripts"
# (continues from Test 4 state — both plugins installed)
check_grep_absent '\${CLAUDE_PLUGIN_ROOT}' "$TEST_PROJECT/.claude/skills" "skills/"
check_grep_absent '\${CLAUDE_PLUGIN_ROOT}' "$TEST_PROJECT/.claude/anvil" "anvil/"
check_grep_absent '\${CLAUDE_PLUGIN_ROOT}' "$TEST_PROJECT/.claude/xcode" "xcode/"
check_grep_absent '/anvil:' "$TEST_PROJECT/.claude/skills/commit/SKILL.md" "skills/commit/SKILL.md"
check_grep_absent '/anvil:' "$TEST_PROJECT/.claude/skills/create-pr/SKILL.md" "skills/create-pr/SKILL.md"
check_grep_absent '/xcode:' "$TEST_PROJECT/.claude/skills/build/SKILL.md" "skills/build/SKILL.md"
check_grep_absent '/xcode:' "$TEST_PROJECT/.claude/skills/test/SKILL.md" "skills/test/SKILL.md"

# --------------------------------------------------------------------
# Test 6: Transformed script references point to new location
# --------------------------------------------------------------------
start "6. SKILL.md references point to .claude/<plugin>/ paths"
check_grep_present '\.claude/xcode/skills/test/scripts/test\.sh' \
    "$TEST_PROJECT/.claude/skills/test/SKILL.md" \
    "xcode test SKILL.md"
check_grep_present '\.claude/xcode/skills/build/scripts/build\.sh' \
    "$TEST_PROJECT/.claude/skills/build/SKILL.md" \
    "xcode build SKILL.md"

# --------------------------------------------------------------------
# Test 7: Command headers renamed
# --------------------------------------------------------------------
start "7. SKILL.md command headers use unprefixed form"
check_grep_present '^# /commit' "$TEST_PROJECT/.claude/skills/commit/SKILL.md" "commit header"
check_grep_present '^# /create-pr' "$TEST_PROJECT/.claude/skills/create-pr/SKILL.md" "create-pr header"
check_grep_present '^# /build' "$TEST_PROJECT/.claude/skills/build/SKILL.md" "build header"
check_grep_present '^# /test' "$TEST_PROJECT/.claude/skills/test/SKILL.md" "test header"

# --------------------------------------------------------------------
# Test 8: Shell scripts are executable
# --------------------------------------------------------------------
start "8. Installed shell scripts have executable bit"
for sh in \
    "$TEST_PROJECT/.claude/anvil/scripts/check_hook.sh" \
    "$TEST_PROJECT/.claude/anvil/scripts/extract_issue_ref.sh" \
    "$TEST_PROJECT/.claude/xcode/skills/test/scripts/test.sh" \
    "$TEST_PROJECT/.claude/xcode/skills/build/scripts/build.sh"; do
    if [[ -x "$sh" ]]; then
        pass "executable: $(basename "$sh")"
    else
        fail "not executable: $sh"
    fi
done

# --------------------------------------------------------------------
# Test 9: .source_version files record correct plugin metadata
# --------------------------------------------------------------------
start "9. .source_version records plugin name + version"
if grep -q "^source_plugin: anvil" "$TEST_PROJECT/.claude/anvil/.source_version" 2>/dev/null; then
    pass "anvil .source_version has source_plugin: anvil"
else
    fail "anvil .source_version missing or wrong"
fi
if grep -q "^source_plugin_version:" "$TEST_PROJECT/.claude/anvil/.source_version" 2>/dev/null; then
    pass "anvil .source_version has source_plugin_version"
else
    fail "anvil .source_version missing version"
fi
if grep -q "^source_plugin: xcode" "$TEST_PROJECT/.claude/xcode/.source_version" 2>/dev/null; then
    pass "xcode .source_version has source_plugin: xcode"
else
    fail "xcode .source_version missing or wrong"
fi

# --------------------------------------------------------------------
# Test 10: Invalid plugin source triggers warning but does not abort
# --------------------------------------------------------------------
start "10. Missing optional plugin source: warning only, core install succeeds"
# Create a fake source tree missing anvil/xcode
FAKE_SOURCE="$SCRIPT_DIR/.fake_source_$$"
mkdir -p "$FAKE_SOURCE/plugins/doc-advisor/.claude-plugin"
# Copy doc-advisor from real submodule so core install still works
cp -R "$PROJECT_ROOT/bw-cc-plugins/plugins/doc-advisor/." "$FAKE_SOURCE/plugins/doc-advisor/"
# Also include forge (otherwise doc-advisor setup warns; that's not what we're testing here)
cp -R "$PROJECT_ROOT/bw-cc-plugins/plugins/forge" "$FAKE_SOURCE/plugins/forge"
# Intentionally DO NOT include anvil/xcode

clean_target
OUTPUT=$("$PROJECT_ROOT/setup.sh" --source "$FAKE_SOURCE/plugins/doc-advisor" \
    --with-anvil --with-xcode "$TEST_PROJECT" 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    pass "setup.sh exited 0 despite missing optional plugins"
else
    fail "setup.sh exited $EXIT_CODE"
fi
if echo "$OUTPUT" | grep -q "anvil plugin not found"; then
    pass "anvil warning emitted"
else
    fail "anvil warning missing. Output: $OUTPUT"
fi
if echo "$OUTPUT" | grep -q "xcode plugin not found"; then
    pass "xcode warning emitted"
else
    fail "xcode warning missing"
fi
check_file_exists "$TEST_PROJECT/.claude/doc-advisor/.source_version" "doc-advisor still installed"
check_file_absent "$TEST_PROJECT/.claude/anvil" "anvil dir not created"
check_file_absent "$TEST_PROJECT/.claude/xcode" "xcode dir not created"

rm -rf "$FAKE_SOURCE"

# --------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------
echo ""
echo "=================================================="
echo "Test Summary"
echo "=================================================="
echo -e "  ${GREEN}PASS${NC}: $PASS"
echo -e "  ${RED}FAIL${NC}: $FAIL"
echo ""

if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}All optional-plugin tests passed!${NC}"
    exit 0
else
    echo -e "${RED}$FAIL check(s) failed.${NC}"
    exit 1
fi
