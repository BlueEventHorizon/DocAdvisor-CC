#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エッジケーステスト。

test_edge_cases.sh からの移行:
- 日本語ファイル名の処理
- 特殊文字を含むコンテンツ
- 深いネスト（5レベル）のファイル検出
- root_dirs: [] 空配列でクラッシュしないこと
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
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
    """root_dirs: [] 空配列でクラッシュしないことのテスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, '.git'))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_doc_structure(self, content):
        path = os.path.join(self.tmpdir, '.doc_structure.yaml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def test_empty_root_dirs_load_config(self):
        """root_dirs: [] でも load_config がクラッシュしない"""
        self._write_doc_structure("""\
# doc_structure_version: 3.0
rules:
  root_dirs: []
  patterns:
    target_glob: "**/*.md"
    exclude: []
""")
        with patch.object(Path, 'cwd', return_value=Path(self.tmpdir)):
            config = toc_utils.load_config('rules')
        self.assertEqual(config['root_dirs'], [])

    def test_empty_root_dirs_expand_globs(self):
        """空の root_dirs で expand_root_dir_globs がクラッシュしない"""
        result = toc_utils.expand_root_dir_globs([], Path(self.tmpdir))
        self.assertEqual(result, [])

    def test_empty_root_dirs_rglob(self):
        """存在しないディレクトリで rglob_follow_symlinks がクラッシュしない"""
        nonexistent = Path(self.tmpdir) / 'nonexistent'
        files = list(toc_utils.rglob_follow_symlinks(nonexistent, '**/*.md'))
        self.assertEqual(files, [])


# ===========================================================================
# expand_root_dir_globs additional tests
# ===========================================================================

class TestExpandRootDirGlobs(unittest.TestCase):
    """expand_root_dir_globs() additional test cases."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_non_glob_passthrough(self):
        """Non-glob directory is returned as-is."""
        result = toc_utils.expand_root_dir_globs(
            ['docs/rules/'], Path(self.tmpdir)
        )
        self.assertEqual(result, ['docs/rules/'])

    def test_glob_match_expanded(self):
        """Glob directory with matches is expanded."""
        for name in ('app1', 'app2'):
            (Path(self.tmpdir) / 'specs' / name / 'requirements').mkdir(parents=True)
        result = toc_utils.expand_root_dir_globs(
            ['specs/*/requirements/'], Path(self.tmpdir)
        )
        self.assertIn('specs/app1/requirements/', result)
        self.assertIn('specs/app2/requirements/', result)
        self.assertEqual(len(result), 2)

    def test_glob_no_match_returns_original(self):
        """Glob directory with no matches returns the original list."""
        result = toc_utils.expand_root_dir_globs(
            ['nonexistent/*/foo/'], Path(self.tmpdir)
        )
        # When expanded list is empty, original dirs are returned as fallback
        self.assertEqual(result, ['nonexistent/*/foo/'])


# ===========================================================================
# Integration: init_common_config with glob patterns
# ===========================================================================

class TestInitCommonConfigGlobExpansion(unittest.TestCase):
    """Integration test: init_common_config() expands glob patterns in doc_types_map."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, '.git'))
        # Create directory structure matching globs
        for name in ('core', 'ui'):
            os.makedirs(os.path.join(self.tmpdir, 'specs', name, 'design'))
        # Write .doc_structure.yaml with glob patterns
        doc_structure = """\
# doc_structure_version: 3.0

specs:
  root_dirs:
    - specs/*/design/
  doc_types_map:
    specs/*/design/: design
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""
        with open(os.path.join(self.tmpdir, '.doc_structure.yaml'), 'w') as f:
            f.write(doc_structure)
        self.original_env = os.environ.get('CLAUDE_PROJECT_DIR')
        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self.original_env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self.original_env

    def test_doc_types_map_expanded_in_init_common_config(self):
        """init_common_config() returns expanded doc_types_map with concrete paths."""
        result = toc_utils.init_common_config('specs')
        doc_types_map = result['doc_types_map']
        # Glob pattern should be expanded to concrete paths
        self.assertNotIn('specs/*/design/', doc_types_map)
        self.assertIn('specs/core/design/', doc_types_map)
        self.assertIn('specs/ui/design/', doc_types_map)
        self.assertEqual(doc_types_map['specs/core/design/'], 'design')
        self.assertEqual(doc_types_map['specs/ui/design/'], 'design')


class TestConfigNotReadyError(unittest.TestCase):
    """ConfigNotReadyError validation in init_common_config()"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch.object(toc_utils, 'get_project_root')
    def test_raises_when_no_config_and_no_default_dir(self, mock_root):
        """No .doc_structure.yaml + no rules/ dir → ConfigNotReadyError"""
        mock_root.return_value = Path(self.tmpdir)
        # No .doc_structure.yaml, no rules/ directory
        with self.assertRaises(toc_utils.ConfigNotReadyError):
            toc_utils.init_common_config('rules')

    @patch.object(toc_utils, 'get_project_root')
    def test_no_error_when_default_dir_exists(self, mock_root):
        """No .doc_structure.yaml but rules/ dir exists → no error (uses default)"""
        mock_root.return_value = Path(self.tmpdir)
        os.makedirs(os.path.join(self.tmpdir, 'rules'))
        # Should not raise — default dir exists
        result = toc_utils.init_common_config('rules')
        self.assertIn('root_dirs', result)

    @patch.object(toc_utils, 'get_project_root')
    def test_no_error_when_config_has_root_dirs(self, mock_root):
        """Configured .doc_structure.yaml with root_dirs → no error"""
        mock_root.return_value = Path(self.tmpdir)
        docs_dir = os.path.join(self.tmpdir, 'docs', 'rules')
        os.makedirs(docs_dir)
        config_path = os.path.join(self.tmpdir, '.doc_structure.yaml')
        with open(config_path, 'w') as f:
            f.write('rules:\n  root_dirs:\n    - docs/rules/\n')
        result = toc_utils.init_common_config('rules')
        self.assertIn('root_dirs', result)


if __name__ == '__main__':
    unittest.main()
