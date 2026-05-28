#!/usr/bin/env python3
"""start-uxui-design/scripts/resolve_doc.py の薄い wrapper テスト。"""

import unittest

from tests.forge.wrapper_helpers import (
    RESOLVE_DOC_STRUCTURE,
    assert_exit_code_transparent,
    assert_low_level,
    assert_resolve_doc_command,
    assert_transparent_subprocess_kwargs,
    command_from_mock,
    invoke_with_mocked_run,
    load_wrapper,
    wrapper_path,
)

EXPECTED_SKILL = 'start-uxui-design'
EXPECTED_DOC_TYPE = 'requirement'
WRAPPER_PATH = wrapper_path(EXPECTED_SKILL, "resolve_doc.py")


class TestResolveDocWrapper(unittest.TestCase):
    """resolve_doc.py が doc-type を固定して低レベル script へ透過することを検証。"""

    def setUp(self):
        self.wrapper = load_wrapper(WRAPPER_PATH, '_resolve_doc_start_uxui_design')

    def test_doc_type_hardcoded(self):
        self.assertEqual(self.wrapper.DOC_TYPE, EXPECTED_DOC_TYPE)

    def test_low_level_path_points_resolve_doc_structure(self):
        assert_low_level(self, self.wrapper, RESOLVE_DOC_STRUCTURE)

    def test_subprocess_called_with_doc_type(self):
        rc, mock_run = invoke_with_mocked_run(self.wrapper)
        self.assertEqual(rc, 0)
        assert_resolve_doc_command(self, command_from_mock(mock_run), EXPECTED_DOC_TYPE)
        assert_transparent_subprocess_kwargs(self, mock_run)

    def test_exit_code_transparent(self):
        assert_exit_code_transparent(self, self.wrapper, lambda: None)


if __name__ == "__main__":
    unittest.main()
