#!/usr/bin/env python3
"""review/scripts/init_session.py のテスト。

DES-028 §4.1 関連:
  - 位置引数 (review_type / engine / auto_count) を session_manager.py の init flags に変換する
  - --files (空白 / カンマ区切り両対応) を session.yaml に保存する
  - --section は完全撤廃。argparse が "unrecognized arguments" として reject する
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.forge.wrapper_helpers import (
    SESSION_MANAGER,
    assert_init_session_command,
    assert_low_level,
    command_from_mock,
    load_wrapper,
    wrapper_path,
)

EXPECTED_SKILL = 'review'
WRAPPER_PATH = wrapper_path(EXPECTED_SKILL, "init_session.py")


def _make_completed_process(session_dir, returncode=0):
    """session_manager init の JSON 出力を模した CompletedProcess を返す。"""
    payload = {"status": "created", "session_dir": str(session_dir)}
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=json.dumps(payload), stderr=""
    )


def _invoke(wrapper, argv, session_dir, returncode=0):
    """subprocess.run を mock してラッパーを実行する。"""
    with mock.patch.object(wrapper.subprocess, "run") as mock_run:
        mock_run.return_value = _make_completed_process(session_dir, returncode)
        with mock.patch.object(sys, "argv", argv):
            rc = wrapper.main()
    return rc, mock_run


class TestInitSessionWrapper(unittest.TestCase):
    """位置引数 + --files の解析と session_manager 呼び出しを検証する。"""

    def setUp(self):
        self.wrapper = load_wrapper(WRAPPER_PATH, '_init_session_review')
        self._tmpdir = tempfile.TemporaryDirectory()
        self.session_dir = Path(self._tmpdir.name) / "review-abc123"
        self.session_dir.mkdir()
        # session_manager.py が事前に書き出すであろう session.yaml を再現
        (self.session_dir / "session.yaml").write_text(
            'skill: review\n'
            'started_at: "2026-05-21T00:00:00Z"\n'
            'last_updated: "2026-05-21T00:00:00Z"\n'
            'status: in_progress\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 基本: 位置引数のマッピング
    # ------------------------------------------------------------------

    def test_skill_hardcoded(self):
        self.assertEqual(self.wrapper.SKILL, EXPECTED_SKILL)

    def test_low_level_path_points_session_manager(self):
        assert_low_level(self, self.wrapper, SESSION_MANAGER)

    def test_positional_args_mapped_to_flags(self):
        rc, mock_run = _invoke(
            self.wrapper,
            argv=['init_session.py', 'code', 'codex', '3'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        assert_init_session_command(
            self,
            command_from_mock(mock_run),
            EXPECTED_SKILL,
            {
                '--review-type': 'code',
                '--engine': 'codex',
                '--auto-count': '3',
                '--current-cycle': '0',
            },
        )

    def test_exit_code_transparent(self):
        for code in (0, 1, 2, 42):
            with self.subTest(code=code):
                rc, _mock_run = _invoke(
                    self.wrapper,
                    argv=['init_session.py', 'code', 'codex', '3'],
                    session_dir=self.session_dir,
                    returncode=code,
                )
                self.assertEqual(rc, code)

    # ------------------------------------------------------------------
    # --files の session.yaml 保存
    # ------------------------------------------------------------------

    def _read_session_yaml(self):
        from plugins.forge.scripts.session.yaml_utils import read_yaml  # noqa: E501
        return read_yaml(self.session_dir / "session.yaml")

    def test_files_not_provided_writes_empty_list(self):
        """--files 未指定時は空配列として session.yaml に明示記録する。"""
        rc, _ = _invoke(
            self.wrapper,
            argv=['init_session.py', 'code', 'codex', '3'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        text = (self.session_dir / "session.yaml").read_text(encoding="utf-8")
        self.assertIn("files: []", text)

    def test_files_single_value(self):
        rc, _ = _invoke(
            self.wrapper,
            argv=['init_session.py', 'design', 'codex', '0', '--files', 'docs/a.md'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        text = (self.session_dir / "session.yaml").read_text(encoding="utf-8")
        self.assertIn('files: ["docs/a.md"]', text)

    def test_files_multiple_space_separated(self):
        rc, _ = _invoke(
            self.wrapper,
            argv=['init_session.py', 'design', 'codex', '0',
                  '--files', 'docs/a.md', 'docs/b.md'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        text = (self.session_dir / "session.yaml").read_text(encoding="utf-8")
        self.assertIn('files: ["docs/a.md", "docs/b.md"]', text)

    def test_files_comma_separated(self):
        rc, _ = _invoke(
            self.wrapper,
            argv=['init_session.py', 'design', 'codex', '0',
                  '--files', 'docs/a.md,docs/b.md'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        text = (self.session_dir / "session.yaml").read_text(encoding="utf-8")
        self.assertIn('files: ["docs/a.md", "docs/b.md"]', text)

    def test_files_mixed_space_and_comma(self):
        rc, _ = _invoke(
            self.wrapper,
            argv=['init_session.py', 'design', 'codex', '0',
                  '--files', 'a.md,b.md', 'c.md'],
            session_dir=self.session_dir,
        )
        self.assertEqual(rc, 0)
        text = (self.session_dir / "session.yaml").read_text(encoding="utf-8")
        self.assertIn('files: ["a.md", "b.md", "c.md"]', text)

    def test_session_manager_not_called_with_files_flag(self):
        """--files は init_session が消費し、session_manager には渡さない。"""
        _, mock_run = _invoke(
            self.wrapper,
            argv=['init_session.py', 'code', 'codex', '3', '--files', 'a.md'],
            session_dir=self.session_dir,
        )
        cmd = command_from_mock(mock_run)
        self.assertNotIn('--files', cmd)

    # ------------------------------------------------------------------
    # --section の完全撤廃
    # ------------------------------------------------------------------

    def test_section_flag_rejected(self):
        """--section は DES-028 で完全撤廃。argparse が SystemExit で reject する。"""
        with mock.patch.object(sys, "argv",
                               ['init_session.py', 'code', 'codex', '3',
                                '--section', '4.1']):
            with mock.patch.object(self.wrapper.subprocess, "run") as mock_run:
                with self.assertRaises(SystemExit) as ctx:
                    self.wrapper.main()
                # session_manager は呼ばれてはならない
                mock_run.assert_not_called()
        # argparse の unrecognized-args は exit code 2
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
