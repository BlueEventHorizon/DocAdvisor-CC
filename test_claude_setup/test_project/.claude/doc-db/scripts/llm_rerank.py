#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM rerank for doc-db search results."""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

RERANK_MODEL = "gpt-4o-mini"
RERANK_URL = "https://api.openai.com/v1/chat/completions"
CONTEXT_WINDOW = 128000
INPUT_BUDGET_RATIO = 0.7
MIN_CANDIDATES = 5
MAX_CANDIDATES = 30
PREVIEW_TOKENS = 200
PROMPT_OVERHEAD_TOKENS = 800
OUTPUT_BUDGET_TOKENS = 1500


def _estimate_tokens(text: str) -> int:
    ascii_words = len(re.findall(r"[a-zA-Z0-9_]+", text))
    non_ascii_chars = sum(1 for c in text if ord(c) > 127)
    return max(1, ascii_words + max(1, non_ascii_chars // 2))


def _truncate_tokens(text: str, token_limit: int) -> str:
    tokens = re.findall(r"\S+", text)
    if len(tokens) <= token_limit:
        return text
    return " ".join(tokens[:token_limit])


def build_preview(candidate: Dict, max_tokens: int = PREVIEW_TOKENS) -> str:
    heading = " > ".join(candidate.get("heading_path", []))
    body = candidate.get("body", "")
    text = f"{heading}\n{body}".strip()
    return _truncate_tokens(text, max_tokens)


def choose_candidate_count(candidates: List[Dict]) -> int:
    if not candidates:
        return 0
    if len(candidates) <= MIN_CANDIDATES:
        return len(candidates)
    previews = [build_preview(c) for c in candidates[:MAX_CANDIDATES]]
    avg_tokens = max(1, int(sum(_estimate_tokens(p) for p in previews) / len(previews)))
    budget = int(CONTEXT_WINDOW * INPUT_BUDGET_RATIO) - PROMPT_OVERHEAD_TOKENS - OUTPUT_BUDGET_TOKENS
    max_by_budget = max(1, math.floor(budget / avg_tokens))
    count = min(len(candidates), MAX_CANDIDATES, max_by_budget)
    return max(MIN_CANDIDATES, count)


def _call_rerank_api(payload: Dict, api_key: str) -> Dict:
    req = urllib.request.Request(
        RERANK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def rerank(query: str, candidates: List[Dict], api_key: str) -> Tuple[List[Dict], Dict]:
    top_k = choose_candidate_count(candidates)
    selected = candidates[:top_k] if top_k > 0 else []
    if not selected:
        return [], {
            "fallback_used": False,
            "rerank_error": None,
            "api_calls": 0,
            "token_usage": 0,
            "candidate_count": 0,
        }

    payload_candidates = [
        {"id": c["chunk_id"], "preview": build_preview(c)} for c in selected
    ]
    payload = {
        "model": RERANK_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rerank candidates by relevance to the query. "
                    "Return JSON: {\"ranking\":[{\"id\":\"...\",\"score\":0..1}, ...]} "
                    "with all ids included exactly once."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"query": query, "candidates": payload_candidates},
                    ensure_ascii=False,
                ),
            },
        ],
    }

    try:
        result = _call_rerank_api(payload, api_key)
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        rank_rows = parsed.get("ranking", [])
        rank_map = {row["id"]: float(row.get("score", 0.0)) for row in rank_rows if "id" in row}

        default_sorted = sorted(selected, key=lambda x: (-x.get("score", 0.0), x["chunk_id"]))
        reranked = sorted(
            default_sorted,
            key=lambda x: (-rank_map.get(x["chunk_id"], -1.0), -x.get("score", 0.0), x["chunk_id"]),
        )
        for i, row in enumerate(reranked):
            row["rerank_score"] = rank_map.get(row["chunk_id"], max(0.0, 1.0 - i * 0.01))
        usage = result.get("usage", {})
        token_usage = int(usage.get("total_tokens", 0))
        return reranked, {
            "fallback_used": False,
            "rerank_error": None,
            "api_calls": 1,
            "token_usage": token_usage,
            "candidate_count": top_k,
        }
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
        RuntimeError,
    ):
        fallback = sorted(selected, key=lambda x: (-x.get("score", 0.0), x["chunk_id"]))
        for row in fallback:
            row["rerank_score"] = row.get("score", 0.0)
        return fallback, {
            "fallback_used": True,
            "rerank_error": "rerank_api_error",
            "api_calls": 1,
            "token_usage": 0,
            "candidate_count": top_k,
        }
