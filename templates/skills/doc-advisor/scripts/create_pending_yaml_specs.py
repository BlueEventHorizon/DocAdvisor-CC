#!/usr/bin/env python3
"""
Generate pending YAML templates in .claude/doc-advisor/specs/.toc_work/

Usage:
    python3 .claude/skills/doc-advisor/scripts/create_pending_yaml_specs.py [--full]

Options:
    --full    Process all files (default: changed files only)

Run from: Project root
"""

import os
import sys
import hashlib
import re
from pathlib import Path

from toc_utils import get_project_root, load_config, should_exclude, resolve_config_path, get_default_target_dirs

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
SPECS_DIR = None
SPECS_DIR_NAME = None
TOC_WORK_DIR = None
CHECKSUMS_FILE = None
SPECS_TOC_FILE = None
PATTERNS_CONFIG = None
TARGET_DIRS = None
EXCLUDE_PATTERNS = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, SPECS_DIR, SPECS_DIR_NAME, TOC_WORK_DIR, CHECKSUMS_FILE
    global SPECS_TOC_FILE, PATTERNS_CONFIG, TARGET_DIRS, EXCLUDE_PATTERNS

    try:
        CONFIG = load_config('specs')
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    SPECS_DIR_NAME = CONFIG.get('root_dir', 'specs').rstrip('/')
    SPECS_DIR = PROJECT_ROOT / SPECS_DIR_NAME
    TOC_WORK_DIR = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), SPECS_DIR, PROJECT_ROOT)
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'), SPECS_DIR, PROJECT_ROOT)
    SPECS_TOC_FILE = resolve_config_path(CONFIG.get('toc_file', 'specs_toc.yaml'), SPECS_DIR, PROJECT_ROOT)
    PATTERNS_CONFIG = CONFIG.get('patterns', {})
    # target_dirs はマッピング形式: {doc_type: dir_name}
    TARGET_DIRS = PATTERNS_CONFIG.get('target_dirs', get_default_target_dirs())
    EXCLUDE_PATTERNS = PATTERNS_CONFIG.get('exclude', ['.toc_work', '.toc_checksums.yaml', 'specs_toc.yaml', 'reference', '/info/'])
    return True

# Pending YAML template
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


def is_target_dir(filepath):
    """Check if file is under target directory"""
    rel_path = str(filepath.relative_to(SPECS_DIR))
    parts = rel_path.split('/')
    # パスのどこかに target_dirs のディレクトリ名が含まれるかチェック
    # e.g., main/requirements/app.md → ['main', 'requirements', 'app.md']
    #       → 'requirements' in target_dir_names → True
    target_dir_names = TARGET_DIRS.values()
    return any(part in target_dir_names for part in parts)


def get_all_md_files():
    """Get list of target .md files"""
    md_files = []

    for filepath in SPECS_DIR.rglob("*.md"):
        if should_exclude(filepath, SPECS_DIR, EXCLUDE_PATTERNS):
            continue
        if not is_target_dir(filepath):
            continue
        md_files.append(filepath)

    md_files.sort()
    return md_files


def calculate_file_hash(filepath):
    """
    Calculate SHA256 hash of file

    Returns:
        str: Hash value, None on error
    """
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: File read error: {filepath} - {e}")
        return None


def load_checksums():
    """Load existing checksum file (standard library only)"""
    if not CHECKSUMS_FILE.exists():
        return {}

    checksums = {}
    try:
        with open(CHECKSUMS_FILE, "r", encoding="utf-8") as f:
            in_checksums = False
            for line in f:
                stripped = line.strip()
                if stripped == "checksums:":
                    in_checksums = True
                    continue
                if in_checksums and stripped and not stripped.startswith("#"):
                    match = re.match(r"^\s+(.+?):\s*([a-f0-9]+)\s*$", line)
                    if match:
                        filepath = match.group(1)
                        hash_val = match.group(2)
                        checksums[filepath] = hash_val
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Failed to read checksums file: {e}")
        return {}

    return checksums


def get_source_file_path(md_file):
    """Get project-relative path with SPECS_DIR prefix (e.g., 'specs/main/requirements/app.md')"""
    rel_path = str(md_file.relative_to(SPECS_DIR))
    return f"{SPECS_DIR_NAME}/{rel_path}"


def get_doc_type(source_file):
    """
    Determine doc_type from path using TARGET_DIRS

    Args:
        source_file: Project-relative path (e.g., 'specs/main/requirements/login.md')

    Returns:
        str: doc_type ('requirement', 'design', etc.) or None
    """
    parts = source_file.split('/')
    # Skip the first part (root directory like 'specs') to avoid false matches
    # when subdirectory name equals root directory name
    parts_without_root = parts[1:] if len(parts) > 1 else parts

    # Create reverse mapping: directory name → doc_type
    # e.g., {'requirements': 'requirement', 'design': 'design'}
    dir_to_doctype = {v: k for k, v in TARGET_DIRS.items()}

    for part in parts_without_root:
        if part in dir_to_doctype:
            return dir_to_doctype[part]
    return None


def path_to_yaml_filename(source_file):
    """Generate YAML filename from path (/ → _, .md → .yaml)"""
    return source_file.replace('/', '_').replace('.md', '.yaml')


def create_pending_yaml(source_file, doc_type):
    """
    Create pending YAML file

    Returns:
        Path: Created file path, None on error
    """
    yaml_name = path_to_yaml_filename(source_file)
    yaml_path = TOC_WORK_DIR / yaml_name

    try:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(PENDING_TEMPLATE.format(source_file=source_file, doc_type=doc_type))
        return yaml_path
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: File write error: {yaml_path} - {e}")
        return None


def main():
    # Initialize configuration
    if not init_config():
        return 1

    # Parse options
    full_mode = "--full" in sys.argv

    # Force full mode if specs_toc.yaml doesn't exist
    if not SPECS_TOC_FILE.exists():
        full_mode = True
        print("specs_toc.yaml not found, running in full mode")

    # Force full mode if checksums doesn't exist
    if not full_mode and not CHECKSUMS_FILE.exists():
        full_mode = True
        print(".toc_checksums.yaml not found, running in full mode")

    # Get target files
    all_files = get_all_md_files()

    if full_mode:
        # Full mode: process all files
        target_files = all_files
        deleted_files = []
        print(f"Full mode: processing {len(target_files)} files")
    else:
        # Incremental mode: changed files only
        old_checksums = load_checksums()
        current_files = {get_source_file_path(f): f for f in all_files}

        target_files = []

        # Detect new/changed files
        for source_file, full_path in current_files.items():
            current_hash = calculate_file_hash(full_path)
            if current_hash is None:
                continue  # Skip on hash calculation failure
            old_hash = old_checksums.get(source_file)

            if old_hash is None:
                print(f"  [New] {source_file}")
                target_files.append(full_path)
            elif current_hash != old_hash:
                print(f"  [Modified] {source_file}")
                target_files.append(full_path)

        # Detect deleted files
        deleted_files = [
            sf for sf in old_checksums.keys()
            if sf not in current_files
        ]
        for sf in deleted_files:
            print(f"  [Deleted] {sf}")

        if not target_files and not deleted_files:
            print("No changes - specs_toc.yaml is up to date")
            return 0

        if not target_files and deleted_files:
            print(f"\nDeleted files only: {len(deleted_files)} files")
            print("Use --delete-only with merge script")
            return 0

        print(f"\nIncremental mode: {len(target_files)} changes, {len(deleted_files)} deletions")

    # Create .toc_work directory
    TOC_WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Generate pending YAMLs
    created_files = []
    failed_count = 0
    for md_file in target_files:
        source_file = get_source_file_path(md_file)
        doc_type = get_doc_type(source_file)
        if doc_type is None:
            print(f"Warning: Cannot determine doc_type - {source_file}")
            continue
        yaml_path = create_pending_yaml(source_file, doc_type)
        if yaml_path is None:
            failed_count += 1
            continue
        created_files.append(source_file)

    if failed_count > 0:
        print(f"\nWarning: {failed_count} files failed to create")

    print(f"\nCreated {len(created_files)} pending YAMLs:")
    for sf in created_files:
        print(f"  - {sf}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
