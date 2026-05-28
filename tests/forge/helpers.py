#!/usr/bin/env python3
"""
forge テスト共通ヘルパー

ファイルシステムを使うテストの基底クラスを提供する。
"""

import shutil
import tempfile
import unittest
from pathlib import Path


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテストの基底クラス"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, rel_path, content=''):
        """テスト用ファイルを作成する。"""
        p = self.tmpdir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p
