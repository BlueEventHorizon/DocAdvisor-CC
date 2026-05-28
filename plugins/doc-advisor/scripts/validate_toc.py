#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC 検査スクリプト（rules / specs 共通）

生成された {category}_toc.yaml の整合性を検査する。

使用方法:
    python3 validate_toc.py --category rules|specs [--file PATH]

オプション:
    --category  検査対象カテゴリ（rules または specs）
    --file      検査対象ファイル（デフォルト: .claude/doc-advisor/toc/{category}/{category}_toc.yaml）

検査項目:
    1. ファイル読み込み検査
    2. 必須フィールド検査
    3. ファイル参照検査
    4. 重複パス検査
"""

import sys
import argparse
from pathlib import Path

from toc_utils import get_project_root, load_config, resolve_config_path, validate_path_within_base, expand_root_dir_globs, load_existing_toc, log

# Global configuration (initialized in init_config())
CATEGORY = None  # 'rules' or 'specs'
CONFIG = None
PROJECT_ROOT = None
CATEGORY_DIR = None
DEFAULT_TOC_FILE = None


def init_config(category):
    """
    Initialize configuration for the given category.

    Args:
        category: 'rules' or 'specs'

    Returns:
        bool: True on success, False on failure
    """
    global CATEGORY, CONFIG, PROJECT_ROOT, CATEGORY_DIR, DEFAULT_TOC_FILE

    CATEGORY = category

    try:
        CONFIG = load_config(category)
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        log(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        log(f"Error: {e}")
        return False

    root_dirs_config = CONFIG.get('root_dirs', [f'{category}/'])
    if isinstance(root_dirs_config, str):
        root_dirs_config = [root_dirs_config]
    # Expand glob patterns in root_dirs (e.g., "specs/*/requirements/")
    root_dirs_config = expand_root_dir_globs(root_dirs_config, PROJECT_ROOT)
    # root_dirs_config が空の場合は PROJECT_ROOT / category をフォールバックとして使用する
    CATEGORY_DIR = (
        PROJECT_ROOT / root_dirs_config[0].rstrip('/')
        if root_dirs_config
        else PROJECT_ROOT / category
    )
    DEFAULT_TOC_FILE = resolve_config_path(
        CONFIG.get('toc_file', f'{category}_toc.yaml'), CATEGORY_DIR, PROJECT_ROOT
    )
    return True


def validate_toc(toc_path, *, category=None, project_root=None):
    """
    生成された toc ファイルを検査する
    - YAML構文検査
    - 必須フィールド検査
    - ファイル参照検査
    - 重複パス検査

    Args:
        toc_path: 検査対象の ToC ファイルパス
        category: カテゴリ名（省略時はグローバル変数 CATEGORY にフォールバック）
        project_root: プロジェクトルートパス（省略時はグローバル変数 PROJECT_ROOT にフォールバック）
    """
    _category = category if category is not None else CATEGORY
    _project_root = project_root if project_root is not None else PROJECT_ROOT

    if _project_root is None:
        print("Error: project_root が未設定です。init_config() を先に実行するか、project_root パラメータを指定してください。", file=sys.stderr)
        return False

    log("=" * 50)
    log(f"{_category}_toc.yaml 検査")
    log("=" * 50)
    log(f"対象: {toc_path}")
    log()

    errors = []

    # 1. ファイル読み込み検査（ファイルが読み込めるか）
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            f.read()
        log("✓ ファイル読み込み検査: OK（ファイル読み込み成功）")
    except (FileNotFoundError, IOError, OSError, PermissionError, UnicodeDecodeError) as e:
        errors.append(f"ファイル読み込み検査: ファイル読み込み失敗 - {e}")
        log(f"\n❌ 検査失敗: {len(errors)} 件のエラー")
        for err in errors:
            log(f"  - {err}")
        return False

    # パース
    docs = load_existing_toc(toc_path)

    # docs キー存在検査（壊れた YAML で空 dict が返された場合のガード）
    if not docs or not isinstance(docs, dict):
        errors.append("docs セクションが見つからないか、エントリが空です")
        log("✗ docs セクション検査: docs が見つからないか空です")
        log(f"\n❌ 検査失敗: {len(errors)} 件のエラー")
        for err in errors:
            log(f"  - {err}")
        return False
    else:
        log("✓ docs セクション検査: OK")

    # 2. 必須フィールド検査
    # title/purpose/doc_type が必須（文字列）
    # content_details/applicable_tasks/keywords が必須（非空配列）
    # フォーマット定義: No null, No empty arrays ({CATEGORY}_toc_format.md)
    required_string_fields = ['title', 'purpose', 'doc_type']
    required_array_fields = ['content_details', 'applicable_tasks', 'keywords']
    field_errors = []

    for file_path, entry in docs.items():
        for field in required_string_fields:
            if not entry.get(field):
                field_errors.append(f"必須フィールド欠落: {file_path} に '{field}' がありません")
        for field in required_array_fields:
            value = entry.get(field)
            if not isinstance(value, list) or len(value) == 0:
                field_errors.append(
                    f"必須配列フィールド不正: {file_path} の '{field}' が未設定または空配列です"
                )

    if not field_errors:
        log(f"✓ 必須フィールド検査: OK（{len(docs)}件のエントリ）")
    else:
        log(f"✗ 必須フィールド検査: {len(field_errors)}件のエラー")
        errors.extend(field_errors)

    # 3. ファイル参照検査
    # キーはプロジェクトルートからの相対パス（例: {category}/core/doc.md）
    file_errors = []
    for file_path in docs.keys():
        try:
            full_path = validate_path_within_base(file_path, _project_root)
        except ValueError:
            file_errors.append(f"不正なパス: '{file_path}' はプロジェクト外を参照しています")
            continue
        if not full_path.exists():
            file_errors.append(f"ファイル不在: '{file_path}' が存在しません")

    if not file_errors:
        log(f"✓ ファイル参照検査: OK（全ファイルが存在）")
    else:
        log(f"✗ ファイル参照検査: {len(file_errors)}件のエラー")
        errors.extend(file_errors)

    # 結果サマリー
    log()
    if errors:
        log(f"❌ 検査失敗: {len(errors)} 件のエラー")
        log("-" * 40)
        for err in errors:
            log(f"  - {err}")
        return False
    else:
        log(f"✅ 検査完了: 全チェックOK")
        return True


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Validate generated ToC YAML file'
    )
    parser.add_argument('--category', required=True, choices=['rules', 'specs'],
                        help='検査対象カテゴリ: rules or specs')
    parser.add_argument('--file', default=None,
                        help='検査対象ファイルパス（デフォルト: 設定から自動解決）')
    return parser.parse_args()


def main():
    args = parse_args()

    # Initialize configuration
    if not init_config(args.category):
        return 1

    # --file オプションの処理
    toc_path = DEFAULT_TOC_FILE
    if args.file:
        toc_path = Path(args.file)
        try:
            toc_path = validate_path_within_base(toc_path, PROJECT_ROOT)
        except ValueError:
            log(f"エラー: 不正なパス: {toc_path}")
            return 1

    if not toc_path.exists():
        log(f"エラー: ファイルが存在しません: {toc_path}")
        return 1

    success = validate_toc(toc_path)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
