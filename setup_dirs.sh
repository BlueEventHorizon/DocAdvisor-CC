#!/bin/bash
# =============================================================================
# Document Directory Setup for Doc Advisor
# =============================================================================
#
# Auto-detects document directories and asks user for confirmation.
# If detection is wrong, user can input directories manually.
#
# Usage:
#   setup_dirs.sh <target_dir> [python_cmd]
#
# Called from: setup.sh (after template deployment)
# Standalone:  bash setup_dirs.sh /path/to/project
#
# Created by: k_terada
# =============================================================================

TARGET_DIR="${1:?Usage: setup_dirs.sh <target_dir> [python_cmd]}"
PYTHON_CMD="${2:-python3}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR=".claude/doc-advisor/scripts"

echo ""
echo "Detecting document directories..."
echo ""

# Step 1: Detect and show summary
SUMMARY=$( (cd "$TARGET_DIR" && "$PYTHON_CMD" "$SCRIPT_DIR/classify_dirs.py" --format summary) 2>&1 )
DETECT_EXIT=$?

if [[ $DETECT_EXIT -eq 0 ]] && [[ -n "$SUMMARY" ]] && ! echo "$SUMMARY" | grep -q "No document directories detected"; then
    echo "$SUMMARY"

    # Get dirs in bash-parseable format
    DETECTED=$( (cd "$TARGET_DIR" && "$PYTHON_CMD" "$SCRIPT_DIR/classify_dirs.py" --format dirs) 2>&1 )
    RULES_DETECTED=$(echo "$DETECTED" | grep '^RULES=' | cut -d= -f2)
    SPECS_DETECTED=$(echo "$DETECTED" | grep '^SPECS=' | cut -d= -f2)

    # Step 2: User confirmation
    echo ""
    read -p "  Accept? [Y/n]: " DIR_CONFIRM || true
    DIR_CONFIRM="${DIR_CONFIRM:-y}"

    if [[ "$DIR_CONFIRM" =~ ^[Yy] ]]; then
        (cd "$TARGET_DIR" && "$PYTHON_CMD" "$SCRIPT_DIR/set_root_dirs.py" \
            --rules "$RULES_DETECTED" --specs "$SPECS_DETECTED")
    else
        echo ""
        echo "  Enter directories manually (comma-separated, empty to skip):"
        read -p "    Rules directories: " RULES_MANUAL || true
        read -p "    Specs directories: " SPECS_MANUAL || true

        if [[ -n "$RULES_MANUAL" ]] || [[ -n "$SPECS_MANUAL" ]]; then
            (cd "$TARGET_DIR" && "$PYTHON_CMD" "$SCRIPT_DIR/set_root_dirs.py" \
                --rules "${RULES_MANUAL:-}" --specs "${SPECS_MANUAL:-}")
        else
            echo -e "${YELLOW}  Skipped. Run /classify-docs in Claude Code to configure.${NC}"
        fi
    fi
else
    # Detection failed or no dirs found → manual input only
    echo "  No document directories detected."
    echo ""
    echo "  Enter directories manually (comma-separated, empty to skip):"
    read -p "    Rules directories: " RULES_MANUAL || true
    read -p "    Specs directories: " SPECS_MANUAL || true

    if [[ -n "$RULES_MANUAL" ]] || [[ -n "$SPECS_MANUAL" ]]; then
        (cd "$TARGET_DIR" && "$PYTHON_CMD" "$SCRIPT_DIR/set_root_dirs.py" \
            --rules "${RULES_MANUAL:-}" --specs "${SPECS_MANUAL:-}")
    else
        echo -e "${YELLOW}  Skipped. Run /classify-docs in Claude Code to configure.${NC}"
    fi
fi
