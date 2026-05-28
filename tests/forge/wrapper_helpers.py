"""forge wrapper script tests の共通 helper。"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_MANAGER = REPO_ROOT / "plugins" / "forge" / "scripts" / "session_manager.py"
RESOLVE_DOC_STRUCTURE = (
    REPO_ROOT
    / "plugins"
    / "forge"
    / "skills"
    / "doc-structure"
    / "scripts"
    / "resolve_doc_structure.py"
)


def wrapper_path(skill, script_name):
    return REPO_ROOT / "plugins" / "forge" / "skills" / skill / "scripts" / script_name


def load_wrapper(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke_with_mocked_run(wrapper, argv=None, returncode=0):
    """wrapper.main() を subprocess.run mock 付きで実行する。"""
    with mock.patch.object(wrapper.subprocess, "run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=returncode
        )
        if argv is None:
            rc = wrapper.main()
        else:
            with mock.patch.object(sys, "argv", argv):
                rc = wrapper.main()
    return rc, mock_run


def command_from_mock(mock_run):
    call_args = mock_run.call_args
    return call_args.args[0] if call_args.args else call_args.kwargs["args"]


def assert_low_level(testcase, wrapper, expected_low_level):
    testcase.assertEqual(wrapper.LOW_LEVEL.resolve(), expected_low_level.resolve())


def assert_transparent_subprocess_kwargs(testcase, mock_run):
    kwargs = mock_run.call_args.kwargs
    testcase.assertFalse(kwargs.get("check", True))
    testcase.assertNotIn("capture_output", kwargs)
    testcase.assertNotIn("stdout", kwargs)
    testcase.assertNotIn("stderr", kwargs)


def assert_exit_code_transparent(testcase, wrapper, argv_factory):
    for code in (0, 1, 2, 42):
        with testcase.subTest(code=code):
            rc, _mock_run = invoke_with_mocked_run(
                wrapper, argv=argv_factory(), returncode=code
            )
            testcase.assertEqual(rc, code)


def assert_find_session_command(testcase, cmd, expected_skill):
    testcase.assertEqual(
        cmd,
        [
            sys.executable,
            str(SESSION_MANAGER),
            "find",
            "--skill",
            expected_skill,
        ],
    )


def assert_init_session_command(testcase, cmd, expected_skill, expected_flags):
    testcase.assertEqual(cmd[0], sys.executable)
    testcase.assertEqual(Path(cmd[1]).resolve(), SESSION_MANAGER.resolve())
    testcase.assertEqual(cmd[2], "init")
    testcase.assertEqual(cmd[cmd.index("--skill") + 1], expected_skill)
    for flag, value in expected_flags.items():
        testcase.assertIn(flag, cmd)
        testcase.assertEqual(cmd[cmd.index(flag) + 1], value)


def assert_resolve_doc_command(testcase, cmd, expected_doc_type):
    testcase.assertEqual(cmd[0], sys.executable)
    testcase.assertEqual(Path(cmd[1]).resolve(), RESOLVE_DOC_STRUCTURE.resolve())
    testcase.assertIn("--doc-type", cmd)
    testcase.assertEqual(cmd[cmd.index("--doc-type") + 1], expected_doc_type)
