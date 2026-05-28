#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_toc.py のユニットテスト。

bash テスト test_merge.sh から移行。
subprocess.run でスクリプトを呼び出す形式でテスト。
"""

import os
import sys
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
MERGE_SCRIPT = os.path.join(SCRIPTS_DIR, 'merge_toc.py')


class TestMergeTocBase(unittest.TestCase):
    """merge_toc.py テストの基底クラス。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self.original_env[key] = os.environ.get(key)

        # プロジェクトルート設定
        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir
        os.environ['CLAUDE_PLUGIN_ROOT'] = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor'
        ))

        # .doc_structure.yaml 作成
        doc_structure = """\
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
        with open(os.path.join(self.tmpdir, '.doc_structure.yaml'), 'w') as f:
            f.write(doc_structure)

        # rules/ ディレクトリとテスト用 .md ファイル
        rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(rules_dir, exist_ok=True)
        with open(os.path.join(rules_dir, 'coding_standards.md'), 'w') as f:
            f.write('# Coding Standards\n\nDefine coding practices.\n')

        # specs/ ディレクトリとテスト用 .md ファイル
        specs_dir = os.path.join(self.tmpdir, 'specs')
        os.makedirs(specs_dir, exist_ok=True)
        with open(os.path.join(specs_dir, 'auth_spec.md'), 'w') as f:
            f.write('# Auth Spec\n\nAuthentication requirements.\n')
        with open(os.path.join(specs_dir, 'login_spec.md'), 'w') as f:
            f.write('# Login Spec\n\nLogin requirements.\n')

        # ToC 出力ディレクトリ
        for cat in ('rules', 'specs'):
            os.makedirs(os.path.join(self.tmpdir, '.claude', 'doc-advisor', 'toc', cat), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run_merge(self, category, mode='full', delete_only=False):
        """merge_toc.py を subprocess で実行する。"""
        cmd = [sys.executable, MERGE_SCRIPT, '--category', category]
        if delete_only:
            cmd.append('--delete-only')
        else:
            cmd.extend(['--mode', mode])
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )

    def _create_pending_entry(self, category, source_file, title='Test Title',
                              doc_type='rule', status='completed'):
        """pending YAML エントリを手動作成する。"""
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', category, '.toc_work'
        )
        os.makedirs(work_dir, exist_ok=True)

        safe_name = source_file.replace('/', '_').replace('.', '_') + '.yaml'
        entry_path = os.path.join(work_dir, safe_name)

        content = f"""\
_meta:
  source_file: {source_file}
  doc_type: {doc_type}
  status: {status}
  updated_at: "2026-01-31T00:00:00Z"

title: {title}
purpose: Test purpose for {title}
content_details:
  - Detail 1
  - Detail 2
  - Detail 3
  - Detail 4
  - Detail 5
applicable_tasks:
  - Task 1
keywords:
  - keyword1
  - keyword2
  - keyword3
  - keyword4
  - keyword5
"""
        with open(entry_path, 'w') as f:
            f.write(content)
        return entry_path


# ===========================================================================
# full モード マージテスト
# ===========================================================================

class TestMergeTocFullMode(TestMergeTocBase):
    """full モードのマージテスト。"""

    def test_full_mode_rules_exit_code(self):
        """rules full モードが正常終了する"""
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        proc = self._run_merge('rules', mode='full')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

    def test_full_mode_rules_output_created(self):
        """rules_toc.yaml が作成される"""
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        self._run_merge('rules', mode='full')
        toc_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', 'rules_toc.yaml'
        )
        self.assertTrue(os.path.exists(toc_path))

    def test_full_mode_rules_has_docs_section(self):
        """rules_toc.yaml に docs セクションがある"""
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        self._run_merge('rules', mode='full')
        toc_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', 'rules_toc.yaml'
        )
        with open(toc_path, 'r') as f:
            content = f.read()
        self.assertIn('docs:', content)

    def test_full_mode_specs_exit_code(self):
        """specs full モードが正常終了する"""
        self._create_pending_entry('specs', 'specs/auth_spec.md', 'Auth Spec', doc_type='spec')
        proc = self._run_merge('specs', mode='full')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

    def test_full_mode_specs_has_doc_type(self):
        """specs_toc.yaml に doc_type フィールドがある"""
        self._create_pending_entry('specs', 'specs/auth_spec.md', 'Auth Spec', doc_type='spec')
        self._run_merge('specs', mode='full')
        toc_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'specs', 'specs_toc.yaml'
        )
        with open(toc_path, 'r') as f:
            content = f.read()
        self.assertIn('doc_type:', content)


# ===========================================================================
# incremental モード マージテスト
# ===========================================================================

class TestMergeTocIncrementalMode(TestMergeTocBase):
    """incremental モードのマージテスト。"""

    def test_incremental_mode_merges_with_existing(self):
        """incremental モードで既存エントリに新規エントリが追加される"""
        # 1. full モードで初期 ToC 作成
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        self._run_merge('rules', mode='full')

        # 2. .toc_work をクリアし新規ソースファイルと pending エントリ追加
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        shutil.rmtree(work_dir, ignore_errors=True)

        # 新規ソースファイル作成
        with open(os.path.join(self.tmpdir, 'rules', 'new_rule.md'), 'w') as f:
            f.write('# New Rule\n\nNew rule content.\n')

        self._create_pending_entry('rules', 'rules/new_rule.md', 'New Rule')

        # 3. incremental マージ
        proc = self._run_merge('rules', mode='incremental')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

        # 4. 両エントリが存在すること
        toc_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', 'rules_toc.yaml'
        )
        with open(toc_path, 'r') as f:
            content = f.read()
        self.assertIn('rules/coding_standards.md', content)
        self.assertIn('rules/new_rule.md', content)

    def test_incremental_exit_code(self):
        """incremental モードが正常終了する"""
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        proc = self._run_merge('rules', mode='incremental')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')


# ===========================================================================
# delete-only モード テスト
# ===========================================================================

class TestMergeTocDeleteOnly(TestMergeTocBase):
    """delete-only モードのテスト。"""

    def test_delete_only_removes_deleted_file_entry(self):
        """削除されたファイルのエントリが ToC から除去される"""
        # 1. full モードで ToC 作成
        self._create_pending_entry('rules', 'rules/coding_standards.md', 'Coding Standards')
        self._run_merge('rules', mode='full')

        # 2. .toc_work クリア
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        shutil.rmtree(work_dir, ignore_errors=True)

        # 3. checksums ファイル作成（削除検知のため）
        checksums_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_checksums.yaml'
        )
        with open(checksums_path, 'w') as f:
            f.write('checksums:\n  rules/coding_standards.md: abc123\n')

        # 4. ソースファイル削除
        os.remove(os.path.join(self.tmpdir, 'rules', 'coding_standards.md'))

        # 5. delete-only 実行
        proc = self._run_merge('rules', delete_only=True)
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

        # 6. ToC からエントリが消えていること
        toc_path = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', 'rules_toc.yaml'
        )
        with open(toc_path, 'r') as f:
            content = f.read()
        self.assertNotIn('rules/coding_standards.md', content)

    def test_delete_only_no_toc_file_fails(self):
        """ToC ファイルが存在しない場合はエラー"""
        proc = self._run_merge('rules', delete_only=True)
        self.assertNotEqual(proc.returncode, 0)


# ===========================================================================
# エラーケース
# ===========================================================================

class TestMergeTocErrors(TestMergeTocBase):
    """エラーケースのテスト。"""

    def test_no_pending_files_fails(self):
        """pending ファイルがない場合はエラー"""
        # .toc_work を空で作成
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        os.makedirs(work_dir, exist_ok=True)
        proc = self._run_merge('rules', mode='full')
        self.assertNotEqual(proc.returncode, 0)

    def test_pending_not_completed_skipped(self):
        """status が completed でないエントリはスキップされる"""
        self._create_pending_entry(
            'rules', 'rules/coding_standards.md', 'Coding Standards', status='pending'
        )
        proc = self._run_merge('rules', mode='full')
        # エントリが有効でないためエラー（No valid entries）
        self.assertNotEqual(proc.returncode, 0)


# ===========================================================================
# write_yaml_output() パラメータ経由テスト（TASK-001: グローバル変数依存排除）
# ===========================================================================

class TestWriteYamlOutputWithParams(unittest.TestCase):
    """write_yaml_output() を category / output_config パラメータ経由で呼び出すテスト。
    グローバル変数に依存せず、パラメータ経由で設定を渡して正常動作することを確認する。
    """

    def setUp(self):
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_category_param_used_in_output(self):
        """category パラメータが ToC ヘッダーに反映される"""
        from merge_toc import write_yaml_output
        output_path = Path(os.path.join(self.tmpdir, 'test_toc.yaml'))
        docs = {
            'rules/test.md': {
                'title': 'Test',
                'purpose': 'Test purpose',
                'doc_type': 'rule',
                'content_details': ['detail1'],
                'applicable_tasks': ['task1'],
                'keywords': ['kw1'],
            }
        }
        output_config = {
            'header_comment': 'Custom Header',
            'metadata_name': 'Custom Index',
        }
        result = write_yaml_output(docs, output_path, category='myrules', output_config=output_config)
        self.assertTrue(result)
        content = output_path.read_text(encoding='utf-8')
        # category がパスとコメントに反映されている
        self.assertIn('myrules_toc.yaml', content)
        self.assertIn('Custom Header', content)
        self.assertIn('Custom Index', content)
        self.assertIn('create-myrules-toc', content)

    def test_output_config_param_overrides_global(self):
        """output_config パラメータがグローバル変数より優先される"""
        from merge_toc import write_yaml_output
        output_path = Path(os.path.join(self.tmpdir, 'test_toc.yaml'))
        docs = {
            'specs/api.md': {
                'title': 'API Spec',
                'purpose': 'API specification',
                'doc_type': 'spec',
                'content_details': ['api detail'],
                'applicable_tasks': ['api task'],
                'keywords': ['api'],
            }
        }
        output_config = {
            'header_comment': 'Overridden Header Comment',
            'metadata_name': 'Overridden Metadata Name',
        }
        result = write_yaml_output(docs, output_path, category='specs', output_config=output_config)
        self.assertTrue(result)
        content = output_path.read_text(encoding='utf-8')
        self.assertIn('Overridden Header Comment', content)
        self.assertIn('Overridden Metadata Name', content)

    def test_docs_content_written_correctly(self):
        """パラメータ経由でもドキュメントエントリが正しく書き出される"""
        from merge_toc import write_yaml_output
        output_path = Path(os.path.join(self.tmpdir, 'test_toc.yaml'))
        docs = {
            'rules/coding.md': {
                'title': 'Coding Standards',
                'purpose': 'Define coding practices',
                'doc_type': 'rule',
                'content_details': ['detail A', 'detail B'],
                'applicable_tasks': ['coding review'],
                'keywords': ['coding', 'standards'],
            }
        }
        output_config = {'header_comment': 'Test', 'metadata_name': 'Test Index'}
        result = write_yaml_output(docs, output_path, category='rules', output_config=output_config)
        self.assertTrue(result)
        content = output_path.read_text(encoding='utf-8')
        self.assertIn('rules/coding.md', content)
        self.assertIn('doc_type: rule', content)
        self.assertIn('Coding Standards', content)
        self.assertIn('file_count: 1', content)


if __name__ == '__main__':
    unittest.main()
