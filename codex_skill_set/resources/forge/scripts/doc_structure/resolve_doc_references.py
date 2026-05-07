#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.doc_structure.yaml から参考文書を解決するスクリプト。

rules / specs カテゴリのパスを読み込み、glob 展開・exclude 適用後に
.md ファイルの一覧を JSON で出力する。

DocAdvisor（/query-rules, /query-specs）が利用不可の場合のフォールバックとして使用する。

注意: .doc_structure.yaml のフォーマットが旧 doc_type-centric 形式から
config.yaml 互換形式に変更された。パース処理は resolve_doc_structure.py に委譲している。

使用例:
    python3 resolve_doc_references.py --type rules
    python3 resolve_doc_references.py --type specs
    python3 resolve_doc_references.py --type all
    python3 resolve_doc_references.py --type rules --project-root /path/to/project
"""

import argparse
import json
import os
import sys

# resolve_doc_structure.py をインポート
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'skills', 'doc-structure', 'scripts'
))
from resolve_doc_structure import (
    load_doc_structure,
    resolve_files,
    find_project_root,
)


# ---------------------------------------------------------------------------
# メインロジック
# ---------------------------------------------------------------------------

def resolve_references(resolve_type, project_root, doc_structure_path=None):
    """参考文書を解決して結果 dict を返す。

    Args:
        resolve_type: 'rules' / 'specs' / 'all'
        project_root: プロジェクトルートの絶対パス
        doc_structure_path: .doc_structure.yaml のパス（省略時は自動決定）

    Returns:
        dict: JSON 出力用の結果 dict
    """
    try:
        config, _content = load_doc_structure(project_root, doc_structure_path)
    except FileNotFoundError as e:
        return {
            'status': 'error',
            'message': str(e),
        }
    except (IOError, OSError, UnicodeDecodeError) as e:
        return {
            'status': 'error',
            'message': f".doc_structure.yaml のパースに失敗しました: {e}",
        }
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {
            'status': 'error',
            'message': f".doc_structure.yaml のパース中にエラーが発生しました: {e}",
        }

    result = {
        'status': 'resolved',
        'project_root': project_root,
    }

    if resolve_type in ('rules', 'all'):
        result['rules'] = resolve_files(config, 'rules', project_root)

    if resolve_type in ('specs', 'all'):
        result['specs'] = resolve_files(config, 'specs', project_root)

    return result


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def parse_args():
    """コマンドライン引数をパースする。"""
    parser = argparse.ArgumentParser(
        description='.doc_structure.yaml から参考文書パスを解決して JSON で出力する'
    )
    parser.add_argument(
        '--type',
        required=True,
        choices=['rules', 'specs', 'all'],
        help='解決対象カテゴリ: rules / specs / all',
    )
    parser.add_argument(
        '--project-root',
        default=None,
        help='プロジェクトルートのパス（省略時: .git を遡って自動検出）',
    )
    parser.add_argument(
        '--doc-structure',
        default=None,
        help='.doc_structure.yaml のパス（省略時: project_root/.doc_structure.yaml）',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # プロジェクトルートの決定
    project_root = args.project_root
    if project_root:
        project_root = os.path.abspath(project_root)
    else:
        project_root = find_project_root()

    # .doc_structure.yaml パスの決定
    doc_structure_path = args.doc_structure
    if doc_structure_path:
        doc_structure_path = os.path.abspath(doc_structure_path)

    result = resolve_references(args.type, project_root, doc_structure_path)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get('status') == 'error':
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
