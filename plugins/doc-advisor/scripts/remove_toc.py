#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remove_toc.py — ToC 削除（doc-advisor plugin / key + path I/F）

DES-005 §4.1（モジュール）/ §3.2（ストア構造）/ §8（JSON 出力契約）/
§11.1（ユースケース）/ REQ-001 FR-N06（削除）/ FR-N04-4（`--all` / `--key all`
解決規則）/ FR-N08（JSON 契約）を実装する。

責務（決定的処理。メタデータ抽出はしない / FR-N07-1）:
- key 解決（予約 key all / 任意 all reject。toc_store.resolve_key_from_args を使う）
- key 全体削除（--paths-json 未指定時。store_dir ディレクトリ全体を rmtree。
  不在は冪等に status ok / FR-N06-1）
- path 個別削除（--paths-json 指定時。toc.yaml から指定 path のエントリを除去し
  書き戻す。.toc_checksums.yaml の該当エントリも整合的に除去。toc.yaml 不在は
  TOC_NOT_FOUND。削除後の docs 順序は既存の定義順を保持 / FR-N06-2）
- JSON 出力（toc_store.emit_json）

CLI:
    python3 remove_toc.py --key <key>
    python3 remove_toc.py --all
    python3 remove_toc.py --key <key> --paths-json '["docs/a.md", ...]'

標準ライブラリのみ使用（NFR-N01）。
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from toc_utils import (
    get_project_root,
    normalize_path,
    load_existing_toc,
    load_checksums,
    write_checksums_yaml,
    yaml_escape,
    log,
)
from toc_store import (
    CHECKSUMS_FILENAME,
    ErrorCode,
    KeyError_,
    STATUS_OK,
    STATUS_ERROR,
    resolve_store_dir,
    resolve_key_from_args,
    emit_json,
    toc_path_rel,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# toc.yaml ファイル名
TOC_FILENAME = "toc.yaml"

# ToC エントリのフィールド描画順（DES-005 §7.1: doc_type を除去。get_toc と同一）。
SCALAR_FIELDS = ("title", "purpose")
LIST_FIELDS = ("content_details", "applicable_tasks", "keywords")


# ---------------------------------------------------------------------------
# toc.yaml metadata の読み取り（書き戻し時に保持する用途）
# ---------------------------------------------------------------------------

def read_toc_metadata(toc_path):
    """toc.yaml の metadata セクションを読み取る（DES-005 §7.1）。

    load_existing_toc は docs のみ返し metadata を捨てるため、書き戻し時に
    metadata.name / metadata.key を保持できるよう本関数で別途読み取る。
    file_count は書き戻し時に再計算するため読まない。

    Args:
        toc_path: toc.yaml の Path

    Returns:
        dict: {name, key} など metadata セクションの key→値（簡易スカラのみ）。
              不在・読込失敗時は空 dict。
    """
    toc_path = Path(toc_path)
    if not toc_path.exists():
        return {}
    try:
        with open(toc_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: Failed to read {toc_path}: {e}")
        return {}

    meta = {}
    in_metadata = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped == "metadata:":
            in_metadata = True
            continue
        if stripped == "docs:":
            break
        if not in_metadata:
            continue
        # metadata 配下は 2 スペースインデントのスカラ（name/key/generated_at/file_count）
        if line.startswith("  ") and ":" in stripped and not stripped.startswith("-"):
            mk, _, mv = stripped.partition(":")
            mk = mk.strip()
            mv = mv.strip().strip("\"'")
            meta[mk] = mv
    return meta


# ---------------------------------------------------------------------------
# toc.yaml の書き戻し（DES-005 §7.1 スキーマ / 原子的書き込み）
# ---------------------------------------------------------------------------

def render_toc_doc(docs, *, key, name):
    """docs を toc.yaml 本体の文字列として描画する（DES-005 §7.1: doc_type 除去）。

    docs の定義順（dict 挿入順）をそのまま保持する（sorted しない / FR-N06-2）。

    Args:
        docs: source_file -> entry の dict（定義順保持）
        key: original key（metadata.key に転記）
        name: metadata.name（保持。不在時は key を流用）

    Returns:
        str: toc.yaml 文字列（末尾改行付き）
    """
    lines = []
    lines.append("# .claude/.doc-advisor/toc/<slug>/toc.yaml")
    lines.append("# Document Search Index (key-based ToC)")
    lines.append("# Auto-generated - Do not edit directly")
    lines.append("")

    lines.append("metadata:")
    lines.append(f"  name: {yaml_escape(name if name else key)}")
    lines.append(f"  key: {yaml_escape(key)}")
    lines.append(
        f"  generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    lines.append(f"  file_count: {len(docs)}")
    lines.append("")

    lines.append("docs:")
    if not docs:
        lines.append("  {}")
    else:
        for source_file, entry in docs.items():
            lines.append(f"  {yaml_escape(source_file)}:")
            for field in SCALAR_FIELDS:
                if field in entry and entry[field] is not None:
                    lines.append(f"    {field}: {yaml_escape(entry[field])}")
            for field in LIST_FIELDS:
                if field in entry and entry[field]:
                    lines.append(f"    {field}:")
                    for item in entry[field]:
                        lines.append(f"      - {yaml_escape(item)}")

    return "\n".join(lines) + "\n"


def write_toc_atomic(docs, toc_path, *, key, name):
    """toc.yaml を原子的に書き戻す（os.replace。書き込み途中の破損を防ぐ）。

    Args:
        docs: source_file -> entry の dict（定義順保持）
        toc_path: 書き込み先 toc.yaml の Path
        key: original key
        name: metadata.name

    Returns:
        bool: True on success, False on failure
    """
    toc_path = Path(toc_path)
    body = render_toc_doc(docs, key=key, name=name)
    try:
        output_dir = toc_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(output_dir), suffix=".tmp", prefix=".toc_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(tmp_path, str(toc_path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to write file: {toc_path} - {e}")
        return False


# ---------------------------------------------------------------------------
# key 全体削除（FR-N06-1）
# ---------------------------------------------------------------------------

def remove_key(store_dir):
    """store_dir ディレクトリ全体を削除する（FR-N06-1）。

    不在時は冪等に成功扱いとする。

    Args:
        store_dir: store_dir の Path

    Returns:
        tuple: (ok, existed)
            ok: 削除に成功（不在も True）
            existed: 削除前に存在していたか
    """
    store_dir = Path(store_dir)
    if not store_dir.exists():
        log(f"Store directory not found (idempotent ok): {store_dir}")
        return True, False
    try:
        shutil.rmtree(str(store_dir))
    except (OSError, PermissionError) as e:
        log(f"Error: Failed to remove store directory: {store_dir} - {e}")
        return False, True
    log(f"Removed store directory: {store_dir}")
    return True, True


# ---------------------------------------------------------------------------
# path 個別削除（FR-N06-2）
# ---------------------------------------------------------------------------

def parse_paths_json(raw):
    """--paths-json（JSON 配列）を正規化・重複除去して返す（初出順保持）。

    Args:
        raw: --paths-json の生文字列

    Returns:
        list[str]: 正規化済み path リスト

    Raises:
        ValueError: JSON 不正・型不正
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for paths: {e}") from e
    if not isinstance(data, list):
        raise ValueError("paths must be a JSON array")
    if not all(isinstance(p, str) for p in data):
        raise ValueError("paths array must contain only strings")

    normalized = []
    seen = set()
    for token in data:
        token = token.strip()
        if not token:
            continue
        norm = normalize_path(token)
        if norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
    return normalized


def remove_paths(store_dir, requested_paths, key):
    """toc.yaml / .toc_checksums.yaml から指定 path のエントリを個別削除する。

    削除後の docs 順序は既存の定義順を保持する（FR-N06-2 / get_toc の FR-N05-2
    と整合）。.toc_checksums.yaml の該当エントリも整合的に除去する。

    Args:
        store_dir: store_dir の Path
        requested_paths: 正規化済みの削除対象 path リスト
        key: original key（書き戻し時に metadata.key へ転記）

    Returns:
        tuple: (ok, deleted, missing, toc_found)
            ok: 処理成功
            deleted: 実際に削除した path（定義順）
            missing: toc.yaml に存在しなかった path（要求順）
            toc_found: toc.yaml が存在したか
    """
    store_dir = Path(store_dir)
    toc_path = store_dir / TOC_FILENAME
    checksums_file = store_dir / CHECKSUMS_FILENAME

    if not toc_path.exists():
        return False, [], list(requested_paths), False

    docs = load_existing_toc(toc_path)
    metadata = read_toc_metadata(toc_path)
    requested_set = set(requested_paths)

    # 定義順を保持して削除対象を抽出（docs の挿入順）
    deleted = [p for p in docs.keys() if p in requested_set]
    missing = [p for p in requested_paths if p not in docs]

    for p in deleted:
        del docs[p]

    # toc.yaml 書き戻し（定義順保持・原子的書き込み）
    name = metadata.get("name", "")
    if not write_toc_atomic(docs, toc_path, key=key, name=name):
        return False, [], missing, True

    # .toc_checksums.yaml の該当エントリも整合的に除去（存在する場合のみ）
    if checksums_file.exists():
        checksums = load_checksums(checksums_file)
        changed = False
        for p in deleted:
            if p in checksums:
                del checksums[p]
                changed = True
        if changed:
            write_checksums_yaml(
                checksums,
                checksums_file,
                header_comment="Document Search Index checksums (key-based)",
            )

    return True, deleted, missing, True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Remove ToC: whole key (store dir) or specific path entries"
    )
    parser.add_argument("--key", help="User-specified key (opaque)")
    parser.add_argument(
        "--all", action="store_true",
        help="Single mode: target reserved key 'all'",
    )
    parser.add_argument(
        "--paths-json",
        help="JSON array of project-root-relative paths to remove individually",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    project_root = get_project_root()

    # 1. key 解決（--all / --key 省略 → 予約 all、--key all → KEY_RESERVED、空 → KEY_EMPTY）
    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    store_dir = resolve_store_dir(key, project_root)
    toc_rel = toc_path_rel(store_dir, project_root)

    # 2. path 個別削除（--paths-json 指定時 / FR-N06-2）
    if args.paths_json is not None:
        try:
            requested_paths = parse_paths_json(args.paths_json)
        except ValueError as e:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.INVALID_PATH,
                message=str(e),
                key=key,
                toc_path=toc_rel,
            )
            return 1

        ok, deleted, missing, toc_found = remove_paths(
            store_dir, requested_paths, key
        )

        if not toc_found:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.TOC_NOT_FOUND,
                message=f"ToC not found for key: {key} ({toc_rel})",
                key=key,
                toc_path=toc_rel,
            )
            return 1

        if not ok:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.NOT_FOUND,
                message="Failed to write updated ToC",
                key=key,
                toc_path=toc_rel,
            )
            return 1

        warnings = []
        if missing:
            warnings.append(
                f"{len(missing)} path(s) not present in ToC: {', '.join(missing)}"
            )

        log(f"remove paths: deleted={len(deleted)} missing={len(missing)}")
        # normalized_paths に「実際に削除した path 一覧」を載せる（個別削除の主結果）。
        # ToC に無く削除されなかった path は warnings の missing で示す。
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_rel,
            normalized_paths=deleted,
            counts={"deleted": len(deleted)},
            warnings=warnings,
        )
        return 0

    # 3. key 全体削除（--paths-json 未指定時 / FR-N06-1）
    ok, existed = remove_key(store_dir)
    if not ok:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.NOT_FOUND,
            message=f"Failed to remove store directory for key: {key}",
            key=key,
            toc_path=toc_rel,
        )
        return 1

    message = (
        f"Removed store for key: {key}"
        if existed
        else f"Store for key '{key}' not found (idempotent ok)"
    )
    log(message)
    emit_json(
        STATUS_OK,
        error_code=None,
        message=message,
        key=key,
        toc_path=toc_rel,
        counts={"deleted": 1 if existed else 0},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
