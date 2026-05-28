import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import llm_rerank


class LlmRerankTests(unittest.TestCase):
    def test_preview_truncation(self):
        candidate = {
            "heading_path": ["H1", "H2"],
            "body": " ".join(f"w{i}" for i in range(400)),
        }
        preview = llm_rerank.build_preview(candidate, max_tokens=200)
        self.assertLessEqual(len(preview.split()), 200)

    def test_token_budget_shrinks_candidates(self):
        candidates = [
            {
                "chunk_id": f"c{i}",
                "heading_path": ["H"],
                "body": " ".join("x" for _ in range(3000)),
                "score": 1.0,
            }
            for i in range(50)
        ]
        count = llm_rerank.choose_candidate_count(candidates)
        self.assertGreaterEqual(count, 5)
        self.assertLessEqual(count, 30)

    def test_fallback_on_api_error(self):
        old_call = llm_rerank._call_rerank_api
        llm_rerank._call_rerank_api = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            candidates = [
                {"chunk_id": "a", "heading_path": ["H"], "body": "aa", "score": 0.9},
                {"chunk_id": "b", "heading_path": ["H"], "body": "bb", "score": 0.8},
            ]
            reranked, meta = llm_rerank.rerank("query", candidates, "dummy")
            self.assertTrue(meta["fallback_used"])
            self.assertEqual(meta["rerank_error"], "rerank_api_error")
            self.assertEqual(reranked[0]["chunk_id"], "a")
        finally:
            llm_rerank._call_rerank_api = old_call


if __name__ == "__main__":
    unittest.main()
