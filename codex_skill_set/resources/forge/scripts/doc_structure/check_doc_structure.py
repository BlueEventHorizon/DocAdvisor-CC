#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.doc_structure.yaml の存在確認・バージョンチェックスクリプト。

setup-doc-structure スキルの Step 1 で使用する。
存在確認・バージョン検出・マイグレーション要否を一括で JSON 出力する。

Usage:
    python3 check_doc_structure.py [project_root]

Created by: k_terada
"""

import json
import sys
from pathlib import Path

# 同一ディレクトリの migrate_doc_structure.py から関数をインポート
from migrate_doc_structure import CURRENT_VERSION, detect_version

# resolve_doc_structure.py の find_project_root をインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'skills' / 'doc-structure' / 'scripts'))
from resolve_doc_structure import find_project_root


def check(project_root):
    """
    .doc_structure.yaml の状態を確認する。

    Returns:
        dict: 確認結果
    """
    doc_structure_path = Path(project_root) / '.doc_structure.yaml'

    if not doc_structure_path.exists():
        return {'exists': False}

    try:
        content = doc_structure_path.read_text(encoding='utf-8')
    except (IOError, OSError, UnicodeDecodeError) as e:
        return {
            'exists': True,
            'error': f"ファイルの読み込みに失敗しました: {e}",
        }

    detected = detect_version(content)
    needs_migration = detected < CURRENT_VERSION

    return {
        'exists': True,
        'needs_migration': needs_migration,
        'detected_version': detected,
        'current_version': CURRENT_VERSION,
        'content': content,
    }


def main():
    project_root = sys.argv[1] if len(sys.argv) > 1 else None

    if project_root is None:
        project_root = find_project_root()
    else:
        project_root = str(Path(project_root).resolve())

    result = check(project_root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
