#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.toc_checksums.yaml 生成スクリプト（統合版）

rules/ または specs/ 配下の全 .md ファイルの SHA-256 ハッシュを計算し、
.toc_checksums.yaml に保存する。incremental モード判定に使用。

使用方法:
    python3 create_checksums.py --target rules
    python3 create_checksums.py --target specs
"""

import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import get_project_root, load_config, should_exclude, resolve_config_path


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


def find_md_files_rules(root_dir, exclude_patterns):
    """rules/ 配下の全 .md ファイルを検索"""
    md_files = []
    for filepath in root_dir.rglob("*.md"):
        if not should_exclude(filepath, root_dir, exclude_patterns):
            md_files.append(filepath)
    return sorted(md_files)


def find_md_files_specs(root_dir, exclude_patterns, target_dir_names):
    """specs/ 配下の対象ディレクトリの .md ファイルを検索"""
    md_files = []
    for filepath in root_dir.rglob("*.md"):
        if should_exclude(filepath, root_dir, exclude_patterns):
            continue
        # パスのどこかに target_dirs のディレクトリ名が含まれるかチェック
        # e.g., main/requirements/app.md → ['main', 'requirements', 'app.md']
        #       → 'requirements' in target_dir_names → True
        rel_path = str(filepath.relative_to(root_dir))
        parts = rel_path.split('/')
        if any(part in target_dir_names for part in parts):
            md_files.append(filepath)
    return sorted(md_files)


def write_checksums_yaml(checksums, output_path, target):
    """
    チェックサムをYAML形式で出力

    Returns:
        bool: 成功時True、失敗時False
    """
    lines = [
        f"# {target}_toc.yaml 用チェックサムファイル",
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
    # オプション解析
    if '--target' not in sys.argv:
        print("エラー: --target オプションが必要です（rules または specs）")
        print("使用方法: python3 create_checksums.py --target rules")
        print("         python3 create_checksums.py --target specs")
        return 1

    idx = sys.argv.index('--target')
    if idx + 1 >= len(sys.argv):
        print("エラー: --target の値が指定されていません")
        return 1

    target = sys.argv[idx + 1]
    if target not in ('rules', 'specs'):
        print(f"エラー: --target は 'rules' または 'specs' を指定してください（指定: {target}）")
        return 1

    print("=" * 50)
    print(f".toc_checksums.yaml 生成スクリプト（{target}）")
    print("=" * 50)

    # 設定読み込み
    config = load_config(target)
    try:
        project_root = get_project_root()
    except RuntimeError as e:
        print(f"エラー: {e}")
        return 1

    root_dir_name = config.get('root_dir', f'{target}').rstrip('/')
    root_dir = project_root / root_dir_name
    output_file = resolve_config_path(config.get('checksums_file', '.toc_checksums.yaml'), root_dir, project_root)
    patterns_config = config.get('patterns', {})
    exclude_patterns = patterns_config.get('exclude', [])

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if not root_dir.exists():
        print(f"エラー: {root_dir} が存在しません")
        return 1

    # 対象ファイル検索
    if target == 'rules':
        md_files = find_md_files_rules(root_dir, exclude_patterns)
    else:
        # target_dirs はマッピング形式: {doc_type: dir_name}
        # e.g., {'requirement': 'requirements', 'design': 'design'}
        target_dirs_map = patterns_config.get('target_dirs', {'requirement': 'requirements', 'design': 'design'})
        target_dir_names = list(target_dirs_map.values())  # ['requirements', 'design']
        md_files = find_md_files_specs(root_dir, exclude_patterns, target_dir_names)

    if not md_files:
        print(f"エラー: {root_dir} に .md ファイルが見つかりません")
        return 1

    print(f"対象ファイル: {len(md_files)} 件")

    # ハッシュ計算
    checksums = {}
    skipped_count = 0
    for filepath in md_files:
        rel_path = str(filepath.relative_to(root_dir))
        # Include root_dir prefix for project-relative path (e.g., "rules/core/..." or "specs/main/...")
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
    if not write_checksums_yaml(checksums, output_file, target):
        return 1

    print(f"\n✅ 生成完了: {output_file}")
    print(f"   - ファイル数: {len(checksums)}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
