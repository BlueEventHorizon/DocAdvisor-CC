#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_toc.py のユニットテスト（key + path I/F / DES-005 §7.1）。

doc_type 廃止・key ストアパス対応に合わせて改修。

テスト対象:
- doc_type なしの正常な ToC → exit code 0 / status ok
- title 欠損の ToC → 非ゼロ exit code / status error
- 3 配列いずれか欠落の ToC → 非ゼロ exit code
- 存在しないファイル参照の ToC → 非ゼロ exit code
- --key / --all（予約 key all）での store_dir/toc.yaml 検証
- --key all（任意指定）は予約語 reject
- JSON 出力契約（status / error_code enum）
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
VALIDATE_SCRIPT = os.path.join(SCRIPTS_DIR, 'validate_toc.py')

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _last_json_line(stdout):
    """stdout 末尾の JSON 行をパースする（JSON 出力契約の検証用）。"""
    lines = [ln for ln in stdout.strip().split('\n') if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


class TestValidateTocBase(unittest.TestCase):
    """テスト用の共通セットアップ（key ストアパス対応）"""

    KEY = 'myrules'

    def setUp(self):
        """一時ディレクトリとテスト用プロジェクト構造を作成"""
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        # .git ディレクトリ作成（project root 判定用）
        os.makedirs(os.path.join(self.project_root, '.git'))

        # docs/ ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'docs'), exist_ok=True)

        # key ストアを解決して store_dir を作成
        from toc_store import resolve_store_dir
        self.store_dir = resolve_store_dir(self.KEY, self.project_root)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_toc(self, content):
        """store_dir/toc.yaml を作成"""
        toc_path = self.store_dir / 'toc.yaml'
        toc_path.write_text(content, encoding='utf-8')
        return str(toc_path)

    def _run_validate(self, key=None, use_all=False, toc_file=None):
        """validate_toc.py を subprocess で実行"""
        cmd = [sys.executable, VALIDATE_SCRIPT]
        if use_all:
            cmd.append('--all')
        elif key is not None:
            cmd.extend(['--key', key])
        if toc_file:
            cmd.extend(['--file', toc_file])
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        env['PYTHONPATH'] = SCRIPTS_DIR
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )
        return result


class TestValidateTocFields(TestValidateTocBase):
    """必須フィールド検査（doc_type なし / DES-005 §7.1）"""

    def test_valid_toc_without_doc_type(self):
        """doc_type なしの正常な ToC → exit code 0 / status ok"""
        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test Rule\n\nContent.\n')

        toc_content = """\
docs:
  docs/test.md:
    title: "Test Rule"
    purpose: "A test rule document"
    content_details:
      - "contains test rules"
    applicable_tasks:
      - "testing"
    keywords:
      - "test"
      - "rule"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        self.assertEqual(result.returncode, 0,
                         f"doc_type なしの正常 ToC で非ゼロ。stdout: {result.stdout}\nstderr: {result.stderr}")
        payload = _last_json_line(result.stdout)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['status'], 'ok')
        self.assertIsNone(payload['error_code'])

    def test_missing_title(self):
        """title 欠損の ToC → 非ゼロ exit code / status error"""
        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')

        toc_content = """\
docs:
  docs/test.md:
    purpose: "test purpose"
    content_details:
      - "detail 1"
    applicable_tasks:
      - "task 1"
    keywords:
      - "kw"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        self.assertNotEqual(result.returncode, 0,
                            f"title 欠損で exit 0。stdout: {result.stdout}")
        payload = _last_json_line(result.stdout)
        self.assertEqual(payload['status'], 'error')

    def test_missing_keywords_array(self):
        """keywords 配列欠落の ToC → 非ゼロ exit code（3 配列必須）"""
        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')

        toc_content = """\
docs:
  docs/test.md:
    title: "Test Rule"
    purpose: "A test rule document"
    content_details:
      - "detail 1"
    applicable_tasks:
      - "task 1"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        self.assertNotEqual(result.returncode, 0,
                            f"keywords 欠落で exit 0。stdout: {result.stdout}")

    def test_doc_type_not_required(self):
        """doc_type が無くても valid（doc_type は必須から除外 / DES-005 §7.1）"""
        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')

        # doc_type フィールド自体を持たないエントリ
        toc_content = """\
docs:
  docs/test.md:
    title: "T"
    purpose: "P"
    content_details:
      - "d"
    applicable_tasks:
      - "t"
    keywords:
      - "k"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        self.assertEqual(result.returncode, 0,
                         f"doc_type なしで invalid 判定。stdout: {result.stdout}")

    def test_nonexistent_file_reference(self):
        """存在しないファイル参照の ToC → 非ゼロ exit code"""
        toc_content = """\
docs:
  docs/nonexistent_file.md:
    title: "Ghost Document"
    purpose: "References a file that does not exist"
    content_details:
      - "detail 1"
    applicable_tasks:
      - "task 1"
    keywords:
      - "test"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        self.assertNotEqual(result.returncode, 0,
                            f"存在しないファイル参照で exit 0。stdout: {result.stdout}")


class TestValidateTocKeyResolution(TestValidateTocBase):
    """key 解決・ストアパス対応のテスト"""

    def test_default_store_path_by_key(self):
        """--file 省略時に store_dir/toc.yaml を検証する"""
        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')

        toc_content = """\
docs:
  docs/test.md:
    title: "T"
    purpose: "P"
    content_details:
      - "d"
    applicable_tasks:
      - "t"
    keywords:
      - "k"
"""
        # store_dir/toc.yaml を直接書き出し、--file なしで検証
        self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY)
        self.assertEqual(result.returncode, 0,
                         f"store_dir/toc.yaml 検証で非ゼロ。stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_all_single_mode(self):
        """--all（予約 key all）で store_dir/toc.yaml を検証する"""
        from toc_store import resolve_store_dir, DEFAULT_KEY
        all_store = resolve_store_dir(DEFAULT_KEY, self.project_root)
        all_store.mkdir(parents=True, exist_ok=True)

        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')

        toc_content = """\
docs:
  docs/test.md:
    title: "T"
    purpose: "P"
    content_details:
      - "d"
    applicable_tasks:
      - "t"
    keywords:
      - "k"
"""
        (all_store / 'toc.yaml').write_text(toc_content, encoding='utf-8')
        result = self._run_validate(use_all=True)
        self.assertEqual(result.returncode, 0,
                         f"--all 検証で非ゼロ。stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_reserved_key_rejected(self):
        """--key all（任意指定）は予約語として reject（KEY_RESERVED）"""
        result = self._run_validate(key='all')
        self.assertNotEqual(result.returncode, 0)
        payload = _last_json_line(result.stdout)
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error_code'], 'KEY_RESERVED')

    def test_toc_not_found(self):
        """toc.yaml が存在しない key → status error / error_code TOC_NOT_FOUND"""
        result = self._run_validate(key='neverindexed')
        self.assertNotEqual(result.returncode, 0)
        payload = _last_json_line(result.stdout)
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error_code'], 'TOC_NOT_FOUND')


class TestValidateTocJsonContract(TestValidateTocBase):
    """JSON 出力契約（status / error_code enum 固定）"""

    def test_status_and_error_code_enum(self):
        """出力 JSON の status / error_code が enum の値域に収まる"""
        from toc_store import STATUSES, ERROR_CODES

        test_file = os.path.join(self.project_root, 'docs', 'test.md')
        with open(test_file, 'w') as f:
            f.write('# Test\n\nContent.\n')
        toc_content = """\
docs:
  docs/test.md:
    title: "T"
    purpose: "P"
    content_details:
      - "d"
    applicable_tasks:
      - "t"
    keywords:
      - "k"
"""
        toc_path = self._write_toc(toc_content)
        result = self._run_validate(key=self.KEY, toc_file=toc_path)
        payload = _last_json_line(result.stdout)
        self.assertIn(payload['status'], STATUSES)
        self.assertTrue(
            payload['error_code'] is None or payload['error_code'] in ERROR_CODES
        )


# ===========================================================================
# validate_toc() パラメータ経由テスト（グローバル変数非依存）
# ===========================================================================

class TestValidateTocWithParams(unittest.TestCase):
    """validate_toc() を project_root パラメータ経由で呼び出すテスト。"""

    def setUp(self):
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        docs_dir = self.project_root / 'docs'
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / 'test.md').write_text('# Test Rule\n\nContent.\n', encoding='utf-8')
        self.store_dir = self.project_root / '.claude' / 'doc-advisor' / 'toc' / 'mystore'
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_toc(self, content):
        toc_path = self.store_dir / 'toc.yaml'
        toc_path.write_text(content, encoding='utf-8')
        return toc_path

    def test_valid_toc_with_params(self):
        """パラメータ経由で doc_type なしの正常 ToC 検査が成功する"""
        from validate_toc import validate_toc
        toc_content = """\
docs:
  docs/test.md:
    title: "Test Rule"
    purpose: "A test rule document"
    content_details:
      - "contains test rules"
    applicable_tasks:
      - "testing"
    keywords:
      - "test"
      - "rule"
"""
        toc_path = self._write_toc(toc_content)
        result = validate_toc(toc_path, project_root=self.project_root)
        self.assertTrue(result)

    def test_missing_title_with_params(self):
        """パラメータ経由で title 欠損を検出する（doc_type は無くても可）"""
        from validate_toc import validate_toc
        toc_content = """\
docs:
  docs/test.md:
    purpose: "A test rule document"
    content_details:
      - "detail"
    applicable_tasks:
      - "task"
    keywords:
      - "kw"
"""
        toc_path = self._write_toc(toc_content)
        result = validate_toc(toc_path, project_root=self.project_root)
        self.assertFalse(result)

    def test_nonexistent_file_with_params(self):
        """パラメータ経由で存在しないファイル参照を検出する"""
        from validate_toc import validate_toc
        toc_content = """\
docs:
  docs/nonexistent.md:
    title: "Ghost"
    purpose: "Does not exist"
    content_details:
      - "detail"
    applicable_tasks:
      - "task"
    keywords:
      - "ghost"
"""
        toc_path = self._write_toc(toc_content)
        result = validate_toc(toc_path, project_root=self.project_root)
        self.assertFalse(result)

    def test_doc_type_not_required_with_params(self):
        """doc_type フィールドが無くても valid（DES-005 §7.1）"""
        from validate_toc import validate_toc
        toc_content = """\
docs:
  docs/test.md:
    title: "Test"
    purpose: "Test"
    content_details:
      - "d"
    applicable_tasks:
      - "t"
    keywords:
      - "k"
"""
        toc_path = self._write_toc(toc_content)
        result = validate_toc(toc_path, project_root=self.project_root)
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
