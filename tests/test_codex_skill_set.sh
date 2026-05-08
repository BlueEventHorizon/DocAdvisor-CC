#!/bin/bash
# Validate generated Codex-native skill set.
# Created by: k2moons

# Note: Do not use 'set -e' as individual assertions should report all failures.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SET_DIR="$PROJECT_ROOT/codex_skill_set"
PROFILE="$PROJECT_ROOT/codex_install_profiles/doc-advisor/current.yaml"

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
echo "Codex Skill Set Validation"
echo "=================================================="
echo ""

check "codex_skill_set exists" "[[ -d '$SET_DIR/skills' && -d '$SET_DIR/resources' ]]"
check "profile exists" "[[ -f '$PROFILE' ]]"
check "disabled code-index skills are absent" "[[ ! -d '$SET_DIR/skills/create-code-index' && ! -d '$SET_DIR/skills/query-code' ]]"
check "forge monitor is excluded" "[[ ! -d '$SET_DIR/resources/forge/scripts/monitor' ]]"
check "forge authoring wrapper skills exist" "[[ -f '$SET_DIR/skills/start-requirements/SKILL.md' && -f '$SET_DIR/skills/start-design/SKILL.md' && -f '$SET_DIR/skills/start-plan/SKILL.md' ]]"
check "forge confirmation protocol exists" "[[ -f '$SET_DIR/resources/forge/docs/codex_confirmation_protocol.md' ]]"
check "no Claude/plugin placeholders remain" "! grep -R -n -E '\\\$\\{CLAUDE_PLUGIN_ROOT\\}|DOC_ADVISOR_PLUGIN_ROOT|/doc-advisor:|/forge:|AskUserQuestion|Task\\(subagent_type:' '$SET_DIR' >/dev/null 2>&1"
check "no project-local resource references remain" "! grep -R -n -E '\\.codex/resources/|\\.codex/skills/' '$SET_DIR/skills' '$SET_DIR/resources' >/dev/null 2>&1"

python3 - "$SET_DIR" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
allowed = {"name", "description", "metadata"}
failures = []
for skill in sorted(root.glob("skills/*/SKILL.md")):
    text = skill.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        failures.append(f"{skill}: missing frontmatter")
        continue
    end = text.find("\n---\n", 4)
    if end == -1:
        failures.append(f"{skill}: unterminated frontmatter")
        continue
    frontmatter = text[4:end]
    keys = []
    for line in frontmatter.splitlines():
        if line and not line.startswith(" ") and ":" in line:
            keys.append(line.split(":", 1)[0])
    missing = {"name", "description"} - set(keys)
    extra = set(keys) - allowed
    if missing:
        failures.append(f"{skill}: missing {sorted(missing)}")
    if extra:
        failures.append(f"{skill}: unsupported keys {sorted(extra)}")

if failures:
    for failure in failures:
        print(failure)
    sys.exit(1)
PY
if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}PASS${NC}: skill frontmatter is Codex-compatible"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: skill frontmatter is Codex-compatible"
    ((FAIL_COUNT++))
fi

PY_FILES=$(find "$SET_DIR/resources" -name "*.py" -type f | sort)
if python3 -m py_compile $PY_FILES; then
    echo -e "${GREEN}PASS${NC}: Python resources compile"
    ((PASS_COUNT++))
else
    echo -e "${RED}FAIL${NC}: Python resources compile"
    ((FAIL_COUNT++))
fi

echo ""
echo "PASS: $PASS_COUNT"
echo "FAIL: $FAIL_COUNT"

[[ $FAIL_COUNT -eq 0 ]]
