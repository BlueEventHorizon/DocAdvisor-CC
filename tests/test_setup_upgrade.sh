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
    cat > "$TEST_PROJECT/.doc_structure.yaml" << 'DOCEOF'
rules:
  rule:
    paths: [rules/]
specs:
  spec:
    paths: [specs/]
DOCEOF
}

CURRENT_VERSION=$(grep 'DOC_ADVISOR_VERSION=' "$PROJECT_ROOT/setup.sh" | cut -d'"' -f2)
PYTHON3=$(command -v python3 2>/dev/null || echo "python3")

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
SETUP_OUTPUT=$(echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" 2>&1)

# Verify: doc-advisor commands deleted, user custom preserved
test_result "Legacy create-rules_toc.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/commands/create-rules_toc.md" ]] && echo 0 || echo 1)"
test_result "Legacy create-specs_toc.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/commands/create-specs_toc.md" ]] && echo 0 || echo 1)"
test_result "User custom command preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/commands/my-custom-command.md" ]] && echo 0 || echo 1)"

# Verify: console output shows deletion messages (REQ-002-01 AC)
if echo "$SETUP_OUTPUT" | grep -q "Removed legacy"; then
    echo -e "${GREEN}PASS${NC}: Deletion messages displayed"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: No 'Removed legacy' message in output"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 3: v3.2 structure verification (split skills)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom exclude to config
echo "      - my_custom_exclude" >> "$TEST_PROJECT/.claude/doc-advisor/config.yaml"
CUSTOM_LINE=$(grep -c "my_custom_exclude" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" | tr -d '[:space:]')

# Run setup again with 's' to skip config
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom exclude to config
echo "      - my_custom_exclude" >> "$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Run setup again with 'o' to overwrite
echo -e "opus\no" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create fake v3.0 structure (unified skill)
mkdir -p "$TEST_PROJECT/.claude/skills/doc-advisor"
echo "# Old v3.0 skill" > "$TEST_PROJECT/.claude/skills/doc-advisor/SKILL.md"

# Run setup again with 'o' to overwrite config
echo -e "opus\no" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom agent
echo "# My custom agent" > "$TEST_PROJECT/.claude/agents/my-custom-agent.md"

# Run setup again (capture output for message verification)
SETUP_OUTPUT=$(echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" 2>&1)

# Verify: custom agent preserved, managed agents still exist
test_result "Custom agent preserved" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/my-custom-agent.md" ]] && echo 0 || echo 1)"
test_result "Managed agent exists" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/toc-updater.md" ]] && echo 0 || echo 1)"

# Verify: console output shows preserving message (REQ-002-02 AC)
if echo "$SETUP_OUTPUT" | grep -q "Preserving:"; then
    echo -e "${GREEN}PASS${NC}: Preserving message displayed"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: No 'Preserving:' message in output"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 8: Repeated setup preserves toc/ directory structure"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create fake ToC files (simulating generated output)
echo "# Generated ToC" > "$TEST_PROJECT/.claude/doc-advisor/toc/rules/rules_toc.yaml"
echo "# Generated ToC" > "$TEST_PROJECT/.claude/doc-advisor/toc/specs/specs_toc.yaml"

# Run setup again with 's' to skip config
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: skills/doc-advisor/ with current version is protected
test_result "skills/doc-advisor/ with current version protected" "0" "$([[ -d "$TEST_PROJECT/.claude/skills/doc-advisor" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 11: advisor agent 削除 (T-008)"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create legacy advisor agent files (should be deleted on next setup)
echo "# Legacy rules advisor" > "$TEST_PROJECT/.claude/agents/rules-advisor.md"
echo "# Legacy specs advisor" > "$TEST_PROJECT/.claude/agents/specs-advisor.md"

# Run setup again
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: advisor agents deleted
test_result "rules-advisor.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-advisor.md" ]] && echo 0 || echo 1)"
test_result "specs-advisor.md deleted" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/specs-advisor.md" ]] && echo 0 || echo 1)"
# Verify: managed agents still exist
test_result "toc-updater.md exists" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/toc-updater.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 12: query-* skill インストール (T-009)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: query-rules and query-specs skills installed
test_result "query-rules/SKILL.md installed" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/query-rules/SKILL.md" ]] && echo 0 || echo 1)"
test_result "query-specs/SKILL.md installed" "0" "$([[ -f "$TEST_PROJECT/.claude/skills/query-specs/SKILL.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 13: setup-config skill installed from template"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: setup-config skill installed
test_result "setup-config/SKILL.md installed" "1" "$([[ -f "$TEST_PROJECT/.claude/skills/setup-config/SKILL.md" ]] && echo 1 || echo 0)"
test_result "setup-config/ dir exists" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/setup-config" ]] && echo 1 || echo 0)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 14: v3.8 unified scripts (old scripts removed)"
echo "=================================================="

setup_test_project

# First install (old scripts don't exist in fresh install, simulate upgrade)
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create old per-category scripts (simulate pre-3.8 installation)
echo "# Old script" > "$TEST_PROJECT/.claude/doc-advisor/scripts/create_pending_yaml_rules.py"
echo "# Old script" > "$TEST_PROJECT/.claude/doc-advisor/scripts/merge_rules_toc.py"
echo "# Old script" > "$TEST_PROJECT/.claude/doc-advisor/scripts/write_rules_pending.py"

# Run setup again
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: old scripts removed, new unified scripts exist
test_result "Old create_pending_yaml_rules.py removed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/create_pending_yaml_rules.py" ]] && echo 0 || echo 1)"
test_result "Old merge_rules_toc.py removed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/merge_rules_toc.py" ]] && echo 0 || echo 1)"
test_result "Old write_rules_pending.py removed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/write_rules_pending.py" ]] && echo 0 || echo 1)"
test_result "New create_pending_yaml.py exists" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/create_pending_yaml.py" ]] && echo 0 || echo 1)"
test_result "New merge_toc.py exists" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/merge_toc.py" ]] && echo 0 || echo 1)"
test_result "New write_pending.py exists" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/write_pending.py" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 15: v3.8 unified agents (old agents removed)"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create old per-category agents (simulate pre-3.8 installation)
echo "# Old agent" > "$TEST_PROJECT/.claude/agents/rules-toc-updater.md"
echo "# Old agent" > "$TEST_PROJECT/.claude/agents/specs-toc-updater.md"

# Run setup again
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: old agents removed, new unified agent exists
test_result "Old rules-toc-updater.md removed" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-toc-updater.md" ]] && echo 0 || echo 1)"
test_result "Old specs-toc-updater.md removed" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/specs-toc-updater.md" ]] && echo 0 || echo 1)"
test_result "New toc-updater.md exists" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/toc-updater.md" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 16: config.yaml has root_dirs imported from .doc_structure.yaml"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Verify: root_dirs IS set (imported from .doc_structure.yaml by setup.sh)
ACTIVE_ROOTDIRS=$(grep -c "^  root_dirs:" "$CONFIG" || true)
test_result "root_dirs imported from .doc_structure.yaml" "2" "$ACTIVE_ROOTDIRS"

# Verify: doc_types_map is also set
DOCTYPES_MAP=$(grep -c "^  doc_types_map:" "$CONFIG" || true)
test_result "doc_types_map imported from .doc_structure.yaml" "2" "$DOCTYPES_MAP"
echo ""

# ==================================================
echo "=================================================="
echo "Test 16b: import_doc_structure.py - multiple doc_types and paths"
echo "=================================================="

cleanup
mkdir -p "$TEST_PROJECT/rules" "$TEST_PROJECT/references"
mkdir -p "$TEST_PROJECT/specs/requirements" "$TEST_PROJECT/specs/design" "$TEST_PROJECT/specs/plans"
echo "# Rule" > "$TEST_PROJECT/rules/test.md"
echo "# Ref" > "$TEST_PROJECT/references/test.md"
echo "# Req" > "$TEST_PROJECT/specs/requirements/test.md"
echo "# Des" > "$TEST_PROJECT/specs/design/test.md"
echo "# Plan" > "$TEST_PROJECT/specs/plans/test.md"

cat > "$TEST_PROJECT/.doc_structure.yaml" << 'DOCEOF'
rules:
  rule:
    paths: [rules/]
  reference:
    paths:
      - references/
specs:
  requirement:
    paths: [specs/requirements/]
  design:
    paths: [specs/design/]
  plan:
    paths: [specs/plans/]
DOCEOF

echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Verify: rules has 2 root_dirs (rules/, references/)
RULES_DIRS=$(awk '/^rules:/{s="rules"} /^specs:/{s="specs"} /^common:/{s=""} s=="rules" && /^    - /{c++} END{print c+0}' "$CONFIG")
test_result "rules has 2 root_dirs" "2" "$RULES_DIRS"

# Verify: specs has 3 root_dirs
SPECS_DIRS=$(awk '/^rules:/{s="rules"} /^specs:/{s="specs"} /^common:/{s=""} s=="specs" && /^    - /{c++} END{print c+0}' "$CONFIG")
test_result "specs has 3 root_dirs" "3" "$SPECS_DIRS"

# Verify: doc_types_map has correct mappings
test_result "doc_types_map: rules/ -> rule" "1" "$(grep -c 'rules/: rule' "$CONFIG" || echo 0)"
test_result "doc_types_map: references/ -> reference" "1" "$(grep -c 'references/: reference' "$CONFIG" || echo 0)"
test_result "doc_types_map: specs/requirements/ -> requirement" "1" "$(grep -c 'specs/requirements/: requirement' "$CONFIG" || echo 0)"
test_result "doc_types_map: specs/design/ -> design" "1" "$(grep -c 'specs/design/: design' "$CONFIG" || echo 0)"
test_result "doc_types_map: specs/plans/ -> plan" "1" "$(grep -c 'specs/plans/: plan' "$CONFIG" || echo 0)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 16c: import_doc_structure.py - no .doc_structure.yaml"
echo "=================================================="

cleanup
mkdir -p "$TEST_PROJECT/rules" "$TEST_PROJECT/specs"
echo "# Rule" > "$TEST_PROJECT/rules/test.md"
echo "# Spec" > "$TEST_PROJECT/specs/test.md"
# No .doc_structure.yaml created

echo -e "c\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Verify: root_dirs remains commented out
ACTIVE_ROOTDIRS=$(grep -c "^  root_dirs:" "$CONFIG" || true)
test_result "No root_dirs when no .doc_structure.yaml" "0" "$ACTIVE_ROOTDIRS"

# Verify: doc_types_map remains commented out
ACTIVE_DOCTYPES=$(grep -c "^  doc_types_map:" "$CONFIG" || true)
test_result "No doc_types_map when no .doc_structure.yaml" "0" "$ACTIVE_DOCTYPES"
echo ""

# ==================================================
echo "=================================================="
echo "Test 16d: import_doc_structure.py - rules only (no specs in .doc_structure.yaml)"
echo "=================================================="

cleanup
mkdir -p "$TEST_PROJECT/rules"
echo "# Rule" > "$TEST_PROJECT/rules/test.md"

cat > "$TEST_PROJECT/.doc_structure.yaml" << 'DOCEOF'
rules:
  rule:
    paths: [rules/]
DOCEOF

echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Verify: rules root_dirs is set (uncommented root_dirs: exists in rules section)
RULES_SET=$(awk '/^rules:/{s="rules"} /^specs:/{s="specs"} /^common:/{s=""} s=="rules" && /^  root_dirs:/{print}' "$CONFIG" | grep -c "root_dirs:" || true)
test_result "rules root_dirs set (rules-only .doc_structure)" "1" "$RULES_SET"

# Verify: specs root_dirs remains commented
SPECS_SET=$(awk '/^rules:/{s="rules"} /^specs:/{s="specs"} /^common:/{s=""} s=="specs" && /^  root_dirs:/{print}' "$CONFIG" | grep -c "root_dirs:" || true)
test_result "specs root_dirs NOT set (rules-only .doc_structure)" "0" "$SPECS_SET"
echo ""

# ==================================================
echo "=================================================="
echo "Test 17: classify_dirs.py installed from template"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: classify_dirs.py and classification_rules.md exist (REQ-002-07 AC)
test_result "classify_dirs.py installed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/classify_dirs.py" ]] && echo 1 || echo 0)"
test_result "classification_rules.md installed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/docs/classification_rules.md" ]] && echo 1 || echo 0)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 18: v3.9 set_root_dirs.py legacy cleanup"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create legacy set_root_dirs.py (simulate pre-3.9 installation)
echo "# Legacy set_root_dirs" > "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py"

# Run setup again
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: set_root_dirs.py removed
test_result "set_root_dirs.py removed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 19: config.yaml root_dirs manual override"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Manually change root_dirs to custom value (override auto-imported value)
$PYTHON3 -c "
import re
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
content = re.sub(r'(rules:\n)  root_dirs:\n    - rules/', r'\1  root_dirs:\n    - custom_rules/', content)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write(content)
"

# Verify: root_dirs override is set
RULES_CUSTOM=$(grep -c "custom_rules" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" || echo 0)
test_result "Manual root_dirs override in config" "1" "$RULES_CUSTOM"
echo ""

# ==================================================
echo "=================================================="
echo "Test 20: config.yaml exclude patterns (empty defaults)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Verify: exclude section exists with empty array (no items)
RULES_EXCLUDE_ITEMS=$(awk '/^rules:/,/^specs:/' "$CONFIG" | grep -c "^      - " | tr -d '[:space:]')
RULES_EXCLUDE_ITEMS="${RULES_EXCLUDE_ITEMS:-0}"
test_result "Rules exclude empty by default" "0" "$RULES_EXCLUDE_ITEMS"
SPECS_EXCLUDE_ITEMS=$(awk '/^specs:/,/^common:/' "$CONFIG" | grep -c "^      - " | tr -d '[:space:]')
SPECS_EXCLUDE_ITEMS="${SPECS_EXCLUDE_ITEMS:-0}"
test_result "Specs exclude empty by default" "0" "$SPECS_EXCLUDE_ITEMS"
echo ""

# ==================================================
echo "=================================================="
echo "Test 21: No skip/exclude (empty input)"
echo "=================================================="

setup_test_project

# Setup only asks for model name now
echo -e "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CONFIG="$TEST_PROJECT/.claude/doc-advisor/config.yaml"
# exclude: should be present but with no items (no lines starting with 6-space dash)
EXCLUDE_ITEMS=$(awk '/^rules:/,/^specs:/' "$CONFIG" | grep -c "^      - " | tr -d '[:space:]')
EXCLUDE_ITEMS="${EXCLUDE_ITEMS:-0}"
test_result "No rules exclude items" "0" "$EXCLUDE_ITEMS"
EXCLUDE_ITEMS=$(awk '/^specs:/,/^common:/' "$CONFIG" | grep -c "^      - " | tr -d '[:space:]')
EXCLUDE_ITEMS="${EXCLUDE_ITEMS:-0}"
test_result "No specs exclude items" "0" "$EXCLUDE_ITEMS"
echo ""

# ==================================================
echo "=================================================="
echo "Test 22: v3.9 full legacy cleanup (all removed files)"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create all legacy files (simulate pre-3.9 installation + v4.2 classify-docs)
mkdir -p "$TEST_PROJECT/.claude/skills/setup-config"
echo "# Legacy" > "$TEST_PROJECT/.claude/skills/setup-config/SKILL.md"
mkdir -p "$TEST_PROJECT/.claude/skills/classify-docs"
echo "# Legacy" > "$TEST_PROJECT/.claude/skills/classify-docs/SKILL.md"
echo "# Legacy" > "$TEST_PROJECT/.claude/doc-advisor/scripts/classify_dirs.py"
echo "# Legacy" > "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py"

# Run setup again
echo -e "opus\ns" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify all legacy files cleaned up
test_result "setup-config/ exists after upgrade" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/setup-config" ]] && echo 1 || echo 0)"
test_result "classify-docs/ removed after upgrade" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/classify-docs" ]] && echo 0 || echo 1)"
test_result "classify_dirs.py exists after upgrade" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/classify_dirs.py" ]] && echo 1 || echo 0)"
test_result "set_root_dirs.py removed in upgrade" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 23: check_config.sh installed with exec permission (T-011)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: check_config.sh exists and is executable
test_result "check_config.sh exists" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/check_config.sh" ]] && echo 0 || echo 1)"
test_result "check_config.sh is executable" "0" "$([[ -x "$TEST_PROJECT/.claude/doc-advisor/scripts/check_config.sh" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 24: Skill Pre-check sections (T-012)"
echo "=================================================="

# Verify: all 4 skills have Pre-check section referencing check_config.sh
ALL_PRECHECK_OK=true
for SKILL_NAME in create-rules-toc create-specs-toc query-rules query-specs; do
    SKILL_FILE="$TEST_PROJECT/.claude/skills/$SKILL_NAME/SKILL.md"
    if grep -q "Pre-check" "$SKILL_FILE" 2>/dev/null && grep -q "check_config.sh" "$SKILL_FILE" 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: $SKILL_NAME has Pre-check"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $SKILL_NAME missing Pre-check"
        ((FAIL_COUNT++))
        ALL_PRECHECK_OK=false
    fi
done
echo ""

# ==================================================
echo "=================================================="
echo "Test 25: check_config.sh behavior (FR-08)"
echo "=================================================="

setup_test_project

# Run setup (root_dirs imported from .doc_structure.yaml)
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

CHECK_SCRIPT="$TEST_PROJECT/.claude/doc-advisor/scripts/check_config.sh"

# Case 1: root_dirs set (after setup import) → no output
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" 2>/dev/null)
test_result "No output when root_dirs set (no category arg)" "" "$OUTPUT"

# Case 2: Category-specific check → no output for configured category
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" rules 2>/dev/null)
test_result "No output for 'rules' when configured" "" "$OUTPUT"

# Case 2b: specs category check → no output when configured
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" specs 2>/dev/null)
test_result "No output for 'specs' when configured" "" "$OUTPUT"

# Case 3: Remove root_dirs → ACTION REQUIRED
$PYTHON3 -c "
import re
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
content = re.sub(r'  root_dirs:\n(    - [^\n]+\n)+', '  # root_dirs: []    # Auto-configured by setup.sh or /setup-config\n', content)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write(content)
"
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" rules 2>/dev/null)
if [[ "$OUTPUT" == *"ACTION REQUIRED"* ]]; then
    echo -e "${GREEN}PASS${NC}: ACTION REQUIRED when root_dirs not set"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected ACTION REQUIRED message, got: $OUTPUT"
    ((FAIL_COUNT++))
fi

# Case 4: .doc_structure.yaml exists but root_dirs NOT set → still ACTION REQUIRED (FR-08)
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" rules 2>/dev/null)
if [[ "$OUTPUT" == *"ACTION REQUIRED"* ]]; then
    echo -e "${GREEN}PASS${NC}: ACTION REQUIRED even with .doc_structure.yaml present (FR-08)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected ACTION REQUIRED (FR-08: no runtime .doc_structure.yaml), got: $OUTPUT"
    ((FAIL_COUNT++))
fi

# Case 5: Cross-category — restore rules root_dirs only, specs stays removed
# Re-run setup to get fresh config, then selectively remove only specs root_dirs
setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1
$PYTHON3 -c "
import re
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
# Remove only specs root_dirs (between 'specs:' section and next section or EOF)
# Find specs section and remove its root_dirs block
lines = content.split('\n')
result = []
in_specs = False
skip_root_items = False
for line in lines:
    stripped = line.strip()
    # Track section
    if stripped and not stripped.startswith('#') and ':' in stripped:
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            key = stripped.partition(':')[0].strip()
            if key in ('rules', 'specs', 'common'):
                in_specs = (key == 'specs')
    # In specs section: replace root_dirs with commented version
    if in_specs and stripped == 'root_dirs:' and line.startswith('  '):
        result.append('  # root_dirs: []    # Auto-configured by setup.sh or /setup-config')
        skip_root_items = True
        continue
    if skip_root_items:
        if stripped.startswith('- '):
            continue  # skip list items
        else:
            skip_root_items = False
    result.append(line)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write('\n'.join(result))
"

# rules should still pass
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" rules 2>/dev/null)
test_result "Cross-category: 'rules' OK when only rules configured" "" "$OUTPUT"

# specs should fail
OUTPUT=$(cd "$TEST_PROJECT" && bash "$CHECK_SCRIPT" specs 2>/dev/null)
if [[ "$OUTPUT" == *"ACTION REQUIRED"* ]] && [[ "$OUTPUT" == *"specs"* ]]; then
    echo -e "${GREEN}PASS${NC}: Cross-category: 'specs' ACTION REQUIRED when only rules configured"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected ACTION REQUIRED for specs, got: $OUTPUT"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 26: config.yaml merge option (REQ-002-03 [m])"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add custom setting to config
echo "      - merge_test_custom_setting" >> "$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Run setup again with 'm' to merge
SETUP_OUTPUT=$(echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" 2>&1)

# Verify: config.yaml.old exists (old config saved)
test_result "config.yaml.old created" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml.old" ]] && echo 0 || echo 1)"

# Verify: old config preserved in .old
CUSTOM_IN_OLD=$(grep -c "merge_test_custom_setting" "$TEST_PROJECT/.claude/doc-advisor/config.yaml.old" 2>/dev/null | tr -d '[:space:]' || echo 0)
test_result "Custom setting in .old" "1" "$CUSTOM_IN_OLD"

# Verify: new config does NOT have the custom setting (overwritten with template)
CUSTOM_IN_NEW=$(grep -c "merge_test_custom_setting" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null | tr -d '[:space:]' || echo 0)
test_result "Custom NOT in new config" "0" "$CUSTOM_IN_NEW"

# Verify: diff output was shown
if echo "$SETUP_OUTPUT" | grep -q "Config diff"; then
    echo -e "${GREEN}PASS${NC}: Diff output displayed"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: No diff output in merge mode"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 26b: config.yaml merge - root_dirs and doc_types_map preserved"
echo "=================================================="

setup_test_project

# First install (with .doc_structure.yaml → root_dirs and doc_types_map are set)
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify root_dirs was set by first install
RULES_DIRS=$(grep -c "^  root_dirs:" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "root_dirs set after first install" "2" "$RULES_DIRS"

# Run setup again with 'm' (merge)
echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: root_dirs is still present in merged config
RULES_DIRS_AFTER=$(grep -c "^  root_dirs:" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "root_dirs preserved after merge" "2" "$RULES_DIRS_AFTER"

# Verify: doc_types_map is still present in merged config
DOC_TYPES_AFTER=$(grep -c "^  doc_types_map:" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "doc_types_map preserved after merge" "2" "$DOC_TYPES_AFTER"

# Verify: actual directory path value is preserved
RULES_PATH=$(grep -c -- "- rules/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "rules/ path preserved after merge" "1" "$([[ $RULES_PATH -ge 1 ]] && echo 1 || echo 0)"

echo ""

# ==================================================
echo "=================================================="
echo "Test 26c: config.yaml merge - exclude patterns preserved"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add exclude pattern to rules section
$PYTHON3 -c "
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
lines = content.split('\n')
result = []
replaced = False
for line in lines:
    if not replaced and line.strip() == 'exclude: []':
        result.append('    exclude:')
        result.append('      - archive/')
        result.append('      - draft/')
        replaced = True
    else:
        result.append(line)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write('\n'.join(result))
"

# Verify exclude was set
BEFORE_EXCLUDE=$(grep -c "archive/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "exclude pattern set before merge" "1" "$([[ $BEFORE_EXCLUDE -ge 1 ]] && echo 1 || echo 0)"

# Run setup again with 'm' (merge)
echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: exclude patterns are preserved
EXCLUDE_AFTER=$(grep -c "archive/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "exclude pattern 'archive/' preserved after merge" "1" "$([[ $EXCLUDE_AFTER -ge 1 ]] && echo 1 || echo 0)"

echo ""

# ==================================================
echo "=================================================="
echo "Test 26c-2: config.yaml merge - exclude in inline list format preserved"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add exclude pattern in inline YAML list format (edge case)
$PYTHON3 -c "
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
# Replace first 'exclude: []' with inline list format
import re
replaced = False
lines = content.split('\n')
result = []
for line in lines:
    if not replaced and line.strip() == 'exclude: []':
        result.append('    exclude: [inline_archive/, inline_draft/]')
        replaced = True
    else:
        result.append(line)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write('\n'.join(result))
"

# Verify inline exclude was set
BEFORE_INLINE=$(grep -c "inline_archive/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "inline exclude set before merge" "1" "$([[ $BEFORE_INLINE -ge 1 ]] && echo 1 || echo 0)"

# Run setup again with 'm' (merge)
echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: inline exclude patterns are preserved after merge
EXCLUDE_INLINE_AFTER=$(grep -c "inline_archive/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "inline exclude 'inline_archive/' preserved after merge" "1" "$([[ $EXCLUDE_INLINE_AFTER -ge 1 ]] && echo 1 || echo 0)"

echo ""

# ==================================================
echo "=================================================="
echo "Test 26c-3: config.yaml merge - section-level exclude migrated to patterns.exclude"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Add section-level exclude (indent=2, directly under specs) - legacy format
$PYTHON3 -c "
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
# Insert section-level exclude after root_dirs block in specs section
lines = content.split('\n')
result = []
in_specs = False
inserted = False
for i, line in enumerate(lines):
    result.append(line)
    if line.startswith('specs:'):
        in_specs = True
    elif in_specs and not inserted and line.strip().startswith('toc_file:'):
        # Insert section-level exclude before toc_file
        result.insert(len(result) - 1, '  exclude:')
        result.insert(len(result) - 1, '    - section_plugins/')
        result.insert(len(result) - 1, '    - section_reference/')
        inserted = True
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write('\n'.join(result))
"

# Verify section-level exclude was set
BEFORE_SECTION=$(grep -c "section_plugins/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "section-level exclude set before merge" "1" "$([[ $BEFORE_SECTION -ge 1 ]] && echo 1 || echo 0)"

# Run setup again with 'm' (merge)
echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: section-level excludes are preserved in patterns.exclude after merge
AFTER_SECTION=$(grep -c "section_plugins/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || true)
test_result "section-level exclude migrated to patterns.exclude after merge" "1" "$([[ $AFTER_SECTION -ge 1 ]] && echo 1 || echo 0)"

# Verify: now under patterns.exclude (not at section level)
UNDER_PATTERNS=$($PYTHON3 -c "
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
lines = content.split('\n')
in_patterns = False
for line in lines:
    if line.strip() == 'patterns:' and '    ' not in line[:4]:
        in_patterns = True
    elif in_patterns and 'section_plugins/' in line:
        print('1')
        exit()
    elif in_patterns and line.strip() and not line.startswith('    '):
        in_patterns = False
print('0')
" 2>/dev/null || echo 0)
test_result "exclude is now under patterns (not section level)" "1" "$UNDER_PATTERNS"

echo ""

# ==================================================
echo "=================================================="
echo "Test 26d: config.yaml merge - root_dirs preserved WITHOUT .doc_structure.yaml"
echo "=================================================="

# This test verifies merge_config.py works independently of import_doc_structure.py.
# Tests 26b/26c have .doc_structure.yaml which causes import_doc_structure.py to
# restore root_dirs as a fallback even if merge_config.py fails.
# This test has NO .doc_structure.yaml, so only merge_config.py can preserve root_dirs.

cleanup
mkdir -p "$TEST_PROJECT/rules" "$TEST_PROJECT/specs"
echo "# Test Rule" > "$TEST_PROJECT/rules/test.md"
echo "# Test Spec" > "$TEST_PROJECT/specs/test.md"
# Note: intentionally NO .doc_structure.yaml

# First install (no .doc_structure.yaml → root_dirs stays commented out)
echo -e "c\nopus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Manually set root_dirs in config (simulating user who ran /setup-config manually)
$PYTHON3 -c "
content = open('$TEST_PROJECT/.claude/doc-advisor/config.yaml').read()
# Replace '# root_dirs: []' for rules section (first occurrence)
import re
# Replace only the first occurrence (rules section)
content = re.sub(
    r'(# === rules configuration ===.*?)(\s*# root_dirs: \[\])',
    lambda m: m.group(1) + '\n  root_dirs:\n    - rules/',
    content, count=1, flags=re.DOTALL
)
# Replace only the first occurrence of # doc_types_map: {} (rules section)
content = re.sub(
    r'  # doc_types_map: \{\}.*',
    '  doc_types_map:\n    rules/: rule',
    content, count=1
)
open('$TEST_PROJECT/.claude/doc-advisor/config.yaml', 'w').write(content)
"

# Verify root_dirs was manually set
RULES_DIRS_BEFORE=$(grep -c "^  root_dirs:" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "root_dirs manually set before merge" "1" "$RULES_DIRS_BEFORE"

# Run setup again with 'm' (merge) — NO .doc_structure.yaml, so only merge_config.py helps
echo -e "opus\nm" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: root_dirs preserved by merge_config.py (not fallback import_doc_structure.py)
RULES_DIRS_AFTER=$(grep -c "^  root_dirs:" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "root_dirs preserved after merge (no .doc_structure.yaml)" "1" "$RULES_DIRS_AFTER"

# Verify: the actual path value is preserved
RULES_PATH=$(grep -c -- "- rules/" "$TEST_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "rules/ path value preserved (no .doc_structure.yaml)" "1" "$([[ $RULES_PATH -ge 1 ]] && echo 1 || echo 0)"

echo ""

# ==================================================
echo "=================================================="
echo "Test 26e: config.yaml merge from external directory (README scenario)"
echo "=================================================="

# This test reproduces the exact README usage pattern:
#   cd DocAdvisor-CC && bash setup.sh /path/to/your-project
# where the target project is OUTSIDE DocAdvisor-CC.
# Without the (cd "$TARGET_DIR" && ...) fix, merge_config.py would fail with
# "Path traversal detected" because Path.cwd() (= DocAdvisor-CC) != target_dir.

EXTERNAL_PROJECT="$(mktemp -d "$PROJECT_ROOT/../test_external_XXXXXX")"
trap "rm -rf '$EXTERNAL_PROJECT'" EXIT

mkdir -p "$EXTERNAL_PROJECT/rules" "$EXTERNAL_PROJECT/specs"
echo "# Rule" > "$EXTERNAL_PROJECT/rules/test.md"
echo "# Spec" > "$EXTERNAL_PROJECT/specs/test.md"
cat > "$EXTERNAL_PROJECT/.doc_structure.yaml" << 'DOCEOF'
rules:
  rule:
    paths: [rules/]
specs:
  spec:
    paths: [specs/]
DOCEOF

# First install from PROJECT_ROOT (simulating README usage: cd DocAdvisor-CC && bash setup.sh /path/...)
echo "opus" | (cd "$PROJECT_ROOT" && bash "$PROJECT_ROOT/setup.sh" "$EXTERNAL_PROJECT") > /dev/null 2>&1

# Verify root_dirs was set
DIRS_AFTER_FIRST=$(grep -c "^  root_dirs:" "$EXTERNAL_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "root_dirs set after first install (external dir)" "2" "$DIRS_AFTER_FIRST"

# Add custom exclude pattern
$PYTHON3 -c "
content = open('$EXTERNAL_PROJECT/.claude/doc-advisor/config.yaml').read()
lines = content.split('\n')
result = []
replaced = False
for line in lines:
    if not replaced and line.strip() == 'exclude: []':
        result.append('    exclude:')
        result.append('      - archive/')
        replaced = True
    else:
        result.append(line)
open('$EXTERNAL_PROJECT/.claude/doc-advisor/config.yaml', 'w').write('\n'.join(result))
"

# Second install with [m] from PROJECT_ROOT (same README usage pattern)
echo -e "opus\nm" | (cd "$PROJECT_ROOT" && bash "$PROJECT_ROOT/setup.sh" "$EXTERNAL_PROJECT") > /dev/null 2>&1

# Verify root_dirs preserved after merge (failed if path traversal check triggered)
DIRS_AFTER_MERGE=$(grep -c "^  root_dirs:" "$EXTERNAL_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "root_dirs preserved after merge (external dir)" "2" "$DIRS_AFTER_MERGE"

# Verify exclude preserved (only merge_config.py can do this; import_doc_structure.py cannot)
EXCLUDE_AFTER=$(grep -c "archive/" "$EXTERNAL_PROJECT/.claude/doc-advisor/config.yaml" 2>/dev/null || echo 0)
test_result "exclude pattern preserved after merge (external dir)" "1" "$([[ $EXCLUDE_AFTER -ge 1 ]] && echo 1 || echo 0)"

echo ""

# ==================================================
echo "=================================================="
echo "Test 27: validate_rules_toc.py abnormal input handling"
echo "=================================================="

setup_test_project

# Run setup to install scripts
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
TOC_DIR="$TEST_PROJECT/.claude/doc-advisor/toc/rules"
mkdir -p "$TOC_DIR"

# Detect Python command (same as other test suites)
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' "$TEST_PROJECT/.claude/doc-advisor/docs/toc_orchestrator.md" 2>/dev/null | head -1 || echo "$PYTHON3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")

# Case 1: Missing required fields (no title, no keywords)
cat > "$TOC_DIR/rules_toc.yaml" << 'TOCEOF'
docs:
  rules/test.md:
    purpose: "test purpose"
    content_details:
      - "detail 1"
    applicable_tasks:
      - "task 1"
TOCEOF

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_rules_toc.py" --file "$TOC_DIR/rules_toc.yaml" 2>&1)
VALIDATE_EXIT=$?
if [[ $VALIDATE_EXIT -ne 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Validator exits non-zero for missing required fields (title, keywords)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Validator should fail for missing required fields, got exit 0. Output: $VALIDATE_OUTPUT"
    ((FAIL_COUNT++))
fi

# Case 2: Non-existent file reference
cat > "$TOC_DIR/rules_toc.yaml" << 'TOCEOF'
docs:
  rules/nonexistent_file.md:
    title: "Ghost Document"
    purpose: "References a file that does not exist"
    content_details:
      - "detail 1"
    applicable_tasks:
      - "task 1"
    keywords:
      - "test"
TOCEOF

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_rules_toc.py" --file "$TOC_DIR/rules_toc.yaml" 2>&1)
VALIDATE_EXIT=$?
if [[ $VALIDATE_EXIT -ne 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Validator exits non-zero for non-existent file reference"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Validator should fail for non-existent file, got exit 0. Output: $VALIDATE_OUTPUT"
    ((FAIL_COUNT++))
fi

# Case 3: Valid ToC file (sanity check — should pass)
cat > "$TOC_DIR/rules_toc.yaml" << 'TOCEOF'
docs:
  rules/test.md:
    title: "Test Rule"
    purpose: "A test rule document"
    doc_type: "rule"
    content_details:
      - "contains test rules"
    applicable_tasks:
      - "testing"
    keywords:
      - "test"
      - "rule"
TOCEOF

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_rules_toc.py" --file "$TOC_DIR/rules_toc.yaml" 2>&1)
VALIDATE_EXIT=$?
if [[ $VALIDATE_EXIT -eq 0 ]]; then
    echo -e "${GREEN}PASS${NC}: Validator passes for valid ToC file"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Validator should pass for valid ToC, got exit $VALIDATE_EXIT. Output: $VALIDATE_OUTPUT"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 28: root_dirs: [] does not crash (IndexError guard)"
echo "=================================================="

setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' "$TEST_PROJECT/.claude/doc-advisor/docs/toc_orchestrator.md" 2>/dev/null | head -1 || echo "$PYTHON3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")

# Set root_dirs: [] in config.yaml for both sections
$PYTHON3 - "$TEST_PROJECT/.claude/doc-advisor/config.yaml" << 'PYEOF'
import sys, re
path = sys.argv[1]
content = open(path).read()
# Replace "# root_dirs: []" comments with "root_dirs: []"
content = re.sub(r'^\s*#\s*(root_dirs:\s*\[\])', r'  \1', content, flags=re.MULTILINE)
open(path, 'w').write(content)
PYEOF

# create_checksums.py with empty root_dirs should not crash with IndexError
CREATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules 2>&1)
CREATE_EXIT=$?
if echo "$CREATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: create_checksums.py raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: create_checksums.py does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi

# validate_rules_toc.py with empty root_dirs should not crash with IndexError
VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_rules_toc.py" 2>&1)
if echo "$VALIDATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: validate_rules_toc.py raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: validate_rules_toc.py does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi

# validate_specs_toc.py with empty root_dirs should not crash with IndexError
VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_specs_toc.py" 2>&1)
if echo "$VALIDATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: validate_specs_toc.py raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: validate_specs_toc.py does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 29: write_pending.py --error keeps status: pending (not error)"
echo "=================================================="

setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR="$TEST_PROJECT/.claire/doc-advisor/scripts"
SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' "$TEST_PROJECT/.claude/doc-advisor/docs/toc_orchestrator.md" 2>/dev/null | head -1 || echo "$PYTHON3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")

# Create a pending YAML entry
WORK_DIR="$TEST_PROJECT/.claude/doc-advisor/toc/rules/.toc_work"
mkdir -p "$WORK_DIR"
ENTRY_FILE="$WORK_DIR/test_entry.yaml"
cat > "$ENTRY_FILE" << 'ENTRYEOF'
_meta:
  source_file: rules/test.md
  doc_type: rule
  status: pending
  updated_at: null

title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
ENTRYEOF

# Run write_pending.py --error
cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/write_pending.py" \
    --target rules \
    --entry-file ".claude/doc-advisor/toc/rules/.toc_work/test_entry.yaml" \
    --error --error-message "Test error message" > /dev/null 2>&1

STATUS_LINE=$(grep "status:" "$ENTRY_FILE" | head -1)
if echo "$STATUS_LINE" | grep -q "status: pending"; then
    echo -e "${GREEN}PASS${NC}: write_pending.py --error keeps status: pending"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: write_pending.py --error should set status: pending, got: $STATUS_LINE"
    ((FAIL_COUNT++))
fi

ERROR_MSG_LINE=$(grep "error_message:" "$ENTRY_FILE" | head -1)
if [[ -n "$ERROR_MSG_LINE" ]]; then
    echo -e "${GREEN}PASS${NC}: write_pending.py --error preserves error_message field"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: write_pending.py --error should preserve error_message field"
    ((FAIL_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 30: create_checksums.py respects rules.target_glob"
echo "=================================================="

setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' "$TEST_PROJECT/.claude/doc-advisor/docs/toc_orchestrator.md" 2>/dev/null | head -1 || echo "$PYTHON3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")

# Add a non-.md file and set target_glob to *.md only (default)
mkdir -p "$TEST_PROJECT/rules"
echo "# Rule doc" > "$TEST_PROJECT/rules/test_rule.md"
echo "This is a text file" > "$TEST_PROJECT/rules/ignore_me.txt"

# Set rules.root_dirs and target_glob: "**/*.md" in config
$PYTHON3 - "$TEST_PROJECT/.claude/doc-advisor/config.yaml" << 'PYEOF'
import sys, re
path = sys.argv[1]
content = open(path).read()
content = re.sub(r'(rules:\n(?:.*\n)*?\s*)#\s*(root_dirs:\s*\[\])', r'\1root_dirs:\n    - rules/', content)
open(path, 'w').write(content)
PYEOF

# Run create_checksums.py
CHECKSUMS_FILE="$TEST_PROJECT/.claude/doc-advisor/toc/rules/.toc_checksums.yaml"
cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --target rules > /dev/null 2>&1

if [[ -f "$CHECKSUMS_FILE" ]]; then
    # .md file should be included, .txt file should NOT be included
    MD_IN=$(grep -c "test_rule.md" "$CHECKSUMS_FILE" 2>/dev/null; true)
    TXT_IN=$(grep -c "ignore_me.txt" "$CHECKSUMS_FILE" 2>/dev/null; true)
    if [[ "$MD_IN" -ge 1 ]] && [[ "$TXT_IN" -eq 0 ]]; then
        echo -e "${GREEN}PASS${NC}: create_checksums.py rules uses target_glob (*.md included, *.txt excluded)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: create_checksums.py rules target_glob not working. md=$MD_IN txt=$TXT_IN"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: create_checksums.py did not create checksums file"
    ((FAIL_COUNT++))
fi
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
