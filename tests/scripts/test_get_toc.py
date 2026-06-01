#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_toc.py のユニットテスト（DES-005 §13 / REQ-001 NFR-N03 / FR-N05）。

テスト対象:
- 全体取得（--key / --all）
- --paths 縮小抽出（一致エントリのみ・定義順保持）
- ToC の定義順保持の固定（FR-N05-2 観測可能基準）
- score / rank フィールド非存在の固定（FR-N05-2 観測可能基準）
- TOC_NOT_FOUND（toc.yaml 不在）
- --key 省略 → 予約 key 'all' に解決
- --key all（任意指定）→ KEY_RESERVED で reject
- 空 key → KEY_EMPTY で reject
- JSON 契約（status / error_code enum）
- YAML 出力モード（検索 SKILL が AI に渡す用途）

移行元: test_filter_toc.py（filter_toc.py のテスト）。
新 I/F（key + path）へ作り替え、category / doc_type 依存テストは廃止。

テスト方針:
- in-process import（filter_docs_by_paths / build_docs_payload / render_toc_yaml 等）
- subprocess JSON / YAML 契約（CLI の status / error_code / docs）の両方を使う。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from get_toc import (
    filter_docs_by_paths,
    build_docs_payload,
    render_toc_yaml,
    parse_paths_arg,
)
from toc_store import (
    resolve_store_dir,
    DEFAULT_KEY,
    ErrorCode,
    ERROR_CODES,
    STATUSES,
    STATUS_OK,
    STATUS_ERROR,
)

GET_TOC_SCRIPT = os.path.join(SCRIPTS_DIR, 'get_toc.py')


# 新スキーマ（DES-005 §7.1: doc_type 除去）の toc.yaml。
# 定義順は z, a, m とし、出力で sorted されないこと（定義順保持）を観測する。
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


# ===========================================================================
# 共通基盤（subprocess 実行 + 一時 project root + store toc.yaml 書き込み）
# ===========================================================================

class GetTocTestBase(unittest.TestCase):
    """一時 project root と subprocess 実行ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        os.makedirs(self.project_root / '.git', exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _write_toc(self, key, content=SAMPLE_TOC_YAML):
        """store_dir/toc.yaml に ToC を書き出す。"""
        store_dir = self._store_dir(key)
        store_dir.mkdir(parents=True, exist_ok=True)
        toc_path = store_dir / "toc.yaml"
        toc_path.write_text(content, encoding="utf-8")
        return toc_path

    def _run(self, *args):
        cmd = [sys.executable, GET_TOC_SCRIPT] + list(args)
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
# 縮小抽出ロジック（in-process / FR-N05-1）
# ===========================================================================

class TestFilterDocsByPaths(unittest.TestCase):
    """filter_docs_by_paths の抽出・定義順保持・missing 算出。"""

    def _docs(self):
        # 定義順 z, a, m（dict は挿入順保持）
        return {
            "docs/z.md": {"title": "Z"},
            "docs/a.md": {"title": "A"},
            "docs/m.md": {"title": "M"},
        }

    def test_extracts_only_requested(self):
        filtered, missing = filter_docs_by_paths(
            self._docs(), ["docs/a.md"]
        )
        self.assertEqual(list(filtered.keys()), ["docs/a.md"])
        self.assertEqual(missing, [])

    def test_preserves_definition_order_not_request_order(self):
        """抽出は要求順ではなく ToC の定義順を保持する（FR-N05-2）。"""
        # 要求順は a, m, z だが、定義順は z, a, m
        filtered, _ = filter_docs_by_paths(
            self._docs(), ["docs/a.md", "docs/m.md", "docs/z.md"]
        )
        self.assertEqual(list(filtered.keys()), ["docs/z.md", "docs/a.md", "docs/m.md"])

    def test_missing_paths_reported(self):
        filtered, missing = filter_docs_by_paths(
            self._docs(), ["docs/a.md", "docs/nope.md"]
        )
        self.assertEqual(list(filtered.keys()), ["docs/a.md"])
        self.assertEqual(missing, ["docs/nope.md"])

    def test_empty_request_yields_empty(self):
        filtered, missing = filter_docs_by_paths(self._docs(), [])
        self.assertEqual(filtered, {})
        self.assertEqual(missing, [])


class TestParsePathsArg(unittest.TestCase):
    """parse_paths_arg の正規化・重複除去・空処理。"""

    def test_none_returns_none(self):
        self.assertIsNone(parse_paths_arg(None))

    def test_splits_and_trims(self):
        self.assertEqual(
            parse_paths_arg(" docs/a.md , docs/b.md "),
            ["docs/a.md", "docs/b.md"],
        )

    def test_deduplicates_preserving_first_order(self):
        self.assertEqual(
            parse_paths_arg("docs/a.md,docs/a.md,docs/b.md"),
            ["docs/a.md", "docs/b.md"],
        )

    def test_empty_tokens_dropped(self):
        self.assertEqual(parse_paths_arg("  ,  "), [])


# ===========================================================================
# score / rank フィールド非存在の固定（in-process / FR-N05-2）
# ===========================================================================

class TestNoScoreRankFields(unittest.TestCase):
    """build_docs_payload / render_toc_yaml が score / rank を持たないこと。"""

    def _docs(self):
        return {
            "docs/a.md": {
                "title": "A",
                "purpose": "p",
                "content_details": ["d"],
                "applicable_tasks": ["t"],
                "keywords": ["k"],
            },
        }

    def test_json_payload_has_no_score_or_rank(self):
        payload = build_docs_payload(self._docs())
        for entry in payload.values():
            self.assertNotIn("score", entry)
            self.assertNotIn("rank", entry)
            # doc_type も新スキーマでは除去（DES-005 §7.1）
            self.assertNotIn("doc_type", entry)

    def test_json_payload_keeps_allowed_fields(self):
        payload = build_docs_payload(self._docs())
        entry = payload["docs/a.md"]
        self.assertEqual(
            set(entry.keys()),
            {"title", "purpose", "content_details", "applicable_tasks", "keywords"},
        )

    def test_yaml_render_has_no_score_or_rank(self):
        out = render_toc_yaml(
            self._docs(), key="docs", toc_rel="x/toc.yaml", full_count=1
        )
        self.assertNotIn("score", out)
        self.assertNotIn("rank", out)
        self.assertNotIn("doc_type", out)

    def test_build_docs_payload_preserves_definition_order(self):
        docs = {
            "docs/z.md": {"title": "Z"},
            "docs/a.md": {"title": "A"},
            "docs/m.md": {"title": "M"},
        }
        payload = build_docs_payload(docs)
        self.assertEqual(list(payload.keys()), ["docs/z.md", "docs/a.md", "docs/m.md"])


# ===========================================================================
# CLI 統合: 全体取得 / 縮小抽出（JSON）
# ===========================================================================

class TestGetTocCliJson(GetTocTestBase):
    """get_toc.py の JSON 出力 CLI 統合テスト。"""

    def test_full_get_by_key(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertIsNone(data["error_code"])
        self.assertEqual(data["key"], "docs")
        self.assertEqual(data["file_count"], 3)
        self.assertEqual(data["full_count"], 3)
        self.assertEqual(set(data["docs"].keys()), {"docs/z.md", "docs/a.md", "docs/m.md"})

    def test_full_get_preserves_definition_order(self):
        """JSON docs が ToC の定義順（z, a, m）を保持する（FR-N05-2）。"""
        self._write_toc("docs")
        proc = self._run("--key", "docs")
        data = self._parse_json_stdout(proc)
        self.assertEqual(
            list(data["docs"].keys()), ["docs/z.md", "docs/a.md", "docs/m.md"]
        )

    def test_subset_by_paths(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs", "--paths", "docs/a.md,docs/m.md")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["file_count"], 2)
        self.assertEqual(data["full_count"], 3)
        # 定義順保持: m は a より後だが z は除外される → [a, m]
        self.assertEqual(list(data["docs"].keys()), ["docs/a.md", "docs/m.md"])
        self.assertEqual(data["missing_paths"], [])

    def test_subset_reports_missing(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs", "--paths", "docs/a.md,docs/nope.md")
        data = self._parse_json_stdout(proc)
        self.assertEqual(list(data["docs"].keys()), ["docs/a.md"])
        self.assertEqual(data["missing_paths"], ["docs/nope.md"])

    def test_json_docs_have_no_score_rank(self):
        """CLI JSON 出力でも score / rank / doc_type を持たない（FR-N05-2）。"""
        self._write_toc("docs")
        proc = self._run("--key", "docs")
        data = self._parse_json_stdout(proc)
        for entry in data["docs"].values():
            self.assertNotIn("score", entry)
            self.assertNotIn("rank", entry)
            self.assertNotIn("doc_type", entry)


# ===========================================================================
# CLI 統合: YAML 出力
# ===========================================================================

class TestGetTocCliYaml(GetTocTestBase):
    """get_toc.py の YAML 出力 CLI 統合テスト。"""

    def test_yaml_full_preserves_definition_order(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs", "--format", "yaml")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        out = proc.stdout
        z_pos = out.index("docs/z.md")
        a_pos = out.index("docs/a.md")
        m_pos = out.index("docs/m.md")
        # 定義順 z, a, m が保持される（sorted なら a, m, z になる）
        self.assertLess(z_pos, a_pos)
        self.assertLess(a_pos, m_pos)

    def test_yaml_has_no_score_rank_doc_type(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs", "--format", "yaml")
        out = proc.stdout
        self.assertNotIn("score", out)
        self.assertNotIn("rank", out)
        self.assertNotIn("doc_type", out)

    def test_yaml_subset(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs", "--paths", "docs/a.md", "--format", "yaml")
        out = proc.stdout
        self.assertIn("docs/a.md", out)
        self.assertNotIn("docs/z.md", out)
        self.assertNotIn("docs/m.md", out)


# ===========================================================================
# key 解決・エラー（JSON 契約）
# ===========================================================================

class TestGetTocKeyResolution(GetTocTestBase):
    """予約 key all / 任意 all reject / 空 key / TOC_NOT_FOUND。"""

    def test_key_omitted_resolves_to_reserved_all(self):
        """--key 省略時は予約 key 'all' を対象にする（FR-N04-4）。"""
        self._write_toc(DEFAULT_KEY)  # key 'all' のストアに書く
        proc = self._run()  # --key も --all も無し
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_OK)
        self.assertEqual(data["key"], DEFAULT_KEY)
        self.assertEqual(data["file_count"], 3)

    def test_all_flag_resolves_to_reserved_all(self):
        self._write_toc(DEFAULT_KEY)
        proc = self._run("--all")
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["key"], DEFAULT_KEY)

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

    def test_toc_not_found(self):
        """toc.yaml が存在しない場合は TOC_NOT_FOUND。"""
        proc = self._run("--key", "docs")
        self.assertEqual(proc.returncode, 1)
        data = self._parse_json_stdout(proc)
        self.assertEqual(data["status"], STATUS_ERROR)
        self.assertEqual(data["error_code"], ErrorCode.TOC_NOT_FOUND)
        self.assertEqual(data["key"], "docs")


# ===========================================================================
# JSON 契約: status / error_code enum の固定（FR-N08-2）
# ===========================================================================

class TestJsonContractEnums(GetTocTestBase):
    """全経路の status / error_code が enum 集合に収まることを固定する。"""

    def test_status_and_error_code_in_enum_on_success(self):
        self._write_toc("docs")
        proc = self._run("--key", "docs")
        data = self._parse_json_stdout(proc)
        self.assertIn(data["status"], STATUSES)
        self.assertIn(data["error_code"], ERROR_CODES | {None})

    def test_status_and_error_code_in_enum_on_error(self):
        proc = self._run("--key", "docs")  # toc 不在
        data = self._parse_json_stdout(proc)
        self.assertIn(data["status"], STATUSES)
        self.assertIn(data["error_code"], ERROR_CODES | {None})

    def test_reserved_key_error_code_in_enum(self):
        proc = self._run("--key", "all")
        data = self._parse_json_stdout(proc)
        self.assertIn(data["error_code"], ERROR_CODES)


if __name__ == '__main__':
    unittest.main()
