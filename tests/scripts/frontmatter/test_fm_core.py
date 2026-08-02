#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_core.py のユニットテスト（DES-008 §6.4）。

テスト対象:
- フロントマター境界の切り出し（DES-008 §4.2）
- フロントマターの最小 YAML 解析（スカラ / ブロック配列 / インラインフロー配列）
- 本文正規化と body_hash（CRLF / 末尾空行で不変、本文変更で変化、
  フロントマター変更で不変）
- 信頼判定の各分岐（type 欠落 / doc-advisor を含まない type / フィールド欠落 /
  空値 / 型不一致 / 件数超過 / 文字数超過 / ハッシュ不一致 / ハッシュ形式不正 /
  未知の接頭辞。type はスカラ・配列の双方）

テスト方針:
- in-process import（fm_core は純粋ロジックのため subprocess を要しない）
"""

import os
import sys
import unittest

# テスト対象モジュールの import
FRONTMATTER_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..',
    'plugins', 'doc-advisor', 'scripts', 'frontmatter'
))
if FRONTMATTER_DIR not in sys.path:
    sys.path.insert(0, FRONTMATTER_DIR)

import fm_core
from fm_core import (
    MARKER,
    PURPOSE_MAX_LENGTH,
    LIST_MAX_ITEMS,
    VIOLATIONS,
    Violation,
    compute_body_hash,
    evaluate,
    evaluate_file,
    has_marker,
    normalize_body,
    parse_frontmatter,
    split_document,
    type_values,
    validate_metadata,
)


# ===========================================================================
# 共通ヘルパ（フロントマター付き文書の組み立て）
# ===========================================================================

BODY = "# タイトル\n\n本文の内容。\n"

VALID_FIELDS = {
    "title": "テスト文書",
    "purpose": "テストのための文書であることを示す",
    "content_details": ["項目 A", "項目 B"],
    "applicable_tasks": ["タスク A"],
    "keywords": ["fm_core", "body_hash"],
}


def render_frontmatter(fields):
    """dict をフロントマターの行へ変換する（値はそのまま出力する）。"""
    lines = []
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def build_document(fields=None, body=BODY, body_hash="auto", type_value=MARKER):
    """フロントマター付き文書を組み立てる。

    Args:
        fields: 5 フィールド（None なら VALID_FIELDS）
        body: 本文
        body_hash: 'auto' なら本文から算出、None なら body_hash 行を省略、
            それ以外は与えられた値をそのまま書く
        type_value: type に書く値。None なら type 行を省略。
            list を渡すとブロック配列として出力する

    Returns:
        str: 文書全体
    """
    ordered = {}
    if type_value is not None:
        ordered["type"] = type_value
    ordered.update(VALID_FIELDS if fields is None else fields)
    if body_hash == "auto":
        ordered["body_hash"] = compute_body_hash(body)
    elif body_hash is not None:
        ordered["body_hash"] = body_hash

    return "---\n" + render_frontmatter(ordered) + "\n---\n" + body


def violation_codes(result):
    """TrustResult から違反コードの集合を取り出す。"""
    return {code for code, _field, _detail in result.violations}


# ===========================================================================
# 境界の切り出し（DES-008 §4.2）
# ===========================================================================

class TestSplitDocument(unittest.TestCase):
    """フロントマター境界の切り出し。"""

    def test_no_frontmatter(self):
        text = "# タイトル\n\n本文。\n"
        parts = split_document(text)
        self.assertFalse(parts.has_frontmatter)
        self.assertEqual(parts.body, text)
        self.assertIsNone(parts.start_line)
        self.assertIsNone(parts.end_line)

    def test_empty_text(self):
        parts = split_document("")
        self.assertFalse(parts.has_frontmatter)
        self.assertEqual(parts.body, "")

    def test_frontmatter_split(self):
        text = "---\ntype: doc-advisor\n---\n# タイトル\n\n本文。\n"
        parts = split_document(text)
        self.assertTrue(parts.has_frontmatter)
        self.assertEqual(parts.frontmatter_text, "type: doc-advisor")
        self.assertEqual(parts.body, "# タイトル\n\n本文。\n")
        self.assertEqual(parts.start_line, 0)
        self.assertEqual(parts.end_line, 2)

    def test_leading_blank_lines_are_skipped(self):
        """先頭の空行は読み飛ばす（has_substantive_content と同じ方針）。"""
        text = "\n\n---\ntype: doc-advisor\n---\n本文。\n"
        parts = split_document(text)
        self.assertTrue(parts.has_frontmatter)
        self.assertEqual(parts.start_line, 2)
        self.assertEqual(parts.body, "本文。\n")

    def test_horizontal_rule_in_body_is_not_a_delimiter(self):
        """本文中の '---' は境界に影響しない。"""
        text = "---\ntype: doc-advisor\n---\n本文 1。\n\n---\n\n本文 2。\n"
        parts = split_document(text)
        self.assertTrue(parts.has_frontmatter)
        self.assertEqual(parts.body, "本文 1。\n\n---\n\n本文 2。\n")

    def test_unclosed_frontmatter_is_treated_as_absent(self):
        """未閉鎖はフロントマターとして成立していないものとして扱う。"""
        text = "---\ntype: doc-advisor\ntitle: x\n"
        parts = split_document(text)
        self.assertFalse(parts.has_frontmatter)
        self.assertEqual(parts.body, text)

    def test_crlf_delimiter_is_recognized(self):
        text = "---\r\ntype: doc-advisor\r\n---\r\n本文。\r\n"
        parts = split_document(text)
        self.assertTrue(parts.has_frontmatter)
        self.assertEqual(parts.body, "本文。\r\n")

    def test_empty_body(self):
        text = "---\ntype: doc-advisor\n---\n"
        parts = split_document(text)
        self.assertTrue(parts.has_frontmatter)
        self.assertEqual(parts.body, "")


# ===========================================================================
# フロントマターの最小 YAML 解析
# ===========================================================================

class TestParseFrontmatter(unittest.TestCase):
    """スカラ / ブロック配列 / インラインフロー配列の解析。"""

    def test_scalar_and_block_list(self):
        text = "type: doc-advisor\ntitle: 文書\nkeywords:\n  - a\n  - b\n"
        parsed = parse_frontmatter(text)
        self.assertEqual(parsed["type"], "doc-advisor")
        self.assertEqual(parsed["title"], "文書")
        self.assertEqual(parsed["keywords"], ["a", "b"])

    def test_inline_flow_list(self):
        """parse_simple_yaml が読めない 'type: [a, b]' を受理する。"""
        parsed = parse_frontmatter("type: [temporary-feature-requirement, doc-advisor]")
        self.assertEqual(
            parsed["type"], ["temporary-feature-requirement", "doc-advisor"]
        )

    def test_inline_empty_list(self):
        self.assertEqual(parse_frontmatter("keywords: []")["keywords"], [])

    def test_key_without_value_is_empty_list(self):
        self.assertEqual(parse_frontmatter("keywords:\n")["keywords"], [])

    def test_quoted_scalar_is_unquoted(self):
        parsed = parse_frontmatter('title: "a: b"\npurpose: \'x\'\n')
        self.assertEqual(parsed["title"], "a: b")
        self.assertEqual(parsed["purpose"], "x")

    def test_double_quoted_escapes(self):
        parsed = parse_frontmatter('title: "line\\nbreak \\"q\\" \\\\"')
        self.assertEqual(parsed["title"], 'line\nbreak "q" \\')

    def test_comments_and_blank_lines_are_ignored(self):
        parsed = parse_frontmatter("# コメント\n\ntitle: 文書\n")
        self.assertEqual(parsed, {"title": "文書"})

    def test_unknown_keys_are_kept(self):
        parsed = parse_frontmatter("name: skill-name\ndescription: 説明\n")
        self.assertEqual(parsed["name"], "skill-name")
        self.assertEqual(parsed["description"], "説明")

    def test_block_scalar_is_unparseable(self):
        """ブロックスカラは復元せず None（欠落と同じ扱いに落とす）。"""
        parsed = parse_frontmatter("description: |\n  複数行\n  の説明\n")
        self.assertIsNone(parsed["description"])

    def test_nested_mapping_is_ignored(self):
        parsed = parse_frontmatter("meta:\n  nested: 1\ntitle: 文書\n")
        self.assertEqual(parsed["title"], "文書")
        self.assertEqual(parsed["meta"], [])


# ===========================================================================
# 本文正規化と body_hash（DES-008 §4.2 / §6.4）
# ===========================================================================

class TestNormalizeBody(unittest.TestCase):
    """正規化の規定（改行 LF 統一 / 末尾の空白・空行除去 + 改行 1 つ）。"""

    def test_crlf_becomes_lf(self):
        self.assertEqual(normalize_body("a\r\nb\r\n"), "a\nb\n")

    def test_lone_cr_becomes_lf(self):
        self.assertEqual(normalize_body("a\rb\r"), "a\nb\n")

    def test_trailing_blank_lines_removed_and_single_newline_added(self):
        self.assertEqual(normalize_body("a\n\n\n   \n"), "a\n")

    def test_body_without_trailing_newline_gets_one(self):
        self.assertEqual(normalize_body("a"), "a\n")

    def test_leading_blank_lines_are_preserved(self):
        self.assertEqual(normalize_body("\n\na\n"), "\n\na\n")


class TestComputeBodyHash(unittest.TestCase):
    """body_hash の不変性・変化（DES-008 §6.4）。"""

    def test_format_is_prefixed_sha256(self):
        value = compute_body_hash(BODY)
        self.assertTrue(value.startswith("sha256:"))
        self.assertEqual(len(value), len("sha256:") + 64)
        self.assertRegex(value, r"^sha256:[0-9a-f]{64}$")

    def test_invariant_under_crlf(self):
        """CRLF と LF で不変。"""
        self.assertEqual(
            compute_body_hash("# T\n\n本文。\n"),
            compute_body_hash("# T\r\n\r\n本文。\r\n"),
        )

    def test_invariant_under_trailing_blank_lines(self):
        """末尾空行の有無で不変。"""
        self.assertEqual(
            compute_body_hash("# T\n\n本文。\n"),
            compute_body_hash("# T\n\n本文。\n\n\n  \n"),
        )

    def test_changes_when_body_changes(self):
        """本文変更で変化。"""
        self.assertNotEqual(
            compute_body_hash("# T\n\n本文。\n"),
            compute_body_hash("# T\n\n本文が変わった。\n"),
        )

    def test_invariant_when_frontmatter_changes(self):
        """フロントマター変更で不変（自己参照回避の要）。"""
        doc_a = build_document()
        doc_b = build_document(
            fields=dict(VALID_FIELDS, title="別のタイトル"), body_hash=None
        )
        hash_a = compute_body_hash(split_document(doc_a).body)
        hash_b = compute_body_hash(split_document(doc_b).body)
        self.assertEqual(hash_a, hash_b)

    def test_invariant_when_frontmatter_changes_through_evaluate(self):
        """フロントマターを書き換えても、打刻済みの body_hash は有効なまま。"""
        doc = build_document()
        self.assertTrue(evaluate(doc).trust)

        parts = split_document(doc)
        extended = (
            "---\n"
            + parts.frontmatter_text
            + "\nname: 追加キー\n---\n"
            + parts.body
        )
        self.assertTrue(evaluate(extended).trust)


# ===========================================================================
# type の正規化（スカラ・配列）
# ===========================================================================

class TestTypeValues(unittest.TestCase):
    """type はスカラ・配列の双方を受理する（DES-008 §5.1）。"""

    def test_scalar(self):
        self.assertEqual(type_values("doc-advisor"), ["doc-advisor"])

    def test_list(self):
        self.assertEqual(
            type_values(["temporary-feature-requirement", "doc-advisor"]),
            ["temporary-feature-requirement", "doc-advisor"],
        )

    def test_blank_scalar_is_empty(self):
        self.assertEqual(type_values("   "), [])

    def test_non_string_is_none(self):
        self.assertIsNone(type_values(None))
        self.assertIsNone(type_values(["ok", None]))

    def test_has_marker(self):
        self.assertTrue(has_marker({"type": "doc-advisor"}))
        self.assertTrue(has_marker({"type": ["x", "doc-advisor"]}))
        self.assertFalse(has_marker({"type": "x"}))
        self.assertFalse(has_marker({}))
        self.assertFalse(has_marker({"type": None}))


# ===========================================================================
# 信頼判定（DES-008 §5.1 / §5.3 / §6.4）
# ===========================================================================

class TestTrustDecision(unittest.TestCase):
    """§5.1 述語の各分岐。"""

    def assert_untrusted(self, result, code, warn=True):
        self.assertFalse(result.trust)
        self.assertIn(code, violation_codes(result))
        self.assertEqual(result.warn, warn)

    # --- 真になるケース ---

    def test_trusted_with_scalar_type(self):
        result = evaluate(build_document())
        self.assertTrue(result.trust)
        self.assertTrue(result.has_frontmatter)
        self.assertTrue(result.has_marker)
        self.assertFalse(result.warn)
        self.assertEqual(result.violations, [])
        self.assertEqual(result.expected_body_hash, result.actual_body_hash)

    def test_trusted_with_block_list_type(self):
        doc = build_document(type_value=["temporary-feature-requirement", MARKER])
        result = evaluate(doc)
        self.assertTrue(result.trust)
        self.assertTrue(result.has_marker)

    def test_trusted_with_inline_list_type(self):
        doc = build_document(type_value="[temporary-feature-requirement, doc-advisor]")
        result = evaluate(doc)
        self.assertTrue(result.trust)
        self.assertTrue(result.has_marker)

    def test_trusted_with_unknown_keys_present(self):
        fields = dict(VALID_FIELDS)
        fields["name"] = "skill-name"
        fields["applicable_when"] = ["条件 A"]
        result = evaluate(build_document(fields=fields))
        self.assertTrue(result.trust)

    def test_purpose_at_limit_is_trusted(self):
        fields = dict(VALID_FIELDS, purpose="あ" * PURPOSE_MAX_LENGTH)
        self.assertTrue(evaluate(build_document(fields=fields)).trust)

    def test_list_at_limit_is_trusted(self):
        fields = dict(
            VALID_FIELDS,
            keywords=[f"k{i}" for i in range(LIST_MAX_ITEMS)],
        )
        self.assertTrue(evaluate(build_document(fields=fields)).trust)

    # --- フロントマターが無い / マーカーが無い（正常な対象外。warning なし） ---

    def test_no_frontmatter_is_not_trusted_and_not_warned(self):
        result = evaluate("# タイトル\n\n本文。\n")
        self.assertFalse(result.trust)
        self.assertFalse(result.has_frontmatter)
        self.assertFalse(result.has_marker)
        self.assertFalse(result.warn)
        self.assertEqual(result.violations, [])

    def test_unclosed_frontmatter_is_not_warned(self):
        """未閉鎖はフロントマター無しと同じ扱い（warning を出さない）。"""
        result = evaluate("---\ntype: doc-advisor\ntitle: x\n")
        self.assertFalse(result.trust)
        self.assertFalse(result.has_frontmatter)
        self.assertFalse(result.warn)

    def test_type_missing(self):
        doc = build_document(type_value=None)
        result = evaluate(doc)
        self.assertFalse(result.has_marker)
        self.assert_untrusted(result, Violation.TYPE_MISSING, warn=False)

    def test_type_without_marker(self):
        doc = build_document(type_value="temporary-feature-requirement")
        result = evaluate(doc)
        self.assertFalse(result.has_marker)
        self.assert_untrusted(result, Violation.TYPE_MARKER_ABSENT, warn=False)

    def test_type_list_without_marker(self):
        doc = build_document(type_value=["temporary-feature-requirement", "other"])
        result = evaluate(doc)
        self.assertFalse(result.has_marker)
        self.assert_untrusted(result, Violation.TYPE_MARKER_ABSENT, warn=False)

    # --- マーカー有りで壊れている（warning あり） ---

    def test_field_missing(self):
        fields = dict(VALID_FIELDS)
        del fields["keywords"]
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_MISSING)

    def test_field_empty_string(self):
        fields = dict(VALID_FIELDS, title='""')
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_EMPTY)

    def test_field_empty_list(self):
        fields = dict(VALID_FIELDS, keywords=[])
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_EMPTY)

    def test_list_with_empty_item(self):
        fields = dict(VALID_FIELDS, keywords=['""', "b"])
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_EMPTY)

    def test_field_type_mismatch_string_where_array_expected(self):
        """content_details が配列ではなく文字列（§5.1 が挙げる代表例）。"""
        fields = dict(VALID_FIELDS)
        fields["content_details"] = "x"
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_TYPE_MISMATCH)

    def test_field_type_mismatch_array_where_string_expected(self):
        fields = dict(VALID_FIELDS)
        fields["title"] = ["a", "b"]
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_TYPE_MISMATCH)

    def test_type_invalid_shape(self):
        """type がブロックスカラ等で文字列・配列に解決できない。"""
        doc = (
            "---\ntype: |\n  doc-advisor\n"
            + render_frontmatter(VALID_FIELDS)
            + "\nbody_hash: "
            + compute_body_hash(BODY)
            + "\n---\n"
            + BODY
        )
        result = evaluate(doc)
        self.assertFalse(result.has_marker)
        self.assert_untrusted(result, Violation.TYPE_INVALID, warn=False)

    def test_too_many_items(self):
        fields = dict(
            VALID_FIELDS,
            keywords=[f"k{i}" for i in range(LIST_MAX_ITEMS + 1)],
        )
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_TOO_MANY_ITEMS)

    def test_purpose_too_long(self):
        fields = dict(VALID_FIELDS, purpose="あ" * (PURPOSE_MAX_LENGTH + 1))
        result = evaluate(build_document(fields=fields))
        self.assert_untrusted(result, Violation.FIELD_TOO_LONG)

    def test_body_hash_missing(self):
        result = evaluate(build_document(body_hash=None))
        self.assert_untrusted(result, Violation.BODY_HASH_MISSING)

    def test_body_hash_mismatch(self):
        doc = build_document(body_hash=compute_body_hash("別の本文\n"))
        result = evaluate(doc)
        self.assert_untrusted(result, Violation.BODY_HASH_MISMATCH)

    def test_body_hash_mismatch_after_body_edit(self):
        """打刻後に本文だけが編集された状態を検出する。"""
        doc = build_document()
        result = evaluate(doc + "\n追記された段落。\n")
        self.assert_untrusted(result, Violation.BODY_HASH_MISMATCH)

    def test_body_hash_malformed_no_prefix(self):
        result = evaluate(build_document(body_hash="0" * 64))
        self.assert_untrusted(result, Violation.BODY_HASH_MALFORMED)

    def test_body_hash_malformed_short_digest(self):
        result = evaluate(build_document(body_hash="sha256:abc"))
        self.assert_untrusted(result, Violation.BODY_HASH_MALFORMED)

    def test_body_hash_malformed_uppercase_digest(self):
        result = evaluate(build_document(body_hash="sha256:" + "A" * 64))
        self.assert_untrusted(result, Violation.BODY_HASH_MALFORMED)

    def test_body_hash_unknown_prefix(self):
        """未知の接頭辞は判定不能として扱い、混在期間を移行なしで越える。"""
        result = evaluate(build_document(body_hash="sha512:" + "a" * 64))
        self.assert_untrusted(result, Violation.BODY_HASH_UNKNOWN_ALGORITHM)

    def test_all_or_nothing_collects_every_violation(self):
        """部分利用しないため、複数の違反はすべて収集される（§5.2）。"""
        fields = dict(VALID_FIELDS, purpose="あ" * (PURPOSE_MAX_LENGTH + 1))
        del fields["keywords"]
        result = evaluate(build_document(fields=fields, body_hash="sha256:xyz"))
        codes = violation_codes(result)
        self.assertIn(Violation.FIELD_TOO_LONG, codes)
        self.assertIn(Violation.FIELD_MISSING, codes)
        self.assertIn(Violation.BODY_HASH_MALFORMED, codes)

    def test_violation_codes_are_declared(self):
        """違反コードは VIOLATIONS 集合に含まれる（enum の固定）。"""
        fields = dict(VALID_FIELDS)
        del fields["title"]
        result = evaluate(build_document(fields=fields, body_hash="bogus"))
        for code, _field, _detail in result.violations:
            self.assertIn(code, VIOLATIONS)


# ===========================================================================
# validate_metadata 単体（body_hash を含まない部分の検証）
# ===========================================================================

class TestValidateMetadata(unittest.TestCase):
    """スキーマ検証のみを直接呼ぶ。"""

    def test_valid(self):
        metadata = dict(VALID_FIELDS, type=MARKER)
        self.assertEqual(validate_metadata(metadata), [])

    def test_reports_field_name(self):
        metadata = dict(VALID_FIELDS, type=MARKER)
        del metadata["applicable_tasks"]
        violations = validate_metadata(metadata)
        self.assertEqual(len(violations), 1)
        code, field, _detail = violations[0]
        self.assertEqual(code, Violation.FIELD_MISSING)
        self.assertEqual(field, "applicable_tasks")


# ===========================================================================
# 独立性の境界（DES-008 §6.1）
# ===========================================================================

class TestIndependence(unittest.TestCase):
    """toc_store / toc_utils を import しないこと。"""

    def test_does_not_import_toc_modules(self):
        source_path = os.path.join(FRONTMATTER_DIR, "fm_core.py")
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import toc_store", source)
        self.assertNotIn("import toc_utils", source)
        self.assertNotIn("from toc_store", source)
        self.assertNotIn("from toc_utils", source)

    def test_module_namespace_is_clean(self):
        self.assertFalse(hasattr(fm_core, "toc_store"))
        self.assertFalse(hasattr(fm_core, "toc_utils"))


# ===========================================================================
# ファイル入力
# ===========================================================================

class TestEvaluateFile(unittest.TestCase):
    """ファイル経由の評価。"""

    def setUp(self):
        import shutil
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self._cleanup = lambda: shutil.rmtree(self.tmpdir, ignore_errors=True)

    def tearDown(self):
        self._cleanup()

    def test_evaluate_file(self):
        path = os.path.join(self.tmpdir, "doc.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_document())
        self.assertTrue(evaluate_file(path).trust)


if __name__ == "__main__":
    unittest.main()
