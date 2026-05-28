import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

ROOT = pathlib.Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import build_index
import llm_rerank
import search_index
from search_index import SearchError


def _write_doc_structure(root: pathlib.Path):
    (root / ".doc_structure.yaml").write_text(
        "\n".join(
            [
                "rules:",
                "  root_dirs:",
                "    - docs/rules/",
                "  doc_types_map:",
                "    docs/rules/: rule",
                "  patterns:",
                "    target_glob: \"**/*.md\"",
                "    exclude: []",
                "specs:",
                "  root_dirs:",
                "    - docs/specs/**/requirements/",
                "    - docs/specs/**/design/",
                "  doc_types_map:",
                "    docs/specs/**/requirements/: requirement",
                "    docs/specs/**/design/: design",
                "  patterns:",
                "    target_glob: \"**/*.md\"",
                "    exclude: []",
            ]
        ),
        encoding="utf-8",
    )


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "docs/rules").mkdir(parents=True)
        (self.root / "docs/specs/f1/requirements").mkdir(parents=True)
        (self.root / "docs/specs/f1/design").mkdir(parents=True)
        (self.root / "docs/rules/a.md").write_text("# FNC-006\nalpha body", encoding="utf-8")
        (self.root / "docs/specs/f1/requirements/r1.md").write_text("# REQ-001\nspec body", encoding="utf-8")
        (self.root / "docs/specs/f1/design/d1.md").write_text("# DES-001\ndesign body", encoding="utf-8")
        _write_doc_structure(self.root)
        self._old_api_key = os.environ.get("OPENAI_API_DOCDB_KEY")
        os.environ["OPENAI_API_DOCDB_KEY"] = "dummy"

        self._old_embed = build_index.call_embedding_api
        self._old_qembed = search_index.call_embedding_api_single
        self._old_rerank = llm_rerank.rerank
        build_index.call_embedding_api = lambda texts, _: [[0.1, 0.2] for _ in texts]
        search_index.call_embedding_api_single = lambda *_: [0.1, 0.2]
        llm_rerank.rerank = lambda _q, cand, _k: (
            list(reversed(cand)),
            {
                "fallback_used": False,
                "rerank_error": None,
                "api_calls": 1,
                "token_usage": 111,
                "candidate_count": len(cand),
            },
        )
        build_index.run_build(self.root, "rules", full=True)

    def tearDown(self):
        build_index.call_embedding_api = self._old_embed
        search_index.call_embedding_api_single = self._old_qembed
        llm_rerank.rerank = self._old_rerank
        if self._old_api_key is None:
            os.environ.pop("OPENAI_API_DOCDB_KEY", None)
        else:
            os.environ["OPENAI_API_DOCDB_KEY"] = self._old_api_key
        self.tmp.cleanup()

    def test_modes(self):
        for mode in ("emb", "lex", "hybrid", "rerank"):
            rc, result = search_index.search(self.root, "rules", "FNC-006", mode, 5)
            self.assertEqual(rc, 0)
            self.assertIn("results", result)

    def test_validation_query_length(self):
        err = StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SearchError) as ctx:
                search_index.search(self.root, "rules", "", "lex", 5)
        self.assertEqual(ctx.exception.exit_code, 2)
        self.assertIn('"event_type": "validation_error"', err.getvalue())

    def test_validation_top_n(self):
        err = StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SearchError) as ctx:
                search_index.search(self.root, "rules", "abc", "lex", 0)
        self.assertEqual(ctx.exception.exit_code, 2)
        self.assertIn('"event_type": "validation_error"', err.getvalue())

    def test_validation_doc_type_allowlist(self):
        err = StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SearchError) as ctx:
                search_index.search(self.root, "specs", "abc", "lex", 3, doc_type="invalid")
        self.assertEqual(ctx.exception.exit_code, 2)
        self.assertIn("unsupported doc_type", err.getvalue())

    def test_generated_at_mismatch(self):
        checksums_path = build_index.get_checksums_path(build_index.get_index_path(self.root, "rules"))
        txt = checksums_path.read_text(encoding="utf-8").replace("generated_at:", "generated_at: 1999-01-01T00:00:00Z #")
        checksums_path.write_text(txt, encoding="utf-8")
        with self.assertRaises(SearchError) as ctx:
            search_index.search(self.root, "rules", "x", "lex", 3)
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_stale_auto_rebuild(self):
        (self.root / "docs/rules/a.md").write_text("# FNC-006\nupdated body", encoding="utf-8")
        rc, result = search_index.search(self.root, "rules", "updated", "hybrid", 3)
        self.assertEqual(rc, 0)
        index = json.loads(build_index.get_index_path(self.root, "rules").read_text(encoding="utf-8"))
        bodies = [v["body"] for v in index["entries"].values()]
        self.assertTrue(any("updated body" in b for b in bodies))

    def test_new_file_detected_as_stale_and_rebuilt(self):
        (self.root / "docs/rules/new.md").write_text("# NEW-ID\nnew file body", encoding="utf-8")
        rc, result = search_index.search(self.root, "rules", "NEW-ID", "lex", 5)
        self.assertEqual(rc, 0)
        index = json.loads(build_index.get_index_path(self.root, "rules").read_text(encoding="utf-8"))
        paths = {v["path"] for v in index["entries"].values()}
        self.assertIn("docs/rules/new.md", paths)

    def test_specs_missing_index_is_auto_built(self):
        req_index = build_index.get_index_path(self.root, "specs", "requirement")
        des_index = build_index.get_index_path(self.root, "specs", "design")
        req_index.unlink(missing_ok=True)
        des_index.unlink(missing_ok=True)
        rc, result = search_index.search(self.root, "specs", "REQ-001", "lex", 5)
        self.assertEqual(rc, 0)
        self.assertTrue(req_index.exists())
        self.assertTrue(des_index.exists())
        req_data = json.loads(req_index.read_text(encoding="utf-8"))
        des_data = json.loads(des_index.read_text(encoding="utf-8"))
        req_paths = {v["path"] for v in req_data["entries"].values()}
        des_paths = {v["path"] for v in des_data["entries"].values()}
        self.assertIn("docs/specs/f1/requirements/r1.md", req_paths)
        self.assertIn("docs/specs/f1/design/d1.md", des_paths)

    def test_specs_default_doc_types_dynamic(self):
        """--doc-type 省略時は .doc_structure.yaml の全 doc_type を動的取得する。"""
        # plan を追加した .doc_structure.yaml を作成
        (self.root / "docs/specs/f1/plan").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/specs/f1/plan/p1.md").write_text("# PLAN\nplan body", encoding="utf-8")
        (self.root / ".doc_structure.yaml").write_text(
            "\n".join([
                "rules:",
                "  root_dirs:",
                "    - docs/rules/",
                "  doc_types_map:",
                "    docs/rules/: rule",
                "  patterns:",
                '    target_glob: "**/*.md"',
                "    exclude: []",
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
            ]),
            encoding="utf-8",
        )
        rc, result = search_index.search(self.root, "specs", "plan body", "lex", 5)
        self.assertEqual(rc, 0)
        paths = [r["path"] for r in result["results"]]
        self.assertIn("docs/specs/f1/plan/p1.md", paths)

    def test_auto_rebuild_does_not_pollute_stdout(self):
        """Regression: search() must not write anything to stdout (I/O separation)."""
        (self.root / "docs/rules/extra.md").write_text("# EXTRA\nextra body", encoding="utf-8")
        stdout_capture = StringIO()
        with redirect_stdout(stdout_capture):
            rc, result = search_index.search(self.root, "rules", "EXTRA", "lex", 5)
        self.assertEqual(rc, 0)
        self.assertEqual(stdout_capture.getvalue(), "")
        self.assertIn("results", result)
        self.assertNotIn("index", result)


if __name__ == "__main__":
    unittest.main()
