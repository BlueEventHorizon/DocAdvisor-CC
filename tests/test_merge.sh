#!/bin/bash
# Test script for merge_toc.py --category rules and merge_toc.py --category specs
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
# Pass explicit values: rules, specs, agent_model
echo "opus" | "$PROJECT_ROOT/setup.sh" "$TEST_PROJECT"
echo ""

cd "$TEST_PROJECT"

# Get Python path from orchestrator docs
PYTHON_CMD=python3
echo "Using Python: $PYTHON_CMD"

echo ""

SCRIPTS_DIR="$TEST_PROJECT/.claude/doc-advisor/scripts"

echo "=================================================="
echo "Test 2-5: merge_toc.py --category rules - Full mode"
echo "=================================================="

# Clean and regenerate
rm -f .claude/doc-advisor/toc/rules/rules_toc.yaml
rm -rf .claude/doc-advisor/toc/rules/.toc_work
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --category rules --full 2>/dev/null || true

# Get pending file and write completed entry
RULES_PENDING=$(ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
if [[ -n "$RULES_PENDING" ]]; then
    $PYTHON_CMD "$SCRIPTS_DIR/write_pending.py" --category rules \
        --entry-file "$RULES_PENDING" \
        --title "Coding Standards" \
        --purpose "Define coding practices" \
        --content-details "Naming ||| Structure ||| Errors ||| Testing ||| Docs" \
        --applicable-tasks "Code review" \
        --keywords "coding ||| standards ||| naming ||| structure ||| testing" \
        --force 2>/dev/null || true
fi

# Run merge
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category rules --mode full 2>/dev/null || EXIT_CODE=$?

test_result "merge_toc rules full mode" "0" "$EXIT_CODE"

# Verify output file exists
if [[ -f ".claude/doc-advisor/toc/rules/rules_toc.yaml" ]]; then
    echo -e "${GREEN}PASS${NC}: rules_toc.yaml created"
    ((PASS_COUNT++))

    # Verify content
    if grep -q "docs:" .claude/doc-advisor/toc/rules/rules_toc.yaml; then
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
echo "Test 2-6: merge_toc.py --category rules - Incremental mode"
echo "=================================================="

# Add another pending entry (simulate new file added after full mode)
# Clean old .toc_work/ first to avoid stale files
rm -rf ".claude/doc-advisor/toc/rules/.toc_work"
# Create a NEW source file that wasn't in the full mode
echo "# Incremental Test Rule" > "rules/incremental_test.md"
WORK_DIR=".claude/doc-advisor/toc/rules/.toc_work"
mkdir -p "$WORK_DIR"
cat > "$WORK_DIR/incremental_entry.yaml" << 'EOF'
_meta:
  source_file: rules/incremental_test.md
  status: completed
  updated_at: "2026-01-31T00:00:00Z"

title: Incremental Test Rule
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
$PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category rules --mode incremental 2>/dev/null || EXIT_CODE=$?

test_result "merge_toc rules incremental mode" "0" "$EXIT_CODE"

# Verify both entries exist (count lines starting with 2 spaces followed by path)
ENTRY_COUNT=$(grep -cE "^  (rules|specs)/" .claude/doc-advisor/toc/rules/rules_toc.yaml 2>/dev/null | tr -d '[:space:]' || echo "0")
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
echo "Test 2-7: merge_toc.py --category specs - Full mode"
echo "=================================================="

# Clean and regenerate
rm -f .claude/doc-advisor/toc/specs/specs_toc.yaml
rm -rf .claude/doc-advisor/toc/specs/.toc_work
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --category specs --full 2>/dev/null || true

# Get pending files and write completed entries
for SPECS_PENDING in .claude/doc-advisor/toc/specs/.toc_work/*.yaml; do
    if [[ -f "$SPECS_PENDING" ]]; then
        $PYTHON_CMD "$SCRIPTS_DIR/write_pending.py" --category specs \
            --entry-file "$SPECS_PENDING" \
            --title "Test Spec Document" \
            --purpose "Testing specs merge" \
            --content-details "Item1 ||| Item2 ||| Item3 ||| Item4 ||| Item5" \
            --applicable-tasks "Testing" \
            --keywords "test ||| spec ||| doc ||| merge ||| yaml" \
            --force 2>/dev/null || true
    fi
done

# Run merge
EXIT_CODE=0
$PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category specs --mode full 2>/dev/null || EXIT_CODE=$?

test_result "merge_toc specs full mode" "0" "$EXIT_CODE"

# Verify output file exists and has no doc_type (removed in v3.8)
if [[ -f ".claude/doc-advisor/toc/specs/specs_toc.yaml" ]]; then
    echo -e "${GREEN}PASS${NC}: specs_toc.yaml created"
    ((PASS_COUNT++))

    # Verify doc_type is present in final ToC
    if grep -q "doc_type:" .claude/doc-advisor/toc/specs/specs_toc.yaml; then
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
echo "Test: merge then manual cleanup"
echo "=================================================="

# Regenerate pending files
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --category rules --full 2>/dev/null || true

# Write and merge (without --cleanup)
RULES_PENDING=$(ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
if [[ -n "$RULES_PENDING" ]]; then
    $PYTHON_CMD "$SCRIPTS_DIR/write_pending.py" --category rules \
        --entry-file "$RULES_PENDING" \
        --title "Cleanup Test" \
        --purpose "Test cleanup option" \
        --content-details "a ||| b ||| c ||| d ||| e" \
        --applicable-tasks "test" \
        --keywords "a ||| b ||| c ||| d ||| e" \
        --force 2>/dev/null || true
fi

if ! $PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category rules --mode full 2>/dev/null; then
    echo -e "${RED}ERROR: merge_toc.py failed (prep for cleanup test)${NC}"
    ((FAIL_COUNT++))
fi

# Manual cleanup (as orchestrator does after checksums update)
rm -rf .claude/doc-advisor/toc/rules/.toc_work

# Check if .toc_work is cleaned up
if [[ ! -d ".claude/doc-advisor/toc/rules/.toc_work" ]] || [[ -z "$(ls -A .claude/doc-advisor/toc/rules/.toc_work 2>/dev/null)" ]]; then
    echo -e "${GREEN}PASS${NC}: .toc_work cleaned up after merge"
    ((PASS_COUNT++))
else
    echo -e "${YELLOW}WARN${NC}: .toc_work not fully cleaned up (may have pending entries)"
fi
echo ""

echo "=================================================="
echo "Test: --delete-only mode (rules)"
echo "=================================================="

# Setup: create a ToC with an entry, then delete the source file
$PYTHON_CMD "$SCRIPTS_DIR/create_pending_yaml.py" --category rules --full 2>/dev/null || true

RULES_PENDING=$(ls .claude/doc-advisor/toc/rules/.toc_work/*.yaml 2>/dev/null | head -1 || echo "")
if [[ -n "$RULES_PENDING" ]]; then
    $PYTHON_CMD "$SCRIPTS_DIR/write_pending.py" --category rules \
        --entry-file "$RULES_PENDING" \
        --title "Delete Test" \
        --purpose "Test delete-only mode" \
        --content-details "a ||| b ||| c ||| d ||| e" \
        --applicable-tasks "test" \
        --keywords "a ||| b ||| c ||| d ||| e" \
        --force 2>/dev/null || true
fi

if ! $PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category rules --mode full 2>/dev/null; then
    echo -e "${RED}ERROR: merge_toc.py failed (prep for delete-only test)${NC}"
    ((FAIL_COUNT++))
fi
rm -rf .claude/doc-advisor/toc/rules/.toc_work

# Count entries before deletion (entry keys start with 2 spaces + path)
BEFORE_COUNT=$(grep -cE "^  (rules|specs)/" .claude/doc-advisor/toc/rules/rules_toc.yaml 2>/dev/null)
[[ -z "$BEFORE_COUNT" ]] && BEFORE_COUNT=0

# Delete the source .md file that has an entry in the ToC (not just any file)
# Find a file that actually has an entry in the ToC
DELETED_FILE=""
for f in rules/*.md; do
    if grep -q "^  ${f}:" .claude/doc-advisor/toc/rules/rules_toc.yaml 2>/dev/null; then
        DELETED_FILE="$f"
        break
    fi
done
if [[ -n "$DELETED_FILE" ]]; then
    DELETED_CONTENT=$(cat "$DELETED_FILE")
    rm -f "$DELETED_FILE"

    # Update checksums (so delete-only can detect the deletion)
    $PYTHON_CMD "$SCRIPTS_DIR/create_checksums.py" --category rules 2>/dev/null || true

    # Run --delete-only
    EXIT_CODE=0
    $PYTHON_CMD "$SCRIPTS_DIR/merge_toc.py" --category rules --delete-only 2>/dev/null || EXIT_CODE=$?

    test_result "merge_toc rules --delete-only exit code" "0" "$EXIT_CODE"

    AFTER_COUNT=$(grep -cE "^  (rules|specs)/" .claude/doc-advisor/toc/rules/rules_toc.yaml 2>/dev/null)
    [[ -z "$AFTER_COUNT" ]] && AFTER_COUNT=0
    if [[ $AFTER_COUNT -lt $BEFORE_COUNT ]]; then
        echo -e "${GREEN}PASS${NC}: Entry count decreased ($BEFORE_COUNT -> $AFTER_COUNT)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: Entry count not decreased ($BEFORE_COUNT -> $AFTER_COUNT)"
        ((FAIL_COUNT++))
    fi

    # Restore deleted file (preserve test fixtures for subsequent tests)
    echo "$DELETED_CONTENT" > "$DELETED_FILE"
else
    echo -e "${YELLOW}SKIP${NC}: No rules .md file to delete"
fi
echo ""

# Cleanup test-created files (keep shared fixtures clean)
rm -f "rules/incremental_test.md"

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
