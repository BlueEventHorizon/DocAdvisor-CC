#!/usr/bin/env python3
"""
present-findings/scripts/mark_skipped.py のテスト

update_plan.py を透過的に呼び出すラッパーを検証する。
位置引数 {session_dir} {id} {reason} → --id / --status=skipped / --skip-reason
へのマッピング、ハードコード --status 値、exit code 透過、stdio 透過を確認。
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'present-findings' / 'scripts' / 'mark_skipped.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'scripts'
                      / 'session' / 'update_plan.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_mark_skipped_present_findings", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMarkSkippedWrapper(unittest.TestCase):
    """mark_skipped.py が update_plan.py を透過的に呼ぶことを検証"""

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path_points_update_plan(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_positional_args_mapped_to_flags(self):
        """位置引数 {session_dir} {id} {reason} が正しく flag に変換される"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_skipped.py", "/tmp/session", "3", "ユーザー判断: 対応不要"]
            with mock.patch.object(sys, "argv", argv):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).resolve(), EXPECTED_LOW_LEVEL.resolve())
        self.assertEqual(cmd[2], "/tmp/session")
        self.assertIn("--id", cmd)
        self.assertEqual(cmd[cmd.index("--id") + 1], "3")
        self.assertIn("--status", cmd)
        self.assertEqual(cmd[cmd.index("--status") + 1], "skipped")
        self.assertIn("--skip-reason", cmd)
        self.assertEqual(cmd[cmd.index("--skip-reason") + 1], "ユーザー判断: 対応不要")
        self.assertFalse(mock_run.call_args.kwargs.get("check", True))

    def test_status_hardcoded_skipped(self):
        """--status の値は 'skipped' にハードコードされている"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_skipped.py", "/x", "1", "r"]
            with mock.patch.object(sys, "argv", argv):
                self.wrapper.main()
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--status") + 1], "skipped")
        self.assertNotIn("--batch", cmd)

    def test_exit_code_transparent(self):
        for code in (0, 1, 2, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    argv = ["mark_skipped.py", "/x", "1", "r"]
                    with mock.patch.object(sys, "argv", argv):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_stdio_not_touched_by_wrapper(self):
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_skipped.py", "/x", "1", "r"]
            with mock.patch.object(sys, "argv", argv):
                self.wrapper.main()
        kw = mock_run.call_args.kwargs
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)
        self.assertNotIn("stdin", kw)
        self.assertNotIn("input", kw)


if __name__ == "__main__":
    unittest.main()
