#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全文行マッチ検索（grep_docs.py）— doc-db plugin

.doc_structure.yaml の root_dirs / exclude に従い対象 .md を走査し、
キーワードの行単位・大文字小文字無視・部分一致でヒットを返す。
doc-advisor 本体への runtime 依存は持たない（doc_structure.py でパス解決）。

Usage:
    python3 grep_docs.py --category {rules|specs} --keyword "<text>" [--doc-type t1,t2]

Run from: プロジェクトルート（または CLAUDE_PROJECT_DIR が指すルート）

stdout 出力:
    {
      "status": "ok",
      "keyword": "<keyword>",
      "results": [{"path": "<rel>", "line": N, "content": "<line text>"}]
    }

規約:
    - specs かつ --doc-type 省略時は .doc_structure.yaml の全 doc_type を対象とする
    - rules 時は --doc-type を無視（FNC-006 OP-05）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from _utils import get_project_root, log, normalize_path
from doc_structure import (
    invert_doc_types_map,
    load_doc_structure,
    resolve_files,
    resolve_files_by_doc_type,
    validate_doc_structure,
)


def parse_args(argv: List[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Keyword line search over doc-db scoped markdown files",
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=["rules", "specs"],
        help="rules または specs",
    )
    parser.add_argument(
        "--keyword",
        required=True,
        help="検索キーワード（行内・大文字小文字無視・部分一致）",
    )
    parser.add_argument(
        "--doc-type",
        default="",
        help="specs のみ。カンマ区切り（例: requirement,design）。省略時は全 doc_type",
    )
    return parser.parse_args(argv)


def _resolve_target_rel_paths(project_root: Path, category: str, doc_type: str) -> List[str]:
    """対象ファイルを解決する。--doc-type 省略時は .doc_structure.yaml の全 doc_type を対象とする。"""
    config, raw_content = load_doc_structure(str(project_root))
    validation = validate_doc_structure(config, raw_content)
    if not validation.get("valid"):
        raise ValueError(validation.get("error", "invalid .doc_structure.yaml"))

    if category == "rules":
        return resolve_files(config, "rules", str(project_root))

    # specs
    specs = config.get("specs", {})
    doc_types_map = specs.get("doc_types_map", {})
    allowed = set(invert_doc_types_map(doc_types_map).keys())

    dt = doc_type.strip()
    if dt:
        types = [x.strip() for x in dt.split(",") if x.strip()]
        invalid = [t for t in types if t not in allowed]
        if invalid:
            raise ValueError(
                f"unsupported doc_type: {','.join(invalid)}; allowed: {','.join(sorted(allowed))}"
            )
    else:
        types = sorted(allowed)

    files: List[str] = []
    for t in types:
        files.extend(resolve_files_by_doc_type(config, "specs", t, str(project_root)))
    return sorted(set(files))


def search_lines(project_root: Path, rel_paths: List[str], keyword: str) -> dict:
    """行単位の keyword 検索を実行する。

    Returns:
        dict with keys: "results" (List[dict]), "skipped_files" (List[str])
    """
    keyword_lower = keyword.lower()
    results: List[dict] = []
    skipped_files: List[str] = []
    for rel in sorted(rel_paths):
        abs_path = project_root / rel
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, start=1):
                    if keyword_lower in line.lower():
                        results.append(
                            {
                                "path": normalize_path(rel),
                                "line": line_no,
                                "content": line.rstrip("\r\n"),
                            }
                        )
        except (OSError, PermissionError) as e:
            log(f"Warning: skipping unreadable file {abs_path}: {e}")
            skipped_files.append(normalize_path(rel))
            continue
    return {"results": results, "skipped_files": skipped_files}


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    keyword = args.keyword.strip()
    if not keyword or len(keyword) > 1024:
        print(
            json.dumps(
                {"status": "error", "error": "--keyword must be 1..1024 chars."},
                ensure_ascii=False,
            )
        )
        return 1

    project_root = get_project_root()

    try:
        rel_paths = _resolve_target_rel_paths(project_root, args.category, args.doc_type)
    except FileNotFoundError as e:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(e),
                },
                ensure_ascii=False,
            )
        )
        return 1
    except ValueError as e:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(e),
                },
                ensure_ascii=False,
            )
        )
        return 1

    search_result = search_lines(project_root, rel_paths, keyword)
    out = {
        "status": "partial" if search_result["skipped_files"] else "ok",
        "keyword": args.keyword,
        "results": search_result["results"],
    }
    if search_result["skipped_files"]:
        out["skipped_files"] = search_result["skipped_files"]
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
