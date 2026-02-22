#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
Set root_dirs and exclude patterns in Doc Advisor config.yaml.

Writes the specified directories and exclude patterns to config.yaml.
Replaces marker comments for initial setup, or
can be used standalone to set directories manually.

Usage:
    python3 .claude/doc-advisor/scripts/set_root_dirs.py --rules "rules,guidelines" --specs "specs"
    python3 .claude/doc-advisor/scripts/set_root_dirs.py --rules "rules" --specs "specs" --exclude-rules "archive" --exclude-specs "draft"

Run from: Project root
Created by: k_terada
"""

import sys
import argparse
from pathlib import Path

from toc_utils import get_project_root


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Set root_dirs and exclude patterns in Doc Advisor config.yaml'
    )
    parser.add_argument('--rules', type=str, default='',
                        help='Comma-separated rules directories')
    parser.add_argument('--specs', type=str, default='',
                        help='Comma-separated specs directories')
    parser.add_argument('--exclude-rules', type=str, default='',
                        help='Comma-separated exclude patterns for rules')
    parser.add_argument('--exclude-specs', type=str, default='',
                        help='Comma-separated exclude patterns for specs')
    return parser.parse_args()


def format_root_dirs_yaml(dirs):
    """Format directory list as YAML root_dirs value"""
    if not dirs:
        return 'root_dirs: []'
    lines = ['root_dirs:']
    for d in dirs:
        lines.append(f'    - {d}')
    return '\n'.join(lines)


def format_excludes_yaml(patterns):
    """Format exclude list as YAML value"""
    if not patterns:
        return 'exclude:'
    lines = ['exclude:']
    for p in patterns:
        lines.append(f'      - {p}')
    return '\n'.join(lines)


def set_root_dirs(rules_str, specs_str, exclude_rules_str='', exclude_specs_str=''):
    """
    Write root_dirs and exclude patterns to config.yaml.

    Replaces marker comments in order:
    - 'root_dirs: []    # Auto-classified by /classify-docs' (1st=rules, 2nd=specs)
    - 'exclude: []    # Set during setup' (1st=rules, 2nd=specs)
    """
    rules_dirs = [d.strip() for d in rules_str.split(',') if d.strip()]
    specs_dirs = [d.strip() for d in specs_str.split(',') if d.strip()]
    exclude_rules = [p.strip() for p in exclude_rules_str.split(',') if p.strip()]
    exclude_specs = [p.strip() for p in exclude_specs_str.split(',') if p.strip()]

    config_path = Path(get_project_root()) / '.claude' / 'doc-advisor' / 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace root_dirs markers
    root_marker = 'root_dirs: []    # Auto-classified by /classify-docs'
    content = content.replace(root_marker, format_root_dirs_yaml(rules_dirs), 1)
    content = content.replace(root_marker, format_root_dirs_yaml(specs_dirs), 1)

    # Replace exclude markers
    exclude_marker = 'exclude: []    # Set during setup'
    content = content.replace(exclude_marker, format_excludes_yaml(exclude_rules), 1)
    content = content.replace(exclude_marker, format_excludes_yaml(exclude_specs), 1)

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)

    parts = [f"rules={len(rules_dirs)} dir(s)", f"specs={len(specs_dirs)} dir(s)"]
    if exclude_rules:
        parts.append(f"rules_exclude={len(exclude_rules)}")
    if exclude_specs:
        parts.append(f"specs_exclude={len(exclude_specs)}")
    print(f"  config.yaml updated: {', '.join(parts)}")


def main():
    args = parse_args()

    try:
        get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    set_root_dirs(args.rules, args.specs, args.exclude_rules, args.exclude_specs)
    return 0


if __name__ == '__main__':
    sys.exit(main())
