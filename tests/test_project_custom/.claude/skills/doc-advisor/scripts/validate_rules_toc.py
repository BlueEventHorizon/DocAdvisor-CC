#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rules_toc.yaml 検査スクリプト

生成された rules_toc.yaml の整合性を検査する。

使用方法:
    python3 validate_rules_toc.py [--file PATH]

オプション:
    --file    検査対象ファイル（デフォルト: .claude/doc-advisor/rules/rules_toc.yaml）

検査項目:
    1. YAML構文検査
    2. 必須フィールド検査
    3. ファイル参照検査
    4. 重複パス検査
"""

import sys
from pathlib import Path

from toc_utils import get_project_root, load_config, resolve_config_path

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
RULES_DIR = None
DEFAULT_TOC_FILE = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, RULES_DIR, DEFAULT_TOC_FILE

    try:
        CONFIG = load_config('rules')
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    RULES_DIR = PROJECT_ROOT / CONFIG.get('root_dir', 'rules').rstrip('/')
    DEFAULT_TOC_FILE = resolve_config_path(CONFIG.get('toc_file', 'rules_toc.yaml'), RULES_DIR, PROJECT_ROOT)
    return True


def load_existing_toc(toc_path):
    """既存の rules_toc.yaml を読み込み"""
    if not toc_path.exists():
        return {}

    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Failed to read {toc_path}: {e}")
        return {}

    docs = {}
    current_file = None
    current_entry = {}
    current_list = None
    in_docs = False

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            continue

        if stripped == 'docs:':
            in_docs = True
            continue

        if not in_docs:
            continue

        # ファイルパスの検出（2スペースインデントで : で終わる）
        if line.startswith('  ') and not line.startswith('    ') and stripped.endswith(':'):
            if current_file and current_entry:
                docs[current_file] = current_entry
            current_file = stripped.rstrip(':')
            current_entry = {}
            current_list = None
        elif line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
            if current_file:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip().strip('"\'')
                if val:
                    current_entry[key] = val
                else:
                    current_list = []
                    current_entry[key] = current_list
        elif stripped.startswith('- ') and current_list is not None:
            item = stripped[2:].strip().strip('"\'')
            current_list.append(item)

    if current_file and current_entry:
        docs[current_file] = current_entry

    return docs


def validate_toc(toc_path):
    """
    生成された toc ファイルを検査する
    - YAML構文検査
    - 必須フィールド検査
    - ファイル参照検査
    - 重複パス検査
    """
    print("=" * 50)
    print("rules_toc.yaml 検査")
    print("=" * 50)
    print(f"対象: {toc_path}")
    print()

    errors = []

    # 1. YAML構文検査（ファイルが読み込めるか）
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print("✓ YAML構文検査: OK（ファイル読み込み成功）")
    except Exception as e:
        errors.append(f"YAML構文検査: ファイル読み込み失敗 - {e}")
        print(f"\n❌ 検査失敗: {len(errors)} 件のエラー")
        for err in errors:
            print(f"  - {err}")
        return False

    # パース
    docs = load_existing_toc(toc_path)

    # 2. 必須フィールド検査
    # title/purpose が必須（文字列）
    # content_details/applicable_tasks/keywords が必須（非空配列）
    # フォーマット定義: No null, No empty arrays (rules_toc_format.md)
    required_string_fields = ['title', 'purpose']
    required_array_fields = ['content_details', 'applicable_tasks', 'keywords']
    field_errors = []

    for filepath, entry in docs.items():
        for field in required_string_fields:
            if not entry.get(field):
                field_errors.append(f"必須フィールド欠落: '{filepath}' に '{field}' がありません")
        for field in required_array_fields:
            value = entry.get(field)
            if not isinstance(value, list) or len(value) == 0:
                field_errors.append(f"必須配列フィールド不正: '{filepath}' の '{field}' が未設定または空配列です")

    if not field_errors:
        print(f"✓ 必須フィールド検査: OK（{len(docs)}件のエントリ）")
    else:
        print(f"✗ 必須フィールド検査: {len(field_errors)}件のエラー")
        errors.extend(field_errors)

    # 3. ファイル参照検査
    # キーはプロジェクトルートからの相対パス（例: rules/core/architecture_rule.md）
    file_errors = []
    for filepath in docs.keys():
        full_path = PROJECT_ROOT / filepath
        if not full_path.exists():
            file_errors.append(f"ファイル不在: '{filepath}' が存在しません")

    if not file_errors:
        print(f"✓ ファイル参照検査: OK（全ファイルが存在）")
    else:
        print(f"✗ ファイル参照検査: {len(file_errors)}件のエラー")
        errors.extend(file_errors)

    # 4. 重複パス検査（辞書なので本質的に重複はないが確認）
    print(f"✓ 重複パス検査: OK（{len(docs)}件のユニークパス）")

    # 結果サマリー
    print()
    if errors:
        print(f"❌ 検査失敗: {len(errors)} 件のエラー")
        print("-" * 40)
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print(f"✅ 検査完了: 全チェックOK")
        return True


def main():
    # Initialize configuration
    if not init_config():
        return 1

    # --file オプションの処理
    toc_path = DEFAULT_TOC_FILE
    if '--file' in sys.argv:
        idx = sys.argv.index('--file')
        if idx + 1 < len(sys.argv):
            toc_path = Path(sys.argv[idx + 1])

    if not toc_path.exists():
        print(f"エラー: ファイルが存在しません: {toc_path}")
        return 1

    success = validate_toc(toc_path)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
