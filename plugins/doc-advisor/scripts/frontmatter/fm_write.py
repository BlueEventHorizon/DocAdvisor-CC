#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_write.py — フロントマターへのマージ書き込みと body_hash の打刻
（doc-advisor plugin / frontmatter）

DES-008 §4.2（打刻タイミング）/ §4.5（マージ規則）/ §6.1（独立性の境界）/
§6.2（責務）/ §6.3（整形コマンド）を実装する。マージそのものの規則は fm_core が
持ち、本 script は「渡されたメタデータを原子的に書き込み、整形の不動点で
body_hash を打刻し、per-file の結果を JSON へ写像する」ことだけを担う。

責務:
- --entries-json で受け取った (path, metadata) を入力順に処理する
- 原子的書き込み（一時ファイル + os.replace）で原本の破損を防ぐ
- --format-command が指定された場合のみ整形器を呼ぶ（未指定なら呼ばない）
- 整形の**後**に body_hash を計算・打刻する（§4.2）
- 個別 entry の失敗で全体を落とさず status: partial へ写像する

**対象を自ら探索しない**（DES-008 §6.1 / §10.2）。ディレクトリ走査も、特定
ディレクトリの除外判定も持たない。何を対象にするかは呼び出し側
（write-frontmatter SKILL 等）が決めて渡す。

処理順序（DES-008 §4.2）[MANDATORY]:
    1. 対象を読む
    2. merge_frontmatter(text, metadata) — **body_hash を含めない**
    3. 原子的に書き込む
    4. --format-command が指定されていれば実行する（未指定ならスキップ）
    5. 再読込して本文から body_hash を算出する
    6. merge_frontmatter(text2, {'body_hash': h}) — **body_hash 単独**
    7. 原子的に書き込む

打刻を整形の後に置くのは、整形が本文のバイト列を変えるためである。逆順にすると
打刻直後に全ハッシュが無効化され、全件が AI 再抽出へ落ちる（§4.2 / §6.3）。
本文ハッシュは本文のみを対象とするため、打刻後にフロントマターが整形されても
ハッシュは有効なままである。

独立性（DES-008 §6.1）:
- toc_store.py / toc_utils.py を import しない。key 解決も store_dir 解決も行わない
- JSON 出力契約（status / error_code / emit_json / log）と引数解析の骨格は
  同一ディレクトリの fm_read から import して共有する（§6.1 が禁じているのは
  toc_store / toc_utils の import であり、frontmatter 内部の共有は二重実装を
  避けるために行う）

CLI:
    python3 fm_write.py --entries-json '[{"path": "docs/a.md",
                                          "metadata": {"title": "...", ...}}]'
                        [--format-command "dprint fmt {file}"]

--entries-json の形式:
- JSON 配列。要素は {"path": <非空文字列>, "metadata": <object>} の dict
- 要素のキーは path / metadata のみ（metadata は省略可）
- 構造の不正（配列でない・要素が dict でない・path が非空文字列でない・
  metadata が object でない・未知キー）は **引数自体の不正**であり
  status: error（error_code: INVALID_PATH）として全体を落とす

metadata の値域:
- キーは fm_core.DOC_ADVISOR_FIELDS のうち body_hash を除いたもの
  （type / title / purpose / content_details / applicable_tasks / keywords）
- body_hash は本 script が整形後に算出して打刻するため、呼び出し側からは渡せない
- 値は文字列、または文字列の配列
- DES-008 §5.1 の上限（purpose 200 文字・配列 1〜10 件）は検証しない。部分更新
  （一部のキーのみ差し替え）を許すため必須フィールドの充足も要求しない。
  書き込んだ結果が信頼できるかの判定は fm_read が担う（責務の分離）

整形コマンド（DES-008 §6.3 / 戦略書 R5）:
- shlex.split でトークン化し subprocess.run(shell=False) で実行する
- 置換するプレースホルダは {file} のみ。他のプレースホルダは展開しない
- {file} を含まないコマンドは受け付けない（対象ファイル以外を書き換える恐れが
  あるため）。status: error（UNSUPPORTED_ARG）とする
- timeout は設けない（配布物内に前例がなく、妥当な値の根拠も無いため）
- 非ゼロ終了は当該 entry の失敗とし、その文書には打刻しない。加えて手順 3 の
  書き込みを取り消して元の内容へ戻す。打刻に到達しなかった entry を信頼できる
  状態のまま残さないためである（rollback の docstring 参照）。結果としてその
  文書は fm_write を実行する前と同じ状態になり、新規付与であれば trust は偽の
  ままで AI 抽出へフォールバックする（戦略書 R4 の「帰結は現行挙動への復帰」と整合）
- 設定ファイルからコマンドを読まない（§6.3 の CLI 引数受け取りを厳守）

error_code の値域:
DES-005 §8.1 の共通列挙に含まれる値のみを使う（共通列挙の外の値を独自に作らない）。
共通列挙で表せない失敗（未閉鎖フロントマター・整形コマンドの失敗・書き込み失敗）は
error_code を null とし、results[].ok を偽にして detail に理由を書く。したがって
**entry の失敗判定は error_code ではなく ok で行う**。

終了コード:
    0: status ok / partial（partial は一部 entry が失敗した状態。他の entry の
       処理は完了している。fm_read が partial で 0 を返すのと揃える）
    1: status error（引数不正）

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

from fm_core import (
    BODY_HASH_FIELD,
    DOC_ADVISOR_FIELDS,
    FrontmatterWriteError,
    compute_body_hash,
    merge_frontmatter,
    read_text,
    split_document,
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

# 整形コマンド内で対象ファイルパスへ置換される唯一のプレースホルダ（DES-008 §6.3）
FORMAT_PLACEHOLDER = "{file}"

# metadata として受け取れるキー（body_hash は本 script が算出するため除く）
WRITABLE_FIELDS = tuple(
    field for field in DOC_ADVISOR_FIELDS if field != BODY_HASH_FIELD
)

# --entries-json の各要素が持てるキー
ENTRY_KEYS = frozenset({"path", "metadata"})


# ---------------------------------------------------------------------------
# 原子的書き込み（merge_toc.write_toc_atomic の様式を踏襲）
# ---------------------------------------------------------------------------

def write_text_atomic(path, text):
    """テキストを原子的にファイルへ書き込む。

    一時ファイルへ書いてから os.replace で置換する。途中で失敗しても原本が
    壊れた中間状態にならないことが目的である（原本 Markdown の破損は致命的
    であるため、write_pending.py の素朴な直書きは踏襲しない）。

    既存ファイルのパーミッションは維持する。mkstemp が作る一時ファイルは
    0600 であり、そのまま置換すると原本の権限を落としてしまう。

    Args:
        path: 書き込み先のパス（str）
        text: 書き込む内容

    Raises:
        OSError: 一時ファイルの作成・書き込み・置換に失敗した場合
    """
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp", prefix=".fm_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if os.path.exists(path):
            shutil.copymode(path, tmp_path)
        os.replace(tmp_path, path)
    finally:
        # os.replace が成功していれば tmp_path は既に存在しない。失敗した場合に
        # 限り後始末する。finally で行うことで、捕捉範囲を広げずに（例外型を
        # 問わずに）一時ファイルの残存を防ぐ（COMMON-REQ-002 FR-01）。
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 整形コマンド（DES-008 §6.3 / 戦略書 R5）
# ---------------------------------------------------------------------------

def validate_format_command(command):
    """--format-command をトークン化して受理可能か検証する。

    Args:
        command: --format-command に渡された文字列

    Returns:
        list: shlex.split したトークン列（{file} は未置換）

    Raises:
        ValueError: トークン化できない / 空 / {file} を含まない場合
    """
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        raise ValueError(f"--format-command を解析できません: {e}")

    if not tokens:
        raise ValueError("--format-command が空です")

    if not any(FORMAT_PLACEHOLDER in token for token in tokens):
        raise ValueError(
            f"--format-command は {FORMAT_PLACEHOLDER} を含む必要があります"
            "（対象ファイル以外を書き換える恐れがあるため）"
        )

    return tokens


def build_format_argv(command, path):
    """整形コマンドの実引数列を組み立てる。

    {file} のみを対象ファイルパスへ置換する。他のプレースホルダは展開しない。
    シェルを介さないため、リダイレクトやコマンド連結の記号は単なる引数として
    渡り、解釈されない（戦略書 R5）。

    Args:
        command: --format-command に渡された文字列
        path: 対象ファイルパス

    Returns:
        list: subprocess.run に渡す引数列

    Raises:
        ValueError: validate_format_command と同じ条件
    """
    tokens = validate_format_command(command)
    return [token.replace(FORMAT_PLACEHOLDER, path) for token in tokens]


def run_format_command(command, path):
    """整形コマンドを実行する。

    timeout は設けない（DES-008 §6.3 の運用に対して妥当な値の根拠が無く、
    配布物内に前例も無いため）。

    Args:
        command: --format-command に渡された文字列
        path: 対象ファイルパス

    Returns:
        subprocess.CompletedProcess

    Raises:
        ValueError: コマンドの形式が不正な場合
        OSError: コマンドを起動できなかった場合
    """
    argv = build_format_argv(command, path)
    return subprocess.run(argv, shell=False, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# metadata の検証
# ---------------------------------------------------------------------------

def validate_metadata_argument(metadata):
    """metadata が書き込み可能な形かを検証する。

    キーの所有権判定は merge_frontmatter も行うが、body_hash は
    DOC_ADVISOR_FIELDS に含まれるため向こうでは弾かれない。打刻は本 script の
    責務であり呼び出し側から渡させないため、ここで明示的に拒否する。

    Args:
        metadata: --entries-json の各要素の metadata（None 可）

    Raises:
        ValueError: キーまたは値の形が不正な場合
    """
    for key, value in (metadata or {}).items():
        if key == BODY_HASH_FIELD:
            raise ValueError(
                f"{BODY_HASH_FIELD} は整形後に本 script が算出するため metadata "
                "では渡せません"
            )
        if key not in WRITABLE_FIELDS:
            raise ValueError(f"doc-advisor が所有しないキーは書き込めません: {key}")
        if isinstance(value, str):
            continue
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            continue
        raise ValueError(
            f"{key} の値は文字列または文字列の配列である必要があります"
        )


# ---------------------------------------------------------------------------
# per-entry の処理
# ---------------------------------------------------------------------------

def _result(path, *, ok, error_code=None, detail=None, changed=False,
            formatted=False, body_hash=None):
    """results の要素 1 つ分の dict を組み立てる。

    Args:
        path: 対象パス
        ok: entry が成功したか（**失敗判定はこの値で行う**。error_code は
            DES-005 §8.1 の共通列挙で表せる失敗にのみ入る）
        error_code: ErrorCode のいずれか、または None
        detail: 失敗理由（成功時は None）
        changed: ファイル内容を変更したか（冪等性の観測用）
        formatted: 整形コマンドを実行し成功したか
        body_hash: 打刻した body_hash（失敗時は None）

    Returns:
        dict
    """
    return {
        "path": path,
        "ok": ok,
        "error_code": error_code,
        "detail": detail,
        "changed": changed,
        "formatted": formatted,
        "body_hash": body_hash,
    }


def rollback(path, original_text):
    """打刻まで到達しなかった entry を、書き込み前の内容へ戻す。

    手順 3 でメタデータを書いた後に整形や打刻が失敗すると、メタデータだけが
    更新され body_hash は打刻されていない中間状態が残る。この状態は放置できない。
    元の文書が既に body_hash を持っていた場合、その値はマージ規則（指定された
    キーだけを差し替える）により残っており、整形器が本文を変えていなければ
    依然として本文と一致する。すると fm_read は trust 真と判定し、失敗を報告した
    はずの entry が転記対象になってしまう（DES-008 §6.3 の意図に反する）。

    書き込み前へ戻すことで、失敗した entry は「何も起きなかった」状態になる。

    Args:
        path: 対象ファイルパス
        original_text: 手順 1 で読み取った書き込み前の内容

    Returns:
        str: 復元に失敗した場合の理由。復元が成功したか不要だった場合は None
    """
    try:
        current = read_text(path)
    except (OSError, UnicodeDecodeError) as e:
        return f"復元前の読み取りに失敗しました: {e.__class__.__name__}: {e}"
    if current == original_text:
        return None
    try:
        write_text_atomic(path, original_text)
    except OSError as e:
        return f"復元に失敗しました: {e.__class__.__name__}: {e}"
    return None


def _failed_after_write(path, original_text, detail, error_code=None,
                        formatted=False):
    """手順 3 以降で失敗した entry の結果を、ロールバックしたうえで組み立てる。

    復元が成功すれば原本は実行前と同一になるため changed は偽である。復元に
    失敗した場合は手順 3 または整形器による変更が残っていることが確定するため、
    changed を真として返す。観測値が実際のファイル状態と食い違うと、呼び出し側は
    「失敗したが原本は無傷」と誤って判断してしまう。

    Args:
        path: 対象ファイルパス
        original_text: 書き込み前の内容
        detail: 失敗理由
        error_code: 共通契約の error_code（該当するものがある場合）
        formatted: 整形コマンドが成功していたか

    Returns:
        dict: results の要素 1 つ分
    """
    rollback_error = rollback(path, original_text)
    if rollback_error is not None:
        return _result(path, ok=False, error_code=error_code,
                       detail=f"{detail} / {rollback_error}",
                       changed=True, formatted=formatted)
    return _result(path, ok=False, error_code=error_code, detail=detail,
                   changed=False, formatted=formatted)


def write_entry(path, metadata=None, format_command=None):
    """1 件の文書へメタデータを書き込み、整形後に body_hash を打刻する。

    処理順序は DES-008 §4.2 の規定どおり（本モジュールの docstring 参照）。
    内容が変わらない場合は書き込みを省略する（不要な mtime の更新を避ける）。
    2 回目以降の適用で内容が変化しないこと（冪等）は、この省略に依らず
    merge_frontmatter と body_hash 算出が冪等であることによって成立する。

    手順 3 の書き込み後に整形や打刻が失敗した場合は、書き込み前の内容へ戻す
    （rollback の docstring 参照）。打刻に到達しなかった entry が信頼できる
    状態のまま残らないようにするためである。

    Args:
        path: 対象ファイルパス
        metadata: 書き込むメタデータの dict（省略可。省略時は type の和集合更新のみ）
        format_command: 整形コマンド（省略時は整形しない / DES-008 §6.3）

    Returns:
        dict: results の要素 1 つ分
    """
    try:
        validate_metadata_argument(metadata)
    except ValueError as e:
        return _result(path, ok=False, error_code=ErrorCode.UNSUPPORTED_ARG,
                       detail=str(e))

    # 1. 読む
    try:
        text = read_text(path)
    except FileNotFoundError as e:
        return _result(path, ok=False, error_code=ErrorCode.NOT_FOUND, detail=str(e))
    except (OSError, UnicodeDecodeError) as e:
        return _result(path, ok=False, error_code=ErrorCode.READ_ERROR,
                       detail=f"{e.__class__.__name__}: {e}")

    # 2. マージ（body_hash は含めない）
    try:
        merged = merge_frontmatter(text, metadata)
    except FrontmatterWriteError as e:
        return _result(path, ok=False, detail=str(e))
    except ValueError as e:
        return _result(path, ok=False, error_code=ErrorCode.UNSUPPORTED_ARG,
                       detail=str(e))

    # 3. 原子的に書き込む
    changed = False
    if merged != text:
        try:
            write_text_atomic(path, merged)
        except OSError as e:
            return _result(path, ok=False,
                           detail=f"書き込みに失敗しました: {e.__class__.__name__}: {e}")
        changed = True

    # 4. 整形（未指定ならスキップ）
    formatted = False
    if format_command:
        try:
            completed = run_format_command(format_command, path)
        except (ValueError, OSError) as e:
            return _failed_after_write(
                path, text,
                f"整形コマンドを実行できません: {e.__class__.__name__}: {e}")
        if completed.returncode != 0:
            return _failed_after_write(
                path, text,
                f"整形コマンドが失敗しました（exit {completed.returncode}）: "
                f"{(completed.stderr or '').strip()}")
        formatted = True

    # 5. 再読込して本文から body_hash を算出する
    try:
        stamped_source = read_text(path)
    except (OSError, UnicodeDecodeError) as e:
        return _failed_after_write(
            path, text,
            f"整形後の再読込に失敗しました: {e.__class__.__name__}: {e}",
            error_code=ErrorCode.READ_ERROR, formatted=formatted)

    body_hash = compute_body_hash(split_document(stamped_source).body)

    # 6. body_hash 単独でマージする（他のキーには触らない）
    try:
        stamped = merge_frontmatter(stamped_source, {BODY_HASH_FIELD: body_hash})
    except (FrontmatterWriteError, ValueError) as e:
        return _failed_after_write(
            path, text, f"整形後のフロントマターへ打刻できません: {e}",
            formatted=formatted)

    # 7. 原子的に書き込む
    if stamped != stamped_source:
        try:
            write_text_atomic(path, stamped)
        except OSError as e:
            return _failed_after_write(
                path, text,
                f"打刻の書き込みに失敗しました: {e.__class__.__name__}: {e}",
                formatted=formatted)
        changed = True

    return _result(path, ok=True, changed=changed, formatted=formatted,
                   body_hash=body_hash)


def process_entries(entries, format_command=None):
    """entry 集合を入力順に処理し、JSON 出力に必要な各要素を組み立てる。

    個別 entry の失敗は 1 件で全体を落とさず status: partial へ写像する
    （error は引数自体が不正な場合に限る / DES-008 §6.2）。
    対象 0 件は error にしない（DES-005 §9.2）。

    Args:
        entries: [(path, metadata)] の list（入力順を保つ）
        format_command: 整形コマンド（省略時は整形しない）

    Returns:
        tuple: (status, results, counts)
    """
    results = [
        write_entry(path, metadata, format_command) for path, metadata in entries
    ]

    failed = [item for item in results if not item["ok"]]
    counts = {
        "total": len(results),
        "written": len(results) - len(failed),
        "failed": len(failed),
        "changed": sum(1 for item in results if item["changed"]),
        "formatted": sum(1 for item in results if item["formatted"]),
    }

    status = STATUS_PARTIAL if failed else STATUS_OK
    return status, results, counts


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
        ArgError: 未知引数・値不足・--entries-json の欠落
    """
    # add_help=False の理由は fm_read.parse_args と同じ（help が JSON 以外を
    # stdout へ出して exit 0 する経路を作らないため）。利用方法は本 script の
    # docstring と DES-008 に記述する。
    parser = _JsonArgumentParser(
        description=(
            "渡されたメタデータをフロントマターへマージ書き込みし、整形後に "
            "body_hash を打刻する"
        ),
        add_help=False,
    )
    parser.add_argument(
        "--entries-json",
        dest="entries_json",
        required=True,
        help="[{path, metadata}] の JSON 配列。相対パスは cwd 起点で解決する（必須）",
    )
    parser.add_argument(
        "--format-command",
        dest="format_command",
        default=None,
        help="整形コマンド（例: 'dprint fmt {file}'）。未指定なら整形しない",
    )
    return parser.parse_args(argv)


def parse_entries_json(raw):
    """--entries-json を (path, metadata) の list へ変換する。

    構造の不正は引数自体の不正であり、per-entry の失敗にはしない（path を
    特定できない要素があり、per-entry の結果として報告できないため）。

    Args:
        raw: --entries-json に渡された文字列

    Returns:
        list: (path, metadata) のタプルの list（入力順）

    Raises:
        ValueError: JSON として解析できない / 配列でない / 要素の構造が不正
    """
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as e:
        raise ValueError(f"--entries-json を JSON として解析できません: {e}")

    if not isinstance(value, list):
        raise ValueError("--entries-json は JSON 配列である必要があります")

    entries = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(
                f"--entries-json[{index}] は object である必要があります"
            )

        unknown = sorted(set(item) - ENTRY_KEYS)
        if unknown:
            raise ValueError(
                f"--entries-json[{index}] に未知のキーがあります: {', '.join(unknown)}"
            )

        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(
                f"--entries-json[{index}].path は非空の文字列である必要があります"
            )

        metadata = item.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError(
                f"--entries-json[{index}].metadata は object である必要があります"
            )

        entries.append((path, metadata))

    return entries


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

    # 1. --entries-json の構造検証（引数そのものの不正は script 全体の error）
    try:
        entries = parse_entries_json(args.entries_json)
    except ValueError as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.INVALID_PATH,
            message=str(e),
        )
        return 1

    # 2. 整形コマンドの検証（1 件目を処理してから落とさないため事前に行う）
    if args.format_command is not None:
        try:
            validate_format_command(args.format_command)
        except ValueError as e:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.UNSUPPORTED_ARG,
                message=str(e),
            )
            return 1

    # 3. 入力順に 1 件ずつ書き込む（対象 0 件は error ではない / DES-005 §9.2）
    status, results, counts = process_entries(entries, args.format_command)

    for item in results:
        if not item["ok"]:
            log(f"skip (failed): {item['path']} - {item['detail']}")

    emit_json(
        status,
        error_code=None,
        counts=counts,
        results=results,
    )
    # partial は「一部 entry が失敗したが他は完了した」状態であり処理は続行されている。
    # fm_read が partial で 0 を返すのと揃える。
    return 0


if __name__ == "__main__":
    sys.exit(main())
