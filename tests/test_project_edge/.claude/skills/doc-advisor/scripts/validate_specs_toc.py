#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specs_toc.yaml 検査スクリプト

生成された specs_toc.yaml の整合性を検査する。

使用方法:
    python3 validate_specs_toc.py [--file PATH]

オプション:
    --file    検査対象ファイル（デフォルト: .claude/doc-advisor/specs/specs_toc.yaml）

検査項目:
    1. YAML構文検査
    2. 必須フィールド検査
    3. ファイル参照検査
    4. 重複ID検査
"""

import sys
import re
from pathlib import Path

from toc_utils import get_project_root, load_config, resolve_config_path

# Global configuration (initialized in init_config())
CONFIG = None
PROJECT_ROOT = None
SPECS_DIR = None
DEFAULT_TOC_FILE = None


def init_config():
    """
    Initialize configuration. Call this at the start of main().

    Returns:
        bool: True on success, False on failure
    """
    global CONFIG, PROJECT_ROOT, SPECS_DIR, DEFAULT_TOC_FILE

    try:
        CONFIG = load_config('specs')
        PROJECT_ROOT = get_project_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    SPECS_DIR = PROJECT_ROOT / CONFIG.get('root_dir', 'specs').rstrip('/')
    DEFAULT_TOC_FILE = resolve_config_path(CONFIG.get('toc_file', 'specs_toc.yaml'), SPECS_DIR, PROJECT_ROOT)
    return True


def load_existing_toc(toc_path):
    """既存の specs_toc.yaml を読み込み（docs: セクション形式対応）"""
    if not toc_path.exists():
        return {}, {}

    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        print(f"Warning: Failed to read {toc_path}: {e}")
        return {}, {}

    requirements = {}  # doc_type: requirement
    designs = {}       # doc_type: design
    current_section = None
    current_path = None
    current_entry = {}
    current_list = None

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            continue

        # セクション検出
        if stripped == 'docs:':
            current_section = 'docs'
            continue
        elif stripped.startswith('metadata:'):
            current_section = 'metadata'
            continue

        # docs セクション内のエントリ解析
        if current_section == 'docs':
            # ファイルパスキーの検出 (e.g., "main/requirements/app.md:")
            if line.startswith('  ') and not line.startswith('    ') and stripped.endswith(':'):
                # 前のエントリを保存
                if current_path and current_entry:
                    doc_type = current_entry.get('doc_type', '')
                    if doc_type == 'requirement':
                        requirements[current_path] = current_entry
                    elif doc_type == 'design':
                        designs[current_path] = current_entry

                current_path = stripped.rstrip(':')
                current_entry = {}
                current_list = None

            # エントリのフィールド解析
            elif line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
                if current_path:
                    key, _, val = stripped.partition(':')
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    if val:
                        current_entry[key] = val
                    else:
                        current_list = []
                        current_entry[key] = current_list

            # リスト項目
            elif stripped.startswith('- ') and current_list is not None:
                item = stripped[2:].strip().strip('"\'')
                current_list.append(item)

    # 最後のエントリを保存
    if current_path and current_entry:
        doc_type = current_entry.get('doc_type', '')
        if doc_type == 'requirement':
            requirements[current_path] = current_entry
        elif doc_type == 'design':
            designs[current_path] = current_entry

    return requirements, designs


def validate_toc(toc_path):
    """
    生成された toc ファイルを検査する
    - YAML構文検査
    - 必須フィールド検査
    - ファイル参照検査
    - 重複ID検査
    """
    print("=" * 50)
    print("specs_toc.yaml 検査")
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

    # パース（新形式: docs セクション内の doc_type で分類）
    requirements, designs = load_existing_toc(toc_path)

    # 2. 必須フィールド検査
    # 新形式: キーがファイルパス、doc_type/title/purpose が必須（文字列）
    # content_details/applicable_tasks/keywords が必須（非空配列）
    # フォーマット定義: No null, No empty arrays (specs_toc_format.md)
    required_string_fields = ['doc_type', 'title', 'purpose']
    required_array_fields = ['content_details', 'applicable_tasks', 'keywords']
    field_errors = []

    all_entries = list(requirements.items()) + list(designs.items())
    for file_path, entry in all_entries:
        for field in required_string_fields:
            if not entry.get(field):
                field_errors.append(f"必須フィールド欠落: {file_path} に '{field}' がありません")
        for field in required_array_fields:
            value = entry.get(field)
            if not isinstance(value, list) or len(value) == 0:
                field_errors.append(f"必須配列フィールド不正: {file_path} の '{field}' が未設定または空配列です")

    if not field_errors:
        print(f"✓ 必須フィールド検査: OK（requirements: {len(requirements)}件, designs: {len(designs)}件）")
    else:
        print(f"✗ 必須フィールド検査: {len(field_errors)}件のエラー")
        errors.extend(field_errors)

    # 3. ファイル参照検査
    # 新形式: キーはプロジェクトルートからの相対パス（例: specs/main/requirements/app.md）
    file_errors = []
    for file_path in requirements.keys():
        full_path = PROJECT_ROOT / file_path
        if not full_path.exists():
            file_errors.append(f"ファイル不在: '{file_path}' が存在しません")

    for file_path in designs.keys():
        full_path = PROJECT_ROOT / file_path
        if not full_path.exists():
            file_errors.append(f"ファイル不在: '{file_path}' が存在しません")

    if not file_errors:
        print(f"✓ ファイル参照検査: OK（全ファイルが存在）")
    else:
        print(f"✗ ファイル参照検査: {len(file_errors)}件のエラー")
        errors.extend(file_errors)

    # 4. 重複パス検査
    all_paths = list(requirements.keys()) + list(designs.keys())
    seen = set()
    duplicates = []
    for file_path in all_paths:
        if file_path in seen:
            duplicates.append(f"重複パス: '{file_path}' が複数回定義されています")
        seen.add(file_path)

    if not duplicates:
        print(f"✓ 重複パス検査: OK（{len(all_paths)}件のユニークパス）")
    else:
        print(f"✗ 重複パス検査: {len(duplicates)}件の重複")
        errors.extend(duplicates)

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
