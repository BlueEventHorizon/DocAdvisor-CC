#!/usr/bin/env python3
"""
update-version/scripts/update_required_dependent.py のテスト

update_version_files.py {file} {cur} {new} を透過的に呼び出すラッパーを検証する
（--optional も --filter も付けない必須・filter なしパターン）。

実行:
  python3 -m unittest tests.forge.update-version.test_update_required_dependent -v
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'update-version' / 'scripts' / 'update_required_dependent.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                      / 'update-version' / 'scripts' / 'update_version_files.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_update_required_dependent", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUpdateRequiredDependentWrapper(unittest.TestCase):

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_no_optional_no_filter(self):
        """--optional も --filter も付けない"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["w", "f.json", "1.0.0", "1.0.1"]):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertNotIn("--optional", cmd)
        self.assertNotIn("--filter", cmd)
        self.assertNotIn("--version-path", cmd)
        self.assertEqual(cmd[2], "f.json")
        self.assertEqual(cmd[3], "1.0.0")
        self.assertEqual(cmd[4], "1.0.1")

    def test_exit_code_transparent(self):
        for code in (0, 1, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    with mock.patch.object(sys, "argv",
                                           ["w", "f", "1.0.0", "1.0.1"]):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_not_captured(self):
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["w", "f", "1.0.0", "1.0.1"]):
                self.wrapper.main()
        kw = mock_run.call_args.kwargs
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)


if __name__ == "__main__":
    unittest.main()
