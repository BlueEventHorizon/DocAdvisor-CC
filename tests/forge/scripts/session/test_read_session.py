"""read_session のテスト。"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[4] / "plugins" / "forge" / "scripts"),
)

from session.read_session import read_session_files, read_file_entry

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "read_session.py"
)


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテストの基底クラス。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-abc123"
        self.session_dir.mkdir()
        (self.session_dir / "refs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel_path, content):
        p = self.session_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p


class TestReadFileEntry(_FsTestCase):
    """read_file_entry のテスト。"""

    def test_missing_file(self):
        result = read_file_entry(self.session_dir / "missing.yaml")
        self.assertFalse(result["exists"])
        self.assertIsNone(result["content"])

    def test_yaml_file(self):
        self._write("session.yaml", "skill: review\nstatus: in_progress\n")
        result = read_file_entry(self.session_dir / "session.yaml")
        self.assertTrue(result["exists"])
        self.assertEqual(result["content"]["skill"], "review")

    def test_markdown_file(self):
        self._write("review.md", "# Review\n\nSome content\n")
        result = read_file_entry(self.session_dir / "review.md")
        self.assertTrue(result["exists"])
        self.assertIn("# Review", result["content"])


class TestReadSessionFiles(_FsTestCase):
    """read_session_files のテスト。"""

    def test_all_files_present(self):
        self._write("session.yaml", "skill: review\n")
        self._write("refs.yaml", "target_files:\n  - a.py\n")
        self._write("plan.yaml", "items:\n  - id: 1\n    severity: critical\n    title: test\n    status: pending\n")
        self._write("review.md", "# Review\n")
        self._write("refs/specs.yaml", "source: query-specs\ndocuments:\n  - path: spec.md\n    reason: test\n")

        result = read_session_files(str(self.session_dir))
        self.assertTrue(result["files"]["session.yaml"]["exists"])
        self.assertTrue(result["files"]["refs.yaml"]["exists"])
        self.assertTrue(result["files"]["plan.yaml"]["exists"])
        self.assertTrue(result["files"]["review.md"]["exists"])
        self.assertTrue(result["refs"]["specs.yaml"]["exists"])
        self.assertFalse(result["refs"]["rules.yaml"]["exists"])

    def test_partial_files(self):
        """一部ファイルのみ存在。"""
        self._write("session.yaml", "skill: review\n")
        result = read_session_files(str(self.session_dir))
        self.assertTrue(result["files"]["session.yaml"]["exists"])
        self.assertFalse(result["files"]["plan.yaml"]["exists"])

    def test_file_filter(self):
        """ファイルフィルター指定。"""
        self._write("session.yaml", "skill: review\n")
        self._write("plan.yaml", "items:\n  - id: 1\n    title: x\n    severity: major\n    status: pending\n")

        result = read_session_files(str(self.session_dir), ["session.yaml"])
        self.assertIn("session.yaml", result["files"])
        # plan.yaml はフィルターに含まれないので出力されない
        self.assertNotIn("plan.yaml", result["files"])

    def test_empty_session(self):
        """空のセッションディレクトリ。"""
        result = read_session_files(str(self.session_dir))
        for name, entry in result["files"].items():
            self.assertFalse(entry["exists"])


class TestCLI(_FsTestCase):
    """CLI 統合テスト。"""

    def test_basic_cli(self):
        self._write("session.yaml", "skill: review\nstatus: in_progress\n")
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["files"]["session.yaml"]["exists"])

    def test_missing_dir(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.tmpdir / "nonexistent")],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_files_filter_cli(self):
        self._write("session.yaml", "skill: review\n")
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--files", "session.yaml"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertIn("session.yaml", result["files"])


if __name__ == "__main__":
    unittest.main()
