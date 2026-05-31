#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""remove_toc.py のユニットテスト（DES-006 §13 / REQ-004 NFR-N03 / FR-N06）。

テスト対象:
- key 全体削除（--key で store_dir 削除。存在/不在冪等 / FR-N06-1）
- path 個別削除（--paths-json で指定エントリのみ削除・残りと順序保持 / FR-N06-2）
- .toc_checksums.yaml の該当エントリ整合除去
- 予約 all（--all）での削除
- --key all（任意指定）→ KEY_RESERVED で reject（FR-N04-4）
- 空 key → KEY_EMPTY で reject
- TOC_NOT_FOUND（個別削除で toc.yaml 不在）
- JSON 契約（status / error_code enum / FR-N08）

テスト方針:
- in-process import（parse_paths_json / remove_paths / render_toc_doc 等）
- subprocess JSON 契約（CLI の status / error_code / counts）の両方を使う。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from remove_toc import (
    parse_paths_json,
    render_toc_doc,
    read_toc_metadata,
    remove_key,
    remove_paths,
)
from toc_store import (
    resolve_store_dir,
    DEFAULT_KEY,
    CHECKSUMS_FILENAME,
    ErrorCode,
    ERROR_CODES,
    STATUSES,
    STATUS_OK,
    STATUS_ERROR,
)
from toc_utils import load_existing_toc, load_checksums

REMOVE_TOC_SCRIPT = os.path.join(SCRIPTS_DIR, 'remove_toc.py')


# 新スキーマ（DES-006 §7.1: doc_type 除去）の toc.yaml。
# 定義順は z, a, m とし、削除後の順序保持を観測する。
SAMPLE_TOC_YAML = """\
# .claude/doc-advisor/toc/keys/<slug>-<hash>/toc.yaml
# Auto-generated - Do not edit directly

metadata:
  name: Sample ToC
  key: docs
  generated_at: 2026-05-30T00:00:00Z
  file_count: 3

docs:
  docs/z.md:
    title: Z Doc
    purpose: zeta purpose
    content_details:
      - z detail
    applicable_tasks:
      - z task
    keywords:
      - zeta
  docs/a.md:
    title: A Doc
    purpose: alpha purpose
    content_details:
      - a detail
    applicable_tasks:
      - a task
    keywords:
      - alpha
  docs/m.md:
    title: M Doc
    purpose: mu purpose
    content_details:
      - m detail
    applicable_tasks:
      - m task
    keywords:
      - mu
"""

SAMPLE_CHECKSUMS_YAML = """\
# Document Search Index checksums (key-based)
# Auto-generated - do not edit
generated_at: 2026-05-30T00:00:00Z
file_count: 3
checksums:
  docs/a.md: aaaaaaaa
  docs/m.md: mmmmmmmm
  docs/z.md: zzzzzzzz
"""


# ===========================================================================
# 共通基盤（一時 project root + store 書き込み + subprocess）
# ===========================================================================

class RemoveTocTestBase(unittest.TestCase):
    """一時 project root と subprocess 実行ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        os.makedirs(self.project_root / '.git', exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _write_store(self, key, toc=SAMPLE_TOC_YAML, checksums=SAMPLE_CHECKSUMS_YAML):
        """store_dir に toc.yaml / .toc_checksums.yaml / meta.yaml を書き出す。"""
        store_dir = self._store_dir(key)
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "toc.yaml").write_text(toc, encoding="utf-8")
        if checksums is not None:
            (store_dir / CHECKSUMS_FILENAME).write_text(checksums, encoding="utf-8")
        (store_dir / "meta.yaml").write_text(
            f"original_key: {key}\nschema_version: 1\n", encoding="utf-8"
        )
        return store_dir

    def _run(self, *args):
        cmd = [sys.executable, REMOVE_TOC_SCRIPT] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )

    def _parse_json_stdout(self, proc):
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(
            len(out.split("\n")), 1, f"stdout must be single JSON: {out}"
        )
        return json.loads(out)


# ===========================================================================
# parse_paths_json（in-process）
# ===========================================================================

class TestParsePathsJson(unittest.TestCase):
    """parse_paths_json の正規化・重複除去・型検証。"""

    def test_basic_array(self):
        self.assertEqual(
            parse_paths_json('["docs/a.md", "docs/b.md"]'),
            ["docs/a.md", "docs/b.md"],
        )

    def test_deduplicates_preserving_first_order(self):
        self.assertEqual(
            parse_paths_json('["docs/a.md", "docs/a.md", "docs/b.md"]'),
            ["docs/a.md", "docs/b.md"],
        )

    def test_blank_tokens_dropped(self):
        self.assertEqual(parse_paths_json('["  ", "docs/a.md"]'), ["docs/a.md"])

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            parse_paths_json("{not json")

    def test_non_array_raises(self):
        with self.assertRaises(ValueError):
            parse_paths_json('{"a": 1}')

    def test_non_string_elements_raise(self):
        with self.assertRaises(ValueError):
            parse_paths_json('["docs/a.md", 1]')


# ===========================================================================
# render_toc_doc / read_toc_metadata（in-process）
# ===========================================================================

class TestRenderTocDoc(unittest.TestCase):
    """render_toc_doc の定義順保持・doc_type 非出力・空 docs。"""

    def _docs(self):
        return {
            "docs/z.md": {"title": "Z", "purpose": "zp", "keywords": ["zeta"]},
            "docs/a.md": {"title": "A", "purpose": "ap", "keywords": ["alpha"]},
        }

    def test_preserves_definition_order(self):
        out = render_toc_doc(self._docs(), key="docs", name="Sample")
        z_pos = out.index("docs/z.md")
        a_pos = out.index("docs/a.md")
        self.assertLess(z_pos, a_pos)

    def test_no_doc_type(self):
        out = render_toc_doc(self._docs(), key="docs", name="Sample")
        self.assertNotIn("doc_type", out)

    def test_metadata_present(self):
        out = render_toc_doc(self._docs(), key="docs", name="Sample")
        self.assertIn("metadata:", out)
        self.assertIn("key: docs", out)
        self.assertIn("file_count: 2", out)

    def test_empty_docs(self):
        out = render_toc_doc({}, key="docs", name="Sample")
        self.assertIn("docs:", out)
        self.assertIn("{}", out)
        self.assertIn("file_count: 0", out)

    def test_round_trip_through_loader(self):
        """render_toc_doc → load_existing_toc で docs が往復する。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "toc.yaml"
            p.write_text(
                render_toc_doc(self._docs(), key="docs", name="Sample"),
                encoding="utf-8",
            )
            loaded = load_existing_toc(p)
            self.assertEqual(list(loaded.keys()), ["docs/z.md", "docs/a.md"])
            self.assertEqual(loaded["docs/z.md"]["title"], "Z")


class TestReadTocMetadata(unittest.TestCase):
    """read_toc_metadata が metadata セクションのスカラを読む。"""

    def test_reads_name_and_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "toc.yaml"
            p.write_text(SAMPLE_TOC_YAML, encoding="utf-8")
            meta = read_toc_metadata(p)
            self.assertEqual(meta.get("name"), "Sample ToC")
            self.assertEqual(meta.get("key"), "docs")

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_toc_metadata(Path(d) / "nope.yaml"), {})


# ===========================================================================
# remove_key（in-process / FR-N06-1）
# ===========================================================================

class TestRemoveKeyInProcess(RemoveTocTestBase):
    """remove_key の削除・冪等。"""

    def test_removes_existing_store(self):
        store_dir = self._write_store("docs")
        self.assertTrue(store_dir.exists())
        ok, existed = remove_key(store_dir)
        self.assertTrue(ok)
        self.assertTrue(existed)
        self.assertFalse(store_dir.exists())

    def test_idempotent_when_absent(self):
        store_dir = self._store_dir("docs")  # 作らない
        self.assertFalse(store_dir.exists())
        ok, existed = remove_key(store_dir)
        self.assertTrue(ok)
        self.assertFalse(existed)


# ===========================================================================
# remove_paths（in-process / FR-N06-2）
# ===========================================================================

class TestRemovePathsInProcess(RemoveTocTestBase):
    """remove_paths の個別削除・順序保持・checksums 整合・TOC_NOT_FOUND。"""

    def test_removes_specified_entry_only(self):
        store_dir = self._write_store("docs")
        ok, deleted, missing, found = remove_paths(store_dir, ["docs/a.md"], "docs")
        self.assertTrue(ok)
        self.assertTrue(found)
        self.assertEqual(deleted, ["docs/a.md"])
        self.assertEqual(missing, [])
        # 残りエントリと定義順（z, m）が保持される
        remaining = load_existing_toc(store_dir / "toc.yaml")
        self.assertEqual(list(remaining.keys()), ["docs/z.md", "docs/m.md"])

    def test_deleted_preserves_definition_order(self):
        """削除対象が複数のとき deleted は ToC 定義順（z, a）になる。"""
        store_dir = self._write_store("docs")
        # 要求順は a, z だが定義順は z, a
        ok, deleted, missing, found = remove_paths(
            store_dir, ["docs/a.md", "docs/z.md"], "docs"
        )
        self.assertTrue(ok)
        self.assertEqual(deleted, ["docs/z.md", "docs/a.md"])
        remaining = load_existing_toc(store_dir / "toc.yaml")
        self.assertEqual(list(remaining.keys()), ["docs/m.md"])

    def test_checksums_entry_removed(self):
        store_dir = self._write_store("docs")
        remove_paths(store_dir, ["docs/a.md"], "docs")
        checksums = load_checksums(store_dir / CHECKSUMS_FILENAME)
        self.assertNotIn("docs/a.md", checksums)
        self.assertIn("docs/m.md", checksums)
        self.assertIn("docs/z.md", checksums)

    def test_missing_path_reported_not_deleted(self):
        store_dir = self._write_store("docs")
        ok, deleted, missing, found = remove_paths(
            store_dir, ["docs/nope.md"], "docs"
        )
        self.assertTrue(ok)
        self.assertEqual(deleted, [])
        self.assertEqual(missing, ["docs/nope.md"])
        # ToC は変化しない（全 3 件残る）
        remaining = load_existing_toc(store_dir / "toc.yaml")
        self.assertEqual(len(remaining), 3)

    def test_toc_not_found(self):
        store_dir = self._store_dir("docs")  # toc.yaml 不在
        ok, deleted, missing, found = remove_paths(store_dir, ["docs/a.md"], "docs")
        self.assertFalse(ok)
        self.assertFalse(found)

    def test_no_checksums_file_is_tolerated(self):
        """checksums 不在でも toc.yaml の削除は成立する。"""
        store_dir = self._write_store("docs", checksums=None)
        ok, deleted, _, found = remove_paths(store_dir, ["docs/a.md"], "docs")
        self.assertTrue(ok)
        self.assertEqual(deleted, ["docs/a.md"])
        remaining = load_existing_toc(store_dir / "toc.yaml")
        self.assertEqual(list(remaining.keys()), ["docs/z.md", "docs/m.md"])


# ===========================================================================
# CLI 統合: key 全体削除（JSON / FR-N06-1）
# ===========================================================================

class TestRemoveKeyCli(RemoveTocTestBase):
    """remove_toc.py --key の store_dir 削除（存在/不在冪等）。"""

    def test_removes_store_dir(self):
        store_dir = self._write_store("docs")
        proc = self._run("--key", "docs")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertIsNone(data["error_code"])
        self.assertEqual(data["key"], "docs")
        self.assertEqual(data["counts"]["deleted"], 1)
        self.assertFalse(store_dir.exists())

    def test_idempotent_absent_store(self):
        proc = self._run("--key", "docs")  # store 不在
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertIsNone(data["error_code"])
        self.assertEqual(data["counts"]["deleted"], 0)


# ===========================================================================
# CLI 統合: path 個別削除（JSON / FR-N06-2）
# ===========================================================================

class TestRemovePathsCli(RemoveTocTestBase):
    """remove_toc.py --paths-json の個別削除と JSON 出力。"""

    def test_removes_specified_paths(self):
        store_dir = self._write_store("docs")
        proc = self._run("--key", "docs", "--paths-json", '["docs/a.md"]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertEqual(data["counts"]["deleted"], 1)
        self.assertEqual(data["normalized_paths"], ["docs/a.md"])
        # store_dir 自体は残る（個別削除なので）
        self.assertTrue(store_dir.exists())
        remaining = load_existing_toc(store_dir / "toc.yaml")
        self.assertEqual(list(remaining.keys()), ["docs/z.md", "docs/m.md"])

    def test_missing_path_in_warnings(self):
        self._write_store("docs")
        proc = self._run("--key", "docs", "--paths-json", '["docs/nope.md"]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["counts"]["deleted"], 0)
        self.assertTrue(data["warnings"])

    def test_toc_not_found(self):
        proc = self._run("--key", "docs", "--paths-json", '["docs/a.md"]')
        self.assertEqual(proc.returncode, 1)
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_ERROR)
        self.assertEqual(data["error_code"], ErrorCode.TOC_NOT_FOUND)
        self.assertEqual(data["key"], "docs")

    def test_invalid_paths_json(self):
        self._write_store("docs")
        proc = self._run("--key", "docs", "--paths-json", "{not json")
        self.assertEqual(proc.returncode, 1)
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_ERROR)
        self.assertEqual(data["error_code"], ErrorCode.INVALID_PATH)


# ===========================================================================
# CLI 統合: 予約 all / key 解決エラー（FR-N04-4）
# ===========================================================================

class TestRemoveKeyResolution(RemoveTocTestBase):
    """予約 all（--all）削除 / --key all reject / 空 key reject。"""

    def test_all_flag_removes_reserved_store(self):
        store_dir = self._write_store(DEFAULT_KEY)
        proc = self._run("--all")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertEqual(data["key"], DEFAULT_KEY)
        self.assertFalse(store_dir.exists())

    def test_key_omitted_resolves_to_reserved_all(self):
        store_dir = self._write_store(DEFAULT_KEY)
        proc = self._run()  # --key も --all も無し
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["key"], DEFAULT_KEY)
        self.assertFalse(store_dir.exists())

    def test_user_key_all_is_rejected(self):
        """--key all（任意指定）は KEY_RESERVED で reject（FR-N04-4）。"""
        proc = self._run("--key", "all")
        self.assertEqual(proc.returncode, 1)
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_ERROR)
        self.assertEqual(data["error_code"], ErrorCode.KEY_RESERVED)

    def test_empty_key_is_rejected(self):
        proc = self._run("--key", "   ")
        self.assertEqual(proc.returncode, 1)
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_ERROR)
        self.assertEqual(data["error_code"], ErrorCode.KEY_EMPTY)


# ===========================================================================
# JSON 契約: status / error_code enum の固定（FR-N08-2）
# ===========================================================================

class TestJsonContractEnums(RemoveTocTestBase):
    """全経路の status / error_code が enum 集合に収まることを固定する。"""

    def test_status_and_error_code_on_success(self):
        self._write_store("docs")
        proc = self._run("--key", "docs")
        data = self._parse_json_stdout(proc)
        self.assertIn(data["status"], STATUSES)
        self.assertIn(data["error_code"], ERROR_CODES | {None})

    def test_status_and_error_code_on_error(self):
        proc = self._run("--key", "docs", "--paths-json", '["docs/a.md"]')  # toc 不在
        data = self._parse_json_stdout(proc)
        self.assertIn(data["status"], STATUSES)
        self.assertIn(data["error_code"], ERROR_CODES | {None})

    def test_reserved_key_error_code_in_enum(self):
        proc = self._run("--key", "all")
        data = self._parse_json_stdout(proc)
        self.assertIn(data["error_code"], ERROR_CODES)


if __name__ == '__main__':
    unittest.main()
