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
STORE_ROOT_REL = ".claude/.doc-advisor/toc"

# work dir / pending / promote 先のファイル名（key 単位ストア配下に閉じる）
WORK_DIRNAME = ".toc_work"

# 限定バッチング（ADR-006 案 B）の既定バッチサイズ。
# 同一ディレクトリ近傍の pending を最大 DEFAULT_MAX_BATCH 件ずつ 1 つの toc-updater に渡す。
# context rot 回避のため小さく保つ（k=2〜3）。1 を指定すれば従来どおりの 1 ファイル 1 起動。
DEFAULT_MAX_BATCH = 3

# claim/lease（ADR-006 連続ディスパッチ）の既定リース TTL（秒）。
# 連続ディスパッチで entry を投入する際 claimed_at をスタンプし、work_status は有効リース内の
# entry（in-flight）を pending から除外して二重投入を防ぐ。停止した agent の stale lease は
# この TTL 超過で自動回収（再投入対象に戻す）。1 件最大 ~41s に対し十分な余裕を取る。
DEFAULT_LEASE_TTL_SEC = 900
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
    # 鮮度確認（check-toc / DES-009 §5.2）。
    # INVALID_MAX_AGE は引数値の不正であり、未対応引数の UNSUPPORTED_ARG とは分けて診断する。
    INVALID_MAX_AGE = "INVALID_MAX_AGE"
    # TOC_READ_ERROR は toc.yaml を読めない状態。ToC 不在は error ではないため
    # TOC_NOT_FOUND とは別（check-toc では不在を freshness=stale として返す）。
    TOC_READ_ERROR = "TOC_READ_ERROR"
    # READ_ERROR は対象文書そのものを読めない状態（権限不足・デコード不能等）。
    # 不在は NOT_FOUND、toc.yaml の読み取り失敗は TOC_READ_ERROR と区別する。
    READ_ERROR = "READ_ERROR"


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
    ErrorCode.INVALID_MAX_AGE,
    ErrorCode.TOC_READ_ERROR,
    ErrorCode.READ_ERROR,
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

    store_dir(key) = {project_root}/.claude/.doc-advisor/toc/{slug}-{sha256(key)[:12]}/

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


# ---------------------------------------------------------------------------
# claim / lease（ADR-006 連続ディスパッチ。決定論は script、判断は AI の原則）
# ---------------------------------------------------------------------------

# entry YAML の _meta に書く claim タイムスタンプのキー。
# completed / error 化時に write_pending.py が _meta を再構築するため自然に消える
# （pending のまま投入された entry にのみ残る）。
CLAIMED_AT_KEY = "claimed_at"
_LEASE_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # write_pending.py の updated_at と同形式


def _utc_now_iso(now=None):
    """UTC の現在時刻（or 注入された now）を ISO 8601 文字列で返す。"""
    dt = now if now is not None else datetime.now(timezone.utc)
    return dt.strftime(_LEASE_TS_FORMAT)


def _parse_lease_ts(value):
    """claimed_at 文字列を aware datetime に。パース不能・空は None（= unclaimed 扱い）。"""
    if not value:
        return None
    try:
        return datetime.strptime(value, _LEASE_TS_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _is_active_lease(claimed_at, now, lease_ttl):
    """claimed_at が現在時刻 now から見て有効リース内（in-flight）かを判定する。

    未 claim・パース不能・TTL 超過（stale）はすべて False（= pending 再投入対象）。
    安全側に倒す: 不正な claimed_at で永久ブロックさせない。
    """
    claimed = _parse_lease_ts(claimed_at)
    if claimed is None:
        return False
    return (now - claimed).total_seconds() < lease_ttl


def _stamp_claimed_at(filepath, claimed_iso):
    """entry YAML の `_meta` ブロックに claimed_at を upsert する（本体は一切触らない）。

    pending テンプレート（title: null / content_details: [] 等）を壊さないよう、
    行レベルで `_meta:` 配下に `claimed_at:` 行を追加/置換し、原子的に書き戻す。
    """
    path = Path(filepath)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    out = []
    in_meta = False
    done = False
    for line in lines:
        stripped = line.strip()
        if not done and not in_meta and stripped == "_meta:":
            in_meta = True
            out.append(line)
            continue
        if in_meta and not done:
            is_meta_field = (
                line.startswith("  ") and ":" in stripped and not stripped.startswith("#")
            )
            if is_meta_field:
                key = stripped.partition(":")[0].strip()
                if key == CLAIMED_AT_KEY:
                    out.append(f"  {CLAIMED_AT_KEY}: {claimed_iso}")  # 既存を置換
                    done = True
                    in_meta = False
                    continue
                out.append(line)
                continue
            # _meta ブロック終端（インデントが切れた）。終端直前に追加。
            out.append(f"  {CLAIMED_AT_KEY}: {claimed_iso}")
            done = True
            in_meta = False
            out.append(line)
            continue
        out.append(line)
    if in_meta and not done:
        # ファイルが _meta ブロックだけで終わっていた場合
        out.append(f"  {CLAIMED_AT_KEY}: {claimed_iso}")
        done = True

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    tmp.replace(path)  # os.replace 相当のアトミック差し替え


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


def work_status(store_dir, project_root, max_batch=DEFAULT_MAX_BATCH,
                now=None, lease_ttl=DEFAULT_LEASE_TTL_SEC):
    """key の `.toc_work/` 状態と継続判定を返す（決定論 / index-docs Step 0・2）。

    index-docs SKILL が AI に手作業させていた「`.toc_work` 有無判定 / pending 列挙 /
    completed・error 分類 / 継続判定 / バッチ・グルーピング」を script 化する
    （Issue #22 A1 / Issue #27 案 B）。連続ディスパッチ（ADR-006 / Issue #29）では
    有効リース中（in-flight）の entry を pending から除外し二重投入を防ぐ。

    Args:
        store_dir: store_dir の Path
        project_root: project root（entry_file を相対化するため）
        max_batch: 限定バッチング（案 B）の 1 グループ最大件数。1 で従来挙動。
        now: 現在時刻（aware datetime）。テスト注入用。未指定なら UTC now。
        lease_ttl: claim の有効秒数。これを超えた claimed_at は stale として pending に戻す。

    Returns:
        dict:
            has_work_dir (bool): `.toc_work/` が存在するか
            pending (list[str]): 未充填かつ未 claim（or stale）な entry_file。toc-updater 起動対象
            pending_groups (list[list[str]]): pending を同一ディレクトリ近傍で max_batch 件ずつ
                まとめたグループ列（案 B）。各グループを 1 つの toc-updater に渡す
            max_batch (int): 適用したバッチ最大件数
            in_flight (list[str]): 有効リース中（claim 済み・TTL 内）の entry_file（フラット）
            in_flight_groups (list[list[str]]): in_flight を同一ディレクトリ近傍で max_batch 件ずつ
                まとめたグループ列。`len(in_flight_groups)` = 走行中 Agent 数（1 グループ = 1 Agent）。
                連続ディスパッチの空きスロット計算は `window - len(in_flight_groups)` を使う
                （`len(in_flight)` は entry 数なので Agent 数として使ってはならない）
            completed (int): status == 'completed' の件数
            error_pending (list[dict]): [{entry_file, error_message}]（充填試行済みエラー）
            next_action (str):
                'prepare' — work-dir なし
                'fill'    — 投入可能な pending（未 claim or stale）あり
                'wait'    — 投入可能 pending は無いが in_flight あり（完了待ち。merge/blocked はまだ）
                'blocked' — pending も in_flight も無いが error_pending あり。**silent merge 禁止**。
                            merge は completed のみ採用し成功時に .toc_work を削除するため、
                            errored doc は今回 ToC から脱落し、**updated doc は現内容 checksum が
                            書かれて次回も再索引されず stale 固定**になる。上位層が
                            retry / 承知で merge / 中止 を選ぶ（Issue #22 レビュー対応）。
                'merge'   — pending・in_flight・error_pending すべて無い（全 completed / 空）
    """
    if now is None:
        now = datetime.now(timezone.utc)
    store_dir = Path(store_dir)
    work_dir = store_dir / WORK_DIRNAME
    result = {
        "has_work_dir": work_dir.exists(),
        "pending": [],
        "pending_groups": [],
        "max_batch": max_batch,
        "in_flight": [],
        "in_flight_groups": [],
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
    in_flight_entries = []  # 同上（in_flight を Agent 単位グループに再構成するため）
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
        elif _is_active_lease(meta.get(CLAIMED_AT_KEY), now, lease_ttl):
            # 有効リース中（連続ディスパッチで投入済み・完了待ち）。pending に含めない。
            result["in_flight"].append(rel)
            in_flight_entries.append(
                {"entry_file": rel, "source_file": meta.get("source_file")}
            )
        else:
            # 未 claim or stale lease → 投入対象 pending
            result["pending"].append(rel)
            pending_entries.append(
                {"entry_file": rel, "source_file": meta.get("source_file")}
            )

    # in_flight を pending と同じ決定論グルーピングで Agent 単位に再構成する。
    # claim は pending_groups（同じ group_pending_by_dir 出力）に従って行うため、
    # in_flight 全体の再グループ化は claim グループ境界と一致し、グループ数 = 走行中 Agent 数になる。
    result["pending_groups"] = group_pending_by_dir(pending_entries, max_batch)
    result["in_flight_groups"] = group_pending_by_dir(in_flight_entries, max_batch)

    # 継続判定:
    #   pending あり            → fill（空きスロットへ投入可。in_flight 併存でも fill 優先）
    #   pending 無 + in_flight  → wait（完了待ち。silent merge も blocked も避ける）
    #   上記なし + error あり    → blocked（silent merge せず上位層が判断。脱落/stale 防止）
    #   すべて無し               → merge
    if result["pending"]:
        result["next_action"] = "fill"
    elif result["in_flight"]:
        result["next_action"] = "wait"
    elif result["error_pending"]:
        result["next_action"] = "blocked"
    else:
        result["next_action"] = "merge"
    return result


def claim_entries(store_dir, project_root, entry_files,
                  now=None, lease_ttl=DEFAULT_LEASE_TTL_SEC):
    """指定 entry_files を claim（claimed_at スタンプ）する（連続ディスパッチの投入直前に呼ぶ）。

    既に有効リース中（in-flight）の entry は二重 claim を拒否する。stale lease / 未 claim は
    claim 可（stale は再投入）。completed / error_pending / 不在 / 読込不能は claim 対象外。
    決定論は script、ループ制御（どれを投入するか）は呼び出し側（orchestrator）の判断。

    Args:
        store_dir: store_dir の Path
        project_root: project root（entry_file 解決・相対化用）
        entry_files: claim 対象 entry_file のリスト（project-root 相対 or 絶対）。
            この key の `store_dir/.toc_work/` 配下に限る（外は outside_work_dir で reject）。
        now: 現在時刻（aware datetime）。テスト注入用。未指定なら UTC now。
        lease_ttl: 既存 claim を in-flight と見なす有効秒数。

    Returns:
        dict: {"claimed": [rel...], "rejected": [{"entry_file": rel, "reason": str}...]}
            reason: outside_work_dir / not_found / read_error / error_pending /
                    completed / already_claimed
    """
    if now is None:
        now = datetime.now(timezone.utc)
    claimed_iso = _utc_now_iso(now)
    project_root = Path(project_root)
    # claim 対象はこの key の .toc_work/ 配下に限定する（key 単位ストア分離の保全・
    # traversal による無関係 YAML への書き込み防止）。--claim は work_status が返した
    # pending_groups 専用の操作であり、配下外を claim する正当な経路は無い。
    work_dir = (Path(store_dir) / WORK_DIRNAME).resolve()
    result = {"claimed": [], "rejected": []}
    for ef in entry_files:
        path = Path(ef)
        if not path.is_absolute():
            path = project_root / ef
        rel = _entry_file_rel(path, project_root)
        try:
            path.resolve().relative_to(work_dir)
        except ValueError:
            # resolve は成功したが work_dir 配下でない（別 key / traversal で外を指す）
            result["rejected"].append({"entry_file": rel, "reason": "outside_work_dir"})
            continue
        except (OSError, RuntimeError):
            # 壊れた / ループ symlink 等で resolve 自体が失敗。配下と確認できないため
            # 安全側で reject（CLI をクラッシュさせず JSON 契約を保つ）。
            result["rejected"].append({"entry_file": rel, "reason": "outside_work_dir"})
            continue
        if not path.exists():
            result["rejected"].append({"entry_file": rel, "reason": "not_found"})
            continue
        try:
            meta, _entry = load_entry_file(path)
        except IOError:
            result["rejected"].append({"entry_file": rel, "reason": "read_error"})
            continue
        if meta.get("error_message"):
            result["rejected"].append({"entry_file": rel, "reason": "error_pending"})
            continue
        if meta.get("status") == "completed":
            result["rejected"].append({"entry_file": rel, "reason": "completed"})
            continue
        if _is_active_lease(meta.get(CLAIMED_AT_KEY), now, lease_ttl):
            result["rejected"].append({"entry_file": rel, "reason": "already_claimed"})
            continue
        _stamp_claimed_at(path, claimed_iso)
        result["claimed"].append(rel)
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
    parser.add_argument(
        "--claim", nargs="+", metavar="ENTRY_FILE",
        help=(
            "Claim one or more pending entry_files (stamp claimed_at) before dispatching "
            "a toc-updater in continuous-dispatch mode (ADR-006 / Issue #29). Emits "
            "claimed/rejected JSON. Already in-flight entries are rejected (no double-dispatch)."
        ),
    )
    parser.add_argument(
        "--lease-ttl", type=int, default=DEFAULT_LEASE_TTL_SEC,
        help=(
            "Lease TTL in seconds for claim/in-flight detection in --work-status / --claim "
            f"(default {DEFAULT_LEASE_TTL_SEC}). Claims older than this are stale and re-dispatchable."
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

    if (not args.promote_pending and not args.clean_work_dir
            and not args.work_status and not args.claim):
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.NO_TARGETS,
            message=(
                "No action specified "
                "(use --work-status / --claim / --promote-pending / --clean-work-dir)"
            ),
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
        status = work_status(
            store_dir, project_root, max_batch=args.max_batch, lease_ttl=args.lease_ttl
        )
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_path_rel(store_dir, project_root),
            extra=status,
        )
        return 0

    # --claim は連続ディスパッチの投入直前に呼ぶ。claimed/rejected を JSON で返す。
    if args.claim:
        claim_result = claim_entries(
            store_dir, project_root, args.claim, lease_ttl=args.lease_ttl
        )
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_path_rel(store_dir, project_root),
            extra=claim_result,
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
