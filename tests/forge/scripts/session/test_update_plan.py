"""update_plan のテスト。"""

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

from session.update_plan import (
    read_plan, update_item, update_items_batch, write_plan,
)
from session.yaml_utils import write_nested_yaml

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "update_plan.py"
)


class _FsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-abc123"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plan(self, items):
        """テスト用の plan.yaml を書き出す。"""
        sections = [("items", items)]
        write_nested_yaml(
            str(self.session_dir / "plan.yaml"), sections
        )


def _sample_items():
    return [
        {"id": 1, "severity": "critical", "title": "問題1", "status": "pending"},
        {"id": 2, "severity": "major", "title": "問題2", "status": "pending"},
        {"id": 3, "severity": "minor", "title": "問題3", "status": "pending"},
    ]


class TestUpdateItem(unittest.TestCase):
    """update_item のテスト。"""

    def test_update_to_fixed(self):
        items = _sample_items()
        result = update_item(items, 1, {"status": "fixed", "files_modified": ["a.py"]})
        self.assertTrue(result)
        self.assertEqual(items[0]["status"], "fixed")
        self.assertEqual(items[0]["files_modified"], ["a.py"])
        # fixed_at が自動生成される
        self.assertIn("fixed_at", items[0])

    def test_update_to_skipped(self):
        items = _sample_items()
        result = update_item(items, 2, {"status": "skipped", "skip_reason": "FP"})
        self.assertTrue(result)
        self.assertEqual(items[1]["status"], "skipped")
        self.assertEqual(items[1]["skip_reason"], "FP")

    def test_update_to_in_progress(self):
        items = _sample_items()
        result = update_item(items, 1, {"status": "in_progress"})
        self.assertTrue(result)
        self.assertEqual(items[0]["status"], "in_progress")

    def test_update_to_needs_review(self):
        items = _sample_items()
        result = update_item(items, 3, {"status": "needs_review"})
        self.assertTrue(result)
        self.assertEqual(items[2]["status"], "needs_review")

    def test_explicit_fixed_at(self):
        items = _sample_items()
        ts = "2026-03-09T18:35:00Z"
        update_item(items, 1, {"status": "fixed", "fixed_at": ts})
        self.assertEqual(items[0]["fixed_at"], ts)

    def test_not_found(self):
        items = _sample_items()
        result = update_item(items, 99, {"status": "fixed"})
        self.assertFalse(result)

    def test_update_recommendation(self):
        items = _sample_items()
        result = update_item(items, 1, {
            "status": "pending",
            "recommendation": "fix",
            "auto_fixable": True,
            "reason": "明確な問題",
        })
        self.assertTrue(result)
        self.assertEqual(items[0]["recommendation"], "fix")
        self.assertTrue(items[0]["auto_fixable"])
        self.assertEqual(items[0]["reason"], "明確な問題")

    def test_update_recommendation_skip(self):
        items = _sample_items()
        result = update_item(items, 2, {
            "status": "skipped",
            "recommendation": "skip",
            "reason": "FP: 意図的な設計",
        })
        self.assertTrue(result)
        self.assertEqual(items[1]["recommendation"], "skip")
        self.assertEqual(items[1]["reason"], "FP: 意図的な設計")
        # auto_fixable は設定されない
        self.assertNotIn("auto_fixable", items[1])

    def test_update_recommendation_needs_review(self):
        items = _sample_items()
        result = update_item(items, 3, {
            "status": "needs_review",
            "recommendation": "needs_review",
            "auto_fixable": False,
            "reason": "確認が必要",
        })
        self.assertTrue(result)
        self.assertEqual(items[2]["recommendation"], "needs_review")
        self.assertFalse(items[2]["auto_fixable"])
        self.assertEqual(items[2]["reason"], "確認が必要")

    def test_update_recommendation_create_issue(self):
        """DES-028 §3.3 / REQ-004 FNC-406: create_issue が受理される。

        ルール未整備の指摘を Issue 化対象として記録するフロー。
        status は skipped (fixer 対象外として扱う) を想定。
        """
        items = _sample_items()
        result = update_item(items, 2, {
            "status": "skipped",
            "recommendation": "create_issue",
            "auto_fixable": False,
            "reason": "P1 SSOT に該当規定なし。再発性あり。明文化可能粒度。",
        })
        self.assertTrue(result)
        self.assertEqual(items[1]["recommendation"], "create_issue")
        self.assertFalse(items[1]["auto_fixable"])
        self.assertIn("該当規定なし", items[1]["reason"])

    def test_invalid_status(self):
        items = _sample_items()
        with self.assertRaises(ValueError):
            update_item(items, 1, {"status": "invalid"})

    def test_invalid_recommendation(self):
        items = _sample_items()
        with self.assertRaises(ValueError):
            update_item(items, 1, {"status": "pending", "recommendation": "invalid"})


class TestUpdateItemsBatch(unittest.TestCase):
    """update_items_batch のテスト。"""

    def test_batch(self):
        items = _sample_items()
        updates = [
            {"id": 1, "status": "pending"},
            {"id": 2, "status": "skipped", "skip_reason": "FP"},
            {"id": 3, "status": "needs_review"},
        ]
        updated = update_items_batch(items, updates)
        self.assertEqual(updated, [1, 2, 3])
        self.assertEqual(items[1]["status"], "skipped")

    def test_missing_id(self):
        items = _sample_items()
        with self.assertRaises(ValueError):
            update_items_batch(items, [{"status": "fixed"}])

    def test_partial_match(self):
        items = _sample_items()
        updated = update_items_batch(items, [
            {"id": 1, "status": "fixed"},
            {"id": 99, "status": "skipped"},
        ])
        self.assertEqual(updated, [1])

    def test_duplicate_id_raises(self):
        """updates 配列に同一 ID が複数回含まれる場合は ValueError。

        evaluator の local ID を直接流す典型的な誤用パターン
        （2026-04-15 ID 衝突インシデントの再発防止）。
        """
        items = _sample_items()
        with self.assertRaises(ValueError) as ctx:
            update_items_batch(items, [
                {"id": 1, "status": "pending", "recommendation": "fix"},
                {"id": 2, "status": "pending", "recommendation": "fix"},
                {"id": 1, "status": "skipped", "recommendation": "skip"},  # 重複
            ])
        # エラーメッセージに merge_evals.py への誘導が含まれていることを確認
        self.assertIn("merge_evals.py", str(ctx.exception))

    def test_duplicate_id_does_not_partially_update(self):
        """重複検出時は部分更新が残らない（事前チェック方式の保証）。"""
        items = _sample_items()
        original_status_1 = items[0]["status"]
        with self.assertRaises(ValueError):
            update_items_batch(items, [
                {"id": 1, "status": "fixed"},
                {"id": 1, "status": "skipped"},
            ])
        # id=1 は変更されていない
        self.assertEqual(items[0]["status"], original_status_1)


class TestReadWritePlan(_FsTestCase):
    """read_plan / write_plan のラウンドトリップ。"""

    def test_roundtrip(self):
        items = _sample_items()
        self._write_plan(items)

        plan_data = read_plan(str(self.session_dir))
        self.assertEqual(len(plan_data["items"]), 3)

        # 更新して書き戻し
        update_item(plan_data["items"], 1, {
            "status": "fixed",
            "fixed_at": "2026-03-09T18:35:00Z",
            "files_modified": ["a.py", "b.py"],
        })
        write_plan(str(self.session_dir), plan_data)

        # 再読み込みで確認
        reloaded = read_plan(str(self.session_dir))
        item1 = reloaded["items"][0]
        self.assertEqual(item1["status"], "fixed")
        self.assertEqual(item1["fixed_at"], "2026-03-09T18:35:00Z")
        # files_modified は文字列リストとして読み込まれるはず
        self.assertIn("a.py", item1.get("files_modified", []))

    def test_roundtrip_with_recommendation(self):
        items = _sample_items()
        self._write_plan(items)

        plan_data = read_plan(str(self.session_dir))
        update_item(plan_data["items"], 1, {
            "status": "pending",
            "recommendation": "fix",
            "auto_fixable": True,
            "reason": "明確な不整合",
        })
        update_item(plan_data["items"], 2, {
            "status": "skipped",
            "recommendation": "skip",
            "reason": "FP",
        })
        write_plan(str(self.session_dir), plan_data)

        reloaded = read_plan(str(self.session_dir))
        item1 = reloaded["items"][0]
        self.assertEqual(item1["recommendation"], "fix")
        self.assertTrue(item1["auto_fixable"])
        self.assertEqual(item1["reason"], "明確な不整合")
        item2 = reloaded["items"][1]
        self.assertEqual(item2["recommendation"], "skip")
        self.assertEqual(item2["reason"], "FP")

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            read_plan(str(self.session_dir))


class TestCLI(_FsTestCase):
    """CLI 統合テスト。"""

    def test_single_update(self):
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "fixed",
             "--files-modified", "a.py", "b.py"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["updated"], [1])

    def test_batch_update(self):
        self._write_plan(_sample_items())
        batch = {
            "updates": [
                {"id": 1, "status": "pending"},
                {"id": 2, "status": "skipped", "skip_reason": "FP"},
            ]
        }
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir), "--batch"],
            input=json.dumps(batch),
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["updated"], [1, 2])

    def test_batch_update_raw_array(self):
        """JSON 配列を直接渡してもバッチ更新できる。"""
        self._write_plan(_sample_items())
        batch = [
            {"id": 1, "status": "pending"},
            {"id": 2, "status": "skipped", "skip_reason": "FP"},
        ]
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir), "--batch"],
            input=json.dumps(batch),
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["updated"], [1, 2])

    def test_missing_plan(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "fixed"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_args(self):
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_not_found_id(self):
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "99", "--status", "fixed"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_single_update_with_recommendation(self):
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "pending",
             "--recommendation", "fix",
             "--auto-fixable", "true",
             "--reason", "明確な問題"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")

        # ファイルを再読み込みして検証
        plan_data = read_plan(str(self.session_dir))
        item1 = plan_data["items"][0]
        self.assertEqual(item1["recommendation"], "fix")
        self.assertTrue(item1["auto_fixable"])
        self.assertEqual(item1["reason"], "明確な問題")

    def test_cli_recommendation_args(self):
        """CLI で --recommendation / --auto-fixable / --reason が plan.yaml に反映される。"""
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "pending",
             "--recommendation", "fix",
             "--auto-fixable", "true",
             "--reason", "テスト理由"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["updated"], [1])

        # plan.yaml を再読み込みして値を検証
        plan_data = read_plan(str(self.session_dir))
        item1 = plan_data["items"][0]
        self.assertEqual(item1["recommendation"], "fix")
        self.assertTrue(item1["auto_fixable"])
        self.assertEqual(item1["reason"], "テスト理由")

    def test_cli_recommendation_create_issue(self):
        """CLI で --recommendation create_issue が受理され plan.yaml に反映される。

        DES-028 §3.3 / REQ-004 FNC-406 で recommendation 値域に追加された
        新値の CLI 受理確認。
        """
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "skipped",
             "--recommendation", "create_issue",
             "--reason", "ルール未整備"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")

        plan_data = read_plan(str(self.session_dir))
        item1 = plan_data["items"][0]
        self.assertEqual(item1["recommendation"], "create_issue")
        self.assertEqual(item1["reason"], "ルール未整備")

    def test_cli_invalid_recommendation(self):
        """CLI で --recommendation に不正な値を渡すと exit 1 になる。"""
        self._write_plan(_sample_items())
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--id", "1", "--status", "pending",
             "--recommendation", "invalid_value"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        error = json.loads(proc.stderr)
        self.assertEqual(error["status"], "error")
        self.assertIn("recommendation", error["error"])

    def test_batch_duplicate_id_cli_fails(self):
        """CLI で stdin JSON に重複 ID が含まれる場合は exit 1 + stderr JSON。

        2026-04-15 ID 衝突インシデントの再発防止。
        """
        self._write_plan(_sample_items())
        batch = {"updates": [
            {"id": 1, "status": "fixed"},
            {"id": 1, "status": "skipped"},
        ]}
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir), "--batch"],
            input=json.dumps(batch),
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1)
        err = json.loads(proc.stderr)
        self.assertEqual(err["status"], "error")
        self.assertIn("merge_evals.py", err["error"])

    def test_batch_update_with_recommendation(self):
        self._write_plan(_sample_items())
        batch = {
            "updates": [
                {
                    "id": 1, "status": "pending",
                    "recommendation": "fix", "auto_fixable": True,
                    "reason": "修正すべき",
                },
                {
                    "id": 2, "status": "skipped",
                    "recommendation": "skip",
                    "reason": "FP",
                },
            ]
        }
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir), "--batch"],
            input=json.dumps(batch),
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["updated"], [1, 2])

        plan_data = read_plan(str(self.session_dir))
        self.assertEqual(plan_data["items"][0]["recommendation"], "fix")
        self.assertTrue(plan_data["items"][0]["auto_fixable"])
        self.assertEqual(plan_data["items"][1]["recommendation"], "skip")


if __name__ == "__main__":
    unittest.main()
