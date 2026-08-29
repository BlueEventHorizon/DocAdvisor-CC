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
**Agent の起動**と**判断**（越境 symlink の承認・充填エラーへの対応。書き戻しの承認判定は
write-frontmatter が行う）
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

`external_symlink` は **`--all`（project root 全体の走査）でのみ起きる**。`--dirs` /
`--paths` で渡された対象は、越境 symlink であってもそのまま索引する（渡す側がそれが
symlink であることを知っている / NFR-N06）。`--allow-external` は確認の答えを戻す
内部的な通路であり、上位層との契約ではない（公開引数表には載せない）。

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
from pathlib import Path

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
    reset_error_entries,
    resolve_store_dir,
    toc_path_rel,
    validate_user_key,
    work_status,
)
from toc_utils import (
    ensure_project_root_cwd,
    filter_excluded,
    get_project_root,
    log,
)

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
#
# **「撤回」と「破損」を区別する [MANDATORY]**: ディレクトリごと消えているのは
# 撤回であり許容する。ディレクトリがあるのに読み込めないのは破損であり error に
# する。区別の基準は「異常か否か」であり「索引できるか否か」ではない
# （破損時も AI 抽出で索引は完了し、失われるのは高速化だけである。詳細は
# _transcribe の except 節のコメントと DES-005 §4.1.1）。
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
        dict: {"transcribed": int, "warnings": [str]}。方式を撤回した状態と、
            転記の部分的な失敗は 0 件として扱い warnings で透明化する

    Raises:
        WrapperError: frontmatter/ が存在するのに読み込めない（破損）
    """
    if not os.path.isdir(_FRONTMATTER_DIR):
        # ディレクトリが無い = フロントマター方式を撤回した状態。転記 0 件と
        # 等価であり、すべての pending が AI 抽出へ回るだけなので索引は成立する
        # （DES-008 §6.1 の撤回可能性）。**方式の不在だけをここで許容する。**
        return {
            "transcribed": 0,
            "warnings": ["transcription skipped (frontmatter method withdrawn)"],
        }

    try:
        import fm_to_pending
    except Exception as e:
        # ディレクトリはあるのに読み込めない = 破損（部分配置・壊れた import・
        # 依存の欠落・構文エラー）。
        #
        # 転記 0 件として続行しても toc.yaml の内容は正しい（未信頼の文書は
        # AI 抽出へ回り、それは転記のフォールバック先として正常な経路である /
        # DES-008 §7.1）。失われるのは**転記による高速化だけ**である。
        # したがってここで防ぐのは「誤った ToC」ではなく「配布物が壊れたまま
        # 性能劣化が黙って続くこと」である。転記は大量文書の索引コストを
        # 削減するために導入した機構であり、それが恒久的に機能していないのに
        # done が返り続ければ利用者は気づけない。warning は自動実行で
        # 見落とされるため、成功経路に載せてはならない。
        #
        # 撤回（上の isdir 判定）を続行させ破損を error にする基準は
        # 「異常か否か」であり「索引できるか否か」ではない。撤回は意図された
        # 状態であり、破損は放置してよい状態ではない。
        #
        # **ImportError だけでなく Exception 全体を捕まえる [MANDATORY]**:
        # 構文エラーは SyntaxError であり ImportError ではない。捕まえ損ねると
        # 例外が main() の外へ伝播して traceback で終了し、「stdout に単一 JSON」
        # という CLI 契約（DES-005 §8.1）を破る。呼び出し側は action で分岐する
        # ため、機械的に扱えない終了は silent success と別種の欠陥である。
        # KeyboardInterrupt / SystemExit は BaseException 派生であり、
        # ここでは意図的に捕まえない（利用者による中断を握りつぶさない）。
        raise WrapperError(
            f"{_FRONTMATTER_DIR} は存在するが転記モジュールを読み込めません"
            f"（撤回ではなく破損の可能性）: {e.__class__.__name__}: {e}",
            ErrorCode.READ_ERROR,
        )

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


# 対象指定の引数（CLI フラグ名 → args の属性名）。`--all` との排他判定と
# 「対象が明示されたか」の判定を 1 箇所から引くための表。
TARGET_ARGS = (
    ("--dirs", "dirs"),
    ("--dirs-json", "dirs_json"),
    ("--paths", "paths"),
    ("--paths-json", "paths_json"),
    ("--paths-file", "paths_file"),
)


def _explicit_target_flags(args):
    """明示された対象指定のフラグ名を返す（単体モードとの排他判定と報告に使う）。"""
    return [flag for flag, attr in TARGET_ARGS if getattr(args, attr, None)]


def _is_single_mode(args):
    """単体モード（project root 以下の全走査）へ入るか。

    単体モードへ入る書き方は **2 つある**——`--all` の明示と `--key` の省略で
    あり、REQ-001 FR-N04-1 と一元定義表がこれを同義と定めている（DES-005 §10.1）。
    key 解決（`args.all or args.key is None`）と `prepare_toc.single_mode` は
    どちらもこの 2 つを見ており、**判定を `args.all` だけで行うと片方が漏れる**。

    漏らした場合の帰結は「対象指定が黙って捨てられ、project root 全体が索引される」
    ことであり、desired-state のため当該 key の ToC の内容も全件へ置き換わる。
    """
    return bool(args.all) or args.key is None


def _single_mode_flag(args):
    """エラーメッセージに出す、単体モードへ入った原因の呼び方。"""
    return "--all" if args.all else "--key の省略（単体モード）"


def _has_explicit_target(args):
    """対象が明示されているか（偽なら単体モードとして prepare が走査する）。"""
    return bool(_explicit_target_flags(args))


def _merge_list_arg(repeated, json_form, json_flag):
    """繰り返し指定（nargs）と JSON 配列指定を 1 つの list へ揃える。

    同じ対象を 2 通りで受け取るのは、**呼び出し元が 2 種類ある**ためである。

    - 人間・AI が手で打つ経路 — `--dirs docs/rules/ docs/specs/` の方が短く、
      引用符のエスケープも要らない
    - 上位層（forge 等）が機械的に渡す経路 — 自身の設定から解決した配列を
      そのまま `--dirs-json '[...]'` で渡す。文字列を組み立て直させない
      （どの設定から解決するかは上位層の関心であり、本 script は知らない）

    両方を受け取り、指定されていれば連結する（併用可）。上位層の既存の呼び出しを
    壊さないための互換であり、増やしてよいオプションの例外ではない。

    Args:
        repeated: nargs で受けた list（None 可）
        json_form: JSON 配列の文字列（None 可）
        json_flag: エラーメッセージに出すフラグ名

    Returns:
        list: 連結した結果（どちらも無ければ空 list）

    Raises:
        WrapperError: json_form が JSON 配列として解析できない
    """
    merged = list(repeated or [])
    if not json_form:
        return merged
    try:
        parsed = json.loads(json_form)
    except ValueError as e:
        raise WrapperError(
            f"{json_flag} を JSON として解析できません: {e}",
            ErrorCode.INVALID_PATH,
        )
    if not isinstance(parsed, list):
        raise WrapperError(
            f"{json_flag} は JSON 配列である必要があります",
            ErrorCode.INVALID_PATH,
        )
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise WrapperError(
                f"{json_flag} の要素は非空の文字列である必要があります",
                ErrorCode.INVALID_PATH,
            )
    merged.extend(parsed)
    return merged


def _expand_targets(args):
    """対象指定（`--dirs` / `--paths` / それらの JSON 形 / `--paths-file`）を
    prepare 用の paths へ揃える。

    ディレクトリ展開は expand_dirs の責務であり、ラッパーは列挙を自分で書かない。

    Returns:
        tuple: (paths または None, rejected_dirs, warnings)
            paths が None のときは単体モード（prepare が自分で走査する）

    Raises:
        WrapperError: expand_dirs が error を返した / JSON 形の引数が不正
    """
    if not _has_explicit_target(args):
        return None, [], []

    if args.paths_file:
        # paths-file はそのまま prepare へ渡す（展開の対象ではない）
        return None, [], []

    all_dirs = _merge_list_arg(args.dirs, args.dirs_json, "--dirs-json")
    explicit_paths = _merge_list_arg(args.paths, args.paths_json, "--paths-json")
    all_exclude = _merge_list_arg(args.exclude, args.exclude_json, "--exclude-json")

    # 除外は expand_dirs へ渡さない。**確定した対象集合へ最後に 1 回適用する**。
    # ディレクトリ展開の内側だけで適用すると、--dirs を伴わない指定（明示 paths のみ）で
    # 黙って無視される。--exclude は「選び方」ではなく「選んだ結果から何を落とすか」
    # であり、適用点は対象の確定後が正しい（DES-005 §4.2.2）。
    argv = []
    if all_dirs:
        argv.extend(["--dirs-json", json.dumps(all_dirs)])
    if explicit_paths:
        argv.extend(["--paths-json", json.dumps(explicit_paths)])

    if not all_dirs:
        # 展開するディレクトリが無い＝明示 paths のみ。expand_dirs を通す必要がない。
        # 落とした件数は --dirs 経路と同じく warnings に載せる（DES-005 §4.2.2）。
        # 黙って対象から消すと、除外が効いたのか対象が無かったのかを区別できない。
        paths, excluded = filter_excluded(
            explicit_paths, get_project_root(), all_exclude
        )
        warnings = []
        if excluded:
            warnings.append(f"excluded by --exclude: {len(excluded)} path(s)")
        return paths, [], warnings

    _exit_code, payload = call_core(expand_dirs, argv)
    if payload.get("status") == STATUS_ERROR:
        raise WrapperError(
            f"expand_dirs: {payload.get('message')}",
            payload.get("error_code") or ErrorCode.INVALID_PATH,
        )
    paths, excluded = filter_excluded(
        payload.get("paths") or [], get_project_root(), all_exclude
    )
    warnings = list(payload.get("warnings") or [])
    if excluded:
        warnings.append(f"excluded by --exclude: {len(excluded)} path(s)")
    return paths, payload.get("rejected_dirs") or [], warnings


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

    # 0. 矛盾する対象指定を弾く。単体モードは project root 以下を prepare が自分で
    #    走査するため、ディレクトリ・パスの指定と併用しても片方が黙って無視される。
    #    どちらを優先すべきか推定せずエラーにする。
    #
    #    **判定はフラグではなくモードで行う [MANDATORY]**（REQ-001 FR-N04-1 /
    #    DES-005 §10.1）。単体モードへ入る書き方は --all の明示と --key の省略の
    #    2 つがあり、仕様はこれを同義と定めている。args.all だけを見ると、
    #    --key を省いた呼び出しがガードを素通りし、渡した対象指定が prepare の
    #    単体モード分岐（prepare_toc の single_mode）で捨てられる。
    explicit_targets = _explicit_target_flags(args)
    if _is_single_mode(args) and explicit_targets:
        raise WrapperError(
            f"{_single_mode_flag(args)} は project root 以下の全 Markdown を"
            f"対象にするため {' / '.join(explicit_targets)} と併用できない"
            + ("。対象を指定して索引するなら --key <key> を渡す"
               if args.key is None else ""),
            ErrorCode.UNSUPPORTED_ARG,
        )

    # 0a. --paths-file と他の対象指定の併用を弾く（DES-005 §4.2.3）。
    #     --dirs / --paths とそれぞれの JSON 形は連結されるが、--paths-file は
    #     配列をファイルのまま prepare へ渡す経路であり、連結する先が無い。
    #     実装は --paths-file を優先して他を捨てるため、黙って受理すると
    #     「指定したのに索引されない文書がある」状態になる（§4.2.2 の黙殺と同型）。
    #     どちらを優先すべきか推定せずエラーにする。
    if args.paths_file:
        conflicting = [flag for flag in explicit_targets if flag != "--paths-file"]
        if conflicting:
            raise WrapperError(
                f"--paths-file は {' / '.join(conflicting)} と併用できない"
                "（配列をファイルのまま渡す経路であり、連結する先が無い）。"
                "対象をひとつの指定にまとめて実行する",
                ErrorCode.UNSUPPORTED_ARG,
            )

    # 0b. 除外を適用できない経路での --exclude を弾く（DES-005 §4.2.2）。
    #     除外は「確定した対象集合」へ適用する規則だが、次の 2 経路では対象集合が
    #     ラッパーの手元に無い。
    #       単体モード  : prepare が project root 以下を自分で走査する
    #                     （--all の明示と --key の省略の 2 つの入口がある）
    #       --paths-file: 長大な配列を argv に載せないためファイルのまま prepare へ渡す
    #     黙って捨てると「除外したつもりの文書が索引される」ため、拒否して知らせる
    #     （--dirs / --paths 経路では対象集合が確定するので従来どおり適用される）。
    if _merge_list_arg(args.exclude, args.exclude_json, "--exclude-json"):
        blocked = None
        remedy = ""
        if _is_single_mode(args):
            blocked = _single_mode_flag(args)
            remedy = (
                "--key <key> を渡して対象を指定する"
                if args.key is None
                else "--all をやめて --key <key> と --dirs / --paths で対象を渡す"
            )
        elif args.paths_file:
            blocked = "--paths-file"
            remedy = "--paths-file をやめて --dirs / --paths で対象を渡す"
        if blocked:
            raise WrapperError(
                f"--exclude / --exclude-json は {blocked} と併用できない"
                "（対象集合がラッパーの手元に無いため適用できない）。"
                f"{remedy}か、除外を外して実行する",
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
            # 走査で見つかった越境 symlink の承認待ち（--all のみ。NFR-N06）。
            # 書き込みは行われていない。明示指定された対象はここへ来ない。
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
            # **error 状態を解除してから通常の claim 経路に乗せる。**
            #
            # error_pending をそのまま dispatch すると claim/lease の保護が働かない。
            # claim_entries は error_message を持つ entry を reject する（正しい仕様）
            # ため、claim せずに投入することになり、同じコマンドの再実行で同一 entry が
            # 二重投入される。複数の Agent が同じ pending を同時に更新すれば結果が
            # 競合・上書きされる。
            #
            # そこで error_message を消して通常の pending に戻し、以降は
            # next_dispatch（claim あり）に任せる。2 回目の実行では claim 済みの
            # in-flight として扱われ wait になる。
            errored = [item["entry_file"] for item in status["error_pending"]]
            reset_result = reset_error_entries(store_dir, project_root, errored)
            if reset_result["rejected"]:
                warnings.extend(
                    f"reset-error rejected: {item['entry_file']} ({item['reason']})"
                    for item in reset_result["rejected"]
                )
            if not reset_result["reset"]:
                raise WrapperError(
                    "再試行の対象を pending へ戻せなかった。work dir の状態を"
                    "確認するか、toc_store.py --clean-work-dir で破棄して"
                    "やり直す必要がある",
                    ErrorCode.NO_TARGETS,
                )
            warnings.append(
                f"retrying {len(reset_result['reset'])} failed entr(ies); "
                "a permanent failure (a problem in the source document) will "
                "keep failing on every retry"
            )
            # 解除後の状態で再判定し、通常の連続ディスパッチへ合流する
            status = work_status(store_dir, project_root, max_batch=args.max_batch)
            dispatch = next_dispatch(
                store_dir, project_root, key,
                window=args.window, max_batch=args.max_batch, status=status,
            )
            if dispatch["rejected"]:
                warnings.extend(
                    f"claim rejected: {item['entry_file']} ({item['reason']})"
                    for item in dispatch["rejected"]
                )
            return (
                {
                    "action": ACTION_DISPATCH if dispatch["agents"] else ACTION_WAIT,
                    "agents": dispatch["agents"],
                    "in_flight_agents": dispatch["in_flight_agents"],
                    "window": dispatch["window"],
                    "available": dispatch["available"],
                    "pending": len(status["pending"]),
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
        "--dirs-json", dest="dirs_json",
        help="dirs の JSON 配列（上位層からの機械的な受け渡し用。--dirs と併用可）",
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
        help="確定した対象集合から除外するパス・ディレクトリ（--dirs / --paths のどちらでも効く）",
    )
    parser.add_argument(
        "--exclude-json", dest="exclude_json",
        help="exclude の JSON 配列（上位層からの機械的な受け渡し用。--exclude と併用可）",
    )
    # 確認の答えを戻す内部的な通路。上位層との契約ではないため公開引数表には出さない
    # （--all の走査で越境 symlink が見つかったときだけ SKILL が使う）。
    parser.add_argument(
        "--allow-external", dest="allow_external", nargs="*", metavar="SYMLINK",
        help=argparse.SUPPRESS,
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

    # パスの基準を 1 つに固定する。本ラッパーは 1 回の実行で「結合して開く」作法
    # （prepare_toc / merge_toc の hash 計算）と「そのまま開く」作法
    # （fm_to_pending の read_text）の両方を通すため、cwd と project root が違うと
    # 別のファイルを指す。**cwd を変える前に** argv で受けたファイルの位置を絶対
    # パスへ解決する（--paths-file は呼び出し元の cwd 基準で渡され得る。
    # --dirs / --paths は契約上 project-root-relative）。
    if args.paths_file:
        args.paths_file = str(Path(args.paths_file).resolve())
    ensure_project_root_cwd()

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
