#!/bin/bash
# Local scenario test for installed Codex bridge scripts.
# Created by: k2moons

# Note: Do not use 'set -e' as assertions should report all failures.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_PROJECT="$SCRIPT_DIR/codex_test_project"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1"
    local command="$2"
    if eval "$command"; then
        echo -e "${GREEN}PASS${NC}: $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}FAIL${NC}: $name"
        ((FAIL_COUNT++))
    fi
}

echo "=================================================="
echo "Codex Bridge Local Scenario"
echo "=================================================="
echo ""

cd "$TEST_PROJECT"
rm -rf .codex
"$PROJECT_ROOT/setup_for_codex.sh" "$TEST_PROJECT" >/dev/null || {
    echo -e "${RED}FAIL${NC}: setup_for_codex.sh failed"
    exit 1
}

PYTHON_CMD=python3

if $PYTHON_CMD .codex/doc-advisor/resources/doc-advisor/scripts/create_pending_yaml.py --category rules --full; then
    echo -e "${GREEN}PASS${NC}: create_pending_yaml rules"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: create_pending_yaml rules"
    ((FAIL_COUNT++))
fi

if $PYTHON_CMD .codex/doc-advisor/resources/doc-advisor/scripts/create_pending_yaml.py --category specs --full; then
    echo -e "${GREEN}PASS${NC}: create_pending_yaml specs"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: create_pending_yaml specs"
    ((FAIL_COUNT++))
fi

check "rules pending YAML created under .codex" "ls .codex/doc-advisor/toc/rules/.toc_work/*.yaml >/dev/null 2>&1"
check "specs pending YAML created under .codex" "ls .codex/doc-advisor/toc/specs/.toc_work/*.yaml >/dev/null 2>&1"
check "rules source_file uses fixture path" "grep -q 'source_file: docs/rules/coding.md' .codex/doc-advisor/toc/rules/.toc_work/*.yaml"
check "specs source_file uses fixture path" "grep -q 'source_file: docs/specs/sample/requirements.md' .codex/doc-advisor/toc/specs/.toc_work/*.yaml"
check "no .claude output created by Codex scripts" "[[ ! -d '.claude/doc-advisor' ]]"

echo ""
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"

[[ $FAIL_COUNT -eq 0 ]]
