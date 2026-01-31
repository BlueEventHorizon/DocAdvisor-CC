#!/bin/bash
# Run all test suites
# Usage: ./run_all_tests.sh

# Note: Do not use 'set -e' as individual test failures should not stop the suite

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results array
declare -a TEST_NAMES
declare -a TEST_RESULTS

run_test() {
    local name="$1"
    local script="$2"

    echo ""
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}Running: $name${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""

    TEST_NAMES+=("$name")

    if [[ -x "$SCRIPT_DIR/$script" ]]; then
        if "$SCRIPT_DIR/$script"; then
            TEST_RESULTS+=("PASS")
        else
            TEST_RESULTS+=("FAIL")
        fi
    else
        TEST_RESULTS+=("SKIP")
    fi
}

echo "=================================================="
echo "DocAdvisor-CC Full Test Suite"
echo "=================================================="

cd "$SCRIPT_DIR"

# Make all test scripts executable
chmod +x *.sh 2>/dev/null || true

# Phase 1: Basic tests
run_test "Phase 1: Basic Setup" "test.sh"

# Phase 2: Script unit tests
run_test "Phase 2a: write_pending.py" "test_write_pending.sh"
run_test "Phase 2b: merge_toc.py" "test_merge.sh"
run_test "Phase 2c: create_checksums.py" "test_checksums.sh"
run_test "Phase 2d: should_exclude()" "test_should_exclude.sh"

# Phase 3: Custom directory tests
run_test "Phase 3: Custom Directories" "test_custom_dirs.sh"

# Phase 4: Edge cases
run_test "Phase 4: Edge Cases" "test_edge_cases.sh"

# Count results
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

for result in "${TEST_RESULTS[@]}"; do
    case "$result" in
        PASS) ((PASS_COUNT++)) ;;
        FAIL) ((FAIL_COUNT++)) ;;
        SKIP) ((SKIP_COUNT++)) ;;
    esac
done

# Print summary table
echo ""
echo "=================================================="
echo "Test Results Summary"
echo "=================================================="
echo ""
echo "+----------------------------------+--------+"
echo "| Test Suite                       | Result |"
echo "+----------------------------------+--------+"

for i in "${!TEST_NAMES[@]}"; do
    name="${TEST_NAMES[$i]}"
    result="${TEST_RESULTS[$i]}"

    # Pad name to 32 chars
    padded_name=$(printf "%-32s" "$name")

    # Color the result
    case "$result" in
        PASS) colored_result="${GREEN}PASS${NC}" ;;
        FAIL) colored_result="${RED}FAIL${NC}" ;;
        SKIP) colored_result="${YELLOW}SKIP${NC}" ;;
    esac

    echo -e "| $padded_name | $colored_result   |"
done

echo "+----------------------------------+--------+"
echo ""
echo "=================================================="
echo "Final Summary"
echo "=================================================="
echo ""
echo -e "  ${GREEN}PASS${NC}: $PASS_COUNT"
echo -e "  ${RED}FAIL${NC}: $FAIL_COUNT"
echo -e "  ${YELLOW}SKIP${NC}: $SKIP_COUNT"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    exit 1
fi
