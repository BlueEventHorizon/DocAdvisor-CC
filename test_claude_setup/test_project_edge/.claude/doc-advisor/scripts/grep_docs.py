#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全文検索スクリプト（grep_docs.py）— doc-advisor plugin

固有名詞・識別子などのキーワードでドキュメントを全文検索する。
検索はキーワードの大文字小文字を区別しない部分一致で行う。
標準ライブラリのみ使用。

Usage:
    python3 grep_docs.py --category {specs|rules} --keyword "doc_structure.yaml"

Options:
    --category  対象カテゴリ: specs または rules（必須）
    --keyword   検索キーワード（必須）

Run from: プロジェクトルート

出力形式:
    {
      "status": "ok",
      "keyword": "<検索キーワード>",
      "results": [
        {"path": "<プロジェクトルート相対パス>"},
        ...
      ]
    }

エラー出力形式:
    {
      "status": "error",
      "error": "<エラーメッセージ>"
    }

設定未準備時:
    {
      "status": "config_required",
      "message": "<案内メッセージ>"
    }
"""

import argparse
import json
import sys

from toc_utils import (
    ConfigNotReadyError,
    get_all_md_files,
    init_common_config,
    log,
    normalize_path,
)


def parse_args():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description='全文検索スクリプト — キーワードでドキュメントを検索する'
    )
    parser.add_argument(
        '--category',
        required=True,
        choices=['rules', 'specs'],
        help='対象カテゴリ: rules または specs',
    )
    parser.add_argument(
        '--keyword',
        required=True,
        help='検索キーワード（大文字小文字区別なし部分一致）',
    )
    return parser.parse_args()


def search_files(keyword, common_config):
    """
    全対象ファイルからキーワードを部分一致検索する。

    検索は大文字小文字を区別しない（str.lower() で統一）。

    Args:
        keyword: 検索キーワード（空文字でないこと）
        common_config: init_common_config() の返り値 dict

    Returns:
        list[str]: マッチしたファイルのプロジェクトルート相対パス（ソート済み）
    """
    project_root = common_config['project_root']
    keyword_lower = keyword.lower()

    md_files, _ = get_all_md_files(common_config)

    matched_paths = []
    for filepath in md_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except (IOError, OSError, PermissionError) as e:
            # 読み取り不可ファイルはスキップ（警告を stderr に出力）
            log(f"Warning: skipping unreadable file {filepath}: {e}")
            continue

        if keyword_lower in content.lower():
            # プロジェクトルート相対パスに変換
            try:
                rel_path = normalize_path(filepath.relative_to(project_root))
            except ValueError:
                # relative_to が失敗した場合（シンボリックリンク等）は絶対パスを使用
                rel_path = normalize_path(filepath)
            matched_paths.append(str(rel_path))

    matched_paths.sort()
    return matched_paths


def main():
    args = parse_args()

    # --keyword 空文字チェック
    if not args.keyword.strip():
        print(json.dumps({
            "status": "error",
            "error": "--keyword must not be empty.",
        }))
        return 1

    # 設定初期化
    try:
        common_config = init_common_config(args.category)
    except ConfigNotReadyError as e:
        print(json.dumps({
            "status": "config_required",
            "message": str(e),
        }))
        return 1
    except (RuntimeError, FileNotFoundError) as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
        }))
        return 1

    # 全文検索実行
    matched_paths = search_files(args.keyword, common_config)

    # 結果を JSON 出力
    result = {
        "status": "ok",
        "keyword": args.keyword,
        "results": [{"path": p} for p in matched_paths],
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
