#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc-db index を検索する。"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import build_index
import hybrid_score
import lexical_search
import llm_rerank
from _utils import calculate_file_hash, load_checksums
from embedding_api import EMBEDDING_MODEL, call_embedding_api_single


class SearchError(Exception):
    """search_index 内部で発生する回復可能なエラー。"""

    def __init__(self, message: str, hint: str = "-", exit_code: int = 2):
        super().__init__(message)
        self.hint = hint
        self.exit_code = exit_code


def _event(event_type: str, **fields):
    payload = {"event_type": event_type}
    payload.update(fields)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Search doc-db index")
    parser.add_argument("--category", required=True, choices=["rules", "specs"])
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", default="hybrid", choices=["emb", "lex", "hybrid", "rerank"])
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--doc-type", default="")
    return parser.parse_args()


def _error(message: str, hint: str = "-", exit_code: int = 2):
    _event("validation_error", error=message, hint=hint)
    raise SearchError(message, hint, exit_code)


def load_index(index_path: Path) -> Dict:
    if not index_path.exists():
        _error("index_not_found", "run build_index first")
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _error("index_corrupted", "run build_index --full")
    return {}


def _load_index_or_rebuild(
    project_root: Path,
    category: str,
    doc_type: str,
    require_full: bool = False,
) -> Dict:
    index_path = build_index.get_index_path(project_root, category, doc_type)
    if not index_path.exists():
        rc, _ = build_index.run_build(project_root, category, full=require_full, doc_type=doc_type)
        if rc != 0:
            _error("index_not_found", "run build_index first")
    return load_index(index_path)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _resolve_doc_types(category: str, doc_type: str, project_root: Path) -> List[str]:
    if category != "specs":
        return [""]
    if doc_type:
        return [x.strip() for x in doc_type.split(",") if x.strip()]
    return build_index.resolve_specs_doc_types(project_root)


def _validate_doc_type_values(project_root: Path, category: str, doc_types: List[str]):
    if category != "specs":
        return
    allowed = set(build_index.resolve_specs_doc_types(project_root))
    invalid = [d for d in doc_types if d not in allowed]
    if invalid:
        _error(
            f"unsupported doc_type: {','.join(invalid)}",
            f"allowed: {','.join(sorted(allowed))}",
        )


def _is_stale(project_root: Path, category: str, index: Dict, doc_type: str) -> bool:
    checksums_path = build_index.get_checksums_path(
        build_index.get_index_path(project_root, category, doc_type)
    )
    saved = load_checksums(checksums_path)
    index_generated_at = index.get("metadata", {}).get("generated_at", "")
    checksum_generated_at = build_index._read_checksums_generated_at(checksums_path)
    if checksum_generated_at and index_generated_at and checksum_generated_at != index_generated_at:
        _error("generated_at_mismatch", "run build_index --full")

    for rel, digest in saved.items():
        if calculate_file_hash(project_root / rel) != digest:
            return True
    current_files = set(build_index.resolve_target_files(project_root, category, doc_type))
    if current_files != set(saved.keys()):
        return True
    return False



def _make_results(entries: List[Dict], ids: List[str], score_key: str) -> List[Dict]:
    mapping = {f"{e['path']}#{e['chunk_id']}": e for e in entries}
    out = []
    for row in ids:
        entry = mapping.get(row["chunk_id"])
        if entry is None:
            continue
        out.append(
            {
                "path": entry["path"],
                "heading_path": entry["heading_path"],
                "body": entry["body"],
                "score": row["score"],
                "breakdown": {
                    "emb": row.get("emb_score", 0.0),
                    "lex": row.get("lex_score", 0.0),
                },
            }
        )
    return out


def search(project_root: Path, category: str, query: str, mode: str, top_n: int, doc_type: str = "") -> Tuple[int, Dict]:
    """検索を実行し結果を返す。stdout には出力しない。

    Returns:
        Tuple[int, Dict]: (exit_code, result_dict)

    Raises:
        SearchError: バリデーションエラー等の回復可能なエラー
    """
    query_len = len(query.strip())
    if query_len < 1 or query_len > 1024:
        _error("query length must be 1..1024", "set --query to non-empty text up to 1024 chars")
    if top_n < 1 or top_n > 100:
        _error("top_n must be 1..100", "set --top-n 1..100")

    doc_types = _resolve_doc_types(category, doc_type, project_root)
    _validate_doc_type_values(project_root, category, doc_types)
    indexes = []
    for one_type in doc_types:
        index = _load_index_or_rebuild(project_root, category, one_type)
        if index.get("metadata", {}).get("model") not in ("", EMBEDDING_MODEL):
            _error("model_mismatch", "run build_index --full")
        if _is_stale(project_root, category, index, one_type):
            rc, _ = build_index.run_build(project_root, category, full=False, doc_type=one_type)
            if rc != 0:
                _error("auto_rebuild_failed", "run build_index manually")
            index = _load_index_or_rebuild(project_root, category, one_type)
        indexes.append(index)

    if any(i.get("metadata", {}).get("build_state") == "incomplete" for i in indexes):
        _event(
            "incomplete_detected",
            incomplete_count=sum(len(i.get("metadata", {}).get("failed_chunks", [])) for i in indexes),
        )

    entries_map = {}
    for index in indexes:
        entries_map.update(index.get("entries", {}))
    entries = list(entries_map.values())

    fallback_used = False
    rerank_error = None
    rerank_api_calls = 0
    rerank_token_usage = 0

    if mode == "lex":
        lex = lexical_search.score_chunks(query, entries)
        results = [
            {
                "path": x["path"],
                "heading_path": x["heading_path"],
                "body": x["body"],
                "score": x["lex_score"],
                "breakdown": {"emb": 0.0, "lex": x["lex_score"]},
            }
            for x in lex[:top_n]
        ]
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            _error("OPENAI_API_KEY not set", "export OPENAI_API_KEY=...")
        qvec = call_embedding_api_single(query, api_key)
        emb = []
        for key, entry in entries_map.items():
            emb_score = cosine_similarity(qvec, entry.get("embedding", []))
            emb.append({"chunk_id": key, "emb_score": emb_score, "score": emb_score})

        if mode == "emb":
            emb.sort(key=lambda x: (-x["emb_score"], x["chunk_id"]))
            ids = emb[:top_n]
            results = _make_results(entries, ids, "emb_score")
        else:
            lex = lexical_search.score_chunks(query, entries)
            lex_for_fuse = [
                {
                    "chunk_id": f"{x['path']}#{x['chunk_id']}",
                    "lex_score": x["lex_score"],
                }
                for x in lex
            ]
            fused = hybrid_score.combine_scores(emb, lex_for_fuse, method="rrf")
            emb_map = {row["chunk_id"]: row["emb_score"] for row in emb}
            lex_map = {row["chunk_id"]: row["lex_score"] for row in lex_for_fuse}
            ids = []
            for row in fused[: max(top_n, llm_rerank.MAX_CANDIDATES)]:
                row["emb_score"] = emb_map.get(row["chunk_id"], 0.0)
                row["lex_score"] = lex_map.get(row["chunk_id"], 0.0)
                ids.append(row)
            base_results = _make_results(entries, ids, "score")
            if mode == "hybrid":
                results = base_results[:top_n]
            else:
                candidates = []
                for row in ids:
                    entry = entries_map.get(row["chunk_id"])
                    if entry is None:
                        continue
                    candidates.append(
                        {
                            "chunk_id": row["chunk_id"],
                            "path": entry["path"],
                            "heading_path": entry["heading_path"],
                            "body": entry["body"],
                            "score": row["score"],
                            "emb_score": row["emb_score"],
                            "lex_score": row["lex_score"],
                        }
                    )
                reranked, rerank_meta = llm_rerank.rerank(query, candidates, api_key)
                fallback_used = rerank_meta["fallback_used"]
                rerank_error = rerank_meta["rerank_error"]
                rerank_api_calls = rerank_meta["api_calls"]
                rerank_token_usage = rerank_meta["token_usage"]
                if fallback_used:
                    _event(
                        "fallback_triggered",
                        reason=rerank_error,
                        candidate_count=rerank_meta.get("candidate_count", len(candidates)),
                    )
                results = [
                    {
                        "path": c["path"],
                        "heading_path": c["heading_path"],
                        "body": c["body"],
                        "score": c.get("rerank_score", c["score"]),
                        "breakdown": {
                            "emb": c["emb_score"],
                            "lex": c["lex_score"],
                            "rerank": c.get("rerank_score", c["score"]),
                        },
                    }
                    for c in reranked[:top_n]
                ]

    output = {
        "results": results,
        "fallback_used": fallback_used,
        "rerank_error": rerank_error,
        "api_calls": {
            "embedding": 1 if mode in ("emb", "hybrid", "rerank") else 0,
            "rerank": rerank_api_calls,
        },
        "token_usage": {"embedding": 0, "rerank": rerank_token_usage},
        "build_state": "incomplete"
        if any(i.get("metadata", {}).get("build_state") == "incomplete" for i in indexes)
        else "complete",
        "incomplete_count": sum(len(i.get("metadata", {}).get("failed_chunks", [])) for i in indexes),
    }
    return 0, output


def main():
    args = parse_args()
    try:
        rc, result = search(
            Path.cwd().resolve(),
            args.category,
            args.query,
            args.mode,
            args.top_n,
            doc_type=args.doc_type,
        )
    except SearchError as e:
        sys.stderr.write(json.dumps({"error": str(e), "hint": e.hint}) + "\n")
        return e.exit_code
    print(json.dumps(result, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
