#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_checksums.py のユニットテスト。

bash テスト test_checksums.sh から移行。
subprocess.run でスクリプトを呼び出す形式でテスト。
test_setup_upgrade.sh Test 30（target_glob 尊重）も含む。
"""

import os
import sys
import subprocess
import tempfile
import shutil
import re
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
CHECKSUMS_SCRIPT = os.path.join(SCRIPTS_DIR, 'create_checksums.py')


class TestCreateChecksumsBase(unittest.TestCase):
    """create_checksums.py テストの基底クラス。"""

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

        # rules/ ディレクトリとテスト用ファイル
        rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(rules_dir, exist_ok=True)
        with open(os.path.join(rules_dir, 'coding_standards.md'), 'w') as f:
            f.write('# Coding Standards\n\nDefine coding practices.\n')

        # specs/ ディレクトリとテスト用ファイル
        specs_dir = os.path.join(self.tmpdir, 'specs')
        os.makedirs(specs_dir, exist_ok=True)
        with open(os.path.join(specs_dir, 'auth_spec.md'), 'w') as f:
            f.write('# Auth Spec\n\nAuthentication requirements.\n')
        with open(os.path.join(specs_dir, 'login_spec.md'), 'w') as f:
            f.write('# Login Spec\n\nLogin requirements.\n')

        # ToC 出力ディレクトリ
        for cat in ('rules', 'specs'):
            os.makedirs(os.path.join(
                self.tmpdir, '.claude', 'doc-advisor', 'toc', cat
            ), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run_checksums(self, category):
        """create_checksums.py を subprocess で実行する。"""
        cmd = [sys.executable, CHECKSUMS_SCRIPT, '--category', category]
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )

    def _get_checksums_path(self, category):
        return os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', category, '.toc_checksums.yaml'
        )


# ===========================================================================
# rules カテゴリのチェックサム生成
# ===========================================================================

class TestCreateChecksumsRules(TestCreateChecksumsBase):
    """rules カテゴリのチェックサム生成テスト。"""

    def test_rules_exit_code(self):
        """rules のチェックサム生成が正常終了する"""
        proc = self._run_checksums('rules')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

    def test_rules_file_created(self):
        """rules のチェックサムファイルが作成される"""
        self._run_checksums('rules')
        self.assertTrue(os.path.exists(self._get_checksums_path('rules')))

    def test_rules_has_checksums_section(self):
        """チェックサムファイルに checksums セクションがある"""
        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            content = f.read()
        self.assertIn('checksums:', content)

    def test_rules_has_sha256_hash(self):
        """チェックサムファイルに有効な SHA-256 ハッシュがある"""
        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            content = f.read()
        self.assertRegex(content, r'[a-f0-9]{64}')


# ===========================================================================
# specs カテゴリのチェックサム生成
# ===========================================================================

class TestCreateChecksumsSpecs(TestCreateChecksumsBase):
    """specs カテゴリのチェックサム生成テスト。"""

    def test_specs_exit_code(self):
        """specs のチェックサム生成が正常終了する"""
        proc = self._run_checksums('specs')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

    def test_specs_file_created(self):
        """specs のチェックサムファイルが作成される"""
        self._run_checksums('specs')
        self.assertTrue(os.path.exists(self._get_checksums_path('specs')))

    def test_specs_multiple_entries(self):
        """specs のチェックサムファイルに複数エントリがある"""
        self._run_checksums('specs')
        with open(self._get_checksums_path('specs'), 'r') as f:
            content = f.read()
        # SHA-256 ハッシュの数をカウント（2ファイル分）
        hashes = re.findall(r'[a-f0-9]{64}', content)
        self.assertGreaterEqual(len(hashes), 2)


# ===========================================================================
# 変更検知テスト
# ===========================================================================

class TestChecksumsChangeDetection(TestCreateChecksumsBase):
    """ファイル変更後のハッシュ変化テスト。"""

    def test_hash_changes_after_modification(self):
        """ファイル変更後にハッシュが変化する"""
        # 1. 初回チェックサム生成
        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            original_content = f.read()
        original_hash = re.search(r'coding_standards.*?([a-f0-9]{64})', original_content)
        self.assertIsNotNone(original_hash, 'coding_standards のハッシュが見つからない')
        original_hash = original_hash.group(1)

        # 2. ファイル変更
        with open(os.path.join(self.tmpdir, 'rules', 'coding_standards.md'), 'a') as f:
            f.write('\nAdditional content.\n')

        # 3. 再生成
        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            new_content = f.read()
        new_hash = re.search(r'coding_standards.*?([a-f0-9]{64})', new_content)
        self.assertIsNotNone(new_hash)
        new_hash = new_hash.group(1)

        # 4. ハッシュが変化していること
        self.assertNotEqual(original_hash, new_hash)


# ===========================================================================
# target_glob 尊重テスト（test_setup_upgrade.sh Test 30 から移行）
# ===========================================================================

class TestChecksumsTargetGlob(TestCreateChecksumsBase):
    """target_glob パターン尊重のテスト。.md のみ対象、.txt は除外。"""

    def test_txt_files_excluded(self):
        """.txt ファイルがチェックサムに含まれない"""
        # .txt ファイルを追加
        with open(os.path.join(self.tmpdir, 'rules', 'notes.txt'), 'w') as f:
            f.write('Some notes\n')

        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            content = f.read()
        self.assertNotIn('notes.txt', content)

    def test_md_files_included(self):
        """.md ファイルがチェックサムに含まれる"""
        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            content = f.read()
        self.assertIn('coding_standards.md', content)

    def test_non_md_extensions_excluded(self):
        """target_glob: **/*.md の場合、.yaml や .json は除外される"""
        # 様々な拡張子のファイルを追加
        for ext in ('.yaml', '.json', '.py', '.txt'):
            with open(os.path.join(self.tmpdir, 'rules', f'test_file{ext}'), 'w') as f:
                f.write(f'test content for {ext}\n')

        self._run_checksums('rules')
        with open(self._get_checksums_path('rules'), 'r') as f:
            content = f.read()
        for ext in ('.yaml', '.json', '.py', '.txt'):
            self.assertNotIn(f'test_file{ext}', content,
                             f'{ext} ファイルがチェックサムに含まれている')


# ===========================================================================
# 無効な引数テスト
# ===========================================================================

class TestChecksumsInvalidArgs(TestCreateChecksumsBase):
    """無効な引数のテスト。"""

    def test_invalid_category_rejected(self):
        """無効なカテゴリは拒否される"""
        cmd = [sys.executable, CHECKSUMS_SCRIPT, '--category', 'invalid']
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )
        self.assertNotEqual(proc.returncode, 0)


# ===========================================================================
# --promote-pending テスト
# ===========================================================================

class TestPromotePending(TestCreateChecksumsBase):
    """--promote-pending フラグのテスト。"""

    def _run_promote(self, category):
        """--promote-pending を subprocess で実行する。"""
        cmd = [sys.executable, CHECKSUMS_SCRIPT, '--category', category, '--promote-pending']
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )

    def test_promote_copies_pending_to_checksums(self):
        """pending checksums が active checksums にコピーされる"""
        # .toc_work/ に pending ファイルを作成
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        os.makedirs(work_dir, exist_ok=True)
        pending_content = "# pending checksums\nchecksums:\n  rules/test.md: abc123\n"
        with open(os.path.join(work_dir, '.toc_checksums_pending.yaml'), 'w') as f:
            f.write(pending_content)

        proc = self._run_promote('rules')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')

        # active checksums ファイルに pending の内容がコピーされていること
        checksums_path = self._get_checksums_path('rules')
        self.assertTrue(os.path.exists(checksums_path))
        with open(checksums_path, 'r') as f:
            content = f.read()
        self.assertIn('abc123', content)

    def test_promote_fails_when_no_pending(self):
        """pending ファイルが存在しない場合はエラー終了"""
        proc = self._run_promote('rules')
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('Pending checksums not found', proc.stderr)


# ===========================================================================
# --clean-work-dir テスト
# ===========================================================================

class TestCleanWorkDir(TestCreateChecksumsBase):
    """--clean-work-dir フラグのテスト。"""

    def _run_clean(self, category):
        """--clean-work-dir を subprocess で実行する。"""
        cmd = [sys.executable, CHECKSUMS_SCRIPT, '--category', category, '--clean-work-dir']
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.tmpdir,
            env={**os.environ, 'PYTHONPATH': SCRIPTS_DIR}
        )

    def test_clean_removes_work_dir(self):
        """work directory が削除される"""
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        os.makedirs(work_dir, exist_ok=True)
        # ダミーファイルを作成
        with open(os.path.join(work_dir, 'dummy.yaml'), 'w') as f:
            f.write('dummy')

        proc = self._run_clean('rules')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')
        self.assertFalse(os.path.exists(work_dir))

    def test_clean_succeeds_when_no_work_dir(self):
        """work directory が不在時はスキップして正常終了"""
        work_dir = os.path.join(
            self.tmpdir, '.claude', 'doc-advisor', 'toc', 'rules', '.toc_work'
        )
        # work_dir が存在しないことを確認
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir)

        proc = self._run_clean('rules')
        self.assertEqual(proc.returncode, 0, f'stderr: {proc.stderr}')
        self.assertIn('not found (skip)', proc.stderr)


if __name__ == '__main__':
    unittest.main()
