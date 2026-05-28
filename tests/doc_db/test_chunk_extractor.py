import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import chunk_extractor


class ChunkExtractorTests(unittest.TestCase):
    def test_heading_hierarchy_and_ranges(self):
        text = "# A\nintro\n## B\nbody\n### C\nmore\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text)
        self.assertEqual(chunks[0]["heading_path"], ["A"])
        self.assertEqual(chunks[1]["heading_path"], ["A", "B"])
        self.assertEqual(chunks[2]["heading_path"], ["A", "B", "C"])
        for chunk in chunks:
            start, end = chunk["char_range"]
            self.assertEqual(text[start:end], chunk["body"])

    def test_no_heading_single_chunk(self):
        text = "plain\ncontent\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["heading_path"], [])
        self.assertEqual(chunks[0]["body"], text)

    def test_split_large_chunk(self):
        text = "# A\n" + ("x" * 30) + "\n\n" + ("y" * 30)
        chunks = chunk_extractor.extract_chunks("docs/a.md", text, max_chunk_chars=40)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(c["body"]) <= 40 for c in chunks))

    # 施策4: min_chunk_level テスト
    def test_min_chunk_level_1_collapses_to_h1(self):
        """min_chunk_level=1 では h1 のみがチャンク境界となり h2/h3 が同一チャンクに含まれる"""
        text = "# A\nintro\n## B\nbody\n### C\nmore\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text, min_chunk_level=1)
        # h1 のみが境界 → 1チャンクのみ
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["heading_path"], ["A"])
        # h2 以下のテキストも含まれる
        self.assertIn("body", chunks[0]["body"])
        self.assertIn("more", chunks[0]["body"])

    def test_min_chunk_level_2_collapses_h3(self):
        """min_chunk_level=2 では h1/h2 が境界となり h3 以下が h2 チャンクに含まれる"""
        text = "# A\nintro\n## B\nbody\n### C\nmore\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text, min_chunk_level=2)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["heading_path"], ["A"])
        self.assertEqual(chunks[1]["heading_path"], ["A", "B"])
        # h3 の "more" は h2 チャンクに含まれる
        self.assertIn("more", chunks[1]["body"])

    def test_min_chunk_level_default_unchanged(self):
        """デフォルト (min_chunk_level=6) では既存動作と同じ"""
        text = "# A\nintro\n## B\nbody\n### C\nmore\n"
        chunks_default = chunk_extractor.extract_chunks("docs/a.md", text)
        chunks_explicit = chunk_extractor.extract_chunks("docs/a.md", text, min_chunk_level=6)
        self.assertEqual(len(chunks_default), 3)
        self.assertEqual(
            [c["heading_path"] for c in chunks_default],
            [c["heading_path"] for c in chunks_explicit],
        )

    def test_embed_text_includes_heading_path(self):
        """embed_text に heading_path の文脈が含まれる"""
        prose = "ここが本文です。十分な長さのテキストを含みます。テスト用のサンプルテキスト。"
        text = f"# AAA\n## BBB\n### CCC\n{prose}\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text)
        ccc = next(c for c in chunks if c["heading_path"] == ["AAA", "BBB", "CCC"])
        self.assertIn("AAA", ccc["embed_text"])
        self.assertIn("BBB", ccc["embed_text"])
        self.assertIn("CCC", ccc["embed_text"])
        self.assertIn("ここが本文", ccc["embed_text"])

    def test_embed_text_fallback_to_ancestor_prose(self):
        """prose が MIN_EMBED_PROSE 未満の空セクションは直前チャンクの prose で補完される"""
        prose = "十分な長さの本文テキストです。" * 5
        text = f"# AAA\n{prose}\n## BBB\n### 空セクション\n"
        chunks = chunk_extractor.extract_chunks("docs/a.md", text)
        empty_chunk = next(c for c in chunks if "空セクション" in c["heading_path"])
        self.assertIn(prose.strip()[:20], empty_chunk["embed_text"])
        self.assertIn("空セクション", empty_chunk["embed_text"])

    def test_embed_text_no_fallback_across_files(self):
        """異なる path の chunk を遡らない"""
        prose = "十分な長さの本文テキストです。" * 5
        chunks_a = chunk_extractor.extract_chunks("docs/a.md", f"# A\n{prose}\n")
        chunks_b = chunk_extractor.extract_chunks("docs/b.md", "# B\n## 空\n")
        combined = chunks_a + chunks_b
        chunk_extractor._enrich_embed_texts(combined)
        b_empty = next(c for c in combined if c["path"] == "docs/b.md" and "空" in c["heading_path"])
        self.assertNotIn(prose.strip()[:20], b_empty.get("embed_text", ""))

    def test_chunk_id_collision_adds_suffix(self):
        class _FakeHash:
            def hexdigest(self):
                return "deadbeef" * 8

        text = "# A\nfirst\n## B\nsecond\n"
        with patch.object(chunk_extractor.hashlib, "sha256", return_value=_FakeHash()):
            chunks = chunk_extractor.extract_chunks("docs/a.md", text)
        self.assertEqual(chunks[0]["chunk_id"], "deadbeef")
        self.assertEqual(chunks[1]["chunk_id"], "deadbeef-2")


if __name__ == "__main__":
    unittest.main()
