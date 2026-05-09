"""
doc-db 機能テスト (Layer 1) — TST-001 準拠

setup.sh --with-doc-db でインストールされたスクリプトを対象とする。
Embedding / Rerank は全てモック化し、API キー不要で動作する。

Created by k2moons
"""

import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

# インストール済みスクリプトを優先、フォールバックで bw-cc-plugins ソース
_installed = PROJECT_ROOT / "tests" / "test_project" / ".claude" / "doc-db" / "scripts"
_source = PROJECT_ROOT / "bw-cc-plugins" / "plugins" / "doc-db" / "scripts"

if _installed.is_dir():
    SCRIPTS_PATH = _installed
elif _source.is_dir():
    SCRIPTS_PATH = _source
else:
    raise FileNotFoundError(
        "doc-db scripts not found. Run: bash setup.sh --source bw-cc-plugins "
        "--target tests/test_project --with-doc-db"
    )

sys.path.insert(0, str(SCRIPTS_PATH))

import build_index
import chunk_extractor
import doc_structure
import embedding_api
import grep_docs
import hybrid_score
import lexical_search
import llm_rerank
import search_index
import _utils

# ---------------------------------------------------------------------------
# テスト用定数
# ---------------------------------------------------------------------------

FIXED_DIM = 1536
FIXED_VEC = [0.1] * FIXED_DIM

DOC_STRUCTURE_YAML = """\
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
specs:
  root_dirs:
    - specs/requirements/
    - specs/design/
  doc_types_map:
    specs/requirements/: requirement
    specs/design/: design
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""

RULES_CODING = """\
# Coding Standards
## Naming
Use camelCase for variables. MARKER_RULE_CODING_001.
"""

RULES_NAMING = """\
# Naming Convention
## Functions
Use snake_case for functions. MARKER_RULE_NAMING_002.
"""

SPECS_REQ = """\
# User Authentication Requirements
## FR-001: Login
Users can log in with email and password. MARKER_SPEC_REQ_003.
"""

SPECS_DESIGN = """\
# Authentication API Design
## Endpoints
POST /api/auth/login. MARKER_SPEC_DES_004.
"""


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


def _create_test_project(root: pathlib.Path):
    """一時ディレクトリにテスト用プロジェクトを構築する。"""
    (root / "rules").mkdir(parents=True)
    (root / "specs/requirements").mkdir(parents=True)
    (root / "specs/design").mkdir(parents=True)

    (root / ".doc_structure.yaml").write_text(DOC_STRUCTURE_YAML, encoding="utf-8")
    (root / "rules/coding_standards.md").write_text(RULES_CODING, encoding="utf-8")
    (root / "rules/naming_convention.md").write_text(RULES_NAMING, encoding="utf-8")
    (root / "specs/requirements/user_auth.md").write_text(SPECS_REQ, encoding="utf-8")
    (root / "specs/design/auth_api.md").write_text(SPECS_DESIGN, encoding="utf-8")


class DocDbTestBase(unittest.TestCase):
    """モック設定と一時ディレクトリを管理する共通基底クラス。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        _create_test_project(self.root)

        self._old_api_key = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "dummy"

        self._old_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)

        self._old_embed_batch = build_index.call_embedding_api
        self._old_embed_single = search_index.call_embedding_api_single
        self._old_rerank = llm_rerank.rerank

        build_index.call_embedding_api = lambda texts, _: [list(FIXED_VEC) for _ in texts]
        search_index.call_embedding_api_single = lambda *_: list(FIXED_VEC)
        llm_rerank.rerank = lambda _q, cand, _k: (
            list(reversed(cand)),
            {
                "fallback_used": False,
                "rerank_error": None,
                "api_calls": 1,
                "token_usage": 100,
                "candidate_count": len(cand),
            },
        )

    def tearDown(self):
        build_index.call_embedding_api = self._old_embed_batch
        search_index.call_embedding_api_single = self._old_embed_single
        llm_rerank.rerank = self._old_rerank

        if self._old_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self._old_api_key

        if self._old_project_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._old_project_dir

        self.tmp.cleanup()


# ---------------------------------------------------------------------------
# L1-3-01: インポートチェーン
# ---------------------------------------------------------------------------


class TestImportChain(unittest.TestCase):
    """L1-3-01: 全モジュールのインポート成功を検証。"""

    def test_all_modules_importable(self):
        modules = [
            build_index, search_index, grep_docs, chunk_extractor,
            embedding_api, hybrid_score, lexical_search, llm_rerank,
            doc_structure, _utils,
        ]
        for mod in modules:
            self.assertTrue(hasattr(mod, "__name__"), f"{mod} has no __name__")


# ---------------------------------------------------------------------------
# L1-3-02 〜 L1-3-05: grep_docs
# ---------------------------------------------------------------------------


class TestGrepDocs(DocDbTestBase):
    """L1-3-02 〜 L1-3-05: grep_docs.py の機能テスト。"""

    def test_grep_rules_keyword_match(self):
        """L1-3-02: rules キーワードヒット。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "MARKER_RULE_CODING_001"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertGreater(len(data["results"]), 0)
        paths = [r["path"] for r in data["results"]]
        self.assertTrue(any("coding_standards.md" in p for p in paths))

    def test_grep_specs_keyword_match(self):
        """L1-3-03: specs キーワードヒット。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "specs", "--keyword", "MARKER_SPEC_REQ_003"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], "ok")
        self.assertGreater(len(data["results"]), 0)

    def test_grep_no_match(self):
        """L1-3-04: ヒットなし → 空配列。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main(["--category", "rules", "--keyword", "ZZZ_NONEXISTENT_999"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["results"], [])

    def test_grep_doc_type_filter(self):
        """L1-3-05: --doc-type で requirement のみ。"""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = grep_docs.main([
                "--category", "specs",
                "--keyword", "MARKER_SPEC",
                "--doc-type", "requirement",
            ])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        for r in data["results"]:
            self.assertIn("requirements/", r["path"])
            self.assertNotIn("design/", r["path"])


# ---------------------------------------------------------------------------
# L1-3-06 〜 L1-3-10: build_index
# ---------------------------------------------------------------------------


class TestBuildIndex(DocDbTestBase):
    """L1-3-06 〜 L1-3-10: build_index.py の機能テスト。"""

    def test_build_check_no_index(self):
        """L1-3-06: index 未構築 → stale。"""
        results = build_index.run_check(self.root, "rules")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "stale")
        self.assertEqual(results[0]["reason"], "index_not_found")

    def test_build_full_rules(self):
        """L1-3-07: rules フルビルド成功。"""
        rc, result = build_index.run_build(self.root, "rules", full=True)
        self.assertEqual(rc, 0)
        index_path = build_index.get_index_path(self.root, "rules")
        self.assertTrue(index_path.exists())
        data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(data["metadata"]["build_state"], "complete")
        self.assertGreater(len(data["entries"]), 0)

    def test_build_full_specs_multi_doctype(self):
        """L1-3-08: specs で requirement + design 分離ビルド。"""
        rc, result = build_index.run_build(self.root, "specs", full=True)
        self.assertEqual(rc, 0)
        req_path = build_index.get_index_path(self.root, "specs", "requirement")
        des_path = build_index.get_index_path(self.root, "specs", "design")
        self.assertTrue(req_path.exists())
        self.assertTrue(des_path.exists())
        req_data = json.loads(req_path.read_text(encoding="utf-8"))
        des_data = json.loads(des_path.read_text(encoding="utf-8"))
        self.assertGreater(len(req_data["entries"]), 0)
        self.assertGreater(len(des_data["entries"]), 0)

    def test_build_no_api_key(self):
        """L1-3-09: API キー未設定 → エラー。"""
        os.environ["OPENAI_API_KEY"] = ""
        rc, result = build_index.run_build(self.root, "rules", full=True)
        self.assertEqual(rc, 1)
        self.assertIn("error", result)
        self.assertIn("OPENAI_API_KEY", result["error"])

    def test_build_check_after_build(self):
        """L1-3-10: ビルド後 → fresh。"""
        build_index.run_build(self.root, "rules", full=True)
        results = build_index.run_check(self.root, "rules")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "fresh")


# ---------------------------------------------------------------------------
# L1-3-11 〜 L1-3-17: search_index
# ---------------------------------------------------------------------------


class TestSearchIndex(DocDbTestBase):
    """L1-3-11 〜 L1-3-17: search_index.py の機能テスト。"""

    def setUp(self):
        super().setUp()
        build_index.run_build(self.root, "rules", full=True)
        build_index.run_build(self.root, "specs", full=True)

    def test_search_lex_mode(self):
        """L1-3-11: lex モード動作。"""
        rc, result = search_index.search(self.root, "rules", "camelCase", "lex", 5)
        self.assertEqual(rc, 0)
        self.assertIn("results", result)
        self.assertIsInstance(result["results"], list)

    def test_search_emb_mode(self):
        """L1-3-12: emb モード動作。"""
        rc, result = search_index.search(self.root, "rules", "naming", "emb", 5)
        self.assertEqual(rc, 0)
        self.assertIn("results", result)

    def test_search_hybrid_mode(self):
        """L1-3-13: hybrid モード動作。"""
        rc, result = search_index.search(self.root, "rules", "coding", "hybrid", 5)
        self.assertEqual(rc, 0)
        self.assertIn("results", result)
        for r in result["results"]:
            self.assertIn("breakdown", r)
            self.assertIn("emb", r["breakdown"])
            self.assertIn("lex", r["breakdown"])

    def test_search_rerank_mode(self):
        """L1-3-14: rerank モード動作。"""
        rc, result = search_index.search(self.root, "rules", "coding", "rerank", 5)
        self.assertEqual(rc, 0)
        self.assertIn("results", result)

    def test_search_result_schema(self):
        """L1-3-15: 結果スキーマ検証。"""
        rc, result = search_index.search(self.root, "rules", "coding", "hybrid", 5)
        self.assertEqual(rc, 0)

        required_top = {
            "results", "fallback_used", "rerank_error",
            "api_calls", "token_usage", "build_state", "incomplete_count",
        }
        self.assertEqual(set(result.keys()), required_top)
        self.assertIsInstance(result["results"], list)
        self.assertIsInstance(result["fallback_used"], bool)
        self.assertIsInstance(result["incomplete_count"], int)

        for row in result["results"]:
            self.assertIn("path", row)
            self.assertIn("heading_path", row)
            self.assertIn("body", row)
            self.assertIn("score", row)
            self.assertIsInstance(row["score"], (int, float))

    def test_search_doc_type_filter(self):
        """L1-3-16: --doc-type で requirement のみ検索。"""
        rc, result = search_index.search(
            self.root, "specs", "MARKER_SPEC", "lex", 10, doc_type="requirement"
        )
        self.assertEqual(rc, 0)
        for r in result["results"]:
            self.assertIn("requirements/", r["path"])

    def test_search_auto_rebuild(self):
        """L1-3-17: ファイル変更 → 自動リビルド。"""
        (self.root / "rules/coding_standards.md").write_text(
            "# Updated\nMARKER_UPDATED_CONTENT_999.\n", encoding="utf-8"
        )
        rc, result = search_index.search(
            self.root, "rules", "MARKER_UPDATED_CONTENT_999", "lex", 5
        )
        self.assertEqual(rc, 0)
        texts = [r["body"] for r in result["results"]]
        self.assertTrue(any("MARKER_UPDATED_CONTENT_999" in t for t in texts))


# ---------------------------------------------------------------------------
# L1-3-18: パス変換確認
# ---------------------------------------------------------------------------


class TestPathTransform(unittest.TestCase):
    """L1-3-18: スクリプト内に CLAUDE_PLUGIN_ROOT 残留なし。"""

    def test_no_plugin_root_in_scripts(self):
        for py_file in SCRIPTS_PATH.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            self.assertNotIn(
                "CLAUDE_PLUGIN_ROOT",
                content,
                f"{py_file.name} contains CLAUDE_PLUGIN_ROOT reference",
            )


if __name__ == "__main__":
    unittest.main()
