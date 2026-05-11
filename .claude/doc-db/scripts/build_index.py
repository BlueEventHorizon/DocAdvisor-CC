#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc-db の chunk 単位 index を構築する。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import chunk_extractor
from _utils import calculate_file_hash, load_checksums
from doc_structure import (
    invert_doc_types_map,
    load_doc_structure,
    resolve_files,
    resolve_files_by_doc_type,
)
from embedding_api import EMBEDDING_MODEL, call_embedding_api

SCHEMA_VERSION = "1.0"
CHECKSUMS_SUFFIX = ".checksums.yaml"


def _event(event_type: str, **fields):
    payload = {"event_type": event_type}
    payload.update(fields)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Build doc-db index")
    parser.add_argument("--category", required=True, choices=["rules", "specs"])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--doc-type", default="")
    return parser.parse_args()


def get_index_path(project_root: Path, category: str, doc_type: str = "") -> Path:
    if category == "specs":
        suffix = f"{doc_type}_index.json" if doc_type else "specs_index.json"
        return project_root / f".claude/doc-db/index/specs/{suffix}"
    return project_root / ".claude/doc-db/index/rules/rules_index.json"


def get_checksums_path(index_path: Path) -> Path:
    return index_path.with_suffix(index_path.suffix + CHECKSUMS_SUFFIX)


def _read_checksums_generated_at(checksums_path: Path) -> str:
    if not checksums_path.exists():
        return ""
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("generated_at:"):
            return line.split(":", 1)[1].strip()
    return ""


def load_index(index_path: Path) -> Dict:
    if not index_path.exists():
        return {"metadata": {}, "entries": {}}
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _render_checksums_content(checksums: Dict[str, str], generated_at: str) -> str:
    lines = [
        "# doc-db checksums",
        "# Auto-generated - do not edit",
        f"generated_at: {generated_at}",
        f"file_count: {len(checksums)}",
        "checksums:",
    ]
    for rel_path, hash_value in sorted(checksums.items()):
        lines.append(f"  {rel_path}: {hash_value}")
    return "\n".join(lines) + "\n"


def save_index_and_checksums_two_phase(
    index: Dict,
    index_path: Path,
    checksums: Dict[str, str],
    checksums_path: Path,
    generated_at: str,
):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    checksums_path.parent.mkdir(parents=True, exist_ok=True)
    index_tmp = None
    checksums_tmp = None
    old_index_bytes = index_path.read_bytes() if index_path.exists() else None
    old_checksums_bytes = checksums_path.read_bytes() if checksums_path.exists() else None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=index_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tf_index:
            index_tmp = Path(tf_index.name)
            json.dump(index, tf_index, ensure_ascii=False, separators=(",", ":"))
            tf_index.flush()
            os.fsync(tf_index.fileno())
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=checksums_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tf_checksums:
            checksums_tmp = Path(tf_checksums.name)
            tf_checksums.write(_render_checksums_content(checksums, generated_at))
            tf_checksums.flush()
            os.fsync(tf_checksums.fileno())
        os.replace(index_tmp, index_path)
        try:
            os.replace(checksums_tmp, checksums_path)
        except Exception:
            if old_index_bytes is not None:
                index_path.write_bytes(old_index_bytes)
            else:
                index_path.unlink(missing_ok=True)
            if old_checksums_bytes is not None:
                checksums_path.write_bytes(old_checksums_bytes)
            else:
                checksums_path.unlink(missing_ok=True)
            raise
    except Exception:
        if index_tmp and index_tmp.exists():
            index_tmp.unlink(missing_ok=True)
        if checksums_tmp and checksums_tmp.exists():
            checksums_tmp.unlink(missing_ok=True)
        raise


def resolve_target_files(project_root: Path, category: str, doc_type: str) -> List[str]:
    config, _ = load_doc_structure(str(project_root))
    if doc_type:
        files = []
        for t in [x.strip() for x in doc_type.split(",") if x.strip()]:
            files.extend(resolve_files_by_doc_type(config, category, t, str(project_root)))
        return sorted(set(files))
    return resolve_files(config, category, str(project_root))


def resolve_specs_doc_types(project_root: Path) -> List[str]:
    config, _ = load_doc_structure(str(project_root))
    specs = config.get("specs", {})
    doc_types_map = specs.get("doc_types_map", {})
    return sorted(invert_doc_types_map(doc_types_map).keys())


def _validate_existing_schema(existing: Dict, full: bool):
    schema = existing.get("metadata", {}).get("schema_version")
    if schema and schema != SCHEMA_VERSION and not full:
        raise RuntimeError("schema mismatch: run with --full")


def _classify_embedding_error(exc: Exception) -> str:
    """DES-026 §4.1 の error_type 分類: rate_limit | timeout | 5xx | invalid_request | other"""
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return "rate_limit"
        if 500 <= exc.code < 600:
            return "5xx"
        if exc.code in (400, 422):
            return "invalid_request"
    if isinstance(exc, urllib.error.URLError):
        reason = str(getattr(exc, "reason", ""))
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return "timeout"
    msg = str(exc).lower()
    if "429" in msg or "rate" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "500" in msg or "502" in msg or "503" in msg:
        return "5xx"
    return "other"


def _embed_chunks(chunk_records: List[Dict], api_key: str):
    texts = [c["body"] if c["body"].strip() else c["path"] for c in chunk_records]
    vectors = call_embedding_api(texts, api_key)
    for i, vector in enumerate(vectors):
        chunk_records[i]["embedding"] = vector
    return chunk_records


def _run_build_one(project_root: Path, category: str, full: bool = False, doc_type: str = "") -> Tuple[int, Dict]:
    index_path = get_index_path(project_root, category, doc_type)
    checksums_path = get_checksums_path(index_path)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        _event("validation_error", error="OPENAI_API_KEY is required")
        return 1, {"status": "error", "error": "OPENAI_API_KEY is required"}

    existing = load_index(index_path)
    try:
        _validate_existing_schema(existing, full)
    except RuntimeError as e:
        _event("validation_error", error=str(e), hint="use --full")
        return 2, {"status": "error", "error": str(e), "hint": "use --full"}

    targets = resolve_target_files(project_root, category, doc_type)
    current_checksums = {p: calculate_file_hash(project_root / p) for p in targets}
    old_checksums = {} if full else load_checksums(checksums_path)

    changed = [p for p in targets if old_checksums.get(p) != current_checksums.get(p)]
    deleted = [p for p in old_checksums if p not in current_checksums]
    if not changed and not deleted and existing.get("entries"):
        return 0, {"status": "ok", "message": "up-to-date"}

    entries = {} if full else dict(existing.get("entries", {}))
    for key, val in list(entries.items()):
        if val.get("path") in deleted:
            entries.pop(key, None)
    for key, val in list(entries.items()):
        if val.get("path") in changed:
            entries.pop(key, None)

    failed_chunks: List[Dict] = []
    to_embed: List[Dict] = []
    for rel_path in changed:
        abs_path = project_root / rel_path
        text = abs_path.read_text(encoding="utf-8")
        chunks = chunk_extractor.extract_chunks(rel_path, text)
        for c in chunks:
            to_embed.append(c)

    if to_embed:
        try:
            _embed_chunks(to_embed, api_key)
        except Exception as e:  # noqa: BLE001
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            error_type = _classify_embedding_error(e)
            for c in to_embed:
                failed_chunks.append(
                    {
                        "chunk_id": c["chunk_id"],
                        "path": c["path"],
                        "error_type": error_type,
                        "message": str(e),
                        "attempts": 1,
                        "last_failed_at": now,
                    }
                )
            to_embed = []
            _event("incomplete_detected", failed_chunks=len(failed_chunks), reason=str(e))

    for c in to_embed:
        key = f"{c['path']}#{c['chunk_id']}"
        entries[key] = {
            "path": c["path"],
            "chunk_id": c["chunk_id"],
            "heading_path": c["heading_path"],
            "body": c["body"],
            "char_range": c["char_range"],
            "embedding": c["embedding"],
            "checksum": current_checksums.get(c["path"], ""),
        }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dims = 0
    if entries:
        dims = len(next(iter(entries.values())).get("embedding", []))
    index = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "category": category,
            "doc_type": doc_type or None,
            "model": EMBEDDING_MODEL,
            "dimensions": dims,
            "generated_at": now,
            "chunk_count": len(entries),
            "file_count": len({v["path"] for v in entries.values()}),
            "build_state": "incomplete" if failed_chunks else "complete",
            "failed_chunks": failed_chunks,
        },
        "entries": entries,
    }
    save_index_and_checksums_two_phase(index, index_path, current_checksums, checksums_path, now)
    return 0, {
        "status": "ok",
        "index": str(index_path.relative_to(project_root)),
        "build_state": index["metadata"]["build_state"],
        "failed_count": len(failed_chunks),
    }


def run_build(project_root: Path, category: str, full: bool = False, doc_type: str = "") -> Tuple[int, Dict]:
    if category == "specs":
        if doc_type:
            doc_types = [x.strip() for x in doc_type.split(",") if x.strip()]
        else:
            doc_types = resolve_specs_doc_types(project_root)
        allowed = set(resolve_specs_doc_types(project_root))
        invalid = [d for d in doc_types if d not in allowed]
        if invalid:
            _event(
                "validation_error",
                error=f"unsupported doc_type: {','.join(invalid)}",
                hint=f"allowed: {','.join(sorted(allowed))}",
            )
            return 2, {
                "status": "error",
                "error": f"unsupported doc_type: {','.join(invalid)}",
                "hint": f"allowed: {','.join(sorted(allowed))}",
            }
        for one_type in doc_types:
            rc, result = _run_build_one(project_root, category, full=full, doc_type=one_type)
            if rc != 0:
                return rc, result
        return 0, {"status": "ok"}
    if doc_type.strip():
        _event("validation_error", error="doc_type is only valid for specs category")
        return 2, {
            "status": "error",
            "error": "doc_type is only valid for specs category",
            "hint": "remove --doc-type or use --category specs",
        }
    return _run_build_one(project_root, category, full=full, doc_type=doc_type)


def _run_check_one(project_root: Path, category: str, doc_type: str = "") -> Dict:
    index_path = get_index_path(project_root, category, doc_type)
    checksums_path = get_checksums_path(index_path)
    if not index_path.exists():
        return {"status": "stale", "reason": "index_not_found"}
    index = load_index(index_path)
    files = resolve_target_files(project_root, category, doc_type)
    disk = {p: calculate_file_hash(project_root / p) for p in files}
    saved = load_checksums(checksums_path)
    if disk != saved:
        return {"status": "stale", "reason": "checksum_mismatch"}
    checksum_generated_at = _read_checksums_generated_at(checksums_path)
    if checksum_generated_at and checksum_generated_at != index.get("metadata", {}).get("generated_at"):
        return {"status": "stale", "reason": "generated_at_mismatch"}
    return {"status": "fresh"}


def run_check(project_root: Path, category: str) -> List[Dict]:
    if category == "specs":
        doc_types = resolve_specs_doc_types(project_root)
        return [_run_check_one(project_root, category, one_type) for one_type in doc_types]
    return [_run_check_one(project_root, category)]


def main():
    args = parse_args()
    project_root = Path.cwd().resolve()
    if args.check:
        results = run_check(project_root, args.category)
        for r in results:
            print(json.dumps(r))
        return 0
    rc, result = run_build(project_root, args.category, full=args.full, doc_type=args.doc_type)
    print(json.dumps(result))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
