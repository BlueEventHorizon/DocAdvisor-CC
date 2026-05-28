import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import hybrid_score


class HybridScoreTests(unittest.TestCase):
    def test_rrf_is_deterministic(self):
        emb = [{"chunk_id": "a", "emb_score": 0.9}, {"chunk_id": "b", "emb_score": 0.8}]
        lex = [{"chunk_id": "b", "lex_score": 5.0}, {"chunk_id": "a", "lex_score": 2.0}]
        r1 = hybrid_score.rrf_fuse(emb, lex, k=60)
        r2 = hybrid_score.rrf_fuse(emb, lex, k=60)
        self.assertEqual(r1, r2)

    def test_linear_alpha_boundaries(self):
        emb = [{"chunk_id": "a", "emb_score": 0.9}]
        lex = [{"chunk_id": "a", "lex_score": 0.1}]
        only_lex = hybrid_score.linear_fuse(emb, lex, alpha=0.0)[0]["score"]
        only_emb = hybrid_score.linear_fuse(emb, lex, alpha=1.0)[0]["score"]
        self.assertEqual(only_lex, 0.1)
        self.assertEqual(only_emb, 0.9)

    def test_empty_input(self):
        self.assertEqual(hybrid_score.combine_scores([], [], method="rrf"), [])
        self.assertEqual(hybrid_score.combine_scores([], [], method="linear"), [])

    # 施策3: emb-only フォールバックテスト
    def test_emb_fallback_when_lex_ratio_low(self):
        """lex ヒット率が EMB_FALLBACK_LEX_RATIO 未満の場合、emb スコア順でフォールバックする"""
        # emb 100 件に対して lex ヒット 4 件 → lex_ratio = 0.04 < 0.05
        emb = [{"chunk_id": str(i), "emb_score": 1.0 - i * 0.01} for i in range(100)]
        lex = [{"chunk_id": str(i), "lex_score": float(i)} for i in range(4)]
        result = hybrid_score.rrf_fuse(emb, lex, k=60)
        # フォールバック時は emb スコア降順になる
        scores = [r["score"] for r in result[:5]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # rank 1 は emb スコア最高の chunk_id="0"
        self.assertEqual(result[0]["chunk_id"], "0")

    def test_rrf_used_when_lex_ratio_sufficient(self):
        """lex ヒット率が EMB_FALLBACK_LEX_RATIO 以上なら通常 RRF を使用する"""
        # emb 10 件に対して lex 1 件 → lex_ratio = 0.1 >= 0.05 → RRF
        emb = [{"chunk_id": str(i), "emb_score": 1.0 - i * 0.1} for i in range(10)]
        lex = [{"chunk_id": "9", "lex_score": 100.0}]  # lex 最高スコアは emb 最低スコアのチャンク
        result = hybrid_score.rrf_fuse(emb, lex, k=60)
        # RRF なら chunk "9" が上位に来る（lex ブーストがかかるため）
        top_ids = [r["chunk_id"] for r in result[:3]]
        self.assertIn("9", top_ids)

    def test_emb_guarantee_k_in_top_k(self):
        """emb 上位 K 件は lex=0 でも fused 上位 K 件に含まれる"""
        # emb 上位: a(0.9), b(0.8) — どちらも lex=0
        # lex 上位: c,d,e,f,g — emb では下位
        emb = [{"chunk_id": c, "emb_score": s} for c, s in [
            ("a", 0.9), ("b", 0.8), ("c", 0.4), ("d", 0.35), ("e", 0.3), ("f", 0.25), ("g", 0.2)
        ]]
        lex = [{"chunk_id": c, "lex_score": s} for c, s in [
            ("c", 10.0), ("d", 9.0), ("e", 8.0), ("f", 7.0), ("g", 6.0)
        ]]
        result = hybrid_score.rrf_fuse(emb, lex, k=60)
        top_k_ids = {r["chunk_id"] for r in result[:hybrid_score.EMB_GUARANTEE_K]}
        self.assertIn("a", top_k_ids)
        self.assertIn("b", top_k_ids)

    def test_emb_guarantee_preserves_emb_rank_order(self):
        """昇格した emb 上位 K 件は top-K 内で emb ランク順（best が second より前）を保つ"""
        emb = [{"chunk_id": c, "emb_score": s} for c, s in [
            ("best", 0.95), ("second", 0.85), ("c", 0.1), ("d", 0.1), ("e", 0.1), ("f", 0.1), ("g", 0.1)
        ]]
        lex = [{"chunk_id": c, "lex_score": s} for c, s in [
            ("c", 10.0), ("d", 9.0), ("e", 8.0), ("f", 7.0), ("g", 6.0)
        ]]
        result = hybrid_score.rrf_fuse(emb, lex, k=60)
        top_k_ids = [r["chunk_id"] for r in result[:hybrid_score.EMB_GUARANTEE_K]]
        # best と second が top-K に含まれる
        self.assertIn("best", top_k_ids)
        self.assertIn("second", top_k_ids)
        # best が second より前の位置にある（emb ランク順が保持される）
        self.assertLess(top_k_ids.index("best"), top_k_ids.index("second"))

    def test_emb_guarantee_no_effect_when_already_in_top_k(self):
        """emb 上位 K 件がすでに fused 上位 K 件に含まれる場合はスコアを変えない"""
        emb = [{"chunk_id": "a", "emb_score": 0.9}, {"chunk_id": "b", "emb_score": 0.8}]
        lex = [{"chunk_id": "a", "lex_score": 5.0}, {"chunk_id": "b", "lex_score": 4.0}]
        result_normal = hybrid_score.rrf_fuse(emb, lex, k=60)
        # a, b は RRF でも上位 → 昇格不要
        self.assertEqual(result_normal[0]["chunk_id"], "a")
        self.assertEqual(result_normal[1]["chunk_id"], "b")

    def test_emb_fallback_with_zero_lex(self):
        """lex ヒットが 0 件の場合も emb only フォールバックが動作する"""
        emb = [{"chunk_id": "a", "emb_score": 0.9}, {"chunk_id": "b", "emb_score": 0.5}]
        result = hybrid_score.rrf_fuse(emb, [], k=60)
        self.assertEqual(result[0]["chunk_id"], "a")
        self.assertEqual(result[1]["chunk_id"], "b")


if __name__ == "__main__":
    unittest.main()
