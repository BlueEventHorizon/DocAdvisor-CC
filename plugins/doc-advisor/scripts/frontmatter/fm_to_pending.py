#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_to_pending.py — 信頼できるフロントマターを pending YAML へ転記する
（doc-advisor plugin / frontmatter）

DES-008 §5.1（判定述語）/ §5.3（warning の条件）/ §6.1（配置と独立性の境界）/
§6.2（責務）を実装する。判定ロジックは fm_core が持ち、本 script は
「渡された work-dir 直下の pending を列挙し、信頼できるものだけを in-place で
status: completed へ書き直す」ことだけを担う。

責務:
- --work-dir 直下の pending を決定論的順序で列挙する
- 各 pending の _meta.source_file が指す文書を fm_core で判定する
- 信頼できるものはその pending を completed として原子的に書き直す
- 信頼できないもの・読めないものは pending を**バイト単位で無変更のまま残す**
  （AI 抽出の対象として prepare の出力を壊さない）

pending の**形式は知るが、置き場所は知らない**（DES-008 §6.1）。key 解決も
store_dir 解決も project root 解決も行わない。処理対象のディレクトリ
（store_dir/.toc_work/ そのもの）は呼び出し側が決めて渡す。

列挙規則は merge_toc.load_completed_pendings と揃える（`*.yaml` かつ先頭 '.'
以外、sorted）。隠しファイル（.toc_checksums_pending.yaml / .deleted.json 等）は
pending ではないため対象外である。転記した pending をそのまま読む相手が merge
であり、列挙集合が食い違うと「転記したのに merge が拾わない」または逆が起きる。

出力する pending の書式は write_pending.write_entry_yaml の出力と**バイト一致**
させる（同一 work-dir に AI 抽出由来と転記由来が混在するため、書式が揺れると
merge 側の読み取りに 2 系統の入力を作ってしまう）。バイト一致はテストで固定する。

独立性（DES-008 §6.1）:
- toc_store.py / toc_utils.py を import しない。したがって pending の読み取りに
  toc_utils.parse_simple_yaml は使えず、_meta 配下を読む最小のリーダを本 script に
  持つ。必要なのは source_file と status の 2 つだけであり、本文フィールドは読む
  必要がない（転記はフロントマター由来の新しい内容で書き直すため）
- fm_core.parse_frontmatter は最上位キーのみを解析しインデント行を無視するため
  _meta 配下を読めない。流用せず本 script のリーダで読む
- JSON 出力契約（status / error_code / emit_json / log）と引数解析の骨格、および
  原子的書き込みは同一ディレクトリの fm_read / fm_write から import して共有する
  （§6.1 が禁じているのは toc_store / toc_utils の import であり、frontmatter
  内部の共有は二重実装を避けるために行う）

CLI:
    python3 fm_to_pending.py --work-dir ".claude/.doc-advisor/toc/<slug>/.toc_work"

--work-dir の扱い:
- 渡されるのは .toc_work/ ディレクトリそのもの。その直下のみを見る
  （サブディレクトリを再帰しない）
- 存在しない場合は 0 件として status ok を返す。merge_toc.load_completed_pendings が
  work_dir 不在で空を返すのと揃える（prepare が対象 0 件で work_dir を作らない場合に、
  呼び出し側の手順を止めないため）

終了コード:
    0: status ok / partial（partial は一部 pending の処理に失敗した状態。他の
       pending の処理は完了している。fm_read / fm_write が partial で 0 を返すのと揃える）
    1: status error（引数不正）

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from fm_core import (
    LIST_FIELDS,
    STRING_FIELDS,
    evaluate,
    read_text,
    yaml_escape,
    unquote_yaml_value,
)
from fm_read import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PARTIAL,
    ArgError,
    ErrorCode,
    _JsonArgumentParser,
    emit_json,
    log,
)
from fm_write import write_text_atomic

# pending の _meta セクションのキー名（formats/toc_format.md の Intermediate File Schema）
META_KEY = "_meta"
SOURCE_FILE_KEY = "source_file"
STATUS_KEY = "status"

# _meta.status の値域（同上）
PENDING_STATUS = "pending"
COMPLETED_STATUS = "completed"

# results[].action の値域。ok（成否）とは別軸で「pending をどう扱ったか」を表す
ACTION_TRANSCRIBED = "transcribed"
ACTION_LEFT_PENDING = "left_pending"
ACTION_ALREADY_COMPLETED = "already_completed"
ACTION_FAILED = "failed"

ACTIONS = frozenset({
    ACTION_TRANSCRIBED,
    ACTION_LEFT_PENDING,
    ACTION_ALREADY_COMPLETED,
    ACTION_FAILED,
})


# ---------------------------------------------------------------------------
# pending の列挙（merge_toc.load_completed_pendings と同一規則）
# ---------------------------------------------------------------------------

def list_pendings(work_dir):
    """work_dir 直下の pending ファイルを決定論的順序で列挙する。

    merge_toc.load_completed_pendings と同一の規則を用いる（`*.yaml` かつ
    先頭 '.' 以外、sorted）。列挙集合が食い違うと、転記した pending を merge が
    拾わない（あるいは merge が拾うものを転記が見ない）状態が生まれる。

    Args:
        work_dir: .toc_work/ ディレクトリのパス（str または Path）

    Returns:
        list: Path の list（パス昇順）。ディレクトリが無ければ空 list
    """
    work_dir = Path(work_dir)
    if not work_dir.is_dir():
        return []
    return sorted(
        path for path in work_dir.glob("*.yaml") if not path.name.startswith(".")
    )


# ---------------------------------------------------------------------------
# pending の読み取り（_meta 配下の最小リーダ）
# ---------------------------------------------------------------------------

def read_pending_meta(text):
    """pending YAML の _meta 配下から `key: value` を読む。

    必要なのは source_file と status の 2 つだけであり、本文フィールド
    （title / purpose / 3 配列）は読まない。転記はフロントマター由来の新しい
    内容で pending 全体を書き直すため、既存の本文フィールドを引き継がない。

    toc_utils.parse_simple_yaml は import できず（DES-008 §6.1）、
    fm_core.parse_frontmatter は最上位キーのみを解析してインデント行を無視する
    ため _meta 配下が読めない。よって本 script で最小のリーダを持つ。

    値の引用符除去は fm_core.unquote_yaml_value に委ねる。write_pending.py が
    yaml_escape で書いた値と往復一致する必要があり、その逆変換を 3 つ目の
    実装として作らないためである（fm_core と同一パッケージ内の共有）。

    Args:
        text: pending YAML の全文

    Returns:
        dict: _meta 配下のキー → 値（文字列）。_meta が無ければ空 dict
    """
    meta = {}
    in_meta = False

    for line in text.split("\n"):
        if not line.strip():
            continue

        # 最上位キー行（インデントなし）でセクションが切り替わる
        if not line[:1].isspace():
            in_meta = line.partition(":")[0].strip() == META_KEY
            continue

        if not in_meta:
            continue

        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("- ") or ":" not in stripped:
            continue

        key, _, value = stripped.partition(":")
        meta[key.strip()] = unquote_yaml_value(value.strip())

    return meta


# ---------------------------------------------------------------------------
# pending の書き込み（write_pending.write_entry_yaml とバイト一致）
# ---------------------------------------------------------------------------

def utc_timestamp():
    """_meta.updated_at に書く現在時刻を返す。

    形式は write_pending.py と同一（ISO 8601 の UTC、秒精度、末尾 'Z'）。

    Returns:
        str: 例 '2026-08-02T12:34:56Z'
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_pending_text(source_file, metadata, updated_at):
    """completed 状態の pending YAML 全文を組み立てる。

    write_pending.write_entry_yaml の出力と**バイト一致**させる:
    - _meta は source_file（yaml_escape 適用）/ status: completed /
      updated_at（生値）の 3 キー、インデント 2 スペース
    - _meta ブロックの直後に空行 1 行
    - title / purpose はスカラ（yaml_escape 適用）
    - content_details / applicable_tasks / keywords はブロック配列
      （各要素に yaml_escape 適用）。要素 0 件でもキー行だけ出る
    - 末尾改行はちょうど 1 つ

    claimed_at / error_message は書かない（_meta を作り直すため。
    write_pending.py が completed 時に _meta を再構築するのと同じ扱い）。

    Args:
        source_file: 転記元文書のパス（pending から読んだ値をそのまま使う）
        metadata: フロントマター由来のメタデータ dict
        updated_at: _meta.updated_at に書く値（生値で出力する）

    Returns:
        str: pending YAML の全文
    """
    lines = [META_KEY + ":"]
    lines.append(f"  {SOURCE_FILE_KEY}: {yaml_escape(source_file)}")
    lines.append(f"  {STATUS_KEY}: {COMPLETED_STATUS}")
    lines.append(f"  updated_at: {updated_at}")
    lines.append("")

    for field in STRING_FIELDS:
        lines.append(f"{field}: {yaml_escape(metadata.get(field, ''))}")

    for field in LIST_FIELDS:
        lines.append(f"{field}:")
        for item in metadata.get(field) or []:
            lines.append(f"  - {yaml_escape(item)}")

    lines.append("")  # 末尾改行
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# per-pending の処理
# ---------------------------------------------------------------------------

def _result(pending, *, ok, action, source_file=None, error_code=None, detail=None,
            trust=None, warn=False, violations=None):
    """results の要素 1 つ分の dict を組み立てる。

    Args:
        pending: pending ファイルのパス（文字列）
        ok: 処理が成功したか（**失敗判定はこの値で行う**。error_code は
            DES-005 §8.1 の共通列挙で表せる失敗にのみ入る）
        action: pending をどう扱ったか（ACTIONS のいずれか）
        source_file: 転記元文書のパス（読めた場合）
        error_code: ErrorCode のいずれか、または None
        detail: 失敗・スキップの理由（該当しない場合は None）
        trust: 信頼判定の結果（判定に到達しなかった場合は None）
        warn: type に doc-advisor を含むのに trust が偽か（DES-008 §5.3）
        violations: 検出した違反コードの list

    Returns:
        dict
    """
    return {
        "pending": pending,
        "source_file": source_file,
        "ok": ok,
        "action": action,
        "error_code": error_code,
        "detail": detail,
        "trust": trust,
        "warn": warn,
        "violations": list(violations or []),
    }


def process_pending(path, *, updated_at=None):
    """pending 1 件を判定し、信頼できる場合のみ completed へ書き直す。

    信頼できない場合・読めない場合は pending を**一切変更しない**。prepare が
    作った pending をそのまま残すことで、後続の AI 抽出（toc-updater Agent）が
    従来どおり処理できる状態を保つ。

    既に status: completed の pending は再処理しない。write_pending.py が
    --force なしで completed を拒否するのと同じ扱いである。

    Args:
        path: pending ファイルのパス（str または Path）
        updated_at: _meta.updated_at に書く値（省略時は現在時刻）

    Returns:
        dict: results の要素 1 つ分
    """
    path = Path(path)
    name = str(path)

    # 1. pending を読む
    try:
        pending_text = read_text(path)
    except (OSError, UnicodeDecodeError) as e:
        return _result(name, ok=False, action=ACTION_FAILED,
                       error_code=ErrorCode.READ_ERROR,
                       detail=f"{e.__class__.__name__}: {e}")

    meta = read_pending_meta(pending_text)
    source_file = meta.get(SOURCE_FILE_KEY)
    status = meta.get(STATUS_KEY)

    # 2. source_file が無い pending は転記できない。壊さず残す
    #    （merge_toc が warnings に載せてスキップするのと整合する扱い）
    if not source_file:
        return _result(name, ok=False, action=ACTION_FAILED,
                       detail=f"missing {META_KEY}.{SOURCE_FILE_KEY}")

    # 3. 既に completed のものは再処理しない
    if status == COMPLETED_STATUS:
        return _result(name, ok=True, action=ACTION_ALREADY_COMPLETED,
                       source_file=source_file,
                       detail=f"{STATUS_KEY} is already {COMPLETED_STATUS}")

    # 4. source_file が指す文書を判定する（相対パスは cwd 起点。project root の
    #    解決は行わない / DES-008 §6.1）
    try:
        document_text = read_text(source_file)
    except FileNotFoundError as e:
        return _result(name, ok=False, action=ACTION_FAILED,
                       source_file=source_file,
                       error_code=ErrorCode.NOT_FOUND, detail=str(e))
    except (OSError, UnicodeDecodeError) as e:
        return _result(name, ok=False, action=ACTION_FAILED,
                       source_file=source_file,
                       error_code=ErrorCode.READ_ERROR,
                       detail=f"{e.__class__.__name__}: {e}")

    result = evaluate(document_text)
    violations = [code for code, _field, _detail in result.violations]

    # 5. 信頼できないものは pending を無変更で残す（AI 抽出へ）
    if not result.trust:
        return _result(name, ok=True, action=ACTION_LEFT_PENDING,
                       source_file=source_file, trust=False,
                       warn=result.warn, violations=violations,
                       detail="frontmatter is not trustworthy")

    # 6. 転記（原子的書き込み。中間状態の pending が merge に拾われると
    #    validate_toc を落としうるため / 戦略書 R2）
    text = build_pending_text(
        source_file, result.metadata,
        updated_at if updated_at is not None else utc_timestamp(),
    )
    try:
        write_text_atomic(str(path), text)
    except OSError as e:
        return _result(name, ok=False, action=ACTION_FAILED,
                       source_file=source_file, trust=True,
                       detail=f"書き込みに失敗しました: {e.__class__.__name__}: {e}")

    return _result(name, ok=True, action=ACTION_TRANSCRIBED,
                   source_file=source_file, trust=True)


def process_work_dir(work_dir, *, updated_at=None):
    """work_dir 直下の pending を一括処理する。

    個別 pending の失敗は 1 件で全体を落とさず status: partial へ写像する
    （error は引数自体が不正な場合に限る / DES-008 §6.2）。対象 0 件は
    error にしない（DES-005 §9.2）。

    warnings に載せるのは、type に doc-advisor を含むのに trust が偽だった
    文書だけである（DES-008 §5.3）。フロントマターを持たない文書は正常な
    対象外であり warning を出さない。

    Args:
        work_dir: .toc_work/ ディレクトリのパス
        updated_at: _meta.updated_at に書く値（省略時は現在時刻）

    Returns:
        tuple: (status, results, counts, warnings)
    """
    pendings = list_pendings(work_dir)
    results = [process_pending(path, updated_at=updated_at) for path in pendings]

    warnings = []
    for item in results:
        if not item["warn"]:
            continue
        codes = ", ".join(item["violations"])
        warnings.append(
            f"frontmatter has the doc-advisor marker but is not trustworthy: "
            f"{item['source_file']} ({codes})"
        )
    def _count(action):
        return sum(1 for item in results if item["action"] == action)

    counts = {
        "total": len(results),
        "transcribed": _count(ACTION_TRANSCRIBED),
        "left_pending": _count(ACTION_LEFT_PENDING),
        "already_completed": _count(ACTION_ALREADY_COMPLETED),
        "failed": _count(ACTION_FAILED),
        "warned": sum(1 for item in results if item["warn"]),
    }

    status = STATUS_PARTIAL if counts["failed"] else STATUS_OK
    return status, results, counts, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """引数を解析する。解析できない場合は ArgError を送出する。

    Args:
        argv: 引数列（省略時 sys.argv[1:]）

    Returns:
        argparse.Namespace

    Raises:
        ArgError: 未知引数・値不足・--work-dir の欠落
    """
    # add_help=False の理由は fm_read.parse_args と同じ（help が JSON 以外を
    # stdout へ出して exit 0 する経路を作らないため）。利用方法は本 script の
    # docstring と DES-008 に記述する。
    parser = _JsonArgumentParser(
        description=(
            "work-dir 直下の pending を判定し、信頼できるフロントマターを "
            "completed として転記する"
        ),
        add_help=False,
    )
    parser.add_argument(
        "--work-dir",
        dest="work_dir",
        required=True,
        help=".toc_work/ ディレクトリのパス。相対パスは cwd 起点で解決する（必須）",
    )
    return parser.parse_args(argv)


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

    work_dir = args.work_dir
    if not work_dir.strip():
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.INVALID_PATH,
            message="--work-dir が空です",
        )
        return 1

    # 1. 一括処理（work_dir 不在は 0 件として扱う。merge_toc と揃える）
    message = None
    if not Path(work_dir).is_dir():
        message = f"work-dir が存在しません（0 件として扱います）: {work_dir}"
        log(message)

    status, results, counts, warnings = process_work_dir(work_dir)

    for item in results:
        if item["action"] == ACTION_FAILED:
            log(f"skip (failed): {item['pending']} - {item['detail']}")
        elif item["action"] == ACTION_LEFT_PENDING:
            log(f"left pending: {item['source_file']}")

    emit_json(
        status,
        error_code=None,
        message=message,
        counts=counts,
        results=results,
        warnings=warnings,
    )
    # partial は「一部 pending の処理に失敗したが他は完了した」状態であり処理は
    # 続行されている。fm_read / fm_write が partial で 0 を返すのと揃える。
    return 0


if __name__ == "__main__":
    sys.exit(main())
