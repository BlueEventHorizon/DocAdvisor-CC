#!/usr/bin/env python3
"""
review/scripts/resolve_specs.py のテスト

resolve_doc_structure.py --type specs を透過的に呼び出すラッパーを検証する。

実行:
  python3 -m unittest tests.forge.review.test_resolve_specs -v
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'review' / 'scripts' / 'resolve_specs.py')
EXPECTED_TYPE = "specs"
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                      / 'doc-structure' / 'scripts' / 'resolve_doc_structure.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_resolve_specs_review", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestResolveSpecsWrapper(unittest.TestCase):
    """resolve_specs.py が resolve_doc_structure.py --type specs を透過的に呼ぶことを検証"""

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_type_hardcoded(self):
        """TYPE 定数が specs にハードコードされている"""
        self.assertEqual(self.wrapper.TYPE, EXPECTED_TYPE)

    def test_low_level_path_points_resolve_doc_structure(self):
        """LOW_LEVEL パスが resolve_doc_structure.py を指す"""
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_subprocess_called_with_type(self):
        """subprocess.run が --type specs で呼ばれる"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        self.assertEqual(mock_run.call_count, 1)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).resolve(), EXPECTED_LOW_LEVEL.resolve())
        self.assertIn("--type", cmd)
        idx = cmd.index("--type")
        self.assertEqual(cmd[idx + 1], EXPECTED_TYPE)
        self.assertFalse(mock_run.call_args.kwargs.get("check", True))

    def test_exit_code_transparent_zero(self):
        """低レベル return 0 → ラッパー return 0"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            rc = self.wrapper.main()
        self.assertEqual(rc, 0)

    def test_exit_code_transparent_nonzero(self):
        """低レベル return 非0 → ラッパー同じ非0"""
        for code in (1, 2, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_stdout_stderr_not_captured_by_wrapper(self):
        """ラッパーは stdout/stderr を capture しない（透過のため）"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            self.wrapper.main()
        kw = mock_run.call_args.kwargs
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)


if __name__ == "__main__":
    unittest.main()
