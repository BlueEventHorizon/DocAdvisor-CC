#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""write_pending.py のユニットテスト（key + path I/F / DES-005 §7.1）。

doc_type 廃止・--key 対応に合わせて改修。
- pending YAML（store_dir/.toc_work/ 配下、doc_type なし）への充填
- --doc-type なしで動作すること
- --key / --all（予約 key all）でストアパス対応
- title/purpose/3 配列の欠落・不足を検出すること
- --error モードで status pending 保持
- _meta.extracted_by に AI 抽出由来（ai）が記録され、error 経路には出ないこと、
  および toc.yaml には書き出されないこと（DES-008 §8.2）
subprocess.run でスクリプトを呼び出す形式でテスト。
"""

import json
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
MERGE_SCRIPT = os.path.join(SCRIPTS_DIR, 'merge_toc.py')
TOC_STORE_SCRIPT = os.path.join(SCRIPTS_DIR, 'toc_store.py')

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
        return self._run_script(WRITE_SCRIPT, args)

    def _run_script(self, script, args):
        """scripts/ 配下のスクリプトを subprocess で実行する。"""
        cmd = [sys.executable, script] + args
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )

    def _fill(self, entry):
        """代表値で pending を充填する（正常モード）。"""
        return self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--title', 'Coding Standards',
            '--purpose', 'Define consistent coding practices',
            '--content-details', 'Naming ||| Structure ||| Errors ||| Testing ||| Docs',
            '--applicable-tasks', 'Code review',
            '--keywords', 'coding ||| standards ||| naming ||| structure ||| testing',
        ])


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


# ===========================================================================
# 抽出来歴 _meta.extracted_by（DES-008 §8.2）
# ===========================================================================

class TestWritePendingExtractedBy(TestWritePendingBase):
    """AI 抽出経路の来歴が記録され、error 経路と toc.yaml には出ないこと。"""

    def test_completed_output_has_extracted_by_ai(self):
        """充填した pending に extracted_by: ai が書かれる"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._fill(entry)
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('  extracted_by: ai\n', content)

    def test_extracted_by_is_last_meta_key(self):
        """extracted_by は _meta の最終キー（_meta ブロック直後は空行）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._fill(entry)

        with open(entry, 'r') as f:
            content = f.read()
        self.assertIn('  extracted_by: ai\n\ntitle:', content)

    def test_error_mode_has_no_extracted_by(self):
        """--error の出力に extracted_by は書かない（充填失敗は書き戻し候補でない）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        proc = self._run_write([
            '--key', self.KEY,
            '--entry-file', entry,
            '--error',
            '--error-message', 'Source file not found',
        ])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

        with open(entry, 'r') as f:
            content = f.read()
        self.assertNotIn('extracted_by', content)

    def test_work_status_handles_extracted_by(self):
        """extracted_by を持つ pending でも --work-status が壊れない"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._fill(entry)

        proc = self._run_script(TOC_STORE_SCRIPT, ['--key', self.KEY, '--work-status'])
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload['completed'], 1)
        self.assertEqual(payload['pending'], [])

    def test_toc_yaml_has_no_extracted_by(self):
        """merge 後の toc.yaml に extracted_by が現れない（DES-008 §8.2）"""
        entry = self._create_pending_yaml('docs/coding_standards.md')
        self._fill(entry)

        merge = self._run_script(MERGE_SCRIPT, ['--key', self.KEY])
        self.assertEqual(merge.returncode, 0, f'stderr: {merge.stderr}')

        toc = (self.store_dir / 'toc.yaml').read_text(encoding='utf-8')
        self.assertIn('docs/coding_standards.md:', toc)
        self.assertNotIn('extracted_by', toc)


if __name__ == '__main__':
    unittest.main()
