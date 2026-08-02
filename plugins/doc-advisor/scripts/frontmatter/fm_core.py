#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_core.py — フロントマターの読み取り基盤（doc-advisor plugin / frontmatter）

DES-008 §4.1（確定スキーマ）/ §4.2（境界・正規化・body_hash）/ §5.1（信頼判定の述語）/
§6.1（独立性の境界）/ §6.2（責務）を実装する。

責務（読み取り系のみ。書き込み・マージは本モジュールの対象外）:
- フロントマター境界の切り出し（先頭 '---' 〜 終端 '---'）
- フロントマターの最小 YAML 解析（スカラ / ブロック配列 / インラインフロー配列）
- 本文の正規化（改行 LF 統一・末尾の空白と空行の除去 + 改行 1 つ）
- 本文ハッシュの算出（SHA-256、値は 'sha256:<64 桁 hex>'）
- 信頼判定（DES-008 §5.1 の述語。type はスカラ・配列の双方を受理）

独立性（DES-008 §6.1）:
- toc_store.py / toc_utils.py を import しない。key 解決も store_dir 解決も行わない
- 判定に必要な違反コードは本モジュールに独立定義する

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import hashlib
import re
from collections import namedtuple

# ---------------------------------------------------------------------------
# 定数（DES-008 §4.1 / §4.2 / §5.1、上限の正本は formats/toc_format.md）
# ---------------------------------------------------------------------------

# フロントマターのデリミタ行（前後の空白を除いた比較で用いる）
DELIMITER = "---"

# 識別マーカー（DES-008 §4.1）。type に含まれるかどうかで判定する
MARKER = "doc-advisor"

# doc-advisor が定義する 7 キー。type 以外の 6 キーは doc-advisor が単独所有する
TYPE_FIELD = "type"
BODY_HASH_FIELD = "body_hash"
STRING_FIELDS = ("title", "purpose")
LIST_FIELDS = ("content_details", "applicable_tasks", "keywords")
DOC_ADVISOR_FIELDS = (TYPE_FIELD,) + STRING_FIELDS + LIST_FIELDS + (BODY_HASH_FIELD,)

# purpose の文字数上限・各配列の件数上限（formats/toc_format.md の Field Guidelines）
PURPOSE_MAX_LENGTH = 200
LIST_MIN_ITEMS = 1
LIST_MAX_ITEMS = 10

# 本文ハッシュのアルゴリズムと値の形式（DES-008 §4.2）。
# 接頭辞は将来のアルゴリズム変更時に既存値と区別するために前置する。
HASH_ALGORITHM = "sha256"
BODY_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# 'name:' 形式の接頭辞を持つかどうかの判定用（未知接頭辞と単なる形式不正を分ける）
HASH_PREFIX_RE = re.compile(r"^([A-Za-z0-9_-]+):")


class Violation:
    """信頼判定で検出した違反の種別（DES-008 §5.1 / §5.3）。

    toc_store.ErrorCode と同形だが、独立性の境界（§6.1）により frontmatter 側に
    独立定義する。値はテストで固定する。
    """

    # type（識別マーカー）
    TYPE_MISSING = "TYPE_MISSING"
    TYPE_INVALID = "TYPE_INVALID"
    TYPE_MARKER_ABSENT = "TYPE_MARKER_ABSENT"

    # 5 フィールド共通
    FIELD_MISSING = "FIELD_MISSING"
    FIELD_EMPTY = "FIELD_EMPTY"
    FIELD_TYPE_MISMATCH = "FIELD_TYPE_MISMATCH"
    FIELD_TOO_LONG = "FIELD_TOO_LONG"
    FIELD_TOO_MANY_ITEMS = "FIELD_TOO_MANY_ITEMS"

    # body_hash
    BODY_HASH_MISSING = "BODY_HASH_MISSING"
    BODY_HASH_MALFORMED = "BODY_HASH_MALFORMED"
    BODY_HASH_UNKNOWN_ALGORITHM = "BODY_HASH_UNKNOWN_ALGORITHM"
    BODY_HASH_MISMATCH = "BODY_HASH_MISMATCH"


# 違反コードの有効値集合。テスト・呼び出し側の検証で参照する
VIOLATIONS = frozenset({
    Violation.TYPE_MISSING,
    Violation.TYPE_INVALID,
    Violation.TYPE_MARKER_ABSENT,
    Violation.FIELD_MISSING,
    Violation.FIELD_EMPTY,
    Violation.FIELD_TYPE_MISMATCH,
    Violation.FIELD_TOO_LONG,
    Violation.FIELD_TOO_MANY_ITEMS,
    Violation.BODY_HASH_MISSING,
    Violation.BODY_HASH_MALFORMED,
    Violation.BODY_HASH_UNKNOWN_ALGORITHM,
    Violation.BODY_HASH_MISMATCH,
})


# ---------------------------------------------------------------------------
# 戻り値の構造体
# ---------------------------------------------------------------------------

# フロントマター境界の切り出し結果。
# start_line / end_line は改行で分割した行の 0 始まり添字（書き込み側が原文を
# 行単位で保持したまま差し替えるために保持する）。フロントマターが無い場合は None。
DocumentParts = namedtuple(
    "DocumentParts",
    "has_frontmatter frontmatter_text body start_line end_line",
)

# 信頼判定の結果。
# trust:      DES-008 §5.1 の述語の値
# has_marker: type に doc-advisor が含まれるか（warning を出すかの判断に使う）
# warn:       has_marker かつ trust が偽（§5.3。規約違反として報告する）
# violations: 検出した違反（(コード, フィールド名, 詳細) のタプルの列）
TrustResult = namedtuple(
    "TrustResult",
    "trust has_frontmatter has_marker warn violations metadata "
    "expected_body_hash actual_body_hash",
)


# ---------------------------------------------------------------------------
# 境界の切り出し（DES-008 §4.2）
# ---------------------------------------------------------------------------

def split_document(text):
    """Markdown 文書をフロントマターと本文に切り分ける。

    prepare_toc.has_substantive_content と同じステートマシン方針を踏襲する
    （先頭の空行を読み飛ばし、最初の '---' で開始、次の '---' で終了。それ以降の
    '---' は本文の通常行）。ただし import はせず独立に再実装する（DES-008 §6.1）。

    未閉鎖（先頭 '---' はあるが終端 '---' が無い）の場合は **フロントマターとして
    成立していない** とみなし、フロントマター無しとして返す。DES-008 §4.2 は本文を
    「終端デリミタ行の次の行から EOF まで」と定義しており、終端が無ければ本文の範囲
    自体が定義されず body_hash を算出できないためである。has_substantive_content は
    未閉鎖を「以降すべて frontmatter（＝本文ゼロ）」として扱うが、あちらの目的は
    「実体内容の有無」の判定であり、本関数の目的（本文範囲の確定）とは異なるため
    挙動を一致させない。

    Args:
        text: 文書全体の文字列

    Returns:
        DocumentParts: has_frontmatter が False のとき frontmatter_text は空文字列、
            body は text 全体、start_line / end_line は None
    """
    # splitlines は \x0b / \x0c /   等でも分割するため使わない。
    # 本文をバイト単位で復元できるよう '\n' のみで分割する（\r は行末に残り
    # strip() 比較で吸収され、body へは原文のまま引き継がれる）。
    lines = text.split("\n")

    index = 0
    while index < len(lines) and lines[index].strip() == "":
        index += 1

    if index >= len(lines) or lines[index].strip() != DELIMITER:
        return DocumentParts(False, "", text, None, None)

    start_line = index
    for i in range(start_line + 1, len(lines)):
        if lines[i].strip() == DELIMITER:
            frontmatter_text = "\n".join(lines[start_line + 1:i])
            body = "\n".join(lines[i + 1:])
            return DocumentParts(True, frontmatter_text, body, start_line, i)

    # 未閉鎖 → フロントマター無しとして扱う
    return DocumentParts(False, "", text, None, None)


# ---------------------------------------------------------------------------
# フロントマターの最小 YAML 解析
# ---------------------------------------------------------------------------

def _unquote(value):
    """引用符付きスカラを素の文字列へ戻す。

    toc_utils.yaml_escape が出力する二重引用符形式（バックスラッシュ・引用符・
    改行・タブをエスケープ）を復元する。単一引用符は YAML の規約に従い '' のみを
    ' へ戻す。引用符で囲まれていない値はそのまま返す。
    """
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        inner = value[1:-1]
        result = []
        i = 0
        while i < len(inner):
            char = inner[i]
            if char == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                if nxt in mapping:
                    result.append(mapping[nxt])
                    i += 2
                    continue
            result.append(char)
            i += 1
        return "".join(result)

    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")

    return value


def _parse_inline_list(value):
    """インラインフロー配列（'[a, b]'）を要素の list へ変換する。

    toc_format はインライン配列を禁止しているが、type は他ツールが書く可能性が
    あるため読み取り側は受理する（DES-008 §4.1 の共有キー）。
    """
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_unquote(item.strip()) for item in inner.split(",")]


def parse_frontmatter(frontmatter_text):
    """フロントマターの最上位キーを dict へ解析する。

    対応する形式:
    - スカラ（`key: value`。引用符付きも可）
    - ブロック配列（`key:` の次行以降の `- item`）
    - インラインフロー配列（`key: [a, b]` / `key: []`）

    ブロックスカラ（`|` / `>`）は toc_format が禁止しており、値を復元すると
    デリミタ記号そのものが非空文字列として通ってしまうため、値 None として扱う
    （スキーマ検証で欠落と同じく落ち、AI 抽出へフォールバックする）。
    最上位キー配下のネストした dict は解析せず無視する。

    Args:
        frontmatter_text: デリミタ行を含まないフロントマター本体

    Returns:
        dict: キー → 文字列 / 文字列の list / None
    """
    result = {}
    current_key = None
    current_list = None

    for line in frontmatter_text.split("\n"):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # ブロック配列の要素（インデントの有無は問わない）
        if stripped.startswith("- ") or stripped == "-":
            if current_list is not None:
                item = stripped[1:].strip()
                current_list.append(_unquote(item))
            continue

        # 最上位キー以外（ネストした dict 等）は無視する
        if line[:1].isspace():
            continue

        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        current_key = key
        current_list = None

        if not value:
            # 次行以降のブロック配列を受け付ける（要素が無ければ空配列）
            current_list = []
            result[key] = current_list
        elif value.startswith("[") and value.endswith("]"):
            result[key] = _parse_inline_list(value)
        elif value[0] in ("|", ">"):
            result[key] = None
        else:
            result[key] = _unquote(value)

    return result


# ---------------------------------------------------------------------------
# 本文の正規化と body_hash（DES-008 §4.2）
# ---------------------------------------------------------------------------

def normalize_body(body):
    """本文をハッシュ計算前の正規形へ変換する。

    1. 改行コードを LF に統一する（CRLF / 単独 CR → LF）
    2. 末尾の空白・空行を除去し、改行 1 つを付与する

    「迷ったら正規化する」（DES-008 §4.2）方針に従い、単独 CR も LF へ寄せる。
    正規化しすぎて起きるのは「意味が同じ本文が同じハッシュになる」＝正しい挙動であり、
    陳腐化の見逃しは生まない。

    Args:
        body: 本文（終端デリミタ行の次の行から EOF まで）

    Returns:
        str: 正規化済みの本文
    """
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip() + "\n"


def compute_body_hash(body):
    """本文の正規形から body_hash を算出する。

    Args:
        body: 本文（正規化前でよい）

    Returns:
        str: 'sha256:<64 桁 hex>'
    """
    digest = hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{digest}"


# ---------------------------------------------------------------------------
# スキーマ検証（DES-008 §5.1）
# ---------------------------------------------------------------------------

def type_values(raw):
    """type の値をリストへ正規化する。

    スカラは 1 要素として扱う（DES-008 §5.1）。文字列 / 文字列の list 以外は
    正規化できないため None を返す。

    Args:
        raw: parse_frontmatter が返した type の値

    Returns:
        list または None（型が不正な場合）
    """
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        if not all(isinstance(item, str) for item in raw):
            return None
        return [item.strip() for item in raw if item.strip()]
    return None


def has_marker(metadata):
    """type に識別マーカー doc-advisor が含まれるか判定する。

    Args:
        metadata: parse_frontmatter が返した dict

    Returns:
        bool
    """
    if TYPE_FIELD not in metadata:
        return False
    values = type_values(metadata[TYPE_FIELD])
    if values is None:
        return False
    return MARKER in values


def validate_metadata(metadata):
    """5 フィールドと type を DES-008 §5.1 の表に従って検証する。

    body_hash の検証は本文が必要なため check_body_hash が担う。

    Args:
        metadata: parse_frontmatter が返した dict

    Returns:
        list: (violation_code, field, detail) のタプルの列。空なら適合
    """
    violations = []

    # type: string または array[string]、doc-advisor を要素に含む
    if TYPE_FIELD not in metadata:
        violations.append((Violation.TYPE_MISSING, TYPE_FIELD, "type がありません"))
    else:
        values = type_values(metadata[TYPE_FIELD])
        if values is None:
            violations.append((
                Violation.TYPE_INVALID,
                TYPE_FIELD,
                "type は文字列または文字列の配列である必要があります",
            ))
        elif MARKER not in values:
            violations.append((
                Violation.TYPE_MARKER_ABSENT,
                TYPE_FIELD,
                f"type に {MARKER} が含まれていません",
            ))

    # title / purpose: 非空文字列（purpose は 200 文字以内）
    for field in STRING_FIELDS:
        if field not in metadata:
            violations.append((Violation.FIELD_MISSING, field, f"{field} がありません"))
            continue
        value = metadata[field]
        if value is None or isinstance(value, list):
            violations.append((
                Violation.FIELD_TYPE_MISMATCH, field, f"{field} は文字列である必要があります"
            ))
            continue
        if not value.strip():
            violations.append((Violation.FIELD_EMPTY, field, f"{field} が空です"))
            continue
        if field == "purpose" and len(value) > PURPOSE_MAX_LENGTH:
            violations.append((
                Violation.FIELD_TOO_LONG,
                field,
                f"purpose が {PURPOSE_MAX_LENGTH} 文字を超えています（{len(value)} 文字）",
            ))

    # content_details / applicable_tasks / keywords: 1〜10 件、各要素は非空文字列
    for field in LIST_FIELDS:
        if field not in metadata:
            violations.append((Violation.FIELD_MISSING, field, f"{field} がありません"))
            continue
        value = metadata[field]
        if not isinstance(value, list):
            violations.append((
                Violation.FIELD_TYPE_MISMATCH, field, f"{field} は配列である必要があります"
            ))
            continue
        if len(value) < LIST_MIN_ITEMS:
            violations.append((Violation.FIELD_EMPTY, field, f"{field} が空配列です"))
            continue
        if len(value) > LIST_MAX_ITEMS:
            violations.append((
                Violation.FIELD_TOO_MANY_ITEMS,
                field,
                f"{field} が {LIST_MAX_ITEMS} 件を超えています（{len(value)} 件）",
            ))
            continue
        if any((not isinstance(item, str)) or (not item.strip()) for item in value):
            violations.append((
                Violation.FIELD_EMPTY, field, f"{field} に空の要素が含まれています"
            ))

    return violations


def check_body_hash(metadata, body):
    """body_hash が存在し、接頭辞が既知で、現在の本文と一致するか検証する。

    Args:
        metadata: parse_frontmatter が返した dict
        body: 本文（正規化前でよい）

    Returns:
        tuple: (violations, expected, actual)。violations は
            (violation_code, field, detail) のタプルの列
    """
    actual = compute_body_hash(body)

    if BODY_HASH_FIELD not in metadata:
        return (
            [(Violation.BODY_HASH_MISSING, BODY_HASH_FIELD, "body_hash がありません")],
            None,
            actual,
        )

    expected = metadata[BODY_HASH_FIELD]
    if not isinstance(expected, str):
        return (
            [(
                Violation.BODY_HASH_MALFORMED,
                BODY_HASH_FIELD,
                "body_hash は文字列である必要があります",
            )],
            None,
            actual,
        )
    if not expected.strip():
        return (
            [(Violation.BODY_HASH_MISSING, BODY_HASH_FIELD, "body_hash が空です")],
            None,
            actual,
        )

    expected = expected.strip()

    if not BODY_HASH_RE.match(expected):
        prefix_match = HASH_PREFIX_RE.match(expected)
        if prefix_match and prefix_match.group(1) != HASH_ALGORITHM:
            # 未知の接頭辞は「判定不能 → AI 抽出へフォールバック」として扱う（§4.2）
            return (
                [(
                    Violation.BODY_HASH_UNKNOWN_ALGORITHM,
                    BODY_HASH_FIELD,
                    f"未知のハッシュ接頭辞です: {prefix_match.group(1)}",
                )],
                expected,
                actual,
            )
        return (
            [(
                Violation.BODY_HASH_MALFORMED,
                BODY_HASH_FIELD,
                "body_hash が 'sha256:<64 桁 hex>' の形式ではありません",
            )],
            expected,
            actual,
        )

    if expected != actual:
        return (
            [(
                Violation.BODY_HASH_MISMATCH,
                BODY_HASH_FIELD,
                "body_hash が現在の本文と一致しません",
            )],
            expected,
            actual,
        )

    return [], expected, actual


# ---------------------------------------------------------------------------
# 信頼判定（DES-008 §5.1 / §5.3）
# ---------------------------------------------------------------------------

def evaluate(text):
    """文書全体を受け取り信頼判定の結果を返す。

    trust = (doc-advisor ∈ type)
          ∧ (5 フィールドが全て存在し、非空で、スキーマに適合する)
          ∧ (body_hash が存在し、接頭辞が既知で、現在の本文と一致)

    all-or-nothing であり（DES-008 §5.2）、部分利用はしない。
    warn は「type に doc-advisor が含まれるのに trust が偽」のときのみ真とする
    （§5.3）。フロントマターを持たない文書は正常な対象外であり warn しない。

    Args:
        text: 文書全体の文字列

    Returns:
        TrustResult
    """
    parts = split_document(text)

    if not parts.has_frontmatter:
        return TrustResult(
            trust=False,
            has_frontmatter=False,
            has_marker=False,
            warn=False,
            violations=[],
            metadata={},
            expected_body_hash=None,
            actual_body_hash=compute_body_hash(parts.body),
        )

    metadata = parse_frontmatter(parts.frontmatter_text)
    marker = has_marker(metadata)

    violations = list(validate_metadata(metadata))
    hash_violations, expected, actual = check_body_hash(metadata, parts.body)
    violations.extend(hash_violations)

    trust = not violations
    return TrustResult(
        trust=trust,
        has_frontmatter=True,
        has_marker=marker,
        warn=(marker and not trust),
        violations=violations,
        metadata=metadata,
        expected_body_hash=expected,
        actual_body_hash=actual,
    )


def read_text(path):
    """UTF-8 のテキストファイルを読み込む。

    Args:
        path: 対象ファイルパス（str または Path）

    Returns:
        str: ファイル内容

    Raises:
        OSError / UnicodeDecodeError: 読み取りに失敗した場合（呼び出し側が扱う）
    """
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def evaluate_file(path):
    """ファイルを読み込んで evaluate する。

    Args:
        path: 対象ファイルパス（str または Path）

    Returns:
        TrustResult

    Raises:
        OSError / UnicodeDecodeError: 読み取りに失敗した場合
    """
    return evaluate(read_text(path))
