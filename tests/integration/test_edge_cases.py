#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エッジケーステスト。

test_edge_cases.sh からの移行:
- 日本語ファイル名の処理
- 特殊文字を含むコンテンツ
- 深いネスト（5レベル）のファイル検出
- 存在しないディレクトリでクラッシュしないこと

注: 旧 doc_structure 依存のテスト（load_config / expand_root_dir_globs /
init_common_config / ConfigNotReadyError）は REQ-004 §6.2 の clean break で
当該ロジックが削除されたため除去済み（TASK-008）。
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import toc_utils


class TestJapaneseFilenames(unittest.TestCase):
    """日本語ファイル名の処理テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, '.git'))
        # 日本語ファイル名を含むディレクトリ構造を作成
        rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(rules_dir, exist_ok=True)
        with open(os.path.join(rules_dir, '日本語ルール.md'), 'w', encoding='utf-8') as f:
            f.write('# 日本語ルール\n\nこのファイルはテスト用です。\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_japanese_filename_detected(self):
        """日本語ファイル名が rglob_follow_symlinks で検出される"""
        rules_dir = Path(self.tmpdir) / 'rules'
        files = list(toc_utils.rglob_follow_symlinks(rules_dir, '**/*.md'))
        self.assertEqual(len(files), 1)
        self.assertIn('日本語ルール.md', str(files[0]))

    def test_japanese_filename_normalize_path(self):
        """日本語パスが NFC 正規化される"""
        import unicodedata
        # NFD 形式の「プラグイン」
        nfd_text = unicodedata.normalize('NFD', 'プラグイン')
        nfc_text = unicodedata.normalize('NFC', 'プラグイン')
        result = toc_utils.normalize_path(nfd_text)
        self.assertEqual(result, nfc_text)

    def test_should_exclude_japanese_dir(self):
        """日本語ディレクトリ名の exclude が機能する"""
        base = Path(self.tmpdir) / 'rules'
        jp_dir = base / 'テスト除外'
        jp_dir.mkdir(parents=True, exist_ok=True)
        test_file = jp_dir / 'test.md'
        test_file.write_text('# test', encoding='utf-8')

        result = toc_utils.should_exclude(test_file, base, ['テスト除外'])
        self.assertTrue(result)


class TestSpecialCharacters(unittest.TestCase):
    """特殊文字を含むコンテンツのテスト"""

    def test_yaml_escape_special_chars(self):
        """特殊文字が正しくエスケープされる"""
        # コロン+スペース
        result = toc_utils.yaml_escape('foo: bar')
        self.assertTrue(result.startswith('"'))

        # アンパサンドで始まる
        result = toc_utils.yaml_escape('&reference')
        self.assertTrue(result.startswith('"'))

        # パイプ文字で始まる
        result = toc_utils.yaml_escape('|literal')
        self.assertTrue(result.startswith('"'))

    def test_yaml_escape_quotes_in_content(self):
        """引用符を含むコンテンツが正しくエスケープされる"""
        result = toc_utils.yaml_escape('Special: "quotes" & ampersand')
        self.assertTrue(result.startswith('"'))
        # ダブルクォートがエスケープされていること
        self.assertIn('\\"', result)

    def test_yaml_escape_plain_text_not_quoted(self):
        """プレーンテキストはクォートされない"""
        result = toc_utils.yaml_escape('normal text')
        self.assertFalse(result.startswith('"'))

    def test_yaml_escape_empty_string(self):
        """空文字列はクォートされる"""
        result = toc_utils.yaml_escape('')
        self.assertEqual(result, '""')


class TestDeepNesting(unittest.TestCase):
    """深いネスト（5レベル）のファイル検出テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 5レベルの深いディレクトリを作成
        deep_dir = os.path.join(self.tmpdir, 'rules', 'a', 'b', 'c', 'd', 'e')
        os.makedirs(deep_dir, exist_ok=True)
        with open(os.path.join(deep_dir, 'deep_rule.md'), 'w', encoding='utf-8') as f:
            f.write('# Deep Rule\n\n5階層の深いルール。\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_deep_nested_file_found(self):
        """5レベルの深さのファイルが検出される"""
        rules_dir = Path(self.tmpdir) / 'rules'
        files = list(toc_utils.rglob_follow_symlinks(rules_dir, '**/*.md'))
        self.assertEqual(len(files), 1)
        self.assertIn('deep_rule.md', str(files[0]))

    def test_deep_nested_file_relative_path(self):
        """深いファイルの相対パスが正しい"""
        rules_dir = Path(self.tmpdir) / 'rules'
        files = list(toc_utils.rglob_follow_symlinks(rules_dir, '**/*.md'))
        rel_path = str(files[0].relative_to(rules_dir))
        # パスの区切り文字を統一して検証
        parts = Path(rel_path).parts
        self.assertEqual(parts, ('a', 'b', 'c', 'd', 'e', 'deep_rule.md'))


class TestEmptyRootDirs(unittest.TestCase):
    """存在しないディレクトリでクラッシュしないことのテスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_empty_root_dirs_rglob(self):
        """存在しないディレクトリで rglob_follow_symlinks がクラッシュしない"""
        nonexistent = Path(self.tmpdir) / 'nonexistent'
        files = list(toc_utils.rglob_follow_symlinks(nonexistent, '**/*.md'))
        self.assertEqual(files, [])


if __name__ == '__main__':
    unittest.main()
