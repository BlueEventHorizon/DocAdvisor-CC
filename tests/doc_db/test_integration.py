"""doc-db 統合テスト: Index 構築→検索 E2E、doc_type 分離、doc-advisor 不変 (AC-01)。"""

import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "plugins/doc-db/scripts"))

import build_index
import search_index

# DES-026 / タスク指示: CI でもキー不要。1536 次元固定ベクトル（モック）
FIXED_EMBEDDING_DIM = 1536
FIXED_EMBEDDING_VEC = [0.1] * FIXED_EMBEDDING_DIM


def _write_doc_structure_rules_only(root: pathlib.Path) -> None:
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


def _write_doc_structure_with_plan(root: pathlib.Path) -> None:
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
                "    - docs/specs/**/plan/",
                "  doc_types_map:",
                "    docs/specs/**/requirements/: requirement",
                "    docs/specs/**/design/: design",
                "    docs/specs/**/plan/: plan",
                "  patterns:",
                "    target_glob: \"**/*.md\"",
                "    exclude: []",
            ]
        ),
        encoding="utf-8",
    )


def _collect_dir_checksums(base: pathlib.Path) -> dict[str, str]:
    """相対パス -> SHA256 hex（ファイルのみ）。"""
    out: dict[str, str] = {}
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = p.relative_to(base).as_posix()
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            out[rel] = h
    return out


@contextmanager
def _mock_embedding_apis():
    """build / search の embedding 呼び出しを固定ベクトルに差し替える。"""

    def _batch(_texts, _key):
        return [list(FIXED_EMBEDDING_VEC) for _ in _texts]

    def _single(_text, _key):
        return list(FIXED_EMBEDDING_VEC)

    old_build = build_index.call_embedding_api
    old_search = search_index.call_embedding_api_single
    build_index.call_embedding_api = _batch
    search_index.call_embedding_api_single = _single
    try:
        yield
    finally:
        build_index.call_embedding_api = old_build
        search_index.call_embedding_api_single = old_search


def _assert_search_result_schema(tc: unittest.TestCase, result: dict, mode: str) -> None:
    """DES-026 §5.3 のトップレベル観測性フィールドと result 行の形を検証。"""
    required_top = {
        "results",
        "fallback_used",
        "rerank_error",
        "api_calls",
        "token_usage",
        "build_state",
        "incomplete_count",
    }
    tc.assertEqual(set(result.keys()), required_top)

    tc.assertIsInstance(result["results"], list)
    tc.assertIsInstance(result["fallback_used"], bool)
    tc.assertIn(
        result["rerank_error"],
        (None, "context_window_exceeded", "timeout", "5xx"),
    )
    tc.assertIn("embedding", result["api_calls"])
    tc.assertIn("rerank", result["api_calls"])
    tc.assertIn("embedding", result["token_usage"])
    tc.assertIn("rerank", result["token_usage"])
    tc.assertIn(result["build_state"], ("complete", "incomplete", "inconsistent"))
    tc.assertIsInstance(result["incomplete_count"], int)

    if mode == "lex":
        tc.assertEqual(result["api_calls"]["embedding"], 0)
    else:
        tc.assertEqual(result["api_calls"]["embedding"], 1)

    for row in result["results"]:
        tc.assertIn("path", row)
        tc.assertIn("heading_path", row)
        tc.assertIn("body", row)
        tc.assertIn("score", row)
        tc.assertIsInstance(row["score"], (int, float))
        bd = row["breakdown"]
        tc.assertIsInstance(bd, dict)
        tc.assertIn("emb", bd)
        tc.assertIn("lex", bd)
        tc.assertIsInstance(bd["emb"], (int, float))
        tc.assertIsInstance(bd["lex"], (int, float))


class TestDocDbIntegration(unittest.TestCase):
    """TASK-014: 統合シナリオ 1〜3。"""

    def setUp(self):
        self._old_api_key = os.environ.get("OPENAI_API_DOCDB_KEY")
        os.environ["OPENAI_API_DOCDB_KEY"] = "dummy"

    def tearDown(self):
        if self._old_api_key is None:
            os.environ.pop("OPENAI_API_DOCDB_KEY", None)
        else:
            os.environ["OPENAI_API_DOCDB_KEY"] = self._old_api_key

    def test_scenario1_e2e_build_then_search_schema(self):
        """シナリオ 1: rules Index 構築 → lex / hybrid / emb でスキーマ検証。"""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "docs/rules").mkdir(parents=True)
            (root / "docs/rules/rule_alpha.md").write_text(
                "# RULE-INT-001\nunique marker phrase alpha_int for search.\n",
                encoding="utf-8",
            )
            _write_doc_structure_rules_only(root)

            with _mock_embedding_apis():
                rc, _ = build_index.run_build(root, "rules", full=True)
                self.assertEqual(rc, 0)
                index_path = build_index.get_index_path(root, "rules")
                self.assertTrue(index_path.exists())
                data = json.loads(index_path.read_text(encoding="utf-8"))
                self.assertEqual(data["metadata"]["build_state"], "complete")
                self.assertEqual(data["metadata"]["dimensions"], FIXED_EMBEDDING_DIM)

                for mode in ("lex", "hybrid", "emb"):
                    rc2, result = search_index.search(
                        root,
                        "rules",
                        "alpha_int",
                        mode,
                        5,
                    )
                    self.assertEqual(rc2, 0, msg=f"mode={mode}")
                    _assert_search_result_schema(self, result, mode)
                    self.assertIsNone(result["rerank_error"])
                    self.assertFalse(result["fallback_used"])
                    self.assertGreater(len(result["results"]), 0)
                    paths = {r["path"] for r in result["results"]}
                    self.assertIn("docs/rules/rule_alpha.md", paths)

    def test_scenario2_doc_type_split_and_merge(self):
        """シナリオ 2: requirement / design / plan の Index 分離とマージ検索。"""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "docs/specs/f1/requirements").mkdir(parents=True)
            (root / "docs/specs/f1/design").mkdir(parents=True)
            (root / "docs/specs/f1/plan").mkdir(parents=True)
            (root / "docs/specs/f1/requirements/r_int.md").write_text(
                "# REQ-INT-ONLY\nmarker token req_only_gamma_int.\n",
                encoding="utf-8",
            )
            (root / "docs/specs/f1/design/d_int.md").write_text(
                "# DES-INT-ONLY\nmarker token des_only_delta_int.\n",
                encoding="utf-8",
            )
            (root / "docs/specs/f1/plan/p_int.md").write_text(
                "# PLAN-INT-ONLY\nmarker token plan_only_epsilon_int.\n",
                encoding="utf-8",
            )
            _write_doc_structure_with_plan(root)

            with _mock_embedding_apis():
                rc, _ = build_index.run_build(root, "specs", full=True)
                self.assertEqual(rc, 0)
                req_p = build_index.get_index_path(root, "specs", "requirement")
                des_p = build_index.get_index_path(root, "specs", "design")
                plan_p = build_index.get_index_path(root, "specs", "plan")
                self.assertTrue(req_p.exists())
                self.assertTrue(des_p.exists())
                self.assertTrue(plan_p.exists())

                rc_m, merged = search_index.search(
                    root,
                    "specs",
                    "req_only_gamma_int",
                    "lex",
                    10,
                    doc_type="requirement,design",
                )
                self.assertEqual(rc_m, 0)
                paths_m = {r["path"] for r in merged["results"]}
                self.assertIn("docs/specs/f1/requirements/r_int.md", paths_m)
                self.assertNotIn("docs/specs/f1/plan/p_int.md", paths_m)

                rc_m2, merged2 = search_index.search(
                    root,
                    "specs",
                    "des_only_delta_int",
                    "lex",
                    10,
                    doc_type="requirement,design",
                )
                self.assertEqual(rc_m2, 0)
                paths_m2 = {r["path"] for r in merged2["results"]}
                self.assertIn("docs/specs/f1/design/d_int.md", paths_m2)
                self.assertNotIn("docs/specs/f1/plan/p_int.md", paths_m2)

                rc_p, only_plan = search_index.search(
                    root,
                    "specs",
                    "plan_only_epsilon_int",
                    "lex",
                    10,
                    doc_type="plan",
                )
                self.assertEqual(rc_p, 0)
                paths_p = {r["path"] for r in only_plan["results"]}
                self.assertIn("docs/specs/f1/plan/p_int.md", paths_p)
                self.assertNotIn("docs/specs/f1/requirements/r_int.md", paths_p)
                self.assertNotIn("docs/specs/f1/design/d_int.md", paths_p)

    def test_scenario3_doc_advisor_unchanged_after_doc_db(self):
        """シナリオ 3: doc-db 利用後も plugins/doc-advisor と .claude/doc-advisor が不変。"""
        advisor_plugin = ROOT / "plugins" / "doc-advisor"
        advisor_claude = ROOT / ".claude" / "doc-advisor"

        before_plugin = _collect_dir_checksums(advisor_plugin)
        before_claude = (
            _collect_dir_checksums(advisor_claude) if advisor_claude.is_dir() else None
        )

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "docs/rules").mkdir(parents=True)
            (root / "docs/rules/ac01.md").write_text(
                "# AC01-GUARD\nparallel op marker.\n",
                encoding="utf-8",
            )
            _write_doc_structure_rules_only(root)

            with _mock_embedding_apis():
                rc, _ = build_index.run_build(root, "rules", full=True)
                self.assertEqual(rc, 0)
                rc2, res = search_index.search(root, "rules", "AC01", "hybrid", 5)
                self.assertEqual(rc2, 0)
                self.assertGreater(len(res["results"]), 0)

        after_plugin = _collect_dir_checksums(advisor_plugin)
        self.assertEqual(
            before_plugin,
            after_plugin,
            "plugins/doc-advisor must be unchanged after doc-db build/search",
        )
        if before_claude is not None:
            after_claude = _collect_dir_checksums(advisor_claude)
            self.assertEqual(
                before_claude,
                after_claude,
                ".claude/doc-advisor must be unchanged after doc-db build/search",
            )


if __name__ == "__main__":
    unittest.main()
