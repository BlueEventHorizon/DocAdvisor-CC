#!/usr/bin/env python3
"""
SKILL の引数契約テスト（DES-005 §10.1 / DES-008 §8.1）

SKILL の引数は上位層との公開インターフェースである。正本は設計書に置くが、
配布物（SKILL.md）と実装（script の argparse）がその契約を実際に満たしていることは
テストで固定する。

このテストが存在する理由は実際の事故である。ラッパー化の際に `index-docs` から
`--dirs-json` / `--exclude-json` が落ち、forge の update-db-rules / update-db-specs /
query-db-rules / query-db-specs が `unrecognized arguments` で失敗した。上位層は
引数を組み替えず再試行もしないため、索引が動かないまま上位層には理由が分からない
状態になる。当時 SKILL.md が引数仕様の唯一の正本であり、全面書き換えで契約が
消えても突き合わせる相手が無かった。

したがって検証するのは 2 点である:

1. script が契約の引数を**受け付ける**こと（実装が壊れていない）
2. SKILL.md が契約の引数を**記載している**こと（AI がその形で呼べる／消えたら落ちる）

引数の**追加**は既存の呼び出し元を壊さないため、このテストは網羅性を要求しない
（契約分が揃っていれば追加分は自由）。削除・改名を検出することが目的である。

実行:
  python3 -m unittest tests.skills.test_skill_argument_contract -v
"""

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / 'plugins' / 'doc-advisor'
SCRIPTS_DIR = PLUGIN_ROOT / 'scripts'

# DES-005 §10.1: index-docs が受け付けなければならない引数
INDEX_DOCS_CONTRACT = [
    '--key',
    '--dirs',
    '--dirs-json',
    '--paths',
    '--paths-json',
    '--paths-file',
    '--exclude',
    '--exclude-json',
    '--all',
    '--allow-external',
    '--on-fill-error',
]

# DES-008 §8.1: write-frontmatter が受け付けなければならない引数
WRITE_FRONTMATTER_CONTRACT = [
    '--paths',
    '--dirs',
    '--exclude',
    '--format-command',
]

# DES-009 / DES-005 §10.1
CHECK_TOC_CONTRACT = ['--key', '--all', '--max-age']


def _load_module(name, path):
    """script を単体モジュールとして読み込む（パッケージ化されていないため）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIndexDocsArgumentContract(unittest.TestCase):
    """index-docs: script 実装と SKILL.md の双方が契約を満たすこと。"""

    @classmethod
    def setUpClass(cls):
        cls.module = _load_module('index_docs_contract',
                                  SCRIPTS_DIR / 'index_docs.py')
        cls.skill_text = (PLUGIN_ROOT / 'skills' / 'index-docs' / 'SKILL.md').read_text(
            encoding='utf-8')

    # 契約の各引数を単体で通すための最小 argv。unrecognized arguments を
    # 検出するのが目的であり、値の妥当性は各引数のテストが別途担う。
    ARGV_FOR_FLAG = {
        '--key': ['--key', 'k'],
        '--all': ['--all'],
        '--on-fill-error': ['--key', 'k', '--on-fill-error', 'merge'],
        '--allow-external': ['--key', 'k', '--allow-external'],
    }

    def test_script_accepts_contract_flags(self):
        for flag in INDEX_DOCS_CONTRACT:
            argv = self.ARGV_FOR_FLAG.get(flag, ['--key', 'k', flag, 'x'])
            try:
                self.module.parse_args(argv)
            except SystemExit as e:
                self.fail(f'index_docs.py が契約の引数 {flag} を受け付けない'
                          f'（SystemExit {e.code}）。DES-005 §10.1。'
                          '削除・改名は上位層の呼び出しを壊すため承認が必要')

    def test_skill_documents_contract_flags(self):
        # assertIn は失敗時に SKILL.md 全文をダンプするため assertTrue を使う。
        for flag in INDEX_DOCS_CONTRACT:
            self.assertTrue(
                flag in self.skill_text,
                f'index-docs/SKILL.md が契約の引数 {flag} を記載していない'
                '（記載が消えると AI がその形で呼べず、上位層の呼び出しが失敗する）')

    def test_skill_forbids_rewriting_json_form(self):
        """上位層が渡した JSON 形をそのまま渡す規定が残っていること。"""
        self.assertTrue('--dirs-json' in self.skill_text,
                        'index-docs/SKILL.md に --dirs-json の記載がない')
        self.assertTrue('そのまま' in self.skill_text,
                        '受け取った JSON 形をそのまま渡す規定が SKILL.md から消えている')


class TestWriteFrontmatterArgumentContract(unittest.TestCase):
    """write-frontmatter: 引数契約（DES-008 §8.1）。"""

    @classmethod
    def setUpClass(cls):
        cls.skill_path = PLUGIN_ROOT / 'skills' / 'write-frontmatter' / 'SKILL.md'
        cls.skill_text = cls.skill_path.read_text(encoding='utf-8')

    def test_skill_documents_contract_flags(self):
        for flag in WRITE_FRONTMATTER_CONTRACT:
            self.assertTrue(
                flag in self.skill_text,
                f'write-frontmatter/SKILL.md が契約の引数 {flag} を記載していない')

    def test_wrapper_accepts_contract_flags(self):
        """fm_run.py が契約の引数を受け付けること（サブコマンド構成のため実行で確認）。"""
        module = _load_module('fm_run_contract',
                              SCRIPTS_DIR / 'frontmatter' / 'fm_run.py')
        for argv in (
            ['plan', '--paths', 'docs/a.md'],
            ['plan', '--dirs', 'docs/'],
            ['plan', '--dirs', 'docs/', '--exclude', 'docs/draft/'],
            ['apply', '--entries-json', '[]', '--format-command', 'x {file}'],
        ):
            try:
                module.parse_args(argv)
            except SystemExit as e:
                self.fail(f'fm_run.py が {argv} を受け付けない（SystemExit {e.code}）'
                          '。DES-008 §8.1')


class TestCheckTocArgumentContract(unittest.TestCase):
    """check-toc: 引数契約（DES-009）。列挙外の引数は受け取らない規定がある。"""

    @classmethod
    def setUpClass(cls):
        cls.skill_text = (PLUGIN_ROOT / 'skills' / 'check-toc' / 'SKILL.md').read_text(
            encoding='utf-8')

    def test_skill_documents_contract_flags(self):
        for flag in CHECK_TOC_CONTRACT:
            self.assertTrue(
                flag in self.skill_text,
                f'check-toc/SKILL.md が契約の引数 {flag} を記載していない')


if __name__ == '__main__':
    unittest.main()
