import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

ROOT = pathlib.Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import build_index


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


class BuildIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "docs/rules").mkdir(parents=True)
        (self.root / "docs/specs/f1/requirements").mkdir(parents=True)
        (self.root / "docs/specs/f1/design").mkdir(parents=True)
        (self.root / "docs/rules/a.md").write_text("# Title\nbody", encoding="utf-8")
        (self.root / "docs/specs/f1/requirements/r1.md").write_text("# R1\nbody", encoding="utf-8")
        (self.root / "docs/specs/f1/design/d1.md").write_text("# D1\nbody", encoding="utf-8")
        _write_doc_structure(self.root)
        self._old_api_key = os.environ.get("OPENAI_API_DOCDB_KEY")
        os.environ["OPENAI_API_DOCDB_KEY"] = "dummy"
        self._old_embed = build_index.call_embedding_api
        build_index.call_embedding_api = lambda texts, _: [[0.1, 0.2] for _ in texts]

    def tearDown(self):
        build_index.call_embedding_api = self._old_embed
        if self._old_api_key is None:
            os.environ.pop("OPENAI_API_DOCDB_KEY", None)
        else:
            os.environ["OPENAI_API_DOCDB_KEY"] = self._old_api_key
        self.tmp.cleanup()

    def test_build_chunk_index(self):
        rc, _ = build_index.run_build(self.root, "rules", full=True)
        self.assertEqual(rc, 0)
        index_path = build_index.get_index_path(self.root, "rules")
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["build_state"], "complete")
        self.assertGreater(len(data["entries"]), 0)

    def test_schema_mismatch_requires_full(self):
        index_path = build_index.get_index_path(self.root, "rules")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps({"metadata": {"schema_version": "0.0"}, "entries": {}}),
            encoding="utf-8",
        )
        rc, _ = build_index.run_build(self.root, "rules", full=False)
        self.assertEqual(rc, 2)

    def test_failed_chunks_mark_incomplete(self):
        def _raise(*_args, **_kwargs):
            raise RuntimeError("boom")

        build_index.call_embedding_api = _raise
        rc, _ = build_index.run_build(self.root, "rules", full=True)
        self.assertEqual(rc, 0)
        data = json.loads(build_index.get_index_path(self.root, "rules").read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["build_state"], "incomplete")
        self.assertGreater(len(data["metadata"]["failed_chunks"]), 0)

    def test_specs_doc_type_split(self):
        rc, _ = build_index.run_build(self.root, "specs", full=True)
        self.assertEqual(rc, 0)
        req_index = build_index.get_index_path(self.root, "specs", "requirement")
        des_index = build_index.get_index_path(self.root, "specs", "design")
        self.assertTrue(req_index.exists())
        self.assertTrue(des_index.exists())
        req_data = json.loads(req_index.read_text(encoding="utf-8"))
        des_data = json.loads(des_index.read_text(encoding="utf-8"))
        self.assertGreater(len(req_data["entries"]), 0)
        self.assertGreater(len(des_data["entries"]), 0)

        req_gen = req_data["metadata"]["generated_at"]
        req_checksum_gen = build_index._read_checksums_generated_at(
            build_index.get_checksums_path(req_index)
        )
        des_gen = des_data["metadata"]["generated_at"]
        des_checksum_gen = build_index._read_checksums_generated_at(
            build_index.get_checksums_path(des_index)
        )
        self.assertEqual(req_gen, req_checksum_gen)
        self.assertEqual(des_gen, des_checksum_gen)

    def test_two_phase_failure_keeps_old_state(self):
        index_path = build_index.get_index_path(self.root, "rules")
        checksums_path = build_index.get_checksums_path(index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        checksums_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text('{"old": true}', encoding="utf-8")
        checksums_path.write_text("generated_at: old\nchecksums:\n", encoding="utf-8")

        old_replace = build_index.os.replace
        counter = {"n": 0}

        def flaky_replace(src, dst):
            counter["n"] += 1
            if counter["n"] == 2:
                raise OSError("replace failed")
            return old_replace(src, dst)

        build_index.os.replace = flaky_replace
        try:
            with self.assertRaises(OSError):
                build_index.save_index_and_checksums_two_phase(
                    {"metadata": {}, "entries": {}},
                    index_path,
                    {"a.md": "hash"},
                    checksums_path,
                    "2026-01-01T00:00:00Z",
                )
        finally:
            build_index.os.replace = old_replace

        self.assertEqual(index_path.read_text(encoding="utf-8"), '{"old": true}')
        self.assertIn("generated_at: old", checksums_path.read_text(encoding="utf-8"))

    def test_validation_doc_type_not_allowed_for_rules(self):
        err = StringIO()
        with redirect_stderr(err):
            rc, _ = build_index.run_build(self.root, "rules", full=True, doc_type="requirement")
        self.assertEqual(rc, 2)
        self.assertIn("validation_error", err.getvalue())

    def test_validation_doc_type_allowlist_specs(self):
        err = StringIO()
        with redirect_stderr(err):
            rc, _ = build_index.run_build(self.root, "specs", full=True, doc_type="invalid")
        self.assertEqual(rc, 2)
        self.assertIn("unsupported doc_type", err.getvalue())


class OutputDirTests(unittest.TestCase):
    """get_index_path が output_dir を尊重するかのテスト。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "docs/rules").mkdir(parents=True)
        (self.root / "docs/rules/a.md").write_text("# A\nbody", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_path_without_output_dir(self):
        """output_dir 未設定時はデフォルトの .claude/doc-db/index/ を使う。"""
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
            ]),
            encoding="utf-8",
        )
        path = build_index.get_index_path(self.root, "rules")
        self.assertEqual(
            path,
            self.root / ".claude" / "doc-db" / "index" / "rules" / "rules_index.json",
        )

    def test_custom_path_with_output_dir(self):
        """output_dir 設定時はそのディレクトリにインデックスを出力する。"""
        (self.root / ".doc_structure.yaml").write_text(
            "\n".join([
                "rules:",
                "  output_dir: custom/test_output/",
                "  root_dirs:",
                "    - docs/rules/",
                "  doc_types_map:",
                "    docs/rules/: rule",
                "  patterns:",
                '    target_glob: "**/*.md"',
                "    exclude: []",
            ]),
            encoding="utf-8",
        )
        path = build_index.get_index_path(self.root, "rules")
        self.assertEqual(
            path,
            self.root / "custom" / "test_output" / "index" / "rules" / "rules_index.json",
        )

    def test_specs_with_output_dir(self):
        """specs カテゴリでも output_dir が効く。"""
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
                "  output_dir: meta/test/",
                "  root_dirs:",
                '    - "docs/specs/**/requirements/"',
                "  doc_types_map:",
                '    "docs/specs/**/requirements/": requirement',
                "  patterns:",
                '    target_glob: "**/*.md"',
                "    exclude: []",
            ]),
            encoding="utf-8",
        )
        path = build_index.get_index_path(self.root, "specs", "requirement")
        self.assertEqual(
            path,
            self.root / "meta" / "test" / "index" / "specs" / "requirement_index.json",
        )

    def test_missing_doc_structure_falls_back_to_default(self):
        """doc_structure.yaml がない場合はデフォルトパスにフォールバック。"""
        path = build_index.get_index_path(self.root, "rules")
        self.assertEqual(
            path,
            self.root / ".claude" / "doc-db" / "index" / "rules" / "rules_index.json",
        )


if __name__ == "__main__":
    unittest.main()
