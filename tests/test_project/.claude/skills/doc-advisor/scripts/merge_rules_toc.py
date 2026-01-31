#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rules_toc.yaml Merge Script (standard library only)

Reads all entries from .claude/doc-advisor/rules/.toc_work/*.yaml,
removes _meta sections, merges them, and generates .claude/doc-advisor/rules/rules_toc.yaml.

Usage:
    python3 merge_rules_toc.py [--cleanup] [--mode full|incremental]

Options:
    --cleanup   Delete .toc_work/ after successful merge
    --mode      full (default): Generate new, incremental: Differential merge
"""

import sys
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
    get_system_exclude_patterns,
)

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
RULES_DIR = None
RULES_DIR_NAME = None
TOC_WORK_DIR = None
OUTPUT_FILE = None
CHECKSUMS_FILE = None
OUTPUT_CONFIG = None
PATTERNS_CONFIG = None
EXCLUDE_PATTERNS = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, RULES_DIR, RULES_DIR_NAME, TOC_WORK_DIR, OUTPUT_FILE
    global CHECKSUMS_FILE, OUTPUT_CONFIG, PATTERNS_CONFIG, EXCLUDE_PATTERNS

    try:
        CONFIG = load_config('rules')
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    RULES_DIR_NAME = CONFIG.get('root_dir', 'rules').rstrip('/')
    RULES_DIR = PROJECT_ROOT / RULES_DIR_NAME
    TOC_WORK_DIR = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), RULES_DIR, PROJECT_ROOT)
    OUTPUT_FILE = resolve_config_path(CONFIG.get('toc_file', 'rules_toc.yaml'), RULES_DIR, PROJECT_ROOT)
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'), RULES_DIR, PROJECT_ROOT)
    OUTPUT_CONFIG = CONFIG.get('output', {})
    PATTERNS_CONFIG = CONFIG.get('patterns', {})
    # System patterns (always excluded) + user-defined patterns
    EXCLUDE_PATTERNS = get_system_exclude_patterns('rules') + PATTERNS_CONFIG.get('exclude', [])
    return True


def load_existing_toc(toc_path):
    """Load existing rules_toc.yaml"""
    if not toc_path.exists():
        return {}

    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Failed to read {toc_path}: {e}")
        return {}

    docs = {}
    current_file = None
    current_entry = {}
    current_list = None
    in_docs = False

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            continue

        if stripped == 'docs:':
            in_docs = True
            continue

        if not in_docs:
            continue

        # Detect file path (2-space indent ending with :)
        if line.startswith('  ') and not line.startswith('    ') and stripped.endswith(':'):
            if current_file and current_entry:
                docs[current_file] = current_entry
            current_file = stripped.rstrip(':')
            current_entry = {}
            current_list = None
        elif line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
            if current_file:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip().strip('"\'')
                if val:
                    current_entry[key] = val
                else:
                    current_list = []
                    current_entry[key] = current_list
        elif stripped.startswith('- ') and current_list is not None:
            item = stripped[2:].strip().strip('"\'')
            current_list.append(item)

    if current_file and current_entry:
        docs[current_file] = current_entry

    return docs


def get_existing_files():
    """Get list of currently existing files with RULES_DIR prefix"""
    files = set()
    target_glob = PATTERNS_CONFIG.get('target_glob', '**/*.md')
    for filepath in RULES_DIR.glob(target_glob):
        if should_exclude(filepath, RULES_DIR, EXCLUDE_PATTERNS):
            continue
        rel_path = str(filepath.relative_to(RULES_DIR))
        # Include RULES_DIR prefix for project-relative path
        prefixed_path = f"{RULES_DIR_NAME}/{rel_path}"
        files.add(prefixed_path)
    return files


def write_yaml_output(docs, output_path):
    """
    Write YAML file

    Returns:
        bool: True on success, False on failure
    """
    lines = []

    # File header comment
    header_comment = OUTPUT_CONFIG.get('header_comment', 'Development Document Search Index for rules-advisor Subagent')
    metadata_name = OUTPUT_CONFIG.get('metadata_name', 'Development Document Search Index')

    lines.append("# .claude/doc-advisor/rules/rules_toc.yaml")
    lines.append(f"# {header_comment}")
    lines.append("")

    lines.append("metadata:")
    lines.append(f"  name: {metadata_name}")
    lines.append(f"  generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"  file_count: {len(docs)}")
    lines.append("")

    lines.append("docs:")
    for source_file, entry in sorted(docs.items()):
        lines.append(f"  {source_file}:")

        for key in ['title', 'purpose']:
            if key in entry:
                lines.append(f"    {key}: {yaml_escape(entry[key])}")

        for key in ['content_details', 'applicable_tasks', 'keywords']:
            if key in entry and entry[key]:
                lines.append(f"    {key}:")
                for item in entry[key]:
                    lines.append(f"      - {yaml_escape(item)}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"Error: Failed to write file: {output_path} - {e}")
        return False


def delete_only_mode():
    """Delete-only mode: Apply deletions without .toc_work/"""
    print("Mode: delete-only")

    if not OUTPUT_FILE.exists():
        print("Error: rules_toc.yaml does not exist")
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

            if not source_file:
                errors.append(f"{filename}: Cannot get source_file")
                continue

            if status != 'completed':
                errors.append(f"{filename}: Status is not completed ({status})")
                continue

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
    print(f"   - File count: {len(docs)}")

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
    print("rules_toc.yaml Merge Script")
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
