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
```

`plan` は「書き込むべき対象」だけを `targets` に返す。既に信頼できるフロントマターを
持つ文書は `skipped` へ回す（絞り込みを AI にさせない）。

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

# expand_dirs は scripts/ 直下にある（frontmatter/ の外）。--dirs のときだけ使う。
_FRONTMATTER_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_FRONTMATTER_DIR)
for _path in (_FRONTMATTER_DIR, _SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import evaluate_file
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

# plan が targets / skipped に載せる理由
REASON_NO_FRONTMATTER = "no frontmatter"
REASON_NOT_TRUSTWORTHY = "frontmatter is not trustworthy"
REASON_ALREADY_TRUSTED = "already trusted"


class RunError(Exception):
    """ラッパーが続行できない状態。error_code を保持する。"""

    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# 対象の展開（--dirs 指定時のみ expand_dirs へ委ねる）
# ---------------------------------------------------------------------------

def expand_targets(dirs=None, paths=None, exclude=None):
    """`--dirs` / `--paths` を対象パスの list に揃える。

    ディレクトリの列挙は決定論的な定型処理であり、既存の `expand_dirs.py` に委ねる。
    frontmatter 系統に走査規則を持たせると `prepare_toc.py` の列挙と 2 箇所に分かれ、
    片方だけが改訂される（DES-008 §6.1）。

    Args:
        dirs: 展開するディレクトリの list（省略可）
        paths: 明示パスの list（省略可）
        exclude: 除外パスの list（省略可）

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
    if exclude:
        argv.extend(["--exclude-json", json.dumps(exclude)])

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

    apply_p = sub.add_parser("apply", add_help=False,
                             description="メタデータを書き込み、信頼判定まで行う")
    group = apply_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--entries-file", dest="entries_file",
                       help="[{path, metadata}] の JSON ファイル（推奨）")
    group.add_argument("--entries-json", dest="entries_json",
                       help="[{path, metadata}] の JSON 文字列")
    apply_p.add_argument("--format-command", dest="format_command",
                         help="整形コマンド。{file} が対象パスへ置換される")

    return parser.parse_args(argv)


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

    if args.command == "plan":
        try:
            paths, rejected_dirs, expand_warnings = expand_targets(
                dirs=args.dirs, paths=args.paths, exclude=args.exclude,
            )
        except RunError as e:
            emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
            return 1

        # 対象 0 件でも targets / skipped は常に出す。呼び出し側にフィールドの
        # 有無で分岐させると、そこが新たな判断点になる。
        status, targets, skipped, rejected_paths, warnings = run_plan(paths)
        emit_json(
            status,
            error_code=None,
            counts={
                "total": len(paths),
                "targets": len(targets),
                "skipped": len(skipped),
                "unreadable": len(rejected_paths),
            },
            rejected_paths=rejected_paths,
            warnings=expand_warnings + warnings,
            extra={
                "targets": targets,
                "skipped": skipped,
                "rejected_dirs": rejected_dirs,
            },
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

    try:
        entries = _load_entries(args)
    except RunError as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    status, results, counts = run_apply(entries, args.format_command)
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
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
