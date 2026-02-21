#!/bin/bash
# Test script for setup.sh upgrade scenarios
# Tests: legacy file deletion, config.yaml handling, agent preservation
# Usage: ./test_setup_upgrade.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/test_project_upgrade"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

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

cleanup() {
    rm -rf "$TEST_PROJECT"
}

setup_test_project() {
    cleanup
    mkdir -p "$TEST_PROJECT/rules"
    mkdir -p "$TEST_PROJECT/specs/main/requirements"
    echo "# Test Rule" > "$TEST_PROJECT/rules/test.md"
    echo "# Test Spec" > "$TEST_PROJECT/specs/main/requirements/test.md"
}

CURRENT_VERSION=$(grep 'DOC_ADVISOR_VERSION=' "$PROJECT_ROOT/setup.sh" | cut -d'"' -f2)

echo "=================================================="
echo "Setup Upgrade Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo "Current version: $CURRENT_VERSION"
echo ""

# ==================================================
echo "=================================================="
echo "Test 1: Clean install (no existing .claude)"
echo "=================================================="

setup_test_project

# Run setup with defaults
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify structure
test_result "agents/ created" "0" "$([[ -d "$TEST_PROJECT/.claude/agents" ]] && echo 0 || echo 1)"
test_result "skills/create-rules-toc/SKILL.md created" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-rules-toc/SKILL.md" ]] && echo 0 || echo 1)"
test_result "skills/create-specs-toc/SKILL.md created" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-specs-toc/SKILL.md" ]] && echo 0 || echo 1)"
test_result "No skills/doc-advisor/ (legacy)" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"
test_result "doc-advisor/config.yaml created" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml" ]] && echo 0 || echo 1)"
test_result "doc-advisor/docs/ created" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/docs" ]] && echo 0 || echo 1)"
test_result "doc-advisor/scripts/ created" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/scripts" ]] && echo 0 || echo 1)"
test_result "doc-advisor/toc/rules/ created" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/toc/rules" ]] && echo 0 || echo 1)"
test_result "doc-advisor/toc/specs/ created" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/toc/specs" ]] && echo 0 || echo 1)"
test_result "No commands/ (legacy)" "1" "$([[ -d "$TEST_PROJECT/.claude/commands" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 2: Legacy commands/ auto-deleted (file-specific)"
echo "=================================================="

setup_test_project

# Create legacy structure
mkdir -p "$TEST_PROJECT/.claude/commands"
echo "# Legacy command" > "$TEST_PROJECT/.claude/commands/create-rules_toc.md"
echo "# Legacy command" > "$TEST_PROJECT/.claude/commands/create-specs_toc.md"
echo "# User custom command" > "$TEST_PROJECT/.claude/commands/my-custom-command.md"

# Run setup - legacy files are auto-deleted (no user confirmation)
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: doc-advisor commands deleted, user custom preserved
test_result "Legacy create-rules_toc.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/commands/create-rules_toc.md" ]] && echo 0 || echo 1)"
test_result "Legacy create-specs_toc.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/commands/create-specs_toc.md" ]] && echo 0 || echo 1)"
test_result "User custom command preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/commands/my-custom-command.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 3: v3.2 structure verification (split skills)"
echo "=================================================="

setup_test_project

# Run setup
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify new structure
test_result "config.yaml in doc-advisor/" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml" ]] && echo 0 || echo 1)"
test_result "docs/ in doc-advisor/" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/docs" ]] && echo 0 || echo 1)"
test_result "scripts/ in doc-advisor/" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/scripts" ]] && echo 0 || echo 1)"
test_result "toc/rules/ in doc-advisor/" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/toc/rules" ]] && echo 0 || echo 1)"
test_result "toc/specs/ in doc-advisor/" "0" "$([[ -d "$TEST_PROJECT/.claude/doc-advisor/toc/specs" ]] && echo 0 || echo 1)"
test_result "SKILL.md in skills/create-rules-toc/" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-rules-toc/SKILL.md" ]] && echo 0 || echo 1)"
test_result "SKILL.md in skills/create-specs-toc/" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-specs-toc/SKILL.md" ]] && echo 0 || echo 1)"
test_result "No legacy skills/doc-advisor/" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 4: config.yaml skip (preserve existing)"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom exclude to config
echo "      - my_custom_exclude" >> "$TEST_PROJECT/.claude/doc-advisor/config.yaml"
CUSTOM_LINE=$(grep -c "my_custom_exclude" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" | tr -d '[:space:]')

# Run setup again with 's' to skip config
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify custom line is preserved
CUSTOM_LINE_AFTER=$(grep -c "my_custom_exclude" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null | tr -d '[:space:]' || echo 0)
test_result "Custom config preserved (skip)" "$CUSTOM_LINE" "$CUSTOM_LINE_AFTER"
echo ""

# ==================================================
echo "=================================================="
echo "Test 5: config.yaml overwrite with backup"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom exclude to config
echo "      - my_custom_exclude" >> "$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Run setup again with 'o' to overwrite
echo -e "rules\nspecs\nopus\no" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify backup exists and custom line is gone from main config
test_result "Backup created" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml.bak" ]] && echo 0 || echo 1)"
CUSTOM_IN_BACKUP=$(grep -c "my_custom_exclude" "$TEST_PROJECT/.claude/doc-advisor/config.yaml.bak" 2>/dev/null | tr -d '[:space:]' || echo 0)
test_result "Custom in backup" "1" "$CUSTOM_IN_BACKUP"
CUSTOM_IN_NEW=$(grep -c "my_custom_exclude" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null | tr -d '[:space:]' || echo 0)
test_result "Custom NOT in new config" "0" "$CUSTOM_IN_NEW"
echo ""

# ==================================================
echo "=================================================="
echo "Test 6: v3.0 skills/doc-advisor/ removed when upgrading to v3.1 (split skills)"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create fake v3.0 structure (unified skill)
mkdir -p "$TEST_PROJECT/.claude/skills/doc-advisor"
echo "# Old v3.0 skill" > "$TEST_PROJECT/.claude/skills/doc-advisor/SKILL.md"

# Run setup again with 'o' to overwrite config
echo -e "rules\nspecs\nopus\no" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: v3.0 unified skill removed, v3.1 split skills installed
test_result "Legacy skills/doc-advisor/ removed" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"
test_result "skills/create-rules-toc/SKILL.md exists" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-rules-toc/SKILL.md" ]] && echo 0 || echo 1)"
test_result "skills/create-specs-toc/SKILL.md exists" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/create-specs-toc/SKILL.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 7: agents/ custom agent preserved"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom agent
echo "# My custom agent" > "$TEST_PROJECT/.claude/agents/my-custom-agent.md"

# Run setup again
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: custom agent preserved, managed agents still exist
test_result "Custom agent preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/my-custom-agent.md" ]] && echo 0 || echo 1)"
test_result "Managed agent exists" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-toc-updater.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 8: Repeated setup preserves toc/ directory structure"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create fake ToC files (simulating generated output)
echo "# Generated ToC" > "$TEST_PROJECT/.claude/doc-advisor/toc/rules/rules_toc.yaml"
echo "# Generated ToC" > "$TEST_PROJECT/.claude/doc-advisor/toc/specs/specs_toc.yaml"

# Run setup again with 's' to skip config
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: toc files are preserved
test_result "rules_toc.yaml preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/toc/rules/rules_toc.yaml" ]] && echo 0 || echo 1)"
test_result "specs_toc.yaml preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/toc/specs/specs_toc.yaml" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 9: Version-based protection (current version protected, no identifier deleted)"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create legacy file WITH CURRENT version (should be protected)
mkdir -p "$TEST_PROJECT/.claude/commands"
cat > "$TEST_PROJECT/.claude/commands/create-rules_toc.md" << EOF
---
doc-advisor-version-xK9XmQ: "$CURRENT_VERSION"
name: protected-command
---
# This file has CURRENT version and should be protected
EOF

# Create legacy file WITHOUT identifier (should be deleted)
echo "# No identifier - legacy file" > "$TEST_PROJECT/.claude/commands/create-specs_toc.md"

# Run setup again
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: file with current version is protected, file without is deleted
test_result "File with current version protected" "0" "$([[ -f "$TEST_PROJECT/.claude/commands/create-rules_toc.md" ]] && echo 0 || echo 1)"
test_result "File without identifier deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/commands/create-specs_toc.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 10: Old version is deleted, current version is protected"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create skills/doc-advisor/ with OLD version (should be deleted)
mkdir -p "$TEST_PROJECT/.claude/skills/doc-advisor"
cat > "$TEST_PROJECT/.claude/skills/doc-advisor/SKILL.md" << 'EOF'
---
doc-advisor-version-xK9XmQ: "3.1"
name: doc-advisor
---
# This skill has OLD version and should be deleted
EOF

# Run setup again
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: skills/doc-advisor/ with old version is deleted
test_result "skills/doc-advisor/ with old version deleted" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"

# Now test current version protection
mkdir -p "$TEST_PROJECT/.claude/skills/doc-advisor"
cat > "$TEST_PROJECT/.claude/skills/doc-advisor/SKILL.md" << EOF
---
doc-advisor-version-xK9XmQ: "$CURRENT_VERSION"
name: doc-advisor
---
# This skill has CURRENT version and should be protected
EOF

# Run setup again
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: skills/doc-advisor/ with current version is protected
test_result "skills/doc-advisor/ with current version protected" "0" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 11: CLAUDE.md に Doc Advisor ルールを追記 (y)"
echo "=================================================="

setup_test_project

# Create existing CLAUDE.md with some content
echo "# My Project" > "$TEST_PROJECT/CLAUDE.md"
echo "" >> "$TEST_PROJECT/CLAUDE.md"
echo "Existing content here." >> "$TEST_PROJECT/CLAUDE.md"

# Run setup with 'y' for CLAUDE.md prompt
echo -e "rules\nspecs\nopus\ny" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: marker exists and existing content preserved
MARKER_COUNT=$(grep -c "doc-advisor-section-start" "$TEST_PROJECT/CLAUDE.md" 2>/dev/null || echo 0)
test_result "CLAUDE.md marker added" "1" "$MARKER_COUNT"
EXISTING_PRESERVED=$(grep -c "Existing content here" "$TEST_PROJECT/CLAUDE.md" 2>/dev/null || echo 0)
test_result "Existing CLAUDE.md content preserved" "1" "$EXISTING_PRESERVED"
echo ""

# ==================================================
echo "=================================================="
echo "Test 12: CLAUDE.md 新規作成 (y)"
echo "=================================================="

setup_test_project

# No CLAUDE.md exists

# Run setup with 'y' for CLAUDE.md prompt
echo -e "rules\nspecs\nopus\ny" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: CLAUDE.md created with marker
test_result "CLAUDE.md created" "0" "$([[ -f "$TEST_PROJECT/CLAUDE.md" ]] && echo 0 || echo 1)"
MARKER_COUNT=$(grep -c "doc-advisor-section-start" "$TEST_PROJECT/CLAUDE.md" 2>/dev/null || echo 0)
test_result "CLAUDE.md marker exists" "1" "$MARKER_COUNT"
echo ""

# ==================================================
echo "=================================================="
echo "Test 13: CLAUDE.md マーカー既存でスキップ"
echo "=================================================="

setup_test_project

# Create CLAUDE.md with existing marker
cat > "$TEST_PROJECT/CLAUDE.md" << 'EOF'
# My Project

<!-- doc-advisor-section-start -->
## Doc Advisor ルール [MANDATORY]
<!-- doc-advisor-section-end -->
EOF

# Run setup (no extra input needed - marker detected, prompt skipped)
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: marker still only appears once (not duplicated)
MARKER_COUNT=$(grep -c "doc-advisor-section-start" "$TEST_PROJECT/CLAUDE.md" 2>/dev/null || echo 0)
test_result "CLAUDE.md marker not duplicated" "1" "$MARKER_COUNT"
echo ""

# ==================================================
echo "=================================================="
echo "Test 14: CLAUDE.md スキップ (n)"
echo "=================================================="

setup_test_project

# Create CLAUDE.md without marker
echo "# My Project" > "$TEST_PROJECT/CLAUDE.md"

# Run setup with 'n' for CLAUDE.md prompt
echo -e "rules\nspecs\nopus\nn" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: no marker added
MARKER_COUNT=$(grep -c "doc-advisor-section-start" "$TEST_PROJECT/CLAUDE.md" 2>/dev/null; true)
test_result "CLAUDE.md marker not added (skipped)" "0" "$MARKER_COUNT"
echo ""

# ==================================================
echo "=================================================="
echo "Test 15: advisor agent 削除 (T-008)"
echo "=================================================="

setup_test_project

# First install
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create legacy advisor agent files (should be deleted on next setup)
echo "# Legacy rules advisor" > "$TEST_PROJECT/.claude/agents/rules-advisor.md"
echo "# Legacy specs advisor" > "$TEST_PROJECT/.claude/agents/specs-advisor.md"

# Run setup again
echo -e "rules\nspecs\nopus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: advisor agents deleted
test_result "rules-advisor.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-advisor.md" ]] && echo 0 || echo 1)"
test_result "specs-advisor.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/specs-advisor.md" ]] && echo 0 || echo 1)"
# Verify: managed agents still exist
test_result "rules-toc-updater.md preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-toc-updater.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 16: query-* skill インストール (T-009)"
echo "=================================================="

setup_test_project

# Run setup
echo -e "rules\nspecs\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: query-rules and query-specs skills installed
test_result "query-rules/SKILL.md installed" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/query-rules/SKILL.md" ]] && echo 0 || echo 1)"
test_result "query-specs/SKILL.md installed" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/query-specs/SKILL.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
# Cleanup
cleanup

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
