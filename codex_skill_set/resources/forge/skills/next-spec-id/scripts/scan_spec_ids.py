#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全ブランチ（ローカル + リモート）から指定プレフィックスの仕様書 ID をスキャンし、
次の連番 ID を JSON で返す。

.doc_structure.yaml から specs の root_dirs を取得してスキャン対象パスを
動的に決定する。.doc_structure.yaml が存在しない場合は specs/ をフォールバックとして使用。

使用例:
    PYTHONDONTWRITEBYTECODE=1 python3 scan_spec_ids.py SCR
    PYTHONDONTWRITEBYTECODE=1 python3 scan_spec_ids.py DES
    PYTHONDONTWRITEBYTECODE=1 python3 scan_spec_ids.py --project-root /path/to/project TASK
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# resolve_doc_structure.py を import
_SCRIPT_DIR = Path(__file__).resolve().parent
_DOC_STRUCTURE_SCRIPTS = _SCRIPT_DIR.parent.parent / 'doc-structure' / 'scripts'
sys.path.insert(0, str(_DOC_STRUCTURE_SCRIPTS))

from resolve_doc_structure import (
    find_project_root,
    load_doc_structure,
    parse_config,
)

FALLBACK_SPECS_DIRS = ['specs/']


def _run_git(*args, cwd=None):
    """git コマンドを実行して stdout を返す。失敗時は空文字列。"""
    try:
        result = subprocess.run(
            ['git'] + list(args),
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ''


def get_specs_root_dirs(project_root, doc_structure_path=None):
    """specs の root_dirs を取得する。glob パターンのまま返す。"""
    try:
        config, _ = load_doc_structure(project_root, doc_structure_path)
        specs = config.get('specs', {})
        root_dirs = specs.get('root_dirs', [])
        if root_dirs:
            return [d.rstrip('/') + '/' for d in root_dirs]
    except (FileNotFoundError, Exception):
        pass
    return FALLBACK_SPECS_DIRS


def _normalize_glob_to_prefix(pattern):
    """glob パターンを git ls-tree 用のプレフィックスに変換する。

    'docs/specs/**/design/' → 'docs/specs/'
    'docs/specs/*/requirements/' → 'docs/specs/'
    'specs/' → 'specs/'
    """
    parts = pattern.rstrip('/').split('/')
    prefix_parts = []
    for part in parts:
        if '*' in part or '?' in part:
            break
        prefix_parts.append(part)
    if prefix_parts:
        return '/'.join(prefix_parts) + '/'
    return ''


def detect_base_branch(cwd=None):
    """ベースブランチ（develop or main）を特定する。"""
    for ref in [
        'refs/heads/develop',
        'refs/remotes/origin/develop',
        'refs/heads/main',
        'refs/remotes/origin/main',
    ]:
        result = _run_git('show-ref', '--verify', '--quiet', ref, cwd=cwd)
        # show-ref --quiet は見つかれば exit 0
        try:
            proc = subprocess.run(
                ['git', 'show-ref', '--verify', '--quiet', ref],
                capture_output=True,
                cwd=cwd,
                timeout=10,
            )
            if proc.returncode == 0:
                if ref.startswith('refs/remotes/'):
                    return ref.split('refs/remotes/')[-1]
                return ref.split('refs/heads/')[-1]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return 'main'


def get_scan_branches(base_branch, cwd=None):
    """ベースブランチから派生した全ブランチを取得する。"""
    output = _run_git(
        'for-each-ref', '--format=%(refname:short)',
        'refs/heads/', 'refs/remotes/origin/',
        cwd=cwd,
    )
    if not output:
        return [base_branch]

    all_branches = [
        b for b in output.split('\n')
        if b and 'HEAD' not in b
    ]
    all_branches = sorted(set(all_branches))

    scan = []
    for branch in all_branches:
        if branch == base_branch:
            scan.append(branch)
            continue
        try:
            proc = subprocess.run(
                ['git', 'merge-base', '--is-ancestor', base_branch, branch],
                capture_output=True,
                cwd=cwd,
                timeout=10,
            )
            if proc.returncode == 0:
                scan.append(branch)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return scan if scan else [base_branch]


def scan_ids_in_branch(branch, prefix, scan_dirs, cwd=None):
    """1つのブランチから指定プレフィックスの ID を抽出する。

    Returns:
        list[tuple[str, str]]: (id_string, branch_name) のリスト
    """
    pattern = re.compile(re.escape(prefix) + r'-(\d+)')
    results = []

    unique_prefixes = sorted(set(
        _normalize_glob_to_prefix(d) for d in scan_dirs
    ))
    unique_prefixes = [p for p in unique_prefixes if p]
    if not unique_prefixes:
        unique_prefixes = ['specs/']

    for dir_prefix in unique_prefixes:
        output = _run_git(
            'ls-tree', '-r', '--name-only', branch, '--', dir_prefix,
            cwd=cwd,
        )
        if not output:
            continue

        for filepath in output.split('\n'):
            if not filepath:
                continue
            match = pattern.search(filepath)
            if match:
                id_str = '{}-{}'.format(prefix, match.group(1))
                results.append((id_str, branch))

    return results


def find_duplicates(id_branch_pairs):
    """異なるブランチで同じ ID が使用されているケースを検出する。"""
    id_to_branches = {}
    for id_str, branch in id_branch_pairs:
        if id_str not in id_to_branches:
            id_to_branches[id_str] = set()
        id_to_branches[id_str].add(branch)

    duplicates = []
    for id_str, branches in sorted(id_to_branches.items()):
        if len(branches) > 1:
            duplicates.append({
                'id': id_str,
                'branches': sorted(branches),
            })
    return duplicates


def scan_spec_ids(prefix, project_root, doc_structure_path=None, cwd=None):
    """メインロジック: 全ブランチスキャンで次の ID を返す。"""
    if cwd is None:
        cwd = project_root

    scan_dirs = get_specs_root_dirs(project_root, doc_structure_path)

    # リモートをフェッチ
    _run_git('fetch', '--quiet', cwd=cwd)

    base_branch = detect_base_branch(cwd=cwd)
    branches = get_scan_branches(base_branch, cwd=cwd)

    all_pairs = []
    for branch in branches:
        pairs = scan_ids_in_branch(branch, prefix, scan_dirs, cwd=cwd)
        all_pairs.extend(pairs)

    # 最大番号を算出
    number_pattern = re.compile(re.escape(prefix) + r'-(\d+)')
    max_number = 0
    unique_ids = set()

    for id_str, _ in all_pairs:
        unique_ids.add(id_str)
        m = number_pattern.match(id_str)
        if m:
            num = int(m.group(1))
            if num > max_number:
                max_number = num

    next_number = max_number + 1
    next_id = '{}-{:03d}'.format(prefix, next_number)

    duplicates = find_duplicates(all_pairs)

    return {
        'status': 'ok',
        'next_id': next_id,
        'prefix': prefix,
        'max_number': max_number,
        'base_branch': base_branch,
        'branches_scanned': len(branches),
        'ids_found': len(unique_ids),
        'duplicates': duplicates,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description='全ブランチスキャンで仕様書 ID の次の連番を取得する'
    )
    parser.add_argument(
        'prefix',
        help='ID プレフィックス（例: SCR, DES, TASK）',
    )
    parser.add_argument(
        '--project-root',
        default=None,
        help='プロジェクトルートのパス（省略時: cwd）',
    )
    parser.add_argument(
        '--doc-structure',
        default=None,
        help='.doc_structure.yaml のパス（省略時: project_root/.doc_structure.yaml）',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    project_root = args.project_root
    if project_root:
        project_root = os.path.abspath(project_root)
    else:
        project_root = find_project_root()

    doc_structure_path = args.doc_structure
    if doc_structure_path:
        doc_structure_path = os.path.abspath(doc_structure_path)

    try:
        result = scan_spec_ids(
            args.prefix,
            project_root,
            doc_structure_path,
        )
    except Exception as e:
        result = {
            'status': 'error',
            'message': str(e),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
