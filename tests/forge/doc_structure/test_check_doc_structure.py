#!/usr/bin/env python3
"""
check_doc_structure.py のテスト

実行:
    python3 -m unittest tests.forge.doc_structure.test_check_doc_structure -v
"""
import sys
import unittest
from pathlib import Path

# テスト対象のスクリプトパスを追加
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'scripts' / 'doc_structure'
sys.path.insert(0, str(SCRIPTS_DIR))

from check_doc_structure import check

# テストヘルパー
sys.path.insert(0, str(REPO_ROOT / 'tests' / 'forge'))
from helpers import _FsTestCase


class TestCheck(_FsTestCase):
    """check() 関数のテスト"""

    def test_file_not_exists(self):
        """ファイルが存在しない場合"""
        result = check(self.tmpdir)
        self.assertFalse(result['exists'])
        self.assertNotIn('needs_migration', result)

    def test_v3_no_migration(self):
        """v3 ファイルはマイグレーション不要"""
        content = '# doc_structure_version: 3.0\nrules:\n  root_dirs:\n    - docs/rules/\n'
        self._write_file('.doc_structure.yaml', content)
        result = check(self.tmpdir)
        self.assertTrue(result['exists'])
        self.assertFalse(result['needs_migration'])
        self.assertEqual(result['detected_version'], 3)
        self.assertEqual(result['current_version'], 3)
        self.assertEqual(result['content'], content)

    def test_v2_needs_migration(self):
        """v2 ファイルはマイグレーション必要"""
        content = '# doc_structure_version: 2.0\nrules:\n  root_dirs:\n    - docs/rules/\n'
        self._write_file('.doc_structure.yaml', content)
        result = check(self.tmpdir)
        self.assertTrue(result['exists'])
        self.assertTrue(result['needs_migration'])
        self.assertEqual(result['detected_version'], 2)
        self.assertEqual(result['current_version'], 3)

    def test_v1_needs_migration(self):
        """v1 ファイルはマイグレーション必要"""
        content = 'version: "1.0"\nspecs:\n  design:\n    paths: [docs/]\n'
        self._write_file('.doc_structure.yaml', content)
        result = check(self.tmpdir)
        self.assertTrue(result['exists'])
        self.assertTrue(result['needs_migration'])
        self.assertEqual(result['detected_version'], 1)

    def test_future_version_no_migration(self):
        """将来バージョンはマイグレーション不要"""
        content = '# doc_structure_version: 5.0\nrules:\n  root_dirs:\n    - rules/\n'
        self._write_file('.doc_structure.yaml', content)
        result = check(self.tmpdir)
        self.assertTrue(result['exists'])
        self.assertFalse(result['needs_migration'])
        self.assertEqual(result['detected_version'], 5)

    def test_content_included(self):
        """結果にファイル内容が含まれる"""
        content = '# doc_structure_version: 3.0\nspecs:\n  root_dirs:\n    - specs/\n'
        self._write_file('.doc_structure.yaml', content)
        result = check(self.tmpdir)
        self.assertIn('content', result)
        self.assertEqual(result['content'], content)

    def test_unreadable_file(self):
        """読み取り不能ファイルの場合 error を返す"""
        filepath = Path(self.tmpdir) / '.doc_structure.yaml'
        filepath.write_text('test', encoding='utf-8')
        filepath.chmod(0o000)
        try:
            result = check(self.tmpdir)
            self.assertTrue(result['exists'])
            self.assertIn('error', result)
        finally:
            filepath.chmod(0o644)


if __name__ == '__main__':
    unittest.main()
