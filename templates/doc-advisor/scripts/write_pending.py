#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
pending YAML write script (unified for rules/specs)

Writes analysis results from subagent to pending YAML,
changing status to completed.

Usage:
    python3 write_pending.py --target rules \
      --entry-file ".claude/doc-advisor/toc/rules/.toc_work/xxx.yaml" \
      --title "Title" \
      --purpose "Purpose" \
      --content-details "item1 ||| item2 ||| item3 ||| item4 ||| item5" \
      --applicable-tasks "task1 ||| task2" \
      --keywords "kw1 ||| kw2 ||| kw3 ||| kw4 ||| kw5"

    python3 write_pending.py --target specs \
      --entry-file ".claude/doc-advisor/toc/specs/.toc_work/xxx.yaml" \
      ... \
      --references "ref1 ||| ref2"

Exit codes:
    0: Success
    1: File not found
    2: Missing required field
    3: Array element count insufficient
    4: Write failure
"""

import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import yaml_escape, load_entry_file


# Validation settings
MIN_CONTENT_DETAILS = 5
MIN_APPLICABLE_TASKS = 1
MIN_KEYWORDS = 5


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Write analysis results to pending YAML'
    )
    parser.add_argument('--target', required=True, choices=['rules', 'specs'],
                        help='Target category: rules or specs')
    parser.add_argument('--entry-file', required=True,
                        help='Target entry YAML file path')
    parser.add_argument('--title', required=True,
                        help='Document title')
    parser.add_argument('--purpose', required=True,
                        help='Document purpose (1-2 sentences)')
    parser.add_argument('--content-details', required=True,
                        help='Content details (||| separated, 5-10 items)')
    parser.add_argument('--applicable-tasks', required=True,
                        help='Applicable tasks (||| separated, 1+ items)')
    parser.add_argument('--keywords', required=True,
                        help='Keywords (||| separated, 5-10)')
    parser.add_argument('--references', default='',
                        help='Reference documents (||| separated, specs only)')
    parser.add_argument('--force', action='store_true',
                        help='Force overwrite even if completed')

    return parser.parse_args()


def parse_separated(value, separator='|||'):
    """Convert separator-delimited string to array (default: ||| separator)"""
    if not value:
        return []
    items = [item.strip() for item in value.split(separator)]
    return [item for item in items if item]  # Remove empty strings


def validate_array(name, items, min_count):
    """Validate array element count"""
    if len(items) < min_count:
        print(f"Error: {name} requires at least {min_count} items (got {len(items)})")
        print(f"  Provided: {', '.join(items)}")
        return False
    return True


def write_entry_yaml(filepath, meta, entry, target):
    """
    Write entry YAML file

    Args:
        filepath: Output file path
        meta: _meta section dict
        entry: Entry data dict
        target: 'rules' or 'specs'

    Returns:
        bool: True on success
    """
    lines = []

    # _meta section
    lines.append("_meta:")
    lines.append(f"  source_file: {meta.get('source_file', '')}")
    lines.append(f"  status: {meta.get('status', 'completed')}")
    lines.append(f"  updated_at: {meta.get('updated_at', '')}")
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

    # references field (specs only)
    if target == 'specs':
        references = entry.get('references', [])
        if references:
            lines.append("references:")
            for item in references:
                lines.append(f"  - {yaml_escape(item)}")
        else:
            lines.append("references: []")

    lines.append("")  # Trailing newline

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"Error: Failed to write file: {filepath} - {e}")
        return False


def main():
    args = parse_args()

    target = args.target
    entry_file = Path(args.entry_file)

    # File existence check
    if not entry_file.exists():
        print(f"Error: Entry file not found: {entry_file}")
        return 1

    # Load existing file
    try:
        meta, _ = load_entry_file(entry_file)
    except IOError as e:
        print(f"Error: {e}")
        return 1

    # _meta section check
    if not meta:
        print(f"Error: Entry file missing _meta section: {entry_file}")
        return 1

    # source_file check
    if 'source_file' not in meta:
        print(f"Error: Entry file missing _meta.source_file: {entry_file}")
        return 1

    # completed status check
    if meta.get('status') == 'completed' and not args.force:
        print(f"Error: Entry file already completed: {entry_file}")
        print("  Use --force to overwrite")
        return 1

    # Parse arrays
    content_details = parse_separated(args.content_details)
    applicable_tasks = parse_separated(args.applicable_tasks)
    keywords = parse_separated(args.keywords)
    references = parse_separated(args.references) if target == 'specs' else []

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

    # Update _meta
    updated_meta = {
        'source_file': meta['source_file'],
        'status': 'completed',
        'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    }

    # Entry data
    entry = {
        'title': args.title,
        'purpose': args.purpose,
        'content_details': content_details,
        'applicable_tasks': applicable_tasks,
        'keywords': keywords
    }
    if target == 'specs':
        entry['references'] = references

    # Write
    if not write_entry_yaml(entry_file, updated_meta, entry, target):
        return 4

    # Success message
    print(f"Entry completed: {entry_file}")
    print(f"  source_file: {updated_meta['source_file']}")
    print(f"  status: {updated_meta['status']}")
    print(f"  updated_at: {updated_meta['updated_at']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
