#!/bin/bash
# Doc Advisor Setup Script
#
# Copies all templates to target project and creates configuration
#
# Usage:
#   ./setup.sh TARGET_DIR    # Setup for specified project
#   ./setup.sh               # Interactive mode (prompts for directory)
#   ./setup.sh -h, --help    # Show help

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Format path for display: replace $HOME with ~
display_path() { printf '%s' "${1/#$HOME/\~}"; }

# Get script directory (plugin root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAST_SETUP_FILE="${SCRIPT_DIR}/.last_setup"

# Agent model (opus, sonnet, haiku, inherit)
DEFAULT_AGENT_MODEL="opus"

# Load previous settings if available (safe key=value parser, no source)
_load_last_setup() {
    local file="$1"
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// /}" ]] && continue
        # Only accept KEY="value" or KEY=value where KEY is a known variable
        if [[ "$line" =~ ^LAST_AGENT_MODEL=\"?([a-z]+)\"?$ ]]; then
            DEFAULT_AGENT_MODEL="${BASH_REMATCH[1]}"
        fi
    done < "$file"
}
if [[ -f "$LAST_SETUP_FILE" ]]; then
    _load_last_setup "$LAST_SETUP_FILE"
fi

# Parse arguments
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            echo "Doc Advisor Setup Script"
            echo ""
            echo "Usage:"
            echo "  ./setup.sh TARGET_DIR    # Setup for specified project"
            echo "  ./setup.sh               # Interactive mode (prompts for directory)"
            echo "  ./setup.sh -h, --help    # Show help"
            echo ""
            echo "This script creates:"
            echo "  TARGET_DIR/.claude/agents/         # Worker agents (toc-updater)"
            echo "  TARGET_DIR/.claude/skills/         # Skills (query-*, create-*-toc)"
            echo "  TARGET_DIR/.claude/doc-advisor/    # Config, docs, scripts, ToC files"
            echo ""
            echo "If .doc_structure.yaml exists, it is used as document structure configuration."
            echo "Otherwise, run /setup-config after setup to create .doc_structure.yaml."
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
    echo "Doc Advisor Setup Script"
    echo ""
    # Default: pwd (except when pwd is DocAdvisor itself)
    if [[ -z "$DEFAULT_TARGET_DIR" ]]; then
        CURRENT_DIR="$(pwd)"
        if [[ "$CURRENT_DIR" != "$SCRIPT_DIR" ]]; then
            DEFAULT_TARGET_DIR="$CURRENT_DIR"
        fi
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

# Expand ~ to $HOME (safe alternative to eval)
TARGET_DIR="${TARGET_DIR/#\~/$HOME}"
TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd)" || {
    echo "Error: Directory does not exist: $TARGET_DIR"
    exit 1
}

printf "${GREEN}==========================================${NC}\n"
printf "${GREEN}Doc Advisor Setup${NC}\n"
printf "${GREEN}==========================================${NC}\n"
echo ""
echo "Target project: $(display_path "${TARGET_DIR}")"
echo ""

# =============================================================================
# Document structure check (early exit opportunity)
# =============================================================================
DOC_STRUCTURE_FILE="${TARGET_DIR}/.doc_structure.yaml"
HAS_DOC_STRUCTURE=false

if [[ -f "$DOC_STRUCTURE_FILE" ]]; then
    printf "${GREEN}  .doc_structure.yaml found${NC}\n"
    HAS_DOC_STRUCTURE=true
else
    printf "${YELLOW}  .doc_structure.yaml not found${NC}\n"
    echo "  Document directories will need to be configured after setup."
    printf "  Run ${YELLOW}/setup-config${NC} in Claude Code to auto-detect and configure.\n"
    echo ""
    echo "  Options:"
    echo "    [c] Continue setup (configure directories later with /setup-config)"
    echo "    [e] Exit (install doc-structure plugin first)"
    read -p "  Choice [c]: " DOC_STRUCTURE_CHOICE
    DOC_STRUCTURE_CHOICE="${DOC_STRUCTURE_CHOICE:-c}"
    if [[ "$DOC_STRUCTURE_CHOICE" == [Ee] ]]; then
        echo ""
        echo "Setup cancelled."
        echo "To create .doc_structure.yaml, run /doc-structure:init-doc-structure in Claude Code."
        echo "Then re-run this setup script."
        exit 0
    fi
fi
echo ""

# =============================================================================
# Agent model selection
# =============================================================================

echo "Configure agent model (opus, sonnet, haiku, inherit):"
read -p "  Agent model [${DEFAULT_AGENT_MODEL}]: " AGENT_MODEL
AGENT_MODEL="${AGENT_MODEL:-$DEFAULT_AGENT_MODEL}"

# Validate agent model
case "$AGENT_MODEL" in
    opus|sonnet|haiku|inherit)
        ;;
    *)
        printf "${RED}Warning: Unknown model '$AGENT_MODEL'. Using 'opus' as default.${NC}\n"
        AGENT_MODEL="opus"
        ;;
esac

# python3 works correctly via Claude Code's shell wrapper (wrapSafeChainCommand
# resolves to the pyenv-managed interpreter). No full-path detection needed.
PYTHON_CMD="python3"

echo ""
echo "Configuration:"
printf "  AGENT_MODEL: ${BLUE}${AGENT_MODEL}${NC}\n"
echo ""

# Create directories
CLAUDE_DIR="${TARGET_DIR}/.claude"
DOC_ADVISOR_DIR="${CLAUDE_DIR}/doc-advisor"
AGENTS_DIR="${CLAUDE_DIR}/agents"
SKILLS_DIR="${CLAUDE_DIR}/skills"

# =============================================================================
# Version identifier functions
# =============================================================================
DOC_ADVISOR_VERSION="5.0"
# Unique identifier key: doc-advisor-version-xK9XmQ
# Note: xK9XmQ is a permanent, fixed string to prevent false matches with user files

# Extract doc-advisor-version-xK9XmQ from a file (YAML frontmatter or comment)
# Returns: version string or empty if not found
get_doc_advisor_version() {
    local file="$1"
    if [[ -f "$file" ]]; then
        # Match: doc-advisor-version-xK9XmQ: "3.2" or # doc-advisor-version-xK9XmQ: 3.2
        grep -E '^(#[[:space:]]*)?doc-advisor-version-xK9XmQ:[[:space:]]*' "$file" 2>/dev/null | \
            head -1 | sed -E 's/^(#[[:space:]]*)?doc-advisor-version-xK9XmQ:[[:space:]]*"?([^"]*)"?.*/\2/'
    fi
}

# Check if file has CURRENT doc-advisor-version
# Returns: 0 (true) if version matches current, 1 (false) otherwise
# - No identifier = legacy (return 1)
# - Old version = legacy (return 1)
# - Current version = protected (return 0)
has_current_doc_advisor_version() {
    local file="$1"
    local version
    version=$(get_doc_advisor_version "$file")
    [[ "$version" == "$DOC_ADVISOR_VERSION" ]]
}

# =============================================================================
# Clean up legacy files (hybrid: file-name check + version protection)
# - Known legacy file names are checked
# - Files with CURRENT doc-advisor-version are protected (not deleted)
# - Files with OLD version or NO identifier are deleted
# =============================================================================
LEGACY_CLEANED=0

# commands/ - delete only doc-advisor commands (preserve user's custom commands)
# Skip if file has CURRENT doc-advisor-version (protected)
if [[ -f "${CLAUDE_DIR}/commands/create-rules_toc.md" ]]; then
    if ! has_current_doc_advisor_version "${CLAUDE_DIR}/commands/create-rules_toc.md"; then
        rm -f "${CLAUDE_DIR}/commands/create-rules_toc.md"
        printf "${GREEN}Removed legacy: commands/create-rules_toc.md${NC}\n"
        LEGACY_CLEANED=1
    fi
fi
if [[ -f "${CLAUDE_DIR}/commands/create-specs_toc.md" ]]; then
    if ! has_current_doc_advisor_version "${CLAUDE_DIR}/commands/create-specs_toc.md"; then
        rm -f "${CLAUDE_DIR}/commands/create-specs_toc.md"
        printf "${GREEN}Removed legacy: commands/create-specs_toc.md${NC}\n"
        LEGACY_CLEANED=1
    fi
fi

# v2.0 had config/docs/scripts in skills/doc-advisor/ - migrate if found
LEGACY_SKILL_CONFIG="${SKILLS_DIR}/doc-advisor/config.yaml"
if [[ -f "$LEGACY_SKILL_CONFIG" ]]; then
    rm -f "$LEGACY_SKILL_CONFIG"
    printf "${GREEN}Removed legacy: skills/doc-advisor/config.yaml${NC}\n"
    LEGACY_CLEANED=1
fi
if [[ -d "${SKILLS_DIR}/doc-advisor/docs" ]]; then
    rm -rf "${SKILLS_DIR}/doc-advisor/docs"
    printf "${GREEN}Removed legacy: skills/doc-advisor/docs/${NC}\n"
    LEGACY_CLEANED=1
fi
if [[ -d "${SKILLS_DIR}/doc-advisor/scripts" ]]; then
    rm -rf "${SKILLS_DIR}/doc-advisor/scripts"
    printf "${GREEN}Removed legacy: skills/doc-advisor/scripts/${NC}\n"
    LEGACY_CLEANED=1
fi

# v3.0 moved docs to doc-advisor/ - clean old docs directory if it exists with outdated files
# (scripts and config are handled by the copy process, only docs/ needs explicit cleanup)
if [[ -d "${DOC_ADVISOR_DIR}/docs" ]]; then
    rm -rf "${DOC_ADVISOR_DIR}/docs"
    printf "${GREEN}Removed legacy: doc-advisor/docs/${NC}\n"
    LEGACY_CLEANED=1
fi

# v3.0 unified skill → v3.1 split skills (create-rules-toc, create-specs-toc)
# Skip if SKILL.md has doc-advisor-version identifier (means it's current version)
if [[ -d "${SKILLS_DIR}/doc-advisor" ]]; then
    if ! has_current_doc_advisor_version "${SKILLS_DIR}/doc-advisor/SKILL.md"; then
        rm -rf "${SKILLS_DIR}/doc-advisor"
        printf "${GREEN}Removed legacy: skills/doc-advisor/${NC}\n"
        LEGACY_CLEANED=1
    fi
fi

# v3.7 advisor agents → query-* skills migration
# Remove advisor agents (replaced by query-rules and query-specs skills)
for advisor_agent in "rules-advisor.md" "specs-advisor.md"; do
    if [[ -f "${AGENTS_DIR}/${advisor_agent}" ]]; then
        if ! has_current_doc_advisor_version "${AGENTS_DIR}/${advisor_agent}"; then
            rm -f "${AGENTS_DIR}/${advisor_agent}"
            printf "${GREEN}Removed legacy: agents/${advisor_agent} (replaced by skill)${NC}\n"
            LEGACY_CLEANED=1
        fi
    fi
done

# v3.8 unified scripts (6 per-category scripts → 3 unified --target scripts)
# No version check: these files are replaced by unified scripts regardless of version
for old_script in \
    "create_pending_yaml_rules.py" "create_pending_yaml_specs.py" \
    "write_rules_pending.py" "write_specs_pending.py" \
    "merge_rules_toc.py" "merge_specs_toc.py"; do
    if [[ -f "${DOC_ADVISOR_DIR}/scripts/${old_script}" ]]; then
        rm -f "${DOC_ADVISOR_DIR}/scripts/${old_script}"
        printf "${GREEN}Removed legacy: scripts/${old_script} (unified)${NC}\n"
        LEGACY_CLEANED=1
    fi
done

# v3.8 unified agents (per-category agents → single toc-updater.md)
# No version check: these files are replaced by toc-updater.md regardless of version
for old_agent in "rules-toc-updater.md" "specs-toc-updater.md"; do
    if [[ -f "${AGENTS_DIR}/${old_agent}" ]]; then
        rm -f "${AGENTS_DIR}/${old_agent}"
        printf "${GREEN}Removed legacy: agents/${old_agent} (unified into toc-updater.md)${NC}\n"
        LEGACY_CLEANED=1
    fi
done

# v4.3: classify-docs renamed to setup-config
OLD_CLASSIFY_DIR="${SKILLS_DIR}/classify-docs"
if [[ -d "$OLD_CLASSIFY_DIR" ]]; then
    rm -rf "$OLD_CLASSIFY_DIR"
    printf "${GREEN}Removed legacy: skills/classify-docs/ (renamed to setup-config/)${NC}\n"
    LEGACY_CLEANED=1
fi
for old_script in "set_root_dirs.py" "validate_rules_toc.py" "validate_specs_toc.py"; do
    if [[ -f "${DOC_ADVISOR_DIR}/scripts/${old_script}" ]]; then
        rm -f "${DOC_ADVISOR_DIR}/scripts/${old_script}"
        printf "${GREEN}Removed legacy: scripts/${old_script}${NC}\n"
        LEGACY_CLEANED=1
    fi
done

# v5.0: config.yaml abolished (.doc_structure.yaml is now the sole configuration)
for old_file in "config.yaml" "scripts/import_doc_structure.py" "scripts/merge_config.py"; do
    if [[ -f "${DOC_ADVISOR_DIR}/${old_file}" ]]; then
        rm -f "${DOC_ADVISOR_DIR}/${old_file}"
        printf "${GREEN}Removed legacy: doc-advisor/${old_file} (replaced by .doc_structure.yaml)${NC}\n"
        LEGACY_CLEANED=1
    fi
done

if [[ $LEGACY_CLEANED -eq 1 ]]; then
    echo ""
fi

mkdir -p "${DOC_ADVISOR_DIR}"
mkdir -p "${DOC_ADVISOR_DIR}/toc/rules"    # ToC/checksums for rules
mkdir -p "${DOC_ADVISOR_DIR}/toc/specs"    # ToC/checksums for specs
mkdir -p "${AGENTS_DIR}"
mkdir -p "${SKILLS_DIR}"

# Function to escape a value for use in sed replacement string (| delimiter)
# Escapes: \ → \\, & → \&, | → \|
_sed_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/&/\\&/g; s/|/\\|/g'
}

# Function to copy and substitute variables in a file
copy_and_substitute() {
    local src="$1"
    local dst="$2"

    [[ -f "$src" ]] || return 0

    local esc_model esc_version
    esc_model=$(_sed_escape "${AGENT_MODEL}")
    esc_version=$(_sed_escape "${DOC_ADVISOR_VERSION}")

    # Generate substituted content
    local new_content
    new_content=$(sed -e "s|{{AGENT_MODEL}}|${esc_model}|g" \
        -e "s|{{DOC_ADVISOR_VERSION}}|${esc_version}|g" \
        "$src")

    # If target file exists, compare content excluding version identifier line
    if [[ -f "$dst" ]]; then
        local new_stripped old_stripped
        new_stripped=$(printf '%s\n' "$new_content" | grep -v 'doc-advisor-version-xK9XmQ:' || true)
        old_stripped=$(grep -v 'doc-advisor-version-xK9XmQ:' "$dst" || true)

        if [[ "$new_stripped" = "$old_stripped" ]]; then
            printf "${BLUE}    Skipped (unchanged): %s${NC}\n" "$(basename "$dst")"
            return 0
        fi
    fi

    printf '%s\n' "$new_content" > "$dst"
}

# Function to copy directory recursively with variable substitution
copy_dir_with_substitution() {
    local src_dir="$1"
    local dst_dir="$2"

    if [[ ! -d "$src_dir" ]]; then
        printf "${RED}Warning: Source directory not found: ${src_dir}${NC}\n"
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
        if [[ "$src_file" == *.md ]] || [[ "$src_file" == *.yaml ]] || [[ "$src_file" == *.py ]]; then
            copy_and_substitute "$src_file" "$dst_file"
        else
            # Copy as-is for shell scripts
            cp "$src_file" "$dst_file"
        fi
    done

    # Make shell scripts executable
    find "$dst_dir" -name "*.sh" -type f -exec chmod +x {} \;
}

echo "Copying templates..."
echo ""

# Copy agents (overwrite only - preserve user's custom agents)
echo "  agents/ ..."
if [[ -d "${AGENTS_DIR}" ]]; then
    # doc-advisor managed agents (will be overwritten)
    MANAGED_AGENTS="toc-updater.md"
    # Check for non-managed agents and notify user
    for agent in "${AGENTS_DIR}"/*.md; do
        [[ -e "$agent" ]] || continue
        name=$(basename "$agent")
        if ! echo "$MANAGED_AGENTS" | grep -qw "$name"; then
            printf "${BLUE}    Preserving: $name${NC}\n"
        fi
    done
fi
copy_dir_with_substitution "${SCRIPT_DIR}/templates/agents" "${AGENTS_DIR}"

# Copy skills
echo "  skills/create-rules-toc/ ..."
mkdir -p "${SKILLS_DIR}/create-rules-toc"
copy_and_substitute "${SCRIPT_DIR}/templates/skills/create-rules-toc/SKILL.md" "${SKILLS_DIR}/create-rules-toc/SKILL.md"

echo "  skills/create-specs-toc/ ..."
mkdir -p "${SKILLS_DIR}/create-specs-toc"
copy_and_substitute "${SCRIPT_DIR}/templates/skills/create-specs-toc/SKILL.md" "${SKILLS_DIR}/create-specs-toc/SKILL.md"

echo "  skills/query-rules/ ..."
mkdir -p "${SKILLS_DIR}/query-rules"
copy_and_substitute "${SCRIPT_DIR}/templates/skills/query-rules/SKILL.md" "${SKILLS_DIR}/query-rules/SKILL.md"

echo "  skills/query-specs/ ..."
mkdir -p "${SKILLS_DIR}/query-specs"
copy_and_substitute "${SCRIPT_DIR}/templates/skills/query-specs/SKILL.md" "${SKILLS_DIR}/query-specs/SKILL.md"

echo "  skills/setup-config/ ..."
mkdir -p "${SKILLS_DIR}/setup-config"
copy_and_substitute "${SCRIPT_DIR}/templates/skills/setup-config/SKILL.md" "${SKILLS_DIR}/setup-config/SKILL.md"

# Copy doc-advisor resources (docs, scripts)
echo "  doc-advisor/ ..."

# Copy templates/doc-advisor/ to .claude/doc-advisor/
copy_dir_with_substitution "${SCRIPT_DIR}/templates/doc-advisor" "${DOC_ADVISOR_DIR}"

echo ""
printf "${GREEN}==========================================${NC}\n"
printf "${GREEN}Setup Complete${NC}\n"
printf "${GREEN}==========================================${NC}\n"
echo ""
echo "Files created at:"
echo "  ${CLAUDE_DIR}/"
echo "    agents/            # Worker agents (toc-updater)"
echo "    skills/            # Skills (query-*, create-*-toc)"
echo "    doc-advisor/       # Docs, scripts, ToC files"

# Save settings for next run
cat > "$LAST_SETUP_FILE" << EOF
# Last setup settings (auto-generated)
LAST_AGENT_MODEL="${AGENT_MODEL}"
EOF

echo ""
echo "Next steps:"
echo "  1. Start Claude Code:"
printf "     cd ${BLUE}$(display_path "${TARGET_DIR}")${NC}\n"
echo "     claude"
if [[ "$HAS_DOC_STRUCTURE" != "true" ]]; then
    printf "  2. Run ${YELLOW}/setup-config${NC} to configure document directories\n"
    printf "  3. Run ${YELLOW}/create-rules-toc --full${NC} for initial ToC generation\n"
    printf "  4. Run ${YELLOW}/create-specs-toc --full${NC} for initial ToC generation\n"
else
    printf "  2. Run ${YELLOW}/create-rules-toc --full${NC} for initial ToC generation\n"
    printf "  3. Run ${YELLOW}/create-specs-toc --full${NC} for initial ToC generation\n"
fi
echo ""
