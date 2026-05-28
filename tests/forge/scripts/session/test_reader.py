"""session.reader のテスト。"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[4] / "plugins" / "forge" / "scripts"),
)

from session.reader import (
    REFS_FILES,
    SESSION_FILES,
    read_entry,
    read_session_files,
)


class _FsTestCase(unittest.TestCase):
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


class TestReadEntry(_FsTestCase):
    def test_missing_file(self):
        result = read_entry(self.session_dir / "missing.yaml")
        self.assertFalse(result["exists"])
        self.assertIsNone(result["content"])

    def test_yaml_file(self):
        self._write("session.yaml", "skill: review\nstatus: in_progress\n")
        result = read_entry(self.session_dir / "session.yaml")
        self.assertTrue(result["exists"])
        self.assertEqual(result["content"]["skill"], "review")

    def test_empty_yaml_returns_empty_dict(self):
        self._write("empty.yaml", "")
        result = read_entry(self.session_dir / "empty.yaml")
        self.assertEqual(result["content"], {})

    def test_markdown_file(self):
        self._write("review.md", "# Review\n\nSome content\n")
        result = read_entry(self.session_dir / "review.md")
        self.assertTrue(result["exists"])
        self.assertIn("# Review", result["content"])

    def test_yaml_parse_error_entry(self):
        def bad_parser(_content):
            raise ValueError("bad yaml")

        self._write("broken.yaml", "x: y\n")
        result = read_entry(self.session_dir / "broken.yaml", yaml_parser=bad_parser)
        self.assertTrue(result["exists"])
        self.assertIsNone(result["content"])
        self.assertIn("bad yaml", result["error"])


class TestReadSessionFiles(_FsTestCase):
    def test_default_files(self):
        self._write("session.yaml", "skill: review\n")
        self._write("refs.yaml", "target_files:\n  - a.py\n")
        self._write("refs/specs.yaml", "documents:\n  - path: spec.md\n")

        result = read_session_files(str(self.session_dir))
        for name in SESSION_FILES:
            self.assertIn(name, result["files"])
        for name in REFS_FILES:
            self.assertIn(name, result["refs"])
        self.assertTrue(result["files"]["session.yaml"]["exists"])
        self.assertTrue(result["refs"]["specs.yaml"]["exists"])

    def test_file_filter(self):
        self._write("session.yaml", "skill: review\n")
        self._write("plan.yaml", "items:\n  - id: 1\n")

        result = read_session_files(str(self.session_dir), ["session.yaml"])
        self.assertIn("session.yaml", result["files"])
        self.assertNotIn("plan.yaml", result["files"])

    def test_custom_session_files(self):
        result = read_session_files(
            str(self.session_dir),
            session_files=["session.yaml", "requirements.md", "design.md"],
            refs_files=REFS_FILES,
        )
        self.assertIn("requirements.md", result["files"])
        self.assertIn("design.md", result["files"])


if __name__ == "__main__":
    unittest.main()
