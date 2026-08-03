#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pending YAML write script (doc-advisor plugin / key + path I/F)

DES-005 §7.1（doc_type 除去）/ §4.1（モジュール）を実装する。

toc-updater agent の分析結果を pending YAML（store_dir/.toc_work/ 配下）に
書き込み、status を completed に更新する。doc_type は扱わない。

充填するフィールド: title / purpose / content_details / applicable_tasks / keywords
（DES-005 §7.1: doc_type なし）。

Usage:
    python3 write_pending.py --key K \
      --entry-file ".claude/.doc-advisor/toc/<slug>/.toc_work/xxx.yaml" \
      --title "Title" \
      --purpose "Purpose" \
      --content-details "item1 ||| item2 ||| item3 ||| item4 ||| item5" \
      --applicable-tasks "task1 ||| task2" \
      --keywords "kw1 ||| kw2 ||| kw3 ||| kw4 ||| kw5"

    # 単体モード（予約 key all）: --all または --key 省略
    python3 write_pending.py --all --entry-file "..." --title ... (他フィールド)

Error mode:
    python3 write_pending.py --key K \
      --entry-file "..." \
      --error --error-message "Source file not found"

Exit codes:
    0: Success
    1: File not found / path traversal / key error
    2: Missing required field
    3: Array element count insufficient
    4: Write failure
"""

import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import (
    yaml_escape,
    load_entry_file,
    get_project_root,
    validate_path_within_base,
    log,
)
from toc_store import (
    KeyError_,
    resolve_key_from_args,
)


# Validation settings
MIN_CONTENT_DETAILS = 5
MIN_APPLICABLE_TASKS = 1
MIN_KEYWORDS = 5

# _meta.extracted_by の値域（DES-008 §8.2）。本 script は toc-updater Agent 経由の
# AI 抽出経路であり、常に 'ai' を書く（転記経路の 'frontmatter' は
# frontmatter/fm_to_pending.py が書く）。CLI 引数では受け取らない。
EXTRACTED_BY_AI = 'ai'


def parse_args(argv=None):
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Write analysis results to pending YAML (key + path I/F)'
    )
    # key 解決（--all / --key 省略 → 予約 key all、--key all → reject）
    parser.add_argument('--key', help='User-specified key (opaque)')
    parser.add_argument('--all', action='store_true',
                        help="Single mode: resolve to reserved key 'all'")
    parser.add_argument('--entry-file', required=True,
                        help='Target entry YAML file path (store_dir/.toc_work/ 配下)')

    # Error mode
    parser.add_argument('--error', action='store_true',
                        help='Write error status (skip field validation)')
    parser.add_argument('--error-message', default='',
                        help='Error message (used with --error)')

    # Content fields (required in normal mode, ignored in error mode)
    parser.add_argument('--title', default=None,
                        help='Document title')
    parser.add_argument('--purpose', default=None,
                        help='Document purpose (1-2 sentences)')
    parser.add_argument('--content-details', default=None,
                        help='Content details (||| separated, 5-10 items)')
    parser.add_argument('--applicable-tasks', default=None,
                        help='Applicable tasks (||| separated, 1+ items)')
    parser.add_argument('--keywords', default=None,
                        help='Keywords (||| separated, 5-10)')
    parser.add_argument('--force', action='store_true',
                        help='Force overwrite even if completed')

    return parser.parse_args(argv)


def parse_separated(value, separator='|||'):
    """Convert separator-delimited string to array (default: ||| separator)"""
    if not value:
        return []
    items = [item.strip() for item in value.split(separator)]
    return [item for item in items if item]  # Remove empty strings


def validate_array(name, items, min_count):
    """Validate array element count"""
    if len(items) < min_count:
        log(f"Error: {name} requires at least {min_count} items (got {len(items)})")
        log(f"  Provided: {', '.join(items)}")
        return False
    return True


def write_error_yaml(filepath, meta, error_message):
    """
    Write error status to entry YAML file (DES-005 §7.1: doc_type なし)

    extracted_by は書かない。DES-008 §8.2 の来歴は「AI 抽出結果の書き戻し候補」を
    識別するためのものであり、充填に失敗した error pending は候補にならない。

    Args:
        filepath: Output file path
        meta: _meta section dict (source_file preserved)
        error_message: Error description

    Returns:
        bool: True on success
    """
    lines = []

    # _meta section (doc_type なし)
    lines.append("_meta:")
    lines.append(f"  source_file: {yaml_escape(meta.get('source_file', ''))}")
    lines.append("  status: pending")
    lines.append(f"  error_message: {yaml_escape(error_message)}")
    lines.append(f"  updated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")

    # Null fields (preserve template structure)
    lines.append("title: null")
    lines.append("purpose: null")
    lines.append("content_details: []")
    lines.append("applicable_tasks: []")
    lines.append("keywords: []")

    lines.append("")  # Trailing newline

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to write file: {filepath} - {e}")
        return False


def write_entry_yaml(filepath, meta, entry):
    """
    Write entry YAML file (DES-005 §7.1: doc_type なし)

    extracted_by は列挙値であり yaml_escape を適用しない（status と同じ扱い）。
    転記経路（frontmatter/fm_to_pending.py）と本 script で値が異なるため、
    値は meta 経由で受け取る（CLI 引数では受け取らない）。

    Args:
        filepath: Output file path
        meta: _meta section dict (source_file / status / updated_at / extracted_by)
        entry: Entry data dict

    Returns:
        bool: True on success
    """
    lines = []

    # _meta section (doc_type なし)
    lines.append("_meta:")
    lines.append(f"  source_file: {yaml_escape(meta.get('source_file', ''))}")
    lines.append(f"  status: {meta.get('status', 'completed')}")
    lines.append(f"  updated_at: {meta.get('updated_at', '')}")
    lines.append(f"  extracted_by: {meta.get('extracted_by', EXTRACTED_BY_AI)}")
    lines.append("")

    # Scalar fields
    lines.append(f"title: {yaml_escape(entry.get('title', ''))}")
    lines.append(f"purpose: {yaml_escape(entry.get('purpose', ''))}")

    # Array fields
    for field in ['content_details', 'applicable_tasks', 'keywords']:
        lines.append(f"{field}:")
        items = entry.get(field, [])
        for item in items:
            lines.append(f"  - {yaml_escape(item)}")

    lines.append("")  # Trailing newline

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to write file: {filepath} - {e}")
        return False


def main(argv=None):
    args = parse_args(argv)

    # key 解決（--all / --key 省略 → 予約 all、--key all → KEY_RESERVED）
    # write_pending は store_dir を直接受け取らず entry-file を受けるが、
    # key の妥当性検証（空 / 任意 all reject）は他 script と統一する。
    try:
        resolve_key_from_args(args)
    except KeyError_ as e:
        log(f"Error: {e}")
        return 1

    entry_file = Path(args.entry_file)

    # Path traversal check (CWE-22)
    project_root = get_project_root()
    try:
        entry_file = validate_path_within_base(entry_file, project_root)
    except ValueError:
        log(f"Error: Path traversal detected: {args.entry_file}")
        return 1

    # File existence check
    if not entry_file.exists():
        log(f"Error: Entry file not found: {entry_file}")
        return 1

    # Load existing file
    try:
        meta, _ = load_entry_file(entry_file)
    except IOError as e:
        log(f"Error: {e}")
        return 1

    # _meta section check
    if not meta:
        log(f"Error: Entry file missing _meta section: {entry_file}")
        return 1

    # source_file check
    if 'source_file' not in meta:
        log(f"Error: Entry file missing _meta.source_file: {entry_file}")
        return 1

    # Error mode: write error status and exit
    if args.error:
        if not args.error_message:
            log("Error: --error-message is required with --error")
            return 2
        if not write_error_yaml(entry_file, meta, args.error_message):
            return 4
        log(f"Entry error: {entry_file}")
        log(f"  source_file: {meta['source_file']}")
        log(f"  status: pending (error_message set)")
        log(f"  error_message: {args.error_message}")
        return 0

    # completed status check
    if meta.get('status') == 'completed' and not args.force:
        log(f"Error: Entry file already completed: {entry_file}")
        log("  Use --force to overwrite")
        return 1

    # Required fields check (normal mode)
    missing = []
    for field in ['title', 'purpose', 'content_details', 'applicable_tasks', 'keywords']:
        if getattr(args, field.replace('-', '_')) is None:
            missing.append(f'--{field.replace("_", "-")}')
    if missing:
        log(f"Error: Required arguments in normal mode: {', '.join(missing)}")
        return 2

    # Parse arrays
    content_details = parse_separated(args.content_details)
    applicable_tasks = parse_separated(args.applicable_tasks)
    keywords = parse_separated(args.keywords)
    # Validation
    valid = True
    if not validate_array('content_details', content_details, MIN_CONTENT_DETAILS):
        valid = False
    if not validate_array('applicable_tasks', applicable_tasks, MIN_APPLICABLE_TASKS):
        valid = False
    if not validate_array('keywords', keywords, MIN_KEYWORDS):
        valid = False

    if not valid:
        return 3

    # Update _meta (doc_type なし / DES-005 §7.1)
    # extracted_by は AI 抽出由来を表す（DES-008 §8.2）
    updated_meta = {
        'source_file': meta['source_file'],
        'status': 'completed',
        'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'extracted_by': EXTRACTED_BY_AI
    }

    # Entry data
    entry = {
        'title': args.title,
        'purpose': args.purpose,
        'content_details': content_details,
        'applicable_tasks': applicable_tasks,
        'keywords': keywords
    }
    # Write
    if not write_entry_yaml(entry_file, updated_meta, entry):
        return 4

    # Success message
    log(f"Entry completed: {entry_file}")
    log(f"  source_file: {updated_meta['source_file']}")
    log(f"  status: {updated_meta['status']}")
    log(f"  updated_at: {updated_meta['updated_at']}")
    log(f"  extracted_by: {updated_meta['extracted_by']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
