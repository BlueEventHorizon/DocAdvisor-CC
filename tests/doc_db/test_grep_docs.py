import io
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import grep_docs


def _write_doc_structure(root: pathlib.Path, exclude_archive: bool = False):
    rules_exclude = "    exclude: [archive]" if exclude_archive else "    exclude: []"
    lines = [
        "rules:",
        "  root_dirs:",
        "    - docs/rules/",
        "  doc_types_map:",
        "    docs/rules/: rule",
        "  patterns:",
        '    target_glob: "**/*.md"',
        rules_exclude,
    ]
    lines.extend(
        [
            "specs:",
            "  root_dirs:",
            "    - docs/specs/**/requirements/",
            "    - docs/specs/**/design/",
            "    - docs/specs/**/plan/",
            "  doc_types_map:",
            "    docs/specs/**/requirements/: requirement",
            "    docs/specs/**/design/: design",
            "    docs/specs/**/plan/: plan",
            "  patterns:",
            '    target_glob: "**/*.md"',
            "    exclude: []",
        ]
    )
    (root / ".doc_structure.yaml").write_text("\n".join(lines), encoding="utf-8")


class GrepDocsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "docs/rules").mkdir(parents=True)
        (self.root / "docs/specs/f1/requirements").mkdir(parents=True)
        (self.root / "docs/specs/f1/design").mkdir(parents=True)
        (self.root / "docs/specs/f1/plan").mkdir(parents=True)
        (self.root / "docs/rules/a.md").write_text(
            "# Rule\nline with FooMarker\nother\n",
            encoding="utf-8",
        )
        (self.root / "docs/specs/f1/requirements/r1.md").write_text(
            "REQ-001 in line 1\nno match here\nSECRET-ID twice SECRET-ID\n",
            encoding="utf-8",
        )
        (self.root / "docs/specs/f1/design/d1.md").write_text(
            "design line\n",
            encoding="utf-8",
        )
        (self.root / "docs/specs/f1/plan/p1.md").write_text(
            "plan only content PLAN-XYZ\n",
            encoding="utf-8",
        )
        _write_doc_structure(self.root, exclude_archive=False)
        self._old_proj = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)

    def tearDown(self):
        if self._old_proj is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._old_proj
        self.tmp.cleanup()

    def test_rules_keyword_match_and_line_numbers(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "FooMarker"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["path"], "docs/rules/a.md")
        self.assertEqual(data["results"][0]["line"], 2)
        self.assertIn("FooMarker", data["results"][0]["content"])

    def test_case_insensitive(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "foomarker"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["results"]), 1)

    def test_specs_default_doc_types_includes_all(self):
        """--doc-type 省略時は .doc_structure.yaml の全 doc_type（plan 含む）を検索する。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "specs", "--keyword", "PLAN-XYZ"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["path"], "docs/specs/f1/plan/p1.md")

    def test_specs_explicit_plan_doc_type_finds_plan(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(
                ["--category", "specs", "--doc-type", "plan", "--keyword", "PLAN-XYZ"]
            )
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["path"], "docs/specs/f1/plan/p1.md")

    def test_multiple_matches_same_file(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "specs", "--keyword", "SECRET-ID"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        hits = [r for r in data["results"] if r["path"] == "docs/specs/f1/requirements/r1.md"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["line"], 3)
        self.assertEqual(hits[0]["content"].count("SECRET-ID"), 2)

    def test_empty_results(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "ZZZ_NOT_THERE"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["results"], [])

    def test_empty_keyword_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "   "])
        self.assertEqual(rc, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "error")

    def test_invalid_doc_type(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(
                ["--category", "specs", "--doc-type", "nosuch", "--keyword", "x"]
            )
        self.assertEqual(rc, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "error")
        self.assertIn("unsupported doc_type", data["error"])

    def test_exclude_directory(self):
        arch = self.root / "docs/rules/archive"
        arch.mkdir(parents=True)
        (arch / "hidden.md").write_text("SECRET-IN-ARCHIVE\n", encoding="utf-8")
        _write_doc_structure(self.root, exclude_archive=True)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "SECRET-IN-ARCHIVE"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["results"], [])

    def test_rules_ignores_doc_type_filter(self):
        """--doc-type は rules では無視され、rules の全ファイルが対象。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(
                ["--category", "rules", "--doc-type", "plan", "--keyword", "FooMarker"]
            )
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["results"]), 1)

    def test_keyword_too_long(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "x" * 1025])
        self.assertEqual(rc, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "error")
        self.assertIn("1..1024", data["error"])

    def test_skipped_files_on_unreadable(self):
        unreadable = self.root / "docs/rules/unreadable.md"
        unreadable.write_text("HIDDEN content\n", encoding="utf-8")
        unreadable.chmod(0o000)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = grep_docs.main(["--category", "rules", "--keyword", "HIDDEN"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["status"], "partial")
            self.assertIn("skipped_files", data)
            self.assertIn("docs/rules/unreadable.md", data["skipped_files"])
        finally:
            unreadable.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
