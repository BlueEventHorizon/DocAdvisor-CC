#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specs_toc.yaml Merge Script (standard library only)

Reads all entries from .claude/doc-advisor/specs/.toc_work/*.yaml,
removes _meta sections, merges them, and generates .claude/doc-advisor/specs/specs_toc.yaml.

Usage:
    python3 merge_specs_toc.py [--cleanup] [--mode full|incremental]

Options:
    --cleanup   Delete .toc_work/ after successful merge
    --mode      full (default): Generate new, incremental: Differential merge
"""

import sys
import re
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import (
    get_project_root,
    load_config,
    load_entry_file,
    yaml_escape,
    backup_existing_file,
    load_checksums,
    cleanup_work_dir,
    should_exclude,
    resolve_config_path,
    get_default_target_dirs,
    get_system_exclude_patterns,
)

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
SPECS_DIR = None
SPECS_DIR_NAME = None
TOC_WORK_DIR = None
OUTPUT_FILE = None
CHECKSUMS_FILE = None
OUTPUT_CONFIG = None
PATTERNS_CONFIG = None
TARGET_DIRS = None
EXCLUDE_PATTERNS = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, SPECS_DIR, SPECS_DIR_NAME, TOC_WORK_DIR, OUTPUT_FILE
    global CHECKSUMS_FILE, OUTPUT_CONFIG, PATTERNS_CONFIG, TARGET_DIRS, EXCLUDE_PATTERNS

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
    OUTPUT_FILE = resolve_config_path(CONFIG.get('toc_file', 'specs_toc.yaml'), SPECS_DIR, PROJECT_ROOT)
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'), SPECS_DIR, PROJECT_ROOT)
    OUTPUT_CONFIG = CONFIG.get('output', {})
    PATTERNS_CONFIG = CONFIG.get('patterns', {})
    # target_dirs はマッピング形式: {doc_type: dir_name}
    TARGET_DIRS = PATTERNS_CONFIG.get('target_dirs', get_default_target_dirs())
    # System patterns (always excluded) + user-defined patterns
    EXCLUDE_PATTERNS = get_system_exclude_patterns('specs') + PATTERNS_CONFIG.get('exclude', [])
    return True


def write_yaml_output(docs, output_path):
    """
    Write YAML file

    Returns:
        bool: True on success, False on failure
    """
    lines = []

    # File header comment
    header_comment = OUTPUT_CONFIG.get('header_comment', 'Requirement & Design Document Search Index for specs-advisor Subagent')
    metadata_name = OUTPUT_CONFIG.get('metadata_name', 'Requirement & Design Document Search Index')

    lines.append("# .claude/doc-advisor/specs/specs_toc.yaml")
    lines.append(f"# {header_comment}")
    lines.append("")

    lines.append("metadata:")
    lines.append(f"  name: {metadata_name}")
    lines.append(f"  generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"  file_count: {len(docs)}")
    lines.append("")

    # docs section
    lines.append("docs:")
    for file_path, entry in sorted(docs.items()):
        lines.append(f"  {file_path}:")
        for key in ['doc_type', 'title', 'purpose']:
            if key in entry:
                lines.append(f"    {key}: {yaml_escape(entry[key])}")
        if 'content_details' in entry and entry['content_details']:
            lines.append("    content_details:")
            for item in entry['content_details']:
                lines.append(f"      - {yaml_escape(item)}")
        if 'applicable_tasks' in entry and entry['applicable_tasks']:
            lines.append("    applicable_tasks:")
            for task in entry['applicable_tasks']:
                lines.append(f"      - {yaml_escape(task)}")
        if 'keywords' in entry and entry['keywords']:
            lines.append("    keywords:")
            for kw in entry['keywords']:
                lines.append(f"      - {yaml_escape(kw)}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"Error: Failed to write file: {output_path} - {e}")
        return False


def load_existing_toc(toc_path):
    """Load existing specs_toc.yaml"""
    if not toc_path.exists():
        return {}

    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Failed to read {toc_path}: {e}")
        return {}

    docs = {}
    current_section = None
    current_path = None
    current_entry = {}
    current_list = None
    current_list_key = None

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            continue

        if stripped == 'docs:':
            current_section = 'docs'
            continue
        elif stripped.startswith('metadata:'):
            current_section = 'metadata'
            continue

        if current_section == 'docs':
            # Detect file path as key (e.g., main/requirements/app.md:)
            if re.match(r'^[a-zA-Z0-9_/.-]+\.md:$', stripped):
                if current_path and current_entry:
                    docs[current_path] = current_entry
                current_path = stripped.rstrip(':')
                current_entry = {}
                current_list = None
                current_list_key = None
            elif line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
                if current_path:
                    key, _, val = stripped.partition(':')
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    if val:
                        current_entry[key] = val
                    else:
                        current_list = []
                        current_list_key = key
                        current_entry[key] = current_list
            elif stripped.startswith('- ') and current_list is not None:
                item = stripped[2:].strip().strip('"\'')
                current_list.append(item)

    if current_path and current_entry:
        docs[current_path] = current_entry

    return docs


def is_target_dir(filepath):
    """Check if file is under target directory"""
    rel_path = str(filepath.relative_to(SPECS_DIR))
    parts = rel_path.split('/')
    # パスのどこかに target_dirs のディレクトリ名が含まれるかチェック
    # e.g., main/requirements/app.md → ['main', 'requirements', 'app.md']
    #       → 'requirements' in target_dir_names → True
    target_dir_names = TARGET_DIRS.values()
    return any(part in target_dir_names for part in parts)


def get_existing_files():
    """Get list of currently existing files with SPECS_DIR prefix"""
    files = set()
    for filepath in SPECS_DIR.rglob("*.md"):
        if should_exclude(filepath, SPECS_DIR, EXCLUDE_PATTERNS):
            continue
        if not is_target_dir(filepath):
            continue
        rel_path = str(filepath.relative_to(SPECS_DIR))
        # Include SPECS_DIR prefix for project-relative path
        prefixed_path = f"{SPECS_DIR_NAME}/{rel_path}"
        files.add(prefixed_path)
    return files


def delete_only_mode():
    """Delete-only mode: Apply deletions without .toc_work/"""
    print("Mode: delete-only")

    if not OUTPUT_FILE.exists():
        print("Error: specs_toc.yaml does not exist")
        return False

    # Create backup
    backup_existing_file(OUTPUT_FILE)

    # Load existing data
    docs = load_existing_toc(OUTPUT_FILE)

    # Delete entries that exist in checksums but file doesn't exist
    checksum_files = load_checksums(CHECKSUMS_FILE)
    existing_files = get_existing_files()
    deleted_files = checksum_files - existing_files

    if not deleted_files:
        print("No files to delete")
        return True

    deleted_count = 0
    for del_file in deleted_files:
        if del_file in docs:
            del docs[del_file]
            print(f"  Deleted: {del_file}")
            deleted_count += 1

    if deleted_count == 0:
        print("No entries to delete")
        return True

    if not write_yaml_output(docs, OUTPUT_FILE):
        return False

    print(f"\nDeletion complete: {deleted_count} entries deleted")
    return True


def merge_toc_files(mode='full'):
    yaml_files = sorted(TOC_WORK_DIR.glob("*.yaml"))

    if not yaml_files:
        print(f"Error: No YAML files found in {TOC_WORK_DIR}")
        return False

    print(f"Target files: {len(yaml_files)}")
    print(f"Mode: {mode}")

    # Create backup (common to all modes)
    backup_existing_file(OUTPUT_FILE)

    # In incremental mode, load existing data
    if mode == 'incremental':
        docs = load_existing_toc(OUTPUT_FILE)
        # Delete entries that exist in checksums but file doesn't exist
        checksum_files = load_checksums(CHECKSUMS_FILE)
        existing_files = get_existing_files()
        deleted_files = checksum_files - existing_files
        for del_file in deleted_files:
            if del_file in docs:
                del docs[del_file]
                print(f"  Deleted: {del_file}")
    else:
        docs = {}

    errors = []

    for filepath in yaml_files:
        filename = filepath.name
        try:
            meta, entry = load_entry_file(filepath)
            source_file = meta.get('source_file')
            status = meta.get('status')
            doc_type = meta.get('doc_type')

            if not source_file:
                errors.append(f"{filename}: Cannot get source_file")
                continue

            if status != 'completed':
                errors.append(f"{filename}: Status is not completed ({status})")
                continue

            # Add doc_type to entry
            entry['doc_type'] = doc_type

            # Add to docs (key is file path)
            docs[source_file] = entry
            print(f"  {source_file}")

        except Exception as e:
            errors.append(f"{filename}: {e}")

    if errors:
        print("\nWarnings:")
        for err in errors:
            print(f"  - {err}")

    if not docs:
        print("Error: No valid entries")
        return False

    if not write_yaml_output(docs, OUTPUT_FILE):
        return False

    print(f"\nGeneration complete: {OUTPUT_FILE}")
    print(f"   - docs: {len(docs)}")

    return True


def main():
    # Initialize configuration
    if not init_config():
        return 1

    cleanup = '--cleanup' in sys.argv
    delete_only = '--delete-only' in sys.argv
    mode = 'full'
    if '--mode' in sys.argv:
        idx = sys.argv.index('--mode')
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]

    print("=" * 50)
    print("specs_toc.yaml Merge Script")
    print("=" * 50)

    if delete_only:
        success = delete_only_mode()
    else:
        success = merge_toc_files(mode)

    if success and cleanup:
        cleanup_work_dir(TOC_WORK_DIR)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
