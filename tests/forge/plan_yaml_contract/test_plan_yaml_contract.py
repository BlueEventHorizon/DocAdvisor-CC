#!/usr/bin/env python3
"""forge 実装計画書 `{feature}_plan.yaml` の YAML 正本契約 (Issue #111) を静的検査する回帰テスト。

実行:
  python3 -m unittest tests.forge.plan_yaml_contract.test_plan_yaml_contract -v

検査対象:
  1. ユーザー向けガイド・SKILL の YAML 例が `plan_format.md` 必須フィールドを欠かない
  2. 主要 SKILL / ガイドが forge 実装計画書を Markdown として誘導する旧表現を残していない
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


PLAN_FORMAT = REPO_ROOT / "plugins" / "forge" / "docs" / "plan_format.md"

GUIDE_YAML_EXAMPLE_FILES = [
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_create_docs_ja.md",
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_create_docs.md",
]

REQUIRED_TASK_FIELDS = [
    "task_id",
    "title",
    "priority",
    "status",
    "design_id",
    "depends_on",
    "group_id",
    "build_check",
    "description",
    "acceptance_criteria",
    "required_reading",
]

REQUIRED_TOP_LEVEL_KEYS = [
    "requirements_traceability",
    "design_traceability",
    "tasks",
    "revision_history",
]


SKILL_FILES_TO_AUDIT = [
    REPO_ROOT / "plugins" / "forge" / "skills" / "start-plan" / "SKILL.md",
    REPO_ROOT / "plugins" / "forge" / "skills" / "start-implement" / "SKILL.md",
    REPO_ROOT / "plugins" / "forge" / "docs" / "plan_principles_spec.md",
]

GUIDE_FILES_TO_AUDIT = [
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_create_docs_ja.md",
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_create_docs.md",
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_implement_ja.md",
    REPO_ROOT / "docs" / "readme" / "forge" / "guide_implement.md",
]


FORBIDDEN_MARKDOWN_INDUCERS = [
    re.compile(r"「ビルド確認」列"),
    re.compile(r"「受け入れ基準」列"),
    re.compile(r"「必読」列"),
    re.compile(r"必読列"),
    re.compile(r"タスク表の列"),
    re.compile(r"設計ID ≠ `?-`?"),
    re.compile(r"design_id ≠ `?-`?"),
    re.compile(r"\{feature\}_plan\.md"),
]


def _extract_yaml_blocks(text: str) -> list[str]:
    return re.findall(r"```ya?ml\n(.*?)```", text, flags=re.DOTALL)


class TestGuideYamlExamplesHaveRequiredFields(unittest.TestCase):
    """ユーザー向けガイドの計画書 YAML 例が必須フィールドを欠かないことを検査"""

    def test_guides_have_complete_plan_yaml_example(self):
        for path in GUIDE_YAML_EXAMPLE_FILES:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertTrue(path.exists(), f"missing: {path}")
                text = path.read_text(encoding="utf-8")
                blocks = _extract_yaml_blocks(text)
                self.assertTrue(
                    blocks,
                    "ガイドに YAML コードブロックが 1 つも無い: " + str(path),
                )

                plan_block = self._find_plan_block(blocks)
                self.assertIsNotNone(
                    plan_block,
                    "計画書 YAML 例 (tasks/requirements_traceability を含むブロック) が見当たらない: "
                    + str(path),
                )

                for key in REQUIRED_TOP_LEVEL_KEYS:
                    with self.subTest(top_level=key):
                        self.assertIn(
                            key,
                            plan_block,
                            f"ガイドの計画書 YAML 例に top-level キー '{key}' が含まれていない: {path}",
                        )

                for field in REQUIRED_TASK_FIELDS:
                    with self.subTest(field=field):
                        self.assertIn(
                            field,
                            plan_block,
                            f"ガイドの計画書 YAML 例に tasks[] 必須フィールド '{field}' が含まれていない: {path}",
                        )

    @staticmethod
    def _find_plan_block(blocks: list[str]) -> str | None:
        for block in blocks:
            if "tasks:" in block and "requirements_traceability" in block:
                return block
        return None


class TestPlanFormatIsCanonical(unittest.TestCase):
    """plan_format.md が必須フィールドを全て定義していること（正本性の自己検査）"""

    def test_plan_format_lists_all_required_fields(self):
        text = PLAN_FORMAT.read_text(encoding="utf-8")
        for key in REQUIRED_TOP_LEVEL_KEYS:
            self.assertIn(key, text, f"plan_format.md に top-level キー '{key}' が無い")
        for field in REQUIRED_TASK_FIELDS:
            self.assertIn(field, text, f"plan_format.md に tasks[] フィールド '{field}' が無い")


class TestNoMarkdownInducers(unittest.TestCase):
    """主要 SKILL / ガイドに Markdown 計画書を誘導する旧表現が残っていないことを検査"""

    def test_skill_files_have_no_forbidden_patterns(self):
        self._assert_no_forbidden(SKILL_FILES_TO_AUDIT)

    def test_guide_files_have_no_forbidden_patterns(self):
        self._assert_no_forbidden(GUIDE_FILES_TO_AUDIT)

    def _assert_no_forbidden(self, files: list[Path]) -> None:
        for path in files:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertTrue(path.exists(), f"missing: {path}")
                text = path.read_text(encoding="utf-8")
                for pattern in FORBIDDEN_MARKDOWN_INDUCERS:
                    with self.subTest(pattern=pattern.pattern):
                        found = self._find_active_match(text, pattern)
                        self.assertIsNone(
                            found,
                            f"{path.relative_to(REPO_ROOT)} に Markdown 誘導表現が残存: "
                            f"pattern={pattern.pattern!r} match={found!r}",
                        )

    @staticmethod
    def _find_active_match(text: str, pattern: re.Pattern[str]) -> str | None:
        """改定履歴行は履歴的事実として除外する"""
        for line in text.splitlines():
            stripped = line.lstrip("- *>|").strip()
            # 改定履歴の YAML エントリや「revision_history」セクション内の言及はスキップ
            if stripped.startswith(("content:", "date:")):
                continue
            # 重大度カタログ・改定履歴の本文行は履歴的説明を含むので、
            # 履歴セクションの典型的接頭辞行はスキップ
            if "forge-review feature 統合" in line or "Issue #111" in line:
                continue
            match = pattern.search(line)
            if match:
                return match.group(0)
        return None


class TestRenamedSkillExists(unittest.TestCase):
    """Issue #111 で rename 済みの create-feature-from-markdown-plan が存在し、旧名 wrapper が残っていないこと"""

    def test_renamed_skill_present(self):
        renamed = (
            REPO_ROOT
            / "plugins"
            / "forge"
            / "skills"
            / "create-feature-from-markdown-plan"
            / "SKILL.md"
        )
        self.assertTrue(renamed.exists(), f"rename 後の skill が見当たらない: {renamed}")
        text = renamed.read_text(encoding="utf-8")
        self.assertIn("name: create-feature-from-markdown-plan", text)

    def test_old_skill_dir_absent(self):
        old = REPO_ROOT / "plugins" / "forge" / "skills" / "create-feature-from-plan"
        self.assertFalse(
            old.exists(),
            f"旧 skill ディレクトリが残っている (互換 wrapper は採用していない): {old}",
        )


if __name__ == "__main__":
    unittest.main()
