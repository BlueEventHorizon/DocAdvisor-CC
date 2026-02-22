#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
Set root_dirs in Doc Advisor config.yaml.

Writes the specified directories to config.yaml root_dirs fields.
Replaces the auto-classification marker for initial setup, or
can be used standalone to set directories manually.

Usage:
    python3 .claude/doc-advisor/scripts/set_root_dirs.py --rules "rules,guidelines" --specs "specs"
    python3 .claude/doc-advisor/scripts/set_root_dirs.py --rules "" --specs ""

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
        description='Set root_dirs in Doc Advisor config.yaml'
    )
    parser.add_argument('--rules', type=str, default='',
                        help='Comma-separated rules directories')
    parser.add_argument('--specs', type=str, default='',
                        help='Comma-separated specs directories')
    return parser.parse_args()


def format_root_dirs_yaml(dirs):
    """Format directory list as YAML root_dirs value"""
    if not dirs:
        return 'root_dirs: []'
    lines = ['root_dirs:']
    for d in dirs:
        lines.append(f'    - {d}')
    return '\n'.join(lines)


def set_root_dirs(rules_str, specs_str):
    """
    Write root_dirs to config.yaml.

    Replaces 'root_dirs: []    # Auto-classified by /classify-docs' markers
    in order: first occurrence for rules, second for specs.
    """
    rules_dirs = [d.strip() for d in rules_str.split(',') if d.strip()]
    specs_dirs = [d.strip() for d in specs_str.split(',') if d.strip()]

    config_path = Path(get_project_root()) / '.claude' / 'doc-advisor' / 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    marker = 'root_dirs: []    # Auto-classified by /classify-docs'

    # First replacement: rules section
    content = content.replace(marker, format_root_dirs_yaml(rules_dirs), 1)
    # Second replacement: specs section
    content = content.replace(marker, format_root_dirs_yaml(specs_dirs), 1)

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  config.yaml updated: rules={len(rules_dirs)} dir(s), specs={len(specs_dirs)} dir(s)")


def main():
    args = parse_args()

    try:
        get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    set_root_dirs(args.rules, args.specs)
    return 0


if __name__ == '__main__':
    sys.exit(main())
