#!/bin/bash
# Change the agent model for all Doc Advisor skills and agents.
# Replaces the `model:` line in frontmatter of installed .claude/ files.
#
# Usage: bash change_agent_model.sh <model>
#   model: haiku, sonnet, opus, inherit
#
# Created by k_terada

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Resolve project root
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 1

MODEL="${1:-}"

if [[ -z "$MODEL" ]]; then
    echo "Usage: bash change_agent_model.sh <model>"
    echo "  model: haiku, sonnet, opus, inherit"
    exit 1
fi

# Validate model
case "$MODEL" in
    haiku|sonnet|opus|inherit)
        ;;
    *)
        printf "${RED}Error: Invalid model '%s'. Valid values: haiku, sonnet, opus, inherit${NC}\n" "$MODEL"
        exit 1
        ;;
esac

# Target files: skills and agents with model: in frontmatter
TARGETS=(
    ".claude/skills/query-rules/SKILL.md"
    ".claude/skills/query-specs/SKILL.md"
    ".claude/agents/toc-updater.md"
)

CHANGED=0
for file in "${TARGETS[@]}"; do
    if [[ ! -f "$file" ]]; then
        printf "${RED}  Not found: %s${NC}\n" "$file"
        continue
    fi

    # Replace model: line (any valid value → new value)
    if grep -q '^model: ' "$file" 2>/dev/null; then
        sed -i '' "s/^model: .*/model: ${MODEL}/" "$file"
        printf "${GREEN}  Updated: %s${NC} → model: ${BLUE}%s${NC}\n" "$file" "$MODEL"
        ((CHANGED++))
    else
        printf "${RED}  No model: line found: %s${NC}\n" "$file"
    fi
done

echo ""
if [[ $CHANGED -gt 0 ]]; then
    printf "${GREEN}Done. Changed %d file(s) to model: %s${NC}\n" "$CHANGED" "$MODEL"
else
    printf "${RED}No files were changed.${NC}\n"
    exit 1
fi
