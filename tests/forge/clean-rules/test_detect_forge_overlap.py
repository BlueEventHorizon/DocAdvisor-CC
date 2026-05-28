#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detect_forge_overlap.py のユニットテスト。

テスト対象:
- split_sections(): ## 見出しによるセクション分割
- cosine_similarity(): コサイン類似度計算
- collect_sections(): 複数ファイルからのセクション収集
- find_overlaps(): 閾値ベースの重複検出
- main(): CLI 実行時の JSON 出力フォーマット

Embedding API 呼び出しは全て unittest.mock でモック化。
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[3]
    / "plugins" / "forge" / "skills" / "clean-rules" / "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# doc-advisor の embedding_api も sys.path に追加（detect_forge_overlap が import するため）
DOC_ADVISOR_SCRIPTS = str(
    Path(__file__).resolve().parents[3]
    / "plugins" / "doc-advisor" / "scripts"
)
if DOC_ADVISOR_SCRIPTS not in sys.path:
    sys.path.insert(0, DOC_ADVISOR_SCRIPTS)

from detect_forge_overlap import (
    collect_sections,
    cosine_similarity,
    find_overlaps,
    split_sections,
)


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------

def _make_vector(*values):
    """テスト用の短いベクトルを生成する。"""
    return list(values)


SIMILAR_VEC_A = _make_vector(1.0, 0.0, 0.0)
SIMILAR_VEC_B = _make_vector(0.9, 0.1, 0.0)
ORTHOGONAL_VEC = _make_vector(0.0, 0.0, 1.0)
ZERO_VEC = _make_vector(0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# split_sections テスト
# ---------------------------------------------------------------------------

class TestSplitSections(unittest.TestCase):
    """## 見出しによるセクション分割のテスト。"""

    def test_basic_split(self):
        """基本的な ## 見出しで分割される"""
        content = """# Title

Introduction text.

## Section A

Content A.

## Section B

Content B.
"""
        sections = split_sections(content, filepath="test.md")
        self.assertEqual(len(sections), 3)
        self.assertIn("test.md", sections[0]["heading"])
        self.assertEqual(sections[1]["heading"], "## Section A")
        self.assertEqual(sections[2]["heading"], "## Section B")

    def test_no_sections(self):
        """## 見出しがないファイルは全体を1セクションとして返す"""
        content = "Just plain text without any headings."
        sections = split_sections(content, filepath="plain.md")
        self.assertEqual(len(sections), 1)
        self.assertIn("plain.md", sections[0]["heading"])
        self.assertEqual(sections[0]["text"], "Just plain text without any headings.")

    def test_subsections_not_split(self):
        """### 以下の見出しでは分割しない"""
        content = """## Main Section

### Subsection 1

Text 1.

### Subsection 2

Text 2.
"""
        sections = split_sections(content)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading"], "## Main Section")
        self.assertIn("### Subsection 1", sections[0]["text"])

    def test_empty_content(self):
        """空文字列の場合は空リストを返す"""
        sections = split_sections("")
        self.assertEqual(sections, [])

    def test_whitespace_only(self):
        """空白のみの場合は空リストを返す"""
        sections = split_sections("   \n\n  ")
        self.assertEqual(sections, [])

    def test_line_numbers(self):
        """セクションの開始行番号が正しい"""
        content = """Line 1
Line 2

## Section at Line 4

Content.

## Section at Line 8

More content.
"""
        sections = split_sections(content)
        self.assertEqual(sections[0]["line"], 1)
        self.assertEqual(sections[1]["line"], 4)
        self.assertEqual(sections[2]["line"], 8)

    def test_frontmatter_handling(self):
        """YAML frontmatter がある場合もヘッダーセクションに含まれる"""
        content = """---
name: test
---

# Title

Intro.

## Section A

Content.
"""
        sections = split_sections(content, filepath="fm.md")
        self.assertEqual(len(sections), 2)
        self.assertIn("---", sections[0]["text"])


# ---------------------------------------------------------------------------
# cosine_similarity テスト
# ---------------------------------------------------------------------------

class TestCosineSimilarity(unittest.TestCase):
    """コサイン類似度計算のテスト。"""

    def test_identical_vectors(self):
        """同一ベクトルの類似度は 1.0"""
        self.assertAlmostEqual(
            cosine_similarity(SIMILAR_VEC_A, SIMILAR_VEC_A), 1.0
        )

    def test_orthogonal_vectors(self):
        """直交ベクトルの類似度は 0.0"""
        self.assertAlmostEqual(
            cosine_similarity(SIMILAR_VEC_A, ORTHOGONAL_VEC), 0.0
        )

    def test_similar_vectors(self):
        """類似ベクトルの類似度は 0 < x < 1"""
        score = cosine_similarity(SIMILAR_VEC_A, SIMILAR_VEC_B)
        self.assertGreater(score, 0.9)
        self.assertLess(score, 1.0)

    def test_zero_vector(self):
        """ゼロベクトルの類似度は 0.0"""
        self.assertEqual(cosine_similarity(ZERO_VEC, SIMILAR_VEC_A), 0.0)


# ---------------------------------------------------------------------------
# collect_sections テスト
# ---------------------------------------------------------------------------

class TestCollectSections(unittest.TestCase):
    """ファイルからのセクション収集テスト。"""

    def test_collect_from_files(self):
        """複数ファイルからセクションを収集する"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.md"
            f1.write_text("## Sec A\n\nContent A.\n", encoding="utf-8")
            f2 = Path(tmpdir) / "b.md"
            f2.write_text("## Sec B\n\nContent B.\n\n## Sec C\n\nContent C.\n",
                          encoding="utf-8")

            sections = collect_sections([str(f1), str(f2)])
            self.assertEqual(len(sections), 3)
            self.assertEqual(sections[0]["heading"], "## Sec A")
            self.assertEqual(sections[0]["file"], str(f1))

    def test_missing_file_skipped(self):
        """存在しないファイルはスキップされる"""
        sections = collect_sections(["/nonexistent/file.md"])
        self.assertEqual(sections, [])


# ---------------------------------------------------------------------------
# find_overlaps テスト
# ---------------------------------------------------------------------------

class TestFindOverlaps(unittest.TestCase):
    """重複検出ロジックのテスト。"""

    def test_high_similarity_detected(self):
        """高類似度のペアが検出される"""
        project_sections = [
            {"file": "rules/a.md", "heading": "## Rule A", "text": "...", "line": 1},
        ]
        forge_sections = [
            {"file": "forge/x.md", "heading": "## Forge X", "text": "...", "line": 1},
        ]
        p_emb = [_make_vector(1.0, 0.0, 0.0)]
        f_emb = [_make_vector(0.95, 0.05, 0.0)]

        overlaps = find_overlaps(project_sections, p_emb, forge_sections, f_emb, 0.5)
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]["project_file"], "rules/a.md")
        self.assertEqual(overlaps[0]["forge_file"], "forge/x.md")
        self.assertGreater(overlaps[0]["similarity"], 0.9)

    def test_low_similarity_not_detected(self):
        """低類似度のペアは検出されない"""
        project_sections = [
            {"file": "rules/a.md", "heading": "## Rule A", "text": "...", "line": 1},
        ]
        forge_sections = [
            {"file": "forge/x.md", "heading": "## Forge X", "text": "...", "line": 1},
        ]
        p_emb = [_make_vector(1.0, 0.0, 0.0)]
        f_emb = [_make_vector(0.0, 0.0, 1.0)]

        overlaps = find_overlaps(project_sections, p_emb, forge_sections, f_emb, 0.5)
        self.assertEqual(len(overlaps), 0)

    def test_best_match_selected(self):
        """複数 forge セクションがある場合、最も類似度の高いものが選ばれる"""
        project_sections = [
            {"file": "rules/a.md", "heading": "## Rule A", "text": "...", "line": 1},
        ]
        forge_sections = [
            {"file": "forge/x.md", "heading": "## Low Match", "text": "...", "line": 1},
            {"file": "forge/y.md", "heading": "## High Match", "text": "...", "line": 1},
        ]
        p_emb = [_make_vector(1.0, 0.0, 0.0)]
        f_emb = [
            _make_vector(0.3, 0.3, 0.3),
            _make_vector(0.98, 0.02, 0.0),
        ]

        overlaps = find_overlaps(project_sections, p_emb, forge_sections, f_emb, 0.5)
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]["forge_section"], "## High Match")

    def test_sorted_by_similarity_desc(self):
        """結果は similarity 降順でソートされる"""
        project_sections = [
            {"file": "rules/a.md", "heading": "## A", "text": "...", "line": 1},
            {"file": "rules/b.md", "heading": "## B", "text": "...", "line": 1},
        ]
        forge_sections = [
            {"file": "forge/x.md", "heading": "## X", "text": "...", "line": 1},
        ]
        p_emb = [
            _make_vector(0.7, 0.3, 0.0),
            _make_vector(0.99, 0.01, 0.0),
        ]
        f_emb = [_make_vector(1.0, 0.0, 0.0)]

        overlaps = find_overlaps(project_sections, p_emb, forge_sections, f_emb, 0.5)
        self.assertEqual(len(overlaps), 2)
        self.assertGreaterEqual(overlaps[0]["similarity"], overlaps[1]["similarity"])


# ---------------------------------------------------------------------------
# main() 統合テスト（API モック）
# ---------------------------------------------------------------------------

class TestMainOutput(unittest.TestCase):
    """main() の JSON 出力フォーマットテスト。"""

    def _run_main(self, project_files, forge_files, threshold=0.5):
        """main() を実行して stdout の JSON を返す。"""
        from detect_forge_overlap import main
        import io

        args = ["prog",
                "--project-rules"] + project_files + [
                "--forge-docs"] + forge_files + [
                "--threshold", str(threshold)]

        captured = io.StringIO()
        with patch("sys.argv", args), \
             patch("sys.stdout", captured), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), \
             patch("detect_forge_overlap.call_embedding_api") as mock_api:

            mock_api.return_value = [_make_vector(1.0, 0.0, 0.0)]
            try:
                main()
            except SystemExit:
                pass

        output = captured.getvalue()
        return json.loads(output) if output.strip() else None

    def test_output_has_required_fields(self):
        """JSON 出力に必須フィールドが含まれる"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "rule.md"
            p.write_text("## Sec\n\nContent.\n", encoding="utf-8")
            f = Path(tmpdir) / "forge.md"
            f.write_text("## Forge\n\nContent.\n", encoding="utf-8")

            result = self._run_main([str(p)], [str(f)])
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "ok")
            self.assertIn("overlaps", result)
            self.assertIn("threshold", result)
            self.assertIn("project_section_count", result)
            self.assertIn("forge_section_count", result)

    def test_no_api_key_error(self):
        """OPENAI_API_DOCDB_KEY / OPENAI_API_KEY 双方未設定でエラー (DES-007 / FNC-004 KEY-01)"""
        from detect_forge_overlap import main
        import io

        captured = io.StringIO()
        with patch("sys.argv", ["prog", "--project-rules", "a.md",
                                 "--forge-docs", "b.md"]), \
             patch("sys.stdout", captured), \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                main()

        output = captured.getvalue()
        result = json.loads(output)
        self.assertEqual(result["status"], "error")
        self.assertIn("OPENAI_API_DOCDB_KEY", result["error"])
        self.assertIn("OPENAI_API_KEY", result["error"])

    def test_fallback_to_openai_api_key(self):
        """OPENAI_API_DOCDB_KEY 未設定 / OPENAI_API_KEY のみ設定でフォールバック動作 (DES-007)"""
        from detect_forge_overlap import main
        import io

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "rule.md"
            p.write_text("## Sec\n\nContent.\n", encoding="utf-8")
            f = Path(tmpdir) / "forge.md"
            f.write_text("## Forge\n\nContent.\n", encoding="utf-8")

            captured = io.StringIO()
            with patch("sys.argv", ["prog", "--project-rules", str(p),
                                     "--forge-docs", str(f)]), \
                 patch("sys.stdout", captured), \
                 patch.dict(os.environ, {"OPENAI_API_KEY": "fallback-key"}, clear=True), \
                 patch("detect_forge_overlap.call_embedding_api") as mock_api:
                mock_api.return_value = [_make_vector(1.0, 0.0, 0.0)]
                try:
                    main()
                except SystemExit:
                    pass

            output = captured.getvalue()
            result = json.loads(output)
            # フォールバック経路で正常動作（"error" でない）
            self.assertEqual(result["status"], "ok")


if __name__ == "__main__":
    unittest.main()
