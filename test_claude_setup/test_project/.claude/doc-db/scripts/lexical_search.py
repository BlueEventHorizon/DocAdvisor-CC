#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lexical 検索（語彙一致 + ID 完全一致ブースト）。"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

ID_RE = re.compile(r"[A-Z]+-\d+")
TOKEN_RE = re.compile(r"[A-Za-z]+-\d+|[A-Za-z0-9_]+|[^\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(normalize_text(text)) if t]


def score_chunks(query: str, chunks: List[Dict]) -> List[Dict]:
    query_norm = normalize_text(query)
    query_tokens = tokenize(query_norm)
    id_tokens = [t.lower() for t in ID_RE.findall(unicodedata.normalize("NFKC", query).upper())]
    results: List[Dict] = []

    for chunk in chunks:
        body = normalize_text(chunk.get("body", ""))
        score = 0.0

        for token in query_tokens:
            if not token:
                continue
            score += body.count(token)

        for id_token in id_tokens:
            if id_token in body:
                score += 10.0

        if query_norm.strip() and query_norm in body:
            score += 2.0

        if score > 0:
            results.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "path": chunk.get("path", ""),
                    "heading_path": chunk.get("heading_path", []),
                    "lex_score": float(score),
                    "body": chunk.get("body", ""),
                }
            )

    results.sort(key=lambda x: (-x["lex_score"], x["chunk_id"]))
    return results
