#!/bin/bash
# =============================================================================
# Document Directory Setup for Doc Advisor
# =============================================================================
#
# Auto-detects document directories and asks user for confirmation.
# User can skip (exclude) directories before accepting.
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

# --- Helper functions ---

apply_config() {
    local rules="$1" specs="$2" excludes="$3"
    local cmd="\"$PYTHON_CMD\" \"$SCRIPT_DIR/set_root_dirs.py\" --rules \"$rules\" --specs \"$specs\""
    if [[ -n "$excludes" ]]; then
        cmd="$cmd --exclude-rules \"$excludes\" --exclude-specs \"$excludes\""
    fi
    (cd "$TARGET_DIR" && eval "$cmd")
}

run_classify() {
    local format="$1" skip="$2"
    local cmd="\"$PYTHON_CMD\" \"$SCRIPT_DIR/classify_dirs.py\" --format $format"
    [[ -n "$skip" ]] && cmd="$cmd --skip \"$skip\""
    (cd "$TARGET_DIR" && eval "$cmd") 2>&1
}

# --- Main flow ---

echo ""
echo "Detecting document directories..."
echo ""

# Step 1: Detect and show all candidates
SUMMARY=$(run_classify summary "")
DETECT_EXIT=$?

if [[ $DETECT_EXIT -eq 0 ]] && [[ -n "$SUMMARY" ]] && ! echo "$SUMMARY" | grep -q "No document directories detected"; then
    echo "$SUMMARY"

    # Step 2: Ask for directories to skip
    echo ""
    read -p "  Skip directories? (comma-separated, empty to continue): " SKIP_DIRS || true

    # Step 3: Re-detect with skip if given
    if [[ -n "$SKIP_DIRS" ]]; then
        echo ""
        SUMMARY=$(run_classify summary "$SKIP_DIRS")
        echo "$SUMMARY"
    fi

    # Get dirs in bash-parseable format (with skip)
    DETECTED=$(run_classify dirs "$SKIP_DIRS")
    RULES_DETECTED=$(echo "$DETECTED" | grep '^RULES=' | cut -d= -f2)
    SPECS_DETECTED=$(echo "$DETECTED" | grep '^SPECS=' | cut -d= -f2)

    # Step 4: User confirmation
    echo ""
    read -p "  Accept? [Y/n]: " DIR_CONFIRM || true
    DIR_CONFIRM="${DIR_CONFIRM:-y}"

    if [[ "$DIR_CONFIRM" =~ ^[Yy] ]]; then
        apply_config "$RULES_DETECTED" "$SPECS_DETECTED" "$SKIP_DIRS"
    else
        echo ""
        echo "  Enter directories manually (comma-separated, empty to skip):"
        read -p "    Rules directories: " RULES_MANUAL || true
        read -p "    Specs directories: " SPECS_MANUAL || true

        if [[ -n "$RULES_MANUAL" ]] || [[ -n "$SPECS_MANUAL" ]]; then
            apply_config "${RULES_MANUAL:-}" "${SPECS_MANUAL:-}" "$SKIP_DIRS"
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
        apply_config "${RULES_MANUAL:-}" "${SPECS_MANUAL:-}" ""
    else
        echo -e "${YELLOW}  Skipped. Run /classify-docs in Claude Code to configure.${NC}"
    fi
fi
