#!/usr/bin/env python3
"""fixer/scripts/mark_fixed.py のテスト

session/update_plan.py に --status fixed を hardcoded で渡し、--id, --files-modified flag を
位置引数から組み立てる。stdout / stderr / exit code は完全透過。
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'fixer' / 'scripts' / 'mark_fixed.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'scripts'
                      / 'session' / 'update_plan.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("_mark_fixed_fixer", WRAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMarkFixedWrapper(unittest.TestCase):
    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_subprocess_called_without_files(self):
        """位置引数 session_dir / id のみ → cmd に --files-modified を含めない"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["mark_fixed.py", "/tmp/x", "L-001"]):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).resolve(), EXPECTED_LOW_LEVEL.resolve())
        self.assertEqual(cmd[2], "/tmp/x")
        self.assertIn("--id", cmd)
        self.assertEqual(cmd[cmd.index("--id") + 1], "L-001")
        self.assertIn("--status", cmd)
        self.assertEqual(cmd[cmd.index("--status") + 1], "fixed")
        self.assertNotIn("--files-modified", cmd)
        self.assertFalse(mock_run.call_args.kwargs.get("check", True))

    def test_subprocess_called_with_files(self):
        """位置引数に file が続く → cmd に --files-modified file1 file2 を末尾追加"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["mark_fixed.py", "/tmp/x", "L-001", "a.py", "b.py"]):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertIn("--files-modified", cmd)
        idx = cmd.index("--files-modified")
        self.assertEqual(cmd[idx + 1:], ["a.py", "b.py"])

    def test_status_hardcoded_to_fixed(self):
        """--status fixed が hardcoded（外部からの上書き不可）"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["mark_fixed.py", "/tmp/x", "L-001"]):
                self.wrapper.main()
        cmd = mock_run.call_args.args[0]
        idx = cmd.index("--status")
        self.assertEqual(cmd[idx + 1], "fixed")

    def test_exit_code_transparent(self):
        for code in (0, 1, 2, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    with mock.patch.object(sys, "argv",
                                           ["mark_fixed.py", "/tmp/x", "L-001"]):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_stdout_stderr_not_captured(self):
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            with mock.patch.object(sys, "argv",
                                   ["mark_fixed.py", "/tmp/x", "L-001"]):
                self.wrapper.main()
        kw = mock_run.call_args.kwargs
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)


if __name__ == "__main__":
    unittest.main()
