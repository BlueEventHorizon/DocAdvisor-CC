#!/usr/bin/env python3
"""
回帰防止テスト: review_criteria_*.md に "Perspective:" 見出しが残っていないことを検証する。

DES-028 §3.3 で定めた criteria 固定 3 セクション構造 (SSOT参照 / チェック順 / 判定ルール) を維持し、
Issue #68 系の旧 perspective 軸見出しへの逆戻りを CI で検知することが目的。

実行:
  python3 -m unittest tests.forge.review.test_criteria_no_perspective -v
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CRITERIA_DIR = REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "docs"

EXPECTED_FILES = {
    "review_criteria_code.md",
    "review_criteria_design.md",
    "review_criteria_requirement.md",
    "review_criteria_plan.md",
    "review_criteria_uxui.md",
    "review_criteria_generic.md",
}


class TestCriteriaNoPerspective(unittest.TestCase):
    """回帰防止: criteria に "Perspective:" 見出しが残っていないことを検証 (DES-028 §3.3)"""

    def setUp(self):
        self.criteria_files = sorted(CRITERIA_DIR.glob("review_criteria_*.md"))

    def test_six_criteria_files_exist(self):
        """6 種別の criteria ファイルが全て存在することを確認 (前提条件)"""
        names = {f.name for f in self.criteria_files}
        self.assertEqual(
            names,
            EXPECTED_FILES,
            f"criteria ファイル一覧が想定と異なる: {names ^ EXPECTED_FILES}",
        )

    def test_no_perspective_heading_level_2(self):
        """全 criteria に "## Perspective:" 見出しが存在しないこと"""
        for f in self.criteria_files:
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertNotIn(
                    "## Perspective:",
                    content,
                    f"{f.name} に '## Perspective:' が残存 (DES-028 §3.3 違反)",
                )

    def test_no_perspective_heading_level_3(self):
        """全 criteria に "### Perspective:" 見出しが存在しないこと"""
        for f in self.criteria_files:
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertNotIn(
                    "### Perspective:",
                    content,
                    f"{f.name} に '### Perspective:' が残存 (DES-028 §3.3 違反)",
                )

    def test_three_section_structure_present(self):
        """全 criteria に固定 3 セクション (SSOT参照 / チェック順 / 判定ルール) が存在することを確認 (正の対称テスト)"""
        for f in self.criteria_files:
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertIn(
                    "## 1. SSOT参照",
                    content,
                    f"{f.name} に '## 1. SSOT参照' 見出しがない (DES-028 §3.3)",
                )
                self.assertIn(
                    "## 2. チェック順",
                    content,
                    f"{f.name} に '## 2. チェック順' 見出しがない (DES-028 §3.3)",
                )
                self.assertIn(
                    "## 3. 判定ルール",
                    content,
                    f"{f.name} に '## 3. 判定ルール' 見出しがない (DES-028 §3.3)",
                )


if __name__ == "__main__":
    unittest.main()
