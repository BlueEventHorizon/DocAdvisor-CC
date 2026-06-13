#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_pending.py のユニットテスト（key + path I/F / DES-005 §7.1）。

doc_type 廃止・--key 対応に合わせて改修。
- pending YAML（store_dir/.toc_work/ 配下、doc_type なし）への充填
- --doc-type なしで動作すること
- --key / --all（予約 key all）でストアパス対応
- title/purpose/3 配列の欠落・不足を検出すること
- --error モードで status pending 保持
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
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
WRITE_SCRIPT = os.path.join(SCRIPTS_DIR, 'write_pending.py')

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestWritePendingBase(unittest.TestCase):
    """write_pending.py テストの基底クラス。"""

    KEY = 'myrules'

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self.original_env[key] = os.environ.get(key)

        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir
        os.environ['CLAUDE_PLUGIN_ROOT'] = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..'
        ))

        # ソースドキュメント（project-root-relative）
        os.makedirs(os.path.join(self.tmpdir, 'docs'), exist_ok=True)
        with open(os.path.join(self.tmpdir, 'docs', 'coding_standards.md'), 'w') as f:
            f.write('# Coding Standards\n')

        # key ストアの .toc_work/ を解決して作成
        from toc_store import resolve_store_dir, WORK_DIRNAME
        self.store_dir = resolve_store_dir(self.KEY, self.tmpdir)
        self.work_dir = self.store_dir / WORK_DIRNAME
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _create_pending_yaml(self, source_file):
        """pending YAML ファイルを作成し、パスを返す（doc_type なし / DES-005 §7.1）。"""
        from toc_store import resolve_store_dir, WORK_DIRNAME
        work_dir = resolve_store_dir(self.KEY, self.tmpdir) / WORK_DIRNAME
        safe_name = source_file.replace('/', '_').replace('.', '_') + '.yaml'
        entry_path = os.path.join(str(work_dir), safe_name)

        content = f"""\
_meta:
  source_file: {source_file}
  status: pending
  updated_at: null

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

    def test_normal_exit_code(self):
        """--key + doc_type なしで正常書き込みが exit code 0"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review ||| New development',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_status_completed(self):
        """書き込み後に status が completed になる"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._run_write([
            '--key', self.KEY,
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

    def test_no_doc_type_in_output(self):
        """書き込み後の出力に doc_type が含まれない（DES-005 §7.1）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertNotIn('doc_type', content)

    def test_doc_type_arg_rejected(self):
        """--doc-type は廃止され受け付けない（argparse エラー）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--doc-type', 'rule',
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        # argparse は未知の引数で exit code 2
        self.assertEqual(proc.returncode, 2)

    def test_all_single_mode_exit_code(self):
        """--all（予約 key all）で書き込みが exit code 0"""
        # 単体モード（予約 key all）のストアに pending を置く
        from toc_store import resolve_store_dir, WORK_DIRNAME, DEFAULT_KEY
        all_work = resolve_store_dir(DEFAULT_KEY, self.tmpdir) / WORK_DIRNAME
        all_work.mkdir(parents=True, exist_ok=True)
        entry_path = os.path.join(str(all_work), 'all_entry.yaml')
        with open(entry_path, 'w') as f:
            f.write(
                "_meta:\n"
                "  source_file: docs/coding_standards.md\n"
                "  status: pending\n"
                "  updated_at: null\n\n"
                "title: null\npurpose: null\n"
                "content_details: []\napplicable_tasks: []\nkeywords: []\n"
            )
        proc = self._run_write([
            '--all',
            '--entry-file', entry_path,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_reserved_key_rejected(self):
        """--key all（任意指定）は予約語として reject（exit code 1）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', 'all',
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])
        self.assertEqual(proc.returncode, 1)


# ===========================================================================
# 必須引数不足
# ===========================================================================

class TestWritePendingMissingArgs(TestWritePendingBase):
    """必須引数不足のテスト。"""

    def test_missing_purpose_and_others(self):
        """必須引数不足で非ゼロ exit code"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--title', 'Test',
        ])
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_all_content_fields(self):
        """タイトルのみでは exit code 2"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--title', 'Test',
        ])
        self.assertEqual(proc.returncode, 2)


# ===========================================================================
# 配列要素数不足（exit code 3）
# ===========================================================================

class TestWritePendingInsufficientArrays(TestWritePendingBase):
    """配列要素数不足のテスト。"""

    def test_insufficient_keywords(self):
        """keywords が5件未満で exit code 3"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
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
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
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
            '--key', self.KEY,
            '--entry-file', os.path.join(self.tmpdir, 'nonexistent.yaml'),
            '--title', 'Test',
            '--purpose', 'Test purpose',
            '--content-details', 'a ||| b ||| c ||| d ||| e',
            '--applicable-tasks', 'task1',
            '--keywords', 'a ||| b ||| c ||| d ||| e',
        ])
        self.assertEqual(proc.returncode, 1)


# ===========================================================================
# --error モード
# ===========================================================================

class TestWritePendingErrorMode(TestWritePendingBase):
    """--error モードのテスト。status が pending のまま保持される。"""

    def test_error_mode_exit_code(self):
        """--error モードが exit code 0 で終了"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}\nstdout: {proc.stdout}')

    def test_error_mode_status_pending(self):
        """--error モードで status が pending のまま"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('status: pending', content)
        self.assertNotIn('status: completed', content)

    def test_error_mode_no_doc_type(self):
        """--error モードの出力に doc_type が含まれない（DES-005 §7.1）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        with open(entry, 'r') as f:
            content = f.read()
        self.assertNotIn('doc_type', content)

    def test_error_mode_has_error_message(self):
        """--error モードで error_message が記録される"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._run_write([
            '--key', self.KEY,
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
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--error',
        ])
        self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
