"""summarize_plan のテスト。

/forge:review Phase 5 の終了確認で使う未処理指摘集計の動作を検証する。
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

from session.summarize_plan import summarize_pending
from session.yaml_utils import write_nested_yaml

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "summarize_plan.py"
)


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテスト基底。

    feedback_tempfile_dir の規約に従い、tempfile.mkdtemp(dir=...) で
    親ディレクトリを明示する。
    """

    def setUp(self):
        # プロジェクト直下の tmp/ ではなくシステム tmp を明示（/tmp ブロック時の
        # CWD フォールバックを防ぐ）
        self.tmpdir = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))
        self.session_dir = self.tmpdir / "review-abc123"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plan(self, items):
        sections = [("items", items)]
        write_nested_yaml(str(self.session_dir / "plan.yaml"), sections)


class TestSummarizePending(_FsTestCase):
    def test_counts_unprocessed_by_severity(self):
        """未処理を severity 別に集計する。"""
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "needs_review"},
            {"id": 3, "severity": "minor", "title": "C", "status": "pending"},
            {"id": 4, "severity": "critical", "title": "D", "status": "fixed"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["by_severity"], {"critical": 1, "major": 1, "minor": 1})
        self.assertEqual(result["unprocessed_total"], 3)

    def test_counts_unprocessed_by_status(self):
        """未処理を status 別に集計する。"""
        self._write_plan([
            {"id": 1, "severity": "major", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "pending"},
            {"id": 3, "severity": "major", "title": "C", "status": "needs_review"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        # create_issue は 0 件でもキーが存在する (DES-028 §3.6 / REQ-004 FNC-406)
        self.assertEqual(
            result["by_status"],
            {"pending": 2, "needs_review": 1, "create_issue": 0},
        )

    def test_fixed_and_skipped_not_counted(self):
        """fixed と skipped は未処理にカウントしない。"""
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "fixed"},
            {"id": 2, "severity": "major", "title": "B", "status": "skipped"},
            {"id": 3, "severity": "minor", "title": "C", "status": "pending"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["unprocessed_total"], 1)
        self.assertEqual(result["fixed"], 1)
        self.assertEqual(result["skipped"], 1)

    def test_returns_unprocessed_ids(self):
        """未処理項目の id を返す（一括 skip で使う）。"""
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "fixed"},
            {"id": 3, "severity": "minor", "title": "C", "status": "needs_review"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(sorted(result["unprocessed_ids"]), [1, 3])

    def test_truncates_titles_to_10(self):
        """titles は先頭10件で打ち切る。"""
        items = [
            {"id": i, "severity": "major", "title": f"T{i}", "status": "pending"}
            for i in range(1, 13)  # 12件
        ]
        self._write_plan(items)
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(len(result["titles"]), 10)
        self.assertEqual(result["titles"][0], "T1")
        self.assertEqual(result["titles"][9], "T10")
        # unprocessed_total は全件
        self.assertEqual(result["unprocessed_total"], 12)

    def test_empty_plan_returns_zero(self):
        """空 plan.yaml は unprocessed_total=0 を返す。"""
        self._write_plan([])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["unprocessed_total"], 0)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["fixed"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["by_severity"], {"critical": 0, "major": 0, "minor": 0})
        self.assertEqual(
            result["by_status"],
            {"pending": 0, "needs_review": 0, "create_issue": 0},
        )
        self.assertEqual(result["create_issue"], 0)
        self.assertEqual(result["unprocessed_ids"], [])
        self.assertEqual(result["titles"], [])

    def test_missing_plan_yaml_raises(self):
        """plan.yaml が存在しない場合は FileNotFoundError を送出する。"""
        # plan.yaml を書かないまま集計
        with self.assertRaises(FileNotFoundError):
            summarize_pending(self.session_dir / "plan.yaml")

    def test_unknown_severity_does_not_crash(self):
        """未知の severity があっても by_severity は既定の3キーのみを維持する。"""
        self._write_plan([
            {"id": 1, "severity": "blocker", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "pending"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["unprocessed_total"], 2)
        self.assertEqual(result["by_severity"], {"critical": 0, "major": 1, "minor": 0})

    def test_create_issue_counted_in_by_status(self):
        """create_issue 状態の指摘が by_status.create_issue にカウントされる。

        DES-028 §3.6 / REQ-004 FNC-406: create_issue は外部 Issue 化で決着扱い。
        """
        self._write_plan([
            {"id": 1, "severity": "major", "title": "A", "status": "create_issue"},
            {"id": 2, "severity": "minor", "title": "B", "status": "create_issue"},
            {"id": 3, "severity": "critical", "title": "C", "status": "pending"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["by_status"]["create_issue"], 2)
        self.assertEqual(result["create_issue"], 2)

    def test_create_issue_excluded_from_unprocessed(self):
        """create_issue は unprocessed_total / unprocessed_ids に含めない (decided 扱い)。

        DES-028 §3.6 終了判定: 全指摘が fixed / skipped / create_issue で決着すれば
        unprocessed_total = 0 となり終了可能。
        """
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "fixed"},
            {"id": 2, "severity": "major", "title": "B", "status": "skipped"},
            {"id": 3, "severity": "minor", "title": "C", "status": "create_issue"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        # 全件 decided 扱いのため unprocessed は 0
        self.assertEqual(result["unprocessed_total"], 0)
        self.assertEqual(result["unprocessed_ids"], [])
        # 個別カウントは保持
        self.assertEqual(result["fixed"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["create_issue"], 1)
        self.assertEqual(result["by_status"]["create_issue"], 1)

    def test_create_issue_zero_when_absent(self):
        """create_issue が 0 件の場合の挙動 (回帰防止)。

        既存ケース (pending / needs_review のみ) で create_issue キーは存在し値は 0、
        unprocessed_total は従来どおり pending + needs_review の合計のままであることを確認。
        """
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "needs_review"},
            {"id": 3, "severity": "minor", "title": "C", "status": "fixed"},
        ])
        result = summarize_pending(self.session_dir / "plan.yaml")

        self.assertEqual(result["unprocessed_total"], 2)
        self.assertEqual(result["create_issue"], 0)
        self.assertEqual(result["by_status"]["create_issue"], 0)
        self.assertEqual(result["by_status"]["pending"], 1)
        self.assertEqual(result["by_status"]["needs_review"], 1)


class TestCLI(_FsTestCase):
    def test_cli_json_output(self):
        """CLI 実行で JSON を stdout に出力する。"""
        self._write_plan([
            {"id": 1, "severity": "critical", "title": "A", "status": "pending"},
            {"id": 2, "severity": "major", "title": "B", "status": "fixed"},
        ])

        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)

        self.assertEqual(data["unprocessed_total"], 1)
        self.assertEqual(data["fixed"], 1)
        self.assertEqual(data["total"], 2)

    def test_cli_missing_plan_exits_1(self):
        """plan.yaml が存在しない場合は exit code=1 + stderr JSON を返す。"""
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        err = json.loads(result.stderr)
        self.assertEqual(err["status"], "error")


if __name__ == "__main__":
    unittest.main()
