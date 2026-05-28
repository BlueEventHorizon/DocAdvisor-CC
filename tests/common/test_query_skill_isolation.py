#!/usr/bin/env python3
"""
検索系 SKILL の subagent 隔離 / read-only 制約テスト

ADR-002 (docs/specs/doc-advisor/design/ADR-002_query_skill_subagent_isolation.md)
および COMMON-DES-001 §4 (docs/specs/common/design/COMMON-DES-001_skill_base_design.md)
で採択された以下の制約が、対象 SKILL.md に反映されていることを検証する:

- fork 型 SKILL の frontmatter に `context: fork` が含まれている (§4 規定リスト)
- 全 query-* SKILL の Role 章に read-only 制約 (Edit/Write/MultiEdit/NotebookEdit 禁止) が
  明記されている (B 層: AI 行動規範での逸脱抑止)
- Role 章に git 管理ファイル書き換え禁止が明記されている
- 引数解釈ガード ([MANDATORY]) が含まれている

対象:
- fork 型 (COMMON-DES-001 §4 規定リスト):
  - plugins/doc-advisor/skills/query-rules/SKILL.md
  - plugins/doc-advisor/skills/query-specs/SKILL.md
- 継承型だが Role 制約を維持する SKILL (COMMON-DES-001 §4.2):
  - plugins/forge/skills/query-forge-rules/SKILL.md

実行:
  python3 -m unittest tests.common.test_query_skill_isolation -v
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# COMMON-DES-001 §4 規定リスト: fork 型 SKILL（context: fork 必須）
FORK_TARGET_SKILLS = [
    REPO_ROOT / 'plugins' / 'doc-advisor' / 'skills' / 'query-rules' / 'SKILL.md',
    REPO_ROOT / 'plugins' / 'doc-advisor' / 'skills' / 'query-specs' / 'SKILL.md',
]

# Role 制約・引数解釈ガード・出力契約を維持する全 query-* SKILL
# (fork 型 + COMMON-DES-001 §4.2 で継承型に再分類された SKILL)
CONSTRAINT_TARGET_SKILLS = FORK_TARGET_SKILLS + [
    REPO_ROOT / 'plugins' / 'forge' / 'skills' / 'query-forge-rules' / 'SKILL.md',
]


def _split_frontmatter_body(skill_path: Path):
    """SKILL.md を frontmatter 文字列と本文に分割する。"""
    text = skill_path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        raise AssertionError(f"{skill_path} に YAML frontmatter がない")
    end = text.find('\n---', 3)
    if end == -1:
        raise AssertionError(f"{skill_path} の frontmatter が閉じていない")
    fm = text[3:end]
    body = text[end + 4:]
    return fm, body


class TestQuerySkillFrontmatterFork(unittest.TestCase):
    """fork 型 SKILL の frontmatter に `context: fork` が含まれていることを検証

    対象は COMMON-DES-001 §4 規定リスト（fork 型）のみ。継承型に再分類された
    SKILL（§4.2）は本検証の対象外。
    """

    def test_context_fork_present(self):
        for skill_path in FORK_TARGET_SKILLS:
            with self.subTest(skill=str(skill_path.relative_to(REPO_ROOT))):
                fm, _ = _split_frontmatter_body(skill_path)
                self.assertRegex(
                    fm,
                    r'(?m)^context:\s*fork\s*$',
                    f"{skill_path.relative_to(REPO_ROOT)} の frontmatter に "
                    f"`context: fork` がない (COMMON-DES-001 §4 規定リスト違反)"
                )


class TestQuerySkillRoleReadonlyConstraint(unittest.TestCase):
    """Role 章に read-only 制約が明記されていることを検証 (ADR-002 §B / 多重防御 B 層)"""

    REQUIRED_PHRASES = [
        # read-only であることの明記
        'read-only',
        # 禁止される書き込み系ツール (列挙)
        'Edit',
        'Write',
        'MultiEdit',
        'NotebookEdit',
        # git 副作用を伴うコマンド禁止
        'git commit',
        # git 管理ファイル書き換え禁止
        'git 管理ファイル',
        # MANDATORY タグ (制約セクションの強制力を担保)
        '[MANDATORY]',
    ]

    def test_role_section_has_constraints(self):
        for skill_path in CONSTRAINT_TARGET_SKILLS:
            with self.subTest(skill=str(skill_path.relative_to(REPO_ROOT))):
                _, body = _split_frontmatter_body(skill_path)
                for phrase in self.REQUIRED_PHRASES:
                    self.assertIn(
                        phrase, body,
                        f"{skill_path.relative_to(REPO_ROOT)} に制約文言 "
                        f"'{phrase}' がない (ADR-002 §B 違反)"
                    )


class TestQuerySkillArgumentGuard(unittest.TestCase):
    """引数解釈ガードが含まれていることを検証 (ADR-002 §C)"""

    def test_argument_interpretation_section(self):
        for skill_path in CONSTRAINT_TARGET_SKILLS:
            with self.subTest(skill=str(skill_path.relative_to(REPO_ROOT))):
                _, body = _split_frontmatter_body(skill_path)
                # `### 引数解釈` または `## 引数解釈` 見出しが存在する
                self.assertRegex(
                    body,
                    r'(?m)^#{2,3}\s*引数解釈',
                    f"{skill_path.relative_to(REPO_ROOT)} に "
                    f"`引数解釈` セクションがない (ADR-002 §C 違反)"
                )
                # 命令文を実装指示として解釈しない旨の明記
                self.assertIn(
                    '実装指示として解釈してはならない', body,
                    f"{skill_path.relative_to(REPO_ROOT)} の引数解釈に "
                    f"命令文の解釈ガードがない (ADR-002 §C 違反)"
                )


class TestQuerySkillReturnContract(unittest.TestCase):
    """最終 return が `Required documents:` 形式に限定されていることを検証"""

    def test_return_contract_documented(self):
        for skill_path in CONSTRAINT_TARGET_SKILLS:
            with self.subTest(skill=str(skill_path.relative_to(REPO_ROOT))):
                _, body = _split_frontmatter_body(skill_path)
                self.assertIn(
                    'Required documents:', body,
                    f"{skill_path.relative_to(REPO_ROOT)} に "
                    f"`Required documents:` 出力契約の記載がない"
                )


if __name__ == '__main__':
    unittest.main()
