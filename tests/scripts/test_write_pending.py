#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_pending.py のユニットテスト。

bash テスト test_write_pending.sh から移行。
subprocess.run でスクリプトを呼び出す形式でテスト。
test_setup_upgrade.sh Test 29（--error モード）も含む。
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
WRITE_SCRIPT = os.path.join(SCRIPTS_DIR, 'write_pending.py')


class TestWritePendingBase(unittest.TestCase):
    """write_pending.py テストの基底クラス。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self.original_env[key] = os.environ.get(key)

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

        # rules/specs ディレクトリとソースファイル
        for cat in ('rules', 'specs'):
            os.makedirs(os.path.join(self.tmpdir, cat), exist_ok=True)
        with open(os.path.join(self.tmpdir, 'rules', 'coding_standards.md'), 'w') as f:
            f.write('# Coding Standards\n')
        with open(os.path.join(self.tmpdir, 'specs', 'auth_spec.md'), 'w') as f:
            f.write('# Auth Spec\n')

        # ToC ディレクトリ
        for cat in ('rules', 'specs'):
            work_dir = os.path.join(
                self.tmpdir, '.claude', 'doc-advisor', 'toc', cat, '.toc_work'
            )
            os.makedirs(work_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _create_pending_yaml(self, category, source_file, doc_type='rule'):
        """pending YAML ファイルを作成し、パスを返す。"""
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', category, '.toc_work'
        )
        safe_name = source_file.replace('/', '_').replace('.', '_') + '.yaml'
        entry_path = os.path.join(work_dir, safe_name)

        content = f"""\
_meta:
  source_file: {source_file}
  doc_type: {doc_type}
  status: pending
  updated_at: ""

title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
"""
        with open(entry_path, 'w') as f:
            f.write(content)
        return entry_path

    def _run_write(self, args):
        """write_pending.py を subprocess で実行する。"""
        cmd = [sys.executable, WRITE_SCRIPT] + args
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )


# ===========================================================================
# 正常ケース
# ===========================================================================

class TestWritePendingNormal(TestWritePendingBase):
    """正常ケースのテスト。"""

    def test_rules_normal_exit_code(self):
        """rules 正常書き込みが exit code 0"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review ||| New development',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_rules_status_completed(self):
        """書き込み後に status が completed になる"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('status: completed', content)

    def test_specs_normal_exit_code(self):
        """specs 正常書き込みが exit code 0"""
        entry = self._create_pending_yaml('specs', 'specs/auth_spec.md', doc_type='spec')
        proc = self._run_write([
            '--category', 'specs',
            '--entry-file', entry,
            '--title', 'Auth Requirements',
            '--purpose', 'Define authentication requirements',
            '--content-details', 'Login ||| Register ||| Password ||| Session ||| Security',
            '--applicable-tasks', 'Auth implementation',
            '--keywords', 'auth ||| login ||| security ||| password ||| session',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_specs_doc_type_preserved(self):
        """書き込み後に doc_type が保持される"""
        entry = self._create_pending_yaml('specs', 'specs/auth_spec.md', doc_type='spec')
        self._run_write([
            '--category', 'specs',
            '--entry-file', entry,
            '--title', 'Auth Requirements',
            '--purpose', 'Define authentication requirements',
            '--content-details', 'Login ||| Register ||| Password ||| Session ||| Security',
            '--applicable-tasks', 'Auth implementation',
            '--keywords', 'auth ||| login ||| security ||| password ||| session',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('doc_type: spec', content)


# ===========================================================================
# 必須引数不足
# ===========================================================================

class TestWritePendingMissingArgs(TestWritePendingBase):
    """必須引数不足のテスト。"""

    def test_missing_purpose_and_others(self):
        """必須引数不足で非ゼロ exit code"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Test',
        ])
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_all_content_fields(self):
        """タイトルのみでは exit code 2"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Test',
        ])
        self.assertEqual(proc.returncode, 2)


# ===========================================================================
# keywords 不足（exit code 3）
# ===========================================================================

class TestWritePendingInsufficientKeywords(TestWritePendingBase):
    """keywords 不足のテスト。"""

    def test_insufficient_keywords(self):
        """keywords が5件未満で exit code 3"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Test',
            '--purpose', 'Test purpose',
            '--content-details', 'a ||| b ||| c ||| d ||| e',
            '--applicable-tasks', 'task1',
            '--keywords', 'one ||| two',
        ])
        self.assertEqual(proc.returncode, 3)

    def test_insufficient_content_details(self):
        """content_details が5件未満で exit code 3"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--title', 'Test',
            '--purpose', 'Test purpose',
            '--content-details', 'a ||| b',
            '--applicable-tasks', 'task1',
            '--keywords', 'a ||| b ||| c ||| d ||| e',
        ])
        self.assertEqual(proc.returncode, 3)


# ===========================================================================
# ファイル未検出（exit code 1）
# ===========================================================================

class TestWritePendingFileNotFound(TestWritePendingBase):
    """ファイル未検出のテスト。"""

    def test_nonexistent_entry_file(self):
        """存在しないエントリファイルで exit code 1"""
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', os.path.join(self.tmpdir, 'nonexistent.yaml'),
            '--title', 'Test',
            '--purpose', 'Test purpose',
            '--content-details', 'a ||| b ||| c ||| d ||| e',
            '--applicable-tasks', 'task1',
            '--keywords', 'a ||| b ||| c ||| d ||| e',
        ])
        self.assertEqual(proc.returncode, 1)


# ===========================================================================
# --error モード（test_setup_upgrade.sh Test 29 から移行）
# ===========================================================================

class TestWritePendingErrorMode(TestWritePendingBase):
    """--error モードのテスト。status が pending のまま保持される。"""

    def test_error_mode_exit_code(self):
        """--error モードが exit code 0 で終了"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_error_mode_status_pending(self):
        """--error モードで status が pending のまま"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('status: pending', content)
        self.assertNotIn('status: completed', content)

    def test_error_mode_has_error_message(self):
        """--error モードで error_message が記録される"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('error_message:', content)
        self.assertIn('Source file not found', content)

    def test_error_mode_missing_message(self):
        """--error で --error-message がない場合は exit code 2"""
        entry = self._create_pending_yaml('rules', 'rules/coding_standards.md')
        proc = self._run_write([
            '--category', 'rules',
            '--entry-file', entry,
            '--error',
        ])
        self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
