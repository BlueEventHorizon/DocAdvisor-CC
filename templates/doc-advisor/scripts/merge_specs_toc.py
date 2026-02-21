#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
specs_toc.yaml Merge Script (standard library only)

Reads all entries from .claude/doc-advisor/toc/specs/.toc_work/*.yaml,
removes _meta sections, merges them, and generates .claude/doc-advisor/toc/specs/specs_toc.yaml.

Usage:
    python3 merge_specs_toc.py [--mode full|incremental]

Options:
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
    should_exclude,
    resolve_config_path,
    get_system_exclude_patterns,
    rglob_follow_symlinks,
    normalize_path,
)

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
SPECS_ROOT_DIRS = None  # list of (root_dir_path, root_dir_name)
TOC_WORK_DIR = None
OUTPUT_FILE = None
CHECKSUMS_FILE = None
OUTPUT_CONFIG = None
PATTERNS_CONFIG = None
TARGET_GLOB = None
EXCLUDE_PATTERNS = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, SPECS_ROOT_DIRS, TOC_WORK_DIR, OUTPUT_FILE
    global CHECKSUMS_FILE, OUTPUT_CONFIG, PATTERNS_CONFIG, TARGET_GLOB, EXCLUDE_PATTERNS

    try:
        CONFIG = load_config('specs')
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    root_dirs_config = CONFIG.get('root_dirs', ['specs/'])
    if isinstance(root_dirs_config, str):
        root_dirs_config = [root_dirs_config]
    SPECS_ROOT_DIRS = []
    for entry in root_dirs_config:
        name = entry.rstrip('/')
        SPECS_ROOT_DIRS.append((PROJECT_ROOT / name, name))

    first_specs_dir = SPECS_ROOT_DIRS[0][0] if SPECS_ROOT_DIRS else PROJECT_ROOT / 'specs'
    TOC_WORK_DIR = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), first_specs_dir, PROJECT_ROOT)
    OUTPUT_FILE = resolve_config_path(CONFIG.get('toc_file', 'specs_toc.yaml'), first_specs_dir, PROJECT_ROOT)
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'), first_specs_dir, PROJECT_ROOT)
    OUTPUT_CONFIG = CONFIG.get('output', {})
    PATTERNS_CONFIG = CONFIG.get('patterns', {})
    TARGET_GLOB = PATTERNS_CONFIG.get('target_glob', '**/*.md')
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
    header_comment = OUTPUT_CONFIG.get('header_comment', 'Project Specification Document Search Index for specs-advisor Subagent')
    metadata_name = OUTPUT_CONFIG.get('metadata_name', 'Project Specification Document Search Index')

    lines.append("# .claude/doc-advisor/toc/specs/specs_toc.yaml")
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
        for key in ['title', 'purpose']:
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
        # references フィールド（空配列許容）
        if 'references' in entry:
            if entry['references']:
                lines.append("    references:")
                for ref in entry['references']:
                    lines.append(f"      - {yaml_escape(ref)}")
            else:
                lines.append("    references: []")

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
            # Unicode-safe: 2-space indent (not 4-space) and .md: suffix
            if line.startswith('  ') and not line.startswith('    ') and stripped.endswith('.md:'):
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
                    if val == '[]':
                        # Inline empty array (e.g., "references: []")
                        current_list = []
                        current_list_key = key
                        current_entry[key] = current_list
                    elif val:
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


def get_existing_files():
    """Get list of currently existing files across all root_dirs (symlink-aware)"""
    files = set()
    for root_dir, root_dir_name in SPECS_ROOT_DIRS:
        if not root_dir.exists():
            continue
        for filepath in rglob_follow_symlinks(root_dir, TARGET_GLOB):
            if should_exclude(filepath, root_dir, EXCLUDE_PATTERNS):
                continue
            rel_path = normalize_path(filepath.relative_to(root_dir))
            prefixed_path = f"{root_dir_name}/{rel_path}"
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

    deleted_count = 0
    for del_file in deleted_files:
        if del_file in docs:
            del docs[del_file]
            print(f"  Deleted: {del_file}")
            deleted_count += 1

    # Also delete stale entries in ToC but not in current valid files
    stale_entries = [p for p in docs if p not in existing_files]
    for stale in stale_entries:
        del docs[stale]
        print(f"  Deleted (stale): {stale}")
        deleted_count += 1

    if deleted_count == 0:
        print("No entries to delete")
        return True

    if not write_yaml_output(docs, OUTPUT_FILE):
        return False

    print(f"\nDeletion complete: {deleted_count} entries deleted")
    return True


def merge_toc_files(mode='full'):
    yaml_files = sorted(f for f in TOC_WORK_DIR.glob("*.yaml") if not f.name.startswith('.'))

    if not yaml_files:
        print(f"Error: No YAML files found in {TOC_WORK_DIR}")
        return False

    print(f"Target files: {len(yaml_files)}")
    print(f"Mode: {mode}")

    # Create backup (common to all modes)
    backup_existing_file(OUTPUT_FILE)

    # Get current valid files (exclude/target_dir applied)
    existing_files = get_existing_files()

    # In incremental mode, load existing data
    if mode == 'incremental':
        docs = load_existing_toc(OUTPUT_FILE)
        # Delete entries that exist in checksums but file doesn't exist
        checksum_files = load_checksums(CHECKSUMS_FILE)
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

            # Skip excluded or non-target files
            if source_file not in existing_files:
                errors.append(f"{filename}: Skipped (excluded or missing: {source_file})")
                continue

            # Add to docs (key is file path)
            docs[source_file] = entry
            print(f"  {source_file}")

        except Exception as e:
            errors.append(f"{filename}: {e}")

    # Remove stale entries not in current valid files
    if mode == 'incremental':
        stale_entries = [p for p in docs if p not in existing_files]
        for stale in stale_entries:
            del docs[stale]
            print(f"  Deleted (stale): {stale}")

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

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
