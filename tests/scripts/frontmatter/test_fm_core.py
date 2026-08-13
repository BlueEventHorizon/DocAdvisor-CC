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
- YAML エスケープが toc_utils.yaml_escape そのものであること（DES-008 §6.4）
- 行保存型マージ（未知キーのバイト保持 / type の和集合更新 / 未閉鎖の拒否）

テスト方針:
- in-process import（fm_core は純粋ロジックのため subprocess を要しない）
- fm_core は toc_utils を YAML エスケープの共有に限って import する。key / store_dir /
  ToC の置き場所を知る toc_store は import しない（DES-008 §6.1 の独立性の境界）
"""

import os
import sys
import unittest

# テスト対象モジュールの import
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'plugins', 'doc-advisor', 'scripts')
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import toc_utils

import fm_core
from fm_core import (
    DOC_ADVISOR_FIELDS,
    MARKER,
    PURPOSE_MAX_LENGTH,
    LIST_MAX_ITEMS,
    VIOLATIONS,
    FrontmatterWriteError,
    Violation,
    compute_body_hash,
    evaluate,
    evaluate_file,
    has_marker,
    has_unclosed_frontmatter,
    merge_frontmatter,
    merge_type_values,
    normalize_body,
    parse_frontmatter,
    split_document,
    type_values,
    unquote_yaml_value,
    validate_metadata,
    yaml_escape,
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
    """toc_store を import しないこと（toc_utils はエスケープの共有に限り可）。"""

    def test_does_not_import_toc_store(self):
        source_path = os.path.join(FRONTMATTER_DIR, "fm_core.py")
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import toc_store", source)
        self.assertNotIn("from toc_store", source)

    def test_module_namespace_has_no_key_resolution(self):
        self.assertFalse(hasattr(fm_core, "toc_store"))
        self.assertFalse(hasattr(fm_core, "resolve_store_dir"))


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


# ===========================================================================
# YAML エスケープ（DES-008 §6.4）
# ===========================================================================

# 共通ケース表。unquote_yaml_value の往復テストが入力列を必要とするため本ファイルに
# 置く。tests/scripts/test_toc_utils.py の TestYamlEscape が持つ入力列を網羅し、
# 日本語・': ' 含み・数値様文字列を含む。
YAML_ESCAPE_CASES = (
    # --- プレーンスカラとして安全（クォート不要） ---
    "normal text",
    "App Store, Google Play",
    "scope (App Store, Google Play)",
    "Role assignments (Yumemi, Daytona)",
    "10:00 deadline",
    "foo&bar",
    "item [1] description",
    "path\\to\\file",
    # --- YAML の特殊構文（クォート必要） ---
    "foo: bar",
    "see section #3",
    "[starts with bracket",
    "{starts with brace",
    "- starts with dash",
    "#starts with hash",
    "*starts with star",
    "&starts with amp",
    "!starts with bang",
    "?mapping key",
    "|literal block",
    ">folded block",
    "%TAG",
    "@mention",
    "`code`",
    "trailing colon:",
    "trailing space ",
    " leading space",
    # --- bool / null を表す語 ---
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "null",
    "none",
    "~",
    "TRUE",
    "Yes",
    # --- 数値様文字列 ---
    "123",
    "3.14",
    "0",
    "-1",
    "1e5",
    # --- 制御文字・引用符・バックスラッシュ ---
    "line1\nline2",
    "line1\rline2",
    "has\ttab",
    'has "double quotes"',
    "has 'single quotes'",
    "path\\to\nfile",
    # --- 空値 ---
    "",
    None,
    # --- 日本語（Unicode は無変換で保持される） ---
    "日本語テスト",
    "キーワード: 検索",
    "本文の言語に合わせる（DES-008 §4.4）",
)


class TestYamlEscapeIsShared(unittest.TestCase):
    """fm_core.yaml_escape が toc_utils.yaml_escape そのものであること。

    同じ値がフロントマターと toc.yaml で異なる表記になることを禁じる（§6.4）。
    かつて独立実装を 2 つ持って出力一致をテストで維持していたが、実装を 1 つに
    集約したため、ここでは同一オブジェクトであることを固定して再分岐を防ぐ。
    """

    def test_implementation_is_not_duplicated(self):
        self.assertIs(yaml_escape, toc_utils.yaml_escape)

    def test_frontmatter_inputs_are_escaped_as_expected(self):
        """フロントマター経路で通る入力の表記を固定する（回帰検出）。"""
        for value in YAML_ESCAPE_CASES:
            with self.subTest(value=value):
                escaped = yaml_escape(value)
                self.assertIsInstance(escaped, str)
                self.assertNotIn("\n", escaped)

    def test_empty_values_become_empty_quotes(self):
        """'' / None / 0 / [] は str() より前に空判定される（評価順序の固定）。"""
        for value in ("", None, 0, []):
            with self.subTest(value=value):
                self.assertEqual(yaml_escape(value), '""')

    def test_unicode_is_not_quoted(self):
        self.assertEqual(yaml_escape("日本語テスト"), "日本語テスト")

    def test_colon_space_is_quoted(self):
        self.assertEqual(yaml_escape("foo: bar"), '"foo: bar"')


class TestUnquoteYamlValueRoundTrip(unittest.TestCase):
    """unquote_yaml_value が yaml_escape の逆変換であることを固定する。

    この関数は公開 API であり、同ディレクトリの他 script（pending の _meta を
    読む fm_to_pending 等）が 3 つ目の逆変換実装を作らずに共有している。
    往復関係を壊す変更が入ればここで検出する。
    """

    def test_round_trip_restores_the_original_value(self):
        for value in YAML_ESCAPE_CASES:
            if value is None or value == "" or value == 0 or value == []:
                # 空値は yaml_escape が一律 '""' にするため往復しない（別テストで固定）
                continue
            with self.subTest(value=value):
                self.assertEqual(unquote_yaml_value(yaml_escape(value)), str(value))

    def test_empty_quotes_become_empty_string(self):
        self.assertEqual(unquote_yaml_value('""'), "")

    def test_plain_value_passes_through(self):
        self.assertEqual(unquote_yaml_value("plain"), "plain")

    def test_single_quotes_restore_doubled_apostrophe(self):
        self.assertEqual(unquote_yaml_value("'it''s'"), "it's")

    def test_escape_order_backslash_before_quote(self):
        self.assertEqual(yaml_escape('a\\b"c\n'), '"a\\\\b\\"c\\n"')


# ===========================================================================
# 行保存型マージ（DES-008 §4.5 / 戦略書 R1・D5）
# ===========================================================================

WRITE_METADATA = {
    "title": "テスト文書",
    "purpose": "行保存型マージの検証に用いる文書であることを示す",
    "content_details": ["項目 A", "項目 B"],
    "applicable_tasks": ["タスク A"],
    "keywords": ["fm_core", "merge_frontmatter"],
}


def frontmatter_lines(text):
    """文書のフロントマター部分を行の list として取り出す。"""
    parts = split_document(text)
    if not parts.has_frontmatter:
        return []
    return text.split("\n")[parts.start_line + 1:parts.end_line]


class TestHasUnclosedFrontmatter(unittest.TestCase):
    """未閉鎖の検出（split_document の has_frontmatter=False と区別する）。"""

    def test_unclosed(self):
        self.assertTrue(has_unclosed_frontmatter("---\ntype: doc-advisor\ntitle: x\n"))

    def test_closed(self):
        self.assertFalse(has_unclosed_frontmatter("---\ntype: doc-advisor\n---\n本文\n"))

    def test_no_frontmatter(self):
        self.assertFalse(has_unclosed_frontmatter("# タイトル\n\n本文。\n"))

    def test_empty(self):
        self.assertFalse(has_unclosed_frontmatter(""))


class TestMergeTypeValues(unittest.TestCase):
    """type は置換ではなく和集合で更新する（DES-008 §4.1 / §4.5）。"""

    def test_absent_becomes_marker_only(self):
        self.assertEqual(merge_type_values(None), [MARKER])

    def test_scalar_is_preserved(self):
        self.assertEqual(
            merge_type_values("temporary-feature-requirement"),
            ["temporary-feature-requirement", MARKER],
        )

    def test_list_order_is_preserved(self):
        self.assertEqual(
            merge_type_values(["a", "b"]), ["a", "b", MARKER]
        )

    def test_idempotent(self):
        once = merge_type_values("temporary-feature-requirement")
        self.assertEqual(merge_type_values(once), once)

    def test_marker_already_present_is_unchanged(self):
        self.assertEqual(merge_type_values([MARKER, "x"]), [MARKER, "x"])

    def test_duplicates_are_collapsed(self):
        self.assertEqual(merge_type_values(["a", "a"]), ["a", MARKER])

    def test_additional_values_are_appended(self):
        self.assertEqual(
            merge_type_values("a", ["b"]), ["a", "b", MARKER]
        )

    def test_unparseable_existing_is_treated_as_absent(self):
        self.assertEqual(merge_type_values(None), [MARKER])
        self.assertEqual(merge_type_values(["ok", None]), [MARKER])


class TestMergeFrontmatterTypeUnion(unittest.TestCase):
    """type の和集合更新（DES-008 §6.4 が要求するケース）。"""

    def test_temporary_feature_requirement_is_kept(self):
        doc = "---\ntype: temporary-feature-requirement\n---\n本文。\n"
        merged = merge_frontmatter(doc, WRITE_METADATA)
        parsed = parse_frontmatter(split_document(merged).frontmatter_text)
        self.assertEqual(
            parsed["type"], ["temporary-feature-requirement", MARKER]
        )

    def test_block_list_output_format(self):
        doc = "---\ntype: temporary-feature-requirement\n---\n本文。\n"
        merged = merge_frontmatter(doc, {})
        self.assertIn(
            "type:\n  - temporary-feature-requirement\n  - doc-advisor\n", merged
        )

    def test_single_value_is_scalar(self):
        merged = merge_frontmatter("---\n---\n本文。\n", {})
        self.assertIn("type: doc-advisor\n", merged)

    def test_idempotent_on_second_application(self):
        doc = "---\ntype: temporary-feature-requirement\n---\n本文。\n"
        once = merge_frontmatter(doc, WRITE_METADATA)
        twice = merge_frontmatter(once, WRITE_METADATA)
        self.assertEqual(once, twice)

    def test_existing_inline_list_is_accepted(self):
        doc = "---\ntype: [a, b]\n---\n本文。\n"
        merged = merge_frontmatter(doc, {})
        parsed = parse_frontmatter(split_document(merged).frontmatter_text)
        self.assertEqual(parsed["type"], ["a", "b", MARKER])

    def test_existing_block_list_is_accepted(self):
        doc = "---\ntype:\n  - a\n  - doc-advisor\n---\n本文。\n"
        merged = merge_frontmatter(doc, {})
        parsed = parse_frontmatter(split_document(merged).frontmatter_text)
        self.assertEqual(parsed["type"], ["a", MARKER])

    def test_additional_types_from_metadata(self):
        merged = merge_frontmatter("---\n---\n本文。\n", {"type": ["extra"]})
        parsed = parse_frontmatter(split_document(merged).frontmatter_text)
        self.assertEqual(parsed["type"], ["extra", MARKER])


class TestMergeFrontmatterLinePreservation(unittest.TestCase):
    """所有キー以外は原文行のままバイト保持する（戦略書 R1）。"""

    def test_unknown_keys_are_byte_preserved(self):
        doc = (
            "---\n"
            "name: skill-name\n"
            "description: don't touch this: value\n"
            "user-invocable: true\n"
            "allowed-tools: Bash, Read\n"
            "applicable_when:\n"
            "  - 条件 A\n"
            "---\n"
            "本文。\n"
        )
        merged = merge_frontmatter(doc, WRITE_METADATA)
        merged_lines = frontmatter_lines(merged)
        self.assertEqual(merged_lines[:6], frontmatter_lines(doc))

    def test_block_scalar_description_is_byte_preserved(self):
        doc = (
            "---\n"
            "name: skill-name\n"
            "description: |\n"
            "  1 行目\n"
            "  2 行目: コロンを含む\n"
            "user-invocable: true\n"
            "---\n"
            "本文。\n"
        )
        merged = merge_frontmatter(doc, WRITE_METADATA)
        self.assertEqual(frontmatter_lines(merged)[:5], frontmatter_lines(doc))

    def test_body_is_byte_preserved(self):
        body = "# タイトル\n\n本文 1。\n\n---\n\n本文 2。\ntrailing   \n\n"
        doc = "---\nname: x\n---\n" + body
        merged = merge_frontmatter(doc, WRITE_METADATA)
        self.assertEqual(split_document(merged).body, body)

    def test_existing_owned_key_is_replaced_in_place(self):
        doc = (
            "---\n"
            "name: x\n"
            "title: 旧タイトル\n"
            "description: 説明\n"
            "---\n"
            "本文。\n"
        )
        merged = merge_frontmatter(doc, {"title": "新タイトル"})
        lines = frontmatter_lines(merged)
        self.assertEqual(lines[0], "name: x")
        self.assertEqual(lines[1], "title: 新タイトル")
        self.assertEqual(lines[2], "description: 説明")

    def test_existing_owned_list_block_is_replaced_entirely(self):
        doc = (
            "---\n"
            "keywords:\n"
            "  - 旧 A\n"
            "  - 旧 B\n"
            "name: x\n"
            "---\n"
            "本文。\n"
        )
        merged = merge_frontmatter(doc, {"keywords": ["新 A"]})
        self.assertEqual(
            frontmatter_lines(merged), ["keywords:", "  - 新 A", "name: x", "type: doc-advisor"]
        )

    def test_owned_key_absent_from_metadata_is_left_untouched(self):
        doc = "---\nbody_hash: sha256:xyz\nname: x\n---\n本文。\n"
        merged = merge_frontmatter(doc, {"title": "T"})
        self.assertEqual(frontmatter_lines(merged)[0], "body_hash: sha256:xyz")

    def test_doc_advisor_keys_are_appended_at_the_end(self):
        doc = "---\nname: x\n---\n本文。\n"
        merged = merge_frontmatter(doc, WRITE_METADATA)
        lines = frontmatter_lines(merged)
        self.assertEqual(lines[0], "name: x")
        self.assertEqual(lines[1], "type: doc-advisor")
        self.assertEqual(lines[2], "title: テスト文書")

    def test_values_are_escaped(self):
        merged = merge_frontmatter(
            "---\n---\n本文。\n", {"title": "foo: bar", "keywords": ["true"]}
        )
        self.assertIn('title: "foo: bar"', merged)
        self.assertIn('  - "true"', merged)

    def test_new_frontmatter_is_inserted_when_absent(self):
        doc = "# タイトル\n\n本文。\n"
        merged = merge_frontmatter(doc, WRITE_METADATA)
        self.assertTrue(merged.startswith("---\ntype: doc-advisor\n"))
        self.assertEqual(split_document(merged).body, doc)

    def test_unclosed_frontmatter_is_rejected(self):
        doc = "---\nname: x\ntitle: y\n"
        with self.assertRaises(FrontmatterWriteError):
            merge_frontmatter(doc, WRITE_METADATA)

    def test_unowned_key_is_rejected(self):
        with self.assertRaises(ValueError):
            merge_frontmatter("---\n---\n本文。\n", {"description": "x"})

    def test_merged_document_is_trusted(self):
        doc = "---\nname: x\n---\n" + BODY
        metadata = dict(WRITE_METADATA)
        metadata["body_hash"] = compute_body_hash(split_document(doc).body)
        self.assertTrue(evaluate(merge_frontmatter(doc, metadata)).trust)


class TestMergeFrontmatterRoundTripOnRealFiles(unittest.TestCase):
    """実配布物と実ローカル SKILL を入力にした往復テスト（戦略書 R1 の固定）。

    いずれも読み取り専用の入力として使い、実ファイルは書き換えない。
    """

    TARGETS = (
        "plugins/doc-advisor/skills/check-toc/SKILL.md",
        "plugins/doc-advisor/skills/index-docs/SKILL.md",
        "plugins/doc-advisor/skills/query-docs/SKILL.md",
        "plugins/doc-advisor/agents/toc-updater.md",
        "plugins/doc-advisor/agents/query-worker.md",
        "plugins/doc-advisor/formats/toc_format.md",
        ".claude/skills/review-skill-description/SKILL.md",
    )

    def _read(self, relative_path):
        path = os.path.join(REPO_ROOT, relative_path)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_existing_lines_are_byte_preserved(self):
        for relative_path in self.TARGETS:
            with self.subTest(path=relative_path):
                original = self._read(relative_path)
                parts = split_document(original)
                self.assertTrue(parts.has_frontmatter)

                metadata = dict(WRITE_METADATA)
                metadata["body_hash"] = compute_body_hash(parts.body)
                merged = merge_frontmatter(original, metadata)

                original_lines = original.split("\n")
                merged_lines = merged.split("\n")

                # 終端デリミタ行より前（= 既存フロントマター）が原文のまま
                self.assertEqual(
                    merged_lines[:parts.end_line], original_lines[:parts.end_line]
                )
                # 終端デリミタ行以降（= 本文）が原文のまま
                self.assertEqual(
                    "\n".join(merged_lines[-(len(original_lines) - parts.end_line):]),
                    "\n".join(original_lines[parts.end_line:]),
                )
                self.assertEqual(split_document(merged).body, parts.body)

    def test_doc_advisor_keys_are_added_and_trusted(self):
        for relative_path in self.TARGETS:
            with self.subTest(path=relative_path):
                original = self._read(relative_path)
                metadata = dict(WRITE_METADATA)
                metadata["body_hash"] = compute_body_hash(
                    split_document(original).body
                )
                merged = merge_frontmatter(original, metadata)

                parsed = parse_frontmatter(split_document(merged).frontmatter_text)
                for field in DOC_ADVISOR_FIELDS:
                    self.assertIn(field, parsed)
                self.assertEqual(parsed["type"], MARKER)
                self.assertTrue(evaluate(merged).trust)

    def test_merge_is_idempotent(self):
        for relative_path in self.TARGETS:
            with self.subTest(path=relative_path):
                original = self._read(relative_path)
                metadata = dict(WRITE_METADATA)
                metadata["body_hash"] = compute_body_hash(
                    split_document(original).body
                )
                once = merge_frontmatter(original, metadata)
                self.assertEqual(once, merge_frontmatter(once, metadata))

    def test_source_files_are_not_modified(self):
        for relative_path in self.TARGETS:
            with self.subTest(path=relative_path):
                before = self._read(relative_path)
                merge_frontmatter(before, WRITE_METADATA)
                self.assertEqual(before, self._read(relative_path))


class TestUnsupportedCharacterValueDomain(unittest.TestCase):
    """5 フィールドの値域が「単一行の平文」を機械的に強制すること（Issue #41）。

    以前はこの制約が DES-008 の「前提」として書かれているだけで、どの検査点も文字を
    見ていなかった。前提が守られる保証が無いまま writer 側だけがエスケープで防御し、
    reader（toc_utils の引用符除去）が復元しないため、値が索引サイクルごとに壊れた。
    往復できない値を**入れない**ことで、往復の必要そのものを無くす。
    """

    # yaml_escape が引用符で囲むだけで済み、strip による読み戻しで復元できる値。
    # 禁止対象を広げすぎないことの回帰テストでもある。
    ROUND_TRIPPABLE = (
        "Define the ToC generation flow",
        "query-docs: search entry point",
        "a #tag here",
        "- leading hyphen",
        "trailing space ",
        "it's fine in the middle",
        "true",
        "123",
    )

    # 読み戻しで値が変わってしまう（= 値域外）値。
    NOT_ROUND_TRIPPABLE = (
        'has "double quotes"',
        # バックスラッシュ単独では引用符が付かず往復するが、引用符が付く条件
        # （ここでは `: `）と共起した瞬間に壊れる
        "back\\slash and: colon",
        "line1\nline2",
        "tab\there",
        "'leading single quote",
        "trailing single quote'",
    )

    # 現状の yaml_escape では偶然往復するが、それは「他に引用符を要する文字が無い」
    # という条件に依存している。条件が変わると壊れる値を許容すると、値域が
    # 「共起次第」になり検査の意味が失われるため、無条件で禁止する。
    BANNED_THOUGH_CURRENTLY_HARMLESS = (
        "back\\slash alone",
    )

    def _round_trips(self, value):
        """writer -> toc.yaml -> reader の往復で値が保たれるか（実際の関数で確認）。"""
        emitted = toc_utils.yaml_escape(value)
        return emitted.strip().strip("\"'") == value

    def test_round_trippable_values_are_accepted(self):
        for value in self.ROUND_TRIPPABLE:
            with self.subTest(value=value):
                self.assertIsNone(fm_core.unsupported_character_reason(value))

    def test_not_round_trippable_values_are_rejected(self):
        for value in self.NOT_ROUND_TRIPPABLE:
            with self.subTest(value=value):
                self.assertIsNotNone(fm_core.unsupported_character_reason(value))

    def test_conditionally_safe_values_are_rejected_unconditionally(self):
        """共起次第で壊れる文字は、単独で無害な場合も禁止する。"""
        for value in self.BANNED_THOUGH_CURRENTLY_HARMLESS:
            with self.subTest(value=value):
                self.assertIsNotNone(fm_core.unsupported_character_reason(value))
                # 現状は往復する（= 禁止理由は「今壊れるから」ではない）
                self.assertTrue(self._round_trips(value))

    def test_accepted_values_actually_round_trip(self):
        """受理する値が本当に往復することを、実装ではなく挙動で固定する。"""
        for value in self.ROUND_TRIPPABLE:
            with self.subTest(value=value):
                self.assertTrue(self._round_trips(value))

    def test_rejected_values_would_actually_break(self):
        """禁止する値が本当に壊れることを確認する（過剰な禁止を防ぐ）。"""
        for value in self.NOT_ROUND_TRIPPABLE:
            with self.subTest(value=value):
                self.assertFalse(self._round_trips(value))

    def test_string_field_violation_is_reported(self):
        violations = fm_core.validate_field_values({"title": 'Say "hi" now'})
        self.assertEqual(
            [(code, field) for code, field, _ in violations],
            [(Violation.FIELD_UNSUPPORTED_CHARACTER, "title")],
        )

    def test_list_field_element_violation_is_reported(self):
        violations = fm_core.validate_field_values(
            {"keywords": ["ok", 'bad "quote"', "ok2"]}
        )
        self.assertEqual(
            [(code, field) for code, field, _ in violations],
            [(Violation.FIELD_UNSUPPORTED_CHARACTER, "keywords")],
        )

    def test_violation_code_is_in_declared_set(self):
        """有効値集合に載せ忘れると、呼び出し側の検証が新コードを弾く。"""
        self.assertIn(Violation.FIELD_UNSUPPORTED_CHARACTER, VIOLATIONS)


class TestNormalizeMetadataValues(unittest.TestCase):
    """書き込みの入口で 5 フィールドを値域内へ収めること（Issue #41）。

    値域規則は残す（読み取り側の判定と、変換できない `\\` の拒否に使う）。書き込み側は
    拒否の前に変換を挟み、意味に関わらない表記のために文書全体を再抽出させない。
    """

    def test_string_and_list_fields_are_normalized(self):
        metadata, changed = fm_core.normalize_metadata_values({
            "title": 'Say "hi" now',
            "purpose": "no change here",
            "keywords": ["ok", 'bad "quote"'],
        })
        self.assertEqual(metadata["title"], "Say `hi` now")
        self.assertEqual(metadata["purpose"], "no change here")
        self.assertEqual(metadata["keywords"], ["ok", "bad `quote`"])
        self.assertEqual(changed, ["title", "keywords"])

    def test_unchanged_metadata_reports_no_fields(self):
        metadata, changed = fm_core.normalize_metadata_values({"title": "plain"})
        self.assertEqual(metadata, {"title": "plain"})
        self.assertEqual(changed, [])

    def test_input_dict_is_not_mutated(self):
        original = {"title": 'has "quotes"'}
        fm_core.normalize_metadata_values(original)
        self.assertEqual(original, {"title": 'has "quotes"'})

    def test_none_is_passed_through(self):
        self.assertEqual(fm_core.normalize_metadata_values(None), (None, []))

    def test_only_backslash_survives_normalization_as_a_violation(self):
        """変換で解消できるものは解消され、残るのは `\\` だけであること。"""
        convertible = {
            "title": 'has "quotes"',
            "purpose": "multi\nline",
            "content_details": ["'edge quote'"],
            "applicable_tasks": ["trailing'"],
            "keywords": ["tab\there"],
        }
        normalized, _ = fm_core.normalize_metadata_values(convertible)
        self.assertEqual(fm_core.validate_field_values(normalized), [])

        not_convertible = {"title": "back\\slash"}
        normalized, changed = fm_core.normalize_metadata_values(not_convertible)
        self.assertEqual(changed, [])
        self.assertEqual(
            [(code, field) for code, field, _ in
             fm_core.validate_field_values(normalized)],
            [(Violation.FIELD_UNSUPPORTED_CHARACTER, "title")],
        )


if __name__ == "__main__":
    unittest.main()
