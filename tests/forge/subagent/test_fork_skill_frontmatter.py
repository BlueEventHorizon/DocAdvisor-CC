#!/usr/bin/env python3
"""
TEST-S006 (TASK-013): fork 型 SKILL (reviewer / evaluator / fixer) の frontmatter と
本文が SUBAGENT-DES-001 §9.2 の要件を満たすこと。

検証項目:
- frontmatter に context: fork が含まれる
- frontmatter に agent: general-purpose が含まれる
- reviewer / evaluator の本文に Edit/Write 禁止制約文言がある
- reviewer / evaluator / fixer の本文に「親タスク引継ぎ禁止」の Role 制約がある
- reviewer / evaluator / fixer の本文に「自己再帰禁止」の明示がある

実行:
    python3 -m unittest tests.forge.subagent.test_fork_skill_frontmatter -v
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills'

FORK_SKILLS = ['reviewer', 'evaluator', 'fixer']

# reviewer と evaluator は Edit/Write を禁止する (fixer は許可)
EDIT_WRITE_RESTRICTED = ['reviewer', 'evaluator']


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end]
    result: dict = {}
    for line in fm_text.split('\n'):
        if ':' in line and not line.strip().startswith('-'):
            key, _, val = line.partition(':')
            result[key.strip()] = val.strip()
    return result, content[end + 3:]


class TestForkSkillFrontmatter(unittest.TestCase):
    """TASK-013: reviewer / evaluator / fixer が fork 型 SKILL 要件を満たすこと。"""

    def setUp(self) -> None:
        self.skill_data: dict[str, tuple[dict, str]] = {}
        for name in FORK_SKILLS:
            path = SKILLS_DIR / name / 'SKILL.md'
            self.assertTrue(path.exists(), f'{name}/SKILL.md が存在しない: {path}')
            content = path.read_text(encoding='utf-8')
            fm, body = _parse_frontmatter(content)
            self.skill_data[name] = (fm, body)

    def test_context_fork_in_frontmatter(self) -> None:
        """frontmatter に context: fork が含まれること。"""
        for name in FORK_SKILLS:
            fm, _ = self.skill_data[name]
            self.assertEqual(
                fm.get('context', ''),
                'fork',
                f'{name}/SKILL.md: frontmatter に context: fork がない (現在値: {fm.get("context")})',
            )

    def test_agent_general_purpose_in_frontmatter(self) -> None:
        """frontmatter に agent: general-purpose が含まれること。"""
        for name in FORK_SKILLS:
            fm, _ = self.skill_data[name]
            self.assertEqual(
                fm.get('agent', ''),
                'general-purpose',
                f'{name}/SKILL.md: frontmatter に agent: general-purpose がない (現在値: {fm.get("agent")})',
            )

    def test_edit_write_prohibition_in_body(self) -> None:
        """reviewer / evaluator の本文に Edit/Write 禁止制約文言があること。"""
        # Edit または Write を禁止する文言: "Edit" + "Write" が同じ行または近傍にあり
        # かつ "禁止" / "してはならない" / "は使用してはならない" 等が含まれること
        for name in EDIT_WRITE_RESTRICTED:
            _, body = self.skill_data[name]
            found = False
            for line in body.split('\n'):
                has_edit_or_write = 'Edit' in line or 'Write' in line
                has_prohibition = any(
                    kw in line
                    for kw in ['禁止', 'してはならない', 'は使用しない', '使用してはならない']
                )
                if has_edit_or_write and has_prohibition:
                    found = True
                    break
            self.assertTrue(
                found,
                f'{name}/SKILL.md: Edit/Write 禁止の制約文言が本文に見つからない',
            )

    def test_parent_task_prohibition_in_body(self) -> None:
        """reviewer / evaluator / fixer の本文に親タスク引継ぎ禁止の Role 制約があること。"""
        PARENT_TASK_PATTERNS = ['親タスク', '親セッション']
        for name in FORK_SKILLS:
            _, body = self.skill_data[name]
            found = any(pat in body for pat in PARENT_TASK_PATTERNS)
            self.assertTrue(
                found,
                f'{name}/SKILL.md: 親タスク引継ぎ禁止の Role 制約が本文に見つからない '
                f'(検索パターン: {PARENT_TASK_PATTERNS})',
            )

    def test_self_recursion_prohibition_in_body(self) -> None:
        """reviewer / evaluator / fixer の本文に自己再帰禁止の明示があること。"""
        SELF_RECURSION_PATTERNS = ['自己再帰禁止', '自身を呼び戻すこと']
        for name in FORK_SKILLS:
            _, body = self.skill_data[name]
            found = any(pat in body for pat in SELF_RECURSION_PATTERNS)
            self.assertTrue(
                found,
                f'{name}/SKILL.md: 自己再帰禁止の明示が本文に見つからない '
                f'(検索パターン: {SELF_RECURSION_PATTERNS})',
            )


if __name__ == '__main__':
    unittest.main()
