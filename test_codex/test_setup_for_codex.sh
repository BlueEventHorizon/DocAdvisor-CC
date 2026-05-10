#!/bin/bash
# Test setup_for_codex.sh environment-wide Skill installation.
# Created by: k2moons

# Note: Do not use 'set -e' as assertions should report all failures.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_FIXTURE="$SCRIPT_DIR/codex_test_project"
TEST_PROJECT="$SCRIPT_DIR/codex_setup_project"
TEST_HOME="$SCRIPT_DIR/codex_setup_home"
CODEX_HOME_DIR="$TEST_HOME/.codex"
SKILLS_DIR="$CODEX_HOME_DIR/skills"
RESOURCE_ROOT="$CODEX_HOME_DIR/doc-advisor"
RESOURCES_DIR="$RESOURCE_ROOT/resources"

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

rm -rf "$TEST_PROJECT" "$TEST_HOME"
cp -R "$TEST_FIXTURE" "$TEST_PROJECT"

cd "$TEST_PROJECT"
rm -rf .codex
mkdir -p .codex/skills/create-rules-toc .codex/resources/doc-advisor .codex/doc-advisor
touch .codex/skills/create-rules-toc/SKILL.md .codex/resources/doc-advisor/old.txt .codex/doc-advisor/old.txt
cat > AGENTS.md <<'EOF'
# Codex Test Project

This file has project-owned content that must be preserved by setup_for_codex.sh.
EOF

if HOME="$TEST_HOME" CODEX_HOME="$CODEX_HOME_DIR" "$PROJECT_ROOT/setup_for_codex.sh" --project "$TEST_PROJECT"; then
    echo -e "${GREEN}PASS${NC}: setup_for_codex.sh exits successfully"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: setup_for_codex.sh exits successfully"
    ((FAIL_COUNT++))
fi

check "skill install metadata written" "[[ -f '$RESOURCE_ROOT/install.yaml' && -f '$RESOURCE_ROOT/manifest.yaml' ]]"
check "Codex skills installed" "[[ -f '$SKILLS_DIR/create-rules-toc/SKILL.md' && -f '$SKILLS_DIR/setup-doc-structure/SKILL.md' && -f '$SKILLS_DIR/start-requirements/SKILL.md' && -f '$SKILLS_DIR/start-design/SKILL.md' && -f '$SKILLS_DIR/start-plan/SKILL.md' ]]"
check "shared resources installed" "[[ -f '$RESOURCES_DIR/doc-advisor/scripts/create_pending_yaml.py' && -f '$RESOURCES_DIR/forge/scripts/doc_structure/classify_dirs.py' && -f '$RESOURCES_DIR/forge/docs/codex_confirmation_protocol.md' ]]"
check "global resource root has no runtime state" "[[ ! -d '$RESOURCE_ROOT/state' && ! -d '$RESOURCE_ROOT/toc' && ! -d '$RESOURCE_ROOT/index' ]]"
check "global resources have no Python cache after install" "! find '$RESOURCES_DIR' -name '__pycache__' -o -name '*.pyc' | grep -q ."
check "personal marketplace not written" "[[ ! -e '$TEST_HOME/.agents/plugins/marketplace.json' ]]"
check "project install metadata written" "[[ -f '.codex/installs/doc-advisor.yaml' ]]"
check "state directories created" "[[ -d '.codex/state/doc-advisor/toc/rules' && -d '.codex/state/doc-advisor/index/specs' ]]"
check "AGENTS managed section added" "grep -q 'doc-advisor-codex-bridge-start' AGENTS.md && grep -q 'rules ToC update' AGENTS.md && grep -q 'requirements authoring' AGENTS.md"
check "project AGENTS content preserved" "grep -q 'project-owned content' AGENTS.md"
check "legacy project-local skills/resources removed" "[[ ! -d '.codex/skills' && ! -d '.codex/resources' && ! -d '.codex/doc-advisor' ]]"
check "disabled skills absent" "[[ ! -d '$SKILLS_DIR/create-code-index' && ! -d '$SKILLS_DIR/query-code' ]]"
check "forge monitor absent" "[[ ! -d '$RESOURCES_DIR/forge/scripts/monitor' ]]"
check "no invalid references in Skill install" "! grep -R -n -E '\\\$\\{CLAUDE_PLUGIN_ROOT\\}|DOC_ADVISOR_PLUGIN_ROOT|/doc-advisor:|/forge:|AskUserQuestion|Task\\(subagent_type:|\\.codex/resources/|\\.codex/skills/' '$SKILLS_DIR/create-rules-toc' '$SKILLS_DIR/create-specs-toc' '$SKILLS_DIR/query-rules' '$SKILLS_DIR/query-specs' '$SKILLS_DIR/setup-doc-structure' '$SKILLS_DIR/start-requirements' '$SKILLS_DIR/start-design' '$SKILLS_DIR/start-plan' '$RESOURCES_DIR' >/dev/null 2>&1"

HOME="$TEST_HOME" CODEX_HOME="$CODEX_HOME_DIR" "$PROJECT_ROOT/setup_for_codex.sh" --project "$TEST_PROJECT" >/dev/null
START_COUNT=$(grep -c 'doc-advisor-codex-bridge-start' AGENTS.md || true)
END_COUNT=$(grep -c 'doc-advisor-codex-bridge-end' AGENTS.md || true)
check "AGENTS managed section is idempotent" "[[ '$START_COUNT' == '1' && '$END_COUNT' == '1' ]]"

echo ""
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"

[[ $FAIL_COUNT -eq 0 ]]
