#!/bin/bash
# Test script for merge_rules_toc.py and merge_specs_toc.py
# Usage: ./test_merge.sh

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
echo "merge_toc.py Test Suite"
echo "=================================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Test project: $TEST_PROJECT"
echo ""

# Ensure test project is set up with correct settings
echo "Setting up test project..."
cd "$TEST_PROJECT"
rm -rf .claude .last_setup
# Pass explicit values: rules, specs, requirements, design, plan
echo -e "rules\nspecs\nrequirements\ndesign\nplan" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path
PYTHON_CMD=$(grep -o '/[^"]*python3' .claude/commands/create-rules_toc.md 2>/dev/null | head -1 || echo "python3")
echo "Using Python: $PYTHON_CMD"
echo ""

SCRIPTS_DIR="$TEST_PROJECT/.claude/skills/doc-advisor/scripts"

echo "=================================================="
echo "Test 2-5: merge_rules_toc.py - Full mode"
echo "=================================================="

# Clean and regenerate
rm -f .claude/doc-advisor/rules/rules_toc.yaml
rm -rf .claude/doc-advisor/rules/.toc_work
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || true

# Get pending file and write completed entry
RULES_PENDING=$(ls .claude/doc-advisor/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
if [[ -n "$RULES_PENDING" ]]; then
    $PYTHON_CMD "$SCRIPTS_DIR/write_rules_pending.py" \
        --entry-file "$RULES_PENDING" \
        --title "Coding Standards" \
        --purpose "Define coding practices" \
        --content-details "Naming,Structure,Errors,Testing,Docs" \
        --applicable-tasks "Code review" \
        --keywords "coding,standards,naming,structure,testing" \
        --force 2>/dev/null || true
fi

# Run merge
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/merge_rules_toc.py" --mode full 2>/dev/null || EXIT_CODE=$?

test_result "merge_rules_toc full mode" "0" "$EXIT_CODE"

# Verify output file exists
if [[ -f ".claude/doc-advisor/rules/rules_toc.yaml" ]]; then
    echo -e "${GREEN}PASS${NC}: rules_toc.yaml created"
    ((PASS_COUNT++))

    # Verify content
    if grep -q "docs:" .claude/doc-advisor/rules/rules_toc.yaml; then
        echo -e "${GREEN}PASS${NC}: rules_toc.yaml has docs section"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: rules_toc.yaml missing docs section"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: rules_toc.yaml not created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-6: merge_rules_toc.py - Incremental mode"
echo "=================================================="

# Add another pending entry (simulate new file)
WORK_DIR=".claude/doc-advisor/rules/.toc_work"
mkdir -p "$WORK_DIR"
cat > "$WORK_DIR/rules_new_rule.yaml" << 'EOF'
_meta:
  source_file: rules/new_rule.md
  status: completed
  updated_at: "2026-01-31T00:00:00Z"

title: New Rule
purpose: A new rule for testing incremental merge
content_details:
  - Detail 1
  - Detail 2
  - Detail 3
  - Detail 4
  - Detail 5
applicable_tasks:
  - Task 1
keywords:
  - keyword1
  - keyword2
  - keyword3
  - keyword4
  - keyword5
EOF

# Run incremental merge
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/merge_rules_toc.py" --mode incremental 2>/dev/null || EXIT_CODE=$?

test_result "merge_rules_toc incremental mode" "0" "$EXIT_CODE"

# Verify both entries exist (count lines starting with 2 spaces followed by path)
ENTRY_COUNT=$(grep -cE "^  (rules|specs)/" .claude/doc-advisor/rules/rules_toc.yaml 2>/dev/null | tr -d '[:space:]' || echo "0")
if [[ -z "$ENTRY_COUNT" ]]; then ENTRY_COUNT=0; fi
if [[ "$ENTRY_COUNT" -ge 2 ]]; then
    echo -e "${GREEN}PASS${NC}: Multiple entries merged ($ENTRY_COUNT entries)"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Expected 2+ entries, got $ENTRY_COUNT"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test 2-7: merge_specs_toc.py - Full mode with doc_type"
echo "=================================================="

# Clean and regenerate
rm -f .claude/doc-advisor/specs/specs_toc.yaml
rm -rf .claude/doc-advisor/specs/.toc_work
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_specs.py" --full 2>/dev/null || true

# Get pending files and write completed entries
for SPECS_PENDING in .claude/doc-advisor/specs/.toc_work/*.yaml; do
    if [[ -f "$SPECS_PENDING" ]]; then
        $PYTHON_CMD "$SCRIPTS_DIR/write_specs_pending.py" \
            --entry-file "$SPECS_PENDING" \
            --title "Test Spec Document" \
            --purpose "Testing specs merge" \
            --content-details "Item1,Item2,Item3,Item4,Item5" \
            --applicable-tasks "Testing" \
            --keywords "test,spec,doc,merge,yaml" \
            --force 2>/dev/null || true
    fi
done

# Run merge
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/merge_specs_toc.py" --mode full 2>/dev/null || EXIT_CODE=$?

test_result "merge_specs_toc full mode" "0" "$EXIT_CODE"

# Verify output file exists and has doc_type
if [[ -f ".claude/doc-advisor/specs/specs_toc.yaml" ]]; then
    echo -e "${GREEN}PASS${NC}: specs_toc.yaml created"
    ((PASS_COUNT++))

    # Verify doc_type is preserved
    if grep -q "doc_type:" .claude/doc-advisor/specs/specs_toc.yaml; then
        echo -e "${GREEN}PASS${NC}: specs_toc.yaml has doc_type fields"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: specs_toc.yaml missing doc_type fields"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${RED}FAIL${NC}: specs_toc.yaml not created"
    ((FAIL_COUNT++))
fi
echo ""

echo "=================================================="
echo "Test: merge with --cleanup option"
echo "=================================================="

# Regenerate pending files
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml_rules.py" --full 2>/dev/null || true

# Write and merge with cleanup
RULES_PENDING=$(ls .claude/doc-advisor/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
if [[ -n "$RULES_PENDING" ]]; then
    $PYTHON_CMD "$SCRIPTS_DIR/write_rules_pending.py" \
        --entry-file "$RULES_PENDING" \
        --title "Cleanup Test" \
        --purpose "Test cleanup option" \
        --content-details "a,b,c,d,e" \
        --applicable-tasks "test" \
        --keywords "a,b,c,d,e" \
        --force 2>/dev/null || true
fi

$PYTHON_CMD "$SCRIPTS_DIR/merge_rules_toc.py" --mode full --cleanup 2>/dev/null || true

# Check if .toc_work is cleaned up
if [[ ! -d ".claude/doc-advisor/rules/.toc_work" ]] || [[ -z "$(ls -A .claude/doc-advisor/rules/.toc_work 2>/dev/null)" ]]; then
    echo -e "${GREEN}PASS${NC}: .toc_work cleaned up after merge"
    ((PASS_COUNT++))
else
    echo -e "${YELLOW}WARN${NC}: .toc_work not fully cleaned up (may have pending entries)"
fi
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
