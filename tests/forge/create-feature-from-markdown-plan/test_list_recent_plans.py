#!/usr/bin/env python3
"""list_recent_plans.py のテスト

実行:
  python3 -m unittest tests.forge.create-feature-from-markdown-plan.test_list_recent_plans -v
  （ハイフン入りパッケージ名のため、loader 経由で実行する）
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "plugins" / "forge" / "skills" / "create-feature-from-markdown-plan" / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

from list_recent_plans import _extract_title, list_plans, main  # noqa: E402


class TestExtractTitle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _write(self, name: str, body: str) -> Path:
        p = self.dir / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_first_h1_extracted(self):
        p = self._write("a.md", "# Hello world\n\n本文\n")
        self.assertEqual(_extract_title(p), "Hello world")

    def test_h1_skips_non_heading_lines(self):
        p = self._write("a.md", "前置き\n\n# 本タイトル\n## サブ\n")
        self.assertEqual(_extract_title(p), "本タイトル")

    def test_no_heading_returns_stem(self):
        p = self._write("plain.md", "ただのテキスト\n## H2 only\n")
        self.assertEqual(_extract_title(p), "plain")

    def test_empty_h1_falls_back_to_stem(self):
        p = self._write("alpha.md", "# \n本文\n")
        self.assertEqual(_extract_title(p), "alpha")

    def test_unreadable_file_returns_stem(self):
        missing = self.dir / "ghost.md"
        # ファイルが存在しないケース。OSError は内部で握りつぶされ stem が返る
        self.assertEqual(_extract_title(missing), "ghost")


class TestListPlans(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _make(self, name: str, mtime: float, body: str = "# Title\n") -> Path:
        p = self.dir / name
        p.write_text(body, encoding="utf-8")
        os.utime(p, (mtime, mtime))
        return p

    def test_missing_dir(self):
        result = list_plans(self.dir / "does-not-exist", limit=5)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["plans"], [])
        self.assertIsNone(result["latest"])

    def test_empty_dir(self):
        result = list_plans(self.dir, limit=5)
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["latest"])

    def test_sorted_descending_by_mtime(self):
        self._make("old.md", 1_700_000_000.0, "# Old\n")
        self._make("mid.md", 1_700_000_500.0, "# Mid\n")
        self._make("new.md", 1_700_001_000.0, "# New\n")

        result = list_plans(self.dir, limit=10)
        self.assertEqual(result["status"], "found")
        names = [Path(p["path"]).name for p in result["plans"]]
        self.assertEqual(names, ["new.md", "mid.md", "old.md"])
        self.assertEqual(Path(result["latest"]).name, "new.md")
        self.assertEqual(result["plans"][0]["title"], "New")

    def test_limit_truncates(self):
        for i in range(5):
            self._make(f"p{i}.md", 1_700_000_000.0 + i)

        result = list_plans(self.dir, limit=2)
        self.assertEqual(len(result["plans"]), 2)
        self.assertEqual(result["count"], 2)

    def test_only_md_files_listed(self):
        self._make("note.md", 1_700_000_000.0, "# md\n")
        # 非 .md は無視される
        (self.dir / "ignore.txt").write_text("# txt\n")
        (self.dir / "ignore.markdown").write_text("# markdown ext\n")

        result = list_plans(self.dir, limit=10)
        self.assertEqual(result["count"], 1)
        self.assertEqual(Path(result["plans"][0]["path"]).name, "note.md")


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_cli_with_plans_dir_flag(self):
        p = self.dir / "sample.md"
        p.write_text("# Sample plan\n", encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "list_recent_plans.py"),
                "--plans-dir",
                str(self.dir),
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["plans"][0]["title"], "Sample plan")

    def test_cli_via_env_var(self):
        env = os.environ.copy()
        env["PLANS_DIR"] = str(self.dir)

        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "list_recent_plans.py")],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["plans_dir"], str(self.dir))

    def test_main_function_returns_zero(self):
        # main() 自体の戻り値と stdout 形式を確認
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--plans-dir", str(self.dir), "--limit", "3"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["status"], "empty")


if __name__ == "__main__":
    unittest.main()
