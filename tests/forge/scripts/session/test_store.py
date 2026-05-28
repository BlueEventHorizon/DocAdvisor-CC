"""session.store のテスト。"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[4] / "plugins" / "forge" / "scripts"),
)

from session.store import SessionStore
from session.yaml_utils import read_yaml


class _FsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-abc123"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestSessionStorePathSafety(_FsTestCase):
    def test_rejects_absolute_path(self):
        store = SessionStore(str(self.session_dir))
        with self.assertRaises(ValueError):
            store.write_text("/tmp/outside.yaml", "x")

    def test_rejects_traversal(self):
        store = SessionStore(str(self.session_dir))
        with self.assertRaises(ValueError):
            store.write_text("../outside.yaml", "x")

    def test_rejects_nested_traversal(self):
        store = SessionStore(str(self.session_dir))
        with self.assertRaises(ValueError):
            store.write_text("refs/../../outside.yaml", "x")


class TestSessionStoreWrite(_FsTestCase):
    def test_write_text_creates_file(self):
        store = SessionStore(str(self.session_dir))
        path = store.write_text("refs.yaml", "target_files:\n  - a.py\n")

        self.assertEqual(path, self.session_dir / "refs.yaml")
        self.assertEqual(
            (self.session_dir / "refs.yaml").read_text(encoding="utf-8"),
            "target_files:\n  - a.py\n",
        )

    def test_write_nested_yaml(self):
        store = SessionStore(str(self.session_dir))

        path = store.write_nested_yaml(
            "refs.yaml",
            [("target_files", ["a.py"]), ("reference_docs", [{"path": "docs/r.md"}])],
        )

        self.assertEqual(path, self.session_dir / "refs.yaml")
        data = read_yaml(str(path))
        self.assertEqual(data["target_files"], ["a.py"])
        self.assertEqual(data["reference_docs"][0]["path"], "docs/r.md")


if __name__ == "__main__":
    unittest.main()
