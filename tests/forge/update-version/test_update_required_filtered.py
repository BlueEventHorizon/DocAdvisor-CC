#!/usr/bin/env python3
"""
update-version/scripts/update_required_filtered.py のテスト

update_version_files.py {file} {cur} {new} --filter {filter} を
透過的に呼び出すラッパーを検証する。

実行:
  python3 -m unittest tests.forge.update-version.test_update_required_filtered -v
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'update-version' / 'scripts' / 'update_required_filtered.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                      / 'update-version' / 'scripts' / 'update_version_files.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_update_required_filtered", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUpdateRequiredFilteredWrapper(unittest.TestCase):

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_filter_passed_no_optional(self):
        """--filter が渡され、--optional は付かない"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["w", "f.json", "1.0.0", "1.0.1", "forge"]):
                self.wrapper.main()
        cmd = mock_run.call_args.args[0]
        self.assertIn("--filter", cmd)
        idx = cmd.index("--filter")
        self.assertEqual(cmd[idx + 1], "forge")
        self.assertNotIn("--optional", cmd)

    def test_exit_code_transparent(self):
        for code in (0, 1, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    with mock.patch.object(sys, "argv",
                                           ["w", "f", "1.0.0", "1.0.1", "pat"]):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_not_captured(self):
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["w", "f", "1.0.0", "1.0.1", "pat"]):
                self.wrapper.main()
        kw = mock_run.call_args.kwargs
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)


if __name__ == "__main__":
    unittest.main()
