#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC ストア共通モジュール（doc-advisor plugin / key + path I/F）

DES-005 §3.1 / §3.2 / §4.1 / §8 を実装する。

責務:
- key → store_dir の決定的変換（safe slug + sha256 サフィックス）
- meta.yaml の I/O（original_key 保持・schema_version）
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
    log,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 予約 key（単体モード = 全 Markdown 索引）。ユーザー任意 key としては使えない。
DEFAULT_KEY = "all"

# ストアルート（project root からの相対）
STORE_ROOT_REL = ".claude/doc-advisor/toc/keys"

# meta.yaml のスキーマバージョン
SCHEMA_VERSION = 1

# meta.yaml ファイル名
META_FILENAME = "meta.yaml"

# work dir / pending / promote 先のファイル名（key 単位ストア配下に閉じる）
WORK_DIRNAME = ".toc_work"
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
})

# status の有効値集合（DES-005 §8.2）。
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial"
STATUSES = frozenset({STATUS_OK, STATUS_ERROR, STATUS_PARTIAL})


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
        str: slug（人間可読性のための前置詞。識別はサフィックスが担う）
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
    # 先頭・末尾の '_' は見た目のため除去（識別はサフィックスが担うため安全）
    slug = slug.strip("_")
    slug = slug[:SLUG_MAX_LEN]
    slug = slug.strip("_")

    if not slug:
        return "k"
    return slug


def _key_hash(key):
    """original key 全体の sha256 から 12 桁 hex サフィックスを得る（DES-005 §3.1）。

    NFC 正規化後の key を対象とし、正規化前後の差で別ディレクトリに
    解決されないようにする（Unicode key の冪等性）。
    """
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

    store_dir(key) = {project_root}/.claude/doc-advisor/toc/keys/{slug}-{sha256(key)[:12]}/

    衝突しない根拠: サフィックスは original key 全体の SHA-256 から導出するため、
    slug が衝突しても別ディレクトリに解決される。

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
    - 過長 / Unicode → reject しない（slug 切り詰め + hash で吸収）

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
# meta.yaml I/O（DES-005 §3.2 / FR-N01-4）
# ---------------------------------------------------------------------------

def write_meta(store_dir, original_key):
    """meta.yaml を書き出す（original_key / created_at / schema_version）。

    既存 meta.yaml がある場合、created_at は据え置く（再生成で初回作成日時を保つ）。

    Args:
        store_dir: store_dir の Path
        original_key: 保持する original key

    Returns:
        bool: True on success, False on failure
    """
    store_dir = Path(store_dir)
    meta_path = store_dir / META_FILENAME

    created_at = None
    existing = read_meta(store_dir)
    if existing:
        created_at = existing.get("created_at")
    if not created_at:
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "# doc-advisor key ToC store metadata",
        "# Auto-generated - do not edit",
        f"original_key: {yaml_escape(normalize_path(original_key))}",
        f"created_at: {created_at}",
        f"schema_version: {SCHEMA_VERSION}",
    ]
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to write meta.yaml: {meta_path} - {e}")
        return False


def _unescape_yaml_value(value):
    """meta.yaml の値を `toc_utils.yaml_escape` と対称にデコードする。

    `write_meta` は値を `yaml_escape` で書き出す。`yaml_escape` は引用符が
    必要な値のみ `"..."` で囲み、内部を `\\` → `\\\\` / `"` → `\\"` /
    改行 → `\\n` / CR → `\\r` / タブ → `\\t` の順でエスケープする。引用符が
    不要な素の値（プレーンスカラ）はエスケープせずそのまま書く。

    本関数はこの規則の逆変換を行う:
    - 両端がダブルクォートで囲まれている場合のみアンエスケープを適用する
      （write 側で引用符が付くのはエスケープした場合に限るため）。
    - 引用符なしのプレーン値はそのまま返す（例: 単独バックスラッシュを含む
      `back\\slash` は引用符が付かないので素のまま保持する）。

    バックスラッシュをエスケープ導入文字として左から走査するため、
    `yaml_escape` の置換順序に依存せず正しく復元できる（FR-N01-4 の
    「original key を復元・照合可能にする」往復契約）。

    Args:
        value: meta.yaml の `key: value` から取り出した（strip 済み）値文字列

    Returns:
        str: アンエスケープ済みの値
    """
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        inner = value[1:-1]
        unescape_map = {'"': '"', '\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}
        out = []
        i = 0
        length = len(inner)
        while i < length:
            ch = inner[i]
            if ch == '\\' and i + 1 < length:
                nxt = inner[i + 1]
                out.append(unescape_map.get(nxt, nxt))
                i += 2
                continue
            out.append(ch)
            i += 1
        return ''.join(out)
    return value


def read_meta(store_dir):
    """meta.yaml を読み込む（DES-005 §3.2）。

    Args:
        store_dir: store_dir の Path

    Returns:
        dict: original_key / created_at / schema_version を含む。
              ファイル不在・読込失敗時は空 dict。
    """
    meta_path = Path(store_dir) / META_FILENAME
    if not meta_path.exists():
        return {}

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: Failed to read meta.yaml: {meta_path} - {e}")
        return {}

    meta = {}
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = _unescape_yaml_value(value.strip())
        if key == "schema_version":
            try:
                value = int(value)
            except ValueError:
                pass
        meta[key] = value
    return meta


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

    if not args.promote_pending and not args.clean_work_dir:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.NO_TARGETS,
            message="No action specified (use --promote-pending or --clean-work-dir)",
        )
        return 1

    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    project_root = get_project_root()
    store_dir = resolve_store_dir(key, project_root)

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
