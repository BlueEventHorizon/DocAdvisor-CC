#!/bin/bash
# Generate reviewed Codex-native skill set from bw-cc-plugins sources.
# Created by: k2moons

set -euo pipefail

if [ -z "${BASH_VERSION:-}" ] || ! ( eval ': < <(:)' ) 2>/dev/null; then
    exec bash "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/bw-cc-plugins/plugins/doc-advisor"
OUTPUT_DIR="${SCRIPT_DIR}/codex_skill_set"
PROFILE_DIR="${SCRIPT_DIR}/codex_install_profiles/doc-advisor"
ANALYZE_ONLY=false
PRINT_LAYOUT_HASH=false

usage() {
    cat <<'EOF'
Generate Codex-native Doc Advisor skill set.

Usage:
  ./generate_codex_skill_set.sh [--source SOURCE_DIR] [--output OUTPUT_DIR] [--profile-dir PROFILE_DIR]
  ./generate_codex_skill_set.sh --analyze-only [--source SOURCE_DIR]
  ./generate_codex_skill_set.sh --print-layout-hash [--source SOURCE_DIR]

SOURCE_DIR must point to bw-cc-plugins/plugins/doc-advisor.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            shift
            SOURCE_DIR="${1:?--source requires a path}"
            shift
            ;;
        --output)
            shift
            OUTPUT_DIR="${1:?--output requires a path}"
            shift
            ;;
        --profile-dir)
            shift
            PROFILE_DIR="${1:?--profile-dir requires a path}"
            shift
            ;;
        --analyze-only)
            ANALYZE_ONLY=true
            shift
            ;;
        --print-layout-hash)
            PRINT_LAYOUT_HASH=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
SOURCE_DIR="$(cd "$SOURCE_DIR" 2>/dev/null && pwd)" || {
    echo "Error: source directory does not exist: $SOURCE_DIR" >&2
    exit 1
}

python3 - "$SCRIPT_DIR" "$SOURCE_DIR" "$OUTPUT_DIR" "$PROFILE_DIR" "$ANALYZE_ONLY" "$PRINT_LAYOUT_HASH" <<'PY'
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
doc_source = Path(sys.argv[2]).resolve()
output_dir = Path(sys.argv[3]).resolve()
profile_dir = Path(sys.argv[4]).resolve()
analyze_only = sys.argv[5] == "true"
print_layout_hash = sys.argv[6] == "true"

forge_source = doc_source.parent / "forge"

DOC_SKILLS = [
    "create-rules-toc",
    "create-specs-toc",
    "query-rules",
    "query-specs",
]
DISABLED_SKILLS = ["create-code-index", "query-code"]
DOC_DOCS = [
    "toc_format.md",
    "toc_orchestrator.md",
    "toc_update_workflow.md",
    "query_toc_workflow.md",
    "query_index_workflow.md",
]
DOC_SCRIPTS = [
    "create_pending_yaml.py",
    "write_pending.py",
    "merge_toc.py",
    "validate_toc.py",
    "create_checksums.py",
    "toc_utils.py",
    "filter_toc.py",
    "search_docs.py",
    "grep_docs.py",
    "embed_docs.py",
    "embedding_api.py",
]
FORBIDDEN = [
    "${CLAUDE_PLUGIN_ROOT}",
    "/doc-advisor:",
    "/forge:",
    "AskUserQuestion",
    "Task(subagent_type:",
]


def fail(message):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def read_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


if not (doc_source / ".claude-plugin" / "plugin.json").is_file():
    fail(f"invalid doc-advisor source: {doc_source}")
if not (forge_source / ".claude-plugin" / "plugin.json").is_file():
    fail(f"forge source not found next to doc-advisor source: {forge_source}")

doc_plugin = read_json(doc_source / ".claude-plugin" / "plugin.json")
forge_plugin = read_json(forge_source / ".claude-plugin" / "plugin.json")


def git_output(args, cwd):
    try:
        return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()
    except Exception:
        return ""


submodule_root = doc_source.parents[1]
source_commit = git_output(["rev-parse", "HEAD"], submodule_root) or "unknown"
source_branch = git_output(["branch", "--show-current"], submodule_root) or "unknown"
source_dirty = bool(git_output(["status", "--short"], submodule_root))


def iter_source_items():
    items = []
    for rel in [
        ".claude-plugin/plugin.json",
        "agents/toc-updater.md",
        *[f"skills/{name}/SKILL.md" for name in DOC_SKILLS],
        *[f"docs/{name}" for name in DOC_DOCS],
        *[f"scripts/{name}" for name in DOC_SCRIPTS],
    ]:
        items.append((doc_source, rel))
    for rel in [
        ".claude-plugin/plugin.json",
        "skills/setup-doc-structure/SKILL.md",
        "skills/setup-doc-structure/classification_rules.md",
        "skills/doc-structure/SKILL.md",
        "skills/doc-structure/scripts/resolve_doc_structure.py",
        "docs/doc_structure_format.md",
    ]:
        items.append((forge_source, rel))
    for path in sorted((forge_source / "scripts" / "doc_structure").rglob("*")):
        if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts:
            items.append((forge_source, str(path.relative_to(forge_source))))
    return items


def hash_files(items):
    h = hashlib.sha256()
    for root, rel in sorted(items, key=lambda item: f"{item[0].name}/{item[1]}"):
        path = root / rel
        if not path.is_file():
            fail(f"required source file is missing: {path}")
        key = f"{root.name}/{rel}".replace(os.sep, "/")
        h.update(key.encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


layout_hash = hash_files(iter_source_items())
if print_layout_hash:
    print(layout_hash)
    sys.exit(0)


def write_analysis_only():
    print(f"doc_advisor_version: {doc_plugin.get('version')}")
    print(f"forge_version: {forge_plugin.get('version')}")
    print(f"source_branch: {source_branch}")
    print(f"source_commit: {source_commit}")
    print(f"source_dirty: {str(source_dirty).lower()}")
    print(f"layout_hash: {layout_hash}")


if analyze_only:
    write_analysis_only()
    sys.exit(0)


def transform_text(text, plugin):
    if plugin == "doc-advisor":
        replacements = [
            ("${CLAUDE_PLUGIN_ROOT}/skills/", ".codex/doc-advisor/skills/"),
            ("${CLAUDE_PLUGIN_ROOT}/docs/", ".codex/doc-advisor/resources/doc-advisor/docs/"),
            ("${CLAUDE_PLUGIN_ROOT}/scripts/", ".codex/doc-advisor/resources/doc-advisor/scripts/"),
            ("${CLAUDE_PLUGIN_ROOT}/agents/", ".codex/doc-advisor/resources/doc-advisor/agents/"),
            ("${CLAUDE_PLUGIN_ROOT}/", ".codex/doc-advisor/resources/doc-advisor/"),
        ]
    else:
        replacements = [
            ("${CLAUDE_PLUGIN_ROOT}/skills/", ".codex/doc-advisor/resources/forge/skills/"),
            ("${CLAUDE_PLUGIN_ROOT}/docs/", ".codex/doc-advisor/resources/forge/docs/"),
            ("${CLAUDE_PLUGIN_ROOT}/scripts/", ".codex/doc-advisor/resources/forge/scripts/"),
            ("${CLAUDE_PLUGIN_ROOT}/", ".codex/doc-advisor/resources/forge/"),
        ]
    for old, new in replacements:
        text = text.replace(old, new)

    text = text.replace(".claude/doc-advisor/", ".codex/doc-advisor/")
    text = text.replace("/forge:setup-doc-structure", "setup-doc-structure")
    text = text.replace("/doc-advisor:create-rules-toc", "create-rules-toc")
    text = text.replace("/doc-advisor:create-specs-toc", "create-specs-toc")
    text = text.replace("/doc-advisor:query-rules", "query-rules")
    text = text.replace("/doc-advisor:query-specs", "query-specs")
    text = text.replace("/doc-advisor:create-code-index", "create-code-index")
    text = text.replace("/doc-advisor:", "Doc Advisor bridge skill ")
    text = text.replace("/forge:", "forge bridge skill ")
    text = text.replace("AskUserQuestion", "user confirmation")
    text = text.replace("doc-advisor:toc-updater", "toc-updater reference")
    text = text.replace("Task(subagent_type:", "Codex subagent/reference task:")
    text = text.replace("Claude Code", "Codex")
    return text


def frontmatter_value(frontmatter, key):
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*?)(?=^\S|\Z)", re.M | re.S)
    match = pattern.search(frontmatter)
    if not match:
        return ""
    return match.group(1).rstrip()


def normalize_skill(source_text, plugin):
    body = source_text
    frontmatter = ""
    if source_text.startswith("---\n"):
        end = source_text.find("\n---\n", 4)
        if end != -1:
            frontmatter = source_text[4:end]
            body = source_text[end + 5 :]

    name = frontmatter_value(frontmatter, "name").strip().strip('"') or "unknown"
    description = frontmatter_value(frontmatter, "description").rstrip()
    if not description:
        description = f"Use this skill for {name}."

    description = transform_text(description, plugin)
    if "\n" in description or description.startswith("|"):
        if description.startswith("|"):
            description_lines = description.splitlines()[1:]
        else:
            description_lines = description.splitlines()
        description_yaml = "description: |\n" + "\n".join(f"  {line}" for line in description_lines).rstrip() + "\n"
    else:
        description_yaml = f"description: {description}\n"

    short_description = name.replace("-", " ")
    body = transform_text(body, plugin)
    return (
        "---\n"
        f"name: {name}\n"
        f"{description_yaml}"
        "metadata:\n"
        f"  short-description: {short_description}\n"
        "---\n\n"
        f"{body.lstrip()}"
    )


def copy_text(src, dst, plugin, *, skill=False):
    text = src.read_text(encoding="utf-8")
    if skill:
        text = normalize_skill(text, plugin)
    else:
        text = transform_text(text, plugin)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")


def copy_tree(src, dst, plugin):
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if path.name == ".DS_Store" or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        target = dst / rel
        if path.suffix in {".md", ".yaml", ".py", ".sh"}:
            copy_text(path, target, plugin)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


if output_dir.exists():
    shutil.rmtree(output_dir)

for skill in DOC_SKILLS:
    copy_text(
        doc_source / "skills" / skill / "SKILL.md",
        output_dir / "skills" / skill / "SKILL.md",
        "doc-advisor",
        skill=True,
    )

copy_text(
    forge_source / "skills" / "setup-doc-structure" / "SKILL.md",
    output_dir / "skills" / "setup-doc-structure" / "SKILL.md",
    "forge",
    skill=True,
)
copy_text(
    forge_source / "skills" / "setup-doc-structure" / "classification_rules.md",
    output_dir / "skills" / "setup-doc-structure" / "classification_rules.md",
    "forge",
)

copy_text(
    doc_source / "agents" / "toc-updater.md",
    output_dir / "resources" / "doc-advisor" / "agents" / "toc-updater.md",
    "doc-advisor",
)
for doc in DOC_DOCS:
    copy_text(
        doc_source / "docs" / doc,
        output_dir / "resources" / "doc-advisor" / "docs" / doc,
        "doc-advisor",
    )
for script in DOC_SCRIPTS:
    copy_text(
        doc_source / "scripts" / script,
        output_dir / "resources" / "doc-advisor" / "scripts" / script,
        "doc-advisor",
    )

copy_text(
    forge_source / "docs" / "doc_structure_format.md",
    output_dir / "resources" / "forge" / "docs" / "doc_structure_format.md",
    "forge",
)
copy_text(
    forge_source / "skills" / "doc-structure" / "SKILL.md",
    output_dir / "resources" / "forge" / "skills" / "doc-structure" / "SKILL.md",
    "forge",
    skill=True,
)
copy_text(
    forge_source / "skills" / "doc-structure" / "scripts" / "resolve_doc_structure.py",
    output_dir / "resources" / "forge" / "skills" / "doc-structure" / "scripts" / "resolve_doc_structure.py",
    "forge",
)
copy_tree(
    forge_source / "scripts" / "doc_structure",
    output_dir / "resources" / "forge" / "scripts" / "doc_structure",
    "forge",
)


def set_hash(root):
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
    return h.hexdigest()


codex_set_hash = set_hash(output_dir)
profile_id = f"{doc_plugin['version']}-{source_commit[:12]}-{layout_hash[:12]}"

manifest = f"""# Codex-native Doc Advisor skill set.
# Generated by: generate_codex_skill_set.sh
# Created by: k2moons

manifest_schema: 1
name: doc-advisor-codex-skill-set
install_target_kind: project-local-bridge
source:
  doc_advisor_version: {doc_plugin['version']}
  forge_version: {forge_plugin['version']}
  source_branch: {source_branch}
  source_commit: {source_commit}
  source_dirty: {str(source_dirty).lower()}
  layout_hash: {layout_hash}
codex_set_hash: {codex_set_hash}
skills:
  - create-rules-toc
  - create-specs-toc
  - query-rules
  - query-specs
  - setup-doc-structure
disabled_skills:
  - create-code-index
  - query-code
excluded_components:
  - forge/scripts/monitor
"""
(output_dir / "manifest.yaml").write_text(manifest, encoding="utf-8")

profile_dir.mkdir(parents=True, exist_ok=True)
profile_path = profile_dir / f"{profile_id}.yaml"
current_path = profile_dir / "current.yaml"
profile = f"""# Codex install profile for Doc Advisor.
# Generated by: generate_codex_skill_set.sh
# Created by: k2moons

profile_schema: 1
profile_id: {profile_id}
source:
  plugin: doc-advisor
  plugin_version: {doc_plugin['version']}
  forge_version: {forge_plugin['version']}
  source_branch: {source_branch}
  source_commit: {source_commit}
  source_dirty_allowed: false
  layout_hash: {layout_hash}
  plugin_json: .claude-plugin/plugin.json
compatibility:
  codex_skill_schema: 1
  install_target_kind: project-local-bridge
  generated_by: generate_codex_skill_set.sh
  codex_set_path: codex_skill_set
  codex_set_hash: {codex_set_hash}
  reviewed: true
native_set:
  skills:
    - skills/create-rules-toc
    - skills/create-specs-toc
    - skills/query-rules
    - skills/query-specs
    - skills/setup-doc-structure
  resources:
    - resources/doc-advisor
    - resources/forge
disabled_skills:
  - create-code-index
  - query-code
excluded_components:
  - forge/scripts/monitor
"""
profile_path.write_text(profile, encoding="utf-8")
current_path.write_text(profile, encoding="utf-8")

violations = []
for path in sorted(output_dir.rglob("*")):
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for needle in FORBIDDEN:
        if needle in text:
            violations.append(f"{path.relative_to(output_dir)} contains {needle}")
if violations:
    print("Forbidden Claude-specific references remain:", file=sys.stderr)
    for item in violations:
        print(f"  - {item}", file=sys.stderr)
    sys.exit(1)

print(f"Generated: {output_dir.relative_to(repo_root)}")
print(f"Profile:   {profile_path.relative_to(repo_root)}")
print(f"Current:   {current_path.relative_to(repo_root)}")
print(f"Layout:    {layout_hash}")
print(f"Set hash:  {codex_set_hash}")
PY
