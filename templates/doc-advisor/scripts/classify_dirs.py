#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
Directory classification script for Doc Advisor.

Scans a project for markdown directories and classifies them as
rules or specs using front matter doc_type and term ranking.

Usage:
    python3 .claude/doc-advisor/scripts/classify_dirs.py
    python3 .claude/doc-advisor/scripts/classify_dirs.py --update
    python3 .claude/doc-advisor/scripts/classify_dirs.py --apply

Options:
    --update    Only process directories not already in config.yaml root_dirs
    --apply     Apply classification to config.yaml and print human-readable summary

Output: YAML classification result to stdout (default), or summary text (--apply)

Run from: Project root
"""

import sys
import re
import os
import argparse
from pathlib import Path

from toc_utils import get_project_root, load_config


# Directories to always skip
SKIP_DIRS = {
    '.git', '.claude', '.github', '.vscode', '.idea',
    'node_modules', '__pycache__', '.tox', '.mypy_cache',
    'venv', '.venv', 'env', '.env',
    'dist', 'build', 'target', 'out',
    '.next', '.nuxt', '.svelte-kit',
    'vendor', 'Pods', '.gradle',
}

# Files that indicate a directory is not a documentation directory
SKIP_INDICATORS = {'package.json', 'Cargo.toml', 'go.mod', 'pom.xml', 'setup.py', 'pyproject.toml'}

# Term indicators for classification
RULE_TERMS = [
    r'\bmust\b', r'\bshall\b', r'\bshould not\b', r'\bmust not\b',
    r'\bconvention\b', r'\bstandard\b', r'\bguideline\b',
    r'\bprohibited\b', r'\bnaming\b', r'\bworkflow\b',
    r'\brule\b', r'\bpolicy\b', r'\bdo not\b', r'\bforbidden\b',
    r'\bcompliance\b', r'\bbest practice\b',
]

SPEC_TERMS = [
    r'\brequirement\b', r'\bdesign\b', r'\bfeature\b',
    r'\bspecification\b', r'\barchitecture\b', r'\bcomponent\b',
    r'\buse case\b', r'\bacceptance criteria\b', r'\buser story\b',
    r'\bfunctional\b', r'\bnon-functional\b', r'\binterface\b',
    r'\bapi\b', r'\bschema\b', r'\bdata model\b',
    r'\bsequence\b', r'\bstate\b', r'\bplan\b',
]


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Classify project directories as rules or specs'
    )
    parser.add_argument('--update', action='store_true',
                        help='Only process directories not already in config.yaml')
    parser.add_argument('--apply', action='store_true',
                        help='Apply classification to config.yaml and print summary')
    return parser.parse_args()


def find_md_dirs(project_root):
    """
    Find directories containing .md files.

    Returns:
        list of (relative_dir_path, md_file_count)
    """
    results = []
    root = Path(project_root)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        current = Path(dirpath)
        rel = current.relative_to(root)
        rel_str = str(rel)

        # Skip hidden and system directories
        # Filter dirnames in-place to prevent descent
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith('.')
        ]

        # Skip root directory itself
        if rel_str == '.':
            continue

        # Skip if directory contains project indicators (source code dir)
        if any((current / ind).exists() for ind in SKIP_INDICATORS):
            continue

        # Count .md files in this directory (not recursive)
        md_files = [f for f in filenames if f.endswith('.md')]
        if md_files:
            results.append((rel_str, len(md_files)))

    return results


def extract_front_matter(filepath):
    """
    Extract front matter from a markdown file.

    Returns:
        dict or None: Front matter key-value pairs, None if no front matter
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(4096)  # Read only first 4KB for front matter
    except (IOError, OSError):
        return None

    if not content.startswith('---'):
        return None

    end = content.find('---', 3)
    if end == -1:
        return None

    fm_content = content[3:end]
    result = {}
    for line in fm_content.split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            key, _, val = line.partition(':')
            result[key.strip()] = val.strip().strip('"\'')

    return result


def classify_by_frontmatter(project_root, dir_path):
    """
    Classify directory by front matter doc_type.

    Returns:
        tuple: (category, confidence, reason) or None if not determinable
        category: 'rules' or 'specs'
        confidence: 'high' or 'medium'
    """
    root = Path(project_root)
    dir_full = root / dir_path

    md_files = list(dir_full.glob('*.md'))
    if not md_files:
        return None

    rules_count = 0
    specs_count = 0
    total_with_fm = 0

    for md_file in md_files:
        fm = extract_front_matter(md_file)
        if not fm or 'doc_type' not in fm:
            continue

        total_with_fm += 1
        doc_type = fm['doc_type'].lower()

        if doc_type in ('rule', 'rules', 'guideline', 'standard', 'workflow'):
            rules_count += 1
        elif doc_type in ('requirement', 'requirements', 'design', 'plan',
                          'specification', 'spec', 'specs'):
            specs_count += 1

    if total_with_fm == 0:
        return None

    total_classified = rules_count + specs_count
    if total_classified == 0:
        return None

    if rules_count > specs_count:
        confidence = 'high' if rules_count == total_with_fm else 'medium'
        return ('rules', confidence,
                f"frontmatter doc_type=rule ({rules_count}/{total_with_fm} files)")
    elif specs_count > rules_count:
        confidence = 'high' if specs_count == total_with_fm else 'medium'
        return ('specs', confidence,
                f"frontmatter doc_type=spec ({specs_count}/{total_with_fm} files)")
    else:
        return None  # Equal counts, ambiguous


def score_file_terms(filepath):
    """
    Score a file by rule/spec term frequency.

    Returns:
        tuple: (rule_score, spec_score)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().lower()
    except (IOError, OSError):
        return (0, 0)

    rule_score = 0
    for pattern in RULE_TERMS:
        rule_score += len(re.findall(pattern, content, re.IGNORECASE))

    spec_score = 0
    for pattern in SPEC_TERMS:
        spec_score += len(re.findall(pattern, content, re.IGNORECASE))

    return (rule_score, spec_score)


def classify_by_terms(project_root, dir_path):
    """
    Classify directory by term ranking (BM25-like approach).

    Returns:
        tuple: (category, confidence, reason) or None if ambiguous
    """
    root = Path(project_root)
    dir_full = root / dir_path

    md_files = list(dir_full.glob('*.md'))
    if not md_files:
        return None

    total_rule = 0
    total_spec = 0

    for md_file in md_files:
        r, s = score_file_terms(md_file)
        total_rule += r
        total_spec += s

    total = total_rule + total_spec
    if total == 0:
        return None

    # Require meaningful difference (at least 60/40 split)
    ratio = max(total_rule, total_spec) / total if total > 0 else 0

    if ratio < 0.6:
        return None  # Too ambiguous

    if total_rule > total_spec:
        confidence = 'high' if ratio >= 0.75 else 'medium'
        return ('rules', confidence,
                f"term_ranking: rule_score={total_rule}, spec_score={total_spec}")
    else:
        confidence = 'high' if ratio >= 0.75 else 'medium'
        return ('specs', confidence,
                f"term_ranking: rule_score={total_rule}, spec_score={total_spec}")


def classify_by_dirname(dir_path):
    """
    Classify directory by name heuristic (lowest priority).

    Returns:
        tuple: (category, confidence, reason) or None
    """
    name = Path(dir_path).name.lower()
    parts = set(Path(dir_path).parts)
    parts_lower = {p.lower() for p in parts}

    rule_names = {'rules', 'rule', 'guidelines', 'standards', 'policies', 'conventions'}
    spec_names = {'specs', 'spec', 'specifications', 'requirements', 'design',
                  'designs', 'plans', 'features', 'proposals'}

    if parts_lower & rule_names:
        return ('rules', 'medium', f"dirname match: {parts_lower & rule_names}")
    if parts_lower & spec_names:
        return ('specs', 'medium', f"dirname match: {parts_lower & spec_names}")

    return None


def classify_directory(project_root, dir_path):
    """
    Classify a single directory using multiple strategies.

    Priority:
    1. Front matter doc_type (highest)
    2. Term ranking
    3. Directory name heuristic (lowest)

    Returns:
        tuple: (category, confidence, reason) or None
    """
    # Strategy 1: Front matter
    result = classify_by_frontmatter(project_root, dir_path)
    if result:
        return result

    # Strategy 2: Term ranking
    result = classify_by_terms(project_root, dir_path)
    if result:
        return result

    # Strategy 3: Directory name
    result = classify_by_dirname(dir_path)
    if result:
        return result

    return None


def get_existing_root_dirs():
    """
    Get existing root_dirs from config.yaml.

    Returns:
        set: Set of normalized directory paths
    """
    try:
        config = load_config()
    except (FileNotFoundError, RuntimeError):
        return set()

    existing = set()
    for target in ('rules', 'specs'):
        section = config.get(target, {})
        root_dirs = section.get('root_dirs', [])
        if isinstance(root_dirs, str):
            root_dirs = [root_dirs]
        for d in root_dirs:
            existing.add(d.rstrip('/'))

    return existing


def aggregate_to_top_dirs(classified_dirs):
    """
    Aggregate subdirectory classifications to top-level directories.

    If rules/core/ and rules/workflow/ are both classified as 'rules',
    output rules/ instead of the individual subdirectories.

    Returns:
        dict: {category: [{dir, confidence, reason}]}
    """
    # Group by category and top-level directory
    top_level_groups = {}  # (category, top_dir) -> [results]

    for dir_path, category, confidence, reason in classified_dirs:
        parts = Path(dir_path).parts
        top_dir = parts[0] if parts else dir_path

        key = (category, top_dir)
        if key not in top_level_groups:
            top_level_groups[key] = []
        top_level_groups[key].append({
            'dir': dir_path,
            'confidence': confidence,
            'reason': reason,
        })

    # Decide whether to use top_dir or individual subdirs
    result = {'rules': [], 'specs': [], 'skip': [], 'mixed': []}

    # Track which top_dirs have been assigned
    top_dir_categories = {}  # top_dir -> set of categories

    for (category, top_dir), entries in top_level_groups.items():
        if top_dir not in top_dir_categories:
            top_dir_categories[top_dir] = set()
        top_dir_categories[top_dir].add(category)

    for top_dir, categories in top_dir_categories.items():
        if len(categories) == 1:
            # All subdirs agree on category
            category = next(iter(categories))
            entries = top_level_groups[(category, top_dir)]
            # Use top_dir if multiple subdirs, else use the single subdir
            if len(entries) > 1 or entries[0]['dir'] == top_dir:
                best_confidence = max(e['confidence'] for e in entries)
                reasons = [e['reason'] for e in entries]
                result[category].append({
                    'dir': f"{top_dir}/",
                    'confidence': best_confidence,
                    'reason': f"aggregated from {len(entries)} subdirs: {reasons[0]}",
                })
            else:
                e = entries[0]
                result[category].append({
                    'dir': f"{e['dir']}/",
                    'confidence': e['confidence'],
                    'reason': e['reason'],
                })
        else:
            # Mixed categories under same top_dir
            for category in categories:
                entries = top_level_groups[(category, top_dir)]
                for e in entries:
                    result[category].append({
                        'dir': f"{e['dir']}/",
                        'confidence': e['confidence'],
                        'reason': e['reason'],
                    })

    return result


def is_readme_only(project_root, dir_path):
    """Check if directory only contains README/CHANGELOG type files"""
    root = Path(project_root)
    dir_full = root / dir_path
    md_files = [f.name.lower() for f in dir_full.glob('*.md')]
    skip_names = {'readme.md', 'changelog.md', 'contributing.md', 'license.md',
                  'code_of_conduct.md', 'security.md'}
    return all(f in skip_names for f in md_files)


def output_yaml(classification):
    """Output classification result as YAML to stdout"""
    print("classification:")

    for category in ('rules', 'specs'):
        entries = classification.get(category, [])
        print(f"  {category}:")
        if not entries:
            print("    []")
        else:
            for entry in entries:
                print(f"    - dir: {entry['dir']}")
                print(f"      confidence: {entry['confidence']}")
                print(f"      reason: \"{entry['reason']}\"")

    for category in ('skip', 'mixed'):
        entries = classification.get(category, [])
        if entries:
            print(f"  {category}:")
            for entry in entries:
                print(f"    - dir: {entry['dir']}")
                print(f"      reason: \"{entry.get('reason', '')}\"")


def output_summary(classification):
    """Output human-readable classification summary"""
    has_output = False

    for category in ('rules', 'specs'):
        entries = classification.get(category, [])
        if entries:
            print(f"  {category}:")
            for e in entries:
                dir_str = e['dir'].ljust(25)
                print(f"    {dir_str} ({e['confidence']}: {e['reason']})")
            has_output = True

    skip_entries = classification.get('skip', [])
    if skip_entries:
        print(f"  skipped:")
        for e in skip_entries:
            dir_str = e['dir'].ljust(25)
            print(f"    {dir_str} ({e['reason']})")
        has_output = True

    mixed_entries = classification.get('mixed', [])
    if mixed_entries:
        print(f"  unclassified:")
        for e in mixed_entries:
            dir_str = e['dir'].ljust(25)
            print(f"    {dir_str} ({e.get('reason', '')})")
        has_output = True

    if not has_output:
        print("  No document directories detected.")


def format_root_dirs_yaml(dirs):
    """Format directory list as YAML root_dirs value"""
    if not dirs:
        return 'root_dirs: []'
    lines = ['root_dirs:']
    for d in dirs:
        lines.append(f'    - {d}')
    return '\n'.join(lines)


def apply_to_config(classification):
    """
    Update config.yaml root_dirs with classification results.

    Replaces 'root_dirs: []    # Auto-classified by /classify-docs' patterns
    in order: first occurrence for rules, second for specs.
    """
    config_path = Path(get_project_root()) / '.claude' / 'doc-advisor' / 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    rules_dirs = [e['dir'].rstrip('/') for e in classification.get('rules', [])]
    specs_dirs = [e['dir'].rstrip('/') for e in classification.get('specs', [])]

    marker = 'root_dirs: []    # Auto-classified by /classify-docs'

    # First replacement: rules section
    content = content.replace(marker, format_root_dirs_yaml(rules_dirs), 1)
    # Second replacement: specs section
    content = content.replace(marker, format_root_dirs_yaml(specs_dirs), 1)

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    args = parse_args()

    try:
        project_root = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Get existing root_dirs if --update mode
    existing_dirs = get_existing_root_dirs() if args.update else set()

    # Find directories with .md files
    md_dirs = find_md_dirs(project_root)

    if not md_dirs:
        if args.apply:
            print("  No document directories detected.")
        else:
            print("No markdown directories found.", file=sys.stderr)
            print("classification:")
            print("  rules: []")
            print("  specs: []")
        return 0

    # Classify each directory
    classified = []
    skip_entries = []

    for dir_path, md_count in md_dirs:
        # Skip if already in config (--update mode)
        normalized = dir_path.rstrip('/')
        if normalized in existing_dirs:
            continue

        # Skip README-only directories
        if is_readme_only(project_root, dir_path):
            skip_entries.append({
                'dir': f"{dir_path}/",
                'reason': 'README/CHANGELOG only',
            })
            continue

        result = classify_directory(project_root, dir_path)
        if result:
            category, confidence, reason = result
            classified.append((dir_path, category, confidence, reason))
        else:
            skip_entries.append({
                'dir': f"{dir_path}/",
                'reason': f'unclassifiable ({md_count} md files)',
            })

    # Aggregate subdirectories to top-level
    classification = aggregate_to_top_dirs(classified)
    classification['skip'] = skip_entries

    # Output
    if args.apply:
        output_summary(classification)
        apply_to_config(classification)
        rules_count = len(classification.get('rules', []))
        specs_count = len(classification.get('specs', []))
        if rules_count + specs_count > 0:
            print(f"\n  config.yaml updated: rules={rules_count} dir(s), specs={specs_count} dir(s)")
    else:
        output_yaml(classification)

    return 0


if __name__ == '__main__':
    sys.exit(main())
