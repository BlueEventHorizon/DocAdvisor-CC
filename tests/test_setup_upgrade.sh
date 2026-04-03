#!/bin/bash
# Test script for setup.sh upgrade scenarios
# Tests: legacy file deletion, .doc_structure.yaml handling, agent preservation
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
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/: spec
  patterns:
    target_glob: "**/*.md"
    exclude: []
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
test_result "config.yaml NOT created (abolished)" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml" ]] && echo 0 || echo 1)"
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
test_result "config.yaml NOT in doc-advisor/ (abolished)" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml" ]] && echo 0 || echo 1)"
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
echo "Test 4: v5.0 legacy config.yaml removed"
echo "=================================================="

setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create legacy config.yaml
echo "# legacy" > "$TEST_PROJECT/.claude/doc-advisor/config.yaml"

# Re-run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

test_result "config.yaml removed by v5.0 cleanup" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/config.yaml" ]] && echo 0 || echo 1)"
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

# Run setup again
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
SETUP_OUTPUT=$(echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" 2>&1)

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

# Run setup again
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "Test 13: setup-doc-structure skill installed from template"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: setup-doc-structure skill installed
test_result "setup-doc-structure/SKILL.md installed" "1" "$([[ -f "$TEST_PROJECT/.claude/skills/setup-doc-structure/SKILL.md" ]] && echo 1 || echo 0)"
test_result "setup-doc-structure/ dir exists" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/setup-doc-structure" ]] && echo 1 || echo 0)"
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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: old agents removed, new unified agent exists
test_result "Old rules-toc-updater.md removed" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/rules-toc-updater.md" ]] && echo 0 || echo 1)"
test_result "Old specs-toc-updater.md removed" "1" "$([[ -f "$TEST_PROJECT/.claude/agents/specs-toc-updater.md" ]] && echo 0 || echo 1)"
test_result "New toc-updater.md exists" "0" "$([[ -f "$TEST_PROJECT/.claude/agents/toc-updater.md" ]] && echo 0 || echo 1)"
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
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: set_root_dirs.py removed
test_result "set_root_dirs.py removed" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 22: v3.9 full legacy cleanup (all removed files)"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Create all legacy files (simulate pre-3.9 installation + v4.2 classify-docs)
mkdir -p "$TEST_PROJECT/.claude/skills/setup-doc-structure"
echo "# Legacy" > "$TEST_PROJECT/.claude/skills/setup-doc-structure/SKILL.md"
mkdir -p "$TEST_PROJECT/.claude/skills/classify-docs"
echo "# Legacy" > "$TEST_PROJECT/.claude/skills/classify-docs/SKILL.md"
echo "# Legacy" > "$TEST_PROJECT/.claude/doc-advisor/scripts/classify_dirs.py"
echo "# Legacy" > "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py"

# Run setup again
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify all legacy files cleaned up
test_result "setup-doc-structure/ exists after upgrade" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/setup-doc-structure" ]] && echo 1 || echo 0)"
test_result "classify-docs/ removed after upgrade" "1" "$([[ -d "$TEST_PROJECT/.claude/skills/classify-docs" ]] && echo 0 || echo 1)"
test_result "classify_dirs.py exists after upgrade" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/classify_dirs.py" ]] && echo 1 || echo 0)"
test_result "set_root_dirs.py removed in upgrade" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/set_root_dirs.py" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 23: check_doc_structure.sh removed (legacy cleanup)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: check_doc_structure.sh does NOT exist (removed as legacy)
test_result "check_doc_structure.sh not present" "1" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/check_doc_structure.sh" ]] && echo 0 || echo 1)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 24: Skill Error Handling sections (replaces Pre-check)"
echo "=================================================="

# Verify: all 4 skills have Error Handling section and NO check_doc_structure.sh reference
ALL_ERROR_HANDLING_OK=true
for SKILL_NAME in create-rules-toc create-specs-toc query-rules query-specs; do
    SKILL_FILE="$TEST_PROJECT/.claude/skills/$SKILL_NAME/SKILL.md"
    if grep -q "config_required" "$SKILL_FILE" 2>/dev/null && ! grep -q "check_doc_structure.sh" "$SKILL_FILE" 2>/dev/null; then
        echo -e "${GREEN}PASS${NC}: $SKILL_NAME has Error Handling, no check_doc_structure.sh"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $SKILL_NAME Error Handling check failed"
        ((FAIL_COUNT++))
        ALL_ERROR_HANDLING_OK=false
    fi
done
echo ""

# ==================================================
echo "=================================================="
echo "Test 25: ConfigNotReadyError in Python scripts (FR-08)"
echo "=================================================="

setup_test_project

# Run setup
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR_25="$TEST_PROJECT/.claude/doc-advisor/scripts"

# Remove .doc_structure.yaml and default directory to trigger ConfigNotReadyError
rm -f "$TEST_PROJECT/.doc_structure.yaml"
rm -rf "$TEST_PROJECT/rules"

# create_pending_yaml.py should output config_required JSON
OUTPUT=$(cd "$TEST_PROJECT" && /opt/homebrew/bin/python3 "$SCRIPTS_DIR_25/create_pending_yaml.py" --category rules 2>/dev/null)
if echo "$OUTPUT" | grep -q '"status": "config_required"'; then
    echo -e "${GREEN}PASS${NC}: create_pending_yaml.py outputs config_required when not configured"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected config_required JSON, got: $OUTPUT"
    ((FAIL_COUNT++))
fi

# create_checksums.py should output config_required JSON
OUTPUT=$(cd "$TEST_PROJECT" && /opt/homebrew/bin/python3 "$SCRIPTS_DIR_25/create_checksums.py" --category rules 2>/dev/null)
if echo "$OUTPUT" | grep -q '"status": "config_required"'; then
    echo -e "${GREEN}PASS${NC}: create_checksums.py outputs config_required when not configured"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected config_required JSON, got: $OUTPUT"
    ((FAIL_COUNT++))
fi
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

PYTHON_CMD=python3

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

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_toc.py" --category rules --file "$TOC_DIR/rules_toc.yaml" 2>&1)
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

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_toc.py" --category rules --file "$TOC_DIR/rules_toc.yaml" 2>&1)
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

VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_toc.py" --category rules --file "$TOC_DIR/rules_toc.yaml" 2>&1)
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
PYTHON_CMD=python3

# Set root_dirs: [] in .doc_structure.yaml for both sections
cat > "$TEST_PROJECT/.doc_structure.yaml" << 'DOCEOF'
# doc_structure_version: 3.0

rules:
  root_dirs: []
  doc_types_map: {}
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs: []
  doc_types_map: {}
  patterns:
    target_glob: "**/*.md"
    exclude: []
DOCEOF

# create_checksums.py with empty root_dirs should not crash with IndexError
CREATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --category rules 2>&1)
CREATE_EXIT=$?
if echo "$CREATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: create_checksums.py raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: create_checksums.py does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi

# validate_toc.py (rules) with empty root_dirs should not crash with IndexError
VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_toc.py" --category rules 2>&1)
if echo "$VALIDATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: validate_toc.py --category rules raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: validate_toc.py --category rules does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi

# validate_toc.py (specs) with empty root_dirs should not crash with IndexError
VALIDATE_OUTPUT=$(cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/validate_toc.py" --category specs 2>&1)
if echo "$VALIDATE_OUTPUT" | grep -q "IndexError"; then
    echo -e "${RED}FAIL${NC}: validate_toc.py --category specs raised IndexError with root_dirs: []"
    ((FAIL_COUNT++))
else
    echo -e "${GREEN}PASS${NC}: validate_toc.py --category specs does not raise IndexError with root_dirs: []"
    ((PASS_COUNT++))
fi
echo ""

# ==================================================
echo "=================================================="
echo "Test 29: write_pending.py --error keeps status: pending (not error)"
echo "=================================================="

setup_test_project
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"
PYTHON_CMD=python3

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
    --category rules \
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
PYTHON_CMD=python3

# Add a non-.md file and set target_glob to *.md only (default)
mkdir -p "$TEST_PROJECT/rules"
echo "# Rule doc" > "$TEST_PROJECT/rules/test_rule.md"
echo "This is a text file" > "$TEST_PROJECT/rules/ignore_me.txt"

# .doc_structure.yaml already has rules root_dirs and target_glob: "**/*.md"

# Run create_checksums.py
CHECKSUMS_FILE="$TEST_PROJECT/.claude/doc-advisor/toc/rules/.toc_checksums.yaml"
cd "$TEST_PROJECT" && $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --category rules > /dev/null 2>&1

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
echo "=================================================="
echo "Test 31: Smart copy - unchanged files are skipped"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Record file contents (with version lines) after first install
SKILL_FILE="$TEST_PROJECT/.claude/skills/query-rules/SKILL.md"
SCRIPT_FILE="$TEST_PROJECT/.claude/doc-advisor/scripts/toc_utils.py"
AGENT_FILE="$TEST_PROJECT/.claude/agents/toc-updater.md"

SKILL_BEFORE=$(cat "$SKILL_FILE")
SCRIPT_BEFORE=$(cat "$SCRIPT_FILE")
AGENT_BEFORE=$(cat "$AGENT_FILE")

# Run setup again (same version, no content changes → should skip all files)
SMART_OUTPUT=$(echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" 2>&1)

# Files should be identical (not overwritten)
SKILL_AFTER=$(cat "$SKILL_FILE")
SCRIPT_AFTER=$(cat "$SCRIPT_FILE")
AGENT_AFTER=$(cat "$AGENT_FILE")

test_result "Smart copy: SKILL.md unchanged after re-install" "0" "$([[ "$SKILL_BEFORE" = "$SKILL_AFTER" ]] && echo 0 || echo 1)"
test_result "Smart copy: toc_utils.py unchanged after re-install" "0" "$([[ "$SCRIPT_BEFORE" = "$SCRIPT_AFTER" ]] && echo 0 || echo 1)"
test_result "Smart copy: toc-updater.md unchanged after re-install" "0" "$([[ "$AGENT_BEFORE" = "$AGENT_AFTER" ]] && echo 0 || echo 1)"

# Verify "Skipped" messages appear in output
SKIP_COUNT=$(echo "$SMART_OUTPUT" | grep -c "Skipped (unchanged)" || true)
test_result "Smart copy: skip messages shown (>0)" "1" "$([[ $SKIP_COUNT -gt 0 ]] && echo 1 || echo 0)"
echo ""

# ==================================================
echo "=================================================="
echo "Test 32: Smart copy - changed files are updated"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Modify a template file to simulate content change
ORIG_TEMPLATE="$PROJECT_ROOT/templates/skills/query-rules/SKILL.md"
ORIG_CONTENT=$(cat "$ORIG_TEMPLATE")
echo "# Smart copy test marker" >> "$ORIG_TEMPLATE"

# Run setup again
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: modified template was copied
MARKER_FOUND=$(grep -c "Smart copy test marker" "$TEST_PROJECT/.claude/skills/query-rules/SKILL.md" 2>/dev/null || echo 0)
test_result "Smart copy: changed file is updated" "1" "$MARKER_FOUND"

# Verify: unchanged file was NOT overwritten (version stays the same)
UTILS_VERSION=$(grep 'doc-advisor-version-xK9XmQ:' "$TEST_PROJECT/.claude/doc-advisor/scripts/toc_utils.py" | awk '{print $NF}')
test_result "Smart copy: unchanged file keeps its version" "$CURRENT_VERSION" "$UTILS_VERSION"

# Restore original template
printf '%s\n' "$ORIG_CONTENT" > "$ORIG_TEMPLATE"
echo ""

# ==================================================
echo "=================================================="
echo "Test 33: Smart copy - new files are always copied"
echo "=================================================="

setup_test_project

# First install
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Remove one file to simulate "new file" scenario
rm -f "$TEST_PROJECT/.claude/doc-advisor/scripts/validate_toc.py"

# Run setup again
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT" > /dev/null 2>&1

# Verify: file is re-created
test_result "Smart copy: deleted file re-created" "0" "$([[ -f "$TEST_PROJECT/.claude/doc-advisor/scripts/validate_toc.py" ]] && echo 0 || echo 1)"
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
