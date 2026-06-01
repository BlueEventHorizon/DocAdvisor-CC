#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC 検査スクリプト（doc-advisor plugin / key + path I/F）

DES-005 §7.1（doc_type 必須撤廃）/ §4.1（モジュール）/ §3.2（ストア構造）/
§8（JSON 出力契約）を実装する。

key で解決した store_dir/toc.yaml の整合性を検査する。doc_type は必須としない。

使用方法:
    python3 validate_toc.py --key K [--file PATH]
    python3 validate_toc.py --all [--file PATH]

オプション:
    --key   検査対象 key（opaque）
    --all   単体モード（予約 key all）。--key 省略も同義
    --file  検査対象ファイル（デフォルト: store_dir/toc.yaml）

検査項目:
    1. ファイル読み込み検査
    2. 必須フィールド検査（title/purpose + content_details/applicable_tasks/keywords）
    3. ファイル参照検査
"""

import sys
import argparse
from pathlib import Path

from toc_utils import (
    get_project_root,
    validate_path_within_base,
    load_existing_toc,
    log,
)
from toc_store import (
    KeyError_,
    ErrorCode,
    STATUS_OK,
    STATUS_ERROR,
    resolve_store_dir,
    resolve_key_from_args,
    emit_json,
    toc_path_rel,
)


def validate_toc(toc_path, *, project_root=None):
    """
    生成された toc.yaml を検査する（DES-005 §7.1: doc_type 必須なし）

    - ファイル読み込み検査
    - 必須フィールド検査（title/purpose + 3 配列。doc_type は必須としない）
    - ファイル参照検査

    Args:
        toc_path: 検査対象の ToC ファイルパス
        project_root: プロジェクトルートパス（省略時は get_project_root()）

    Returns:
        bool: 全チェック OK で True
    """
    _project_root = project_root if project_root is not None else get_project_root()

    log("=" * 50)
    log("toc.yaml 検査")
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

    # 2. 必須フィールド検査（DES-005 §7.1）
    # title/purpose が必須（文字列）
    # content_details/applicable_tasks/keywords が必須（非空配列）
    # doc_type は必須から除外する（category 廃止により doc_type 自動分類が成立しないため）
    # フォーマット定義: No null, No empty arrays (formats/toc_format.md)
    required_string_fields = ['title', 'purpose']
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
    # キーはプロジェクトルートからの相対パス
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


def parse_args(argv=None):
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Validate generated ToC YAML file (key + path I/F)'
    )
    parser.add_argument('--key', help='検査対象 key（opaque）')
    parser.add_argument('--all', action='store_true',
                        help="単体モード（予約 key 'all'）。--key 省略も同義")
    parser.add_argument('--file', default=None,
                        help='検査対象ファイルパス（デフォルト: store_dir/toc.yaml）')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    project_root = get_project_root()

    # key 解決（--all / --key 省略 → 予約 all、--key all → KEY_RESERVED）
    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    store_dir = resolve_store_dir(key, project_root)
    toc_rel = toc_path_rel(store_dir, project_root)

    # --file 指定があれば優先、なければ store_dir/toc.yaml
    if args.file:
        toc_path = Path(args.file)
        try:
            toc_path = validate_path_within_base(toc_path, project_root)
        except ValueError:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.PATH_TRAVERSAL,
                message=f"不正なパス: {args.file}",
                key=key,
                toc_path=toc_rel,
            )
            return 1
    else:
        toc_path = store_dir / "toc.yaml"

    if not toc_path.exists():
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.TOC_NOT_FOUND,
            message=f"ファイルが存在しません: {toc_path}",
            key=key,
            toc_path=toc_rel,
        )
        return 1

    success = validate_toc(toc_path, project_root=project_root)

    if success:
        emit_json(
            STATUS_OK,
            error_code=None,
            message="ToC validation passed",
            key=key,
            toc_path=toc_rel,
        )
        return 0

    emit_json(
        STATUS_ERROR,
        error_code=ErrorCode.INVALID_PATH,
        message="ToC validation failed",
        key=key,
        toc_path=toc_rel,
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
