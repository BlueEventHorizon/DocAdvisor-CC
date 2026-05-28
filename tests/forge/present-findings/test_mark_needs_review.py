#!/usr/bin/env python3
"""
present-findings/scripts/mark_needs_review.py のテスト

update_plan.py を透過的に呼び出すラッパーを検証する。
位置引数 {session_dir} {id} → --id / --status=needs_review への
マッピング、ハードコード --status 値、exit code 透過、stdio 透過を確認。
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'present-findings' / 'scripts' / 'mark_needs_review.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'scripts'
                      / 'session' / 'update_plan.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_mark_needs_review_present_findings", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMarkNeedsReviewWrapper(unittest.TestCase):
    """mark_needs_review.py が update_plan.py を透過的に呼ぶことを検証"""

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path_points_update_plan(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_positional_args_mapped_to_flags(self):
        """位置引数 {session_dir} {id} が正しく flag に変換される"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_needs_review.py", "/tmp/session", "7"]
            with mock.patch.object(sys, "argv", argv):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).resolve(), EXPECTED_LOW_LEVEL.resolve())
        self.assertEqual(cmd[2], "/tmp/session")
        self.assertIn("--id", cmd)
        self.assertEqual(cmd[cmd.index("--id") + 1], "7")
        self.assertIn("--status", cmd)
        self.assertEqual(cmd[cmd.index("--status") + 1], "needs_review")
        self.assertFalse(mock_run.call_args.kwargs.get("check", True))

    def test_status_hardcoded_needs_review(self):
        """--status の値は 'needs_review' にハードコードされている"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_needs_review.py", "/x", "1"]
            with mock.patch.object(sys, "argv", argv):
                self.wrapper.main()
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--status") + 1], "needs_review")
        self.assertNotIn("--skip-reason", cmd)
        self.assertNotIn("--batch", cmd)

    def test_exit_code_transparent(self):
        for code in (0, 1, 2, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    argv = ["mark_needs_review.py", "/x", "1"]
                    with mock.patch.object(sys, "argv", argv):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_stdio_not_touched_by_wrapper(self):
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["mark_needs_review.py", "/x", "1"]
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
