#!/bin/bash
# Doc Advisor Setup Script (v3.0)
#
# Copies all templates to target project and creates configuration
#
# Usage:
#   ./setup.sh TARGET_DIR    # Setup for specified project
#   ./setup.sh               # Interactive mode (prompts for directory)
#   ./setup.sh -h, --help    # Show help

set -e

# Get script directory (plugin root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAST_SETUP_FILE="${SCRIPT_DIR}/.last_setup"

# Default values (no trailing slash)
DEFAULT_RULES_DIR="rules"
DEFAULT_SPECS_DIR="specs"
# Subdirectory names for specs (doc_type mapping)
DEFAULT_REQUIREMENT_DIR_NAME="requirements"
DEFAULT_DESIGN_DIR_NAME="design"
DEFAULT_PLAN_DIR_NAME="plan"

# Load previous settings if available
if [[ -f "$LAST_SETUP_FILE" ]]; then
    source "$LAST_SETUP_FILE"
    # Use saved values as defaults
    DEFAULT_TARGET_DIR="${LAST_TARGET_DIR:-}"
    DEFAULT_RULES_DIR="${LAST_RULES_DIR:-$DEFAULT_RULES_DIR}"
    DEFAULT_SPECS_DIR="${LAST_SPECS_DIR:-$DEFAULT_SPECS_DIR}"
    DEFAULT_REQUIREMENT_DIR_NAME="${LAST_REQUIREMENT_DIR_NAME:-$DEFAULT_REQUIREMENT_DIR_NAME}"
    DEFAULT_DESIGN_DIR_NAME="${LAST_DESIGN_DIR_NAME:-$DEFAULT_DESIGN_DIR_NAME}"
    DEFAULT_PLAN_DIR_NAME="${LAST_PLAN_DIR_NAME:-$DEFAULT_PLAN_DIR_NAME}"
fi

# Parse arguments
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            echo "Doc Advisor Setup Script (v3.0)"
            echo ""
            echo "Usage:"
            echo "  ./setup.sh TARGET_DIR    # Setup for specified project"
            echo "  ./setup.sh               # Interactive mode (prompts for directory)"
            echo "  ./setup.sh -h, --help    # Show help"
            echo ""
            echo "This script creates:"
            echo "  TARGET_DIR/.claude/commands/       # Command files"
            echo "  TARGET_DIR/.claude/agents/         # Agent definitions"
            echo "  TARGET_DIR/.claude/skills/         # Skill modules"
            echo "  TARGET_DIR/.claude/doc-advisor/config.yaml"
            echo ""
            echo "Default directories:"
            echo "  Rules: ${DEFAULT_RULES_DIR}"
            echo "  Specs: ${DEFAULT_SPECS_DIR}"
            exit 0
            ;;
        -*)
            echo "Error: Unknown option: $1"
            echo "Run ./setup.sh --help for usage information"
            exit 1
            ;;
        *)
            if [[ -z "$TARGET_DIR" ]]; then
                TARGET_DIR="$1"
            else
                echo "Error: Too many arguments"
                echo "Run ./setup.sh --help for usage information"
                exit 1
            fi
            shift
            ;;
    esac
done

# Interactive prompt if not specified
if [[ -z "$TARGET_DIR" ]]; then
    echo "Doc Advisor Setup Script (v3.0)"
    echo ""
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

echo "=========================================="
echo "Doc Advisor Setup (v3.0)"
echo "=========================================="
echo ""
echo "Target project: ${TARGET_DIR}"
echo ""

# Interactive prompts for directories
echo "Configure document directories for your project."
echo "(Press Enter to use default value)"
echo ""

read -p "Rules directory [${DEFAULT_RULES_DIR}]: " RULES_DIR
RULES_DIR="${RULES_DIR:-$DEFAULT_RULES_DIR}"

read -p "Specs directory [${DEFAULT_SPECS_DIR}]: " SPECS_DIR
SPECS_DIR="${SPECS_DIR:-$DEFAULT_SPECS_DIR}"

echo ""
echo "Configure subdirectory names for specs:"

read -p "  Requirements directory name [${DEFAULT_REQUIREMENT_DIR_NAME}]: " REQUIREMENT_DIR_NAME
REQUIREMENT_DIR_NAME="${REQUIREMENT_DIR_NAME:-$DEFAULT_REQUIREMENT_DIR_NAME}"

read -p "  Design directory name [${DEFAULT_DESIGN_DIR_NAME}]: " DESIGN_DIR_NAME
DESIGN_DIR_NAME="${DESIGN_DIR_NAME:-$DEFAULT_DESIGN_DIR_NAME}"

# Remove trailing slash if present (placeholders should not include trailing slash)
RULES_DIR="${RULES_DIR%/}"
SPECS_DIR="${SPECS_DIR%/}"

# Plan directory name (not configurable via prompt)
PLAN_DIR_NAME="${DEFAULT_PLAN_DIR_NAME}"

echo ""
echo "Configuration:"
echo "  RULES_DIR: ${RULES_DIR}"
echo "  SPECS_DIR: ${SPECS_DIR}"
echo "  REQUIREMENT_DIR_NAME: ${REQUIREMENT_DIR_NAME}"
echo "  DESIGN_DIR_NAME: ${DESIGN_DIR_NAME}"
echo "  PLAN_DIR_NAME: ${PLAN_DIR_NAME}"
echo ""

# Create directories
CLAUDE_DIR="${TARGET_DIR}/.claude"
CONFIG_DIR="${CLAUDE_DIR}/doc-advisor"
COMMANDS_DIR="${CLAUDE_DIR}/commands"
AGENTS_DIR="${CLAUDE_DIR}/agents"
SKILLS_DIR="${CLAUDE_DIR}/skills"

mkdir -p "${CONFIG_DIR}"
mkdir -p "${CONFIG_DIR}/rules"    # ToC/checksums for rules
mkdir -p "${CONFIG_DIR}/specs"    # ToC/checksums for specs
mkdir -p "${COMMANDS_DIR}"
mkdir -p "${AGENTS_DIR}"
mkdir -p "${SKILLS_DIR}"

# Function to copy and substitute variables in a file
copy_and_substitute() {
    local src="$1"
    local dst="$2"

    if [[ -f "$src" ]]; then
        # Perform variable substitution
        sed -e "s|{{RULES_DIR}}|${RULES_DIR}|g" \
            -e "s|{{SPECS_DIR}}|${SPECS_DIR}|g" \
            -e "s|{{REQUIREMENT_DIR_NAME}}|${REQUIREMENT_DIR_NAME}|g" \
            -e "s|{{DESIGN_DIR_NAME}}|${DESIGN_DIR_NAME}|g" \
            -e "s|{{PLAN_DIR_NAME}}|${PLAN_DIR_NAME}|g" \
            "$src" > "$dst"
    fi
}

# Function to copy directory recursively with variable substitution
copy_dir_with_substitution() {
    local src_dir="$1"
    local dst_dir="$2"

    if [[ ! -d "$src_dir" ]]; then
        echo "Warning: Source directory not found: $src_dir"
        return
    fi

    # Create destination directory
    mkdir -p "$dst_dir"

    # Copy files with substitution
    find "$src_dir" -type f \( -name "*.md" -o -name "*.yaml" -o -name "*.py" -o -name "*.sh" \) | while read -r src_file; do
        # Get relative path from source directory
        rel_path="${src_file#$src_dir/}"
        dst_file="${dst_dir}/${rel_path}"

        # Create parent directory if needed
        mkdir -p "$(dirname "$dst_file")"

        # Copy with substitution for text files
        if [[ "$src_file" == *.md ]] || [[ "$src_file" == *.yaml ]]; then
            copy_and_substitute "$src_file" "$dst_file"
        else
            # Copy as-is for Python and shell scripts
            cp "$src_file" "$dst_file"
        fi
    done

    # Make shell scripts executable
    find "$dst_dir" -name "*.sh" -type f -exec chmod +x {} \;
}

echo "Copying templates..."
echo ""

# Copy commands
echo "  commands/ ..."
copy_dir_with_substitution "${SCRIPT_DIR}/templates/commands" "${COMMANDS_DIR}"

# Copy agents
echo "  agents/ ..."
copy_dir_with_substitution "${SCRIPT_DIR}/templates/agents" "${AGENTS_DIR}"

# Copy skills
echo "  skills/ ..."
copy_dir_with_substitution "${SCRIPT_DIR}/templates/skills" "${SKILLS_DIR}"

# Copy doc-advisor (docs + config.yaml)
echo "  doc-advisor/ ..."
copy_dir_with_substitution "${SCRIPT_DIR}/templates/doc-advisor" "${CONFIG_DIR}"

echo ""
echo "Generated configuration:"
echo "  ${CONFIG_DIR}/config.yaml"

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "Files created at:"
echo "  ${CLAUDE_DIR}/"
echo "    commands/          # Command files"
echo "    agents/            # Agent definitions"
echo "    skills/            # Skill modules"
echo "    doc-advisor/       # Configuration"
# Save settings for next run
cat > "$LAST_SETUP_FILE" << EOF
# Last setup settings (auto-generated)
LAST_TARGET_DIR="${TARGET_DIR}"
LAST_RULES_DIR="${RULES_DIR}"
LAST_SPECS_DIR="${SPECS_DIR}"
LAST_REQUIREMENT_DIR_NAME="${REQUIREMENT_DIR_NAME}"
LAST_DESIGN_DIR_NAME="${DESIGN_DIR_NAME}"
LAST_PLAN_DIR_NAME="${PLAN_DIR_NAME}"
EOF

echo ""
echo "Next steps:"
echo "  1. Verify ${RULES_DIR} and ${SPECS_DIR} directories exist in your project"
echo "  2. Start Claude Code:"
echo "     cd ${TARGET_DIR}"
echo "     claude"
echo "  3. Run /create-rules_toc --full for initial ToC generation"
echo "  4. Run /create-specs_toc --full for initial ToC generation"
echo ""
