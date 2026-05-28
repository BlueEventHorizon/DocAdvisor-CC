#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLAUDE_PLUGIN_ROOT / CLAUDE_PROJECT_DIR environment variable tests.

get_project_root() behavior:
1. CLAUDE_PROJECT_DIR set and valid → returns that path
2. CLAUDE_PROJECT_DIR invalid or unset → returns cwd
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import toc_utils


class TestGetProjectRootEnvVar(unittest.TestCase):
    """CLAUDE_PROJECT_DIR set → returns that path"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_claude_project_dir_set(self):
        """CLAUDE_PROJECT_DIR set → returns that path"""
        with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': self.tmpdir}):
            result = toc_utils.get_project_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_claude_project_dir_empty_string_fallback(self):
        """CLAUDE_PROJECT_DIR empty string → falls back to cwd"""
        with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': ''}):
            with patch.object(Path, 'cwd', return_value=Path(self.tmpdir)):
                result = toc_utils.get_project_root()
        self.assertEqual(result, Path(self.tmpdir).resolve())

    def test_claude_project_dir_nonexistent_fallback(self):
        """CLAUDE_PROJECT_DIR nonexistent path → falls back to cwd"""
        nonexistent = os.path.join(self.tmpdir, 'nonexistent_xyz')
        with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': nonexistent}):
            with patch.object(Path, 'cwd', return_value=Path(self.tmpdir)):
                result = toc_utils.get_project_root()
        self.assertEqual(result, Path(self.tmpdir).resolve())


class TestGetProjectRootCwd(unittest.TestCase):
    """CLAUDE_PROJECT_DIR unset → returns cwd"""

    def test_no_env_returns_cwd(self):
        """No env var → returns cwd directly (no upward traversal)"""
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('CLAUDE_PROJECT_DIR', None)
                with patch.object(Path, 'cwd', return_value=Path(tmpdir)):
                    result = toc_utils.get_project_root()
            self.assertEqual(result, Path(tmpdir).resolve())
        finally:
            shutil.rmtree(tmpdir)

    def test_no_env_no_git_still_returns_cwd(self):
        """No env var, no .git/.claude → still returns cwd (no RuntimeError)"""
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('CLAUDE_PROJECT_DIR', None)
                with patch.object(Path, 'cwd', return_value=Path(tmpdir)):
                    # Should NOT raise RuntimeError
                    result = toc_utils.get_project_root()
            self.assertEqual(result, Path(tmpdir).resolve())
        finally:
            shutil.rmtree(tmpdir)


class TestFindConfigFile(unittest.TestCase):
    """find_config_file() のテスト"""

    def test_finds_doc_structure(self):
        """.doc_structure.yaml がプロジェクトルートに存在する場合"""
        tmpdir = tempfile.mkdtemp()
        ds_path = os.path.join(tmpdir, '.doc_structure.yaml')
        with open(ds_path, 'w') as f:
            f.write('rules:\n  root_dirs:\n    - rules/\n')
        try:
            with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': tmpdir}):
                result = toc_utils.find_config_file()
            self.assertEqual(result, Path(tmpdir) / '.doc_structure.yaml')
        finally:
            shutil.rmtree(tmpdir)

    def test_not_found_raises_error(self):
        """.doc_structure.yaml が存在しない場合は FileNotFoundError"""
        tmpdir = tempfile.mkdtemp()
        try:
            with patch.dict(os.environ, {'CLAUDE_PROJECT_DIR': tmpdir}):
                with self.assertRaises(FileNotFoundError):
                    toc_utils.find_config_file()
        finally:
            shutil.rmtree(tmpdir)


if __name__ == '__main__':
    unittest.main()
