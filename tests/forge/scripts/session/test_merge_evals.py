"""merge_evals のテスト (priority ベース単一 reviewer 出力集約)。

reviewer 1 起動原則 (REQ-004 FNC-412 / DES-028 §2.3) のもと、evaluator は
単一 reviewer の findings を 1 ファイル (eval_<種別>.json) に集約して出力する。
findings には priority (P1|P2|P3) と recommendation (fix|skip|create_issue|needs_review)
が付く前提。
"""

import json
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

from session.merge_evals import (  # noqa: E402
    VALID_PRIORITIES,
    collect_eval_files,
    merge_eval_updates,
)
from session.yaml_utils import read_yaml, write_nested_yaml  # noqa: E402

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "merge_evals.py"
)


class _FsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-test"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plan(self, items):
        """テスト用の plan.yaml を書き出す。"""
        write_nested_yaml(
            str(self.session_dir / "plan.yaml"),
            [("items", items)],
        )

    def _write_eval(self, kind, updates):
        """テスト用の eval_<種別>.json を書き出す。"""
        path = self.session_dir / f"eval_{kind}.json"
        path.write_text(
            json.dumps(
                {"kind": kind, "updates": updates},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


def _sample_plan_items():
    """priority 混在の plan.yaml サンプル (global id 1..6)。"""
    return [
        {"id": 1, "priority": "P1", "severity": "major", "title": "A-1",
         "status": "pending"},
        {"id": 2, "priority": "P1", "severity": "minor", "title": "A-2",
         "status": "pending"},
        {"id": 3, "priority": "P2", "severity": "major", "title": "B-1",
         "status": "pending"},
        {"id": 4, "priority": "P2", "severity": "major", "title": "B-2",
         "status": "pending"},
        {"id": 5, "priority": "P3", "severity": "major", "title": "C-1",
         "status": "pending"},
        {"id": 6, "priority": "P3", "severity": "minor", "title": "C-2",
         "status": "pending"},
    ]


# ---------------------------------------------------------------------------
# VALID_PRIORITIES の定義値域
# ---------------------------------------------------------------------------


class TestValidPriorities(unittest.TestCase):
    def test_valid_priorities_are_p1_p2_p3(self):
        """priority の値域は P1/P2/P3 の 3 値のみ (REQ-004 FNC-401)。"""
        self.assertEqual(set(VALID_PRIORITIES), {"P1", "P2", "P3"})


# ---------------------------------------------------------------------------
# collect_eval_files のテスト
# ---------------------------------------------------------------------------


class TestCollectEvalFiles(_FsTestCase):
    def test_collects_eval_json(self):
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix"},
        ])
        self._write_eval("code", [
            {"id": 2, "priority": "P2", "status": "pending",
             "recommendation": "skip"},
        ])
        evals = collect_eval_files(str(self.session_dir))
        self.assertEqual(len(evals), 2)

    def test_ignores_non_eval_files(self):
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending"},
        ])
        # eval_ プレフィックスなしのファイル
        (self.session_dir / "review_design.md").write_text("test")
        evals = collect_eval_files(str(self.session_dir))
        self.assertEqual(len(evals), 1)

    def test_empty_dir(self):
        evals = collect_eval_files(str(self.session_dir))
        self.assertEqual(evals, [])


# ---------------------------------------------------------------------------
# merge_eval_updates のテスト
# ---------------------------------------------------------------------------


class TestMergeEvalUpdates(unittest.TestCase):
    def test_single_reviewer_output_aggregated(self):
        """単一 reviewer 出力 (eval ファイル 1 個) の findings が集約される。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "status": "pending",
                 "recommendation": "fix", "auto_fixable": True},
                {"id": 3, "priority": "P2", "status": "skipped",
                 "recommendation": "skip", "skip_reason": "許容範囲内"},
                {"id": 5, "priority": "P3", "status": "pending",
                 "recommendation": "fix", "auto_fixable": True},
            ]},
        ]
        combined, not_auto, dropped = merge_eval_updates(evals)

        # 全件正常マージ
        self.assertEqual(len(combined), 3)
        self.assertEqual(dropped, [])
        self.assertEqual(not_auto, [])

        # priority 順 (P1 → P2 → P3) でソート
        priorities = [u["priority"] for u in combined]
        self.assertEqual(priorities, ["P1", "P2", "P3"])

        # recommendation が保持されている
        recs = {u["id"]: u["recommendation"] for u in combined}
        self.assertEqual(recs, {1: "fix", 3: "skip", 5: "fix"})

    def test_priority_sort_within_same_priority_by_id(self):
        """同一 priority 内では id 昇順でソートされる。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 5, "priority": "P3", "status": "pending",
                 "recommendation": "fix"},
                {"id": 2, "priority": "P1", "status": "pending",
                 "recommendation": "fix"},
                {"id": 1, "priority": "P1", "status": "pending",
                 "recommendation": "fix"},
                {"id": 3, "priority": "P2", "status": "pending",
                 "recommendation": "fix"},
            ]},
        ]
        combined, _, _ = merge_eval_updates(evals)
        ids = [u["id"] for u in combined]
        # P1: [1, 2] → P2: [3] → P3: [5]
        self.assertEqual(ids, [1, 2, 3, 5])

    def test_invalid_priority_rejected(self):
        """priority が P4 等の不正値の場合は dropped に記録され弾かれる。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P4", "status": "pending",
                 "recommendation": "fix"},
                {"id": 2, "priority": "p1", "status": "pending",
                 "recommendation": "fix"},  # 小文字も不正
                {"id": 3, "priority": "", "status": "pending",
                 "recommendation": "fix"},
                {"id": 4, "status": "pending",
                 "recommendation": "fix"},  # priority 欠落
                {"id": 5, "priority": "P2", "status": "pending",
                 "recommendation": "fix"},  # 正常
            ]},
        ]
        combined, _, dropped = merge_eval_updates(evals)

        # 正常な 1 件 (id=5) だけが combined に入る
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["id"], 5)
        self.assertEqual(combined[0]["priority"], "P2")

        # 4 件 dropped
        self.assertEqual(len(dropped), 4)
        for d in dropped:
            self.assertIn("priority", d["reason"])

    def test_create_issue_recommendation_accepted(self):
        """recommendation: create_issue を含む eval が正しく扱われる (FNC-406)。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "status": "pending",
                 "recommendation": "create_issue",
                 "reason": "ルール未整備"},
            ]},
        ]
        combined, not_auto, dropped = merge_eval_updates(evals)
        self.assertEqual(dropped, [])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["recommendation"], "create_issue")
        # create_issue は auto_fixable に該当しない
        self.assertEqual(not_auto, [])

    def test_not_auto_fixable_detected(self):
        """auto_fixable=False かつ recommendation=fix の id が検出される。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "recommendation": "fix",
                 "auto_fixable": False, "status": "pending"},
                {"id": 2, "priority": "P1", "recommendation": "fix",
                 "auto_fixable": True, "status": "pending"},
                {"id": 3, "priority": "P2", "recommendation": "fix",
                 "auto_fixable": False, "status": "pending"},
            ]},
        ]
        _, not_auto, _ = merge_eval_updates(evals)
        self.assertEqual(not_auto, [1, 3])

    def test_skip_not_in_not_auto_fixable(self):
        """auto_fixable=False でも recommendation=skip なら not_auto_fixable に含まれない。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "recommendation": "skip",
                 "auto_fixable": False, "status": "skipped",
                 "skip_reason": "許容範囲内"},
            ]},
        ]
        _, not_auto, _ = merge_eval_updates(evals)
        self.assertEqual(not_auto, [])

    def test_create_issue_not_in_not_auto_fixable(self):
        """recommendation=create_issue は not_auto_fixable に含まれない (FNC-406)。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "recommendation": "create_issue",
                 "auto_fixable": False, "status": "pending"},
            ]},
        ]
        _, not_auto, _ = merge_eval_updates(evals)
        self.assertEqual(not_auto, [])

    def test_invalid_id_recorded(self):
        """id が未指定・0・負値・非整数の場合は dropped に記録される。"""
        evals = [
            {"kind": "design", "updates": [
                {"priority": "P1", "recommendation": "fix",
                 "status": "pending"},  # id 欠落
                {"id": 0, "priority": "P1", "recommendation": "fix",
                 "status": "pending"},
                {"id": -1, "priority": "P1", "recommendation": "fix",
                 "status": "pending"},
                {"id": "1", "priority": "P1", "recommendation": "fix",
                 "status": "pending"},  # 文字列は不正
                {"id": 1, "priority": "P1", "recommendation": "fix",
                 "status": "pending"},  # 正常
            ]},
        ]
        combined, _, dropped = merge_eval_updates(evals)
        self.assertEqual(len(combined), 1)
        self.assertEqual(len(dropped), 4)
        for d in dropped:
            self.assertIn("id", d["reason"])

    def test_duplicate_id_in_eval_recorded(self):
        """同一 id が複数回現れた場合は 2 回目以降を dropped に記録 (reviewer 1 起動原則)。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "recommendation": "fix",
                 "status": "pending"},
                {"id": 1, "priority": "P2", "recommendation": "skip",
                 "status": "skipped"},
            ]},
        ]
        combined, _, dropped = merge_eval_updates(evals)
        # 最初の 1 件だけ combined に入る
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["recommendation"], "fix")
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["id"], 1)
        self.assertIn("重複", dropped[0]["reason"])

    def test_invalid_recommendation_rejected(self):
        """recommendation が未知の値の場合は dropped に記録される。"""
        evals = [
            {"kind": "design", "updates": [
                {"id": 1, "priority": "P1", "recommendation": "unknown",
                 "status": "pending"},
            ]},
        ]
        combined, _, dropped = merge_eval_updates(evals)
        self.assertEqual(combined, [])
        self.assertEqual(len(dropped), 1)
        self.assertIn("recommendation", dropped[0]["reason"])

    def test_empty_updates_no_dropped(self):
        """eval の updates が空なら combined も dropped も空 (findings 0 件は正常)。"""
        evals = [{"kind": "design", "updates": []}]
        combined, not_auto, dropped = merge_eval_updates(evals)
        self.assertEqual(combined, [])
        self.assertEqual(not_auto, [])
        self.assertEqual(dropped, [])


# ---------------------------------------------------------------------------
# CLI E2E テスト
# ---------------------------------------------------------------------------


class TestMergeEvalsCli(_FsTestCase):
    def _run(self):
        return subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            capture_output=True, text=True,
        )

    def test_basic_e2e(self):
        """CLI 経由で priority 付き eval_*.json → plan.yaml 更新が動作する。"""
        (self.session_dir / "session.yaml").write_text(
            "status: active\nskill: review\n", encoding="utf-8"
        )
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix", "auto_fixable": True,
             "reason": "ルール違反"},
            {"id": 2, "priority": "P1", "status": "skipped",
             "recommendation": "skip", "skip_reason": "対象外"},
            {"id": 3, "priority": "P2", "status": "pending",
             "recommendation": "fix", "auto_fixable": False,
             "reason": "矛盾"},
            {"id": 5, "priority": "P3", "status": "pending",
             "recommendation": "fix", "auto_fixable": True,
             "reason": "複雑化"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)

        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["fix_count"], 3)
        self.assertEqual(output["skip_count"], 1)
        self.assertEqual(output["needs_review_count"], 0)
        self.assertEqual(output["create_issue_count"], 0)
        self.assertEqual(output["should_continue"], True)
        # auto_fixable=False かつ fix なのは id=3 だけ
        self.assertEqual(output["not_auto_fixable"], [3])

    def test_create_issue_excluded_from_should_continue(self):
        """recommendation=create_issue は should_continue=true をトリガーしない (FNC-406)。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "create_issue",
             "reason": "ルール未整備"},
            {"id": 3, "priority": "P2", "status": "skipped",
             "recommendation": "skip", "skip_reason": "許容範囲内"},
            {"id": 5, "priority": "P3", "status": "needs_review",
             "recommendation": "needs_review",
             "reason": "判断保留"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)

        output = json.loads(result.stdout)
        self.assertEqual(output["fix_count"], 0)
        self.assertEqual(output["skip_count"], 1)
        self.assertEqual(output["needs_review_count"], 1)
        self.assertEqual(output["create_issue_count"], 1)
        # fix が 0 件なので should_continue=false
        self.assertEqual(output["should_continue"], False)

    def test_fix_triggers_should_continue(self):
        """recommendation=fix が 1 件でもあれば should_continue=true。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix", "auto_fixable": True},
            {"id": 3, "priority": "P2", "status": "pending",
             "recommendation": "create_issue"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)

        output = json.loads(result.stdout)
        self.assertEqual(output["fix_count"], 1)
        self.assertEqual(output["create_issue_count"], 1)
        self.assertEqual(output["should_continue"], True)

    def test_no_eval_files(self):
        """eval_*.json が存在しない場合はエラーを stderr に出力。"""
        self._write_plan(_sample_plan_items())

        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        err = json.loads(result.stderr)
        self.assertEqual(err["status"], "error")
        self.assertIn("eval_*.json", err["error"])

    def test_error_json_goes_to_stderr_on_missing_plan(self):
        """plan.yaml 不在時も error JSON を stderr に出力する。"""
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix"},
        ])
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")
        err = json.loads(result.stderr)
        self.assertEqual(err["status"], "error")

    def test_all_dropped_is_error_with_diagnostics(self):
        """全 finding が検証失敗 (combined=[]) なら error + dropped 診断情報を返す。"""
        self._write_plan(_sample_plan_items())
        # 全件 priority 不正
        self._write_eval("design", [
            {"id": 1, "priority": "P4", "status": "pending",
             "recommendation": "fix"},
        ])

        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        err = json.loads(result.stderr)
        self.assertEqual(err["status"], "error")
        self.assertIn("マップできませんでした", err["error"])
        self.assertIn("dropped", err)
        self.assertEqual(len(err["dropped"]), 1)

    def test_empty_updates_succeeds_with_zero_counts(self):
        """eval の updates が全て空なら success (fix_count=0)。diagnostics なし。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["fix_count"], 0)
        self.assertEqual(output["skip_count"], 0)
        self.assertEqual(output["needs_review_count"], 0)
        self.assertEqual(output["create_issue_count"], 0)
        self.assertEqual(output["should_continue"], False)
        self.assertEqual(output["updated"], [])
        self.assertNotIn("dropped", output)

    def test_partial_dropped_reported_in_success(self):
        """一部 finding が検証失敗でも combined>0 なら success + dropped 診断を含む。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix", "auto_fixable": True,
             "reason": "有効"},
            {"id": 2, "priority": "BAD", "status": "pending",
             "recommendation": "fix"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["fix_count"], 1)
        self.assertIn("dropped", output)
        self.assertEqual(len(output["dropped"]), 1)
        self.assertEqual(output["dropped"][0]["id"], 2)

    def test_all_skip(self):
        """全件スキップの場合 should_continue=false。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "skipped",
             "recommendation": "skip", "skip_reason": "対象外"},
            {"id": 2, "priority": "P1", "status": "skipped",
             "recommendation": "skip", "skip_reason": "対象外"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["should_continue"], False)
        self.assertEqual(output["fix_count"], 0)
        self.assertEqual(output["skip_count"], 2)

    def test_plan_updated_with_priority(self):
        """plan.yaml の各 item に priority が反映される (id ベース更新)。"""
        self._write_plan(_sample_plan_items())
        self._write_eval("design", [
            {"id": 5, "priority": "P3", "status": "pending",
             "recommendation": "fix", "auto_fixable": True,
             "reason": "テスト理由"},
            {"id": 6, "priority": "P3", "status": "skipped",
             "recommendation": "skip", "skip_reason": "改善提案"},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)

        # plan.yaml を読み直して検証
        plan = read_yaml(str(self.session_dir / "plan.yaml"))
        items = plan["items"]

        item5 = next(i for i in items if i["id"] == 5)
        self.assertEqual(item5["priority"], "P3")
        self.assertEqual(item5["recommendation"], "fix")
        self.assertEqual(item5["status"], "pending")

        item6 = next(i for i in items if i["id"] == 6)
        self.assertEqual(item6["priority"], "P3")
        self.assertEqual(item6["status"], "skipped")

    def test_multiple_eval_files_aggregated(self):
        """複数の eval_*.json も集約される (将来複数種別の同時実行に備える)。"""
        self._write_plan(_sample_plan_items())
        # 各ファイルは別 id を持つ前提 (reviewer 1 起動原則のもとでは
        # 通常 1 ファイルだが、scan 仕様として複数ファイル集約も担保)
        self._write_eval("design", [
            {"id": 1, "priority": "P1", "status": "pending",
             "recommendation": "fix", "auto_fixable": True},
        ])
        self._write_eval("code", [
            {"id": 3, "priority": "P2", "status": "pending",
             "recommendation": "fix", "auto_fixable": True},
        ])

        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["fix_count"], 2)
        self.assertEqual(sorted(output["updated"]), [1, 3])


if __name__ == "__main__":
    unittest.main()
