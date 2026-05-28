#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
セマンティック検索スクリプト (doc-advisor plugin)

インデックス JSON をロードし、クエリ文字列をベクトル化してコサイン類似度で
関連文書を検索する。結果は JSON 形式で標準出力に出力する。

Usage:
    python3 search_docs.py --category {specs|rules} --query "タスクの説明文" [--threshold 0.3]

Options:
    --category   対象カテゴリ（必須）: specs または rules
    --query      検索クエリ（必須）
    --threshold  類似度スコアの下限閾値（デフォルト: 0.3）

Run from: Project root
"""

import argparse
import json
import math
import sys
from pathlib import Path

from embedding_api import EMBEDDING_MODEL, call_embedding_api_single, get_api_key
from toc_utils import (
    ConfigNotReadyError,
    calculate_file_hash,
    get_all_md_files,
    get_project_root,
    init_common_config,
    load_config,
    normalize_path,
    resolve_config_path,
)


def parse_args():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description="セマンティック検索: クエリに類似した文書をインデックスから検索する"
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=["rules", "specs"],
        help="対象カテゴリ: rules または specs",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="検索クエリ（必須）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="類似度スコアの下限閾値（デフォルト: 0.3）",
    )
    parser.add_argument(
        "--skip-stale-check",
        action="store_true",
        help="staleness チェックをスキップする（SKILL 側で事前チェック済みの場合に使用）",
    )
    return parser.parse_args()


def get_index_path(category, project_root):
    """インデックス JSON のパスを返す（config の index_file を参照）。

    config に index_file が設定されていればそのパスを使用し、
    未設定の場合はデフォルトパスにフォールバックする。

    Args:
        category: 'rules' または 'specs'
        project_root: プロジェクトルートパス (Path)

    Returns:
        Path: インデックスファイルの絶対パス
    """
    config = load_config(category)
    default = f'.claude/doc-advisor/index/{category}/{category}_index.json'
    index_file = config.get('index_file', default)
    return resolve_config_path(index_file, project_root, project_root)


def load_index(index_path):
    """
    インデックス JSON を読み込む。

    Args:
        index_path: Path to index JSON file

    Returns:
        dict: インデックス内容

    Raises:
        FileNotFoundError: インデックスが存在しない場合
        ValueError: JSON が破損している場合
    """
    index_path = Path(index_path)
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Index JSON is corrupted: {e}") from e


def check_model_mismatch(index):
    """
    インデックスのモデルと現在のモデル定数を比較する。

    Args:
        index: load_index() が返したインデックス dict

    Returns:
        str or None: モデル不一致の場合はエラーメッセージ、一致する場合は None
    """
    index_model = index.get("metadata", {}).get("model", "")
    if index_model and index_model != EMBEDDING_MODEL:
        return (
            f"Model mismatch: index uses {index_model}, "
            f"current is {EMBEDDING_MODEL}. "
            "Run embed_docs.py --full to rebuild."
        )
    return None


def check_staleness(index, common_config):
    """
    インデックスの鮮度を確認する（チェックサム比較）。

    インデックス内の各エントリが持つ checksum と、現在のファイルのハッシュを比較する。
    いずれか不一致または存在しないファイルがある場合は stale と判定する。

    Args:
        index: load_index() が返したインデックス dict
        common_config: init_common_config() の返り値 dict

    Returns:
        bool: stale であれば True、新鮮であれば False
    """
    project_root = common_config["project_root"]
    entries = index.get("entries", {})

    for rel_path, entry in entries.items():
        stored_checksum = entry.get("checksum", "")
        abs_path = project_root / rel_path
        if not abs_path.exists():
            # インデックスに記録されたファイルが削除されている → stale
            return True
        current_hash = calculate_file_hash(abs_path)
        if current_hash != stored_checksum:
            return True

    # ディスク上の新規ファイルがインデックスに存在しない場合は stale
    if "root_dirs" in common_config:
        md_files, file_root_map = get_all_md_files(common_config)
        disk_paths = set()
        for f in md_files:
            root_dir, root_dir_name = file_root_map[f]
            rel_path = normalize_path(f.relative_to(root_dir))
            disk_paths.add(f"{root_dir_name}/{rel_path}")
        index_paths = set(entries.keys())
        if disk_paths - index_paths:
            return True

    return False


def cosine_similarity(vec_a, vec_b):
    """
    コサイン類似度を純粋 Python で計算する。

    Args:
        vec_a: ベクトル A（list of float）
        vec_b: ベクトル B（list of float）

    Returns:
        float: コサイン類似度（-1.0〜1.0）
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search(query, index, api_key, threshold):
    """
    インデックス内の全エントリとコサイン類似度を計算し、閾値以上の候補を返す。

    Args:
        query: 検索クエリ文字列
        index: load_index() が返したインデックス dict
        api_key: OpenAI API キー
        threshold: 類似度スコアの下限閾値

    Returns:
        list[dict]: score 降順でソートされた {"path": ..., "title": ..., "score": ...} のリスト
    """
    query_vec = call_embedding_api_single(query, api_key)

    entries = index.get("entries", {})
    results = []
    for rel_path, entry in entries.items():
        embedding = entry.get("embedding")
        if not embedding:
            continue
        score = cosine_similarity(query_vec, embedding)
        if score >= threshold:
            results.append({
                "path": normalize_path(rel_path),
                "title": entry.get("title", ""),
                "score": round(score, 6),
            })

    # スコア降順でソート
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def main():
    """メインエントリーポイント"""
    args = parse_args()

    if not args.query.strip():
        print(json.dumps({
            "status": "error",
            "error": "--query must not be empty.",
        }))
        sys.exit(1)

    # 設定初期化
    try:
        common_config = init_common_config(args.category)
    except ConfigNotReadyError as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(1)
    except (RuntimeError, FileNotFoundError) as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        sys.exit(1)

    # インデックスパスの解決
    project_root = common_config["project_root"]
    index_path = get_index_path(args.category, project_root)

    # インデックスの読み込み
    try:
        index = load_index(index_path)
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "error": "Index not found. Run embed_docs.py first.",
        }))
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({
            "status": "error",
            "error": f"Index is corrupted: {e}. Run embed_docs.py --full to rebuild.",
        }))
        sys.exit(1)

    # モデル不一致チェック
    model_error = check_model_mismatch(index)
    if model_error:
        print(json.dumps({"status": "error", "error": model_error}))
        sys.exit(1)

    # Staleness チェック（SKILL 側で embed_docs.py --check 済みなら --skip-stale-check で省略可）
    if not args.skip_stale_check and check_staleness(index, common_config):
        print(json.dumps({
            "status": "error",
            "error": "Index is stale. Run embed_docs.py to update.",
        }))
        sys.exit(1)

    # API キーの取得（FNC-004 KEY-01 / DES-007 §2.2: OPENAI_API_DOCDB_KEY 優先、未設定時 OPENAI_API_KEY にフォールバック）
    api_key = get_api_key()
    if not api_key:
        print(json.dumps({
            "status": "error",
            "error": (
                "OPENAI_API_DOCDB_KEY（または OPENAI_API_KEY）が設定されていません。"
                "export OPENAI_API_DOCDB_KEY='your-api-key' を実行してください。"
            ),
        }))
        sys.exit(1)

    # 検索実行
    try:
        results = search(args.query, index, api_key, args.threshold)
    except RuntimeError as e:
        print(json.dumps({"status": "error", "error": f"API error: {e}"}))
        sys.exit(1)

    # JSON 出力（DES-006 §3.4 準拠）
    print(json.dumps({
        "status": "ok",
        "query": args.query,
        "results": results,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
