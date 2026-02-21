#!/bin/bash
# Add exclude patterns to config.yaml
#
# Usage:
#   ./add-exclude.sh TARGET_DIR
#   ./add-exclude.sh              # Uses last setup target

set -e

# Get script directory (plugin root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Parse arguments
TARGET_DIR="$1"

# Use default or prompt if not specified
if [[ -z "$TARGET_DIR" ]]; then
    # Default: pwd (except when pwd is DocAdvisor itself)
    DEFAULT_TARGET_DIR=""
    CURRENT_DIR="$(pwd)"
    if [[ "$CURRENT_DIR" != "$SCRIPT_DIR" ]]; then
        DEFAULT_TARGET_DIR="$CURRENT_DIR"
    fi
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
    echo "Run './setup.sh' first."
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

# Function to add patterns to a section using awk (cross-platform)
add_patterns_to_section() {
    local section="$1"
    local file="$2"
    shift 2
    local patterns=("$@")

    # Build patterns string for awk
    local patterns_str=""
    for pattern in "${patterns[@]}"; do
        patterns_str="${patterns_str}      - ${pattern}\n"
    done

    # Determine section boundaries
    local start_pattern end_pattern
    if [[ "$section" == "rules" ]]; then
        start_pattern="^rules:"
        end_pattern="^specs:"
    else
        start_pattern="^specs:"
        end_pattern="^common:"
    fi

    # Use awk to insert patterns after "exclude:" line in the target section
    awk -v start="$start_pattern" -v end="$end_pattern" -v patterns="$patterns_str" '
    BEGIN { in_section = 0; done = 0 }
    $0 ~ start { in_section = 1 }
    $0 ~ end { in_section = 0 }
    {
        print
        if (in_section && !done && /^    exclude:/) {
            # Convert \n to actual newlines
            gsub(/\\n/, "\n", patterns)
            printf "%s", patterns
            done = 1
        }
    }
    ' "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"

    for pattern in "${patterns[@]}"; do
        echo "Added to $section: $pattern"
    done
}

# Trim whitespace from patterns
TRIMMED_PATTERNS=()
for pattern in "${PATTERN_ARRAY[@]}"; do
    trimmed=$(echo "$pattern" | xargs)
    if [[ -n "$trimmed" ]]; then
        TRIMMED_PATTERNS+=("$trimmed")
    fi
done

if [[ ${#TRIMMED_PATTERNS[@]} -eq 0 ]]; then
    echo "No valid patterns entered. Exiting."
    exit 0
fi

# Add patterns to selected sections
if [[ "$CHOICE" == "1" || "$CHOICE" == "3" ]]; then
    add_patterns_to_section "rules" "$CONFIG_FILE" "${TRIMMED_PATTERNS[@]}"
fi

if [[ "$CHOICE" == "2" || "$CHOICE" == "3" ]]; then
    add_patterns_to_section "specs" "$CONFIG_FILE" "${TRIMMED_PATTERNS[@]}"
fi

echo ""
echo "Done. Updated excludes:"
echo "  rules:"
grep -A 20 "^rules:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
echo "  specs:"
grep -A 30 "^specs:" "$CONFIG_FILE" | grep -A 10 "exclude:" | grep "^\s*-" | head -10 | sed 's/^/    /'
