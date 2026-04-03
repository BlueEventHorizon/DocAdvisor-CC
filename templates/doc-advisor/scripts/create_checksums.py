#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
.toc_checksums.yaml 生成スクリプト（統合版）

rules/ または specs/ 配下の全 .md ファイルの SHA-256 ハッシュを計算し、
.toc_checksums.yaml に保存する。incremental モード判定に使用。

使用方法:
    python3 create_checksums.py --category rules
    python3 create_checksums.py --category specs
"""

import sys
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import json

from toc_utils import (
    ConfigNotReadyError,
    get_project_root,
    init_common_config,
    load_config,
    should_exclude,
    resolve_config_path,
    get_system_exclude_patterns,
    rglob_follow_symlinks,
    normalize_path,
    expand_root_dir_globs,
)

# Global configuration (initialized in init_config())
CATEGORY = None  # 'rules' or 'specs'
CONFIG = None
PROJECT_ROOT = None
ROOT_DIRS = None  # list of (root_dir_path, root_dir_name)
CHECKSUMS_FILE = None
PATTERNS_CONFIG = None
TARGET_GLOB = None
EXCLUDE_PATTERNS = None


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Generate .toc_checksums.yaml for incremental mode detection'
    )
    parser.add_argument('--category', required=True, choices=['rules', 'specs'],
                        help='Document category: rules or specs')
    return parser.parse_args()


def init_config(category):
    """
    Initialize configuration.

    Args:
        category: 'rules' or 'specs'

    Returns:
        bool: True on success, False on failure
    """
    global CATEGORY, CONFIG, PROJECT_ROOT, ROOT_DIRS, CHECKSUMS_FILE
    global PATTERNS_CONFIG, TARGET_GLOB, EXCLUDE_PATTERNS

    CATEGORY = category

    try:
        common = init_common_config(category)
    except ConfigNotReadyError as e:
        print(json.dumps({"status": "config_required", "message": str(e)}))
        return False
    except RuntimeError as e:
        print(f"Error: {e}")
        return False

    CONFIG = common['config']
    PROJECT_ROOT = common['project_root']
    ROOT_DIRS = common['root_dirs']
    first_dir = common['first_dir']
    PATTERNS_CONFIG = common['patterns_config']
    TARGET_GLOB = common['target_glob']
    EXCLUDE_PATTERNS = common['exclude_patterns']

    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'),
                                          first_dir, PROJECT_ROOT)
    return True


def calculate_file_hash(filepath):
    """
    ファイルの SHA-256 ハッシュを計算

    Returns:
        str: ハッシュ値、エラー時はNone
    """
    try:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError, PermissionError) as e:
        print(f"⚠️ ファイル読み込みエラー: {filepath} - {e}")
        return None


def find_md_files(root_dir, exclude_patterns, target_glob="**/*.md"):
    """指定ディレクトリ配下の全 .md ファイルを検索（シンボリックリンク対応）"""
    md_files = []
    for filepath in rglob_follow_symlinks(root_dir, target_glob):
        if not should_exclude(filepath, root_dir, exclude_patterns):
            md_files.append(filepath)
    return sorted(md_files)


def write_checksums_yaml(checksums, output_path, category):
    """
    チェックサムをYAML形式で出力

    Returns:
        bool: 成功時True、失敗時False
    """
    lines = [
        f"# {category}_toc.yaml 用チェックサムファイル",
        "# 自動生成 - 手動編集禁止",
        f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"file_count: {len(checksums)}",
        "checksums:",
    ]

    for rel_path, hash_value in sorted(checksums.items()):
        lines.append(f"  {rel_path}: {hash_value}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"エラー: ファイル書き込み失敗: {output_path} - {e}")
        return False


def main():
    args = parse_args()

    # Initialize configuration
    if not init_config(args.category):
        return 1

    print("=" * 50)
    print(f".toc_checksums.yaml 生成スクリプト（{CATEGORY}）")
    print("=" * 50)

    # Ensure output directory exists
    CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 対象ファイル検索（複数 root_dirs 対応）
    md_files = []
    root_dir_map = {}  # filepath → (root_dir, root_dir_name)
    for root_dir, root_dir_name in ROOT_DIRS:
        if not root_dir.exists():
            print(f"警告: {root_dir} が存在しません、スキップします")
            continue
        files = find_md_files(root_dir, EXCLUDE_PATTERNS, TARGET_GLOB)
        for f in files:
            root_dir_map[f] = (root_dir, root_dir_name)
        md_files.extend(files)

    md_files.sort()

    if not md_files:
        print(f"エラー: 対象ディレクトリに .md ファイルが見つかりません")
        return 1

    print(f"対象ファイル: {len(md_files)} 件")

    # ハッシュ計算
    checksums = {}
    skipped_count = 0
    for filepath in md_files:
        root_dir, root_dir_name = root_dir_map[filepath]
        rel_path = normalize_path(filepath.relative_to(root_dir))
        # Include root_dir prefix for project-relative path (e.g., "rules/core/..." or "specs/requirements/...")
        prefixed_path = f"{root_dir_name}/{rel_path}"
        hash_value = calculate_file_hash(filepath)
        if hash_value is None:
            skipped_count += 1
            continue
        checksums[prefixed_path] = hash_value
        print(f"  ✓ {prefixed_path}")

    if skipped_count > 0:
        print(f"\n⚠️ {skipped_count}件のファイルをスキップしました")

    if not checksums:
        print("エラー: 有効なファイルがありません")
        return 1

    # 出力
    if not write_checksums_yaml(checksums, CHECKSUMS_FILE, CATEGORY):
        return 1

    print(f"\n✅ 生成完了: {CHECKSUMS_FILE}")
    print(f"   - ファイル数: {len(checksums)}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
