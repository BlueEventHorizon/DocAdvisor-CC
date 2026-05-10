#!/usr/bin/env bash
# Test environment initializer for bw-cc-plugins pre-release testing.
# See: specs/test/DES-TST-001_test_environment_design.md
#
# Usage:
#   bash test_claude_skills/init_fixtures.sh setup    # Install plugins + store
#   bash test_claude_skills/init_fixtures.sh store    # Backup .doc_structure.yaml and swap
#   bash test_claude_skills/init_fixtures.sh restore  # Restore .doc_structure.yaml
#   bash test_claude_skills/init_fixtures.sh clean    # Remove build artifacts
#   bash test_claude_skills/init_fixtures.sh reset    # restore + clean
#   bash test_claude_skills/init_fixtures.sh status   # Show current state

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DOC_STRUCTURE="$PROJECT_ROOT/.doc_structure.yaml"
DOC_STRUCTURE_BAK="$PROJECT_ROOT/.doc_structure.yaml.bak"
TEST_TEMPLATE="$SCRIPT_DIR/test_doc_structure.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

msg_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
msg_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
msg_err()  { echo -e "${RED}[ERROR]${NC} $1"; }

is_stored() { [ -f "$DOC_STRUCTURE_BAK" ]; }

is_doc_db_installed() { [ -f "$PROJECT_ROOT/.claude/doc-db/scripts/build_index.py" ]; }

cmd_store() {
    if is_stored; then
        msg_err ".doc_structure.yaml.bak already exists (double store)."
        msg_err "Run 'restore' first, or manually remove the .bak file."
        exit 1
    fi

    if [ ! -f "$DOC_STRUCTURE" ]; then
        msg_err ".doc_structure.yaml not found at project root."
        exit 1
    fi

    if [ ! -f "$TEST_TEMPLATE" ]; then
        msg_err "Test template not found: $TEST_TEMPLATE"
        exit 1
    fi

    cp "$DOC_STRUCTURE" "$DOC_STRUCTURE_BAK"
    cp "$TEST_TEMPLATE" "$DOC_STRUCTURE"
    msg_ok "Stored .doc_structure.yaml -> .doc_structure.yaml.bak"
    msg_ok "Swapped with test template (test_claude_skills/test_doc_structure.yaml)"
}

cmd_restore() {
    if ! is_stored; then
        msg_err ".doc_structure.yaml.bak not found (not stored)."
        exit 1
    fi

    mv "$DOC_STRUCTURE_BAK" "$DOC_STRUCTURE"
    msg_ok "Restored .doc_structure.yaml from backup"

    if command -v git >/dev/null 2>&1; then
        diff_output=$(cd "$PROJECT_ROOT" && git diff .doc_structure.yaml 2>/dev/null || true)
        if [ -z "$diff_output" ]; then
            msg_ok "git diff: no changes (clean)"
        else
            msg_warn "git diff: .doc_structure.yaml has uncommitted changes"
        fi
    fi
}

cmd_clean() {
    local cleaned=false

    if [ -d "$PROJECT_ROOT/.claude/doc-db/index" ]; then
        rm -rf "$PROJECT_ROOT/.claude/doc-db/index"
        msg_ok "Removed .claude/doc-db/index/"
        cleaned=true
    fi

    if [ -d "$PROJECT_ROOT/.claude/doc-advisor/index" ]; then
        rm -rf "$PROJECT_ROOT/.claude/doc-advisor/index"
        msg_ok "Removed .claude/doc-advisor/index/"
        cleaned=true
    fi

    if ! $cleaned; then
        msg_ok "No build artifacts to clean"
    fi
}

cmd_setup() {
    if ! is_doc_db_installed; then
        msg_ok "Installing plugins (doc-advisor + doc-db)..."
        (cd "$PROJECT_ROOT" && yes | bash setup.sh --source bw-cc-plugins/plugins/doc-advisor --with-doc-db .)
        echo ""
    else
        msg_ok "Plugins already installed"
    fi

    cmd_store
    echo ""
    msg_ok "Test environment ready. Run your tests, then: bash test_claude_skills/init_fixtures.sh reset"
}

cmd_reset() {
    if is_stored; then
        cmd_restore
    else
        msg_ok ".doc_structure.yaml not stored (skipping restore)"
    fi
    cmd_clean
    echo ""
    msg_ok "Test environment reset complete"
}

cmd_status() {
    echo "=== Test Environment Status ==="
    echo ""

    if is_stored; then
        msg_warn ".doc_structure.yaml: STORED (test mode active)"
    else
        msg_ok ".doc_structure.yaml: NORMAL"
    fi

    if is_doc_db_installed; then
        msg_ok "doc-db: installed"
    else
        msg_warn "doc-db: not installed"
    fi

    if [ -f "$PROJECT_ROOT/.claude/doc-advisor/scripts/search_docs.py" ]; then
        msg_ok "doc-advisor: installed"
    else
        msg_warn "doc-advisor: not installed"
    fi

    if [ -d "$PROJECT_ROOT/.claude/doc-db/index" ]; then
        local count
        count=$(find "$PROJECT_ROOT/.claude/doc-db/index" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
        msg_warn "doc-db index: ${count} index file(s) present"
    else
        msg_ok "doc-db index: clean"
    fi

    echo ""
    echo "Fixture documents:"
    find "$PROJECT_ROOT/test_claude_skills/fixtures" -name "*.md" -type f 2>/dev/null | sort | while read -r f; do
        echo "  $(echo "$f" | sed "s|$PROJECT_ROOT/||")"
    done
}

case "${1:-}" in
    setup)   cmd_setup   ;;
    store)   cmd_store   ;;
    restore) cmd_restore ;;
    clean)   cmd_clean   ;;
    reset)   cmd_reset   ;;
    status)  cmd_status  ;;
    *)
        echo "Usage: bash test_claude_skills/init_fixtures.sh {setup|store|restore|clean|reset|status}"
        echo ""
        echo "  setup    Install plugins + store .doc_structure.yaml"
        echo "  store    Backup .doc_structure.yaml and swap with test template"
        echo "  restore  Restore .doc_structure.yaml from backup"
        echo "  clean    Remove build artifacts (index files)"
        echo "  reset    restore + clean"
        echo "  status   Show current test environment state"
        exit 1
        ;;
esac
