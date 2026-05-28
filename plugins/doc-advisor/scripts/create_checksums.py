#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.toc_checksums.yaml 生成スクリプト（統合版）

rules/ または specs/ 配下の全 .md ファイルの SHA-256 ハッシュを計算し、
.toc_checksums.yaml に保存する。incremental モード判定に使用。

使用方法:
    python3 create_checksums.py --category rules
    python3 create_checksums.py --category specs
"""

import json
import sys
import argparse
from pathlib import Path

import shutil

from toc_utils import init_common_config, should_exclude, resolve_config_path, rglob_follow_symlinks, normalize_path, calculate_file_hash, write_checksums_yaml, ConfigNotReadyError, log

# Global configuration (initialized in init_config())
CATEGORY = None  # 'rules' or 'specs'
CONFIG = None
PROJECT_ROOT = None
ROOT_DIRS = None  # list of (root_dir_path, root_dir_name)
FIRST_DIR = None  # 最初の root_dir（パス解決用）
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
    parser.add_argument('--promote-pending', action='store_true',
                        help='Promote pending checksums to active checksums file')
    parser.add_argument('--clean-work-dir', action='store_true',
                        help='Clean up work directory')
    return parser.parse_args()


def init_config(category):
    """
    Initialize configuration.

    Args:
        category: 'rules' or 'specs'

    Returns:
        bool: True on success, False on failure
    """
    global CATEGORY, CONFIG, PROJECT_ROOT, ROOT_DIRS, FIRST_DIR, CHECKSUMS_FILE
    global PATTERNS_CONFIG, TARGET_GLOB, EXCLUDE_PATTERNS

    CATEGORY = category

    try:
        common = init_common_config(category)
    except ConfigNotReadyError as e:
        print(json.dumps({"status": "config_required", "message": str(e)}))
        return False
    except (RuntimeError, FileNotFoundError) as e:
        log(f"Error: {e}")
        return False

    CONFIG = common['config']
    PROJECT_ROOT = common['project_root']
    ROOT_DIRS = common['root_dirs']
    PATTERNS_CONFIG = common['patterns_config']
    TARGET_GLOB = common['target_glob']
    EXCLUDE_PATTERNS = common['exclude_patterns']

    FIRST_DIR = common['first_dir']
    CHECKSUMS_FILE = resolve_config_path(CONFIG.get('checksums_file', '.toc_checksums.yaml'),
                                          FIRST_DIR, PROJECT_ROOT)
    return True


def promote_pending():
    """pending checksums を active checksums ファイルに昇格する。

    toc_orchestrator Phase 3 で使用。
    {work_dir}/.toc_checksums_pending.yaml → {checksums_file} にコピーする。

    Returns:
        bool: True on success, False on failure
    """
    work_dir = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), FIRST_DIR, PROJECT_ROOT)
    pending = work_dir / '.toc_checksums_pending.yaml'
    if not pending.exists():
        log(f"Error: Pending checksums not found: {pending}")
        return False
    CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(pending), str(CHECKSUMS_FILE))
    log(f"Promoted: {pending} -> {CHECKSUMS_FILE}")
    return True


def clean_work_dir():
    """work directory を削除する。

    toc_orchestrator Phase 3 で使用。
    config の work_dir から解決したパスを削除する。

    Returns:
        bool: True on success (不在時もスキップして True)
    """
    work_dir = resolve_config_path(CONFIG.get('work_dir', '.toc_work'), FIRST_DIR, PROJECT_ROOT)
    if not work_dir.exists():
        log(f"Work directory not found (skip): {work_dir}")
        return True
    shutil.rmtree(str(work_dir))
    log(f"Cleaned: {work_dir}")
    return True


def find_md_files(root_dir, exclude_patterns, target_glob="**/*.md"):
    """指定ディレクトリ配下の全 .md ファイルを検索（シンボリックリンク対応）"""
    md_files = []
    for filepath in rglob_follow_symlinks(root_dir, target_glob):
        if not should_exclude(filepath, root_dir, exclude_patterns):
            md_files.append(filepath)
    return sorted(md_files)


def main():
    args = parse_args()

    # Initialize configuration
    if not init_config(args.category):
        return 1

    # --promote-pending: pending checksums を昇格
    if args.promote_pending:
        return 0 if promote_pending() else 1

    # --clean-work-dir: work directory を削除
    if args.clean_work_dir:
        return 0 if clean_work_dir() else 1

    log("=" * 50)
    log(f".toc_checksums.yaml 生成スクリプト（{CATEGORY}）")
    log("=" * 50)

    # Ensure output directory exists
    CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 対象ファイル検索（複数 root_dirs 対応）
    md_files = []
    root_dir_map = {}  # filepath → (root_dir, root_dir_name)
    for root_dir, root_dir_name in ROOT_DIRS:
        if not root_dir.exists():
            log(f"警告: {root_dir} が存在しません、スキップします")
            continue
        files = find_md_files(root_dir, EXCLUDE_PATTERNS, TARGET_GLOB)
        for f in files:
            root_dir_map[f] = (root_dir, root_dir_name)
        md_files.extend(files)

    md_files.sort()

    if not md_files:
        log(f"エラー: 対象ディレクトリに .md ファイルが見つかりません")
        return 1

    log(f"対象ファイル: {len(md_files)} 件")

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
        log(f"  ✓ {prefixed_path}")

    if skipped_count > 0:
        log(f"\n⚠️ {skipped_count}件のファイルをスキップしました")

    if not checksums:
        log("エラー: 有効なファイルがありません")
        return 1

    # 出力
    if not write_checksums_yaml(checksums, CHECKSUMS_FILE,
                                header_comment=f"{CATEGORY}_toc.yaml checksum file"):
        return 1

    log(f"\n✅ 生成完了: {CHECKSUMS_FILE}")
    log(f"   - ファイル数: {len(checksums)}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
