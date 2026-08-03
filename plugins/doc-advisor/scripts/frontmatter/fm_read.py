#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_read.py — フロントマターの読み取りと信頼判定（doc-advisor plugin / frontmatter）

DES-008 §5.1（判定述語）/ §5.3（warning の条件）/ §6.1（独立性の境界）/ §6.2（責務）を
実装する。判定ロジックそのものは fm_core が持ち、本 script は「渡されたパスを 1 件ずつ
評価して DES-005 §8.1 の JSON 契約へ写像する」ことだけを担う。

責務:
- --paths-json で受け取ったパス集合を入力順に評価する
- 個別ファイルの読み取り失敗で全体を落とさず status: partial へ写像する
- type に doc-advisor を含むのに trust が偽の文書だけを warnings に載せる（§5.3）

**対象を自ら探索しない**（DES-008 §6.1 / §10.2）。ディレクトリ走査も、特定ディレクトリの
除外判定も持たない。何を対象にするかは呼び出し側（write-frontmatter SKILL / index-docs
SKILL 等）が決めて渡す。配布先のプロジェクトに存在しないパスの除外判定を script へ焼き
込まないための境界である。

独立性（DES-008 §6.1）:
- toc_store.py / toc_utils.py を import しない。key 解決も store_dir 解決も project root
  解決も行わない。相対パスは cwd 起点で解決し、絶対パスもそのまま受理する
- JSON 出力契約の定数（status / error_code）と emit_json は本 script に独立定義する

CLI:
    python3 fm_read.py --paths-json '["docs/a.md", "docs/b.md"]'

終了コード:
    0: status ok / partial（partial は一部ファイルを読めなかったが判定は得られた状態。
       prepare_toc.py が reject を含む partial で 0 を返すのと同じ扱いにする）
    1: status error（引数不正・--paths-json の形式不正）

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import argparse
import json
import sys

from fm_core import evaluate_file

# ---------------------------------------------------------------------------
# JSON 出力契約（DES-005 §8.1 / §8.2）
#
# toc_store.ErrorCode / STATUS 定数と同形だが、独立性の境界（DES-008 §6.1）により
# frontmatter 側に独立定義する。値はテストで固定する。
# ---------------------------------------------------------------------------


class ErrorCode:
    """本 script が出しうる error_code（DES-005 §8.1 の部分集合）。

    値はすべて DES-005 §8.1 の共通列挙に含まれる。最上位フィールドだけでなく
    rejected_paths[].reason のような入れ子フィールドにも同じ値域が適用されるため、
    共通列挙の外の値を独自に作らない（toc_store.ERROR_CODES との包含をテストで固定）。

    key 解決を行わないため KEY_EMPTY / KEY_RESERVED は持たない。
    NOT_FOUND / READ_ERROR は個々のファイルの失敗理由（rejected_paths[].reason /
    results[].error_code）としてのみ使い、script 全体の成否を表す最上位の
    error_code には使わない。同じ値域の中での使い分けである。
    文書の規約違反は error_code ではなく violations として報告する（別軸）。
    """

    # 最上位の error_code（script 実行の成否）
    INVALID_PATH = "INVALID_PATH"
    UNSUPPORTED_ARG = "UNSUPPORTED_ARG"

    # 個々のファイルの失敗理由
    NOT_FOUND = "NOT_FOUND"
    READ_ERROR = "READ_ERROR"


# error_code の有効値集合（None を含まない）。テスト・バリデーションで参照する。
ERROR_CODES = frozenset({
    ErrorCode.INVALID_PATH,
    ErrorCode.UNSUPPORTED_ARG,
    ErrorCode.NOT_FOUND,
    ErrorCode.READ_ERROR,
})

# status の有効値集合（DES-005 §8.2）。
# needs_confirmation は越境 symlink の承認待ちを表す値であり、path 検証を行わない
# 本 script には到達しないため持たない。
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_ERROR = "error"
STATUSES = frozenset({STATUS_OK, STATUS_PARTIAL, STATUS_ERROR})


def log(message):
    """進捗・診断を stderr へ出す（stdout は単一 JSON 専用 / DES-005 §8.1）。"""
    print(message, file=sys.stderr)


def emit_json(
    status,
    *,
    error_code=None,
    message=None,
    results=None,
    rejected_paths=None,
    counts=None,
    warnings=None,
    stream=None,
):
    """stdout に単一 JSON を出力する（DES-005 §8.1）。

    status / error_code は必須フィールドとして常に出力する（error_code は値が
    無ければ null を明示する）。その他は None でない場合のみ出力する。

    Args:
        status: 'ok' / 'partial' / 'error'
        error_code: ErrorCode のいずれか、または None
        message: human-readable メッセージ
        results: per-file の判定結果の list（入力順）
        rejected_paths: [{path, reason}] の list（読み取れなかったファイル）
        counts: 件数の dict
        warnings: warning 文字列の list
        stream: 出力先（省略時 sys.stdout。テスト用）
    """
    payload = {
        "status": status,
        "error_code": error_code,
    }
    if message is not None:
        payload["message"] = message
    if counts is not None:
        payload["counts"] = counts
    if results is not None:
        payload["results"] = results
    if rejected_paths is not None:
        payload["rejected_paths"] = rejected_paths
    if warnings is not None:
        payload["warnings"] = warnings

    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(payload, ensure_ascii=False))
    out.write("\n")


# ---------------------------------------------------------------------------
# 判定結果 → JSON の写像
# ---------------------------------------------------------------------------

def violations_json(violations):
    """fm_core の violations を JSON 化可能な list へ変換する。

    fm_write も同じ形式で violations を出力するため公開名で共有する（別々に
    実装すると同一の違反が経路によって異なる形で出力される）。

    Args:
        violations: (code, field, detail) のタプルの列

    Returns:
        list: {code, field, detail} の dict の list
    """
    return [
        {"code": code, "field": field, "detail": detail}
        for code, field, detail in violations
    ]


def evaluate_path(path):
    """1 件のパスを評価し、results の要素 1 つ分の dict を返す。

    読み取り失敗（不在・権限・UTF-8 デコード不能）は例外で送出されるため、ここで
    個別に捕捉する。1 件の失敗で全体を落とさないためであり、呼び出し側は返り値の
    error_code が None でないことで失敗を識別する（DES-008 §6.2 / DES-005 §8.1）。

    Args:
        path: 対象パス（相対パスは cwd 起点で解決される）

    Returns:
        dict: path / trust / error_code を必ず含む判定結果
    """
    try:
        result = evaluate_file(path)
    except FileNotFoundError as e:
        return {
            "path": path,
            "trust": False,
            "error_code": ErrorCode.NOT_FOUND,
            "detail": str(e),
        }
    except (OSError, UnicodeDecodeError) as e:
        return {
            "path": path,
            "trust": False,
            "error_code": ErrorCode.READ_ERROR,
            "detail": f"{e.__class__.__name__}: {e}",
        }

    return {
        "path": path,
        "trust": result.trust,
        "error_code": None,
        "has_frontmatter": result.has_frontmatter,
        "has_marker": result.has_marker,
        "warn": result.warn,
        "violations": violations_json(result.violations),
        "expected_body_hash": result.expected_body_hash,
        "actual_body_hash": result.actual_body_hash,
    }


def build_report(paths):
    """パス集合を評価し、JSON 出力に必要な各要素を組み立てる。

    warnings に載せるのは `warn` が真の文書だけである（DES-008 §5.3）。
    フロントマターを持たない文書は正常な対象外であり warning を出さない。

    対象 0 件は error にしない（DES-005 §9.2）。空の results と status ok を返す。

    Args:
        paths: 対象パスの list（入力順を保つ）

    Returns:
        tuple: (status, results, rejected_paths, counts, warnings)
    """
    results = [evaluate_path(path) for path in paths]

    rejected_paths = [
        {"path": item["path"], "reason": item["error_code"]}
        for item in results
        if item["error_code"] is not None
    ]

    warnings = []
    for item in results:
        if not item.get("warn"):
            continue
        codes = ", ".join(v["code"] for v in item["violations"])
        warnings.append(
            f"frontmatter has the doc-advisor marker but is not trustworthy: "
            f"{item['path']} ({codes})"
        )

    counts = {
        "total": len(results),
        "trusted": sum(1 for item in results if item["trust"]),
        "untrusted": sum(
            1 for item in results if not item["trust"] and item["error_code"] is None
        ),
        "unreadable": len(rejected_paths),
        "warned": len(warnings),
    }

    # 読み取れなかったファイルがあっても、他のファイルの判定は返す（partial）
    status = STATUS_PARTIAL if rejected_paths else STATUS_OK
    return status, results, rejected_paths, counts, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class ArgError(Exception):
    """引数の解析エラー（未知引数・値不足・必須引数の欠落）。

    argparse の既定動作（stderr へ usage を出し exit code 2 で終了）は、
    「常に単一 JSON を stdout へ出す」契約（DES-005 §8.1）を破るため、例外へ
    変換して main で JSON 化する。
    """


class _JsonArgumentParser(argparse.ArgumentParser):
    """SystemExit せず ArgError を送出する ArgumentParser。

    status によらず常に ArgError にする。`add_help=False` としているため
    「JSON 以外を stdout へ出して正常終了する」経路（help）は存在せず、ここへ
    到達するのは常に引数の解析失敗である。
    """

    def error(self, message):  # noqa: D102 - argparse の契約を上書きする
        raise ArgError(message)

    def exit(self, status=0, message=None):  # noqa: D102
        raise ArgError(message or "引数の解析に失敗しました")


def parse_args(argv=None):
    """引数を解析する。解析できない場合は ArgError を送出する。

    Args:
        argv: 引数列（省略時 sys.argv[1:]）

    Returns:
        argparse.Namespace

    Raises:
        ArgError: 未知引数・値不足・--paths-json の欠落
    """
    # add_help=False: 自動追加される --help は help テキストを stdout へ出して
    # exit 0 するため、「最終出力は script の JSON のみ」を破る。無効化して未知引数と
    # 同じ経路に乗せる。利用方法は本 docstring と DES-008 に記述する。
    parser = _JsonArgumentParser(
        description="渡された Markdown のフロントマターを信頼判定して JSON 出力する",
        add_help=False,
    )
    parser.add_argument(
        "--paths-json",
        dest="paths_json",
        required=True,
        help="対象パスの JSON 配列。相対パスは cwd 起点で解決する（必須）",
    )
    return parser.parse_args(argv)


def parse_paths_json(raw):
    """--paths-json を文字列の list へ変換する。

    Args:
        raw: --paths-json に渡された文字列

    Returns:
        list: パス文字列の list

    Raises:
        ValueError: JSON として解析できない / 配列でない / 要素が非空文字列でない
    """
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"--paths-json を JSON として解析できません: {e}")

    if not isinstance(value, list):
        raise ValueError("--paths-json は JSON 配列である必要があります")

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("--paths-json の要素は非空の文字列である必要があります")

    return list(value)


def main(argv=None):
    # 0. 引数解析（未知引数・値不足は JSON へ正規化する）
    try:
        args = parse_args(argv)
    except ArgError as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.UNSUPPORTED_ARG,
            message=str(e),
        )
        return 1

    # 1. --paths-json の形式検証（引数そのものの不正は script 全体の error）
    try:
        paths = parse_paths_json(args.paths_json)
    except ValueError as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.INVALID_PATH,
            message=str(e),
        )
        return 1

    # 2. 入力順に 1 件ずつ判定する（対象 0 件は error ではない / DES-005 §9.2）
    status, results, rejected_paths, counts, warnings = build_report(paths)

    for item in rejected_paths:
        log(f"skip (unreadable): {item['path']} [{item['reason']}]")

    emit_json(
        status,
        error_code=None,
        counts=counts,
        results=results,
        rejected_paths=rejected_paths,
        warnings=warnings,
    )
    # partial は「一部を読めなかったが判定は得られた」状態であり処理は続行されている。
    # prepare_toc.py が reject を含む partial で 0 を返すのと揃える。
    return 0


if __name__ == "__main__":
    sys.exit(main())
