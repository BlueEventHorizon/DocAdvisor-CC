#!/usr/bin/env python3
"""
Generate pending YAML templates in .claude/doc-advisor/toc/{category}/.toc_work/
(doc-advisor plugin)

Usage:
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category rules [--full]
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category specs [--full]
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/create_pending_yaml.py --category rules --check

Options:
    --category  Target category: rules or specs (required)
    --full      Process all files (default: changed files only)
    --check     Check staleness only (no file creation)

Run from: Project root
"""

import json
import sys
import argparse
import hashlib

from toc_utils import init_common_config, should_exclude, resolve_config_path, rglob_follow_symlinks, normalize_path, calculate_file_hash, load_checksums, write_checksums_yaml, ConfigNotReadyError, log
from toc_utils import get_all_md_files as _toc_get_all_md_files

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
ROOT_DIRS = None  # list of (root_dir_path, root_dir_name)
TOC_WORK_DIR = None
CHECKSUMS_FILE = None
TOC_FILE = None
PATTERNS_CONFIG = None
TARGET_GLOB = None
EXCLUDE_PATTERNS = None
CATEGORY = None  # 'rules' or 'specs'
DOC_TYPES_MAP = None  # path → doc_type name (from .doc_structure.yaml)

# Pending YAML template (rules/specs 共通)
PENDING_TEMPLATE = """_meta:
  source_file: {source_file}
  doc_type: {doc_type}
  status: pending
  updated_at: null

title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
"""

# Directory name → doc_type mapping for fallback inference
DOC_TYPE_KEYWORDS = {
    'requirement': 'requirement', 'requirements': 'requirement',
    'design': 'design', 'designs': 'design',
    'plan': 'plan', 'plans': 'plan', 'planning': 'plan',
    'api': 'api', 'apis': 'api',
    'reference': 'reference', 'references': 'reference', 'ref': 'reference',
    'rule': 'rule', 'rules': 'rule',
    'spec': 'spec', 'specs': 'spec',
}


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Generate pending YAML templates for ToC generation'
    )
    parser.add_argument('--category', required=True, choices=['rules', 'specs'],
                        help='Document category: rules or specs')
    parser.add_argument('--full', action='store_true',
                        help='Process all files (default: changed files only)')
    parser.add_argument('--check', action='store_true',
                        help='Check staleness only (no file creation)')
    return parser.parse_args()


def init_config(category):
    """
    Initialize configuration.

    Args:
        category: 'rules' or 'specs'

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, ROOT_DIRS, TOC_WORK_DIR, CHECKSUMS_FILE
    global TOC_FILE, PATTERNS_CONFIG, TARGET_GLOB, EXCLUDE_PATTERNS, CATEGORY, DOC_TYPES_MAP

    CATEGORY = category

    try:
        common = init_common_config(category)
    except ConfigNotReadyError as e:
        print(json.dumps({"status": "config_required", "message": str(e)}))
        return False
    except (RuntimeError, FileNotFoundError) as e:
        log(f"Error: {e}")
        return False

    CONFIG = common['config']
    PROJECT_ROOT = common['project_root']
    ROOT_DIRS = common['root_dirs']
    PATTERNS_CONFIG = common['patterns_config']
    TARGET_GLOB = common['target_glob']
    EXCLUDE_PATTERNS = common['exclude_patterns']

    first_dir = common['first_dir']
    TOC_WORK_DIR = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), first_dir, PROJECT_ROOT)
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'), first_dir, PROJECT_ROOT)
    TOC_FILE = resolve_config_path(CONFIG.get('toc_file', f'{category}_toc.yaml'), first_dir, PROJECT_ROOT)
    DOC_TYPES_MAP = common['doc_types_map']
    return True


def determine_doc_type(root_dir_name, *, doc_types_map=None, category=None):
    """Determine doc_type from root_dir path using .doc_structure.yaml doc_types_map

    Args:
        root_dir_name: ルートディレクトリ名
        doc_types_map: パス→doc_type のマッピング辞書（省略時はグローバル変数 DOC_TYPES_MAP にフォールバック）
        category: カテゴリ名（省略時はグローバル変数 CATEGORY にフォールバック）
    """
    _doc_types_map = doc_types_map if doc_types_map is not None else DOC_TYPES_MAP
    _category = category if category is not None else CATEGORY

    if _doc_types_map:
        normalized = root_dir_name.rstrip('/')
        for path, doc_type in _doc_types_map.items():
            if path.rstrip('/') == normalized:
                return doc_type
    # Fallback: infer from directory name
    dir_lower = root_dir_name.rstrip('/').split('/')[-1].lower()
    if dir_lower in DOC_TYPE_KEYWORDS:
        return DOC_TYPE_KEYWORDS[dir_lower]
    # Default by category
    return _category.rstrip('s') if _category else 'unknown'


def get_pending_template():
    """Get the pending YAML template for the current category"""
    return PENDING_TEMPLATE


def has_substantive_content(filepath, min_content_lines=1):
    """
    Check if file has content beyond headers, blank lines, and frontmatter.

    frontmatter はファイル先頭の '---' で開始し、次の '---' で終了する
    ステートマシン方式で判定（先頭以外の '---' は通常行として扱う）。

    Args:
        filepath: Path to the file
        min_content_lines: Minimum number of substantive lines required

    Returns:
        bool: True if file has enough substantive content
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError, UnicodeDecodeError):
        return False

    if not content.strip():
        return False  # Empty file

    # ステートマシン: 'before_start' → 'in_frontmatter' → 'after_frontmatter'
    # 先頭行（空行を除く）が '---' の場合のみ frontmatter 開始
    state = 'before_start'
    content_lines = 0
    for line in content.splitlines():
        stripped = line.strip()

        if state == 'before_start':
            # 先頭の空行はスキップ
            if not stripped:
                continue
            if stripped == '---':
                state = 'in_frontmatter'
                continue
            else:
                # 先頭が '---' でない → frontmatter なし
                state = 'after_frontmatter'
                # fall through してこの行を評価
        elif state == 'in_frontmatter':
            if stripped == '---':
                state = 'after_frontmatter'
            continue

        # state == 'after_frontmatter'
        # Skip empty lines and header-only lines
        if not stripped or stripped.startswith('#'):
            continue

        content_lines += 1
        if content_lines >= min_content_lines:
            return True

    return False


def get_all_md_files():
    """Get list of target .md files across all root_dirs (symlink-aware).

    toc_utils.get_all_md_files() のラッパー。グローバル変数 ROOT_DIRS,
    TARGET_GLOB, EXCLUDE_PATTERNS を common_config 形式に変換して委譲する。
    """
    common_config = {
        'root_dirs': ROOT_DIRS,
        'target_glob': TARGET_GLOB,
        'exclude_patterns': EXCLUDE_PATTERNS,
    }
    return _toc_get_all_md_files(common_config)


def get_source_file_path(md_file, root_dir, root_dir_name):
    """Get project-relative path with root_dir prefix"""
    rel_path = normalize_path(md_file.relative_to(root_dir))
    return f"{root_dir_name}/{rel_path}"


def get_yaml_filename(source_file):
    """Generate YAML filename from source_file using path hash.

    Uses SHA256 hash to avoid:
    - Filename length limits (macOS 255 bytes)
    - Case-insensitive filesystem collisions
    - Special characters in directory/file names
    The original path is preserved in _meta.source_file inside the YAML.
    """
    hash_val = hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:16]
    return f"{hash_val}.yaml"


def create_pending_yaml(source_file, doc_type):
    """
    Create pending YAML file

    Args:
        source_file: Project-relative source file path
        doc_type: Document type (e.g., 'rule', 'requirement', 'design')

    Returns:
        Path: Created file path, None on error
    """
    yaml_name = get_yaml_filename(source_file)
    yaml_path = TOC_WORK_DIR / yaml_name
    template = get_pending_template()

    try:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(template.format(source_file=source_file, doc_type=doc_type))
        return yaml_path
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: File write error: {yaml_path} - {e}")
        return None


def save_pending_checksums(all_files, file_root_map):
    """Save checksums snapshot at Phase 1 time to .toc_work/

    Used to replace .toc_checksums.yaml after merge (Phase 3).
    This ensures that files modified during Phase 2 will be
    detected as changed in the next incremental run.
    """
    checksums = {}
    for md_file in all_files:
        root_dir, root_dir_name = file_root_map[md_file]
        source_file = get_source_file_path(md_file, root_dir, root_dir_name)
        hash_value = calculate_file_hash(md_file)
        if hash_value is not None:
            checksums[source_file] = hash_value

    pending_checksums_path = TOC_WORK_DIR / ".toc_checksums_pending.yaml"
    if write_checksums_yaml(checksums, pending_checksums_path,
                            header_comment="Phase 1 snapshot - used to replace .toc_checksums.yaml after merge"):
        log(f"Saved pending checksums: {len(checksums)} files")
    else:
        log(f"Warning: Failed to save pending checksums")


def main():
    args = parse_args()

    # Initialize configuration
    if not init_config(args.category):
        return 1

    # --check mode: report staleness without creating files
    if args.check:
        if not TOC_FILE.exists():
            log(f"WARNING: ToC not found. Run create-{CATEGORY}-toc to generate it.")
            return 0
        if not CHECKSUMS_FILE.exists():
            return 0
        old_checksums = load_checksums(CHECKSUMS_FILE)
        all_files, file_root_map = get_all_md_files()
        current_files = {}
        for f in all_files:
            root_dir, root_dir_name = file_root_map[f]
            current_files[get_source_file_path(f, root_dir, root_dir_name)] = f
        new_count = 0
        modified_count = 0
        for source_file, full_path in current_files.items():
            current_hash = calculate_file_hash(full_path)
            if current_hash is None:
                continue
            old_hash = old_checksums.get(source_file)
            if old_hash is None:
                new_count += 1
            elif current_hash != old_hash:
                modified_count += 1
        deleted_count = sum(1 for sf in old_checksums if sf not in current_files)
        total = new_count + modified_count + deleted_count
        if total > 0:
            parts = []
            if new_count:
                parts.append(f"{new_count} new")
            if modified_count:
                parts.append(f"{modified_count} modified")
            if deleted_count:
                parts.append(f"{deleted_count} deleted")
            log(f"WARNING: ToC may be stale ({', '.join(parts)}).")
            log(f"Consider running create-{CATEGORY}-toc to refresh the index.")
        return 0

    full_mode = args.full
    toc_name = f"{CATEGORY}_toc.yaml"

    # Force full mode if toc file doesn't exist
    if not TOC_FILE.exists():
        full_mode = True
        log(f"{toc_name} not found, running in full mode")

    # Force full mode if checksums doesn't exist
    if not full_mode and not CHECKSUMS_FILE.exists():
        full_mode = True
        log(".toc_checksums.yaml not found, running in full mode")

    # Get target files
    all_files, file_root_map = get_all_md_files()

    if full_mode:
        # Full mode: process all files
        target_files = all_files
        deleted_files = []
        log(f"Full mode: processing {len(target_files)} files")
    else:
        # Incremental mode: changed files only
        old_checksums = load_checksums(CHECKSUMS_FILE)
        current_files = {}
        for f in all_files:
            root_dir, root_dir_name = file_root_map[f]
            current_files[get_source_file_path(f, root_dir, root_dir_name)] = f

        target_files = []

        # Detect new/changed files
        for source_file, full_path in current_files.items():
            current_hash = calculate_file_hash(full_path)
            if current_hash is None:
                continue  # Skip on hash calculation failure
            old_hash = old_checksums.get(source_file)

            if old_hash is None:
                log(f"  [New] {source_file}")
                target_files.append(full_path)
            elif current_hash != old_hash:
                log(f"  [Modified] {source_file}")
                target_files.append(full_path)

        # Detect deleted files
        deleted_files = [
            sf for sf in old_checksums.keys()
            if sf not in current_files
        ]
        for sf in deleted_files:
            log(f"  [Deleted] {sf}")

        if not target_files and not deleted_files:
            log(f"No changes - {toc_name} is up to date")
            return 0

        if not target_files and deleted_files:
            log(f"\nDeleted files only: {len(deleted_files)} files")
            log("Use --delete-only with merge script")
            # Phase 1 スナップショットを保存（delete-only merge 後のチェックサム更新用）
            TOC_WORK_DIR.mkdir(parents=True, exist_ok=True)
            save_pending_checksums(all_files, file_root_map)
            return 0

        log(f"\nIncremental mode: {len(target_files)} changes, {len(deleted_files)} deletions")

    # Create .toc_work directory
    TOC_WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Save Phase 1 checksums snapshot (for all target files, not just changed ones)
    save_pending_checksums(all_files, file_root_map)

    # Generate pending YAMLs
    created_files = []
    skipped_files = []
    failed_count = 0
    for md_file in target_files:
        root_dir, root_dir_name = file_root_map[md_file]
        source_file = get_source_file_path(md_file, root_dir, root_dir_name)

        # Skip empty/stub files (no substantive content)
        if not has_substantive_content(md_file):
            log(f"  [Skipped] {source_file} (empty or headers only)")
            skipped_files.append(source_file)
            continue

        doc_type = determine_doc_type(root_dir_name)
        yaml_path = create_pending_yaml(source_file, doc_type)
        if yaml_path is None:
            failed_count += 1
            continue
        created_files.append(source_file)

    if skipped_files:
        log(f"\nSkipped {len(skipped_files)} empty/stub files")

    if failed_count > 0:
        log(f"\nWarning: {failed_count} files failed to create")

    log(f"\nCreated {len(created_files)} pending YAMLs:")
    for sf in created_files:
        log(f"  - {sf}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
