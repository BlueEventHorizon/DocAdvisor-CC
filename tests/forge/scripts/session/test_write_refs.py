"""write_refs のテスト (DES-028 §2.3 review_packet 新スキーマ)。"""

import copy
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

from session.write_refs import (
    build_refs_text,
    validate_review_packet,
    write_refs,
)
from session.yaml_utils import read_yaml

SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "plugins" / "forge" / "scripts" / "session" / "write_refs.py"
)


def _base_data():
    """テスト用の最小限の正常データを返す (review_packet 新スキーマ)。"""
    return {
        "target_files": ["a.py"],
        "reference_docs": [{"path": "docs/r.md"}],
        "review_packet": {
            "criteria_path": "review/docs/review_criteria_code.md",
            "ssot_refs": [
                {
                    "path": "docs/rules/implementation_guidelines.md",
                    "priority": "P1",
                    "doc_type": "rules",
                },
                {
                    "path": "plugins/forge/docs/spec_priorities_spec.md",
                    "priority": "P2",
                    "doc_type": "principles",
                },
            ],
            "check_order": ["P1", "P2", "P3"],
            "severity_source": "principles",
            "output_path": "review_code.md",
        },
    }


class _FsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.session_dir = self.tmpdir / "review-abc123"
        self.session_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# validate_review_packet: 正常系 + 既存 (target_files / reference_docs / related_code)
# ---------------------------------------------------------------------------


class TestValidateReviewPacketBasics(unittest.TestCase):
    """validate_review_packet の基本 (既存スキーマ部分維持) テスト。"""

    def test_valid_minimal(self):
        validate_review_packet(_base_data())

    def test_valid_with_related_code(self):
        data = _base_data()
        data["related_code"] = [{"path": "src/x.py", "reason": "関連"}]
        validate_review_packet(data)

    def test_valid_with_related_code_lines(self):
        data = _base_data()
        data["related_code"] = [
            {"path": "src/x.py", "reason": "関連", "lines": "10-50"}
        ]
        validate_review_packet(data)

    def test_empty_reference_docs_allowed(self):
        data = _base_data()
        data["reference_docs"] = []
        validate_review_packet(data)

    # -- target_files --

    def test_empty_target_files(self):
        data = _base_data()
        data["target_files"] = []
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_missing_target_files(self):
        data = _base_data()
        del data["target_files"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    # -- reference_docs --

    def test_reference_docs_missing_path(self):
        data = _base_data()
        data["reference_docs"] = [{"reason": "no path"}]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    # -- related_code --

    def test_related_code_missing_reason(self):
        data = _base_data()
        data["related_code"] = [{"path": "x.py"}]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_related_code_missing_path(self):
        data = _base_data()
        data["related_code"] = [{"reason": "関連"}]
        with self.assertRaises(ValueError):
            validate_review_packet(data)


# ---------------------------------------------------------------------------
# validate_review_packet: review_packet 必須キー
# ---------------------------------------------------------------------------


class TestReviewPacketRequiredKeys(unittest.TestCase):
    """review_packet の必須キー検証テスト。"""

    def test_missing_review_packet(self):
        data = _base_data()
        del data["review_packet"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_review_packet_not_dict(self):
        data = _base_data()
        data["review_packet"] = "not a dict"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_missing_criteria_path(self):
        data = _base_data()
        del data["review_packet"]["criteria_path"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_empty_criteria_path(self):
        data = _base_data()
        data["review_packet"]["criteria_path"] = ""
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_missing_severity_source(self):
        data = _base_data()
        del data["review_packet"]["severity_source"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_empty_severity_source(self):
        data = _base_data()
        data["review_packet"]["severity_source"] = ""
        with self.assertRaises(ValueError):
            validate_review_packet(data)


# ---------------------------------------------------------------------------
# validate_review_packet: ssot_refs
# ---------------------------------------------------------------------------


class TestReviewPacketSsotRefs(unittest.TestCase):
    """ssot_refs の検証テスト。"""

    def test_missing_ssot_refs(self):
        data = _base_data()
        del data["review_packet"]["ssot_refs"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_empty_ssot_refs(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"] = []
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_not_list(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"] = {"path": "x.md"}
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_item_not_dict(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"] = ["not a dict"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_missing_path(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0].pop("path")
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_empty_path(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["path"] = ""
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    # -- priority --

    def test_ssot_refs_priority_p1(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["priority"] = "P1"
        validate_review_packet(data)

    def test_ssot_refs_priority_p2(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["priority"] = "P2"
        validate_review_packet(data)

    def test_ssot_refs_priority_p3(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["priority"] = "P3"
        validate_review_packet(data)

    def test_ssot_refs_priority_invalid(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["priority"] = "P4"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_priority_lowercase(self):
        """小文字 p1 は不可。"""
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["priority"] = "p1"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_priority_missing(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0].pop("priority")
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    # -- doc_type --

    def test_ssot_refs_doc_type_rules(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["doc_type"] = "rules"
        validate_review_packet(data)

    def test_ssot_refs_doc_type_principles(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["doc_type"] = "principles"
        validate_review_packet(data)

    def test_ssot_refs_doc_type_format(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["doc_type"] = "format"
        validate_review_packet(data)

    def test_ssot_refs_doc_type_invalid(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0]["doc_type"] = "spec"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_ssot_refs_doc_type_missing(self):
        data = _base_data()
        data["review_packet"]["ssot_refs"][0].pop("doc_type")
        with self.assertRaises(ValueError):
            validate_review_packet(data)


# ---------------------------------------------------------------------------
# validate_review_packet: check_order
# ---------------------------------------------------------------------------


class TestReviewPacketCheckOrder(unittest.TestCase):
    """check_order の検証テスト。"""

    def test_missing_check_order(self):
        data = _base_data()
        del data["review_packet"]["check_order"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_empty_check_order(self):
        data = _base_data()
        data["review_packet"]["check_order"] = []
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_check_order_not_list(self):
        data = _base_data()
        data["review_packet"]["check_order"] = "P1,P2,P3"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_check_order_non_string_element(self):
        data = _base_data()
        data["review_packet"]["check_order"] = ["P1", 2, "P3"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_check_order_empty_string_element(self):
        data = _base_data()
        data["review_packet"]["check_order"] = ["P1", "", "P3"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)


# ---------------------------------------------------------------------------
# validate_review_packet: output_path
# ---------------------------------------------------------------------------


class TestReviewPacketOutputPath(unittest.TestCase):
    """output_path の検証テスト (^review_<種別>.md$ 形式)。"""

    def test_missing_output_path(self):
        data = _base_data()
        del data["review_packet"]["output_path"]
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_empty_output_path(self):
        data = _base_data()
        data["review_packet"]["output_path"] = ""
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_valid_output_path_code(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "review_code.md"
        validate_review_packet(data)

    def test_valid_output_path_design(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "review_design.md"
        validate_review_packet(data)

    def test_invalid_output_path_no_prefix(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_invalid_output_path_wrong_ext(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "review_code.txt"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_invalid_output_path_uppercase(self):
        """大文字を含む種別は不可。"""
        data = _base_data()
        data["review_packet"]["output_path"] = "review_Code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_invalid_output_path_with_subdir(self):
        """サブディレクトリ含みは不可 (^review_<種別>.md$ 厳密)。"""
        data = _base_data()
        data["review_packet"]["output_path"] = "sub/review_code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_output_path_traversal(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "../review_code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_output_path_traversal_middle(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "sub/../review_code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)

    def test_output_path_absolute(self):
        data = _base_data()
        data["review_packet"]["output_path"] = "/tmp/review_code.md"
        with self.assertRaises(ValueError):
            validate_review_packet(data)


# ---------------------------------------------------------------------------
# validate_review_packet: 旧 perspectives[] スキーマの拒否 (回帰防止)
# ---------------------------------------------------------------------------


class TestRejectLegacyPerspectives(unittest.TestCase):
    """旧 perspectives[] キーが含まれる入力を明示的に拒否する。"""

    def test_reject_legacy_perspectives_present(self):
        data = _base_data()
        data["perspectives"] = [
            {
                "name": "correctness",
                "criteria_path": "review/docs/review_criteria_code.md",
                "output_path": "review_correctness.md",
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_review_packet(data)
        # メッセージに「perspectives」「撤廃」「review_packet」が含まれること
        msg = str(ctx.exception)
        self.assertIn("perspectives", msg)
        self.assertIn("review_packet", msg)

    def test_reject_legacy_perspectives_even_when_review_packet_absent(self):
        """review_packet 欠落 + perspectives 同時指定でも perspectives 拒否を優先。"""
        data = _base_data()
        del data["review_packet"]
        data["perspectives"] = [
            {
                "name": "correctness",
                "criteria_path": "x.md",
                "output_path": "review_x.md",
            }
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_review_packet(data)
        self.assertIn("perspectives", str(ctx.exception))


# ---------------------------------------------------------------------------
# build_refs_text / write_refs / read_yaml ラウンドトリップ
# ---------------------------------------------------------------------------


class TestBuildRefsText(unittest.TestCase):
    """build_refs_text のテスト (順序とネスト構造)。"""

    def test_section_order(self):
        data = _base_data()
        data["related_code"] = [{"path": "src/x.py", "reason": "関連"}]
        text = build_refs_text(data)
        idx_target = text.find("target_files:")
        idx_ref = text.find("reference_docs:")
        idx_packet = text.find("review_packet:")
        idx_related = text.find("related_code:")
        self.assertGreaterEqual(idx_target, 0)
        self.assertGreater(idx_ref, idx_target)
        self.assertGreater(idx_packet, idx_ref)
        self.assertGreater(idx_related, idx_packet)

    def test_no_perspectives_in_output(self):
        text = build_refs_text(_base_data())
        self.assertNotIn("perspectives:", text)

    def test_review_packet_nested(self):
        """review_packet 配下にネスト構造で出力される。"""
        text = build_refs_text(_base_data())
        self.assertIn("review_packet:", text)
        # criteria_path / ssot_refs / check_order / severity_source / output_path
        for key in (
            "criteria_path:",
            "ssot_refs:",
            "check_order:",
            "severity_source:",
            "output_path:",
        ):
            self.assertIn(key, text)

    def test_skip_reference_docs_when_empty(self):
        data = _base_data()
        data["reference_docs"] = []
        text = build_refs_text(data)
        self.assertNotIn("reference_docs:", text)


class TestWriteRefs(_FsTestCase):
    """write_refs (ファイル書き出し + read_yaml ラウンドトリップ)。"""

    def test_minimal(self):
        data = _base_data()
        data["reference_docs"] = []
        path = write_refs(str(self.session_dir), data)
        self.assertTrue(Path(path).exists())
        result = read_yaml(path)
        self.assertEqual(result["target_files"], ["a.py"])
        packet = result["review_packet"]
        self.assertIsInstance(packet, dict)
        self.assertEqual(
            packet["criteria_path"], "review/docs/review_criteria_code.md"
        )
        self.assertEqual(packet["severity_source"], "principles")
        self.assertEqual(packet["output_path"], "review_code.md")
        self.assertEqual(packet["check_order"], ["P1", "P2", "P3"])
        self.assertEqual(len(packet["ssot_refs"]), 2)
        self.assertEqual(packet["ssot_refs"][0]["priority"], "P1")
        self.assertEqual(packet["ssot_refs"][0]["doc_type"], "rules")

    def test_full(self):
        data = copy.deepcopy(_base_data())
        data["reference_docs"] = [
            {"path": "docs/rules.md"},
            {"path": "docs/spec.md"},
        ]
        data["review_packet"]["ssot_refs"].append(
            {
                "path": "plugins/forge/docs/spec_priorities_spec.md",
                "priority": "P3",
                "doc_type": "principles",
            }
        )
        data["related_code"] = [
            {"path": "src/util.py", "reason": "ヘルパー", "lines": "1-30"},
        ]
        path = write_refs(str(self.session_dir), data)
        result = read_yaml(path)
        self.assertEqual(len(result["reference_docs"]), 2)
        self.assertEqual(len(result["review_packet"]["ssot_refs"]), 3)
        self.assertEqual(
            result["review_packet"]["ssot_refs"][2]["priority"], "P3"
        )
        self.assertEqual(result["related_code"][0]["reason"], "ヘルパー")
        self.assertEqual(result["related_code"][0]["lines"], "1-30")


# ---------------------------------------------------------------------------
# CLI 統合テスト
# ---------------------------------------------------------------------------


class TestCLI(_FsTestCase):
    """CLI 統合テスト。"""

    def test_basic(self):
        data = _base_data()
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input=json.dumps(data),
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(Path(result["path"]).exists())

    def test_invalid_json(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input="not json",
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_validation_error(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input=json.dumps({"target_files": []}),
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_reject_legacy_perspectives(self):
        """旧 perspectives[] スキーマが渡されたら CLI もエラー終了する。"""
        data = _base_data()
        data["perspectives"] = [
            {
                "name": "correctness",
                "criteria_path": "x.md",
                "output_path": "review_x.md",
            }
        ]
        proc = subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input=json.dumps(data),
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)


# ---------------------------------------------------------------------------
# TASK-028 回帰防止: 旧 perspectives キー拒否を subprocess 経由で確認
# ---------------------------------------------------------------------------


class TestRejectLegacyPerspectivesRegression(_FsTestCase):
    """TASK-028 回帰防止テスト。

    DES-028 §2.3 / REQ-004 FNC-412 により、refs.yaml の旧スキーマ
    (perspectives[]) は完全撤廃されている (TASK-009 で write_refs.py に
    拒否ロジック実装済み)。本テストはその拒否ロジックが回帰しないよう
    subprocess 経由で実際の振る舞い (終了コード / 標準エラー /
    refs.yaml 非生成) を検証する。
    """

    # 旧スキーマの典型 perspectives エントリ (DES-021 当時の構造)
    LEGACY_PERSPECTIVE = {
        "name": "logic",
        "criteria_path": "review/docs/review_criteria_code.md",
        "section": "Perspective: logic",
        "output_path": "review_logic.md",
    }

    def _run_cli(self, payload):
        return subprocess.run(
            [sys.executable, SCRIPT, str(self.session_dir)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )

    def test_legacy_perspectives_exits_nonzero(self):
        """旧 perspectives キーが含まれる入力では CLI が非 0 終了する。"""
        payload = _base_data()
        payload["perspectives"] = [self.LEGACY_PERSPECTIVE]

        proc = self._run_cli(payload)

        self.assertNotEqual(
            proc.returncode, 0,
            f"perspectives キー入力で 0 終了は不可: stdout={proc.stdout!r}",
        )

    def test_legacy_perspectives_error_message_mentions_key_and_deprecation(self):
        """エラーメッセージに「perspectives」キー名と廃止文言・新スキーマ案内を含む。"""
        payload = _base_data()
        payload["perspectives"] = [self.LEGACY_PERSPECTIVE]

        proc = self._run_cli(payload)

        # write_refs.py は stderr に JSON 形式でエラーを出す
        self.assertTrue(proc.stderr, "stderr が空: エラーメッセージ未出力")
        try:
            err = json.loads(proc.stderr)
        except json.JSONDecodeError:
            self.fail(
                f"stderr が JSON 形式でない (write_refs.py 仕様違反): {proc.stderr!r}"
            )
        self.assertEqual(err.get("status"), "error")
        msg = err.get("error", "")
        # キー名「perspectives」を含む
        self.assertIn(
            "perspectives", msg,
            f"エラーメッセージにキー名 'perspectives' が無い: {msg!r}",
        )
        # 廃止 / 撤廃 / 使用不可 のいずれかを含む (TASK-009 実装文言「撤廃」に対応)
        self.assertTrue(
            any(token in msg for token in ("撤廃", "廃止", "使用不可", "deprecated")),
            f"エラーメッセージに廃止文言が無い: {msg!r}",
        )
        # 新スキーマ (review_packet) への移行案内を含む
        self.assertIn(
            "review_packet", msg,
            f"エラーメッセージに新スキーマ案内 'review_packet' が無い: {msg!r}",
        )

    def test_legacy_perspectives_does_not_create_refs_yaml(self):
        """拒否時に refs.yaml が生成されないこと。"""
        payload = _base_data()
        payload["perspectives"] = [self.LEGACY_PERSPECTIVE]
        refs_path = self.session_dir / "refs.yaml"
        self.assertFalse(refs_path.exists(), "前提: refs.yaml は事前に存在しない")

        proc = self._run_cli(payload)

        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(
            refs_path.exists(),
            "旧スキーマ拒否時に refs.yaml が生成されてはならない",
        )

    def test_new_schema_succeeds_and_creates_refs_yaml(self):
        """対照ケース: perspectives 不在の新スキーマ単体では正常生成。"""
        payload = _base_data()
        # perspectives キーが存在しないことを明示
        self.assertNotIn("perspectives", payload)
        refs_path = self.session_dir / "refs.yaml"

        proc = self._run_cli(payload)

        self.assertEqual(proc.returncode, 0, f"stderr={proc.stderr!r}")
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(refs_path.exists(), "新スキーマでは refs.yaml が生成される")
        # 生成内容にも perspectives が含まれないことを確認 (二重防衛)
        self.assertNotIn("perspectives:", refs_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
