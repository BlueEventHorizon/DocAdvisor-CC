#!/usr/bin/env python3
"""start-uxui-design/scripts/find_session.py の薄い wrapper テスト。"""

import unittest

from tests.forge.wrapper_helpers import (
    SESSION_MANAGER,
    assert_exit_code_transparent,
    assert_find_session_command,
    assert_low_level,
    assert_transparent_subprocess_kwargs,
    command_from_mock,
    invoke_with_mocked_run,
    load_wrapper,
    wrapper_path,
)

EXPECTED_SKILL = 'start-uxui-design'
WRAPPER_PATH = wrapper_path(EXPECTED_SKILL, "find_session.py")


class TestFindSessionWrapper(unittest.TestCase):
    """find_session.py が session_manager.py find を透過的に呼ぶことを検証。"""

    def setUp(self):
        self.wrapper = load_wrapper(WRAPPER_PATH, '_find_session_start_uxui_design')

    def test_skill_hardcoded(self):
        self.assertEqual(self.wrapper.SKILL, EXPECTED_SKILL)

    def test_low_level_path_points_session_manager(self):
        assert_low_level(self, self.wrapper, SESSION_MANAGER)

    def test_subprocess_called_with_find_skill(self):
        rc, mock_run = invoke_with_mocked_run(self.wrapper, argv=["find_session.py"])
        self.assertEqual(rc, 0)
        assert_find_session_command(self, command_from_mock(mock_run), EXPECTED_SKILL)
        assert_transparent_subprocess_kwargs(self, mock_run)

    def test_exit_code_transparent(self):
        assert_exit_code_transparent(self, self.wrapper, lambda: ["find_session.py"])

    def test_extra_argv_not_passed_through(self):
        _rc, mock_run = invoke_with_mocked_run(
            self.wrapper, argv=["find_session.py", "--extra", "v"]
        )
        cmd = command_from_mock(mock_run)
        assert_find_session_command(self, cmd, EXPECTED_SKILL)
        self.assertNotIn("--extra", cmd)
        self.assertNotIn("v", cmd)


if __name__ == "__main__":
    unittest.main()
