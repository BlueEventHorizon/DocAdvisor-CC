"""write_interpretation のテスト。

CLI 引数は `--kind` のみを受け付け、値域は
{code, design, requirement, plan, uxui, generic} に固定される
(DES-028 §2.4 / REQ-004 FNC-410)。
旧 `--perspective` 互換は維持しない。
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

from session.write_interpretation import KIND_CHOICES, write_interpretation

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "write_interpretation.py"
)


class _FsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-test"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_review(self, kind, content):
        path = self.session_dir / f"review_{kind}.md"
        path.write_text(content, encoding="utf-8")
        return path


class TestWriteInterpretation(_FsTestCase):
    def test_first_call_creates_backup(self):
        """初回呼び出しで .raw.md が作成される。"""
        self._write_review("code", "# reviewer 原文\n指摘1\n")

        result = write_interpretation(
            str(self.session_dir), "code", "# evaluator 評価\n整形後\n"
        )

        self.assertTrue(result["backup_created"])
        target = self.session_dir / "review_code.md"
        backup = self.session_dir / "review_code.raw.md"
        self.assertTrue(backup.exists())
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "# evaluator 評価\n整形後\n")
        self.assertEqual(backup.read_text(encoding="utf-8"),
                         "# reviewer 原文\n指摘1\n")

    def test_second_call_preserves_backup(self):
        """2回目呼び出しで .raw.md が保護される(初回バックアップが維持)。"""
        self._write_review("design", "# reviewer 原文\n")

        write_interpretation(
            str(self.session_dir), "design", "# 初回整形\n"
        )
        result2 = write_interpretation(
            str(self.session_dir), "design", "# 2回目整形\n"
        )

        self.assertFalse(result2["backup_created"])
        target = self.session_dir / "review_design.md"
        backup = self.session_dir / "review_design.raw.md"
        self.assertEqual(target.read_text(encoding="utf-8"), "# 2回目整形\n")
        # 初回のバックアップ内容が維持されている
        self.assertEqual(backup.read_text(encoding="utf-8"), "# reviewer 原文\n")

    def test_idempotent_same_content(self):
        """同一内容での連続呼び出しは結果不変。"""
        self._write_review("plan", "# reviewer 原文\n")

        write_interpretation(str(self.session_dir), "plan", "# 整形\n")
        write_interpretation(str(self.session_dir), "plan", "# 整形\n")
        write_interpretation(str(self.session_dir), "plan", "# 整形\n")

        target = self.session_dir / "review_plan.md"
        backup = self.session_dir / "review_plan.raw.md"
        self.assertEqual(target.read_text(encoding="utf-8"), "# 整形\n")
        self.assertEqual(backup.read_text(encoding="utf-8"), "# reviewer 原文\n")

    def test_all_kinds_produce_review_kind_md(self):
        """値域の全種別で出力ファイル名が review_<kind>.md になる。"""
        for kind in KIND_CHOICES:
            with self.subTest(kind=kind):
                # 各種別ごとに独立したセッションディレクトリを用意
                sess = self.tmpdir / f"sess-{kind}"
                sess.mkdir()
                (sess / f"review_{kind}.md").write_text(
                    "# reviewer\n", encoding="utf-8"
                )

                result = write_interpretation(
                    str(sess), kind, f"# integrated {kind}\n"
                )

                target = sess / f"review_{kind}.md"
                backup = sess / f"review_{kind}.raw.md"
                self.assertEqual(result["path"], str(target))
                self.assertEqual(result["backup_path"], str(backup))
                self.assertTrue(result["backup_created"])
                self.assertEqual(
                    target.read_text(encoding="utf-8"),
                    f"# integrated {kind}\n",
                )

    def test_missing_target_raises(self):
        """review_{kind}.md が存在しない場合はエラー。

        値域内の種別でも、対象ファイルが未作成ならエラーとなる。
        """
        with self.assertRaises(FileNotFoundError):
            write_interpretation(
                str(self.session_dir), "generic", "# 整形\n"
            )

    def test_empty_content_raises(self):
        """空内容はエラー。"""
        self._write_review("code", "# reviewer 原文\n")
        with self.assertRaises(ValueError):
            write_interpretation(str(self.session_dir), "code", "")

    def test_no_tmp_files_left_after_write(self):
        """アトミック書き込みの tmp ファイルが session_dir に残らない。"""
        self._write_review("uxui", "# reviewer 原文\n")
        write_interpretation(str(self.session_dir), "uxui", "# 整形\n")
        write_interpretation(str(self.session_dir), "uxui", "# 再整形\n")

        # .tmp で終わるファイルがない(tempfile.mkstemp の suffix 回収確認)
        tmp_files = list(self.session_dir.glob("*.tmp"))
        self.assertEqual(tmp_files, [])
        # .review_uxui.md.* のような隠しファイルも残らない
        hidden_files = list(self.session_dir.glob(".*.tmp"))
        self.assertEqual(hidden_files, [])

    def test_atomic_rename_does_not_corrupt_on_partial(self):
        """書き込みに失敗しても target は直前の内容のまま維持される。

        atomic_write_text の tmp エラーパスを検証: 書き込み中に例外が
        発生した場合、target は書き換わらず tmp は掃除される。
        """
        from session.yaml_utils import atomic_write_text

        target = self.session_dir / "test_atomic.md"
        target.write_text("original", encoding="utf-8")

        # disk full 相当をシミュレート: content 引数に非 str を渡して TypeError
        with self.assertRaises((TypeError, AttributeError)):
            atomic_write_text(target, 12345)  # 非文字列 → 書き込み時に失敗

        # target は元のまま
        self.assertEqual(target.read_text(encoding="utf-8"), "original")
        # tmp ファイルが残らない
        tmp_files = list(self.session_dir.glob(".test_atomic.md.*"))
        self.assertEqual(tmp_files, [])


class TestWriteInterpretationCli(_FsTestCase):
    def test_cli_first_call(self):
        (self.session_dir / "review_code.md").write_text(
            "# reviewer 原文\n", encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "code"],
            input="# 整形\n",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertTrue(output["backup_created"])
        self.assertTrue((self.session_dir / "review_code.raw.md").exists())
        self.assertEqual(
            (self.session_dir / "review_code.md").read_text(encoding="utf-8"),
            "# 整形\n",
        )

    def test_cli_second_call_preserves_backup(self):
        (self.session_dir / "review_design.md").write_text(
            "# reviewer 原文\n", encoding="utf-8"
        )

        subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "design"],
            input="# 初回\n",
            capture_output=True, text=True,
        )
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "design"],
            input="# 2回目\n",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        output = json.loads(result.stdout)
        self.assertFalse(output["backup_created"])
        # .raw.md は初回バックアップのまま
        self.assertEqual(
            (self.session_dir / "review_design.raw.md").read_text(encoding="utf-8"),
            "# reviewer 原文\n",
        )
        self.assertEqual(
            (self.session_dir / "review_design.md").read_text(encoding="utf-8"),
            "# 2回目\n",
        )

    def test_cli_missing_target(self):
        """review_{kind}.md がない場合は非ゼロ終了。"""
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "generic"],
            input="# 整形\n",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_cli_empty_stdin(self):
        """空 stdin は非ゼロ終了。"""
        (self.session_dir / "review_code.md").write_text(
            "# reviewer 原文\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "code"],
            input="",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)

    def test_cli_all_kinds_emit_review_kind_md(self):
        """CLI 経由でも値域全種別が review_<kind>.md を出力する。"""
        for kind in KIND_CHOICES:
            with self.subTest(kind=kind):
                sess = self.tmpdir / f"cli-{kind}"
                sess.mkdir()
                (sess / f"review_{kind}.md").write_text(
                    "# reviewer\n", encoding="utf-8"
                )

                result = subprocess.run(
                    [sys.executable, SCRIPT, str(sess),
                     "--kind", kind],
                    input=f"# fmt {kind}\n",
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

                output = json.loads(result.stdout)
                self.assertEqual(output["status"], "ok")
                self.assertEqual(
                    output["path"], str(sess / f"review_{kind}.md")
                )
                self.assertEqual(
                    output["backup_path"], str(sess / f"review_{kind}.raw.md")
                )

    def test_cli_invalid_kind_value(self):
        """値域外の --kind は argparse のエラー (SystemExit, returncode 2) で終了。"""
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--kind", "invalid_value"],
            input="# 整形\n",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        # argparse の choices エラーは stderr に出る
        self.assertIn("invalid choice", result.stderr.lower())

    def test_cli_missing_kind_argument(self):
        """--kind が無い場合は argparse のエラー (SystemExit, returncode 2) で終了。"""
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input="# 整形\n",
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        # argparse の required エラーが stderr に出る
        self.assertIn("--kind", result.stderr)

    def test_cli_legacy_perspective_rejected(self):
        """旧 --perspective は受理しない (argparse エラー)。"""
        (self.session_dir / "review_code.md").write_text(
            "# reviewer 原文\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir),
             "--perspective", "code"],
            input="# 整形\n",
            capture_output=True, text=True,
        )
        # 未知の引数 → argparse は returncode 2 で終了
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
