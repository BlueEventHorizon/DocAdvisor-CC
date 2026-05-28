#!/usr/bin/env python3
"""
classify_dirs.py のテスト

ディレクトリスキャン、front matter パース、メタデータ収集をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.doc_structure.test_classify_dirs -v
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

# テスト共通ヘルパー
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from forge.helpers import _FsTestCase

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'scripts' / 'doc_structure'))

from classify_dirs import (
    SKIP_DIRS,
    SKIP_INDICATORS,
    extract_front_matter,
    is_readme_only,
    find_md_dirs,
    scan_directories,
    output_scan,
)


# =========================================================================
# 1. Front matter パーステスト
# =========================================================================

class TestExtractFrontMatter(_FsTestCase):
    """extract_front_matter のテスト"""

    def test_valid_front_matter(self):
        f = self._write_file('doc.md', '---\ndoc_type: requirement\ntitle: Test\n---\n# Body')
        fm = extract_front_matter(f)
        self.assertIsNotNone(fm)
        self.assertEqual(fm['doc_type'], 'requirement')
        self.assertEqual(fm['title'], 'Test')

    def test_no_front_matter(self):
        f = self._write_file('doc.md', '# Just markdown\nNo front matter here.')
        fm = extract_front_matter(f)
        self.assertIsNone(fm)

    def test_empty_file(self):
        f = self._write_file('doc.md', '')
        fm = extract_front_matter(f)
        self.assertIsNone(fm)

    def test_incomplete_front_matter(self):
        """閉じ --- がない場合"""
        f = self._write_file('doc.md', '---\ndoc_type: requirement\nNo closing')
        fm = extract_front_matter(f)
        self.assertIsNone(fm)

    def test_quoted_values(self):
        f = self._write_file('doc.md', '---\ntitle: "Quoted Value"\n---\n')
        fm = extract_front_matter(f)
        self.assertEqual(fm['title'], 'Quoted Value')

    def test_nonexistent_file(self):
        fm = extract_front_matter(self.tmpdir / 'nonexistent.md')
        self.assertIsNone(fm)

    def test_comment_lines_skipped(self):
        f = self._write_file('doc.md', '---\n# comment\ndoc_type: design\n---\n')
        fm = extract_front_matter(f)
        self.assertEqual(fm['doc_type'], 'design')
        self.assertNotIn('#', fm)


# =========================================================================
# 2. ファイルシステム探索テスト
# =========================================================================

class TestIsReadmeOnly(_FsTestCase):
    """is_readme_only のテスト"""

    def test_readme_only(self):
        self._write_file('docs/README.md', '# Readme')
        self.assertTrue(is_readme_only(str(self.tmpdir), 'docs'))

    def test_readme_and_changelog(self):
        self._write_file('docs/README.md', '# Readme')
        self._write_file('docs/CHANGELOG.md', '# Changes')
        self.assertTrue(is_readme_only(str(self.tmpdir), 'docs'))

    def test_not_readme_only(self):
        self._write_file('docs/README.md', '# Readme')
        self._write_file('docs/guide.md', '# Guide')
        self.assertFalse(is_readme_only(str(self.tmpdir), 'docs'))

    def test_case_insensitive(self):
        """README.md は大文字小文字を区別しない"""
        self._write_file('docs/readme.md', '# Readme')
        self.assertTrue(is_readme_only(str(self.tmpdir), 'docs'))


class TestFindMdDirs(_FsTestCase):
    """find_md_dirs のテスト"""

    def test_find_dirs(self):
        self._write_file('docs/guide.md', '# Guide')
        self._write_file('specs/req.md', '# Req')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertIn('docs', dirs)
        self.assertIn('specs', dirs)

    def test_skip_dirs(self):
        """SKIP_DIRS に含まれるディレクトリは除外"""
        self._write_file('.git/info.md', 'internal')
        self._write_file('node_modules/pkg/README.md', 'pkg')
        self._write_file('docs/guide.md', '# Guide')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertNotIn('.git', dirs)
        self.assertNotIn('node_modules/pkg', dirs)
        self.assertIn('docs', dirs)

    def test_skip_project_indicators(self):
        """SKIP_INDICATORS を含むディレクトリは除外"""
        self._write_file('frontend/package.json', '{}')
        self._write_file('frontend/README.md', '# Frontend')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertNotIn('frontend', dirs)

    def test_root_not_included(self):
        """ルートディレクトリ自体は含まれない"""
        self._write_file('README.md', '# Root')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertNotIn('.', dirs)

    def test_empty_project(self):
        result = find_md_dirs(str(self.tmpdir))
        self.assertEqual(result, [])

    def test_md_count(self):
        self._write_file('docs/a.md', '# A')
        self._write_file('docs/b.md', '# B')
        self._write_file('docs/c.md', '# C')
        result = find_md_dirs(str(self.tmpdir))
        docs_entry = [r for r in result if r[0] == 'docs']
        self.assertEqual(len(docs_entry), 1)
        self.assertEqual(docs_entry[0][1], 3)

    def test_symlink_loop_no_infinite_walk(self):
        """シンボリックリンクループで無限ループ・重複しない"""
        self._write_file('docs/guide.md', '# Guide')
        loop_link = self.tmpdir / 'docs' / 'self'
        try:
            os.symlink(str(self.tmpdir / 'docs'), str(loop_link))
        except (OSError, NotImplementedError):
            self.skipTest('symlink を作成できない環境')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertEqual(dirs.count('docs'), 1)

    def test_symlink_to_parent_no_infinite_walk(self):
        """親ディレクトリへの symlink でも無限ループしない"""
        self._write_file('docs/guide.md', '# Guide')
        loop_link = self.tmpdir / 'docs' / 'parent'
        try:
            os.symlink(str(self.tmpdir), str(loop_link))
        except (OSError, NotImplementedError):
            self.skipTest('symlink を作成できない環境')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertEqual(dirs.count('docs'), 1)

    def test_symlink_target_discovered(self):
        """シンボリックリンク先のディレクトリが発見される"""
        # プロジェクト外のディレクトリを作成し、プロジェクト内からシンボリックリンク
        external_dir = Path(tempfile.mkdtemp())
        try:
            (external_dir / 'guide.md').write_text('# Guide', encoding='utf-8')
            link_path = self.tmpdir / 'linked_docs'
            try:
                os.symlink(str(external_dir), str(link_path))
            except (OSError, NotImplementedError):
                self.skipTest('symlink を作成できない環境')
            result = find_md_dirs(str(self.tmpdir))
            dirs = [d for d, _ in result]
            self.assertIn('linked_docs', dirs)
        finally:
            shutil.rmtree(external_dir, ignore_errors=True)

    def test_shallow_scan_stops_at_md_dir(self):
        """浅いスキャン: .md があるディレクトリの配下は探索しない"""
        self._write_file('specs/overview.md', '# Overview')
        self._write_file('specs/login/requirements/req.md', '# Req')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        # specs/ で .md が見つかるので specs/login/requirements/ は報告されない
        self.assertIn('specs', dirs)
        self.assertNotIn('specs/login/requirements', dirs)

    def test_shallow_scan_sibling_dirs_independent(self):
        """浅いスキャン: 兄弟ディレクトリは独立して探索"""
        self._write_file('rules/coding/style.md', '# Style')
        self._write_file('rules/naming/names.md', '# Names')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        # rules/ に .md がないので、各サブディレクトリが個別に報告される
        self.assertIn('rules/coding', dirs)
        self.assertIn('rules/naming', dirs)
        self.assertNotIn('rules', dirs)

    def test_shallow_scan_parent_with_md_blocks_children(self):
        """浅いスキャン: 親に .md があれば子は報告されない"""
        self._write_file('docs/guide.md', '# Guide')
        self._write_file('docs/sub/detail.md', '# Detail')
        result = find_md_dirs(str(self.tmpdir))
        dirs = [d for d, _ in result]
        self.assertIn('docs', dirs)
        self.assertNotIn('docs/sub', dirs)


# =========================================================================
# 3. スキャン・メタデータ収集テスト
# =========================================================================

class TestScanDirectories(_FsTestCase):
    """scan_directories のテスト"""

    def test_basic_scan(self):
        """標準的なスキャン結果の構造"""
        self._write_file('docs/guide.md', '# Guide')
        result = scan_directories(str(self.tmpdir))
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry['dir'], 'docs')
        self.assertEqual(entry['md_count'], 1)
        self.assertIsInstance(entry['readme_only'], bool)
        self.assertIsInstance(entry['path_components'], list)
        self.assertIn('frontmatter_doc_types', entry)

    def test_readme_only_flagged(self):
        """readme_only フラグが正しく設定される"""
        self._write_file('docs/README.md', '# Readme')
        self._write_file('specs/req.md', '# Req')
        result = scan_directories(str(self.tmpdir))
        docs = [r for r in result if r['dir'] == 'docs'][0]
        specs = [r for r in result if r['dir'] == 'specs'][0]
        self.assertTrue(docs['readme_only'])
        self.assertFalse(specs['readme_only'])

    def test_frontmatter_collected(self):
        """frontmatter の doc_type 値が収集される"""
        self._write_file('docs/r1.md', '---\ndoc_type: rule\n---\n# Rule 1')
        self._write_file('docs/r2.md', '---\ndoc_type: rule\n---\n# Rule 2')
        self._write_file('docs/plain.md', '# No frontmatter')
        result = scan_directories(str(self.tmpdir))
        entry = result[0]
        self.assertEqual(entry['frontmatter_doc_types'], ['rule', 'rule'])

    def test_no_frontmatter_is_none(self):
        """frontmatter がないディレクトリは None"""
        self._write_file('docs/guide.md', '# Guide')
        result = scan_directories(str(self.tmpdir))
        self.assertIsNone(result[0]['frontmatter_doc_types'])

    def test_path_components(self):
        """path_components が正しく分割される"""
        self._write_file('rules/coding/style.md', '# Style')
        result = scan_directories(str(self.tmpdir))
        entry = [r for r in result if r['dir'] == 'rules/coding'][0]
        self.assertEqual(entry['path_components'], ['rules', 'coding'])

    def test_skip_prefixes(self):
        """--skip で指定されたディレクトリが除外される"""
        self._write_file('docs/guide.md', '# Guide')
        self._write_file('extra/notes/memo.md', '# Memo')
        result_all = scan_directories(str(self.tmpdir))
        result_skip = scan_directories(str(self.tmpdir), skip_prefixes=['extra'])
        dirs_all = [r['dir'] for r in result_all]
        dirs_skip = [r['dir'] for r in result_skip]
        self.assertIn('extra/notes', dirs_all)
        self.assertNotIn('extra/notes', dirs_skip)
        self.assertIn('docs', dirs_skip)

    def test_empty_project(self):
        """.md なしの場合は空リスト"""
        result = scan_directories(str(self.tmpdir))
        self.assertEqual(result, [])

    def test_mixed_frontmatter(self):
        """同一ディレクトリ内で異なる doc_type が混在"""
        self._write_file('docs/r.md', '---\ndoc_type: rule\n---\n')
        self._write_file('docs/d.md', '---\ndoc_type: design\n---\n')
        result = scan_directories(str(self.tmpdir))
        doc_types = result[0]['frontmatter_doc_types']
        self.assertEqual(len(doc_types), 2)
        self.assertIn('rule', doc_types)
        self.assertIn('design', doc_types)


class TestOutputScan(_FsTestCase):
    """output_scan のテスト"""

    def _capture(self, project_root, directories):
        buf = io.StringIO()
        with redirect_stdout(buf):
            output_scan(project_root, directories)
        return buf.getvalue()

    def test_valid_json(self):
        """出力が有効な JSON"""
        output = self._capture('/tmp/project', [
            {'dir': 'docs', 'md_count': 1, 'readme_only': False,
             'path_components': ['docs'], 'frontmatter_doc_types': None},
        ])
        parsed = json.loads(output)
        self.assertIn('project_root', parsed)
        self.assertIn('directories', parsed)

    def test_output_keys(self):
        """必須キーの存在"""
        output = self._capture('/tmp/project', [
            {'dir': 'docs', 'md_count': 2, 'readme_only': True,
             'path_components': ['docs'], 'frontmatter_doc_types': ['rule']},
        ])
        parsed = json.loads(output)
        entry = parsed['directories'][0]
        self.assertEqual(entry['dir'], 'docs')
        self.assertEqual(entry['md_count'], 2)
        self.assertTrue(entry['readme_only'])
        self.assertEqual(entry['path_components'], ['docs'])
        self.assertEqual(entry['frontmatter_doc_types'], ['rule'])

    def test_empty_directories(self):
        """空の場合の出力"""
        output = self._capture('/tmp/project', [])
        parsed = json.loads(output)
        self.assertEqual(parsed['directories'], [])

    def test_ensure_ascii_false(self):
        """日本語パスが正しく出力される"""
        output = self._capture('/tmp/project', [
            {'dir': 'ドキュメント', 'md_count': 1, 'readme_only': False,
             'path_components': ['ドキュメント'], 'frontmatter_doc_types': None},
        ])
        self.assertIn('ドキュメント', output)
        parsed = json.loads(output)
        self.assertEqual(parsed['directories'][0]['dir'], 'ドキュメント')


# =========================================================================
# 4. 定数の健全性テスト
# =========================================================================

class TestConstants(unittest.TestCase):
    """定数の健全性を検証"""

    def test_skip_dirs_no_path_separator(self):
        """SKIP_DIRS にパス区切りが含まれていない"""
        for d in SKIP_DIRS:
            self.assertFalse('/' in d, f'SKIP_DIRS にパス区切り: {d}')

    def test_skip_indicators_are_filenames(self):
        for ind in SKIP_INDICATORS:
            self.assertFalse('/' in ind,
                             f'SKIP_INDICATORS にパス区切り: {ind}')


if __name__ == '__main__':
    unittest.main()
