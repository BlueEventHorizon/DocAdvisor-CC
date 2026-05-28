#!/usr/bin/env python3
"""
doc-advisor auto モード再定義の検査 (Issue #54)

Issue #54 で auto モードから doc-db 連携 (Step 1a/1b/2/3) を削除し、
「ToC + Index 両方実行 (API キーなしなら Index パス)」に再定義した。

このテストは以下の受け入れ条件 (Issue #54) を担保する:

1. doc-db 連携セクション (Step 1a〜3) が両 SKILL.md から完全に消滅している
2. auto モードが「ToC + Index 両方実行」の仕様に書き換わっている
   (Step A〜D + API キー判定式が存在する)
7. description にトリガー句行 ("トリガー:") が含まれていない
8. plugin.json のバージョンが 0.3.0

受け入れ条件 3〜6 (各モードの実行時挙動) は SKILL.md ではなく run-time
で検証する性質のため本ユニットテストの対象外。

対象:
- plugins/doc-advisor/skills/query-rules/SKILL.md
- plugins/doc-advisor/skills/query-specs/SKILL.md
- plugins/doc-advisor/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

実行:
  python3 -m unittest tests.doc_advisor.skills.test_query_auto_redefinition -v
"""

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

QUERY_SKILLS = [
    REPO_ROOT / 'plugins' / 'doc-advisor' / 'skills' / 'query-rules' / 'SKILL.md',
    REPO_ROOT / 'plugins' / 'doc-advisor' / 'skills' / 'query-specs' / 'SKILL.md',
]

PLUGIN_JSON = REPO_ROOT / 'plugins' / 'doc-advisor' / '.claude-plugin' / 'plugin.json'
MARKETPLACE_JSON = REPO_ROOT / '.claude-plugin' / 'marketplace.json'

EXPECTED_VERSION = '0.3.0'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _split_frontmatter_body(skill_path: Path):
    text = _read(skill_path)
    if not text.startswith('---'):
        raise AssertionError(f"{skill_path} に YAML frontmatter がない")
    end = text.find('\n---', 3)
    if end == -1:
        raise AssertionError(f"{skill_path} の frontmatter が閉じていない")
    return text[3:end], text[end + 4:]


class TestDocDbReferencesRemoved(unittest.TestCase):
    """doc-db 連携セクション/コマンドが auto モードから完全に消えていること (受け入れ #1)"""

    # auto モード旧フローの見出し
    FORBIDDEN_HEADINGS = [
        '### Step 1a: doc-db plugin 未インストール検出',
        '### Step 1b: Index 鮮度確認',
        '### Step 2: Index 自動ビルド',
        '### Step 3: Hybrid 検索',
    ]

    # doc-db SKILL の起動コマンド (CLI 表記)
    FORBIDDEN_COMMANDS = [
        '/doc-db:build-index',
        '/doc-db:query',
    ]

    def test_old_step_headings_absent(self):
        for skill in QUERY_SKILLS:
            with self.subTest(skill=skill.relative_to(REPO_ROOT).as_posix()):
                body = _read(skill)
                for heading in self.FORBIDDEN_HEADINGS:
                    self.assertNotIn(
                        heading,
                        body,
                        f"{skill.name} に旧 doc-db 連携の見出し '{heading}' が残っている",
                    )

    def test_doc_db_skill_invocations_absent(self):
        for skill in QUERY_SKILLS:
            with self.subTest(skill=skill.relative_to(REPO_ROOT).as_posix()):
                body = _read(skill)
                for cmd in self.FORBIDDEN_COMMANDS:
                    self.assertNotIn(
                        cmd,
                        body,
                        f"{skill.name} に doc-db SKILL 起動 '{cmd}' が残っている",
                    )


class TestAutoModeNewStructure(unittest.TestCase):
    """auto モードが Step A〜D + API キー判定式に書き換わっていること (受け入れ #2)"""

    REQUIRED_HEADINGS = [
        '### Step A: API キー有無の判定',
        '### Step B: ToC ワークフロー実行',
        '### Step C: Index ワークフロー実行',
        '### Step D: 結果マージ',
    ]

    # forge 全体共通の API キー判定式 (DES-007)
    API_KEY_CHECK_PATTERN = re.compile(
        r'\[\s*-n\s+"\$\{OPENAI_API_DOCDB_KEY:-\}"\s*\]\s*\|\|\s*\[\s*-n\s+"\$\{OPENAI_API_KEY:-\}"\s*\]'
    )

    def test_step_a_through_d_present(self):
        for skill in QUERY_SKILLS:
            with self.subTest(skill=skill.relative_to(REPO_ROOT).as_posix()):
                body = _read(skill)
                for heading in self.REQUIRED_HEADINGS:
                    self.assertIn(
                        heading,
                        body,
                        f"{skill.name} に新 auto モード見出し '{heading}' が存在しない",
                    )

    def test_api_key_check_expression_present(self):
        for skill in QUERY_SKILLS:
            with self.subTest(skill=skill.relative_to(REPO_ROOT).as_posix()):
                body = _read(skill)
                self.assertRegex(
                    body,
                    self.API_KEY_CHECK_PATTERN,
                    f"{skill.name} に API キー判定式 (DES-007) が存在しない",
                )


class TestDescriptionTriggerRemoved(unittest.TestCase):
    """description にトリガー句行が含まれていないこと (受け入れ #7)"""

    def test_no_trigger_line_in_description(self):
        for skill in QUERY_SKILLS:
            with self.subTest(skill=skill.relative_to(REPO_ROOT).as_posix()):
                frontmatter, _ = _split_frontmatter_body(skill)
                # description は frontmatter の `|` ブロックスカラのため
                # トリガー句は本来 "トリガー:" で始まる行として記述されていた
                self.assertNotRegex(
                    frontmatter,
                    r'^\s*トリガー\s*[:：]',
                    f"{skill.name} の description にトリガー句行が残っている",
                )


class TestPluginVersionBumped(unittest.TestCase):
    """plugin.json / marketplace.json のバージョンが 0.3.0 になっていること (受け入れ #8)"""

    def test_plugin_json_version(self):
        data = json.loads(_read(PLUGIN_JSON))
        self.assertEqual(
            data.get('version'),
            EXPECTED_VERSION,
            f"plugins/doc-advisor/.claude-plugin/plugin.json の version が {EXPECTED_VERSION} ではない",
        )

    def test_marketplace_json_version(self):
        data = json.loads(_read(MARKETPLACE_JSON))
        plugins = data.get('plugins', [])
        doc_advisor_entry = next(
            (p for p in plugins if p.get('name') == 'doc-advisor'),
            None,
        )
        self.assertIsNotNone(
            doc_advisor_entry,
            ".claude-plugin/marketplace.json に doc-advisor エントリが存在しない",
        )
        self.assertEqual(
            doc_advisor_entry.get('version'),
            EXPECTED_VERSION,
            f"marketplace.json の doc-advisor.version が {EXPECTED_VERSION} ではない",
        )


if __name__ == '__main__':
    unittest.main()
