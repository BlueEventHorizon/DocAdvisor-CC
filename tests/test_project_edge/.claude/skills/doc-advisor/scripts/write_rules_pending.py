#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pending YAML 書き込みスクリプト（rules 用）

サブエージェントが解析した結果を pending YAML に書き込み、
status を completed に変更する。

使用方法:
    python3 write_rules_pending.py \
      --entry-file ".claude/doc-advisor/rules/.toc_work/xxx.yaml" \
      --title "タイトル" \
      --purpose "目的" \
      --content-details "項目1,項目2,項目3,項目4,項目5" \
      --applicable-tasks "タスク1,タスク2" \
      --keywords "kw1,kw2,kw3,kw4,kw5"

終了コード:
    0: 成功
    1: ファイル不存在
    2: 必須フィールド欠落
    3: 配列要素数不足
    4: 書き込み失敗
"""

import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import yaml_escape, load_entry_file


# バリデーション設定
MIN_CONTENT_DETAILS = 5
MIN_APPLICABLE_TASKS = 1
MIN_KEYWORDS = 5


def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description='pending YAML に解析結果を書き込む（rules 用）'
    )
    parser.add_argument('--entry-file', required=True,
                        help='対象の entry YAML ファイルパス')
    parser.add_argument('--title', required=True,
                        help='ドキュメントタイトル')
    parser.add_argument('--purpose', required=True,
                        help='ドキュメントの目的（1-2文）')
    parser.add_argument('--content-details', required=True,
                        help='内容詳細（カンマ区切り、5-10項目）')
    parser.add_argument('--applicable-tasks', required=True,
                        help='適用タスク（カンマ区切り、1項目以上）')
    parser.add_argument('--keywords', required=True,
                        help='キーワード（カンマ区切り、5-10個）')
    parser.add_argument('--force', action='store_true',
                        help='completed 状態でも強制上書き')

    return parser.parse_args()


def parse_comma_separated(value):
    """カンマ区切り文字列を配列に変換"""
    if not value:
        return []
    items = [item.strip() for item in value.split(',')]
    return [item for item in items if item]  # 空文字を除去


def validate_array(name, items, min_count):
    """配列の要素数をバリデーション"""
    if len(items) < min_count:
        print(f"Error: {name} requires at least {min_count} items (got {len(items)})")
        print(f"  Provided: {', '.join(items)}")
        return False
    return True


def write_entry_yaml(filepath, meta, entry):
    """
    entry YAML ファイルを書き込む

    Args:
        filepath: 出力ファイルパス
        meta: _meta セクションの辞書
        entry: エントリデータの辞書

    Returns:
        bool: 成功時 True
    """
    lines = []

    # _meta セクション
    lines.append("_meta:")
    lines.append(f"  source_file: {meta.get('source_file', '')}")
    lines.append(f"  status: {meta.get('status', 'completed')}")
    lines.append(f"  updated_at: {meta.get('updated_at', '')}")
    lines.append("")

    # 通常フィールド
    lines.append(f"title: {yaml_escape(entry.get('title', ''))}")
    lines.append(f"purpose: {yaml_escape(entry.get('purpose', ''))}")

    # 配列フィールド
    for field in ['content_details', 'applicable_tasks', 'keywords']:
        lines.append(f"{field}:")
        items = entry.get(field, [])
        for item in items:
            lines.append(f"  - {yaml_escape(item)}")

    lines.append("")  # 末尾の空行

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except (IOError, OSError, PermissionError) as e:
        print(f"Error: Failed to write file: {filepath} - {e}")
        return False


def main():
    args = parse_args()

    entry_file = Path(args.entry_file)

    # ファイル存在確認
    if not entry_file.exists():
        print(f"Error: Entry file not found: {entry_file}")
        return 1

    # 既存ファイル読み込み
    try:
        meta, _ = load_entry_file(entry_file)
    except IOError as e:
        print(f"Error: {e}")
        return 1

    # _meta セクション確認
    if not meta:
        print(f"Error: Entry file missing _meta section: {entry_file}")
        return 1

    # source_file 確認
    if 'source_file' not in meta:
        print(f"Error: Entry file missing _meta.source_file: {entry_file}")
        return 1

    # completed 状態チェック
    if meta.get('status') == 'completed' and not args.force:
        print(f"Error: Entry file already completed: {entry_file}")
        print("  Use --force to overwrite")
        return 1

    # 配列をパース
    content_details = parse_comma_separated(args.content_details)
    applicable_tasks = parse_comma_separated(args.applicable_tasks)
    keywords = parse_comma_separated(args.keywords)

    # バリデーション
    valid = True
    if not validate_array('content_details', content_details, MIN_CONTENT_DETAILS):
        valid = False
    if not validate_array('applicable_tasks', applicable_tasks, MIN_APPLICABLE_TASKS):
        valid = False
    if not validate_array('keywords', keywords, MIN_KEYWORDS):
        valid = False

    if not valid:
        return 3

    # _meta 更新
    updated_meta = {
        'source_file': meta['source_file'],
        'status': 'completed',
        'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    }

    # エントリデータ
    entry = {
        'title': args.title,
        'purpose': args.purpose,
        'content_details': content_details,
        'applicable_tasks': applicable_tasks,
        'keywords': keywords
    }

    # 書き込み
    if not write_entry_yaml(entry_file, updated_meta, entry):
        return 4

    # 成功メッセージ
    print(f"Entry completed: {entry_file}")
    print(f"  source_file: {updated_meta['source_file']}")
    print(f"  status: {updated_meta['status']}")
    print(f"  updated_at: {updated_meta['updated_at']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
