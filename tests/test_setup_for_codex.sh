#!/bin/bash
# Test setup_for_codex.sh project-local bridge installation.
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
echo "setup_for_codex.sh Test"
echo "=================================================="
echo ""

cd "$TEST_PROJECT"
rm -rf .codex
cat > AGENTS.md <<'EOF'
# Codex Test Project

This file has project-owned content that must be preserved by setup_for_codex.sh.
EOF

if "$PROJECT_ROOT/setup_for_codex.sh" "$TEST_PROJECT"; then
    echo -e "${GREEN}PASS${NC}: setup_for_codex.sh exits successfully"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: setup_for_codex.sh exits successfully"
    ((FAIL_COUNT++))
fi

check "skills installed" "[[ -f '.codex/doc-advisor/skills/create-rules-toc/SKILL.md' && -f '.codex/doc-advisor/skills/setup-doc-structure/SKILL.md' ]]"
check "resources installed" "[[ -f '.codex/doc-advisor/resources/doc-advisor/scripts/create_pending_yaml.py' && -f '.codex/doc-advisor/resources/forge/scripts/doc_structure/classify_dirs.py' ]]"
check "source version written" "[[ -f '.codex/doc-advisor/.source_version' ]]"
check "AGENTS bridge section added" "grep -q 'doc-advisor-codex-bridge-start' AGENTS.md && grep -q 'rules ToC update' AGENTS.md"
check "project AGENTS content preserved" "grep -q 'project-owned content' AGENTS.md"
check "disabled skills absent" "[[ ! -d '.codex/doc-advisor/skills/create-code-index' && ! -d '.codex/doc-advisor/skills/query-code' ]]"
check "forge monitor absent" "[[ ! -d '.codex/doc-advisor/resources/forge/scripts/monitor' ]]"
check "no Claude-specific references in install" "! grep -R -n -E '\\\$\\{CLAUDE_PLUGIN_ROOT\\}|/doc-advisor:|/forge:|AskUserQuestion|Task\\(subagent_type:' .codex/doc-advisor >/dev/null 2>&1"

"$PROJECT_ROOT/setup_for_codex.sh" "$TEST_PROJECT" >/dev/null
START_COUNT=$(grep -c 'doc-advisor-codex-bridge-start' AGENTS.md || true)
END_COUNT=$(grep -c 'doc-advisor-codex-bridge-end' AGENTS.md || true)
check "AGENTS bridge section is idempotent" "[[ '$START_COUNT' == '1' && '$END_COUNT' == '1' ]]"

echo ""
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"

[[ $FAIL_COUNT -eq 0 ]]
