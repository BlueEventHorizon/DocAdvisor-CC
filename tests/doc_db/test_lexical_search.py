import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import lexical_search


class LexicalSearchTests(unittest.TestCase):
    def test_id_exact_match_boost(self):
        chunks = [
            {"chunk_id": "a", "body": "this has fnc-006 only once"},
            {"chunk_id": "b", "body": "natural language query text repeated repeated"},
        ]
        results = lexical_search.score_chunks("FNC-006", chunks)
        self.assertEqual(results[0]["chunk_id"], "a")

    def test_nfkc_normalization(self):
        chunks = [{"chunk_id": "a", "body": "ＡＢＣ１２３"}]
        results = lexical_search.score_chunks("abc123", chunks)
        self.assertEqual(results[0]["chunk_id"], "a")

    def test_tokenize_splits_cjk_and_ascii(self):
        """日本語と ASCII の境界でトークン分割される"""
        tokens = lexical_search.tokenize("のコンテキスト外検索と3モード検索方式")
        self.assertIn("3", tokens)
        self.assertNotIn("のコンテキスト外検索と3モード検索方式", tokens)

    def test_tokenize_splits_cjk_and_latin(self):
        """日本語の直後に ASCII が続く場合に分割される"""
        tokens = lexical_search.tokenize("見落としゼロの検索精度要件とGolden Set")
        self.assertIn("golden", tokens)
        self.assertIn("set", tokens)
        self.assertNotIn("見落としゼロの検索精度要件とgolden", tokens)

    def test_tokenize_digits_separate(self):
        """数字が独立したトークンになる"""
        tokens = lexical_search.tokenize("3モード検索方式")
        self.assertIn("3", tokens)

    def test_cjk_keyword_matches_in_body(self):
        """クエリの重要語が body 内に存在すれば BM25 スコアが付く"""
        chunks = [
            {"chunk_id": "target", "body": "3 モード検索方式が使用される"},
            {"chunk_id": "other",  "body": "関係ない文書"},
        ]
        results = lexical_search.score_chunks("doc-advisor のコンテキスト外検索と3モード検索方式", chunks)
        chunk_ids = [r["chunk_id"] for r in results]
        self.assertIn("target", chunk_ids)
        target_score = next(r["lex_score"] for r in results if r["chunk_id"] == "target")
        self.assertGreater(target_score, 0)

    def test_bm25_rare_token_outranks_common_token(self):
        """希少トークンにマッチした文書が、一般的なトークンだけにマッチした文書より上位になる"""
        # "special" は 1/6 の chunk のみ → IDF 高い
        # "common" は 5/6 の chunk に出現 → IDF 低い
        chunks = [
            {"chunk_id": "target", "body": "special content only here"},
            {"chunk_id": "c1", "body": "common content document one"},
            {"chunk_id": "c2", "body": "common content document two"},
            {"chunk_id": "c3", "body": "common content document three"},
            {"chunk_id": "c4", "body": "common content document four"},
            {"chunk_id": "c5", "body": "common content document five"},
        ]
        results = lexical_search.score_chunks("common special", chunks)
        self.assertEqual(results[0]["chunk_id"], "target")


if __name__ == "__main__":
    unittest.main()
