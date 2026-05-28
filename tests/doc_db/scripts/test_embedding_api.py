#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embedding_api.py（doc-db 版）のユニットテスト。

doc-advisor 版テスト（tests/doc_advisor/scripts/test_embedding_api.py）から
以下を変更:
- SCRIPTS_DIR を plugins/doc-db/scripts に切替
- FIXED_VECTOR を 3072 次元に変更（text-embedding-3-large）
- EMBEDDING_MODEL = "text-embedding-3-large" の明示確認テストを追加
- import を importlib.util.spec_from_file_location 経由に変更し、モジュール名を
  'doc_db_embedding_api' で一意化（doc-advisor 側 'embedding_api' との sys.modules
  衝突を回避し、`python3 -m unittest discover -s tests` のような全体実行でも安定動作）

検証範囲:
- EMBEDDING_MODEL 定数の値（DES-026 §6.7）
- call_embedding_api: バッチ呼び出し（1件・複数件）、3072 次元動作
- 401 認証エラー → RuntimeError
- 429 レート制限のリトライ・Retry-After 尊重
- 5xx サーバーエラーのリトライ
- ネットワークエラーのリトライ
- 1回目失敗・2回目成功のシナリオ
- call_embedding_api_single ラッパー
"""

import importlib.util
import json
import os
import sys
import unittest
import warnings
from unittest.mock import MagicMock, patch

# urllib.error.HTTPError を side_effect に積むテストでは、HTTPError 内部の
# 一時ファイルが GC されたタイミングで Python 3.14 が ResourceWarning を発する
# （tempfile._TemporaryFileCloser.__del__）。この警告が他テスト中の差し替え
# 後 sys.stderr（io.StringIO 等）に書き込まれて先頭行 assert を壊す事故を
# 招くため、本モジュール内では ResourceWarning を抑制する。テスト対象の
# 正常動作検証には影響しない（unittest が default に戻すケースに備え、
# TestCase.setUp でも再設定する）。
warnings.filterwarnings("ignore", category=ResourceWarning)

# テスト対象モジュールの import パス（plugins/doc-db/scripts）
# importlib.util.spec_from_file_location で一意名 'doc_db_embedding_api' として
# ロードし、doc-advisor 側テストの 'embedding_api' とのモジュール名衝突を回避する
# （`python3 -m unittest discover -s tests` のような全体実行で sys.modules の先勝ち
# 固定により別 plugin の実装を参照する事故を防ぐ）。
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-db', 'scripts'
))
_MODULE_PATH = os.path.join(SCRIPTS_DIR, "embedding_api.py")
_spec = importlib.util.spec_from_file_location("doc_db_embedding_api", _MODULE_PATH)
embedding_api = importlib.util.module_from_spec(_spec)
sys.modules["doc_db_embedding_api"] = embedding_api
_spec.loader.exec_module(embedding_api)

API_MAX_RETRIES = embedding_api.API_MAX_RETRIES
EMBEDDING_MODEL = embedding_api.EMBEDDING_MODEL
OPENAI_EMBEDDINGS_URL = embedding_api.OPENAI_EMBEDDINGS_URL
RATE_LIMIT_WAIT_SECONDS = embedding_api.RATE_LIMIT_WAIT_SECONDS
call_embedding_api = embedding_api.call_embedding_api
call_embedding_api_single = embedding_api.call_embedding_api_single

# text-embedding-3-large は 3072 次元
FIXED_VECTOR = [1.0] + [0.0] * 3071
FIXED_VECTOR_2 = [0.0] + [1.0] + [0.0] * 3070


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


class _SuppressResourceWarningMixin:
    """各テスト実行時に ResourceWarning を抑制するための Mixin。

    unittest は実行時に warnings filter を 'default' に再設定するため、モジュール
    冒頭の filter だけでは効かない。setUp 内で再適用する必要がある。
    """

    def setUp(self):
        warnings.filterwarnings("ignore", category=ResourceWarning)
        super().setUp()


class TestEmbeddingModelConstant(unittest.TestCase):
    """EMBEDDING_MODEL 定数のテスト（DES-026 §6.7 を担保）。"""

    def test_model_is_text_embedding_3_large(self):
        """doc-db 側は text-embedding-3-large を使用する。"""
        self.assertEqual(EMBEDDING_MODEL, "text-embedding-3-large")

    def test_module_constant_matches(self):
        """モジュール経由でアクセスした値も一致する。"""
        self.assertEqual(embedding_api.EMBEDDING_MODEL, "text-embedding-3-large")


class TestCallEmbeddingApi(_SuppressResourceWarningMixin, unittest.TestCase):
    """call_embedding_api のバッチ呼び出しテスト（3072 次元）。"""

    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_single_text_3072_dim(self, mock_urlopen):
        """単一テキストで 3072 次元のベクトルが返る。"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )

        result = call_embedding_api(["テストテキスト"], "fake-api-key")

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 3072)
        self.assertEqual(result[0][0], 1.0)

    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_batch_texts_3072_dim(self, mock_urlopen):
        """バッチテキスト（複数）で各 3072 次元のベクトルが返る。"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR, FIXED_VECTOR_2])
        )

        result = call_embedding_api(["テキスト1", "テキスト2"], "fake-api-key")

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), 3072)
        self.assertEqual(len(result[1]), 3072)
        self.assertEqual(result[0][0], 1.0)
        self.assertEqual(result[1][1], 1.0)

    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_request_payload_uses_large_model(self, mock_urlopen):
        """送信ペイロードに model="text-embedding-3-large" が含まれる。"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )
        call_embedding_api(["テスト"], "fake-key")
        # urllib.request.Request が data=... で渡された内容を検証
        called_args, _ = mock_urlopen.call_args
        request_obj = called_args[0]
        sent_payload = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(sent_payload["model"], "text-embedding-3-large")

    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_api_auth_error_raises(self, mock_urlopen):
        """401 エラーで RuntimeError を発生させる。"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=OPENAI_EMBEDDINGS_URL,
            code=401, msg="Unauthorized", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError) as ctx:
            call_embedding_api(["テスト"], "invalid-key")
        self.assertIn("認証エラー", str(ctx.exception))

    @patch("doc_db_embedding_api.time.sleep")
    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_network_error_retries_then_raises(self, mock_urlopen, mock_sleep):
        """ネットワークエラーでリトライ後に RuntimeError を発生させる。"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            call_embedding_api(["テスト"], "fake-key")
        self.assertIn("API 呼び出し失敗", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)
        self.assertEqual(mock_sleep.call_count, API_MAX_RETRIES)

    @patch("doc_db_embedding_api.time.sleep")
    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_rate_limit_retries(self, mock_urlopen, mock_sleep):
        """429 レート制限でリトライする。"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=OPENAI_EMBEDDINGS_URL,
            code=429, msg="Too Many Requests", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)
        self.assertEqual(mock_sleep.call_count, API_MAX_RETRIES)
        mock_sleep.assert_called_with(RATE_LIMIT_WAIT_SECONDS)

    @patch("doc_db_embedding_api.time.sleep")
    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_rate_limit_respects_retry_after_header(self, mock_urlopen, mock_sleep):
        """429 レスポンスの Retry-After ヘッダーが指定する秒数を待機する。"""
        import http.client
        import urllib.error
        headers = http.client.HTTPMessage()
        headers["Retry-After"] = "30"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=OPENAI_EMBEDDINGS_URL,
            code=429, msg="Too Many Requests", hdrs=headers, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        mock_sleep.assert_called_with(30)

    @patch("doc_db_embedding_api.time.sleep")
    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_server_error_retries(self, mock_urlopen, mock_sleep):
        """500 等のサーバーエラーでリトライ後に RuntimeError を発生させる。"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=OPENAI_EMBEDDINGS_URL,
            code=500, msg="Internal Server Error", hdrs={}, fp=None,
        )
        with self.assertRaises(RuntimeError):
            call_embedding_api(["テスト"], "fake-key")
        self.assertEqual(mock_urlopen.call_count, API_MAX_RETRIES + 1)

    @patch("doc_db_embedding_api.time.sleep")
    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_retry_succeeds_on_second_attempt(self, mock_urlopen, mock_sleep):
        """1回目失敗・2回目成功のリトライシナリオ。"""
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


class TestCallEmbeddingApiSingle(_SuppressResourceWarningMixin, unittest.TestCase):
    """call_embedding_api_single のラッパーテスト。"""

    @patch("doc_db_embedding_api.urllib.request.urlopen")
    def test_returns_single_vector_3072_dim(self, mock_urlopen):
        """単一ベクトルが返る（3072 次元）。"""
        mock_urlopen.return_value = _mock_urlopen_response(
            _make_api_response([FIXED_VECTOR])
        )

        result = call_embedding_api_single("テスト", "fake-api-key")

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3072)
        self.assertEqual(result[0], 1.0)

    @patch("doc_db_embedding_api.call_embedding_api")
    def test_delegates_to_batch(self, mock_batch):
        """内部で call_embedding_api([text], ...) に委譲される。"""
        mock_batch.return_value = [FIXED_VECTOR]

        call_embedding_api_single("テスト", "fake-key")

        mock_batch.assert_called_once_with(["テスト"], "fake-key")


class TestGetApiKey(unittest.TestCase):
    """get_api_key のフォールバック動作テスト。"""

    def setUp(self):
        self._saved = {
            k: os.environ.pop(k, None)
            for k in ("OPENAI_API_DOCDB_KEY", "OPENAI_API_KEY")
        }

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_docdb_key_takes_priority(self):
        """OPENAI_API_DOCDB_KEY が設定されていればそれを返す。"""
        os.environ["OPENAI_API_DOCDB_KEY"] = "docdb-key"
        os.environ["OPENAI_API_KEY"] = "fallback-key"
        self.assertEqual(embedding_api.get_api_key(), "docdb-key")

    def test_fallback_to_openai_api_key(self):
        """OPENAI_API_DOCDB_KEY 未設定時は OPENAI_API_KEY にフォールバックする。"""
        os.environ["OPENAI_API_KEY"] = "fallback-key"
        self.assertEqual(embedding_api.get_api_key(), "fallback-key")

    def test_empty_string_when_both_missing(self):
        """両方未設定のときは空文字列を返す。"""
        self.assertEqual(embedding_api.get_api_key(), "")


if __name__ == '__main__':
    unittest.main()
