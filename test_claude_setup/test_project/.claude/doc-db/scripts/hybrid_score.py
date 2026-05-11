#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Embedding / Lexical スコア統合。"""

from __future__ import annotations

from typing import Dict, List


def _to_rank_map(items: List[Dict], score_key: str) -> Dict[str, int]:
    ordered = sorted(items, key=lambda x: (-float(x.get(score_key, 0.0)), x["chunk_id"]))
    return {item["chunk_id"]: rank + 1 for rank, item in enumerate(ordered)}


def _to_score_map(items: List[Dict], score_key: str) -> Dict[str, float]:
    return {item["chunk_id"]: float(item.get(score_key, 0.0)) for item in items}


def rrf_fuse(emb_items: List[Dict], lex_items: List[Dict], k: int = 60) -> List[Dict]:
    emb_rank = _to_rank_map(emb_items, "emb_score")
    lex_rank = _to_rank_map(lex_items, "lex_score")
    all_ids = set(emb_rank.keys()) | set(lex_rank.keys())
    fused: List[Dict] = []
    for chunk_id in all_ids:
        score = 0.0
        if chunk_id in emb_rank:
            score += 1.0 / (k + emb_rank[chunk_id])
        if chunk_id in lex_rank:
            score += 1.0 / (k + lex_rank[chunk_id])
        fused.append({"chunk_id": chunk_id, "score": score})
    fused.sort(key=lambda x: (-x["score"], x["chunk_id"]))
    return fused


def linear_fuse(emb_items: List[Dict], lex_items: List[Dict], alpha: float = 0.7) -> List[Dict]:
    emb_scores = _to_score_map(emb_items, "emb_score")
    lex_scores = _to_score_map(lex_items, "lex_score")
    all_ids = set(emb_scores.keys()) | set(lex_scores.keys())
    merged: List[Dict] = []
    for chunk_id in all_ids:
        emb = emb_scores.get(chunk_id, 0.0)
        lex = lex_scores.get(chunk_id, 0.0)
        merged.append(
            {
                "chunk_id": chunk_id,
                "score": alpha * emb + (1.0 - alpha) * lex,
                "breakdown": {"emb": emb, "lex": lex},
            }
        )
    merged.sort(key=lambda x: (-x["score"], x["chunk_id"]))
    return merged


def combine_scores(
    emb_items: List[Dict],
    lex_items: List[Dict],
    method: str = "rrf",
    alpha: float = 0.7,
    k: int = 60,
) -> List[Dict]:
    if method == "linear":
        return linear_fuse(emb_items, lex_items, alpha=alpha)
    return rrf_fuse(emb_items, lex_items, k=k)
