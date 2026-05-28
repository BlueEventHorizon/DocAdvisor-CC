"""yaml_utils のテスト。"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[4] / "plugins" / "forge" / "scripts"),
)

from session.yaml_utils import (
    yaml_scalar,
    write_flat_yaml,
    write_nested_yaml,
    build_nested_yaml_text,
    read_yaml,
    parse_yaml,
    now_iso,
)


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテストの基底クラス。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name):
        return self.tmpdir / name


# ---------------------------------------------------------------------------
# yaml_scalar
# ---------------------------------------------------------------------------

class TestYamlScalar(unittest.TestCase):
    """yaml_scalar のテスト。"""

    def test_bool_true(self):
        self.assertEqual(yaml_scalar(True), "true")

    def test_bool_false(self):
        self.assertEqual(yaml_scalar(False), "false")

    def test_int(self):
        self.assertEqual(yaml_scalar(42), "42")

    def test_int_negative(self):
        self.assertEqual(yaml_scalar(-1), "-1")

    def test_plain_string(self):
        self.assertEqual(yaml_scalar("hello"), "hello")

    def test_empty_string(self):
        self.assertEqual(yaml_scalar(""), '""')

    def test_colon_quoted(self):
        result = yaml_scalar("key: value")
        self.assertTrue(result.startswith('"'))
        self.assertIn("key", result)

    def test_special_chars_quoted(self):
        for c in (":", "#", "{", "[", "*", "?", "|"):
            result = yaml_scalar(f"text{c}more")
            self.assertTrue(result.startswith('"'), f"char {c} not quoted")

    def test_space_quoted(self):
        result = yaml_scalar("hello world")
        self.assertTrue(result.startswith('"'))

    def test_backslash_escaped(self):
        """バックスラッシュ含みかつクォートが必要なケース。"""
        result = yaml_scalar("path\\to: file")
        self.assertIn("\\\\", result)

    def test_double_quote_escaped(self):
        """ダブルクォート含みかつクォートが必要なケース。"""
        result = yaml_scalar('key: "value"')
        self.assertIn('\\"', result)


# ---------------------------------------------------------------------------
# write_flat_yaml / read_yaml ラウンドトリップ
# ---------------------------------------------------------------------------

class TestFlatYaml(_FsTestCase):
    """フラット YAML の書き込み・読み込みラウンドトリップ。"""

    def test_basic_roundtrip(self):
        data = {"skill": "review", "status": "in_progress", "auto_count": 3}
        path = self._path("test.yaml")
        write_flat_yaml(path, data, field_order=["skill", "status"])
        result = read_yaml(path)
        self.assertEqual(result["skill"], "review")
        self.assertEqual(result["status"], "in_progress")
        self.assertEqual(result["auto_count"], 3)

    def test_field_order(self):
        data = {"z_field": "z", "a_field": "a", "m_field": "m"}
        path = self._path("order.yaml")
        write_flat_yaml(path, data, field_order=["m_field", "a_field"])
        content = Path(path).read_text()
        lines = [l for l in content.strip().split("\n") if l]
        self.assertTrue(lines[0].startswith("m_field:"))
        self.assertTrue(lines[1].startswith("a_field:"))
        self.assertTrue(lines[2].startswith("z_field:"))

    def test_bool_roundtrip(self):
        data = {"enabled": True, "debug": False}
        path = self._path("bool.yaml")
        write_flat_yaml(path, data)
        result = read_yaml(path)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["debug"])

    def test_quoted_string_roundtrip(self):
        data = {"title": "hello: world"}
        path = self._path("quoted.yaml")
        write_flat_yaml(path, data)
        result = read_yaml(path)
        self.assertEqual(result["title"], "hello: world")

    def test_double_quote_roundtrip(self):
        """ダブルクォートを含む文字列のラウンドトリップで \\\" が復元される。"""
        data = {"title": 'key: "value"'}
        path = self._path("dq.yaml")
        write_flat_yaml(path, data)
        result = read_yaml(path)
        self.assertEqual(result["title"], 'key: "value"')

    def test_backslash_roundtrip(self):
        """バックスラッシュを含む文字列のラウンドトリップで \\\\ が復元される。"""
        data = {"path": "C:\\Users\\test: file"}
        path = self._path("bs.yaml")
        write_flat_yaml(path, data)
        result = read_yaml(path)
        self.assertEqual(result["path"], "C:\\Users\\test: file")

    def test_mixed_escape_roundtrip(self):
        """バックスラッシュとダブルクォートが混在するラウンドトリップ。"""
        data = {"msg": 'say: "hello" with\\path'}
        path = self._path("mixed.yaml")
        write_flat_yaml(path, data)
        result = read_yaml(path)
        self.assertEqual(result["msg"], 'say: "hello" with\\path')

    def test_single_quote_roundtrip(self):
        """シングルクォート内の `''` が `'` に復元される(手書き YAML 互換)。"""
        from session.yaml_utils import parse_yaml
        # yaml_scalar はダブルクォートで出力するが、手書き YAML を読む場合に備える
        content = "greeting: 'it''s me'\n"
        result = parse_yaml(content)
        self.assertEqual(result["greeting"], "it's me")


# ---------------------------------------------------------------------------
# write_nested_yaml
# ---------------------------------------------------------------------------

class TestNestedYaml(_FsTestCase):
    """ネスト YAML の書き込みテスト。"""

    def test_scalar_only(self):
        sections = [("key1", "value1"), ("key2", 42), ("key3", True)]
        path = self._path("scalar.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(result["key1"], "value1")
        self.assertEqual(result["key2"], 42)
        self.assertTrue(result["key3"])

    def test_string_list(self):
        sections = [("items", ["a.py", "b.py", "c.py"])]
        path = self._path("strlist.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(result["items"], ["a.py", "b.py", "c.py"])

    def test_object_list(self):
        sections = [
            ("items", [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"},
            ])
        ]
        path = self._path("objlist.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["id"], 1)
        self.assertEqual(result["items"][0]["name"], "first")
        self.assertEqual(result["items"][1]["id"], 2)

    def test_mixed_sections(self):
        """スカラー + 文字列リスト + オブジェクトリストの混在。"""
        sections = [
            ("review_criteria_path", "docs/review.md"),
            ("target_files", ["a.py", "b.py"]),
            ("reference_docs", [
                {"path": "docs/rules.md"},
                {"path": "docs/spec.md"},
            ]),
        ]
        path = self._path("mixed.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(result["review_criteria_path"], "docs/review.md")
        self.assertEqual(result["target_files"], ["a.py", "b.py"])
        self.assertEqual(len(result["reference_docs"]), 2)
        self.assertEqual(result["reference_docs"][0]["path"], "docs/rules.md")

    def test_none_and_empty_skipped(self):
        """None と空リストはスキップされる。"""
        sections = [("kept", "yes"), ("none_val", None), ("empty", [])]
        path = self._path("skip.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertIn("kept", result)
        self.assertNotIn("none_val", result)
        self.assertNotIn("empty", result)

    def test_object_with_optional_fields(self):
        """オブジェクトの None / 空文字フィールドはスキップされる。"""
        sections = [
            ("items", [
                {"id": 1, "title": "test", "skip_reason": "", "extra": None},
            ])
        ]
        path = self._path("optional.yaml")
        write_nested_yaml(path, sections)
        content = Path(path).read_text()
        self.assertNotIn("skip_reason", content)
        self.assertNotIn("extra", content)

    def test_build_nested_yaml_text(self):
        """ファイル書き出しなしでテキスト取得。"""
        sections = [("key", "value")]
        text = build_nested_yaml_text(sections)
        self.assertIn("key: value", text)


# ---------------------------------------------------------------------------
# parse_yaml（読み込みパーサー）
# ---------------------------------------------------------------------------

class TestParseYaml(unittest.TestCase):
    """parse_yaml のテスト。"""

    def test_flat(self):
        content = "skill: review\nstatus: in_progress\nauto_count: 3\n"
        result = parse_yaml(content)
        self.assertEqual(result["skill"], "review")
        self.assertEqual(result["auto_count"], 3)

    def test_string_list(self):
        content = "target_files:\n  - a.py\n  - b.py\n"
        result = parse_yaml(content)
        self.assertEqual(result["target_files"], ["a.py", "b.py"])

    def test_object_list(self):
        content = (
            "items:\n"
            "  - id: 1\n"
            "    severity: critical\n"
            "    title: \"問題タイトル\"\n"
            "  - id: 2\n"
            "    severity: major\n"
            "    title: second\n"
        )
        result = parse_yaml(content)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["id"], 1)
        self.assertEqual(result["items"][0]["title"], "問題タイトル")

    def test_inline_array(self):
        content = "files_modified: [a.py, b.py]\n"
        result = parse_yaml(content)
        self.assertEqual(result["files_modified"], ["a.py", "b.py"])

    def test_comments_skipped(self):
        content = "# comment\nkey: value\n# another\n"
        result = parse_yaml(content)
        self.assertEqual(result["key"], "value")

    def test_empty_inline_array(self):
        content = "files: []\n"
        result = parse_yaml(content)
        self.assertEqual(result["files"], [])

    def test_bool_values(self):
        content = "auto_fixable: true\ndisabled: false\n"
        result = parse_yaml(content)
        self.assertTrue(result["auto_fixable"])
        self.assertFalse(result["disabled"])

    def test_list_with_many_leading_comments(self):
        """子要素の先頭に 10 行超のコメント / 空行があっても正しくパースされる。

        固定 10 行の先読み制限を削除したことの回帰テスト。
        """
        comment_lines = "\n".join(f"  # comment {i}" for i in range(15))
        content = (
            "items:\n"
            + comment_lines + "\n"
            + "  - id: 1\n"
            + "    title: first\n"
            + "  - id: 2\n"
            + "    title: second\n"
        )
        result = parse_yaml(content)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["id"], 1)
        self.assertEqual(result["items"][1]["title"], "second")

    def test_dict_block_with_many_leading_blank_lines(self):
        """辞書ブロックの先頭に多数の空行があっても正しくパースされる。"""
        blank_lines = "\n" * 12
        content = (
            "config:"
            + blank_lines
            + "  host: localhost\n"
            + "  port: 8080\n"
        )
        result = parse_yaml(content)
        self.assertEqual(result["config"]["host"], "localhost")
        self.assertEqual(result["config"]["port"], 8080)


# ---------------------------------------------------------------------------
# ラウンドトリップ: ネスト YAML
# ---------------------------------------------------------------------------

class TestNestedRoundtrip(_FsTestCase):
    """write_nested_yaml → read_yaml のラウンドトリップ。"""

    def test_plan_yaml_roundtrip(self):
        """plan.yaml 形式のラウンドトリップ。"""
        sections = [
            ("items", [
                {
                    "id": 1,
                    "severity": "critical",
                    "title": "help と review のコマンド仕様不一致",
                    "status": "pending",
                },
                {
                    "id": 2,
                    "severity": "major",
                    "title": "simple problem",
                    "status": "fixed",
                    "fixed_at": "2026-03-09T18:35:00Z",
                },
            ])
        ]
        path = self._path("plan.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["title"],
                         "help と review のコマンド仕様不一致")
        self.assertEqual(result["items"][1]["status"], "fixed")

    def test_evaluation_yaml_roundtrip(self):
        """evaluation.yaml 形式のラウンドトリップ。"""
        sections = [
            ("cycle", 1),
            ("items", [
                {
                    "id": 1,
                    "severity": "critical",
                    "title": "問題",
                    "recommendation": "fix",
                    "auto_fixable": True,
                    "reason": "明確な不整合",
                },
            ])
        ]
        path = self._path("evaluation.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(result["cycle"], 1)
        self.assertEqual(result["items"][0]["recommendation"], "fix")
        self.assertTrue(result["items"][0]["auto_fixable"])

    def test_refs_yaml_roundtrip(self):
        """refs.yaml 形式のラウンドトリップ。"""
        sections = [
            ("target_files", ["src/main.py", "src/util.py"]),
            ("reference_docs", [
                {"path": "docs/rules.md"},
                {"path": "docs/spec.md"},
            ]),
            ("review_criteria_path", "docs/review_criteria.md"),
            ("related_code", [
                {"path": "src/helper.py", "reason": "ユーティリティ関数",
                 "lines": "1-50"},
            ]),
        ]
        path = self._path("refs.yaml")
        write_nested_yaml(path, sections)
        result = read_yaml(path)
        self.assertEqual(result["target_files"], ["src/main.py", "src/util.py"])
        self.assertEqual(len(result["reference_docs"]), 2)
        self.assertEqual(result["review_criteria_path"],
                         "docs/review_criteria.md")
        self.assertEqual(result["related_code"][0]["lines"], "1-50")


# ---------------------------------------------------------------------------
# now_iso
# ---------------------------------------------------------------------------

class TestNowIso(unittest.TestCase):
    """now_iso のテスト。"""

    def test_format(self):
        ts = now_iso()
        import re
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


if __name__ == "__main__":
    unittest.main()
