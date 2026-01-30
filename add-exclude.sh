#!/bin/bash
# Add exclude patterns to config.yaml
#
# Usage:
#   ./add-exclude.sh TARGET_DIR
#   ./add-exclude.sh              # Uses last setup target

set -e

# Get script directory (plugin root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAST_SETUP_FILE="${SCRIPT_DIR}/.last_setup"

# Load previous settings if available
DEFAULT_TARGET_DIR=""
if [[ -f "$LAST_SETUP_FILE" ]]; then
    source "$LAST_SETUP_FILE"
    DEFAULT_TARGET_DIR="${LAST_TARGET_DIR:-}"
fi

# Parse arguments
TARGET_DIR="$1"

# Use default or prompt if not specified
if [[ -z "$TARGET_DIR" ]]; then
    if [[ -n "$DEFAULT_TARGET_DIR" ]]; then
        read -p "Enter target project directory [${DEFAULT_TARGET_DIR}]: " TARGET_DIR
        TARGET_DIR="${TARGET_DIR:-$DEFAULT_TARGET_DIR}"
    else
        read -p "Enter target project directory: " TARGET_DIR
    fi
    if [[ -z "$TARGET_DIR" ]]; then
        echo "Error: Target directory is required"
        exit 1
    fi
fi

# Expand ~ and relative paths
TARGET_DIR="$(eval echo "$TARGET_DIR")"
TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd)" || {
    echo "Error: Directory does not exist: $TARGET_DIR"
    exit 1
}

CONFIG_FILE="${TARGET_DIR}/.claude/doc-advisor/config.yaml"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: config.yaml not found: $CONFIG_FILE"
    echo "Run 'make setup' first."
    exit 1
fi

echo "=========================================="
echo "Add Exclude Patterns"
echo "=========================================="
echo ""
echo "Target: ${CONFIG_FILE}"
echo ""

# Show current excludes
echo "Current excludes:"
echo "  rules:"
grep -A 20 "^rules:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
echo "  specs:"
grep -A 30 "^specs:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
echo ""

# Ask for patterns
read -p "Enter exclude patterns (comma-separated, e.g., reference,archive): " PATTERNS

if [[ -z "$PATTERNS" ]]; then
    echo "No patterns entered. Exiting."
    exit 0
fi

# Convert comma-separated to array
IFS=',' read -ra PATTERN_ARRAY <<< "$PATTERNS"

# Ask which section to add
echo ""
echo "Add to which section?"
echo "  1) rules only"
echo "  2) specs only"
echo "  3) both (default)"
read -p "Choice [3]: " CHOICE
CHOICE="${CHOICE:-3}"

# Function to add pattern to a section
add_pattern_to_section() {
    local section="$1"
    local pattern="$2"
    local file="$3"

    # Find the last line of exclude section (before output: or next section)
    if [[ "$section" == "rules" ]]; then
        # Find last exclude item line in rules section (before "  output:")
        local line_num=$(awk '/^rules:/,/^specs:/{
            if(/^  patterns:/) in_patterns=1
            if(in_patterns && /exclude:/) in_exclude=1
            if(in_exclude && /^      [#-]/) last_line=NR
            if(in_exclude && /^  output:/) {print last_line; exit}
        }' "$file")
    else
        # Find last exclude item line in specs section (before "  output:")
        local line_num=$(awk '/^specs:/,/^common:/{
            if(/^  patterns:/) in_patterns=1
            if(in_patterns && /exclude:/) in_exclude=1
            if(in_exclude && /^      [#-]/) last_line=NR
            if(in_exclude && /^  output:/) {print last_line; exit}
        }' "$file")
    fi

    if [[ -n "$line_num" ]]; then
        # Insert after the last exclude item
        sed -i '' "${line_num}a\\
      - ${pattern}
" "$file"
    else
        echo "Warning: Could not find exclude section in $section"
    fi
}

# Add patterns
for pattern in "${PATTERN_ARRAY[@]}"; do
    # Trim whitespace
    pattern=$(echo "$pattern" | xargs)

    if [[ "$CHOICE" == "1" || "$CHOICE" == "3" ]]; then
        add_pattern_to_section "rules" "$pattern" "$CONFIG_FILE"
        echo "Added to rules: $pattern"
    fi

    if [[ "$CHOICE" == "2" || "$CHOICE" == "3" ]]; then
        add_pattern_to_section "specs" "$pattern" "$CONFIG_FILE"
        echo "Added to specs: $pattern"
    fi
done

echo ""
echo "Done. Updated excludes:"
echo "  rules:"
grep -A 20 "^rules:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
echo "  specs:"
grep -A 30 "^specs:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
