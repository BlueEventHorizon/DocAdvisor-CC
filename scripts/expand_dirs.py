#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
expand_dirs.py — ディレクトリ配列を Markdown ファイルパス配列に展開するヘルパー（FR-N09）

index-docs SKILL がディレクトリ入力（--dirs-json）を受け取った際に、
prepare_toc.py へ渡す --paths-json を生成するために呼び出す。

責務:
- --dirs-json のディレクトリを rglob で展開し Markdown を収集
- SYSTEM_EXCLUDE_PATTERNS を常時適用（--exclude-json の有無に関わらず）
- --exclude-json で指定したパス・ディレクトリを追加除外
- root 外 symlink を除外
- --paths-json の明示ファイルと結合・重複除去
- stdout に単一 JSON を出力（NFR / FR-N08）

CLI:
    python3 expand_dirs.py --dirs-json '["docs/rules/", "docs/specs/"]'
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
    """ディレクトリ相対パスを絶対パスに解決し、存在するディレクトリかを検証する。

    Returns:
        Path: 絶対パス
    Raises:
        ValueError: 不在・非ディレクトリ・traversal の場合
    """
    normalized = normalize_path(rel_dir).rstrip("/")
    p = Path(normalized)
    if p.is_absolute():
        raise ValueError(f"絶対パスは使用できません: {rel_dir}")
    resolved = (project_root / p).resolve()
    try:
        project_root.resolve().relative_to(project_root.resolve())
    except ValueError:
        pass
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        raise ValueError(f"project root 外のディレクトリです: {rel_dir}")
    if not resolved.exists():
        raise ValueError(f"存在しません: {rel_dir}")
    if not resolved.is_dir():
        raise ValueError(f"ディレクトリではありません: {rel_dir}")
    return resolved


def _build_exclude_set(exclude_list, project_root):
    """--exclude-json のパス文字列を正規化した文字列 set に変換する。

    ディレクトリ指定（末尾 / あり・なし問わず）と
    ファイル指定の両方を含む set を返す。
    """
    result = set()
    for raw in exclude_list:
        normalized = normalize_path(raw.rstrip("/"))
        result.add(normalized)
    return result


def _is_user_excluded(rel_path_str, exclude_set):
    """rel_path_str が exclude_set のいずれかと一致またはその配下かを判定する。"""
    for excl in exclude_set:
        if rel_path_str == excl:
            return True
        if rel_path_str.startswith(excl + "/"):
            return True
    return False


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
    exclude_set = _build_exclude_set(exclude_list, project_root)

    collected = set()
    rejected_dirs = []
    warnings = []

    for raw_dir in dirs_json:
        try:
            abs_dir = _resolve_dir(raw_dir, project_root)
        except ValueError as e:
            rejected_dirs.append({"dir": raw_dir, "reason": str(e)})
            continue

        for md_file in rglob_follow_symlinks(abs_dir, MARKDOWN_GLOB):
            # システム固定除外
            if should_exclude(md_file, project_root, SYSTEM_EXCLUDE_PATTERNS):
                continue
            # root 外 symlink を除外
            try:
                resolved = resolve_within_root(md_file, project_root)
            except PathRejection:
                continue
            # project-root-relative に変換
            try:
                rel = normalize_path(str(resolved.relative_to(project_root)))
            except ValueError:
                continue
            # ユーザー指定除外
            if _is_user_excluded(rel, exclude_set):
                continue
            collected.add(rel)

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
        help="展開するディレクトリの JSON 配列（project-root-relative）",
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
