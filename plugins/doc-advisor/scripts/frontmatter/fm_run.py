#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_run.py — フロントマター書き込みのラッパー（doc-advisor plugin / frontmatter）

DES-008 §6.1（独立性の境界）/ §6.2（責務）/ §8.1（書き込み SKILL）を配管する。

## なぜラッパーが必要か

`fm_read` / `fm_write` は個々の処理を決定論的に実装しているが、**その間の受け渡しが
AI に残っていた**。write-frontmatter SKILL の実運用では AI が次を手でやっていた。

- `expand_dirs` の出力 `paths` を `fm_read` の `--paths-json` へ組み替える
- `fm_read` の `results[].trust` を見て「書き込む対象」を自分で絞る
- `--entries-json` の JSON 構造を argv 上に組み立てる（長大になる）
- 書き込み後に `fm_read` を再度呼び、`counts.trusted` と書き込み件数を自分で比較する

本 script は AI が呼ぶ入口を 2 つに畳む。AI に残る責務は **メタデータの内容を作ること**
と **書き込みの承認を取ること** だけである。

## 使い方

```text
# 1. 対象の確定（読み取りのみ。原本は 1 バイトも変わらない）
fm_run.py plan --dirs docs/rules/
fm_run.py plan --paths docs/a.md docs/b.md

# 2. 書き込みと検証（AI がメタデータを作り承認を取った後）
fm_run.py apply --entries-file entries.json [--format-command "dprint fmt {file}"]

# ToC から写す経路（AI はメタデータを作らない。DES-008 §8.2）
fm_run.py plan  --from-toc rules --paths docs/a.md
fm_run.py apply --from-toc rules --paths docs/a.md [--format-command "dprint fmt {file}"]
```

`plan` は「書き込むべき対象」だけを `targets` に返す。既に信頼できるフロントマターを
持つ文書は `skipped` へ回す（絞り込みを AI にさせない）。

`--from-toc <key>` を付けると、各 target のメタデータを **その key の `toc.yaml` から
写して** `targets[].metadata` に載せる（`targets[].source` が `toc`）。`toc.yaml` の
エントリはフロントマターと同じ 5 フィールドを持つため、`body_hash` 以外は既に揃って
おり、AI が本文を読み直して書き直す必要がない。写せなかったものだけが `source: ai`
として残り、理由が `toc_reason` に入る。`--paths` / `--dirs` を省略すると ToC に載って
いる文書すべてが対象になる。

`apply --from-toc` は plan と同じ手順で対象を確定し直してから書き込む。plan の出力を
呼び出し側に持ち回らせないためである（entries の受け渡しが AI に残れば、転記を
script 化した意味が無くなる）。

`apply` は書き込みの**後に信頼判定まで行い** `counts.trusted` を返す。呼び出し側が
`fm_read` を再度呼んで件数を比較する必要がない。`trusted` が `written` に届かなければ
`status: partial` とし、どの文書がなぜ信頼されないかを `results[].violations` で示す。

これは DES-008 §6.2 が定めていた責務境界（`fm_write` は書く / `fm_read` は判定する）を
変更するものである。分離それ自体は正しかったが、その帰結として SKILL が両方を呼んで
件数を AI に比較させていた。**書いた側が「書けたものが信頼されるか」を確認して返す**方が、
呼び出し側に決定論的な作業を残さない。

## 独立性（DES-008 §6.1）

- `toc_store.py` / `toc_utils.py` を import しない。key 解決も store_dir 解決も行わない
- ToC・`.toc_work/`・checksums を読み書きしない（索引は `index-docs` の責務）
- ディレクトリ展開のみ `expand_dirs.py` に委ねる。走査規則を frontmatter 系統に
  持たせると `prepare_toc.py` の列挙と 2 箇所に分かれるため、既存の実装を使う

`expand_dirs.py` は `scripts/` 直下にあり frontmatter 系統の外である。これを import
することは §6.1 の「`toc_store` / `toc_utils` を import しない」に反しない（key 解決も
store_dir 解決も行わない汎用のパス展開であり、フロントマター方式を撤回しても
`expand_dirs.py` は残る）。`--dirs` を使わない経路ではそもそも呼ばない。

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

# expand_dirs は scripts/ 直下にある（frontmatter/ の外）。--dirs のときだけ使う。
_FRONTMATTER_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_FRONTMATTER_DIR)
for _path in (_FRONTMATTER_DIR, _SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import evaluate_file
from fm_from_toc import (
    REASON_INCOMPLETE_ENTRY,
    REASON_UNVERIFIABLE,
    FromTocError,
    load_toc,
    resolve_entry,
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
    violations_json,
)
from fm_write import parse_entries_json, process_entries, validate_format_command

# 中心側に 1 つだけ置くべき規則を共有する（DES-008 §6.1 の表）。パスの基準を
# 決める規則を派生側で 2 実装目として持たない。
from toc_utils import (  # noqa: E402
    ensure_project_root_cwd,
    filter_excluded,
    get_project_root,
)

# plan が targets / skipped に載せる理由
REASON_NO_FRONTMATTER = "no frontmatter"
REASON_NOT_TRUSTWORTHY = "frontmatter is not trustworthy"
REASON_ALREADY_TRUSTED = "already trusted"

# targets[].source: メタデータの出どころ。`toc` は script が写したもの（AI は内容を
# 作らない）、`ai` は AI が起草するもの。呼び出し側はこの値で「作る必要があるか」を
# 判断する。
SOURCE_TOC = "toc"
SOURCE_AI = "ai"

# 転記できない理由のうち、**索引側の異常**を示すもの。これだけを warnings に載せる。
# 残り（not_in_toc / body_changed）は正常に起こる状態であり、warning にすると件数に
# 比例して並んで本当の異常が埋もれる。
ANOMALOUS_TOC_REASONS = frozenset({REASON_INCOMPLETE_ENTRY, REASON_UNVERIFIABLE})


class RunError(Exception):
    """ラッパーが続行できない状態。error_code を保持する。"""

    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# 対象の展開（--dirs 指定時のみ expand_dirs へ委ねる）
# ---------------------------------------------------------------------------

def expand_targets(dirs=None, paths=None):
    """`--dirs` / `--paths` を対象パスの list に揃える。

    ディレクトリの列挙は決定論的な定型処理であり、既存の `expand_dirs.py` に委ねる。
    frontmatter 系統に走査規則を持たせると `prepare_toc.py` の列挙と 2 箇所に分かれ、
    片方だけが改訂される（DES-008 §6.1）。

    **利用者指定の除外は扱わない。** 除外は対象集合の確定後に適用する
    （`resolve_targets` が `filter_excluded` で行う / DES-005 §4.2.2）。

    Args:
        dirs: 展開するディレクトリの list（省略可）
        paths: 明示パスの list（省略可）

    Returns:
        tuple: (paths, rejected_dirs, warnings)

    Raises:
        RunError: expand_dirs が error を返した
    """
    explicit = list(paths or [])
    if not dirs:
        return explicit, [], []

    import expand_dirs

    argv = ["--dirs-json", json.dumps(dirs)]
    if explicit:
        argv.extend(["--paths-json", json.dumps(explicit)])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        expand_dirs.main(argv)
    try:
        payload = json.loads(buf.getvalue())
    except ValueError as e:
        raise RunError(
            f"expand_dirs の出力を JSON として解析できません: {e}",
            ErrorCode.INVALID_PATH,
        )
    if payload.get("status") == STATUS_ERROR:
        raise RunError(
            f"expand_dirs: {payload.get('message')}",
            payload.get("error_code") or ErrorCode.INVALID_PATH,
        )
    return (
        payload.get("paths") or [],
        payload.get("rejected_dirs") or [],
        payload.get("warnings") or [],
    )


# ---------------------------------------------------------------------------
# plan: 書き込むべき対象を確定する（読み取りのみ）
# ---------------------------------------------------------------------------

def run_plan(paths):
    """各パスを評価し、書き込むべき対象と除外を分ける。

    既に信頼できるフロントマターを持つ文書は対象から外す。この絞り込みを呼び出し側に
    させると、`trust` の判定結果を AI が読んで選別する作業が残る。

    Args:
        paths: 対象パスの list（入力順を保つ）

    Returns:
        tuple: (status, targets, skipped, rejected_paths, warnings)
    """
    targets = []
    skipped = []
    rejected_paths = []
    warnings = []

    for path in paths:
        try:
            result = evaluate_file(path)
        except FileNotFoundError:
            rejected_paths.append({"path": path, "reason": ErrorCode.NOT_FOUND})
            continue
        except (OSError, UnicodeDecodeError) as e:
            rejected_paths.append({"path": path, "reason": ErrorCode.READ_ERROR})
            log(f"skip (unreadable): {path} [{e.__class__.__name__}]")
            continue

        if result.trust:
            skipped.append({"path": path, "reason": REASON_ALREADY_TRUSTED})
            continue

        reason = (
            REASON_NOT_TRUSTWORTHY if result.has_frontmatter
            else REASON_NO_FRONTMATTER
        )
        targets.append({
            "path": path,
            "reason": reason,
            "has_frontmatter": result.has_frontmatter,
            "has_marker": result.has_marker,
            "violations": violations_json(result.violations),
        })

        if result.warn:
            # doc-advisor の標識があるのに信頼できない = 規約違反または本文からの
            # 取り残され（DES-008 §5.3）。黙って上書きせず提示する。
            codes = ", ".join(v["code"] for v in violations_json(result.violations))
            warnings.append(
                "frontmatter has the doc-advisor marker but is not trustworthy: "
                f"{path} ({codes})"
            )

    status = STATUS_PARTIAL if rejected_paths else STATUS_OK
    return status, targets, skipped, rejected_paths, warnings


# ---------------------------------------------------------------------------
# from-toc: ToC のメタデータを targets へ写す（DES-008 §8.2）
# ---------------------------------------------------------------------------

def annotate_from_toc(key, targets):
    """plan が確定した targets に ToC 由来のメタデータを付ける。

    ToC のエントリは 5 フィールドがフロントマターと同一であるため、`body_hash` を
    除いてそのまま写せる。**AI に内容を作らせるのは、写せなかった対象だけである。**

    写せない対象（ToC に無い / 索引後に本文が変わった / エントリが揃っていない）は
    `source: ai` として残し、理由を `toc_reason` に入れる。除外はしない。除外すると
    「フロントマターを持たない文書」が黙って対象から消え、書き戻しが不完全になった
    ことに呼び出し側が気づけない。

    warnings に載せるのは **索引側の異常**（エントリが 5 フィールドを満たさない /
    索引時の hash と照合できない）だけである。「ToC に無い」「索引後に本文が変わった」は
    正常に起こる状態であり、これを warning にすると件数に比例して並び、本当の異常が
    埋もれる。分類そのものは `targets[].toc_reason` と `counts.needs_ai` で全件見える。

    Args:
        key: ToC の key（予約 key の単体モードは 'all'）
        targets: `run_plan` が返した targets（in-place で更新する）

    Returns:
        tuple: (toc_path, warnings)

    Raises:
        RunError: ToC を読めない
    """
    try:
        source = load_toc(key)
    except FromTocError as e:
        raise RunError(str(e), ErrorCode.TOC_NOT_FOUND)

    warnings = []
    for item in targets:
        metadata, reason, violations = resolve_entry(source, item["path"])
        if metadata is None:
            item["source"] = SOURCE_AI
            item["toc_reason"] = reason
            if violations:
                item["toc_violations"] = violations_json(violations)
            if reason in ANOMALOUS_TOC_REASONS:
                warnings.append(
                    f"the ToC entry cannot be trusted as a transcription source "
                    f"({reason}): {item['path']}"
                )
            continue
        item["source"] = SOURCE_TOC
        item["metadata"] = metadata

    return str(source.toc_path), warnings


def toc_entries(targets):
    """targets のうち ToC から写せたものを [(path, metadata)] へ変換する。

    Args:
        targets: `annotate_from_toc` を通した targets

    Returns:
        list: (path, metadata) のタプルの list（targets の順序を保つ）
    """
    return [
        (item["path"], item["metadata"])
        for item in targets
        if item.get("source") == SOURCE_TOC
    ]


def resolve_targets(args):
    """plan / apply が共通で使う「対象の確定」を行う。

    `--from-toc` 指定時に `--paths` / `--dirs` が**省略された**場合は、その ToC に載って
    いる文書すべてを対象にする。対象の列挙は決定論的な定型処理であり、ToC を AI に
    手読みさせない（CLAUDE.md）。

    ToC 全件へのフォールバックは「対象が指定されていない」ときに限る。`--dirs` を
    指定したが展開結果が 0 件（Markdown を含まないディレクトリ）だった場合に全件へ
    落とすと、`--from-toc` は原本へ書き込む経路であるため、**利用者が指定した範囲外の
    原本を書き換える**。指定が空振りしたことは 0 件のまま返して呼び出し側に伝える。

    **`--exclude` は対象の出どころによらず、確定した集合へ最後に適用する。**
    ディレクトリ展開の内側だけで適用すると、`--dirs` を伴わない指定（明示 paths のみ /
    ToC 全件）で黙って無視される。`--exclude` は「選び方」ではなく「選んだ結果から
    何を落とすか」であり、適用点は対象の確定後が正しい（`filter_excluded`）。

    Args:
        args: 解析済み引数

    Returns:
        tuple: (paths, rejected_dirs, warnings)

    Raises:
        RunError: expand_dirs が error を返した / ToC を読めない
    """
    # 除外は下流（expand_dirs）へ渡さない。適用点を 1 つにするためである。
    paths, rejected_dirs, warnings = expand_targets(
        dirs=args.dirs, paths=args.paths,
    )
    if not paths and args.from_toc and not (args.paths or args.dirs):
        try:
            source = load_toc(args.from_toc)
        except FromTocError as e:
            raise RunError(str(e), ErrorCode.TOC_NOT_FOUND)
        paths = source.paths

    paths, excluded = filter_excluded(paths, get_project_root(), args.exclude)
    if excluded:
        warnings = warnings + [
            f"excluded by --exclude: {len(excluded)} path(s)"
        ]
    return paths, rejected_dirs, warnings


# ---------------------------------------------------------------------------
# apply: 書き込み + 書き込み後の信頼判定
# ---------------------------------------------------------------------------

def run_apply(entries, format_command=None):
    """entry を書き込み、**書き込んだ結果が信頼されるかを確認して**返す。

    `fm_write.process_entries` の結果に、各 entry の書き込み後の `trust` を付ける。
    書き込みの成功と信頼判定の成立は別であり（上限違反は手順 0 で弾かれるが、
    必須フィールドの欠落は部分更新を許すため書き込み側では検査しない）、呼び出し側に
    `fm_read` を再度呼ばせて件数を比較させないためここで確認する。

    Args:
        entries: [(path, metadata)] の list（入力順を保つ）
        format_command: 整形コマンド（省略時は整形しない）

    Returns:
        tuple: (status, results, counts)
    """
    status, results, counts = process_entries(entries, format_command)

    trusted = 0
    for item in results:
        if not item["ok"]:
            item["trust"] = False
            continue
        try:
            evaluation = evaluate_file(item["path"])
        except (OSError, UnicodeDecodeError) as e:
            # 書き込みは成功したが読み直せない。信頼できるとは言えない。
            item["trust"] = False
            item["detail"] = (
                f"書き込みは成功したが検証のための再読込に失敗した: "
                f"{e.__class__.__name__}: {e}"
            )
            continue
        item["trust"] = evaluation.trust
        if evaluation.trust:
            trusted += 1
        else:
            # 書けたのに信頼されない。値域は手順 0 で弾かれているため、ここに来るのは
            # 必須フィールドの欠落（部分更新で 5 フィールドが揃わなかった）か、
            # 打刻後に別経路で本文が変わった場合である。
            item["violations"] = violations_json(evaluation.violations)

    counts["trusted"] = trusted

    if status == STATUS_OK and trusted < counts["written"]:
        # 全 entry の書き込みは成功したが、信頼判定に至らないものがある。
        # 成功として報告すると呼び出し側が気づけないため partial へ落とす。
        status = STATUS_PARTIAL

    return status, results, counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """引数を解析する。

    サブコマンドは plan / apply の 2 つのみとし、それぞれのオプションを最小に保つ。
    """
    parser = _JsonArgumentParser(
        description=(
            "Plan and apply doc-advisor frontmatter writes. "
            "'plan' resolves what to write (read-only); 'apply' writes and verifies."
        ),
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", add_help=False,
                          description="書き込むべき対象を確定する（読み取りのみ）")
    plan.add_argument("--dirs", nargs="+", metavar="DIR",
                      help="対象ディレクトリ（複数指定可。グロブメタ文字可）")
    plan.add_argument("--paths", nargs="+", metavar="PATH",
                      help="対象ファイル（複数指定可。--dirs と併用可）")
    plan.add_argument("--exclude", nargs="+", metavar="PATH",
                      help="--dirs 展開時に除外するパス・ディレクトリ")
    plan.add_argument("--from-toc", dest="from_toc", metavar="KEY",
                      help="当該 key の ToC からメタデータを写す（単体モードは 'all'）。"
                           "--paths / --dirs 省略時は ToC の全文書を対象にする")

    apply_p = sub.add_parser("apply", add_help=False,
                             description="メタデータを書き込み、信頼判定まで行う")
    group = apply_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--entries-file", dest="entries_file",
                       help="[{path, metadata}] の JSON ファイル（AI が作成した場合）")
    group.add_argument("--entries-json", dest="entries_json",
                       help="[{path, metadata}] の JSON 文字列")
    group.add_argument("--from-toc", dest="from_toc", metavar="KEY",
                       help="当該 key の ToC からメタデータを写して書き込む"
                            "（AI はメタデータを作らない）")
    apply_p.add_argument("--dirs", nargs="+", metavar="DIR",
                         help="対象ディレクトリ（--from-toc 指定時のみ）")
    apply_p.add_argument("--paths", nargs="+", metavar="PATH",
                         help="対象ファイル（--from-toc 指定時のみ）")
    apply_p.add_argument("--exclude", nargs="+", metavar="PATH",
                         help="--dirs 展開時に除外するパス・ディレクトリ")
    apply_p.add_argument("--format-command", dest="format_command",
                         help="整形コマンド。{file} が対象パスへ置換される")

    return parser.parse_args(argv)


def _target_counts(paths, targets, skipped, rejected_paths):
    """plan の counts を組み立てる。

    `from_toc` / `needs_ai` は `--from-toc` を指定しない場合も常に出す（前者 0 件、
    後者は targets 全件）。フィールドの有無で呼び出し側に分岐させると、そこが
    新たな判断点になる。

    Args:
        paths: 対象として確定したパスの list
        targets: 書き込むべき対象の list
        skipped: 対象外の list
        rejected_paths: 読めなかったパスの list

    Returns:
        dict
    """
    return {
        "total": len(paths),
        "targets": len(targets),
        "from_toc": sum(1 for item in targets if item.get("source") == SOURCE_TOC),
        "needs_ai": sum(1 for item in targets if item.get("source") == SOURCE_AI),
        "skipped": len(skipped),
        "unreadable": len(rejected_paths),
    }


def _load_entries(args):
    """--entries-file / --entries-json を [(path, metadata)] へ変換する。

    形式検証は fm_write.parse_entries_json に委ねる（書き込み側と同一の検証を
    通すため。ラッパーが独自に緩い検証を持つと契約が 2 系統になる）。
    """
    if args.entries_file:
        try:
            with open(args.entries_file, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            raise RunError(
                f"--entries-file が見つかりません: {args.entries_file}",
                ErrorCode.NOT_FOUND,
            )
        except (OSError, UnicodeDecodeError) as e:
            raise RunError(
                f"--entries-file を読めません: {e.__class__.__name__}: {e}",
                ErrorCode.READ_ERROR,
            )
    else:
        raw = args.entries_json

    try:
        return parse_entries_json(raw)
    except ValueError as e:
        raise RunError(str(e), ErrorCode.INVALID_PATH)


def main(argv=None):
    try:
        args = parse_args(argv)
    except ArgError as e:
        emit_json(STATUS_ERROR, error_code=ErrorCode.UNSUPPORTED_ARG, message=str(e))
        return 1

    # apply の対象指定は --from-toc 専用である。--entries-file / --entries-json は
    # 対象とメタデータを対で受け取るため、対象指定を併記しても行き先が無い。黙って
    # 無視すると「対象を絞ったつもりの指定が効かないまま原本へ書き込む」ことになる。
    # 既に --from-toc と --entries-* は排他なので、その排他へ対象指定を含める。
    if args.command == "apply" and not args.from_toc:
        given = [
            name for name, value in (
                ("--dirs", args.dirs), ("--paths", args.paths),
                ("--exclude", args.exclude),
            ) if value
        ]
        if given:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.UNSUPPORTED_ARG,
                message=(
                    f"{' / '.join(given)} は --from-toc と併せて使う引数です。"
                    "--entries-file / --entries-json では対象を絞れません"
                ),
            )
            return 1

    # パスの基準を 1 つに固定する。project-root-relative なパスを「結合して開く」
    # 作法（陳腐化ガードの hash 照合）と「そのまま開く」作法（本文の読み書き）が
    # 同じ実行の中で交差しており、cwd と project root が違えば別のファイルを指した。
    # 検査して弾くのではなく基準を揃えることで、食い違いが起こり得なくなる。
    # **cwd を変える前に** argv で受けたファイルの位置を絶対パスへ解決する
    # （呼び出し元の cwd 基準で渡され得る。--paths / --dirs は project-root-relative）。
    if getattr(args, "entries_file", None):
        args.entries_file = str(Path(args.entries_file).resolve())
    ensure_project_root_cwd()

    if args.from_toc is not None and not args.from_toc.strip():
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.KEY_EMPTY,
            message="--from-toc の key が空です",
        )
        return 1

    if args.command == "plan":
        try:
            paths, rejected_dirs, expand_warnings = resolve_targets(args)
            status, targets, skipped, rejected_paths, warnings = run_plan(paths)
            toc_path = None
            if args.from_toc:
                toc_path, toc_warnings = annotate_from_toc(args.from_toc, targets)
                warnings.extend(toc_warnings)
            else:
                for item in targets:
                    item["source"] = SOURCE_AI
        except RunError as e:
            emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
            return 1

        # 対象 0 件でも targets / skipped は常に出す。呼び出し側にフィールドの
        # 有無で分岐させると、そこが新たな判断点になる。
        extra = {
            "targets": targets,
            "skipped": skipped,
            "rejected_dirs": rejected_dirs,
        }
        if toc_path is not None:
            extra["toc_path"] = toc_path
        emit_json(
            status,
            error_code=None,
            counts=_target_counts(paths, targets, skipped, rejected_paths),
            rejected_paths=rejected_paths,
            warnings=expand_warnings + warnings,
            extra=extra,
        )
        return 0

    # apply
    if args.format_command:
        try:
            validate_format_command(args.format_command)
        except ValueError as e:
            emit_json(
                STATUS_ERROR, error_code=ErrorCode.UNSUPPORTED_ARG, message=str(e)
            )
            return 1

    plan_extra = None
    plan_status = None
    plan_warnings = []
    rejected_paths = []
    resolved_total = None
    try:
        if args.from_toc:
            # 転記経路は plan と同じ手順で対象を確定し直す。plan の出力を呼び出し側に
            # 持ち回らせない（entries の受け渡しが AI に残ると転記を script 化した
            # 意味が無くなる。DES-005 §4.1.1 の「AI が呼ぶ入口」の考え方）。
            paths, rejected_dirs, plan_warnings = resolve_targets(args)
            resolved_total = len(paths)
            plan_status, targets, skipped, rejected_paths, run_warnings = run_plan(paths)
            plan_warnings = plan_warnings + run_warnings
            toc_path, toc_warnings = annotate_from_toc(args.from_toc, targets)
            plan_warnings.extend(toc_warnings)
            entries = toc_entries(targets)
            plan_extra = {
                "toc_path": toc_path,
                "needs_ai": [
                    item for item in targets if item.get("source") == SOURCE_AI
                ],
                "skipped": skipped,
                "rejected_dirs": rejected_dirs,
                # 非空のときだけ出す形にしない。フィールドの有無で呼び出し側に
                # 分岐させると、そこが新たな判断点になる（_target_counts と同じ方針）。
                "rejected_paths": rejected_paths,
            }
        else:
            entries = _load_entries(args)
    except RunError as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    status, results, counts = run_apply(entries, args.format_command)
    if plan_status == STATUS_PARTIAL and status == STATUS_OK:
        # 対象の確定側で読めなかったもの（rejected_paths）がある。書き込んだ分が
        # すべて成功していても `ok` として返すと、呼び出し側は「指定した文書はすべて
        # 書かれた」と読む（write-frontmatter SKILL の契約）。plan が partial を
        # 返す同じ状況で apply が ok を返す非対称を作らない。
        status = STATUS_PARTIAL
    # 転記した件数だけでは「書き戻しが完全か」が分からない。AI 起草が必要な残り・
    # 対象外・読めなかった件数を同じ counts に載せる（呼び出し側に数え直させない）。
    # **`--from-toc` の有無で形を変えない**。フィールドの有無で呼び出し側に分岐させると
    # そこが新たな判断点になる（`_target_counts` の方針を apply 側にも適用する）。
    counts["needs_ai"] = len(plan_extra["needs_ai"]) if plan_extra else 0
    counts["skipped"] = len(plan_extra["skipped"]) if plan_extra else 0
    counts["unreadable"] = len(rejected_paths)
    if resolved_total is not None:
        # `total` は「対象として確定した件数」であり、書き込みを試みた entry 数では
        # ない。転記経路では entry 数（= 転記できた分）だけを数えると、同じ counts に
        # 載る needs_ai / skipped / unreadable と基準が食い違い、SKILL の報告が
        # 「対象」から needs_ai の分を落とす。total = 転記 + needs_ai + skipped +
        # unreadable が成り立つ形に揃える（written / failed は書き込み側の数のまま）。
        counts["total"] = resolved_total
    # 表記を変換して書いた entry は必ず報告する。書いた値と原本に入る値が違うことを
    # 黙って済ませない（変換は拒否より安いが、不可視にしてよい理由にはならない）。
    normalization_warnings = [
        f"normalized to fit the value domain: {item['path']} "
        f"({', '.join(item['normalized_fields'])})"
        for item in results
        if item.get("normalized_fields")
    ]
    for item in results:
        if not item["ok"]:
            log(f"failed: {item['path']} - {item['detail']}")
        elif not item["trust"]:
            log(f"written but not trustworthy: {item['path']}")
    emit_json(
        status,
        error_code=None,
        counts=counts,
        results=results,
        warnings=(plan_warnings + normalization_warnings) or None,
        extra=plan_extra,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
