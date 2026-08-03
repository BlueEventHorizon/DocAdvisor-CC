#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index_docs.py — 索引パイプラインのラッパー（doc-advisor plugin）

DES-005 §6.1（prepare / merge の 2 フェーズ）/ §6.6（中断耐性）/ §8（JSON 契約）、
ADR-006（連続ディスパッチ）、DES-008 §7.1（転記フェーズ）を配管する。

## なぜラッパーが必要か

コア script（expand_dirs / prepare_toc / fm_to_pending / toc_store / merge_toc）は
個々の処理を決定論的に実装しているが、**script 間の受け渡しが AI に残っていた**。
実運用では 1 回の索引で AI が 15 回以上のコマンドを手で組み立て、各段の JSON から
次の引数へフィールドを転記していた。とくに連続ディスパッチの空きスロット計算
（`window - len(in_flight_groups)`）は、ADR-006 が「entry 数で引くと過大に減算され
負になり、補充されず wave に逆戻りする」と明示的に警告している計算である。

本 script は AI が呼ぶ唯一の入口として、その配管をすべて引き受ける。AI に残る責務は
**Agent の起動**と**判断**（越境 symlink の承認・充填エラーへの対応・書き戻しの可否）
だけである。

## 使い方

通常経路は次の 1 コマンドだけであり、**Agent の完了通知を受けるたびに同じコマンドを
再実行する**。初回と継続を呼び出し側が区別しない（状態は `.toc_work/` が持つ）。

    python3 index_docs.py --key specs --dirs docs/specs/
    python3 index_docs.py --all

## 返す action

| action     | 意味                                   | 呼び出し側がすること                     |
| ---------- | -------------------------------------- | ---------------------------------------- |
| `dispatch` | 起動すべき Agent がある                | agents[] の各要素で起動 → 同じコマンド再実行 |
| `wait`     | 走行中の Agent のみ（未投入なし）      | 完了通知を待つ → 同じコマンド再実行      |
| `confirm`  | 判断が必要（reason を見る）            | 判断し、決定を引数で渡して再実行         |
| `done`     | 完了                                   | 完了レポートを出す                       |
| `error`    | 異常                                   | error_code / message を報告              |

`agents[]` の要素は `{"subagent_type": ..., "prompt": ...}` であり、**prompt は
そのまま Agent へ渡せる文字列**である（呼び出し側に entry_file を転記させない）。

`confirm` の `reason`:

| reason              | 材料               | 決定の渡し方                          |
| ------------------- | ------------------ | ------------------------------------- |
| `external_symlink`  | `external_pending` | `--allow-external <symlink> ...`      |
| `fill_error`        | `error_pending`    | `--on-fill-error retry|merge|abort`   |

## コア script の呼び方

コア script は **CLI 契約（stdout に単一 JSON / DES-005 §8.1）をそのまま使って呼ぶ**。
`main(argv)` を同一プロセスで呼び、stdout をリダイレクトして JSON を受け取る。
理由は 2 つある。

1. **コア script を一切変更しない**。ラッパーのために新しい戻り値の経路を足すと、
   コア script を単体で使ったときとラッパー経由で使ったときで挙動が分岐しうる。
   CLI 契約が唯一の出口であり続ける方が、両者の一致が構造的に保たれる
2. subprocess を使わないため Python の起動コストが 1 回で済み、stderr のログは
   そのまま呼び出し側へ流れる（進捗が見える）

`toc_store` のみ関数を直接 import する。`store_dir` の解決結果は JSON 契約に
現れないため（CLI は `toc_path` しか返さない）、CLI 経由では受け取れない。

## 独立性（DES-008 §6.1 との関係）

フロントマターの転記は **`_transcribe()` の 1 箇所に閉じている**。フロントマター方式を
撤回する場合は、この関数の呼び出し 1 行と関数本体を削るだけで全体が通る（転記 0 件と
等価になり、すべての pending が AI 抽出へ回る）。`scripts/frontmatter/` を
ディレクトリごと削除できる状態を保つための境界である。

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import argparse
import contextlib
import io
import json
import os
import sys

# frontmatter/ は同一ディレクトリ配下のサブディレクトリであり sys.path に無い。
# 転記フェーズ（_transcribe）のためだけに追加する。
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTMATTER_DIR = os.path.join(_SCRIPTS_DIR, "frontmatter")
for _path in (_SCRIPTS_DIR, _FRONTMATTER_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import expand_dirs
import merge_toc
import prepare_toc
from toc_store import (
    DEFAULT_KEY,
    STATUS_ERROR,
    STATUS_OK,
    WORK_DIRNAME,
    ErrorCode,
    KeyError_,
    claim_entries,
    emit_json,
    resolve_store_dir,
    toc_path_rel,
    validate_user_key,
    work_status,
)
from toc_utils import get_project_root, log

# ---------------------------------------------------------------------------
# 定数（呼び出し側に見せないチューニング値）
# ---------------------------------------------------------------------------

# 並列ウィンドウ（走行中 Agent 数の上限）。ADR-006 案 A の実証済み安全圏。
# 10 超は未検証のため上げない。低 tier で 429 が出る環境では下げる必要があるが、
# その判断はコア script（toc_store.py --work-status --max-batch 等）で行う。
DEFAULT_WINDOW = 10

# 1 Agent が扱う pending の最大件数（ADR-006 案 B の限定バッチング）。
# context rot 回避のため小さく保つ。toc_store の既定と揃える。
DEFAULT_MAX_BATCH = 3

# 充填を担うカスタム Agent の種別（index-docs SKILL が Agent ツールへ渡す値）
TOC_UPDATER = "doc-advisor:toc-updater"

# action の値域
ACTION_DISPATCH = "dispatch"
ACTION_WAIT = "wait"
ACTION_CONFIRM = "confirm"
ACTION_DONE = "done"
ACTION_ERROR = "error"
ACTIONS = frozenset({
    ACTION_DISPATCH, ACTION_WAIT, ACTION_CONFIRM, ACTION_DONE, ACTION_ERROR,
})

# confirm の理由
REASON_EXTERNAL_SYMLINK = "external_symlink"
REASON_FILL_ERROR = "fill_error"
CONFIRM_REASONS = frozenset({REASON_EXTERNAL_SYMLINK, REASON_FILL_ERROR})

# --on-fill-error の値域
ON_FILL_ERROR_CHOICES = ("retry", "merge", "abort")


class WrapperError(Exception):
    """ラッパーが続行できない状態。error_code を保持する。"""

    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# コア script の呼び出し（CLI 契約をそのまま使う）
# ---------------------------------------------------------------------------

def call_core(module, argv):
    """コア script の main(argv) を呼び、stdout の単一 JSON を dict で返す。

    コア script は「stdout に単一 JSON、ログ・進捗は stderr」という契約を持つ
    （DES-005 §8.1）。その契約をそのまま利用するため、戻り値のための新しい経路を
    コア script 側に足さない。stderr は捕捉せずそのまま流し、進捗が呼び出し側に
    見えるようにする。

    Args:
        module: main(argv) を持つコア script モジュール
        argv: 引数列（list of str）

    Returns:
        tuple: (exit_code, payload)。payload は stdout の JSON を dict 化したもの

    Raises:
        WrapperError: stdout が単一 JSON として解析できない（契約違反）
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = module.main(argv)
    raw = buf.getvalue()
    try:
        payload = json.loads(raw)
    except ValueError as e:
        raise WrapperError(
            f"{module.__name__} の出力を JSON として解析できません: {e}: {raw[:200]!r}",
            ErrorCode.UNSUPPORTED_ARG,
        )
    return exit_code, payload


# ---------------------------------------------------------------------------
# frontmatter ブロック [撤回時はここだけを削る]
#
# DES-008 §6.1 の独立性を保つため、フロントマターへの依存を本関数と
# その呼び出し 1 行に閉じている。フロントマター方式を撤回する場合は
# 本関数と run() 内の呼び出しを削除するだけで全体が通る（転記 0 件と等価に
# なり、すべての pending が AI 抽出へ回る）。
# ---------------------------------------------------------------------------

def _transcribe(work_dir):
    """信頼できるフロントマターを持つ pending を転記で完了させる（DES-008 §7.1）。

    転記された pending は `_meta.status: completed` になるため、直後の work_status
    では pending に現れず充填対象から自動的に外れる。全件転記できた場合は
    Agent を 1 つも起動せず merge へ直行する。

    元文書には一切書き込まない（索引実行が原本を書き換えないという REQ-006 の制約）。

    Args:
        work_dir: `.toc_work/` の Path

    Returns:
        dict: {"transcribed": int, "warnings": [str]}。転記できない状態
            （script の失敗・引数不正・frontmatter/ 自体の不在）でも索引全体は
            続行できるため、例外にせず 0 件として扱い warnings で透明化する
    """
    try:
        import fm_to_pending
    except ImportError as e:
        # frontmatter/ が存在しない = フロントマター方式を撤回した状態。
        # 転記 0 件と等価であり、すべての pending が AI 抽出へ回るだけなので
        # 索引そのものは成立する（DES-008 §6.1 の撤回可能性）。
        # 通常運用で起きた場合（frontmatter/ の破損等）に黙って進まないよう
        # warnings で透明化する。
        return {
            "transcribed": 0,
            "warnings": [f"transcription skipped (frontmatter unavailable): {e}"],
        }

    try:
        _exit_code, payload = call_core(
            fm_to_pending, ["--work-dir", str(work_dir)]
        )
    except WrapperError as e:
        return {"transcribed": 0, "warnings": [f"transcription skipped: {e}"]}

    if payload.get("status") == STATUS_ERROR:
        return {
            "transcribed": 0,
            "warnings": [
                "transcription failed: "
                f"{payload.get('error_code')} {payload.get('message')}"
            ],
        }

    counts = payload.get("counts") or {}
    warnings = list(payload.get("warnings") or [])
    failed = counts.get("failed", 0)
    if failed:
        # 転記に失敗した pending は無変更で残り AI 抽出へ落ちるだけなので続行する。
        warnings.append(
            f"{failed} pending entr(ies) could not be transcribed; "
            "they fall back to AI extraction"
        )
    return {"transcribed": counts.get("transcribed", 0), "warnings": warnings}


# ---------------------------------------------------------------------------
# 連続ディスパッチ（ADR-006）
# ---------------------------------------------------------------------------

def next_dispatch(store_dir, project_root, key, *, window=DEFAULT_WINDOW,
                  max_batch=DEFAULT_MAX_BATCH, status=None):
    """今すぐ起動すべき Agent 群を claim 済みの状態で返す。

    空きスロットは **走行中 Agent 数**（`len(in_flight_groups)`）で数える。
    `in_flight` は entry のフラットリストであり、entry 数で引くと過大に減算されて
    負になり、補充されないまま wave 実行へ逆戻りする（ADR-006 の警告）。

    claim は投入直前に行う。claim した entry は次の work_status で in-flight として
    pending から外れるため、同じコマンドを再実行しても二重投入されない。

    Args:
        store_dir: store_dir の Path
        project_root: project root
        key: 実効 key（Agent の prompt に載せる）
        window: 並列ウィンドウ（走行中 Agent 数の上限）
        max_batch: 1 グループの最大 entry 数
        status: 既に取得済みの work_status（省略時は取得する）

    Returns:
        dict: {"agents": [{"subagent_type", "prompt", "entry_files"}],
               "window", "in_flight_agents", "available",
               "rejected": [{"entry_file", "reason"}]}
    """
    if status is None:
        status = work_status(store_dir, project_root, max_batch=max_batch)

    in_flight_agents = len(status["in_flight_groups"])
    available = max(0, window - in_flight_agents)
    groups = status["pending_groups"][:available]

    agents = []
    rejected = []
    for group in groups:
        claim_result = claim_entries(store_dir, project_root, group)
        rejected.extend(claim_result["rejected"])
        claimed = claim_result["claimed"]
        if not claimed:
            # claim が全て拒否されたグループは起動しない。次の work_status が
            # 実際の状態（completed / error / 他プロセスが claim 済み）を返す。
            continue
        agents.append({
            "subagent_type": TOC_UPDATER,
            "prompt": _agent_prompt(key, claimed),
            "entry_files": claimed,
        })

    return {
        "agents": agents,
        "window": window,
        "in_flight_agents": in_flight_agents,
        "available": available,
        "rejected": rejected,
    }


def _agent_prompt(key, entry_files):
    """toc-updater へ渡す prompt 文字列を組み立てる。

    呼び出し側（SKILL）に key と entry_file を転記させないため、渡せる形の
    文字列そのものを返す。単体モードでは toc-updater 側が `write_pending.py --all`
    を使う必要があるため、予約 key であることを明示する。

    Args:
        key: 実効 key
        entry_files: project-root 相対の entry_file リスト

    Returns:
        str
    """
    entries = ", ".join(entry_files)
    if key == DEFAULT_KEY:
        return f"all (single mode), entry_files: {entries}"
    return f"key: {key}, entry_files: {entries}"


# ---------------------------------------------------------------------------
# 段階判定（本体）
# ---------------------------------------------------------------------------

def _prepare_argv(args, key):
    """prepare_toc へ渡す argv を組み立てる。

    `--dirs` は expand_dirs で paths へ展開済みであり、prepare_toc は
    ディレクトリ展開を受け付けない（DES-005 §5.1 の誤用ガード）。
    """
    argv = []
    if key == DEFAULT_KEY:
        argv.append("--all")
    else:
        argv.extend(["--key", key])
    return argv


def _expand_targets(args):
    """`--dirs` / `--paths` / `--paths-file` を prepare 用の paths へ揃える。

    ディレクトリ展開は expand_dirs の責務であり、ラッパーは列挙を自分で書かない。

    Returns:
        tuple: (paths または None, rejected_dirs, warnings)
            paths が None のときは単体モード（prepare が自分で走査する）

    Raises:
        WrapperError: expand_dirs が error を返した
    """
    if not args.dirs and not args.paths and not args.paths_json and not args.paths_file:
        return None, [], []

    if args.paths_file:
        # paths-file はそのまま prepare へ渡す（展開の対象ではない）
        return None, [], []

    argv = []
    if args.dirs:
        argv.extend(["--dirs-json", json.dumps(args.dirs)])
    explicit_paths = list(args.paths or [])
    if args.paths_json:
        try:
            parsed = json.loads(args.paths_json)
        except ValueError as e:
            raise WrapperError(
                f"--paths-json を JSON として解析できません: {e}",
                ErrorCode.INVALID_PATH,
            )
        if not isinstance(parsed, list):
            raise WrapperError(
                "--paths-json は JSON 配列である必要があります",
                ErrorCode.INVALID_PATH,
            )
        explicit_paths.extend(parsed)
    if explicit_paths:
        argv.extend(["--paths-json", json.dumps(explicit_paths)])
    if args.exclude:
        argv.extend(["--exclude-json", json.dumps(args.exclude)])

    if not args.dirs:
        # 展開するディレクトリが無い＝明示 paths のみ。expand_dirs を通す必要がない
        return explicit_paths, [], []

    _exit_code, payload = call_core(expand_dirs, argv)
    if payload.get("status") == STATUS_ERROR:
        raise WrapperError(
            f"expand_dirs: {payload.get('message')}",
            payload.get("error_code") or ErrorCode.INVALID_PATH,
        )
    return (
        payload.get("paths") or [],
        payload.get("rejected_dirs") or [],
        payload.get("warnings") or [],
    )


def _run_prepare(args, key, paths):
    """prepare_toc を呼ぶ。

    Returns:
        dict: prepare_toc の JSON payload
    """
    argv = _prepare_argv(args, key)
    if args.paths_file:
        argv.extend(["--paths-file", args.paths_file])
    elif paths is not None:
        argv.extend(["--paths-json", json.dumps(paths)])
    if args.allow_external is not None:
        argv.extend(["--allow-external-json", json.dumps(args.allow_external)])
    _exit_code, payload = call_core(prepare_toc, argv)
    return payload


def _run_merge(key, delete_only=False):
    """merge_toc を呼ぶ。

    Returns:
        dict: merge_toc の JSON payload
    """
    argv = ["--all"] if key == DEFAULT_KEY else ["--key", key]
    if delete_only:
        argv.append("--delete-only")
    _exit_code, payload = call_core(merge_toc, argv)
    return payload


def _done_payload(merge_payload, *, warnings, rejected_paths, rejected_dirs):
    """merge の結果を完了レポート用の action: done へ写像する。

    `transcribed` / `ai_extracted` の件数はここで算出する。呼び出し側（AI）に
    数えさせない。

    **`transcribed` は merge の出力から導出する。** 本ラッパーは状態を持たない
    （`.toc_work/` が唯一の状態）ため、複数回の呼び出しにまたがる転記件数を
    自分では積算できない。一方 merge は「統合した文書」と「そのうち AI 抽出
    だったもの」を返すので、その差が転記由来である。充填が完了した pending には
    必ず来歴（`_meta.extracted_by`）が書かれるため、統合された文書は転記か
    AI 抽出のいずれかに必ず分類される。

    この導出により、転記件数のために merge_toc へ新しい出力項目を足す必要がなく、
    既存 script への侵入を増やさずに済む。
    """
    ai_paths = list(merge_payload.get("ai_extracted_paths") or [])
    counts = merge_payload.get("counts") or {}
    merged = counts.get("added", 0) + counts.get("updated", 0)
    transcribed = max(0, merged - len(ai_paths))
    return {
        "action": ACTION_DONE,
        "toc_path": merge_payload.get("toc_path"),
        "counts": counts,
        "transcribed": transcribed,
        "ai_extracted": len(ai_paths),
        "ai_extracted_paths": ai_paths,
        "deleted_paths": merge_payload.get("deleted_paths") or [],
        "rejected_paths": rejected_paths,
        "rejected_dirs": rejected_dirs,
        "warnings": warnings + list(merge_payload.get("warnings") or []),
    }


def run(args):
    """1 回の呼び出しで進められるところまで進め、action を返す。

    状態は `.toc_work/` とそのサイドカーが持つ。したがって初回と継続を
    呼び出し側が区別する必要がなく、同じコマンドを繰り返せばよい。

    Args:
        args: parse_args の結果

    Returns:
        tuple: (action_payload, key, toc_rel)

    Raises:
        WrapperError: 続行できない状態
    """
    project_root = get_project_root()

    # 0. 矛盾する対象指定を弾く。--all は project root 以下を自分で走査するため、
    #    ディレクトリ・パスの指定と併用しても片方が黙って無視される。
    #    どちらを優先すべきか推定せずエラーにする。
    explicit_targets = [
        name for name, value in (
            ("--dirs", args.dirs), ("--paths", args.paths),
            ("--paths-json", args.paths_json), ("--paths-file", args.paths_file),
        ) if value
    ]
    if args.all and explicit_targets:
        raise WrapperError(
            "--all は project root 以下の全 Markdown を対象にするため "
            f"{' / '.join(explicit_targets)} と併用できない",
            ErrorCode.UNSUPPORTED_ARG,
        )

    # 1. key 解決
    if args.all or args.key is None:
        key = DEFAULT_KEY
    else:
        try:
            key = validate_user_key(args.key)
        except KeyError_ as e:
            raise WrapperError(str(e), e.error_code)

    store_dir = resolve_store_dir(key, project_root)
    toc_rel = toc_path_rel(store_dir, project_root)
    work_dir = store_dir / WORK_DIRNAME

    warnings = []
    rejected_paths = []
    rejected_dirs = []
    transcribed = 0

    # 2. 継続判定。`.toc_work/` があれば prepare を再実行しない（DES-005 §6.6）。
    #    再実行すると充填済み pending を壊しうる。
    status = work_status(store_dir, project_root, max_batch=args.max_batch)

    if not status["has_work_dir"]:
        # --- 初回: 展開 → prepare ---
        paths, rejected_dirs, expand_warnings = _expand_targets(args)
        warnings.extend(expand_warnings)

        prepare_payload = _run_prepare(args, key, paths)
        prepare_status = prepare_payload.get("status")
        warnings.extend(prepare_payload.get("warnings") or [])
        rejected_paths = list(prepare_payload.get("rejected_paths") or [])

        if prepare_status == STATUS_ERROR:
            raise WrapperError(
                f"prepare_toc: {prepare_payload.get('message')}",
                prepare_payload.get("error_code") or ErrorCode.NO_TARGETS,
            )

        if prepare_status == "needs_confirmation":
            # 越境 symlink の承認待ち。書き込みは行われていない（NFR-N06）。
            return (
                {
                    "action": ACTION_CONFIRM,
                    "reason": REASON_EXTERNAL_SYMLINK,
                    "message": prepare_payload.get("message"),
                    "external_pending": prepare_payload.get("external_pending") or [],
                    "hint": (
                        "承認する symlink を --allow-external に並べて再実行する"
                        "（すべて拒否する場合は --allow-external を空で指定する）"
                    ),
                },
                key,
                toc_rel,
            )

        counts = prepare_payload.get("counts") or {}
        has_targets = counts.get("added", 0) > 0 or counts.get("updated", 0) > 0

        if not has_targets:
            if counts.get("deleted", 0) > 0:
                # 削除のみ。充填せず merge で反映する。
                merge_payload = _run_merge(key, delete_only=True)
                if merge_payload.get("status") == STATUS_ERROR:
                    raise WrapperError(
                        f"merge_toc: {merge_payload.get('message')}",
                        merge_payload.get("error_code") or ErrorCode.NO_TARGETS,
                    )
                return (
                    _done_payload(
                        merge_payload, warnings=warnings,
                        rejected_paths=rejected_paths, rejected_dirs=rejected_dirs,
                    ),
                    key, toc_rel,
                )
            # added / updated / deleted がすべて 0。
            if counts.get("unchanged", 0) > 0:
                # 全件が unchanged。統合するものが無く、既存 toc.yaml がそのまま
                # 有効である。prepare は work_dir を作らないため merge を呼ぶと
                # NO_TARGETS で失敗する。呼ばずに冪等成功として返す。
                return (
                    {
                        "action": ACTION_DONE,
                        "toc_path": toc_rel,
                        "counts": counts,
                        "transcribed": 0,
                        "ai_extracted": 0,
                        "ai_extracted_paths": [],
                        "deleted_paths": [],
                        "rejected_paths": rejected_paths,
                        "rejected_dirs": rejected_dirs,
                        "warnings": warnings,
                    },
                    key, toc_rel,
                )
            # desired 0 件（空 repo / 対象 0 件）。prepare が空意図サイドカーを
            # 残しているため、merge が空 toc.yaml を冪等出力する（DES-005 §9.2）。
            merge_payload = _run_merge(key)
            if merge_payload.get("status") == STATUS_ERROR:
                raise WrapperError(
                    f"merge_toc: {merge_payload.get('message')}",
                    merge_payload.get("error_code") or ErrorCode.NO_TARGETS,
                )
            return (
                _done_payload(
                    merge_payload, warnings=warnings,
                    rejected_paths=rejected_paths, rejected_dirs=rejected_dirs,
                ),
                key, toc_rel,
            )

        # 3. 転記フェーズ [frontmatter ブロック]
        transcription = _transcribe(work_dir)
        transcribed = transcription["transcribed"]
        warnings.extend(transcription["warnings"])

        # 4. 転記後の状態を引き直す（転記済みは pending から外れている）
        status = work_status(store_dir, project_root, max_batch=args.max_batch)
    else:
        # --- 継続: 前回実行後に原本へフロントマターが付与された可能性があるため
        #     転記を再実行する（fm_to_pending は completed をスキップし冪等）。
        #     pending が残っている場合のみ意味があるので next_action を見る。
        if status["next_action"] == "fill":
            transcription = _transcribe(work_dir)
            transcribed = transcription["transcribed"]
            warnings.extend(transcription["warnings"])
            status = work_status(store_dir, project_root, max_batch=args.max_batch)

    # 5. next_action で分岐
    next_action = status["next_action"]

    if next_action == "fill":
        dispatch = next_dispatch(
            store_dir, project_root, key,
            window=args.window, max_batch=args.max_batch, status=status,
        )
        if dispatch["rejected"]:
            warnings.extend(
                f"claim rejected: {item['entry_file']} ({item['reason']})"
                for item in dispatch["rejected"]
            )
        if not dispatch["agents"]:
            # 空きスロットが無い（全スロットが走行中）か、claim が全て拒否された。
            # いずれも完了通知を待って再実行すれば進む。
            return (
                {
                    "action": ACTION_WAIT,
                    "in_flight_agents": dispatch["in_flight_agents"],
                    "window": dispatch["window"],
                    "available": dispatch["available"],
                    "pending": len(status["pending"]),
                    "completed": status["completed"],
                    "transcribed": transcribed,
                    "warnings": warnings,
                },
                key, toc_rel,
            )
        return (
            {
                "action": ACTION_DISPATCH,
                "agents": dispatch["agents"],
                "in_flight_agents": dispatch["in_flight_agents"],
                "window": dispatch["window"],
                "available": dispatch["available"],
                "pending": len(status["pending"]),
                "completed": status["completed"],
                "transcribed": transcribed,
                "warnings": warnings,
            },
            key, toc_rel,
        )

    if next_action == "wait":
        return (
            {
                "action": ACTION_WAIT,
                "in_flight_agents": len(status["in_flight_groups"]),
                "window": args.window,
                "available": 0,
                "pending": 0,
                "completed": status["completed"],
                "transcribed": transcribed,
                "warnings": warnings,
            },
            key, toc_rel,
        )

    if next_action == "blocked":
        # 充填に失敗した entry が残る。**silent merge は禁止**（DES-005 §6.6）。
        # merge は completed のみ採用し成功時に .toc_work を削除するため、
        # errored doc は今回の ToC から脱落し、updated は現内容の checksum が
        # 書かれて次回も再索引されず stale 固定になる。
        if args.on_fill_error == "retry":
            # 失敗した entry へ toc-updater を再投入する。write_pending は充填成功時に
            # `_meta` を再構築するため error_message は消え、entry は completed になる。
            #
            # claim はしない。claim_entries は error_message を持つ entry を
            # reject する（reason: error_pending）ためである。error_pending は
            # pending にも in_flight にも数えられないので、claim による二重投入の
            # 防止が働かない代わりに、二重投入そのものが起きにくい位置にある。
            #
            # 失敗が恒常的（元文書の問題）な場合、再試行は何度やっても成功しない。
            # 同じコマンドを再実行すると再び投入されるため、警告で明示する。
            retry_entries = [
                item["entry_file"] for item in status["error_pending"]
            ][:args.window]
            warnings.append(
                f"retrying {len(retry_entries)} failed entr(ies); "
                "a permanent failure (a problem in the source document) will "
                "keep failing on every retry"
            )
            return (
                {
                    "action": ACTION_DISPATCH,
                    "agents": [
                        {
                            "subagent_type": TOC_UPDATER,
                            "prompt": _agent_prompt(key, [entry]),
                            "entry_files": [entry],
                        }
                        for entry in retry_entries
                    ],
                    "in_flight_agents": len(status["in_flight_groups"]),
                    "window": args.window,
                    "available": args.window,
                    "pending": 0,
                    "completed": status["completed"],
                    "transcribed": transcribed,
                    "retry": True,
                    "warnings": warnings,
                },
                key, toc_rel,
            )
        if args.on_fill_error == "abort":
            raise WrapperError(
                "充填エラーが残っているため中止した（--on-fill-error merge で"
                "脱落を承知のうえ統合できる）",
                ErrorCode.NO_TARGETS,
            )
        if args.on_fill_error == "merge":
            merge_payload = _run_merge(key)
            if merge_payload.get("status") == STATUS_ERROR:
                raise WrapperError(
                    f"merge_toc: {merge_payload.get('message')}",
                    merge_payload.get("error_code") or ErrorCode.NO_TARGETS,
                )
            dropped = [item["entry_file"] for item in status["error_pending"]]
            warnings.append(
                "merged with known fill errors; the following entries were "
                f"dropped from this ToC: {', '.join(dropped)}"
            )
            return (
                _done_payload(
                    merge_payload, warnings=warnings,
                    rejected_paths=rejected_paths, rejected_dirs=rejected_dirs,
                ),
                key, toc_rel,
            )
        return (
            {
                "action": ACTION_CONFIRM,
                "reason": REASON_FILL_ERROR,
                "message": (
                    "充填に失敗した pending が残っている。そのまま統合すると"
                    "当該文書は今回の ToC から脱落し、既存文書の改訂は"
                    "次回以降も索引されない（stale 固定）"
                ),
                "error_pending": status["error_pending"],
                "transcribed": transcribed,
                "warnings": warnings,
                "hint": (
                    "--on-fill-error merge（脱落を承知で統合）/ "
                    "--on-fill-error abort（中止）/ "
                    "元文書を修正してから再実行"
                ),
            },
            key, toc_rel,
        )

    # next_action == "merge": pending も error_pending も無い
    merge_payload = _run_merge(key)
    if merge_payload.get("status") == STATUS_ERROR:
        raise WrapperError(
            f"merge_toc: {merge_payload.get('message')}",
            merge_payload.get("error_code") or ErrorCode.NO_TARGETS,
        )
    return (
        _done_payload(
            merge_payload, warnings=warnings,
            rejected_paths=rejected_paths, rejected_dirs=rejected_dirs,
        ),
        key, toc_rel,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """引数を解析する。

    通常経路で必要なのは key と対象指定だけである。ウィンドウ幅・バッチサイズは
    呼び出し側の判断材料にならないため既定値を隠す（必要ならコア script の
    CLI で調整する）。
    """
    parser = argparse.ArgumentParser(
        description=(
            "Drive the ToC indexing pipeline. Re-run the same command after each "
            "agent completes; the wrapper decides what to do next."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--key", help="対象 ToC の opaque key（上位層が決める）")
    group.add_argument(
        "--all", action="store_true",
        help="単体モード（予約 key all。project root 以下の全 Markdown）",
    )
    parser.add_argument(
        "--dirs", nargs="+", metavar="DIR",
        help="索引するディレクトリ（複数指定可。グロブメタ文字可）",
    )
    parser.add_argument(
        "--paths", nargs="+", metavar="PATH",
        help="索引する Markdown ファイル（複数指定可。--dirs と併用可）",
    )
    parser.add_argument(
        "--paths-json", dest="paths_json",
        help="paths の JSON 配列（上位層からの機械的な受け渡し用）",
    )
    parser.add_argument(
        "--paths-file", dest="paths_file",
        help="paths 配列を含む JSON ファイル",
    )
    parser.add_argument(
        "--exclude", nargs="+", metavar="PATH",
        help="--dirs 展開時に除外するパス・ディレクトリ",
    )
    parser.add_argument(
        "--allow-external", dest="allow_external", nargs="*", metavar="SYMLINK",
        help=(
            "承認する越境 symlink（action: confirm / reason: external_symlink "
            "を受けたときのみ使う。空で指定するとすべて拒否する）"
        ),
    )
    parser.add_argument(
        "--on-fill-error", dest="on_fill_error", choices=ON_FILL_ERROR_CHOICES,
        help=(
            "充填エラーが残る場合の扱い（action: confirm / reason: fill_error "
            "を受けたときのみ使う）"
        ),
    )
    # 隠しオプション: 既定値を変える必要はほぼ無いが、テストと障害切り分けのために残す。
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help=argparse.SUPPRESS)
    parser.add_argument("--max-batch", dest="max_batch", type=int,
                        default=DEFAULT_MAX_BATCH, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        action_payload, key, toc_rel = run(args)
    except WrapperError as e:
        emit_json(
            STATUS_ERROR,
            error_code=e.error_code,
            message=str(e),
            extra={"action": ACTION_ERROR},
        )
        return 1

    action = action_payload["action"]
    log(f"action: {action}")
    emit_json(
        STATUS_OK,
        error_code=None,
        key=key,
        toc_path=toc_rel,
        extra=action_payload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
