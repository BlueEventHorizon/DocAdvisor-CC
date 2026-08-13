#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_from_toc.py（ToC → フロントマターの転記）のテスト。

このモジュールの存在意義は「書き戻しを決定論的な転記にすること」である。したがって
検証すべきは次の 2 点である。

1. ToC の値が**そのまま**メタデータになること（AI の再起草を挟まない）
2. 写してはいけない状態を確実に弾くこと（陳腐化ガード）

とくに陳腐化ガードは、落ちると「索引時点の古い記述に信頼できる body_hash が打刻され、
以後の索引が転記だけで済ませて古い内容が固定される」という回復しにくい状態を作る。

テスト対象:
- ToC のエントリ 5 フィールドがそのまま metadata になること（値の同一性）
- doc-advisor が所有しないキーを写さないこと（fm_write が拒否するため）
- ToC に無い / 索引後に本文が変わった / checksums に記録が無い / エントリが
  揃っていない、の 4 分類が正しい reason で返ること
- 予約 key `all` の ToC を読めること（読み取り経路では拒否しない）
- toc.yaml 不在が FromTocError になること

テスト方針:
- toc.yaml は **本番の writer（merge_toc.write_toc_atomic）で生成する**。テストが
  独自に YAML を組み立てると、reader と writer のずれをこのテストが隠してしまう
- project_root は明示的に渡す（CLAUDE_PROJECT_DIR / cwd に依存させない）
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'plugins', 'doc-advisor', 'scripts')
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from merge_toc import write_toc_atomic
from toc_store import CHECKSUMS_FILENAME, DEFAULT_KEY, TOC_FILENAME, resolve_store_dir
from toc_utils import calculate_file_hash, write_checksums_yaml

from fm_from_toc import (
    COPIED_FIELDS,
    NEEDS_AI_REASONS,
    REASON_BODY_CHANGED,
    REASON_INCOMPLETE_ENTRY,
    REASON_NOT_IN_TOC,
    REASON_UNVERIFIABLE,
    FromTocError,
    extract_metadata,
    load_toc,
    resolve_entry,
)

BODY = "# タイトル\n\n本文の内容。\n"

TOC_ENTRY = {
    "title": "Indexed Document",
    "purpose": "Serve as the transcription source for the write-back path",
    "content_details": ["detail A", "detail B"],
    "applicable_tasks": ["task A"],
    "keywords": ["fm_from_toc", "writeback"],
}


class FromTocTestBase(unittest.TestCase):
    """key の store 配下に toc.yaml と checksums を持つ疑似プロジェクトを組む。"""

    KEY = "rules"

    def setUp(self):
        self.project_root = Path(tempfile.mkdtemp())
        self.store_dir = resolve_store_dir(self.KEY, self.project_root)

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _write_doc(self, rel_path, text=BODY):
        path = self.project_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _write_toc(self, docs, key=None):
        key = key or self.KEY
        store_dir = resolve_store_dir(key, self.project_root)
        store_dir.mkdir(parents=True, exist_ok=True)
        ok = write_toc_atomic(
            docs, store_dir / TOC_FILENAME,
            key=key, toc_rel=f"{store_dir.name}/{TOC_FILENAME}",
        )
        self.assertTrue(ok, "toc.yaml の書き出しに失敗した")

    def _write_checksums(self, rel_paths, key=None):
        """指定パスの現在の hash を索引時点の hash として記録する。"""
        key = key or self.KEY
        store_dir = resolve_store_dir(key, self.project_root)
        checksums = {
            rel: calculate_file_hash(self.project_root / rel) for rel in rel_paths
        }
        write_checksums_yaml(checksums, store_dir / CHECKSUMS_FILENAME)

    def _source(self, key=None):
        return load_toc(key or self.KEY, self.project_root)


class TestTranscription(FromTocTestBase):
    """ToC の値がそのままメタデータになること"""

    def test_entry_fields_are_copied_verbatim(self):
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": dict(TOC_ENTRY)})
        self._write_checksums(["docs/a.md"])

        metadata, reason, violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(reason)
        self.assertEqual(violations, [])
        self.assertEqual(
            metadata, TOC_ENTRY,
            "ToC の 5 フィールドは言い換えず、そのまま metadata になる",
        )

    def test_paths_lists_every_indexed_document_in_order(self):
        for rel in ("docs/b.md", "docs/a.md"):
            self._write_doc(rel)
        self._write_toc({rel: dict(TOC_ENTRY) for rel in ("docs/b.md", "docs/a.md")})

        self.assertEqual(self._source().paths, ["docs/a.md", "docs/b.md"])

    def test_unowned_keys_are_not_copied(self):
        """doc-advisor が所有しないキーは写さない（fm_write が拒否するため）。"""
        entry = dict(TOC_ENTRY)
        entry["doc_type"] = "rule"
        entry["body_hash"] = "sha256:" + "0" * 64

        metadata = extract_metadata(entry)

        self.assertEqual(sorted(metadata), sorted(COPIED_FIELDS))
        self.assertNotIn("doc_type", metadata)
        self.assertNotIn(
            "body_hash", metadata,
            "body_hash は整形後に fm_write が打刻する。写してはならない",
        )

    def test_reserved_key_toc_is_readable(self):
        """単体モードの予約 key `all` の ToC も読める（読み取りは拒否しない）。"""
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": dict(TOC_ENTRY)}, key=DEFAULT_KEY)
        self._write_checksums(["docs/a.md"], key=DEFAULT_KEY)

        metadata, reason, _violations = resolve_entry(
            self._source(DEFAULT_KEY), "docs/a.md")

        self.assertIsNone(reason)
        self.assertEqual(metadata["title"], TOC_ENTRY["title"])


class TestStalenessGuard(FromTocTestBase):
    """写してはいけない状態を弾くこと"""

    def test_path_absent_from_the_toc(self):
        self._write_doc("docs/a.md")
        self._write_toc({"docs/other.md": dict(TOC_ENTRY)})

        metadata, reason, _violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_NOT_IN_TOC)

    def test_body_edited_after_indexing_is_not_transcribed(self):
        """索引後に本文が変わっていれば、その ToC エントリは現在の本文を説明しない。"""
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": dict(TOC_ENTRY)})
        self._write_checksums(["docs/a.md"])

        self._write_doc("docs/a.md", BODY + "\n本文を書き換えた。\n")

        metadata, reason, _violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_BODY_CHANGED)

    def test_missing_checksum_record_is_unverifiable(self):
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": dict(TOC_ENTRY)})
        # checksums を書かない = 索引時点の hash が分からない

        metadata, reason, _violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_UNVERIFIABLE)

    def test_deleted_file_is_unverifiable(self):
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": dict(TOC_ENTRY)})
        self._write_checksums(["docs/a.md"])
        (self.project_root / "docs/a.md").unlink()

        metadata, reason, _violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_UNVERIFIABLE)

    def test_incomplete_entry_reports_the_missing_field(self):
        entry = dict(TOC_ENTRY)
        del entry["keywords"]
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": entry})
        self._write_checksums(["docs/a.md"])

        metadata, reason, violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_INCOMPLETE_ENTRY)
        self.assertEqual([field for _code, field, _detail in violations], ["keywords"])

    def test_value_range_violation_in_the_entry_is_rejected(self):
        """値域規則は fm_core の実装を共有する（転記側で別の規則を持たない）。"""
        entry = dict(TOC_ENTRY)
        entry["purpose"] = "x" * 201
        self._write_doc("docs/a.md")
        self._write_toc({"docs/a.md": entry})
        self._write_checksums(["docs/a.md"])

        metadata, reason, violations = resolve_entry(self._source(), "docs/a.md")

        self.assertIsNone(metadata)
        self.assertEqual(reason, REASON_INCOMPLETE_ENTRY)
        self.assertIn("purpose", [field for _code, field, _detail in violations])

    def test_reasons_are_within_the_declared_domain(self):
        self.assertIn(REASON_NOT_IN_TOC, NEEDS_AI_REASONS)
        self.assertIn(REASON_BODY_CHANGED, NEEDS_AI_REASONS)
        self.assertIn(REASON_UNVERIFIABLE, NEEDS_AI_REASONS)
        self.assertIn(REASON_INCOMPLETE_ENTRY, NEEDS_AI_REASONS)


class TestTocAbsence(FromTocTestBase):
    def test_missing_toc_raises(self):
        with self.assertRaises(FromTocError):
            load_toc(self.KEY, self.project_root)


class TestIndependenceBoundary(unittest.TestCase):
    """依存の向きが派生 → 中心であること（DES-008 §6.1）。"""

    def test_toc_side_does_not_import_the_frontmatter_side(self):
        """中心側の script が frontmatter/ を知らないこと。

        例外は転記の起動 1 箇所（index_docs.py の _transcribe）のみである。ここが
        崩れると「frontmatter/ の削除で撤回できる」性質が失われる。
        """
        for name in ("toc_store.py", "toc_utils.py", "merge_toc.py", "prepare_toc.py"):
            source = Path(SCRIPTS_DIR, name).read_text(encoding="utf-8")
            for token in ("fm_core", "fm_read", "fm_write", "fm_run", "fm_from_toc"):
                self.assertNotIn(
                    token, source,
                    f"{name} が frontmatter 側の {token} を参照している"
                    "（依存は派生 → 中心の一方向。DES-008 §6.1）",
                )


if __name__ == "__main__":
    unittest.main()
