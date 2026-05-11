#!/bin/bash
# Doc Advisor setup script for Codex environment-wide Skill installs.
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
SOURCE_DIR="${SCRIPT_DIR}/bw-cc-plugins/plugins/doc-advisor"
PROFILE_PATH="${SCRIPT_DIR}/codex_install_profiles/doc-advisor/current.yaml"
CODEX_SET_DIR="${SCRIPT_DIR}/codex_skill_set"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
PROJECT_DIR=""

display_path() { printf '%s' "${1/#$HOME/\~}"; }

usage() {
    cat <<'EOF'
Doc Advisor setup for Codex

Usage:
  ./setup_for_codex.sh
  ./setup_for_codex.sh --project PROJECT_DIR
  ./setup_for_codex.sh --codex-home CODEX_HOME_DIR
  ./setup_for_codex.sh --source SOURCE_DIR
  ./setup_for_codex.sh --profile PROFILE_PATH
  ./setup_for_codex.sh --codex-set CODEX_SET_DIR
  ./setup_for_codex.sh --list-profiles
  ./setup_for_codex.sh -h, --help

This installs the reviewed codex_skill_set/ as ordinary environment-wide Codex
Skills:

  ${CODEX_HOME:-~/.codex}/skills/
    create-rules-toc/
    create-specs-toc/
    query-rules/
    query-specs/
    setup-doc-structure/
    start-requirements/
    start-design/
    start-plan/

  ${CODEX_HOME:-~/.codex}/doc-advisor/
    resources/
    manifest.yaml
    install.yaml

When --project is provided, the script also initializes project runtime state:

  PROJECT_DIR/.codex/state/doc-advisor/
  PROJECT_DIR/AGENTS.md managed Doc Advisor section

Codex discovers ordinary Skills from CODEX_HOME. Restart Codex after install if
the new or updated Skills are not visible in the current session.
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
        --codex-home)
            shift
            CODEX_HOME_DIR="${1:?--codex-home requires a path}"
            shift
            ;;
        --project)
            shift
            PROJECT_DIR="${1:?--project requires a path}"
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
            echo "Error: Unexpected argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
PROFILE_PATH="${PROFILE_PATH/#\~/$HOME}"
CODEX_SET_DIR="${CODEX_SET_DIR/#\~/$HOME}"
CODEX_HOME_DIR="${CODEX_HOME_DIR/#\~/$HOME}"
PROJECT_DIR="${PROJECT_DIR/#\~/$HOME}"

SOURCE_DIR="$(cd "$SOURCE_DIR" 2>/dev/null && pwd)" || {
    echo "Error: source directory does not exist: $SOURCE_DIR" >&2
    exit 1
}
PROFILE_PATH="$(cd "$(dirname "$PROFILE_PATH")" 2>/dev/null && pwd)/$(basename "$PROFILE_PATH")"
CODEX_SET_DIR="$(cd "$CODEX_SET_DIR" 2>/dev/null && pwd)" || {
    echo "Error: codex skill set directory does not exist: $CODEX_SET_DIR" >&2
    exit 1
}
CODEX_HOME_DIR="$(python3 - "$CODEX_HOME_DIR" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
)"
if [[ -n "$PROJECT_DIR" ]]; then
    PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)" || {
        echo "Error: project directory does not exist: $PROJECT_DIR" >&2
        exit 1
    }
fi

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
PROFILE_INSTALL_KIND="$(read_profile_value install_target_kind)"

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
[[ "$PROFILE_INSTALL_KIND" == "environment-skill" ]] || fail_match "profile install target is not environment-skill"

HOME_ABS="$(python3 - "$HOME" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
)"
refuse_codex_home() {
    local label="$1"
    local path="$2"
    [[ -n "$path" ]] || return 0
    local resolved
    resolved="$(python3 - "$path" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
)"
    if [[ "$CODEX_HOME_DIR" == "$resolved" ]]; then
        fail_match "refusing unsafe --codex-home (${label}): ${CODEX_HOME_DIR}"
    fi
}
[[ "$CODEX_HOME_DIR" != "/" ]] || fail_match "refusing unsafe --codex-home: /"
refuse_codex_home "HOME" "$HOME_ABS"
refuse_codex_home "repository root" "$SCRIPT_DIR"
refuse_codex_home "source plugin" "$SOURCE_DIR"
refuse_codex_home "codex skill set" "$CODEX_SET_DIR"
refuse_codex_home "project" "$PROJECT_DIR"

SKILLS_DIR="${CODEX_HOME_DIR}/skills"
DOC_ADVISOR_CODEX_ROOT="${CODEX_HOME_DIR}/doc-advisor"
RESOURCES_DIR="${DOC_ADVISOR_CODEX_ROOT}/resources"
INSTALL_METADATA="${DOC_ADVISOR_CODEX_ROOT}/install.yaml"

START_MARKER="<!-- doc-advisor-codex-bridge-start -->"
END_MARKER="<!-- doc-advisor-codex-bridge-end -->"

printf "${GREEN}==========================================${NC}\n"
printf "${GREEN}Doc Advisor Codex Skill Setup${NC}\n"
printf "${GREEN}==========================================${NC}\n"
echo "Source:      $(display_path "$SOURCE_DIR") (v${SOURCE_VERSION})"
echo "Forge:       $(display_path "$FORGE_SOURCE") (v${FORGE_VERSION:-unknown})"
echo "Profile:     $(display_path "$PROFILE_PATH")"
echo "Set:         $(display_path "$CODEX_SET_DIR")"
echo "CODEX_HOME:  $(display_path "$CODEX_HOME_DIR")"
echo "Skills:      $(display_path "$SKILLS_DIR")"
echo "Resources:   $(display_path "$RESOURCES_DIR")"
if [[ -n "$PROJECT_DIR" ]]; then
    echo "Project:     $(display_path "$PROJECT_DIR")"
fi
echo ""

mkdir -p "$SKILLS_DIR" "$DOC_ADVISOR_CODEX_ROOT"
python3 - "$CODEX_SET_DIR" "$SKILLS_DIR" "$DOC_ADVISOR_CODEX_ROOT" "$SOURCE_VERSION" "$FORGE_VERSION" "$PROFILE_ID" "$SOURCE_COMMIT" "$SOURCE_LAYOUT_HASH" "$SET_HASH" <<'PY'
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
skills_dir = Path(sys.argv[2])
codex_root = Path(sys.argv[3])
doc_version = sys.argv[4]
forge_version = sys.argv[5] or "unknown"
profile_id = sys.argv[6]
source_commit = sys.argv[7]
layout_hash = sys.argv[8]
set_hash = sys.argv[9]

managed_skills = [
    "create-rules-toc",
    "create-specs-toc",
    "query-rules",
    "query-specs",
    "setup-doc-structure",
    "start-requirements",
    "start-design",
    "start-plan",
]

def ignore(_directory, names):
    return [
        name
        for name in names
        if name == "__pycache__" or name == ".DS_Store" or name.endswith(".pyc")
    ]

skills_dir.mkdir(parents=True, exist_ok=True)
for skill in managed_skills:
    target = skills_dir / skill
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.copytree(source / "skills" / skill, target, ignore=ignore)

resources_dir = codex_root / "resources"
for name in ["doc-advisor", "forge"]:
    target = resources_dir / name
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.copytree(source / "resources" / name, target, ignore=ignore)
shutil.copy2(source / "manifest.yaml", codex_root / "manifest.yaml")

metadata = f"""profile_id: {profile_id}
doc_advisor_version: {doc_version}
forge_version: {forge_version}
source_commit: {source_commit}
layout_hash: {layout_hash}
codex_set_hash: {set_hash}
install_target_kind: environment-skill
"""
(codex_root / "install.yaml").write_text(metadata, encoding="utf-8")
PY

if [[ -n "$PROJECT_DIR" ]]; then
    TARGET_STATE="${PROJECT_DIR}/.codex/state/doc-advisor"
    TARGET_INSTALLS="${PROJECT_DIR}/.codex/installs"
    AGENTS_FILE="${PROJECT_DIR}/AGENTS.md"
    mkdir -p "${TARGET_STATE}/toc/rules" "${TARGET_STATE}/toc/specs" "${TARGET_STATE}/index/rules" "${TARGET_STATE}/index/specs" "$TARGET_INSTALLS"
    python3 - "$PROJECT_DIR" <<'PY'
import shutil
import sys
from pathlib import Path

project = Path(sys.argv[1])
managed_skills = [
    "create-code-index",
    "create-rules-toc",
    "create-specs-toc",
    "query-code",
    "query-rules",
    "query-specs",
    "setup-doc-structure",
    "start-requirements",
    "start-design",
    "start-plan",
]
managed_paths = [project / ".codex" / "skills" / name for name in managed_skills]
managed_paths.extend([
    project / ".codex" / "resources" / "doc-advisor",
    project / ".codex" / "resources" / "forge",
    project / ".codex" / "doc-advisor",
])
for path in managed_paths:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
for path in [project / ".codex" / "resources", project / ".codex" / "skills"]:
    try:
        path.rmdir()
    except OSError:
        pass
PY
    cat > "${TARGET_INSTALLS}/doc-advisor.yaml" <<EOF
profile_id: ${PROFILE_ID}
doc_advisor_version: ${SOURCE_VERSION}
forge_version: ${FORGE_VERSION:-unknown}
source_commit: ${SOURCE_COMMIT}
layout_hash: ${SOURCE_LAYOUT_HASH}
codex_set_hash: ${SET_HASH}
install_target_kind: environment-skill
codex_home: ${CODEX_HOME_DIR}
skills_path: ${SKILLS_DIR}
resources_path: ${RESOURCES_DIR}
EOF

    BRIDGE_CONTENT="$(cat <<'EOF'
${START_MARKER}

## Doc Advisor / forge Codex Skills

This project is configured to use the environment-wide Doc Advisor Codex Skills.

The installer places ordinary Skills under `${CODEX_HOME:-~/.codex}/skills/`.
Restart Codex if the new or updated Skills are not visible in the current session.

| Function | Typical trigger | Skill |
| --- | --- | --- |
| rules ToC update | rules documents were added, edited, deleted, or the user asks to rebuild rules ToC | `create-rules-toc` |
| specs ToC update | requirements, design, or plan documents were added, edited, deleted, or the user asks to rebuild specs ToC | `create-specs-toc` |
| rules query | the user asks about development rules, coding standards, architecture rules, or workflow guides | `query-rules` |
| specs query | the user asks about requirements, designs, plans, or product/spec documents | `query-specs` |
| document structure setup | `.doc_structure.yaml` is missing/stale, or the user asks to configure document directories | `setup-doc-structure` |
| requirements authoring | the user asks to start requirements, create requirements, derive requirements from code, or write a feature requirements document | `start-requirements` |
| design authoring | the user asks to start design, create a design document, or turn requirements into a design | `start-design` |
| plan authoring | the user asks to start planning, create a plan, or break a design into implementation tasks | `start-plan` |

Project runtime output should use `.codex/state/doc-advisor/toc/` and `.codex/state/doc-advisor/index/`.
Project install metadata is recorded in `.codex/installs/doc-advisor.yaml`.

Unsupported in this Skill set: `create-code-index`, `query-code`.
Excluded from this Skill set: forge localhost monitor, forge review automation, forge version update, forge cleanup.

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
fi

if grep -R -n -E '\$\{CLAUDE_PLUGIN_ROOT\}|DOC_ADVISOR_PLUGIN_ROOT|/doc-advisor:|/forge:|AskUserQuestion|Task\(subagent_type:|\.codex/resources/|\.codex/skills/' "$RESOURCES_DIR" "$SKILLS_DIR"/create-rules-toc "$SKILLS_DIR"/create-specs-toc "$SKILLS_DIR"/query-rules "$SKILLS_DIR"/query-specs "$SKILLS_DIR"/setup-doc-structure "$SKILLS_DIR"/start-requirements "$SKILLS_DIR"/start-design "$SKILLS_DIR"/start-plan >/dev/null 2>&1; then
    printf "${RED}Error: invalid references remain in installed Codex Skills${NC}\n" >&2
    grep -R -n -E '\$\{CLAUDE_PLUGIN_ROOT\}|DOC_ADVISOR_PLUGIN_ROOT|/doc-advisor:|/forge:|AskUserQuestion|Task\(subagent_type:|\.codex/resources/|\.codex/skills/' "$RESOURCES_DIR" "$SKILLS_DIR"/create-rules-toc "$SKILLS_DIR"/create-specs-toc "$SKILLS_DIR"/query-rules "$SKILLS_DIR"/query-specs "$SKILLS_DIR"/setup-doc-structure "$SKILLS_DIR"/start-requirements "$SKILLS_DIR"/start-design "$SKILLS_DIR"/start-plan >&2 || true
    exit 1
fi

printf "${GREEN}Installed Doc Advisor Codex Skills.${NC}\n"
printf "${BLUE}CODEX_HOME:${NC} %s\n" "$(display_path "$CODEX_HOME_DIR")"
printf "${BLUE}Skills:${NC} %s\n" "$(display_path "$SKILLS_DIR")"
printf "${BLUE}Resources:${NC} %s\n" "$(display_path "$RESOURCES_DIR")"
if [[ -n "$PROJECT_DIR" ]]; then
    printf "${BLUE}Project state:${NC} %s\n" "$(display_path "${PROJECT_DIR}/.codex/state/doc-advisor")"
    printf "${BLUE}Updated:${NC} %s\n" "$(display_path "${PROJECT_DIR}/AGENTS.md")"
fi
if [[ -d "${HOME}/plugins/doc-advisor" ]]; then
    printf "${YELLOW}Note:${NC} legacy plugin install still exists at %s; this script no longer modifies plugin marketplace entries.${NC}\n" "$(display_path "${HOME}/plugins/doc-advisor")"
fi
printf "${YELLOW}Next:${NC} Restart Codex if the new or updated Skills are not visible in this session.${NC}\n"
