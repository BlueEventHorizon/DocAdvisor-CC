#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC ストア共通モジュール（doc-advisor plugin / key + path I/F）

DES-005 §3.1 / §3.2 / §4.1 / §8 を実装する。

責務:
- key → store_dir の決定的変換（safe slug + sha256 サフィックス）
- 予約 key `all` の判定・空 key / 任意 all の reject 用ヘルパ
- JSON 出力契約（emit_json）と error_code enum 定数の集約
- key 単位の promote-pending / clean-work-dir（旧 create_checksums.py から統合）

CLI:
    python3 toc_store.py --key <key> --promote-pending
    python3 toc_store.py --all --promote-pending
    python3 toc_store.py --key <key> --clean-work-dir
    python3 toc_store.py --all --clean-work-dir

標準ライブラリのみ使用（NFR-N01）。
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import (
    get_project_root,
    normalize_path,
    yaml_escape,
    load_entry_file,
    log,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 予約 key（単体モード = 全 Markdown 索引）。ユーザー任意 key としては使えない。
DEFAULT_KEY = "all"

# ストアルート（project root からの相対）
STORE_ROOT_REL = ".claude/doc-advisor/toc"

# work dir / pending / promote 先のファイル名（key 単位ストア配下に閉じる）
WORK_DIRNAME = ".toc_work"

# 限定バッチング（ADR-006 案 B）の既定バッチサイズ。
# 同一ディレクトリ近傍の pending を最大 DEFAULT_MAX_BATCH 件ずつ 1 つの toc-updater に渡す。
# context rot 回避のため小さく保つ（k=2〜3）。1 を指定すれば従来どおりの 1 ファイル 1 起動。
DEFAULT_MAX_BATCH = 3
PENDING_CHECKSUMS_FILENAME = ".toc_checksums_pending.yaml"
CHECKSUMS_FILENAME = ".toc_checksums.yaml"

# prepare → merge の協調で deleted（desired から外れた path）を引き渡すサイドカー。
# store_dir/.toc_work/ 配下に置き、merge が読んで toc.yaml から除去する（DES-005 §6.1 / §6.2 / FR-N02-2）。
DELETED_SIDECAR_FILENAME = ".deleted.json"

# prepare → merge の協調で「desired 0 件（空 repo / 対象 0 件）」の意図を引き渡すサイドカー。
# prepare が desired 0 件を検出した場合に store_dir/.toc_work/ 配下へ残し、merge は
# pending も既存 toc も無い場合でもこのマーカーがあれば空 toc.yaml を冪等出力する
# （DES-005 §9.2 / §9.3 / REQ-001 NFR-N05 / 受け入れ基準「空 repo で空 ToC を冪等出力」）。
# これにより「prepare 実行済みで desired 0 件（空にすべき）」と「prepare 未実行で
# 何も準備されていない（NO_TARGETS）」を痕跡で区別し取り違えを防ぐ。
EMPTY_INTENT_SIDECAR_FILENAME = ".empty_intent"

# slug の最大長（DES-005 §3.1）
SLUG_MAX_LEN = 40

# sha256 サフィックスの桁数（DES-005 §3.1）
HASH_SUFFIX_LEN = 12


class ErrorCode:
    """JSON 出力契約の error_code enum（DES-005 §8.1 / §8.2）。

    テストで enum を固定する（FR-N08-2）。null は None で表現する。
    """

    INVALID_PATH = "INVALID_PATH"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    ABSOLUTE_PATH = "ABSOLUTE_PATH"
    OUTSIDE_ROOT = "OUTSIDE_ROOT"
    NOT_FOUND = "NOT_FOUND"
    NOT_MARKDOWN = "NOT_MARKDOWN"
    KEY_EMPTY = "KEY_EMPTY"
    KEY_RESERVED = "KEY_RESERVED"
    TOC_NOT_FOUND = "TOC_NOT_FOUND"
    NO_TARGETS = "NO_TARGETS"
    UNSUPPORTED_ARG = "UNSUPPORTED_ARG"


# error_code の有効値集合（None を含む）。テスト・バリデーションで参照する。
ERROR_CODES = frozenset({
    ErrorCode.INVALID_PATH,
    ErrorCode.PATH_TRAVERSAL,
    ErrorCode.ABSOLUTE_PATH,
    ErrorCode.OUTSIDE_ROOT,
    ErrorCode.NOT_FOUND,
    ErrorCode.NOT_MARKDOWN,
    ErrorCode.KEY_EMPTY,
    ErrorCode.KEY_RESERVED,
    ErrorCode.TOC_NOT_FOUND,
    ErrorCode.NO_TARGETS,
    ErrorCode.UNSUPPORTED_ARG,
})

# status の有効値集合（DES-005 §8.2）。
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial"
# needs_confirmation: 未承認の root 外 symlink があり、上位層の承認を待つ状態（NFR-N06）。
# error ではなく、--allow-external-json での再実行を促す中間状態。
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
STATUSES = frozenset({
    STATUS_OK,
    STATUS_ERROR,
    STATUS_PARTIAL,
    STATUS_NEEDS_CONFIRMATION,
})


class KeyError_(ValueError):
    """key 検証エラー。error_code を保持する。

    （組み込み KeyError と区別するため末尾アンダースコア）
    """

    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# key → 保存パス変換（DES-005 §3.1 / FR-N01-3）
# ---------------------------------------------------------------------------

def _slugify(key):
    """key を safe slug に変換する（DES-005 §3.1）。

    手順:
    1. NFC 正規化（既存 normalize_path 流用）
    2. 英小文字化
    3. [a-z0-9_-] 以外を '_' に置換
    4. 連続 '_' を圧縮
    5. 40 文字で切り詰め
    6. 空になる場合は 'k'

    Args:
        key: original key（NFC 正規化前でよい）

    Returns:
        str: slug（store_dir の識別子。同一 key は常に同一 slug に変換される）
    """
    normalized = normalize_path(key).lower()

    out_chars = []
    prev_underscore = False
    for ch in normalized:
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in ("-",):
            out_chars.append(ch)
            prev_underscore = False
        else:
            # '_' を含むそれ以外の文字はすべて '_' へ。連続は圧縮。
            if not prev_underscore:
                out_chars.append("_")
                prev_underscore = True

    slug = "".join(out_chars)
    # 先頭・末尾の '_' は見た目のため除去（slug = store_dir 名そのものなので整形しても安全）
    slug = slug.strip("_")
    slug = slug[:SLUG_MAX_LEN]
    slug = slug.strip("_")

    if not slug:
        return "k"
    return slug


def _key_hash(key):
    """original key 全体の sha256 から 12 桁 hex サフィックスを得る（DES-005 §3.1）。"""
    normalized = normalize_path(key)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:HASH_SUFFIX_LEN]


def store_root(project_root=None):
    """ストアルート（keys/）の絶対パスを返す。"""
    if project_root is None:
        project_root = get_project_root()
    return Path(project_root) / STORE_ROOT_REL


def resolve_store_dir(key, project_root=None):
    """key から store_dir を決定的に解決する（DES-005 §3.1 / FR-N01-3）。

    store_dir(key) = {project_root}/.claude/doc-advisor/toc/{slug}-{sha256(key)[:12]}/

    slug が衝突しても sha256 サフィックスで別ディレクトリに解決される。

    Args:
        key: original key（空文字は呼び出し側で validate_key により reject 済みである前提だが、
             本関数は決定的変換のみを行い検証はしない）
        project_root: プロジェクトルート（省略時は get_project_root()）

    Returns:
        Path: store_dir の絶対パス（存在は保証しない）
    """
    slug = _slugify(key)
    suffix = _key_hash(key)
    return store_root(project_root) / f"{slug}-{suffix}"


# ---------------------------------------------------------------------------
# key 検証（DES-005 §3.3 / FR-N01-5）
# ---------------------------------------------------------------------------

def is_reserved_key(key):
    """予約 key `all` かどうかを判定する（DES-005 §4.3）。

    NFC 正規化して比較する。
    """
    if key is None:
        return False
    return normalize_path(key) == DEFAULT_KEY


def validate_user_key(key):
    """ユーザーが任意指定した key を検証する（DES-005 §3.3 / FR-N01-5）。

    呼び出し側（CLI の --key 指定）が使うヘルパ。
    - 空 key → KeyError_(KEY_EMPTY)
    - 任意の `all` 指定 → KeyError_(KEY_RESERVED)
    - 過長 / Unicode → reject しない（slug 切り詰めで吸収）

    予約 key `all` への到達は `--all` / `--key` 省略のみが許される。
    その経路は本関数を通さず DEFAULT_KEY を直接使う（呼び出し側で区別）。

    Args:
        key: ユーザー指定 key

    Returns:
        str: NFC 正規化済み key

    Raises:
        KeyError_: 空 key または任意 all 指定
    """
    if key is None or normalize_path(key).strip() == "":
        raise KeyError_("key must not be empty", ErrorCode.KEY_EMPTY)

    normalized = normalize_path(key)
    if normalized == DEFAULT_KEY:
        raise KeyError_(
            f"'{DEFAULT_KEY}' is a reserved key and cannot be used as a user key; "
            "use --all (or omit --key) for single mode",
            ErrorCode.KEY_RESERVED,
        )
    return normalized




# ---------------------------------------------------------------------------
# JSON 出力契約（DES-005 §8 / FR-N08）
# ---------------------------------------------------------------------------

def emit_json(
    status,
    *,
    error_code=None,
    message=None,
    key=None,
    toc_path=None,
    normalized_paths=None,
    rejected_paths=None,
    counts=None,
    deleted_paths=None,
    warnings=None,
    external_pending=None,
    extra=None,
    stream=None,
):
    """stdout に単一 JSON を出力する（DES-005 §8.1 / FR-N08-1）。

    status / error_code は必須フィールド（error_code は値が無ければ null）。
    その他のフィールドは指定されたもののみ出力する。
    ログ・進捗は stderr（toc_utils.log）を使う。

    Args:
        status: 'ok' / 'error' / 'partial'
        error_code: ErrorCode のいずれか、または None
        message: human-readable メッセージ
        key: original key
        toc_path: toc.yaml の project-relative パス
        normalized_paths: 正規化済み path リスト
        rejected_paths: [{path, reason}] のリスト
        counts: {added, updated, deleted, unchanged} の dict
        deleted_paths: 削除された path のリスト（merge の FR-N02-4）
        warnings: warning 文字列リスト
        external_pending: 未承認の越境 symlink リスト
            [{symlink, resolved, affected_count}]（needs_confirmation 時。NFR-N06）
        extra: 追加フィールドの dict（payload にマージ）。work-status 出力等に使う
        stream: 出力先（省略時 sys.stdout。テスト用）
    """
    payload = {
        "status": status,
        "error_code": error_code,
    }
    if message is not None:
        payload["message"] = message
    if key is not None:
        payload["key"] = key
    if toc_path is not None:
        payload["toc_path"] = toc_path
    if normalized_paths is not None:
        payload["normalized_paths"] = normalized_paths
    if rejected_paths is not None:
        payload["rejected_paths"] = rejected_paths
    if counts is not None:
        payload["counts"] = counts
    if deleted_paths is not None:
        payload["deleted_paths"] = deleted_paths
    if warnings is not None:
        payload["warnings"] = warnings
    if external_pending is not None:
        payload["external_pending"] = external_pending
    if extra is not None:
        payload.update(extra)

    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(payload, ensure_ascii=False))
    out.write("\n")


def toc_path_rel(store_dir, project_root=None):
    """store_dir 配下の toc.yaml を project-relative 文字列で返す（JSON 出力用）。"""
    if project_root is None:
        project_root = get_project_root()
    toc_abs = Path(store_dir) / "toc.yaml"
    try:
        return normalize_path(toc_abs.relative_to(Path(project_root)))
    except ValueError:
        return normalize_path(toc_abs)


# ---------------------------------------------------------------------------
# promote / clean（key 単位。旧 create_checksums.py から統合 / DES-005 §4.1）
# ---------------------------------------------------------------------------

def promote_pending(store_dir):
    """pending checksums を active checksums に昇格する（key 単位）。

    {store_dir}/.toc_work/.toc_checksums_pending.yaml
        → {store_dir}/.toc_checksums.yaml

    Args:
        store_dir: store_dir の Path

    Returns:
        bool: True on success, False on failure（pending 不在は失敗）
    """
    store_dir = Path(store_dir)
    pending = store_dir / WORK_DIRNAME / PENDING_CHECKSUMS_FILENAME
    checksums_file = store_dir / CHECKSUMS_FILENAME

    if not pending.exists():
        log(f"Error: Pending checksums not found: {pending}")
        return False

    try:
        checksums_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(pending), str(checksums_file))
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to promote pending checksums: {e}")
        return False

    log(f"Promoted: {pending} -> {checksums_file}")
    return True


def clean_work_dir(store_dir):
    """work directory を削除する（key 単位。不在時も冪等に成功）。

    Args:
        store_dir: store_dir の Path

    Returns:
        bool: True on success（不在時もスキップして True）
    """
    store_dir = Path(store_dir)
    work_dir = store_dir / WORK_DIRNAME

    if not work_dir.exists():
        log(f"Work directory not found (skip): {work_dir}")
        return True

    try:
        shutil.rmtree(str(work_dir))
    except (OSError, PermissionError) as e:
        log(f"Error: Failed to clean work directory: {work_dir} - {e}")
        return False

    log(f"Cleaned: {work_dir}")
    return True


def _entry_file_rel(filepath, project_root):
    """entry_file を project-root 相対の POSIX 文字列で返す（外なら絶対）。"""
    try:
        return normalize_path(Path(filepath).relative_to(Path(project_root)))
    except ValueError:
        return normalize_path(Path(filepath))


def _source_dir(source_file):
    """source_file（project-root 相対 POSIX 文字列）の親ディレクトリを返す。

    トップレベル文書（親なし）は "" を返す。グルーピングの近傍判定キーに使う。
    """
    if not source_file:
        return ""
    return normalize_path(Path(source_file).parent) if Path(source_file).parent != Path(".") else ""


def group_pending_by_dir(pending_entries, max_batch=DEFAULT_MAX_BATCH):
    """pending を同一ディレクトリ近傍で最大 max_batch 件ずつにまとめる（ADR-006 案 B）。

    context rot 回避のため、主題が近い「同一ディレクトリの文書」だけを 1 グループにする。
    異なるディレクトリの文書は混ぜない。グルーピングは決定論的（AI に手作業させない）。

    Args:
        pending_entries (list[dict]): [{"entry_file": str, "source_file": str|None}]
            （work_status が pending として確定した entry の順序を保持）
        max_batch (int): 1 グループの最大件数。1 なら従来どおり 1 件 1 グループ。

    Returns:
        list[list[str]]: entry_file のグループ列。各グループは同一ディレクトリ・最大 max_batch 件。
            source_file 不明（読めなかった pending）の entry は単独グループにする。
    """
    if max_batch < 1:
        max_batch = 1
    # 近傍が隣接するよう (dir, source_file, entry_file) で安定ソートする。
    # source_file 不明は dir を entry_file 基準にし、必ず単独グループへ落とす。
    decorated = []
    for e in pending_entries:
        src = e.get("source_file")
        if src:
            decorated.append((_source_dir(src), src, e["entry_file"], False))
        else:
            decorated.append((e["entry_file"], e["entry_file"], e["entry_file"], True))
    decorated.sort(key=lambda t: (t[0], t[1], t[2]))

    groups = []
    current = []
    current_dir = None
    for dir_key, _src, entry_file, is_unknown in decorated:
        if is_unknown:
            # 近傍不明は他と混ぜず単独で確定
            if current:
                groups.append(current)
                current = []
                current_dir = None
            groups.append([entry_file])
            continue
        if dir_key != current_dir or len(current) >= max_batch:
            if current:
                groups.append(current)
            current = [entry_file]
            current_dir = dir_key
        else:
            current.append(entry_file)
    if current:
        groups.append(current)
    return groups


def work_status(store_dir, project_root, max_batch=DEFAULT_MAX_BATCH):
    """key の `.toc_work/` 状態と継続判定を返す（決定論・純粋関数 / index-docs Step 0・2）。

    index-docs SKILL が AI に手作業させていた「`.toc_work` 有無判定 / pending 列挙 /
    completed・error 分類 / 継続判定 / バッチ・グルーピング」を script 化する
    （Issue #22 A1 / Issue #27 案 B）。

    Args:
        store_dir: store_dir の Path
        project_root: project root（entry_file を相対化するため）
        max_batch: 限定バッチング（案 B）の 1 グループ最大件数。1 で従来挙動。

    Returns:
        dict:
            has_work_dir (bool): `.toc_work/` が存在するか
            pending (list[str]): 未充填 entry_file（project-root 相対）。toc-updater 起動対象
            pending_groups (list[list[str]]): pending を同一ディレクトリ近傍で max_batch 件ずつ
                まとめたグループ列（案 B）。各グループを 1 つの toc-updater に渡す
            max_batch (int): 適用したバッチ最大件数
            completed (int): status == 'completed' の件数
            error_pending (list[dict]): [{entry_file, error_message}]（充填試行済みエラー）
            next_action (str):
                'prepare' — work-dir なし
                'fill'    — 充填可能な pending あり
                'blocked' — 充填可能 pending は無いが error_pending あり。**silent merge 禁止**。
                            merge は completed のみ採用し成功時に .toc_work を削除するため、
                            errored doc は今回 ToC から脱落し、**updated doc は現内容 checksum が
                            書かれて次回も再索引されず stale 固定**になる。上位層が
                            retry / 承知で merge / 中止 を選ぶ（Issue #22 レビュー対応）。
                'merge'   — pending も error_pending も無い（全 completed / 空）
    """
    store_dir = Path(store_dir)
    work_dir = store_dir / WORK_DIRNAME
    result = {
        "has_work_dir": work_dir.exists(),
        "pending": [],
        "pending_groups": [],
        "max_batch": max_batch,
        "completed": 0,
        "error_pending": [],
        "next_action": "prepare",
    }
    if not work_dir.exists():
        return result

    # 隠しファイル（.toc_checksums_pending.yaml / .deleted.json 等）は entry でないため除外。
    # 決定的順序（merge と同一の sorted）で列挙する。
    yaml_files = sorted(
        f for f in work_dir.glob("*.yaml") if not f.name.startswith(".")
    )
    pending_entries = []  # [{entry_file, source_file}]（グルーピング用に source_file を保持）
    for filepath in yaml_files:
        rel = _entry_file_rel(filepath, project_root)
        try:
            meta, _entry = load_entry_file(filepath)
        except IOError:
            # 読めない pending は要再処理として pending に含める（取りこぼし防止）。
            # source_file 不明のため近傍判定できず、単独グループになる。
            result["pending"].append(rel)
            pending_entries.append({"entry_file": rel, "source_file": None})
            continue
        error_message = meta.get("error_message")
        status = meta.get("status")
        if error_message:
            result["error_pending"].append(
                {"entry_file": rel, "error_message": error_message}
            )
        elif status == "completed":
            result["completed"] += 1
        else:
            result["pending"].append(rel)
            pending_entries.append(
                {"entry_file": rel, "source_file": meta.get("source_file")}
            )

    result["pending_groups"] = group_pending_by_dir(pending_entries, max_batch)

    # 継続判定:
    #   pending あり          → fill
    #   pending 無 + error あり → blocked（silent merge せず上位層が判断。脱落/stale 防止）
    #   どちらも無し           → merge
    if result["pending"]:
        result["next_action"] = "fill"
    elif result["error_pending"]:
        result["next_action"] = "blocked"
    else:
        result["next_action"] = "merge"
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Key-based ToC store helper (promote pending / clean work dir)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--key", help="User-specified key (opaque)")
    group.add_argument(
        "--all", action="store_true",
        help="Single mode: resolve to reserved key 'all'",
    )
    parser.add_argument(
        "--promote-pending", action="store_true",
        help="Promote pending checksums to active checksums file",
    )
    parser.add_argument(
        "--clean-work-dir", action="store_true",
        help="Remove the work directory",
    )
    parser.add_argument(
        "--work-status", action="store_true",
        help="Emit .toc_work status (pending entry_files / completed / next_action) as JSON",
    )
    parser.add_argument(
        "--max-batch", type=int, default=DEFAULT_MAX_BATCH,
        help=(
            "Limited batching group size for --work-status pending_groups "
            f"(ADR-006 plan B; default {DEFAULT_MAX_BATCH}, 1 = one file per updater)"
        ),
    )
    return parser.parse_args(argv)


def resolve_key_from_args(args):
    """CLI 引数から実効 key を決定する（FR-N04-4 / §3.3）。

    - --all または --key 省略 → 予約 key 'all'（reject しない）
    - --key <k> → validate_user_key（空 / 任意 all を reject）

    Returns:
        str: NFC 正規化済みの実効 key

    Raises:
        KeyError_: 空 key / 任意 all 指定
    """
    if args.all or args.key is None:
        return DEFAULT_KEY
    return validate_user_key(args.key)


def main(argv=None):
    args = parse_args(argv)

    if not args.promote_pending and not args.clean_work_dir and not args.work_status:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.NO_TARGETS,
            message="No action specified (use --work-status / --promote-pending / --clean-work-dir)",
        )
        return 1

    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    project_root = get_project_root()
    store_dir = resolve_store_dir(key, project_root)

    # --work-status は読み取り専用。promote/clean とは独立に処理して即返す。
    if args.work_status:
        status = work_status(store_dir, project_root, max_batch=args.max_batch)
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_path_rel(store_dir, project_root),
            extra=status,
        )
        return 0

    ok = True
    if args.promote_pending:
        ok = promote_pending(store_dir) and ok
    if args.clean_work_dir:
        ok = clean_work_dir(store_dir) and ok

    if ok:
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_path_rel(store_dir, project_root),
        )
        return 0

    emit_json(
        STATUS_ERROR,
        error_code=ErrorCode.NOT_FOUND,
        message="promote/clean operation failed",
        key=key,
        toc_path=toc_path_rel(store_dir, project_root),
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
