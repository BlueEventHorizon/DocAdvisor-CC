#!/usr/bin/env python3
"""
present-findings/scripts/batch_update.py のテスト

update_plan.py --batch を透過的に呼び出すラッパーを検証する。
位置引数 {session_dir} のみ受け、stdin は親プロセスから subprocess に継承させる
（subprocess.run に stdin/input を渡さない）。cmd に --batch が含まれ、
--id / --status / --skip-reason が含まれないことを確認する。
"""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_PATH = (REPO_ROOT / 'plugins' / 'forge' / 'skills'
                / 'present-findings' / 'scripts' / 'batch_update.py')
EXPECTED_LOW_LEVEL = (REPO_ROOT / 'plugins' / 'forge' / 'scripts'
                      / 'session' / 'update_plan.py')


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "_batch_update_present_findings", WRAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestBatchUpdateWrapper(unittest.TestCase):
    """batch_update.py が update_plan.py --batch を透過的に呼ぶことを検証"""

    def setUp(self):
        self.wrapper = _load_wrapper()

    def test_low_level_path_points_update_plan(self):
        self.assertEqual(self.wrapper.LOW_LEVEL.resolve(),
                         EXPECTED_LOW_LEVEL.resolve())

    def test_positional_arg_and_batch_flag(self):
        """位置引数 {session_dir} と --batch のみが低レベルに渡る"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["batch_update.py", "/tmp/session"]
            with mock.patch.object(sys, "argv", argv):
                rc = self.wrapper.main()
        self.assertEqual(rc, 0)
        cmd = mock_run.call_args.args[0]
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(Path(cmd[1]).resolve(), EXPECTED_LOW_LEVEL.resolve())
        self.assertEqual(cmd[2], "/tmp/session")
        self.assertIn("--batch", cmd)
        # 禁則: 単一項目更新用の flag は付けない
        self.assertNotIn("--id", cmd)
        self.assertNotIn("--status", cmd)
        self.assertNotIn("--skip-reason", cmd)
        # stdin 明示指定は付けない（-（ハイフン）を追加しない）
        self.assertNotIn("-", cmd[3:])
        self.assertFalse(mock_run.call_args.kwargs.get("check", True))

    def test_cmd_has_exactly_four_elements(self):
        """cmd は [python, LOW_LEVEL, session_dir, --batch] の 4 要素のみ"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["batch_update.py", "/tmp/session"]
            with mock.patch.object(sys, "argv", argv):
                self.wrapper.main()
        cmd = mock_run.call_args.args[0]
        self.assertEqual(len(cmd), 4)

    def test_exit_code_transparent(self):
        """低レベル return code をそのまま透過"""
        for code in (0, 1, 2, 42):
            with self.subTest(code=code):
                with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                    mock_run.return_value = subprocess.CompletedProcess(
                        args=[], returncode=code)
                    argv = ["batch_update.py", "/tmp/session"]
                    with mock.patch.object(sys, "argv", argv):
                        rc = self.wrapper.main()
                self.assertEqual(rc, code)

    def test_stdin_inherited_from_parent(self):
        """subprocess.run に stdin / input 引数を渡さない（親プロセスから継承）"""
        with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            argv = ["batch_update.py", "/tmp/session"]
            with mock.patch.object(sys, "argv", argv):
                self.wrapper.main()
        kw = mock_run.call_args.kwargs
        # stdin / input は指定しない（透過継承）
        self.assertNotIn("stdin", kw)
        self.assertNotIn("input", kw)
        # stdout / stderr / capture_output も指定しない
        self.assertNotIn("capture_output", kw)
        self.assertNotIn("stdout", kw)
        self.assertNotIn("stderr", kw)


if __name__ == "__main__":
    unittest.main()
