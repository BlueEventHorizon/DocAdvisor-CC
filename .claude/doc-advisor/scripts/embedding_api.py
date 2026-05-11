#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embedding API 共通モジュール (doc-advisor plugin)

OpenAI Embedding API の定数と呼び出し関数を一元管理する。
embed_docs.py（インデックス構築）と search_docs.py（検索）の両方から使用。

標準ライブラリのみ使用。
"""

import json
import sys
import time
import urllib.error
import urllib.request

EMBEDDING_MODEL = "text-embedding-3-small"

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

EMBEDDING_BATCH_SIZE = 100

# リトライ回数（初回 + リトライ n 回 = 最大 n+1 回試行）
API_MAX_RETRIES = 1

# 429 の Retry-After ヘッダーがない場合のデフォルト待機秒数
RATE_LIMIT_WAIT_SECONDS = 60

# 5xx / ネットワークエラー時のリトライ前待機秒数
RETRY_WAIT_SECONDS = 2


def _log(*args, **kwargs):
    """stderr にログメッセージを出力する。"""
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


def call_embedding_api(texts, api_key):
    """OpenAI Embedding API をバッチ呼び出しする。

    Args:
        texts: Embedding するテキストリスト (list[str])
        api_key: OpenAI API キー

    Returns:
        list[list[float]]: テキストに対応する Embedding ベクトルのリスト

    Raises:
        RuntimeError: API 呼び出し失敗（リトライ後も失敗）
    """
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": texts,
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENAI_EMBEDDINGS_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    last_error = None
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                embeddings = sorted(result["data"], key=lambda x: x["index"])
                return [e["embedding"] for e in embeddings]

        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < API_MAX_RETRIES:
                    # Retry-After ヘッダーがあればその値を優先する
                    retry_after = RATE_LIMIT_WAIT_SECONDS
                    if e.headers and e.headers.get("Retry-After"):
                        try:
                            retry_after = int(e.headers["Retry-After"])
                        except ValueError:
                            pass
                    _log(f"  レート制限 (429)。{retry_after}秒待機してリトライします...")
                    time.sleep(retry_after)
                    last_error = e
                    continue
                last_error = e
            elif e.code == 401:
                raise RuntimeError(
                    "API 認証エラー (401)。OPENAI_API_KEY が正しいか確認してください。"
                ) from e
            else:
                if attempt < API_MAX_RETRIES:
                    _log(f"  API エラー ({e.code})。{RETRY_WAIT_SECONDS}秒後にリトライします...")
                    time.sleep(RETRY_WAIT_SECONDS)
                    last_error = e
                    continue
                last_error = e

        except urllib.error.URLError as e:
            if attempt < API_MAX_RETRIES:
                _log(f"  ネットワークエラー。{RETRY_WAIT_SECONDS}秒後にリトライします: {e}")
                time.sleep(RETRY_WAIT_SECONDS)
                last_error = e
                continue
            last_error = e

    raise RuntimeError(f"API 呼び出し失敗: {last_error}") from last_error


def call_embedding_api_single(text, api_key):
    """単一テキスト用の Embedding API ラッパー。

    Args:
        text: Embedding するテキスト (str)
        api_key: OpenAI API キー

    Returns:
        list[float]: Embedding ベクトル

    Raises:
        RuntimeError: API 呼び出し失敗
    """
    return call_embedding_api([text], api_key)[0]
