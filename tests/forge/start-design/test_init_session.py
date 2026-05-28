#!/usr/bin/env python3
"""start-design/scripts/init_session.py の薄い wrapper テスト。"""

import unittest

from tests.forge.wrapper_helpers import (
    SESSION_MANAGER,
    assert_exit_code_transparent,
    assert_init_session_command,
    assert_low_level,
    assert_transparent_subprocess_kwargs,
    command_from_mock,
    invoke_with_mocked_run,
    load_wrapper,
    wrapper_path,
)

EXPECTED_SKILL = 'start-design'
WRAPPER_PATH = wrapper_path(EXPECTED_SKILL, "init_session.py")


class TestInitSessionWrapper(unittest.TestCase):
    """位置引数 {feature} {mode} {output_dir} を init flags に変換する。"""

    def setUp(self):
        self.wrapper = load_wrapper(WRAPPER_PATH, '_init_session_start_design')

    def test_skill_hardcoded(self):
        self.assertEqual(self.wrapper.SKILL, EXPECTED_SKILL)

    def test_low_level_path_points_session_manager(self):
        assert_low_level(self, self.wrapper, SESSION_MANAGER)

    def test_positional_args_mapped_to_flags(self):
        rc, mock_run = invoke_with_mocked_run(self.wrapper, argv=['init_session.py', 'my_feature', 'new', '/tmp/out'])
        self.assertEqual(rc, 0)
        assert_init_session_command(
            self,
            command_from_mock(mock_run),
            EXPECTED_SKILL,
            {'--feature': 'my_feature', '--mode': 'new', '--output-dir': '/tmp/out'},
        )
        assert_transparent_subprocess_kwargs(self, mock_run)

    def test_exit_code_transparent(self):
        assert_exit_code_transparent(self, self.wrapper, lambda: ['init_session.py', 'f', 'new', '/tmp/out'])


if __name__ == "__main__":
    unittest.main()
