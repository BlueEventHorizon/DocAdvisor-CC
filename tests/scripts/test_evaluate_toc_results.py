#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evaluate_toc_results.py のテスト"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールのインポート
# meta/ は .gitignore 対象（CLAUDE.md 参照: 検索品質測定はローカルのみ）。
# 配置されていない環境ではテストをスキップする。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "meta" / "test_docs"))

try:
    from evaluate_toc_results import (
        evaluate_entry,
        load_results_json,
        match_results_to_queries,
        print_report,
        save_results,
    )
    _HAS_EVALUATE_MODULE = True
except ImportError:
    _HAS_EVALUATE_MODULE = False

_SKIP_REASON = "meta/test_docs/evaluate_toc_results.py is local-only (.gitignore'd)"


@unittest.skipUnless(_HAS_EVALUATE_MODULE, _SKIP_REASON)
class TestEvaluateEntry(unittest.TestCase):
    """evaluate_entry() のテスト"""

    def test_pass_all_expected_found(self):
        """expected_paths が全件ヒットで pass"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md", "path/b.md"],
            "unexpected_paths": [],
            "type": "direct",
            "note": "テスト",
        }
        result = evaluate_entry(entry, ["path/a.md", "path/b.md", "path/c.md"])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["expected_count"], 2)
        self.assertEqual(result["result_count"], 3)

    def test_fail_missing_expected(self):
        """expected_paths に見落としがある場合 fail"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md", "path/b.md"],
            "unexpected_paths": [],
            "type": "direct",
            "note": "",
        }
        result = evaluate_entry(entry, ["path/a.md"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("path/b.md", result["missing"])
        self.assertIn("False Negative", result["reason"])

    def test_fail_false_positive(self):
        """unexpected_paths にヒットした場合 fail"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md"],
            "unexpected_paths": ["path/bad.md"],
            "type": "direct",
            "note": "",
        }
        result = evaluate_entry(entry, ["path/a.md", "path/bad.md"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("path/bad.md", result["false_positives"])
        self.assertIn("False Positive", result["reason"])

    def test_fail_both_missing_and_false_positive(self):
        """見落としと誤検出が同時にある場合"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md", "path/b.md"],
            "unexpected_paths": ["path/bad.md"],
            "type": "crosscut",
            "note": "",
        }
        result = evaluate_entry(entry, ["path/a.md", "path/bad.md"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("False Negative", result["reason"])
        self.assertIn("False Positive", result["reason"])

    def test_negative_pass_empty_results(self):
        """negative テスト: 結果 0 件で pass"""
        entry = {
            "query": "無関係なクエリ",
            "expected_paths": [],
            "unexpected_paths": [],
            "type": "negative",
            "note": "結果なしが正解",
        }
        result = evaluate_entry(entry, [])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["result_count"], 0)

    def test_negative_fail_has_results(self):
        """negative テスト: 結果があれば fail"""
        entry = {
            "query": "無関係なクエリ",
            "expected_paths": [],
            "unexpected_paths": [],
            "type": "negative",
            "note": "",
        }
        result = evaluate_entry(entry, ["path/unexpected.md"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("negative テストだが結果が返された", result["reason"])
        self.assertEqual(result["false_positives"], ["path/unexpected.md"])

    def test_pass_with_extra_results(self):
        """expected_paths 以外の追加結果があっても unexpected でなければ pass"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md"],
            "unexpected_paths": [],
            "type": "task",
            "note": "",
        }
        result = evaluate_entry(entry, ["path/a.md", "path/extra1.md", "path/extra2.md"])
        self.assertEqual(result["status"], "pass")

    def test_empty_result_paths_with_expected(self):
        """結果 0 件だが expected がある場合 fail"""
        entry = {
            "query": "テストクエリ",
            "expected_paths": ["path/a.md"],
            "unexpected_paths": [],
            "type": "direct",
            "note": "",
        }
        result = evaluate_entry(entry, [])
        self.assertEqual(result["status"], "fail")
        self.assertIn("path/a.md", result["missing"])


@unittest.skipUnless(_HAS_EVALUATE_MODULE, _SKIP_REASON)
class TestMatchResultsToQueries(unittest.TestCase):
    """match_results_to_queries() のテスト"""

    def _make_queries(self):
        return {
            "rules": [
                {
                    "query": "クエリ1",
                    "expected_paths": ["path/a.md"],
                    "unexpected_paths": [],
                    "type": "direct",
                    "note": "",
                },
                {
                    "query": "クエリ2",
                    "expected_paths": ["path/b.md"],
                    "unexpected_paths": [],
                    "type": "task",
                    "note": "",
                },
            ],
            "specs": [
                {
                    "query": "スペッククエリ1",
                    "expected_paths": [],
                    "unexpected_paths": [],
                    "type": "negative",
                    "note": "",
                },
            ],
        }

    def test_all_matched(self):
        """全クエリに結果がある場合"""
        queries = self._make_queries()
        results_data = {
            "rules": [
                {"query": "クエリ1", "result_paths": ["path/a.md"]},
                {"query": "クエリ2", "result_paths": ["path/b.md"]},
            ],
            "specs": [
                {"query": "スペッククエリ1", "result_paths": []},
            ],
        }
        all_results = match_results_to_queries(queries, results_data)
        self.assertEqual(len(all_results["rules"]), 2)
        self.assertEqual(len(all_results["specs"]), 1)
        self.assertEqual(all_results["rules"][0]["status"], "pass")
        self.assertEqual(all_results["rules"][1]["status"], "pass")
        self.assertEqual(all_results["specs"][0]["status"], "pass")

    def test_missing_result_entry(self):
        """results_data にクエリの結果がない場合 error"""
        queries = self._make_queries()
        results_data = {
            "rules": [
                {"query": "クエリ1", "result_paths": ["path/a.md"]},
                # クエリ2 の結果がない
            ],
            "specs": [],
        }
        all_results = match_results_to_queries(queries, results_data)
        self.assertEqual(all_results["rules"][0]["status"], "pass")
        self.assertEqual(all_results["rules"][1]["status"], "error")
        self.assertIn("結果なし", all_results["rules"][1]["error"])

    def test_missing_category(self):
        """results_data にカテゴリ自体がない場合"""
        queries = self._make_queries()
        results_data = {
            "rules": [
                {"query": "クエリ1", "result_paths": ["path/a.md"]},
                {"query": "クエリ2", "result_paths": ["path/b.md"]},
            ],
            # specs カテゴリ自体がない
        }
        all_results = match_results_to_queries(queries, results_data)
        self.assertEqual(all_results["specs"][0]["status"], "error")

    def test_empty_results_data(self):
        """results_data が完全に空の場合"""
        queries = self._make_queries()
        all_results = match_results_to_queries(queries, {})
        for category, results in all_results.items():
            for r in results:
                self.assertEqual(r["status"], "error")


@unittest.skipUnless(_HAS_EVALUATE_MODULE, _SKIP_REASON)
class TestLoadResultsJson(unittest.TestCase):
    """load_results_json() のテスト"""

    def test_load_valid_json(self):
        """正常な JSON ファイルの読み込み"""
        data = {
            "rules": [{"query": "テスト", "result_paths": ["a.md"]}],
            "specs": [],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
            dir=str(PROJECT_ROOT / ".claude" / ".temp"),
        ) as f:
            json.dump(data, f, ensure_ascii=False)
            tmp_path = f.name

        try:
            loaded = load_results_json(tmp_path)
            self.assertEqual(loaded, data)
        finally:
            os.unlink(tmp_path)


@unittest.skipUnless(_HAS_EVALUATE_MODULE, _SKIP_REASON)
class TestPrintReport(unittest.TestCase):
    """print_report() のテスト"""

    def test_summary_counts(self):
        """サマリーのカウントが正しい"""
        all_results = {
            "rules": [
                {"query": "q1", "type": "direct", "status": "pass", "expected_count": 1, "result_count": 1, "note": "", "result_paths": ["a.md"]},
                {"query": "q2", "type": "direct", "status": "fail", "expected_count": 1, "result_count": 0, "note": "", "reason": "False Negative: 1 件見落とし", "missing": ["b.md"]},
                {"query": "q3", "type": "task", "status": "error", "error": "結果なし", "note": ""},
            ],
        }
        summary = print_report(all_results, "test_set")
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["errors"], 1)

    def test_all_pass(self):
        """全件 pass のサマリー"""
        all_results = {
            "rules": [
                {"query": "q1", "type": "direct", "status": "pass", "expected_count": 1, "result_count": 1, "note": "", "result_paths": []},
            ],
            "specs": [
                {"query": "q2", "type": "negative", "status": "pass", "result_count": 0, "note": ""},
            ],
        }
        summary = print_report(all_results, "test_set")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 0)

    def test_empty_results(self):
        """空の結果"""
        summary = print_report({}, "test_set")
        self.assertEqual(summary["total"], 0)


@unittest.skipUnless(_HAS_EVALUATE_MODULE, _SKIP_REASON)
class TestSaveResults(unittest.TestCase):
    """save_results() のテスト"""

    def test_save_creates_file(self):
        """結果ファイルが作成される"""
        all_results = {
            "rules": [
                {"query": "q1", "type": "direct", "status": "pass"},
            ],
        }
        summary = {"total": 1, "passed": 1, "failed": 0, "errors": 0}

        with tempfile.TemporaryDirectory(
            dir=str(PROJECT_ROOT / ".claude" / ".temp"),
        ) as tmp_dir:
            results_dir = Path(tmp_dir) / "results"
            result_file = save_results(all_results, summary, "test_set", results_dir)
            self.assertTrue(result_file.exists())

            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["doc_set"], "test_set")
            self.assertEqual(data["mode"], "toc")
            self.assertEqual(data["summary"]["passed"], 1)


if __name__ == "__main__":
    unittest.main()
