#!/bin/bash
# Re-exec under non-POSIX bash if process substitution is unavailable.
# On macOS, `sh setup.sh` runs bash in POSIX mode (BASH_VERSION is still set
# but process substitution `< <(...)` is disabled), so we test the feature directly.
if [ -z "${BASH_VERSION:-}" ] || ! ( eval ': < <(:)' ) 2>/dev/null; then
    exec bash "$0" "$@"
fi
# Doc Advisor Setup Script
#
# Reads doc-advisor files from bw-cc-plugins (read-only source) and installs
# transformed files to the target project. Acts as an intermediary to avoid
# maintaining duplicate code.
#
# Usage:
#   ./setup.sh TARGET_DIR                       # Use submodule as source (default)
#   ./setup.sh --source SOURCE_DIR TARGET_DIR   # Use custom source
#   ./setup.sh -h, --help                       # Show help
#
# SOURCE_DIR: Path to bw-cc-plugins/plugins/doc-advisor/ (default: ./bw-cc-plugins/...)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Format path for display: replace $HOME with ~
display_path() { printf '%s' "${1/#$HOME/\~}"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAST_SETUP_FILE="${SCRIPT_DIR}/.last_setup"

# Load previous settings if available (reserved for future use)
if [[ -f "$LAST_SETUP_FILE" ]]; then
    : # No settings to load currently
fi

# Parse arguments
TARGET_DIR=""
SOURCE_DIR=""
WITH_ANVIL=false
WITH_XCODE=false
OPTIONAL_PLUGINS_SPECIFIED=false  # Track whether CLI flags were used

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            echo "Doc Advisor Setup Script"
            echo ""
            echo "Usage:"
            echo "  ./setup.sh TARGET_DIR                       # Use submodule as source"
            echo "  ./setup.sh --source SOURCE_DIR TARGET_DIR   # Use custom source"
            echo "  ./setup.sh --with-anvil TARGET_DIR          # Also install anvil plugin"
            echo "  ./setup.sh --with-xcode TARGET_DIR          # Also install xcode plugin"
            echo "  ./setup.sh -h, --help                       # Show help"
            echo ""
            echo "SOURCE_DIR: Path to bw-cc-plugins/plugins/doc-advisor/"
            echo "            Default: ./bw-cc-plugins/plugins/doc-advisor/ (git submodule)"
            echo "TARGET_DIR: Path to target project"
            echo ""
            echo "Optional plugins (opt-in, off by default):"
            echo "  --with-anvil    anvil: GitHub commit/create-pr skills"
            echo "  --with-xcode    xcode: iOS/macOS build/test skills"
            echo ""
            echo "This script creates:"
            echo "  TARGET_DIR/.claude/agents/         # Worker agents (toc-updater)"
            echo "  TARGET_DIR/.claude/skills/         # Skills (query-*, create-*-toc)"
            echo "  TARGET_DIR/.claude/doc-advisor/    # Docs, scripts, ToC files"
            echo "  TARGET_DIR/.claude/anvil/          # (if --with-anvil) anvil scripts"
            echo "  TARGET_DIR/.claude/xcode/          # (if --with-xcode) xcode scripts"
            echo ""
            echo "Transformations applied during copy:"
            echo '  ${CLAUDE_PLUGIN_ROOT}/  →  .claude/<plugin>/'
            echo "  /<plugin>:xxx           →  /xxx"
            echo "  /forge:setup-doc-structure → /setup-doc-structure"
            exit 0
            ;;
        --source)
            shift
            if [[ $# -eq 0 ]]; then
                echo "Error: --source requires a path argument"
                exit 1
            fi
            SOURCE_DIR="$1"
            shift
            ;;
        --with-anvil)
            WITH_ANVIL=true
            OPTIONAL_PLUGINS_SPECIFIED=true
            shift
            ;;
        --with-xcode)
            WITH_XCODE=true
            OPTIONAL_PLUGINS_SPECIFIED=true
            shift
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

# Default to submodule path if --source not specified
if [[ -z "$SOURCE_DIR" ]]; then
    SOURCE_DIR="${SCRIPT_DIR}/bw-cc-plugins/plugins/doc-advisor"
    if [[ ! -d "$SOURCE_DIR" ]]; then
        echo "Error: --source not specified and submodule not found at: bw-cc-plugins/"
        echo "  Either specify --source or initialize the submodule:"
        echo "    git submodule update --init"
        echo ""
        echo "Usage: ./setup.sh [--source SOURCE_DIR] TARGET_DIR"
        exit 1
    fi
fi

# Expand ~ and resolve source path
SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
SOURCE_DIR="$(cd "$SOURCE_DIR" 2>/dev/null && pwd)" || {
    echo "Error: Source directory does not exist: $SOURCE_DIR"
    exit 1
}

# Validate source: must contain .claude-plugin/plugin.json
if [[ ! -f "${SOURCE_DIR}/.claude-plugin/plugin.json" ]]; then
    printf "${RED}Error: Invalid source directory: $(display_path "$SOURCE_DIR")${NC}\n"
    echo "Expected: .claude-plugin/plugin.json not found"
    echo "Source should be: /path/to/bw-cc-plugins/plugins/doc-advisor"
    exit 1
fi

# Derive forge source path (sibling plugin directory)
SOURCE_FORGE="$(dirname "$SOURCE_DIR")/forge"

# Read source version from plugin.json
SOURCE_VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" \
    "${SOURCE_DIR}/.claude-plugin/plugin.json" 2>/dev/null) || {
    printf "${RED}Error: Failed to read version from plugin.json${NC}\n"
    exit 1
}

# Known compatible versions (update when transformation logic changes)
KNOWN_VERSIONS=("0.2.1")
VERSION_KNOWN=false
for kv in "${KNOWN_VERSIONS[@]}"; do
    if [[ "$SOURCE_VERSION" == "$kv" ]]; then
        VERSION_KNOWN=true
        break
    fi
done

if [[ "$VERSION_KNOWN" != "true" ]]; then
    printf "${YELLOW}Warning: Source version ${SOURCE_VERSION} is not in known list (${KNOWN_VERSIONS[*]})${NC}\n"
    printf "${YELLOW}Transformation logic may not be compatible. Proceed with caution.${NC}\n"
    echo ""
fi

# Check forge source availability
HAS_FORGE=false
if [[ -d "$SOURCE_FORGE" ]] && [[ -f "${SOURCE_FORGE}/skills/setup-doc-structure/SKILL.md" ]]; then
    HAS_FORGE=true
else
    printf "${YELLOW}Warning: Forge plugin not found at $(display_path "$SOURCE_FORGE")${NC}\n"
    printf "${YELLOW}  setup-doc-structure skill will not be installed${NC}\n"
    echo ""
fi

# Derive sibling plugin source paths (for optional plugins)
SOURCE_PLUGINS_ROOT="$(dirname "$SOURCE_DIR")"
SOURCE_ANVIL="${SOURCE_PLUGINS_ROOT}/anvil"
SOURCE_XCODE="${SOURCE_PLUGINS_ROOT}/xcode"

# Interactive prompt if not specified
INTERACTIVE_TARGET_PROMPT=false
if [[ -z "$TARGET_DIR" ]]; then
    INTERACTIVE_TARGET_PROMPT=true
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

# Interactive prompt for optional plugins (only when TARGET_DIR came from prompt
# AND no --with-* flag was specified — avoids surprising non-interactive callers)
if [[ "$INTERACTIVE_TARGET_PROMPT" == "true" && "$OPTIONAL_PLUGINS_SPECIFIED" == "false" ]]; then
    read -p "Install anvil plugin (commit / create-pr skills)? [y/N]: " _reply
    [[ "$_reply" =~ ^[Yy] ]] && WITH_ANVIL=true
    read -p "Install xcode plugin (build / test skills)? [y/N]: " _reply
    [[ "$_reply" =~ ^[Yy] ]] && WITH_XCODE=true
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
echo "Source:  $(display_path "${SOURCE_DIR}") (v${SOURCE_VERSION})"
if [[ "$HAS_FORGE" == "true" ]]; then
    echo "Forge:   $(display_path "${SOURCE_FORGE}") (available)"
fi
if [[ "$WITH_ANVIL" == "true" ]]; then
    echo "Anvil:   $(display_path "${SOURCE_ANVIL}") (requested)"
fi
if [[ "$WITH_XCODE" == "true" ]]; then
    echo "Xcode:   $(display_path "${SOURCE_XCODE}") (requested)"
fi
echo "Target:  $(display_path "${TARGET_DIR}")"
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
    printf "  Run ${YELLOW}/setup-doc-structure${NC} in Claude Code to auto-detect and configure.\n"
    echo ""
    echo "  Options:"
    echo "    [c] Continue setup (configure directories later with /setup-doc-structure)"
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

# Create directories
CLAUDE_DIR="${TARGET_DIR}/.claude"
DOC_ADVISOR_DIR="${CLAUDE_DIR}/doc-advisor"
AGENTS_DIR="${CLAUDE_DIR}/agents"
SKILLS_DIR="${CLAUDE_DIR}/skills"

# =============================================================================
# Version identifier functions
# =============================================================================
DOC_ADVISOR_VERSION="5.2"
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

# v3.0 moved docs to doc-advisor/ - clean if legacy files exist
# Only remove if docs contain files with old version markers (not from current source install)
if [[ -d "${DOC_ADVISOR_DIR}/docs" ]]; then
    if ls "${DOC_ADVISOR_DIR}/docs/"*.md &>/dev/null && \
       grep -ql 'doc-advisor-version-xK9XmQ:' "${DOC_ADVISOR_DIR}/docs/"*.md 2>/dev/null; then
        rm -rf "${DOC_ADVISOR_DIR}/docs"
        printf "${GREEN}Removed legacy: doc-advisor/docs/ (had old version markers)${NC}\n"
        LEGACY_CLEANED=1
    fi
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

# v4.3: classify-docs renamed to setup-doc-structure
OLD_CLASSIFY_DIR="${SKILLS_DIR}/classify-docs"
if [[ -d "$OLD_CLASSIFY_DIR" ]]; then
    rm -rf "$OLD_CLASSIFY_DIR"
    printf "${GREEN}Removed legacy: skills/classify-docs/ (renamed to setup-doc-structure/)${NC}\n"
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

# v5.0: setup-config renamed to setup-doc-structure
OLD_SETUP_CONFIG="${SKILLS_DIR}/setup-config"
if [[ -d "$OLD_SETUP_CONFIG" ]]; then
    rm -rf "$OLD_SETUP_CONFIG"
    printf "${GREEN}Removed legacy: skills/setup-config/ (renamed to setup-doc-structure/)${NC}\n"
    LEGACY_CLEANED=1
fi
# Remove legacy check_doc_structure.sh (pre-check moved into Python scripts)
if [[ -f "${DOC_ADVISOR_DIR}/scripts/check_doc_structure.sh" ]]; then
    rm -f "${DOC_ADVISOR_DIR}/scripts/check_doc_structure.sh"
    printf "${GREEN}Removed legacy: scripts/check_doc_structure.sh${NC}\n"
    LEGACY_CLEANED=1
fi

# v0.2.1: index skills integrated into query-* (4 skills removed)
for old_skill in "create-rules-index" "create-specs-index" "query-rules-index" "query-specs-index"; do
    if [[ -d "${SKILLS_DIR}/${old_skill}" ]]; then
        rm -rf "${SKILLS_DIR}/${old_skill}"
        printf "${GREEN}Removed legacy: skills/${old_skill}/ (integrated into query-*)${NC}\n"
        LEGACY_CLEANED=1
    fi
done

# Disabled skills: remove if previously installed
for disabled_skill in "create-code-index" "query-code"; do
    if [[ -d "${SKILLS_DIR}/${disabled_skill}" ]]; then
        rm -rf "${SKILLS_DIR}/${disabled_skill}"
        printf "${GREEN}Removed disabled: skills/${disabled_skill}/${NC}\n"
        LEGACY_CLEANED=1
    fi
done

# Legacy: doc-structure skill briefly placed under doc-advisor/skills/
# (relocated to canonical .claude/skills/doc-structure/)
if [[ -d "${DOC_ADVISOR_DIR}/skills" ]]; then
    rm -rf "${DOC_ADVISOR_DIR}/skills"
    printf "${GREEN}Removed legacy: doc-advisor/skills/ (skills moved to .claude/skills/)${NC}\n"
    LEGACY_CLEANED=1
fi

# Legacy template-mode files (no longer generated from templates/)
if [[ -f "${DOC_ADVISOR_DIR}/scripts/change_agent_model.sh" ]]; then
    rm -f "${DOC_ADVISOR_DIR}/scripts/change_agent_model.sh"
    printf "${GREEN}Removed legacy: scripts/change_agent_model.sh${NC}\n"
    LEGACY_CLEANED=1
fi
# Remove old classification_rules.md from doc-advisor/docs/ (moved to skills/setup-doc-structure/)
if [[ -f "${DOC_ADVISOR_DIR}/docs/classification_rules.md" ]]; then
    rm -f "${DOC_ADVISOR_DIR}/docs/classification_rules.md"
    printf "${GREEN}Removed legacy: docs/classification_rules.md (moved to skills/)${NC}\n"
    LEGACY_CLEANED=1
fi

if [[ $LEGACY_CLEANED -eq 1 ]]; then
    echo ""
fi

mkdir -p "${DOC_ADVISOR_DIR}"
mkdir -p "${DOC_ADVISOR_DIR}/toc/rules"    # ToC/checksums for rules
mkdir -p "${DOC_ADVISOR_DIR}/toc/specs"    # ToC/checksums for specs
mkdir -p "${AGENTS_DIR}"
mkdir -p "${SKILLS_DIR}"

# Function to copy and substitute variables in a file
# Applies transformations: plugin paths → template paths, skill name prefixes
copy_and_substitute() {
    local src="$1"
    local dst="$2"

    [[ -f "$src" ]] || return 0

    # Generate substituted content with all transformations:
    # 1. ${CLAUDE_PLUGIN_ROOT}/skills/ → .claude/skills/   (must run BEFORE rule 2)
    #    Skills always live under .claude/skills/ (Claude Code convention),
    #    not under the plugin's directory. Specific rule wins.
    # 2. ${CLAUDE_PLUGIN_ROOT}/ → .claude/doc-advisor/
    # 3. /doc-advisor:xxx → /xxx (remove plugin namespace prefix)
    # 4. /forge:setup-doc-structure → /setup-doc-structure
    # 5-7. Python path navigation fixes for forge's scripts/doc_structure/*.py
    #      that import resolve_doc_structure.py from the doc-structure SKILL.
    #      In forge native layout, the SKILL is a sibling of scripts/ (one level
    #      below plugin root). After install, the SKILL lives at .claude/skills/
    #      while the importing scripts live at .claude/doc-advisor/scripts/, so
    #      we need to walk one more parent to escape doc-advisor/ to .claude/.
    local new_content
    new_content=$(sed \
        -e 's|\${CLAUDE_PLUGIN_ROOT}/skills/|.claude/skills/|g' \
        -e 's|\${CLAUDE_PLUGIN_ROOT}/|.claude/doc-advisor/|g' \
        -e 's|/doc-advisor:|/|g' \
        -e 's|/forge:setup-doc-structure|/setup-doc-structure|g' \
        -e "s|parent\.parent\.parent / 'skills' / 'doc-structure'|parent.parent.parent.parent / 'skills' / 'doc-structure'|g" \
        -e "s|'\\.\\.', '\\.\\.', 'skills', 'doc-structure'|'..', '..', '..', 'skills', 'doc-structure'|g" \
        -e 's|SCRIPT_DIR\.parent\.parent  |SCRIPT_DIR.parent.parent.parent  |' \
        "$src")

    # If target file exists, compare content to skip unchanged files
    if [[ -f "$dst" ]]; then
        local old_content
        old_content=$(cat "$dst")

        if [[ "$new_content" = "$old_content" ]]; then
            printf "${BLUE}    Skipped (unchanged): %s${NC}\n" "$(basename "$dst")"
            return 0
        fi
    fi

    printf '%s\n' "$new_content" > "$dst"
}

# Function to copy directory recursively with variable substitution
# Excludes __pycache__/, *.pyc, .DS_Store
copy_dir_with_substitution() {
    local src_dir="${1%/}"  # Strip trailing slash for correct path matching
    local dst_dir="$2"

    if [[ ! -d "$src_dir" ]]; then
        printf "${RED}Warning: Source directory not found: ${src_dir}${NC}\n"
        return
    fi

    # Create destination directory
    mkdir -p "$dst_dir"

    # Copy files with substitution (exclude __pycache__, .pyc, .DS_Store)
    find "$src_dir" -type f \
        \( -name "*.md" -o -name "*.yaml" -o -name "*.py" -o -name "*.sh" \) \
        -not -path "*/__pycache__/*" \
        -not -name "*.pyc" \
        -not -name ".DS_Store" \
        | while read -r src_file; do
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

echo "Copying from source (v${SOURCE_VERSION})..."
echo ""

# =============================================================================
# Phase A: Copy from doc-advisor plugin source
# =============================================================================

# A1: Agents (overwrite only - preserve user's custom agents)
echo "  agents/ ..."
if [[ -d "${AGENTS_DIR}" ]]; then
    MANAGED_AGENTS="toc-updater.md"
    for agent in "${AGENTS_DIR}"/*.md; do
        [[ -e "$agent" ]] || continue
        name=$(basename "$agent")
        if ! echo "$MANAGED_AGENTS" | grep -qw "$name"; then
            printf "${BLUE}    Preserving: $name${NC}\n"
        fi
    done
fi
copy_dir_with_substitution "${SOURCE_DIR}/agents" "${AGENTS_DIR}"

# A2: Skills from doc-advisor (all skill directories under skills/)
# Skills listed in DISABLED_SKILLS are skipped (currently suspended upstream)
DISABLED_SKILLS="create-code-index query-code"
for skill_dir in "${SOURCE_DIR}/skills"/*/; do
    [[ -d "$skill_dir" ]] || continue
    skill_name=$(basename "$skill_dir")
    if echo " $DISABLED_SKILLS " | grep -qw "$skill_name"; then
        printf "${YELLOW}  skills/${skill_name}/ ... skipped (disabled)${NC}\n"
        continue
    fi
    echo "  skills/${skill_name}/ ..."
    copy_dir_with_substitution "$skill_dir" "${SKILLS_DIR}/${skill_name}"
done

# A3: Docs
echo "  doc-advisor/docs/ ..."
copy_dir_with_substitution "${SOURCE_DIR}/docs" "${DOC_ADVISOR_DIR}/docs"

# A4: Scripts
echo "  doc-advisor/scripts/ ..."
copy_dir_with_substitution "${SOURCE_DIR}/scripts" "${DOC_ADVISOR_DIR}/scripts"

# =============================================================================
# Phase B: Copy from forge plugin source (setup-doc-structure)
# =============================================================================

if [[ "$HAS_FORGE" == "true" ]]; then
    echo ""
    echo "  [forge] skills/setup-doc-structure/ ..."
    copy_dir_with_substitution "${SOURCE_FORGE}/skills/setup-doc-structure" "${SKILLS_DIR}/setup-doc-structure"

    # doc-structure SKILL: contains resolve_doc_structure.py used by forge's
    # scripts/doc_structure/*.py at runtime. Skills always live under
    # .claude/skills/ (Claude Code convention), regardless of user-invocable flag.
    # The Python path-navigation sed rules in copy_and_substitute() rewrite the
    # importers' parent counts so they reach .claude/ → skills/doc-structure/.
    if [[ -d "${SOURCE_FORGE}/skills/doc-structure" ]]; then
        echo "  [forge] skills/doc-structure/ ..."
        copy_dir_with_substitution "${SOURCE_FORGE}/skills/doc-structure" "${SKILLS_DIR}/doc-structure"
    fi

    echo "  [forge] doc-advisor/scripts/doc_structure/ ..."
    # Copy forge's doc_structure scripts (classify, check, migrate)
    FORGE_DOC_SCRIPTS="${SOURCE_FORGE}/scripts/doc_structure"
    if [[ -d "$FORGE_DOC_SCRIPTS" ]]; then
        copy_dir_with_substitution "$FORGE_DOC_SCRIPTS" "${DOC_ADVISOR_DIR}/scripts/doc_structure"
    fi

    # Copy doc_structure_format.md if it exists
    if [[ -f "${SOURCE_FORGE}/docs/doc_structure_format.md" ]]; then
        echo "  [forge] doc-advisor/docs/doc_structure_format.md ..."
        copy_and_substitute "${SOURCE_FORGE}/docs/doc_structure_format.md" "${DOC_ADVISOR_DIR}/docs/doc_structure_format.md"
    fi
fi

# =============================================================================
# Phase C: Optional plugins (--with-anvil / --with-xcode)
# =============================================================================
#
# Layout:
#   .claude/skills/<skill>/SKILL.md          ← skill entry (Claude Code discovers here)
#   .claude/<plugin>/skills/<skill>/scripts/ ← skill's sub-resources
#   .claude/<plugin>/scripts/                ← plugin-level scripts (anvil style)
#   .claude/<plugin>/.source_version         ← version record
#
# Transforms:
#   ${CLAUDE_PLUGIN_ROOT}/  →  .claude/<plugin>/
#   /<plugin>:xxx           →  /xxx
install_optional_plugin() {
    local plugin_name="$1"
    local plugin_source="$2"

    if [[ ! -d "$plugin_source" ]]; then
        printf "${YELLOW}Warning: ${plugin_name} plugin not found at $(display_path "$plugin_source"); skipping${NC}\n"
        return 1
    fi
    if [[ ! -f "${plugin_source}/.claude-plugin/plugin.json" ]]; then
        printf "${YELLOW}Warning: ${plugin_name} source invalid (no plugin.json); skipping${NC}\n"
        return 1
    fi

    local plugin_version
    plugin_version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" \
        "${plugin_source}/.claude-plugin/plugin.json" 2>/dev/null) || plugin_version="unknown"

    local plugin_target_dir="${CLAUDE_DIR}/${plugin_name}"
    mkdir -p "$plugin_target_dir"

    echo ""
    echo "  [${plugin_name}] installing (v${plugin_version})..."

    # Plugin-specific sed transform (stdin → stdout)
    _transform_plugin() {
        sed \
            -e "s|\${CLAUDE_PLUGIN_ROOT}/|.claude/${plugin_name}/|g" \
            -e "s|/${plugin_name}:|/|g"
    }

    _copy_file_transformed() {
        local src="$1" dst="$2"
        mkdir -p "$(dirname "$dst")"
        case "$src" in
            *.md|*.py|*.yaml|*.yml|*.sh)
                _transform_plugin < "$src" > "$dst"
                ;;
            *)
                cp "$src" "$dst"
                ;;
        esac
    }

    # Copy skills: SKILL.md → .claude/skills/<skill>/, rest → .claude/<plugin>/skills/<skill>/
    if [[ -d "${plugin_source}/skills" ]]; then
        local skill_dir skill_name f rel dst
        for skill_dir in "${plugin_source}/skills"/*/; do
            [[ -d "$skill_dir" ]] || continue
            skill_name=$(basename "${skill_dir%/}")
            echo "    skills/${skill_name}/ ..."

            mkdir -p "${SKILLS_DIR}/${skill_name}"
            if [[ -f "${skill_dir}SKILL.md" ]]; then
                _transform_plugin < "${skill_dir}SKILL.md" > "${SKILLS_DIR}/${skill_name}/SKILL.md"
            fi

            # Sub-resources (scripts/, extra docs, etc.) go to .claude/<plugin>/skills/<skill>/
            while IFS= read -r f; do
                rel="${f#${skill_dir}}"
                dst="${plugin_target_dir}/skills/${skill_name}/${rel}"
                _copy_file_transformed "$f" "$dst"
            done < <(find "$skill_dir" -mindepth 1 -type f \
                -not -path "*/__pycache__/*" \
                -not -name "*.pyc" \
                -not -name ".DS_Store" \
                -not -name "SKILL.md")
        done
    fi

    # Copy plugin-level scripts/ (anvil style)
    if [[ -d "${plugin_source}/scripts" ]]; then
        echo "    scripts/ ..."
        local f rel dst
        while IFS= read -r f; do
            rel="${f#${plugin_source}/scripts/}"
            dst="${plugin_target_dir}/scripts/${rel}"
            _copy_file_transformed "$f" "$dst"
        done < <(find "${plugin_source}/scripts" -type f \
            -not -path "*/__pycache__/*" \
            -not -name "*.pyc" \
            -not -name ".DS_Store")
    fi

    # Make all shell scripts executable (both tree locations)
    find "$plugin_target_dir" -name "*.sh" -type f -exec chmod +x {} \; 2>/dev/null || true

    # Record plugin version
    cat > "${plugin_target_dir}/.source_version" << EOF
# Auto-generated by setup.sh — do not edit
source_plugin: ${plugin_name}
source_plugin_version: ${plugin_version}
installed_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
source_path: ${plugin_source}
EOF
    return 0
}

if [[ "$WITH_ANVIL" == "true" ]]; then
    install_optional_plugin "anvil" "$SOURCE_ANVIL" || true
fi
if [[ "$WITH_XCODE" == "true" ]]; then
    install_optional_plugin "xcode" "$SOURCE_XCODE" || true
fi

# =============================================================================
# Record source version
# =============================================================================
cat > "${DOC_ADVISOR_DIR}/.source_version" << EOF
# Auto-generated by setup.sh — do not edit
source_plugin: doc-advisor
source_plugin_version: ${SOURCE_VERSION}
installed_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
source_path: ${SOURCE_DIR}
EOF

echo ""
printf "${GREEN}==========================================${NC}\n"
printf "${GREEN}Setup Complete${NC}\n"
printf "${GREEN}==========================================${NC}\n"
echo ""
echo "Source version: v${SOURCE_VERSION}"
echo ""
echo "Files created at:"
echo "  ${CLAUDE_DIR}/"
echo "    agents/            # Worker agents (toc-updater)"
echo "    skills/            # Skills (query-*, create-*-toc, setup-doc-structure)"
echo "    doc-advisor/       # Docs, scripts, ToC files"
if [[ "$WITH_ANVIL" == "true" && -d "${CLAUDE_DIR}/anvil" ]]; then
    echo "    anvil/             # Anvil plugin resources (commit, create-pr scripts)"
fi
if [[ "$WITH_XCODE" == "true" && -d "${CLAUDE_DIR}/xcode" ]]; then
    echo "    xcode/             # Xcode plugin resources (build, test scripts)"
fi

# Save settings for next run (reserved for future use)
cat > "$LAST_SETUP_FILE" << EOF
# Last setup settings (auto-generated)
SOURCE_DIR=${SOURCE_DIR}
EOF

echo ""
echo "Next steps:"
echo "  1. Start Claude Code:"
printf "     cd ${BLUE}$(display_path "${TARGET_DIR}")${NC}\n"
echo "     claude"
if [[ "$HAS_DOC_STRUCTURE" != "true" ]]; then
    printf "  2. Run ${YELLOW}/setup-doc-structure${NC} to configure document directories\n"
    printf "  3. Run ${YELLOW}/create-rules-toc --full${NC} for initial ToC generation\n"
    printf "  4. Run ${YELLOW}/create-specs-toc --full${NC} for initial ToC generation\n"
else
    printf "  2. Run ${YELLOW}/create-rules-toc --full${NC} for initial ToC generation\n"
    printf "  3. Run ${YELLOW}/create-specs-toc --full${NC} for initial ToC generation\n"
fi
echo ""
