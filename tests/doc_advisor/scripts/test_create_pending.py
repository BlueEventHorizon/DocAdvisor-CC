#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_pending_yaml.py のユニットテスト。

テスト対象:
- --full モード（pending YAML 生成）
- --check モード（staleness check）
- 空ディレクトリの処理

移行元: test_setup_upgrade.sh の create_pending 関連テスト
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
CREATE_PENDING_SCRIPT = os.path.join(SCRIPTS_DIR, 'create_pending_yaml.py')


class TestCreatePendingBase(unittest.TestCase):
    """テスト用の共通セットアップ"""

    def setUp(self):
        """一時ディレクトリとテスト用プロジェクト構造を作成"""
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        # .git ディレクトリ作成（get_project_root() が認識するため）
        os.makedirs(os.path.join(self.project_root, '.git'))

        # .doc_structure.yaml 作成
        self._write_doc_structure()

        # ToC ディレクトリ作成
        self.toc_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'toc', 'rules'
        )
        os.makedirs(self.toc_dir, exist_ok=True)

    def tearDown(self):
        """一時ディレクトリを削除"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_doc_structure(self):
        """テスト用 .doc_structure.yaml を作成"""
        content = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/: spec
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""
        with open(os.path.join(self.project_root, '.doc_structure.yaml'), 'w') as f:
            f.write(content)

    def _create_rule_file(self, rel_path, content='# Test Rule\n\nThis is a test rule document.\n'):
        """rules/ 配下にテスト用 .md ファイルを作成"""
        full_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        return full_path

    def _run_create_pending(self, *extra_args, category='rules'):
        """create_pending_yaml.py を subprocess で実行"""
        cmd = [
            sys.executable, CREATE_PENDING_SCRIPT,
            '--category', category,
        ] + list(extra_args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )
        return result


class TestCreatePendingFull(TestCreatePendingBase):
    """--full モードのテスト"""

    def test_full_mode_creates_pending_yamls(self):
        """--full モードで pending YAML が生成されること"""
        self._create_rule_file('rules/test_rule.md')
        self._create_rule_file('rules/sub/nested_rule.md')

        result = self._run_create_pending('--full')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn('Created 2 pending YAMLs', result.stderr)

        # .toc_work ディレクトリが作成されていること
        work_dir = os.path.join(self.toc_dir, '.toc_work')
        self.assertTrue(os.path.isdir(work_dir), f".toc_work が作成されていない: {work_dir}")

        # YAML ファイルが存在すること（ハッシュベースのファイル名）
        yaml_files = [f for f in os.listdir(work_dir) if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yaml_files), 2, f"期待: 2件、実際: {yaml_files}")

    def test_full_mode_skips_empty_files(self):
        """--full モードで空ファイルがスキップされること"""
        self._create_rule_file('rules/empty.md', content='')
        self._create_rule_file('rules/headers_only.md', content='# Header Only\n\n## Sub Header\n')
        self._create_rule_file('rules/valid.md', content='# Valid\n\nSome content here.\n')

        result = self._run_create_pending('--full')

        self.assertEqual(result.returncode, 0)
        self.assertIn('Created 1 pending YAMLs', result.stderr)
        self.assertIn('Skipped', result.stderr)

    def test_full_mode_pending_yaml_content(self):
        """生成された pending YAML の内容が正しいこと"""
        self._create_rule_file('rules/test.md')

        result = self._run_create_pending('--full')
        self.assertEqual(result.returncode, 0)

        # pending YAML の中身を確認
        work_dir = os.path.join(self.toc_dir, '.toc_work')
        yaml_files = [f for f in os.listdir(work_dir) if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yaml_files), 1)

        with open(os.path.join(work_dir, yaml_files[0]), 'r') as f:
            content = f.read()

        self.assertIn('source_file: rules/test.md', content)
        self.assertIn('doc_type: rule', content)
        self.assertIn('status: pending', content)


class TestCreatePendingCheck(TestCreatePendingBase):
    """--check モード（staleness check）のテスト"""

    def test_check_mode_no_toc_file(self):
        """ToC ファイルが存在しない場合の --check モード"""
        self._create_rule_file('rules/test.md')

        result = self._run_create_pending('--check')

        self.assertEqual(result.returncode, 0)
        self.assertIn('WARNING: ToC not found', result.stderr)

    def test_check_mode_stale_detection(self):
        """変更があった場合に WARNING が出力されること"""
        # まず full モードで ToC 生成環境を構築
        self._create_rule_file('rules/test.md')
        self._run_create_pending('--full')

        # checksums ファイルを作成（空の checksums で新規ファイルとして検出させる）
        checksums_file = os.path.join(self.toc_dir, '.toc_checksums.yaml')
        with open(checksums_file, 'w') as f:
            f.write('checksums:\n')

        # rules_toc.yaml を作成（--check が ToC 存在確認するため）
        toc_file = os.path.join(self.toc_dir, 'rules_toc.yaml')
        with open(toc_file, 'w') as f:
            f.write('docs:\n  rules/test.md:\n    title: "Test"\n')

        result = self._run_create_pending('--check')

        self.assertEqual(result.returncode, 0)
        self.assertIn('WARNING: ToC may be stale', result.stderr)
        self.assertIn('1 new', result.stderr)


class TestCreatePendingEmptyDir(TestCreatePendingBase):
    """空ディレクトリの処理テスト"""

    def test_empty_root_dir(self):
        """root_dirs に指定されたディレクトリが空の場合"""
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)

        result = self._run_create_pending('--full')

        self.assertEqual(result.returncode, 0)
        self.assertIn('Created 0 pending YAMLs', result.stderr)

    def test_nonexistent_root_dir(self):
        """root_dirs に指定されたディレクトリが存在しない場合 → config_required エラー"""
        # rules/ ディレクトリを作成しない → ConfigNotReadyError

        result = self._run_create_pending('--full')

        self.assertEqual(result.returncode, 1)
        self.assertIn('config_required', result.stdout)


class TestHasSubstantiveContent(unittest.TestCase):
    """Unit tests for has_substantive_content()"""

    def setUp(self):
        """Add scripts dir to sys.path for direct import"""
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, content):
        """Write content to a temp file and return its path"""
        path = os.path.join(self.tmpdir, 'test.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_empty_file(self):
        """Empty file returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('')
        self.assertFalse(has_substantive_content(path))

    def test_whitespace_only(self):
        """File with only whitespace returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('   \n\n  \n')
        self.assertFalse(has_substantive_content(path))

    def test_frontmatter_only(self):
        """File with only frontmatter returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('---\ntitle: Test\ndate: 2024-01-01\n---\n')
        self.assertFalse(has_substantive_content(path))

    def test_frontmatter_and_headers_only(self):
        """File with frontmatter + headers but no body returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('---\ntitle: Test\n---\n\n# Header\n\n## Sub Header\n')
        self.assertFalse(has_substantive_content(path))

    def test_frontmatter_with_body(self):
        """File with frontmatter + body returns True"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('---\ntitle: Test\n---\n\n# Header\n\nSome actual content here.\n')
        self.assertTrue(has_substantive_content(path))

    def test_no_frontmatter_with_body(self):
        """File without frontmatter but with body returns True"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('# Header\n\nThis is body content.\n')
        self.assertTrue(has_substantive_content(path))

    def test_unclosed_frontmatter(self):
        """Unclosed frontmatter (missing closing ---) returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('---\ntitle: Test\nkey: value\nmore: data\n')
        self.assertFalse(has_substantive_content(path))

    def test_headers_only_no_frontmatter(self):
        """File with only headers (no frontmatter) returns False"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('# Header\n\n## Sub Header\n')
        self.assertFalse(has_substantive_content(path))

    def test_leading_blank_lines_before_frontmatter(self):
        """Leading blank lines before frontmatter are skipped correctly"""
        from create_pending_yaml import has_substantive_content
        path = self._write_file('\n\n---\ntitle: Test\n---\n\nBody text.\n')
        self.assertTrue(has_substantive_content(path))

    def test_nonexistent_file(self):
        """Nonexistent file returns False"""
        from create_pending_yaml import has_substantive_content
        self.assertFalse(has_substantive_content('/nonexistent/path/file.md'))


class TestDetermineDocType(unittest.TestCase):
    """Unit tests for determine_doc_type()"""

    def setUp(self):
        """Add scripts dir to sys.path and import the module"""
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)
        import create_pending_yaml as mod
        self.mod = mod
        # Save original globals
        self._orig_doc_types_map = mod.DOC_TYPES_MAP
        self._orig_category = mod.CATEGORY

    def tearDown(self):
        """Restore original globals"""
        self.mod.DOC_TYPES_MAP = self._orig_doc_types_map
        self.mod.CATEGORY = self._orig_category

    def test_direct_match_in_doc_types_map(self):
        """DOC_TYPES_MAP direct match returns the mapped type"""
        self.mod.DOC_TYPES_MAP = {'docs/design/': 'design'}
        self.mod.CATEGORY = 'specs'
        result = self.mod.determine_doc_type('docs/design/')
        self.assertEqual(result, 'design')

    def test_doc_types_map_trailing_slash_normalization(self):
        """Trailing slashes are normalized for DOC_TYPES_MAP matching"""
        self.mod.DOC_TYPES_MAP = {'specs/api': 'api'}
        self.mod.CATEGORY = 'specs'
        # Input with trailing slash should match entry without
        result = self.mod.determine_doc_type('specs/api/')
        self.assertEqual(result, 'api')

    def test_keyword_fallback(self):
        """DOC_TYPE_KEYWORDS fallback when DOC_TYPES_MAP has no match"""
        self.mod.DOC_TYPES_MAP = {}
        self.mod.CATEGORY = 'specs'
        result = self.mod.determine_doc_type('some/path/requirements')
        self.assertEqual(result, 'requirement')

    def test_keyword_fallback_case_insensitive(self):
        """DOC_TYPE_KEYWORDS lookup uses lowercase directory name"""
        self.mod.DOC_TYPES_MAP = {}
        self.mod.CATEGORY = 'specs'
        result = self.mod.determine_doc_type('project/Design/')
        self.assertEqual(result, 'design')

    def test_category_default_fallback(self):
        """Falls back to category-based default when no map or keyword matches"""
        self.mod.DOC_TYPES_MAP = {}
        self.mod.CATEGORY = 'rules'
        result = self.mod.determine_doc_type('some/unknown/directory')
        self.assertEqual(result, 'rule')

    def test_category_default_specs(self):
        """Category default for specs returns 'spec'"""
        self.mod.DOC_TYPES_MAP = {}
        self.mod.CATEGORY = 'specs'
        result = self.mod.determine_doc_type('random/dir')
        self.assertEqual(result, 'spec')

    def test_doc_types_map_takes_priority(self):
        """DOC_TYPES_MAP takes priority over DOC_TYPE_KEYWORDS"""
        # 'rules/' would match keyword 'rules' -> 'rule',
        # but DOC_TYPES_MAP should win with a custom type
        self.mod.DOC_TYPES_MAP = {'rules/': 'custom-rule-type'}
        self.mod.CATEGORY = 'rules'
        result = self.mod.determine_doc_type('rules/')
        self.assertEqual(result, 'custom-rule-type')

    def test_none_category_fallback(self):
        """When CATEGORY is None, fallback returns 'unknown'"""
        self.mod.DOC_TYPES_MAP = {}
        self.mod.CATEGORY = None
        result = self.mod.determine_doc_type('no/match/here')
        self.assertEqual(result, 'unknown')


# ===========================================================================
# determine_doc_type() パラメータ経由テスト（TASK-001: グローバル変数依存排除）
# ===========================================================================

class TestDetermineDocTypeWithParams(unittest.TestCase):
    """determine_doc_type() を doc_types_map / category パラメータ経由で呼び出すテスト。
    グローバル変数に依存せず、パラメータ経由で設定を渡して正常動作することを確認する。
    """

    def setUp(self):
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)

    def test_direct_match_via_param(self):
        """doc_types_map パラメータ経由で直接マッチする"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'docs/design/',
            doc_types_map={'docs/design/': 'design'},
            category='specs',
        )
        self.assertEqual(result, 'design')

    def test_trailing_slash_normalization_via_param(self):
        """パラメータ経由でもトレイリングスラッシュが正規化される"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'specs/api/',
            doc_types_map={'specs/api': 'api'},
            category='specs',
        )
        self.assertEqual(result, 'api')

    def test_keyword_fallback_via_param(self):
        """doc_types_map が空辞書の場合、キーワードフォールバックが動作する"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'some/path/requirements',
            doc_types_map={},
            category='specs',
        )
        self.assertEqual(result, 'requirement')

    def test_category_default_via_param(self):
        """マッチしない場合に category パラメータからデフォルト値が生成される"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'some/unknown/dir',
            doc_types_map={},
            category='rules',
        )
        self.assertEqual(result, 'rule')

    def test_category_none_via_param(self):
        """category=None の場合は 'unknown' が返る"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'no/match',
            doc_types_map={},
            category=None,
        )
        self.assertEqual(result, 'unknown')

    def test_empty_doc_types_map_via_param(self):
        """空辞書のパラメータでもエラーにならない"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'project/Design/',
            doc_types_map={},
            category='specs',
        )
        self.assertEqual(result, 'design')

    def test_doc_types_map_priority_via_param(self):
        """doc_types_map パラメータがキーワードフォールバックより優先される"""
        from create_pending_yaml import determine_doc_type
        result = determine_doc_type(
            'rules/',
            doc_types_map={'rules/': 'custom-type'},
            category='rules',
        )
        self.assertEqual(result, 'custom-type')


if __name__ == '__main__':
    unittest.main()
