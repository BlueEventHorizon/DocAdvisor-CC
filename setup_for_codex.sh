#!/bin/bash
# Doc Advisor setup script for Codex project-local bridge installs.
# Created by: k2moons

set -euo pipefail

if [ -z "${BASH_VERSION:-}" ] || ! ( eval ': < <(:)' ) 2>/dev/null; then
    exec bash "$0" "$@"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR=""
SOURCE_DIR="${SCRIPT_DIR}/bw-cc-plugins/plugins/doc-advisor"
PROFILE_PATH="${SCRIPT_DIR}/codex_install_profiles/doc-advisor/current.yaml"
CODEX_SET_DIR="${SCRIPT_DIR}/codex_skill_set"

display_path() { printf '%s' "${1/#$HOME/\~}"; }

usage() {
    cat <<'EOF'
Doc Advisor setup for Codex

Usage:
  ./setup_for_codex.sh TARGET_DIR
  ./setup_for_codex.sh --source SOURCE_DIR TARGET_DIR
  ./setup_for_codex.sh --profile PROFILE_PATH TARGET_DIR
  ./setup_for_codex.sh --codex-set CODEX_SET_DIR TARGET_DIR
  ./setup_for_codex.sh --list-profiles
  ./setup_for_codex.sh -h, --help

This installs the reviewed codex_skill_set/ as a project-local bridge:
  TARGET_DIR/.codex/doc-advisor/skills/
  TARGET_DIR/.codex/doc-advisor/resources/
  TARGET_DIR/AGENTS.md managed bridge section

Install fails when the source plugin version, source commit, layout hash, or
codex_skill_set hash does not match the install profile.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list-profiles)
            find "${SCRIPT_DIR}/codex_install_profiles" -name "*.yaml" -type f | sort
            exit 0
            ;;
        --source)
            shift
            SOURCE_DIR="${1:?--source requires a path}"
            shift
            ;;
        --profile)
            shift
            PROFILE_PATH="${1:?--profile requires a path}"
            shift
            ;;
        --codex-set)
            shift
            CODEX_SET_DIR="${1:?--codex-set requires a path}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [[ -n "$TARGET_DIR" ]]; then
                echo "Error: Too many arguments" >&2
                usage >&2
                exit 1
            fi
            TARGET_DIR="$1"
            shift
            ;;
    esac
done

if [[ -z "$TARGET_DIR" ]]; then
    echo "Error: TARGET_DIR is required" >&2
    usage >&2
    exit 1
fi

SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
PROFILE_PATH="${PROFILE_PATH/#\~/$HOME}"
CODEX_SET_DIR="${CODEX_SET_DIR/#\~/$HOME}"
TARGET_DIR="${TARGET_DIR/#\~/$HOME}"

SOURCE_DIR="$(cd "$SOURCE_DIR" 2>/dev/null && pwd)" || {
    echo "Error: source directory does not exist: $SOURCE_DIR" >&2
    exit 1
}
TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd)" || {
    echo "Error: target directory does not exist: $TARGET_DIR" >&2
    exit 1
}
PROFILE_PATH="$(cd "$(dirname "$PROFILE_PATH")" 2>/dev/null && pwd)/$(basename "$PROFILE_PATH")"
CODEX_SET_DIR="$(cd "$CODEX_SET_DIR" 2>/dev/null && pwd)" || {
    echo "Error: codex skill set directory does not exist: $CODEX_SET_DIR" >&2
    exit 1
}

if [[ ! -f "$PROFILE_PATH" ]]; then
    echo "Error: install profile not found: $PROFILE_PATH" >&2
    exit 1
fi
if [[ ! -f "${CODEX_SET_DIR}/manifest.yaml" ]]; then
    echo "Error: codex skill set manifest not found: ${CODEX_SET_DIR}/manifest.yaml" >&2
    exit 1
fi
if [[ ! -f "${SOURCE_DIR}/.claude-plugin/plugin.json" ]]; then
    echo "Error: invalid source directory: ${SOURCE_DIR}" >&2
    exit 1
fi

read_profile_value() {
    local key="$1"
    python3 - "$PROFILE_PATH" "$key" <<'PY'
import re
import sys
path, key = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
match = re.search(rf"^\s*{re.escape(key)}:\s*['\"]?([^'\"\n#]+)", text, re.M)
if match:
    print(match.group(1).strip())
PY
}

PROFILE_ID="$(read_profile_value profile_id)"
PROFILE_DOC_VERSION="$(read_profile_value plugin_version)"
PROFILE_FORGE_VERSION="$(read_profile_value forge_version)"
PROFILE_COMMIT="$(read_profile_value source_commit)"
PROFILE_LAYOUT_HASH="$(read_profile_value layout_hash)"
PROFILE_SET_HASH="$(read_profile_value codex_set_hash)"
PROFILE_REVIEWED="$(read_profile_value reviewed)"

if [[ -z "$PROFILE_DOC_VERSION" || -z "$PROFILE_COMMIT" || -z "$PROFILE_LAYOUT_HASH" || -z "$PROFILE_SET_HASH" ]]; then
    echo "Error: profile is missing required values: $PROFILE_PATH" >&2
    exit 1
fi

SOURCE_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "${SOURCE_DIR}/.claude-plugin/plugin.json")"
SOURCE_ROOT="$(cd "${SOURCE_DIR}/../.." && pwd)"
SOURCE_COMMIT="$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null || true)"
SOURCE_STATUS="$(git -C "$SOURCE_ROOT" status --short 2>/dev/null || true)"
SOURCE_LAYOUT_HASH="$(bash "${SCRIPT_DIR}/generate_codex_skill_set.sh" --print-layout-hash --source "$SOURCE_DIR")"
SET_HASH="$(python3 - "$CODEX_SET_DIR" <<'PY'
import hashlib
import sys
from pathlib import Path
root = Path(sys.argv[1])
h = hashlib.sha256()
for path in sorted(root.rglob("*")):
    if not path.is_file():
        continue
    rel = path.relative_to(root).as_posix()
    if rel == "manifest.yaml" or "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store":
        continue
    h.update(rel.encode())
    h.update(b"\0")
    h.update(path.read_bytes())
    h.update(b"\0")
print(h.hexdigest())
PY
)"

FORGE_SOURCE="${SOURCE_DIR%/doc-advisor}/forge"
FORGE_VERSION=""
if [[ -f "${FORGE_SOURCE}/.claude-plugin/plugin.json" ]]; then
    FORGE_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "${FORGE_SOURCE}/.claude-plugin/plugin.json")"
fi

fail_match() {
    printf "${RED}Error: %s${NC}\n" "$1" >&2
    exit 1
}

[[ "$SOURCE_VERSION" == "$PROFILE_DOC_VERSION" ]] || fail_match "source doc-advisor version mismatch: source=${SOURCE_VERSION}, profile=${PROFILE_DOC_VERSION}"
if [[ -n "$PROFILE_FORGE_VERSION" ]]; then
    [[ "$FORGE_VERSION" == "$PROFILE_FORGE_VERSION" ]] || fail_match "source forge version mismatch: source=${FORGE_VERSION}, profile=${PROFILE_FORGE_VERSION}"
fi
[[ "$SOURCE_COMMIT" == "$PROFILE_COMMIT" ]] || fail_match "source commit mismatch: source=${SOURCE_COMMIT}, profile=${PROFILE_COMMIT}"
[[ -z "$SOURCE_STATUS" ]] || fail_match "source tree is dirty; generate/review a new profile before install"
[[ "$SOURCE_LAYOUT_HASH" == "$PROFILE_LAYOUT_HASH" ]] || fail_match "source layout hash mismatch"
[[ "$SET_HASH" == "$PROFILE_SET_HASH" ]] || fail_match "codex_skill_set hash mismatch"
[[ "$PROFILE_REVIEWED" == "true" ]] || fail_match "profile is not reviewed"

TARGET_CODEX_ROOT="${TARGET_DIR}/.codex/doc-advisor"
TARGET_SKILLS="${TARGET_CODEX_ROOT}/skills"
TARGET_RESOURCES="${TARGET_CODEX_ROOT}/resources"
AGENTS_FILE="${TARGET_DIR}/AGENTS.md"
START_MARKER="<!-- doc-advisor-codex-bridge-start -->"
END_MARKER="<!-- doc-advisor-codex-bridge-end -->"

printf "${GREEN}==========================================${NC}\n"
printf "${GREEN}Doc Advisor Codex Setup${NC}\n"
printf "${GREEN}==========================================${NC}\n"
echo "Source:  $(display_path "$SOURCE_DIR") (v${SOURCE_VERSION})"
echo "Forge:   $(display_path "$FORGE_SOURCE") (v${FORGE_VERSION:-unknown})"
echo "Profile: $(display_path "$PROFILE_PATH")"
echo "Set:     $(display_path "$CODEX_SET_DIR")"
echo "Target:  $(display_path "$TARGET_DIR")"
echo ""

mkdir -p "$TARGET_CODEX_ROOT"
rm -rf "$TARGET_SKILLS" "$TARGET_RESOURCES"
mkdir -p "$TARGET_SKILLS" "$TARGET_RESOURCES"
python3 - "$CODEX_SET_DIR" "$TARGET_CODEX_ROOT" <<'PY'
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])

def ignore(_directory, names):
    ignored = []
    for name in names:
        if name == "__pycache__" or name == ".DS_Store" or name.endswith(".pyc"):
            ignored.append(name)
    return ignored

for name in ("skills", "resources"):
    shutil.copytree(source / name, target / name, dirs_exist_ok=True, ignore=ignore)
PY
mkdir -p "${TARGET_CODEX_ROOT}/toc/rules" "${TARGET_CODEX_ROOT}/toc/specs" "${TARGET_CODEX_ROOT}/index/rules" "${TARGET_CODEX_ROOT}/index/specs"

cat > "${TARGET_CODEX_ROOT}/.source_version" <<EOF
profile_id: ${PROFILE_ID}
doc_advisor_version: ${SOURCE_VERSION}
forge_version: ${FORGE_VERSION:-unknown}
source_commit: ${SOURCE_COMMIT}
layout_hash: ${SOURCE_LAYOUT_HASH}
codex_set_hash: ${SET_HASH}
install_target_kind: project-local-bridge
EOF

BRIDGE_CONTENT="$(cat <<'EOF'
${START_MARKER}

## Doc Advisor / forge Codex Bridge

This project has a project-local Doc Advisor bridge installed for Codex.

Use the skill instructions under `.codex/doc-advisor/skills/` when the user request matches these functions:

| Function | Typical trigger | Path |
| --- | --- | --- |
| rules ToC update | rules documents were added, edited, deleted, or the user asks to rebuild rules ToC | `.codex/doc-advisor/skills/create-rules-toc/SKILL.md` |
| specs ToC update | requirements, design, or plan documents were added, edited, deleted, or the user asks to rebuild specs ToC | `.codex/doc-advisor/skills/create-specs-toc/SKILL.md` |
| rules query | the user asks about development rules, coding standards, architecture rules, or workflow guides | `.codex/doc-advisor/skills/query-rules/SKILL.md` |
| specs query | the user asks about requirements, designs, plans, or product/spec documents | `.codex/doc-advisor/skills/query-specs/SKILL.md` |
| document structure setup | `.doc_structure.yaml` is missing/stale, or the user asks to configure document directories | `.codex/doc-advisor/skills/setup-doc-structure/SKILL.md` |

Bundled references and scripts live under `.codex/doc-advisor/resources/`.
Doc Advisor ToC and index output should use `.codex/doc-advisor/toc/` and `.codex/doc-advisor/index/`.

Unsupported in this bridge: `create-code-index`, `query-code`.
Excluded from this bridge: forge localhost monitor.

Source profile: `__PROFILE_ID__`.

${END_MARKER}
EOF
)"
BRIDGE_CONTENT="${BRIDGE_CONTENT//'${START_MARKER}'/$START_MARKER}"
BRIDGE_CONTENT="${BRIDGE_CONTENT//'${END_MARKER}'/$END_MARKER}"
BRIDGE_CONTENT="${BRIDGE_CONTENT//__PROFILE_ID__/$PROFILE_ID}"

python3 - "$AGENTS_FILE" "$START_MARKER" "$END_MARKER" "$BRIDGE_CONTENT" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
start = sys.argv[2]
end = sys.argv[3]
section = sys.argv[4].rstrip() + "\n"

original = path.read_text(encoding="utf-8") if path.exists() else ""
if start in original and end in original:
    before = original.split(start, 1)[0].rstrip()
    after = original.split(end, 1)[1].lstrip()
    new_text = (before + "\n\n" if before else "") + section + ("\n" + after if after else "")
else:
    new_text = original.rstrip()
    if new_text:
        new_text += "\n\n"
    new_text += section
path.write_text(new_text, encoding="utf-8")
PY

if grep -R -n -E '\$\{CLAUDE_PLUGIN_ROOT\}|/doc-advisor:|/forge:|AskUserQuestion|Task\(subagent_type:' "$TARGET_CODEX_ROOT" >/dev/null 2>&1; then
    printf "${RED}Error: Claude-specific references remain in installed Codex bridge${NC}\n" >&2
    grep -R -n -E '\$\{CLAUDE_PLUGIN_ROOT\}|/doc-advisor:|/forge:|AskUserQuestion|Task\(subagent_type:' "$TARGET_CODEX_ROOT" >&2 || true
    exit 1
fi

printf "${GREEN}Installed Codex project-local bridge.${NC}\n"
printf "${BLUE}Updated:${NC} %s\n" "$(display_path "$AGENTS_FILE")"
printf "${BLUE}Installed:${NC} %s\n" "$(display_path "$TARGET_CODEX_ROOT")"
