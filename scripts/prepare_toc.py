#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_toc.py — desired-state 差分検出 + pending YAML 生成（doc-advisor plugin / key + path I/F）

DES-005 §5.1（検証フロー）/ §5.3（単体モード走査）/ §6.1（prepare/merge 2 フェーズ）/
§6.2（差分検出アルゴリズム）/ §6.3（破壊性）/ §6.4（work file 名）/ §9（単体モード）/
§8（JSON 出力契約）/ §4.1（モジュール）を実装する。

責務（決定的処理。メタデータ抽出はしない / FR-N07-1）:
- key 解決（予約 key all / 任意 all reject）
- paths 検証（§5.1）と rejected_paths 集約・大小衝突 warning
- desired-state 差分検出（added / updated / unchanged / deleted）
- added + updated について pending YAML を store_dir/.toc_work/ に生成
- --dry-run（書き込みなしで件数・path 一覧を JSON 出力）
- --all 単体モード（rglob + 固定除外 + root 外実体除外、最大ファイル数 warning）
- JSON 出力（toc_store.emit_json）

CLI:
    python3 prepare_toc.py --key <key> --paths-json '["docs/a.md", ...]'
    python3 prepare_toc.py --key <key> --paths-file paths.json
    python3 prepare_toc.py --all
    python3 prepare_toc.py --key <key> --paths-json [...] --dry-run

標準ライブラリのみ使用（NFR-N01）。
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from toc_utils import (
    get_project_root,
    normalize_path,
    calculate_file_hash,
    load_checksums,
    rglob_follow_symlinks,
    should_exclude,
    resolve_within_root,
    validate_path,
    find_escaping_symlink,
    detect_case_collisions,
    PathRejection,
    ExternalSymlinkPending,
    log,
    SYSTEM_EXCLUDE_PATTERNS,
    MARKDOWN_GLOB,
)
from toc_store import (
    WORK_DIRNAME,
    CHECKSUMS_FILENAME,
    DELETED_SIDECAR_FILENAME,
    EMPTY_INTENT_SIDECAR_FILENAME,
    ErrorCode,
    KeyError_,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_PARTIAL,
    STATUS_NEEDS_CONFIRMATION,
    resolve_store_dir,
    resolve_key_from_args,
    emit_json,
    toc_path_rel,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 単体モード（--all）の最大ファイル数 warning 閾値（NFR-N05 / TBD-001 確定値 = 100 件）
MAX_FILES_WARN_THRESHOLD = 100

# pending YAML テンプレート（DES-005 §7.1: doc_type を除去）
PENDING_TEMPLATE = """_meta:
  source_file: {source_file}
  status: pending
  updated_at: null

title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
"""


# ---------------------------------------------------------------------------
# has_substantive_content（旧 create_pending_yaml.py から転用 / DES-005 §12）
# ---------------------------------------------------------------------------

def has_substantive_content(filepath, min_content_lines=1):
    """ヘッダ・空行・frontmatter を除いた実体内容があるか判定する。

    frontmatter はファイル先頭の '---' で開始し、次の '---' で終了する
    ステートマシン方式で判定（先頭以外の '---' は通常行として扱う）。

    Args:
        filepath: 対象ファイルパス
        min_content_lines: 実体行の最小本数

    Returns:
        bool: 実体内容が十分にあれば True
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError, UnicodeDecodeError):
        return False

    if not content.strip():
        return False  # Empty file

    # ステートマシン: 'before_start' → 'in_frontmatter' → 'after_frontmatter'
    state = 'before_start'
    content_lines = 0
    for line in content.splitlines():
        stripped = line.strip()

        if state == 'before_start':
            if not stripped:
                continue
            if stripped == '---':
                state = 'in_frontmatter'
                continue
            else:
                state = 'after_frontmatter'
                # fall through してこの行を評価
        elif state == 'in_frontmatter':
            if stripped == '---':
                state = 'after_frontmatter'
            continue

        # state == 'after_frontmatter'
        if not stripped or stripped.startswith('#'):
            continue

        content_lines += 1
        if content_lines >= min_content_lines:
            return True

    return False


# ---------------------------------------------------------------------------
# work file 名（DES-005 §6.4: sha256(source)[:16].yaml）
# ---------------------------------------------------------------------------

def get_yaml_filename(source_file):
    """source_file から pending YAML のファイル名を生成する（DES-005 §6.4）。

    SHA256 ハッシュを用いることで以下を回避する:
    - ファイル名長制限（macOS 255 bytes）
    - case-insensitive ファイルシステムでの衝突
    - パス中の特殊文字
    元 path は _meta.source_file に保持される。
    """
    hash_val = hashlib.sha256(source_file.encode("utf-8")).hexdigest()[:16]
    return f"{hash_val}.yaml"


def create_pending_yaml(source_file, work_dir):
    """pending YAML ファイルを生成する（DES-005 §7.1: doc_type なし）。

    Args:
        source_file: project-root-relative の source file path
        work_dir: store_dir/.toc_work/ の Path

    Returns:
        Path: 生成したファイルパス、失敗時は None
    """
    yaml_name = get_yaml_filename(source_file)
    yaml_path = Path(work_dir) / yaml_name
    try:
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(PENDING_TEMPLATE.format(source_file=source_file))
        return yaml_path
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: File write error: {yaml_path} - {e}")
        return None


# ---------------------------------------------------------------------------
# paths 検証（DES-005 §5.1 / FR-N03）
# ---------------------------------------------------------------------------

def _build_external_pending(external_counts, project_root):
    """越境 symlink prefix → 件数 の dict を JSON 出力用リストに整形する（NFR-N06）。

    Returns:
        list[{"symlink", "resolved", "affected_count"}]（symlink 昇順）
    """
    root = Path(project_root)
    out = []
    for sym in sorted(external_counts):
        resolved = None
        try:
            resolved = str((root / sym).resolve())
        except (OSError, RuntimeError):
            pass
        out.append({
            "symlink": sym,
            "resolved": resolved,
            "affected_count": external_counts[sym],
        })
    return out


def validate_paths(paths, project_root, allow_external=None):
    """入力 paths を §5.1 の検証フローで検証する。

    重複（正規化後同一）は除去し、初出順を保持する。

    Args:
        paths: 入力 path 文字列のリスト
        project_root: project root（Path）
        allow_external: 承認済み越境 symlink prefix の集合（str iterable）。
            None は承認なし（= 越境 symlink はすべて external_pending に積む）。

    Returns:
        tuple: (normalized_paths, rejected_paths, external_pending)
            normalized_paths: 検証を通過した project-root-relative path（重複除去・順序保持）
            rejected_paths: [{"path": <入力>, "reason": <error_code>}] のリスト
            external_pending: 未承認の越境 symlink リスト
                [{symlink, resolved, affected_count}]（NFR-N06）
    """
    allowed = set(allow_external) if allow_external else set()
    normalized_paths = []
    seen = set()
    rejected_paths = []
    external_counts = {}

    for p in paths:
        try:
            norm = validate_path(p, project_root, allow_external=allowed)
        except ExternalSymlinkPending as e:
            sym = e.symlink or str(p)
            external_counts[sym] = external_counts.get(sym, 0) + 1
            continue
        except PathRejection as e:
            rejected_paths.append({"path": str(p), "reason": e.error_code})
            continue
        if norm in seen:
            continue
        seen.add(norm)
        normalized_paths.append(norm)

    external_pending = _build_external_pending(external_counts, project_root)
    return normalized_paths, rejected_paths, external_pending


# ---------------------------------------------------------------------------
# 単体モード走査（DES-005 §5.3 / §9.1 / FR-N04）
# ---------------------------------------------------------------------------

def collect_all_markdown(project_root, allow_external=None):
    """project root 以下の Markdown を単体モードで収集する（DES-005 §9.1 / §5.3）。

    1. rglob_follow_symlinks で **/*.md を列挙
    2. 固定除外（SYSTEM_EXCLUDE_PATTERNS）を should_exclude で適用
    3. root 外実体（symlink 先）の扱い:
       - 越境 symlink が `allow_external` で承認済み → 収集対象に含める
       - 未承認 → 収集から外し external_pending に集計（§5.3 / NFR-N06）

    `--all` は非対話のバルク索引のため、未承認の越境 symlink は **skip** し
    （needs_confirmation でブロックしない）、external_pending を warning として
    上位層に提示する。取り込みたい場合は `--allow-external-json` で明示承認する。

    Args:
        project_root: project root（Path）
        allow_external: 承認済み越境 symlink prefix の集合（str iterable）。None は承認なし。

    Returns:
        tuple: (paths, external_pending)
            paths: project-root-relative の正規化済み path（昇順）
            external_pending: skip した未承認越境 symlink
                [{symlink, resolved, affected_count}]（昇順）
    """
    root = Path(project_root)
    allowed = set(allow_external) if allow_external else set()
    collected = set()
    external_counts = {}

    for md_file in rglob_follow_symlinks(root, MARKDOWN_GLOB):
        # 固定除外（裸名＝任意階層のディレクトリ名一致 / '/' 含み＝セグメント境界マッチ）
        if should_exclude(md_file, root, SYSTEM_EXCLUDE_PATTERNS):
            continue
        try:
            rel = normalize_path(md_file.relative_to(root))
        except ValueError:
            # root 配下でない（理論上ここには来ないが防御的に除外）
            continue
        # root 外実体（symlink 先が root 外）の判定
        try:
            resolve_within_root(md_file, root)
        except FileNotFoundError:
            continue
        except PathRejection:
            # 越境 symlink を特定し、承認状態で分岐
            sym = find_escaping_symlink(rel, root)
            if sym is None:
                continue
            if sym in allowed:
                collected.add(rel)
            else:
                external_counts[sym] = external_counts.get(sym, 0) + 1
            continue
        collected.add(rel)

    external_pending = _build_external_pending(external_counts, root)
    return sorted(collected), external_pending


# ---------------------------------------------------------------------------
# desired-state 差分検出（DES-005 §6.2）
# ---------------------------------------------------------------------------

def compute_diff(desired_paths, prev_checksums, project_root):
    """desired-state 差分を算出する（DES-005 §6.2）。

    Args:
        desired_paths: 検証済み desired path のリスト（project-root-relative）
        prev_checksums: 前回 checksums（path → hash）
        project_root: project root（Path）

    Returns:
        dict: {
            "added": [path, ...],      # prev に無い
            "updated": [path, ...],    # prev にあり hash 不一致
            "unchanged": [path, ...],  # prev にあり hash 一致
            "deleted": [path, ...],    # prev にあり desired に無い
            "current_hashes": {path: hash},  # 今回算出した desired の hash
        }
    """
    root = Path(project_root)
    desired_set = set(desired_paths)

    added = []
    updated = []
    unchanged = []
    current_hashes = {}

    for path in desired_paths:
        full = root / path
        current_hash = calculate_file_hash(full)
        if current_hash is not None:
            current_hashes[path] = current_hash

        prev_hash = prev_checksums.get(path)
        if prev_hash is None:
            added.append(path)
        elif current_hash != prev_hash:
            updated.append(path)
        else:
            unchanged.append(path)

    deleted = sorted(p for p in prev_checksums.keys() if p not in desired_set)

    return {
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "deleted": deleted,
        "current_hashes": current_hashes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    """コマンドライン引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Prepare ToC: desired-state diff + pending YAML generation"
    )
    parser.add_argument("--key", help="User-specified key (opaque)")
    parser.add_argument(
        "--all", action="store_true",
        help="Single mode: index all Markdown under project root (reserved key 'all')",
    )
    parser.add_argument("--paths-json", help="JSON array of project-root-relative paths")
    parser.add_argument("--paths-file", help="Path to a JSON file containing paths array")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute diff without generating pending YAML",
    )
    parser.add_argument(
        "--allow-external-json",
        help="JSON array of approved external symlink prefixes (root 外を指す symlink の承認)。"
             "未指定=discovery（越境を検出したら needs_confirmation）。"
             "指定=decided（列挙分のみ許可、他の越境は drop）。空配列 '[]' は全拒否。",
    )
    # 誤用ガード: ディレクトリ展開は prepare_toc の責務ではなく expand_dirs.py / index-docs
    # SKILL が担う。argparse の不親切な "unrecognized arguments" を、実行可能な誘導エラーに
    # 変えるために認識だけして main で UNSUPPORTED_ARG として弾く。
    parser.add_argument(
        "--dirs-json",
        help="NOT supported here. Expand dirs with expand_dirs.py first, "
             "or use the index-docs skill which orchestrates expansion.",
    )
    parser.add_argument(
        "--exclude-json",
        help="NOT supported here (only meaningful with --dirs-json). See expand_dirs.py.",
    )
    return parser.parse_args(argv)


def load_input_paths(args):
    """--paths-json / --paths-file から入力 paths を読み込む。

    Returns:
        list[str]: 入力 path 文字列のリスト

    Raises:
        ValueError: JSON 不正・型不正・ファイル読込失敗
    """
    raw = None
    if args.paths_json is not None:
        raw = args.paths_json
    elif args.paths_file is not None:
        try:
            with open(args.paths_file, "r", encoding="utf-8") as f:
                raw = f.read()
        except (IOError, OSError, PermissionError) as e:
            raise ValueError(f"Failed to read paths file: {args.paths_file} - {e}") from e

    if raw is None:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for paths: {e}") from e

    if not isinstance(data, list):
        raise ValueError("paths must be a JSON array")
    if not all(isinstance(p, str) for p in data):
        raise ValueError("paths array must contain only strings")
    return data


def parse_allow_external(args):
    """--allow-external-json を解釈する（NFR-N06）。

    Returns:
        None: 未指定（discovery モード。越境検出で needs_confirmation）
        list[str]: 指定（decided モード。正規化済み prefix の集合。[] は全拒否）

    Raises:
        ValueError: JSON 不正・型不正
    """
    if args.allow_external_json is None:
        return None
    try:
        data = json.loads(args.allow_external_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for --allow-external-json: {e}") from e
    if not isinstance(data, list) or not all(isinstance(s, str) for s in data):
        raise ValueError("--allow-external-json must be a JSON array of strings")
    # path として正規化（symlink prefix は project-root-relative）
    return [normalize_path(os.path.normpath(s)) for s in data]


def main(argv=None):
    args = parse_args(argv)
    project_root = get_project_root()

    # 0. 誤用ガード: --dirs-json / --exclude-json は prepare_toc の責務外（DES-005 §5.1）。
    #    expand_dirs.py で paths に展開してから --paths-json で渡すか、index-docs SKILL を使う。
    if args.dirs_json is not None or args.exclude_json is not None:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.UNSUPPORTED_ARG,
            message=(
                "prepare_toc.py does not expand directories. "
                "Run expand_dirs.py first and pass its 'paths' output via --paths-json, "
                "or use the index-docs skill which orchestrates expansion automatically "
                "(--dirs-json/--exclude-json are handled there, not here)."
            ),
        )
        return 1

    # 1. key 解決（--all / --key 省略 → 予約 all、--key all → KEY_RESERVED）
    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    single_mode = args.all or args.key is None
    store_dir = resolve_store_dir(key, project_root)
    checksums_file = store_dir / CHECKSUMS_FILENAME
    toc_rel = toc_path_rel(store_dir, project_root)

    # 1.5 越境 symlink 承認リスト（NFR-N06）。None=discovery / list=decided。
    try:
        allow_external = parse_allow_external(args)
    except ValueError as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.INVALID_PATH,
            message=str(e),
            key=key,
            toc_path=toc_rel,
        )
        return 1
    decided = allow_external is not None
    allow_set = set(allow_external or ())

    # 2. desired paths の決定
    if single_mode:
        # --all 単体モード: project root 以下の Markdown を収集（§9.1 / §5.3）。
        # 越境 symlink は非対話で skip し external_pending を warning に回す。
        desired_paths, external_pending = collect_all_markdown(project_root, allow_set)
        rejected_paths = []
    else:
        # 明示 paths 入力（--paths-json / --paths-file）の検証（§5.1）
        try:
            input_paths = load_input_paths(args)
        except ValueError as e:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.INVALID_PATH,
                message=str(e),
                key=key,
                toc_path=toc_rel,
            )
            return 1
        desired_paths, rejected_paths, external_pending = validate_paths(
            input_paths, project_root, allow_set
        )

    # 2.5 未承認の越境 symlink がある場合の分岐（NFR-N06）。
    if external_pending:
        if single_mode:
            # --all は非対話: skip した越境 symlink を warning として提示し処理続行。
            pass
        elif not decided:
            # 明示 paths の discovery モード: 承認を取るため確認を要求し、書き込みはしない。
            emit_json(
                STATUS_NEEDS_CONFIRMATION,
                error_code=None,
                message=(
                    "Some paths cross the project root via a symlink and need approval. "
                    "Review the resolved targets, then re-run with "
                    "--allow-external-json '[\"<symlink>\", ...]' listing the symlinks you approve "
                    "(omit any you reject; pass '[]' to reject all)."
                ),
                key=key,
                toc_path=toc_rel,
                external_pending=external_pending,
            )
            return 0
        # decided モード（明示 paths）: 未承認分は drop 済み。warning で透明化して続行。

    # 3. 大小衝突 warning（§5.2 / REQ-001 §6.1）
    warnings = detect_case_collisions(desired_paths)

    # 越境 symlink を skip / drop した場合の透明化 warning（no silent caps）
    for ext in external_pending:
        warnings.append(
            f"external symlink not indexed (needs approval): {ext['symlink']} "
            f"-> {ext['resolved']} ({ext['affected_count']} file(s))"
        )

    # 最大ファイル数超過 warning（単体モード / NFR-N05 / TBD-001 = 100）
    if single_mode and len(desired_paths) > MAX_FILES_WARN_THRESHOLD:
        warnings.append(
            f"file count {len(desired_paths)} exceeds threshold "
            f"{MAX_FILES_WARN_THRESHOLD}; processing continues"
        )

    # 4. desired-state 差分検出（§6.2）
    prev_checksums = load_checksums(checksums_file)
    diff = compute_diff(desired_paths, prev_checksums, project_root)

    # status: reject があれば partial、無ければ ok
    status = STATUS_PARTIAL if rejected_paths else STATUS_OK

    counts = {
        "added": len(diff["added"]),
        "updated": len(diff["updated"]),
        "deleted": len(diff["deleted"]),
        "unchanged": len(diff["unchanged"]),
    }

    # 5. --dry-run: 書き込みをせず件数・path 一覧のみ JSON 出力（FR-N02-5）
    if args.dry_run:
        emit_json(
            status,
            error_code=None,
            message="dry-run: no files written",
            key=key,
            toc_path=toc_rel,
            normalized_paths=desired_paths,
            rejected_paths=rejected_paths,
            counts=counts,
            warnings=warnings,
        )
        return 0

    # 6. pending YAML 生成（added + updated。空ファイルは skip / §12）
    work_dir = store_dir / WORK_DIRNAME
    targets = diff["added"] + diff["updated"]
    skipped = []
    created = []
    failed = 0

    # desired 0 件（空 repo / 対象 0 件）= 空 ToC を意図する状態（DES-005 §9.2 / NFR-N05）。
    # この場合 merge へ「空 toc.yaml を冪等出力すべき」意図を空意図サイドカーで引き渡す。
    # これにより「prepare 実行済みで desired 0 件」と「prepare 未実行（NO_TARGETS）」を
    # merge が痕跡で区別できる（§9.3 の対象 0 件分岐）。
    desired_is_empty = not desired_paths

    # deleted / 空意図サイドカーは pending が無くても work_dir を作って残す必要がある。
    need_work_dir = bool(targets) or bool(diff["deleted"]) or desired_is_empty

    if need_work_dir:
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
        except (IOError, OSError, PermissionError) as e:
            emit_json(
                STATUS_ERROR,
                error_code=ErrorCode.NOT_FOUND,
                message=f"Failed to create work dir: {work_dir} - {e}",
                key=key,
                toc_path=toc_rel,
            )
            return 1

    if targets:
        for source_file in targets:
            full = Path(project_root) / source_file
            if not has_substantive_content(full):
                log(f"  [Skipped] {source_file} (empty or headers only)")
                skipped.append(source_file)
                continue
            yaml_path = create_pending_yaml(source_file, work_dir)
            if yaml_path is None:
                failed += 1
                continue
            created.append(source_file)

    # deleted サイドカーを残す（merge が desired から外れた path を反映する / §6.1 / §6.2 / FR-N02-2）。
    # deleted が空なら古いサイドカーを除去し、前回実行の残骸で誤削除しないようにする。
    sidecar = work_dir / DELETED_SIDECAR_FILENAME
    if diff["deleted"]:
        try:
            sidecar.write_text(
                json.dumps(diff["deleted"], ensure_ascii=False), encoding="utf-8"
            )
        except (IOError, OSError, PermissionError) as e:
            log(f"Warning: Failed to write deleted sidecar: {sidecar} - {e}")
            warnings.append("failed to write deleted sidecar")
    elif sidecar.exists():
        try:
            sidecar.unlink()
        except (OSError, PermissionError):
            pass

    # 空意図サイドカーを残す（desired 0 件のときのみ。merge が空 toc.yaml を冪等出力する）。
    # desired が空でなくなった場合は古い空意図サイドカーを除去し、誤って空出力しないようにする。
    empty_intent = work_dir / EMPTY_INTENT_SIDECAR_FILENAME
    if desired_is_empty:
        try:
            empty_intent.write_text("", encoding="utf-8")
        except (IOError, OSError, PermissionError) as e:
            log(f"Warning: Failed to write empty-intent sidecar: {empty_intent} - {e}")
            warnings.append("failed to write empty-intent sidecar")
    elif empty_intent.exists():
        try:
            empty_intent.unlink()
        except (OSError, PermissionError):
            pass

    if failed > 0:
        warnings.append(f"{failed} pending YAML(s) failed to write")

    log(
        f"prepare: added={counts['added']} updated={counts['updated']} "
        f"deleted={counts['deleted']} unchanged={counts['unchanged']} "
        f"created={len(created)} skipped={len(skipped)}"
    )

    emit_json(
        status,
        error_code=None,
        key=key,
        toc_path=toc_rel,
        normalized_paths=desired_paths,
        rejected_paths=rejected_paths,
        counts=counts,
        warnings=warnings,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
