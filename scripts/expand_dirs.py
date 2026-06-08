#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expand_dirs.py — ディレクトリ配列を Markdown ファイルパス配列に展開するヘルパー（FR-N09）

index-docs SKILL がディレクトリ入力（--dirs-json）を受け取った際に、
prepare_toc.py へ渡す --paths-json を生成するために呼び出す。

責務:
- --dirs-json のディレクトリを rglob で展開し Markdown を収集
- --dirs-json のエントリがグロブメタ文字（* ? [）を含む場合はグロブパターンとして解釈し、
  マッチしたディレクトリは rglob、マッチした Markdown ファイルは直接採用する（FR-N09-8）
- SYSTEM_EXCLUDE_PATTERNS を常時適用（--exclude-json の有無に関わらず）
- --exclude-json で指定したパス・ディレクトリを追加除外（システム固定除外と同じ
  should_exclude セマンティクス: 裸名＝任意階層のディレクトリ名完全一致、
  '/' 含み＝セグメント境界のパスマッチ）
- root 外 symlink は論理 path を後段へ渡し、prepare_toc.py の承認フローに委ねる
- --paths-json の明示ファイルと結合・重複除去
- stdout に単一 JSON を出力（NFR / FR-N08）

CLI:
    python3 expand_dirs.py --dirs-json '["docs/rules/", "docs/specs/"]'
    python3 expand_dirs.py --dirs-json '["docs/specs/**/design/"]'   # グロブ（任意深さの design/）
    python3 expand_dirs.py --dirs-json '["docs/**/*.md"]'            # グロブ（ファイル直接マッチ）
    python3 expand_dirs.py --dirs-json '["docs/"]' --exclude-json '["docs/draft/"]'
    python3 expand_dirs.py --dirs-json '["docs/"]' --paths-json '["extra.md"]'

標準ライブラリのみ使用（NFR-N01）。
"""

import argparse
import json
import sys
from pathlib import Path

from toc_utils import (
    get_project_root,
    normalize_path,
    rglob_follow_symlinks,
    should_exclude,
    resolve_within_root,
    validate_path_within_base,
    PathRejection,
    log,
    SYSTEM_EXCLUDE_PATTERNS,
    MARKDOWN_GLOB,
)

STATUS_OK = "ok"
STATUS_ERROR = "error"


def _emit(status, *, paths=None, rejected_dirs=None, warnings=None, error_code=None, message=None):
    """stdout に単一 JSON を出力する。"""
    obj = {"status": status}
    if error_code is not None:
        obj["error_code"] = error_code
    if message is not None:
        obj["message"] = message
    obj["paths"] = paths or []
    obj["rejected_dirs"] = rejected_dirs or []
    obj["warnings"] = warnings or []
    print(json.dumps(obj, ensure_ascii=False))


def _resolve_dir(rel_dir, project_root):
    """ディレクトリ相対パスを論理 path として検証し、存在するディレクトリか確認する。

    symlink 実体が project root 外でもここでは拒否しない。展開結果の論理 path を
    prepare_toc.py に渡し、外部 symlink の承認確認は後段の path 検証に委ねる。

    Returns:
        Path: project root から辿れるディレクトリ path（symlink は未解決）
    Raises:
        ValueError: 不在・非ディレクトリ・traversal の場合
    """
    normalized = normalize_path(rel_dir).rstrip("/")
    p = Path(normalized)
    if p.is_absolute():
        raise ValueError(f"絶対パスは使用できません: {rel_dir}")
    try:
        abs_dir = validate_path_within_base(normalized, project_root)
    except ValueError as e:
        raise ValueError(str(e)) from e
    if not abs_dir.exists():
        raise ValueError(f"存在しません: {rel_dir}")
    if not abs_dir.is_dir():
        raise ValueError(f"ディレクトリではありません: {rel_dir}")
    return abs_dir


# グロブメタ文字。--dirs-json エントリがこれらを含む場合のみグロブとして解釈し、
# 含まなければ従来どおり実在ディレクトリとして扱う（後方互換）。
_GLOB_META_CHARS = ("*", "?", "[")


def _has_glob_meta(entry):
    """エントリにグロブメタ文字が含まれるか。"""
    return any(c in entry for c in _GLOB_META_CHARS)


def _normalize_glob_pattern(raw):
    """グロブパターンを検証・正規化する。

    NFC 正規化・バックスラッシュ→スラッシュ・末尾スラッシュ除去のみ行い、
    グロブメタ文字（* ? [ **）は保持する（os.path.normpath は使わない）。

    Raises:
        ValueError: 空 / 絶対パス / '..' を含む場合（traversal 防止）
    """
    p = normalize_path(raw).replace("\\", "/").strip().rstrip("/")
    if not p:
        raise ValueError(f"空のグロブパターン: {raw}")
    if p.startswith("/"):
        raise ValueError(f"絶対パスのグロブは使用できません: {raw}")
    if ".." in p.split("/"):
        raise ValueError(f"'..' を含むグロブは使用できません: {raw}")
    return p


def _collect_file(md_file, project_root, exclude_list, collected):
    """単一 Markdown ファイルを検証して collected に追加する（除外適用）。

    システム固定除外（SYSTEM_EXCLUDE_PATTERNS）とユーザー除外（--exclude-json）は
    同一の should_exclude セマンティクスで判定する（裸名＝任意階層のディレクトリ名
    完全一致、'/' 含み＝セグメント境界のパスマッチ）。

    root 外 symlink はここで除外せず、後段の prepare_toc.py の default-deny +
    明示承認に委ねる（論理 path を採用）。
    """
    if should_exclude(md_file, project_root, SYSTEM_EXCLUDE_PATTERNS):
        return
    if should_exclude(md_file, project_root, exclude_list):
        return
    try:
        rel = normalize_path(str(md_file.relative_to(project_root)))
    except ValueError:
        return
    try:
        resolve_within_root(md_file, project_root)
    except PathRejection:
        pass
    collected.add(rel)


def _collect_dir(abs_dir, project_root, exclude_list, collected):
    """ディレクトリ配下の Markdown を rglob で収集し collected に追加する。"""
    for md_file in rglob_follow_symlinks(abs_dir, MARKDOWN_GLOB):
        _collect_file(md_file, project_root, exclude_list, collected)


def expand(dirs_json, exclude_json=None, paths_json=None, project_root=None):
    """ディレクトリ配列を展開し、ファイルパス配列を返す。

    Args:
        dirs_json: project-root-relative ディレクトリパスのリスト
        exclude_json: 除外するパス・ディレクトリのリスト（省略可）
        paths_json: 追加で結合する明示ファイルパスのリスト（省略可）
        project_root: プロジェクトルート（省略時は get_project_root()）

    Returns:
        dict: {paths, rejected_dirs, warnings}
    """
    if project_root is None:
        project_root = Path(get_project_root()).resolve()
    else:
        project_root = Path(project_root).resolve()

    exclude_list = exclude_json or []
    extra_paths = paths_json or []

    collected = set()
    rejected_dirs = []
    warnings = []

    for raw_dir in dirs_json:
        # グロブメタ文字を含むエントリはパターンとして展開（FR-N09-8）。
        # マッチしたディレクトリは rglob、マッチした Markdown ファイルは直接採用する。
        if _has_glob_meta(raw_dir):
            try:
                pattern = _normalize_glob_pattern(raw_dir)
            except ValueError as e:
                rejected_dirs.append({"dir": raw_dir, "reason": str(e)})
                continue
            try:
                matches = sorted(project_root.glob(pattern))
            except (ValueError, OSError) as e:
                rejected_dirs.append({"dir": raw_dir, "reason": f"glob 展開に失敗: {e}"})
                continue
            if not matches:
                warnings.append(f"glob にマッチするものがありません: {raw_dir}")
                continue
            matched_any = False
            for m in matches:
                if m.is_dir():
                    _collect_dir(m, project_root, exclude_list, collected)
                    matched_any = True
                elif m.is_file() and m.suffix.lower() == ".md":
                    _collect_file(m, project_root, exclude_list, collected)
                    matched_any = True
                # それ以外（非 Markdown ファイル等）は無視
            if not matched_any:
                warnings.append(f"glob は Markdown / ディレクトリにマッチしませんでした: {raw_dir}")
            continue

        # リテラルディレクトリ（従来動作）
        try:
            abs_dir = _resolve_dir(raw_dir, project_root)
        except ValueError as e:
            rejected_dirs.append({"dir": raw_dir, "reason": str(e)})
            continue
        _collect_dir(abs_dir, project_root, exclude_list, collected)

    # --paths-json の明示ファイルと結合
    for raw_path in extra_paths:
        normalized = normalize_path(raw_path)
        collected.add(normalized)

    paths = sorted(collected)
    return {"paths": paths, "rejected_dirs": rejected_dirs, "warnings": warnings}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="ディレクトリ配列を Markdown ファイルパス配列に展開する（FR-N09）"
    )
    parser.add_argument(
        "--dirs-json",
        required=True,
        help="展開するディレクトリの JSON 配列（project-root-relative）。"
        "エントリにグロブメタ文字（* ? [）を含めるとパターン展開する（例: docs/specs/**/design/）",
    )
    parser.add_argument(
        "--exclude-json",
        default=None,
        help="除外するパス・ディレクトリの JSON 配列",
    )
    parser.add_argument(
        "--paths-json",
        default=None,
        help="追加で結合する明示ファイルパスの JSON 配列",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="プロジェクトルート（省略時は CLAUDE_PROJECT_DIR または cwd）",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        dirs_json = json.loads(args.dirs_json)
    except json.JSONDecodeError as e:
        _emit(STATUS_ERROR, error_code="INVALID_JSON", message=f"--dirs-json: {e}")
        return 1
    if not isinstance(dirs_json, list):
        _emit(STATUS_ERROR, error_code="INVALID_JSON", message="--dirs-json はリストである必要があります")
        return 1

    exclude_json = None
    if args.exclude_json:
        try:
            exclude_json = json.loads(args.exclude_json)
        except json.JSONDecodeError as e:
            _emit(STATUS_ERROR, error_code="INVALID_JSON", message=f"--exclude-json: {e}")
            return 1

    paths_json = None
    if args.paths_json:
        try:
            paths_json = json.loads(args.paths_json)
        except json.JSONDecodeError as e:
            _emit(STATUS_ERROR, error_code="INVALID_JSON", message=f"--paths-json: {e}")
            return 1

    project_root = Path(args.project_root) if args.project_root else None

    try:
        result = expand(dirs_json, exclude_json=exclude_json, paths_json=paths_json, project_root=project_root)
    except Exception as e:
        log(f"expand_dirs error: {e}")
        _emit(STATUS_ERROR, error_code="INTERNAL_ERROR", message=str(e))
        return 1

    _emit(STATUS_OK, **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
