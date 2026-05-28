#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embedding_api.py のユニットテスト。

テスト対象:
- call_embedding_api() のバッチ呼び出し（単一・複数テキスト）
- call_embedding_api_single() の単一テキストラッパー
- 401 認証エラー
- 429 レート制限リトライ
- ネットワークエラーリトライ
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import embedding_api
from embedding_api import (
    API_MAX_RETRIES,
    RATE_LIMIT_WAIT_SECONDS,
    call_embedding_api,
    call_embedding_api_single,
)

FIXED_VECTOR = [1.0] + [0.0] * 1535
FIXED_VECTOR_2 = [0.0] + [1.0] + [0.0] * 1534


def _make_api_response(vectors):
    """OpenAI Embedding API のレスポンス JSON バイト列を生成する。"""
    data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    return json.dumps({"data": data}).encode("utf-8")


def _mock_urlopen_response(response_bytes):
    """urllib.request.urlopen のモックレスポンスを生成する。"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = response_bytes
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestCallEmbeddingApi(unittest.TestCase):
    """call_embedding_api() のバッチ呼び出しテスト。"""

    @patch("embedding_api.urllib.request.urlopen")
    def test_single_text(self, mock_urlopen):
        """単一テキストの Embedding 取得"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )

        result = call_embedding_api(["テストテキスト"], "fake-api-key")

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1536)
        self.assertEqual(result[0][0], 1.0)

    @patch("embedding_api.urllib.request.urlopen")
    def test_batch_texts(self, mock_urlopen):
        """バッチテキスト（複数テキスト）の Embedding 取得"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR, FIXED_VECTOR_2])
        )

        result = call_embedding_api(["テキスト1", "テキスト2"], "fake-api-key")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 1.0)
        self.assertEqual(result[1][1], 1.0)

    @patch("embedding_api.urllib.request.urlopen")
    def test_api_auth_error_raises(self, mock_urlopen):
        """401 エラーで RuntimeError を発生させる"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.openai.com/v1/embeddings",
            code=401, msg="Unauthorized", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError) as ctx:
            call_embedding_api(["テスト"], "invalid-key")
        self.assertIn("認証エラー", str(ctx.exception))

    @patch("embedding_api.time.sleep")
    @patch("embedding_api.urllib.request.urlopen")
    def test_network_error_retries_then_raises(self, mock_urlopen, mock_sleep):
        """ネットワークエラーでリトライ後に RuntimeError を発生させる"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            call_embedding_api(["テスト"], "fake-key")
        self.assertIn("API 呼び出し失敗", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)
        self.assertEqual(mock_sleep.call_count, API_MAX_RETRIES)

    @patch("embedding_api.time.sleep")
    @patch("embedding_api.urllib.request.urlopen")
    def test_rate_limit_retries(self, mock_urlopen, mock_sleep):
        """429 レート制限でリトライする"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.openai.com/v1/embeddings",
            code=429, msg="Too Many Requests", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)
        self.assertEqual(mock_sleep.call_count, API_MAX_RETRIES)
        # デフォルト待機時間で sleep が呼ばれることを確認
        mock_sleep.assert_called_with(RATE_LIMIT_WAIT_SECONDS)

    @patch("embedding_api.time.sleep")
    @patch("embedding_api.urllib.request.urlopen")
    def test_rate_limit_respects_retry_after_header(self, mock_urlopen, mock_sleep):
        """429 レスポンスの Retry-After ヘッダーが指定する秒数を待機する"""
        import http.client
        import urllib.error
        headers = http.client.HTTPMessage()
        headers["Retry-After"] = "30"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.openai.com/v1/embeddings",
            code=429, msg="Too Many Requests", hdrs=headers, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        mock_sleep.assert_called_with(30)

    @patch("embedding_api.time.sleep")
    @patch("embedding_api.urllib.request.urlopen")
    def test_server_error_retries(self, mock_urlopen, mock_sleep):
        """500 等のサーバーエラーでリトライ後に RuntimeError を発生させる"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.openai.com/v1/embeddings",
            code=500, msg="Internal Server Error", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)

    @patch("embedding_api.time.sleep")
    @patch("embedding_api.urllib.request.urlopen")
    def test_retry_succeeds_on_second_attempt(self, mock_urlopen, mock_sleep):
        """1回目失敗・2回目成功のリトライシナリオ"""
        import urllib.error
        success_response = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )
        mock_urlopen.side_effect = [
            urllib.error.URLError("Connection refused"),
            success_response,
        ]

        result = call_embedding_api(["テスト"], "fake-key")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], FIXED_VECTOR)
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)


class TestCallEmbeddingApiSingle(unittest.TestCase):
    """call_embedding_api_single() のラッパーテスト。"""

    @patch("embedding_api.urllib.request.urlopen")
    def test_returns_single_vector(self, mock_urlopen):
        """単一ベクトルが返される（リストではなく）"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )

        result = call_embedding_api_single("テスト", "fake-api-key")

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1536)
        self.assertEqual(result[0], 1.0)

    @patch("embedding_api.call_embedding_api")
    def test_delegates_to_batch(self, mock_batch):
        """内部で call_embedding_api([text], ...) に委譲される"""
        mock_batch.return_value = [FIXED_VECTOR]

        call_embedding_api_single("テスト", "fake-key")

        mock_batch.assert_called_once_with(["テスト"], "fake-key")


class TestGetApiKey(unittest.TestCase):
    """get_api_key() のフォールバック動作テスト（DES-028 §7.1 / TST-01）。

    検証ケース:
    - (a) OPENAI_API_DOCDB_KEY のみ設定 → DOCDB の値が返る
    - (b) OPENAI_API_KEY のみ設定 → 標準の値が返る
    - (c) 両方設定 → DOCDB の値が返る（フォールバックは使われない）
    - (d) 両方未設定 → 空文字列が返る
    """

    def test_returns_docdb_key_when_only_docdb_set(self):
        """(a) OPENAI_API_DOCDB_KEY のみ設定 → DOCDB の値が返る。"""
        with patch.dict(os.environ, {"OPENAI_API_DOCDB_KEY": "docdb-key"}, clear=True):
            self.assertEqual(embedding_api.get_api_key(), "docdb-key")

    def test_returns_standard_key_when_only_standard_set(self):
        """(b) OPENAI_API_KEY のみ設定 → 標準の値が返る（フォールバック）。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "standard-key"}, clear=True):
            self.assertEqual(embedding_api.get_api_key(), "standard-key")

    def test_returns_docdb_key_when_both_set(self):
        """(c) 両方設定 → DOCDB の値が返る（フォールバックは使われない）。"""
        with patch.dict(
            os.environ,
            {"OPENAI_API_DOCDB_KEY": "docdb-key", "OPENAI_API_KEY": "standard-key"},
            clear=True,
        ):
            self.assertEqual(embedding_api.get_api_key(), "docdb-key")

    def test_returns_empty_string_when_neither_set(self):
        """(d) 両方未設定 → 空文字列が返る。"""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(embedding_api.get_api_key(), "")


if __name__ == '__main__':
    unittest.main()
