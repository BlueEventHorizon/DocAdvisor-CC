#!/bin/bash
# Doc Advisor Minimal Setup Script (without .doc_structure.yaml)
#
# Alternative setup for environments without the doc-structure plugin.
# Prompts for document directories and writes config.yaml root_dirs directly.
#
# Usage:
#   ./setup_dirs.sh TARGET_DIR
#
# Created by k_terada

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Validate arguments
if [[ -z "$1" ]]; then
    echo "Usage: ./setup_dirs.sh TARGET_DIR"
    exit 1
fi

TARGET_DIR="$(cd "$1" 2>/dev/null && pwd)" || {
    printf "${RED}Error: Directory not found: $1${NC}\n"
    exit 1
}

echo ""
printf "${GREEN}Doc Advisor Minimal Setup${NC}\n"
echo "Target: $TARGET_DIR"
echo ""
echo "This script sets up Doc Advisor without .doc_structure.yaml."
echo "Enter directory paths for each document type (empty to skip)."
echo ""

# Collect directory inputs (all 4 prompts displayed, empty allowed)
printf "${YELLOW}rule${NC} directory (e.g., rules):\n"
read -r RULE_DIR
printf "${YELLOW}requirement${NC} directory (e.g., specs/requirements):\n"
read -r REQUIREMENT_DIR
printf "${YELLOW}design${NC} directory (e.g., specs/design):\n"
read -r DESIGN_DIR
printf "${YELLOW}plan${NC} directory (e.g., specs/plan):\n"
read -r PLAN_DIR

# Validate non-empty directories exist
for dir_entry in "rule:$RULE_DIR" "requirement:$REQUIREMENT_DIR" "design:$DESIGN_DIR" "plan:$PLAN_DIR"; do
    type_name="${dir_entry%%:*}"
    dir_path="${dir_entry#*:}"
    if [[ -n "$dir_path" ]] && [[ ! -d "$TARGET_DIR/$dir_path" ]]; then
        printf "${YELLOW}Warning: $type_name directory not found: $TARGET_DIR/$dir_path${NC}\n"
    fi
done

echo ""

# Run base setup (skip .doc_structure.yaml check)
echo "Running base setup..."
"$SCRIPT_DIR/setup.sh" --skip-doc-structure "$TARGET_DIR"

echo ""
echo "Configuring root_dirs..."

# Build root_dirs for rules and specs sections
CONFIG_FILE="$TARGET_DIR/.claude/doc-advisor/config.yaml"

if [[ ! -f "$CONFIG_FILE" ]]; then
    printf "${RED}Error: config.yaml not found after setup${NC}\n"
    exit 1
fi

# Use Python to update config.yaml (environment variables for bash 3.2 compat)
DA_CONFIG="$CONFIG_FILE" \
DA_RULE_DIR="$RULE_DIR" \
DA_REQUIREMENT_DIR="$REQUIREMENT_DIR" \
DA_DESIGN_DIR="$DESIGN_DIR" \
DA_PLAN_DIR="$PLAN_DIR" \
python3 << 'PYEOF'
import os

config_file = os.environ['DA_CONFIG']
rule_dir = os.environ.get('DA_RULE_DIR', '')
requirement_dir = os.environ.get('DA_REQUIREMENT_DIR', '')
design_dir = os.environ.get('DA_DESIGN_DIR', '')
plan_dir = os.environ.get('DA_PLAN_DIR', '')

with open(config_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Build rules root_dirs
rules_dirs = []
if rule_dir:
    rules_dirs.append(rule_dir.rstrip('/'))

# Build specs root_dirs
specs_dirs = []
if requirement_dir:
    specs_dirs.append(requirement_dir.rstrip('/'))
if design_dir:
    specs_dirs.append(design_dir.rstrip('/'))
if plan_dir:
    specs_dirs.append(plan_dir.rstrip('/'))

# Replace commented root_dirs with actual values
# First occurrence is rules, second is specs
if rules_dirs:
    rules_yaml = '  root_dirs:\n' + '\n'.join(f'    - {d}' for d in rules_dirs)
    content = content.replace(
        '  # root_dirs: []    # Uncomment to override .doc_structure.yaml',
        rules_yaml,
        1
    )

if specs_dirs:
    specs_yaml = '  root_dirs:\n' + '\n'.join(f'    - {d}' for d in specs_dirs)
    content = content.replace(
        '  # root_dirs: []    # Uncomment to override .doc_structure.yaml',
        specs_yaml,
        1
    )

with open(config_file, 'w', encoding='utf-8') as f:
    f.write(content)

# Summary
print('Updated config.yaml:')
if rules_dirs:
    print(f'  rules root_dirs: {rules_dirs}')
else:
    print('  rules root_dirs: (skipped - will use default)')
if specs_dirs:
    print(f'  specs root_dirs: {specs_dirs}')
else:
    print('  specs root_dirs: (skipped - will use default)')
PYEOF

echo ""
printf "${GREEN}Minimal setup complete.${NC}\n"
echo ""
echo "To use full .doc_structure.yaml integration later:"
printf "  1. Run ${YELLOW}/doc-structure:init-doc-structure${NC} in Claude Code\n"
printf "  2. Re-run ${YELLOW}${SCRIPT_DIR}/setup.sh ${TARGET_DIR}${NC}\n"
echo ""
