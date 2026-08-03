#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_toc.py のユニットテスト（DES-005 / REQ-001 NFR-N03）。

key + path I/F へ作り替え。category / doc_type 依存テストは廃止。

テスト対象:
- pending 統合で toc.yaml が生成される（§6.1）
- deleted 反映（FR-N02-2。サイドカー由来 / 実体不在 stale 由来）
- backup → validate → restore 異常系（§6.5。validate 失敗時に .bak 復元・
  checksums 据え置き・.toc_work 保持）
- metadata.key が --key 引数と一致する（§7.2）
- 原子的書き込み（os.replace 経路で破損なし）
- JSON 契約（status / error_code enum・counts・deleted_paths）
- AI 抽出結果の書き戻し候補 `ai_extracted_paths`（DES-008 §8.2 / DES-005 §8.2。
  extracted_by: ai のみ集約・toc.yaml には出さない・成功時のみ出力）
- docs 順序の決定性（path 昇順）
- prepare → write_pending → merge の協調フロー（discover 全体は TASK-008）

テスト方針:
- in-process import（render_toc_yaml / run_merge 等）
- subprocess JSON 契約（CLI の status / error_code / counts）
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
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from merge_toc import (
    render_toc_yaml,
    write_toc_atomic,
    load_completed_pendings,
    detect_deleted,
    load_deleted_sidecar,
    compute_checksums_for_docs,
)
from toc_store import (
    resolve_store_dir,
    WORK_DIRNAME,
    CHECKSUMS_FILENAME,
    DELETED_SIDECAR_FILENAME,
    ERROR_CODES,
    STATUSES,
)
from toc_utils import load_existing_toc, load_checksums, calculate_file_hash

MERGE_SCRIPT = os.path.join(SCRIPTS_DIR, 'merge_toc.py')
PREPARE_SCRIPT = os.path.join(SCRIPTS_DIR, 'prepare_toc.py')
WRITE_PENDING_SCRIPT = os.path.join(SCRIPTS_DIR, 'write_pending.py')


# ===========================================================================
# 共通基盤
# ===========================================================================

class MergeTestBase(unittest.TestCase):
    """一時 project root と subprocess / pending 生成ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        os.makedirs(self.project_root / '.git', exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_md(self, rel_path, content='# Title\n\nThis is body content.\n'):
        full = self.project_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
        return full

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _work_dir(self, key):
        return self._store_dir(key) / WORK_DIRNAME

    def _toc_path(self, key):
        return self._store_dir(key) / 'toc.yaml'

    def _write_completed_pending(self, key, source_file, *, title='Test Title',
                                 extracted_by=None):
        """充填済み（status: completed）pending YAML を手動作成する。

        Args:
            key: 対象 key
            source_file: pending の _meta.source_file
            title: entry の title
            extracted_by: _meta.extracted_by の値（None なら行を書かない。
                既存持ち越し等の来歴不明 pending を表す / DES-008 §8.2）
        """
        work_dir = self._work_dir(key)
        work_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        name = hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:16] + '.yaml'
        provenance_line = (
            f"  extracted_by: {extracted_by}\n" if extracted_by is not None else ""
        )
        content = f"""\
_meta:
  source_file: {source_file}
  status: completed
  updated_at: "2026-01-31T00:00:00Z"
{provenance_line}
title: {title}
purpose: Purpose of {title}
content_details:
  - Detail 1
  - Detail 2
  - Detail 3
  - Detail 4
  - Detail 5
applicable_tasks:
  - Task 1
keywords:
  - kw1
  - kw2
  - kw3
  - kw4
  - kw5
"""
        (work_dir / name).write_text(content, encoding='utf-8')
        return work_dir / name

    def _write_pending_status(self, key, source_file, status):
        """任意 status の pending YAML を作成する（completed でないもの等）。"""
        work_dir = self._work_dir(key)
        work_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        name = hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:16] + '.yaml'
        content = f"""\
_meta:
  source_file: {source_file}
  status: {status}
  updated_at: null

title: null
purpose: null
content_details: []
applicable_tasks: []
keywords: []
"""
        (work_dir / name).write_text(content, encoding='utf-8')
        return work_dir / name

    def _write_checksums(self, key, mapping):
        store_dir = self._store_dir(key)
        store_dir.mkdir(parents=True, exist_ok=True)
        lines = ["checksums:"]
        for path, h in mapping.items():
            lines.append(f"  {path}: {h}")
        (store_dir / CHECKSUMS_FILENAME).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _write_sidecar(self, key, deleted):
        work_dir = self._work_dir(key)
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / DELETED_SIDECAR_FILENAME).write_text(
            json.dumps(deleted), encoding="utf-8"
        )

    def _run_merge(self, *args):
        cmd = [sys.executable, MERGE_SCRIPT] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )

    def _run(self, script, *args):
        cmd = [sys.executable, script] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )

    def _parse_stdout(self, proc):
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(
            len(out.split("\n")), 1, f"stdout must be single JSON: {out}"
        )
        return json.loads(out)


# ===========================================================================
# pending 統合（§6.1）
# ===========================================================================

class TestMergePendingIntegration(MergeTestBase):
    def test_merge_creates_toc(self):
        """充填済み pending を統合して toc.yaml を生成する。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md", title="Doc A")
        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertIsNone(obj["error_code"])
        self.assertEqual(obj["counts"]["added"], 1)
        # toc.yaml が生成されている
        toc = self._toc_path("rules")
        self.assertTrue(toc.exists())
        content = toc.read_text(encoding='utf-8')
        self.assertIn("docs:", content)
        self.assertIn("docs/a.md", content)
        self.assertIn("Doc A", content)

    def test_merge_no_doc_type_field(self):
        """toc.yaml に doc_type フィールドが出力されない（§7.1）。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._run_merge('--key', 'rules')
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("doc_type", content)

    def test_merge_incremental_keeps_existing(self):
        """2 回目の merge で既存エントリを保持しつつ追加する。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md", title="Doc A")
        self._run_merge('--key', 'rules')

        # 既存 a の hash を checksums に持つ状態で b を追加
        self._write_md("docs/b.md")
        self._write_completed_pending("rules", "docs/b.md", title="Doc B")
        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertIn("docs/a.md", content)
        self.assertIn("docs/b.md", content)

    def test_non_completed_pending_skipped(self):
        """status が completed でない pending は統合されない。"""
        self._write_md("docs/a.md")
        self._write_pending_status("rules", "docs/a.md", "pending")
        proc = self._run_merge('--key', 'rules')
        # pending が未完了 → 統合対象なし、既存 toc も無い → NO_TARGETS ではなく
        # work dir はあるので merge は走るが docs 空。空 toc を冪等出力。
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["counts"]["added"], 0)


# ===========================================================================
# metadata.key 転記（§7.2）
# ===========================================================================

class TestMetadataKey(MergeTestBase):
    def test_metadata_key_set_from_arg(self):
        """toc.yaml の metadata.key が --key 引数と一致する。"""
        key = "my rules"
        self._write_md("docs/a.md")
        self._write_completed_pending(key, "docs/a.md")
        proc = self._run_merge('--key', key)
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")

        content = self._toc_path(key).read_text(encoding='utf-8')
        self.assertIn(f'key: {self._yaml_key(key)}', content)

    def _yaml_key(self, key):
        from toc_utils import yaml_escape
        return yaml_escape(key)


# ===========================================================================
# deleted 反映（FR-N02-2）
# ===========================================================================

class TestDeletedReflection(MergeTestBase):
    def test_deleted_via_sidecar(self):
        """サイドカー由来の deleted が toc.yaml から除去される（部分配列 → 残り削除）。"""
        # 既存 toc に a と c が入っている状態を作る
        self._write_md("docs/a.md")
        self._write_md("docs/c.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._write_completed_pending("rules", "docs/c.md")
        self._run_merge('--key', 'rules')
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertIn("docs/c.md", content)

        # 今回 desired は a のみ → prepare が c を deleted サイドカーへ。
        # c.md は実在するが desired から外れる。
        self._write_completed_pending("rules", "docs/a.md", title="Doc A v2")
        self._write_sidecar("rules", ["docs/c.md"])
        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["deleted"], 1)
        self.assertIn("docs/c.md", obj["deleted_paths"])
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("docs/c.md", content)
        self.assertIn("docs/a.md", content)

    def test_deleted_via_missing_file(self):
        """実ファイル不在の stale エントリが除去される。"""
        self._write_md("docs/a.md")
        self._write_md("docs/gone.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._write_completed_pending("rules", "docs/gone.md")
        self._run_merge('--key', 'rules')
        # gone.md を削除し、checksums に残す
        h = calculate_file_hash(self.project_root / "docs/gone.md")
        os.remove(self.project_root / "docs/gone.md")

        # 新しい merge: pending は a のみ更新、gone は checksums に残るが不在
        self._write_completed_pending("rules", "docs/a.md", title="Doc A v2")
        # checksums に gone を確実に含める（前回 merge が書いたはず）
        cks = load_checksums(self._store_dir("rules") / CHECKSUMS_FILENAME)
        self.assertIn("docs/gone.md", cks)

        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertIn("docs/gone.md", obj["deleted_paths"])
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("docs/gone.md", content)

    def test_delete_only_mode(self):
        """--delete-only で実体不在の stale を除去する（pending を統合しない）。"""
        self._write_md("docs/a.md")
        self._write_md("docs/b.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._write_completed_pending("rules", "docs/b.md")
        self._run_merge('--key', 'rules')

        # b.md を削除
        os.remove(self.project_root / "docs/b.md")
        proc = self._run_merge('--key', 'rules', '--delete-only')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertIn("docs/b.md", obj["deleted_paths"])
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("docs/b.md", content)
        self.assertIn("docs/a.md", content)

    def test_delete_only_no_toc_fails(self):
        """toc.yaml が無い状態の --delete-only は TOC_NOT_FOUND。"""
        proc = self._run_merge('--key', 'rules', '--delete-only')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertEqual(obj["error_code"], "TOC_NOT_FOUND")


# ===========================================================================
# backup → validate → restore 異常系（§6.5、最重要）
# ===========================================================================

class TestBackupRestore(MergeTestBase):
    def _make_invalid_pending(self, key, source_file):
        """validate を失敗させる pending（必須配列が空）を作る。"""
        work_dir = self._work_dir(key)
        work_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        name = hashlib.sha256(source_file.encode('utf-8')).hexdigest()[:16] + '.yaml'
        # title/purpose はあるが配列が空 → validate_toc が必須配列不正で失敗
        content = f"""\
_meta:
  source_file: {source_file}
  status: completed
  updated_at: "2026-01-31T00:00:00Z"

title: Bad Entry
purpose: Bad purpose
content_details: []
applicable_tasks: []
keywords: []
"""
        (work_dir / name).write_text(content, encoding='utf-8')
        return work_dir / name

    def test_validation_failure_restores_backup(self):
        """validate 失敗時に .bak から復元され元の toc.yaml が保たれる。"""
        # まず有効な toc.yaml を作る
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md", title="Good A")
        self._run_merge('--key', 'rules')
        good_content = self._toc_path("rules").read_text(encoding='utf-8')
        good_checksums = load_checksums(self._store_dir("rules") / CHECKSUMS_FILENAME)

        # 次に無効な pending（空配列）で merge → validate 失敗
        self._write_md("docs/b.md")
        self._make_invalid_pending("rules", "docs/b.md")
        proc = self._run_merge('--key', 'rules')
        self.assertNotEqual(proc.returncode, 0, "validation failure should exit non-zero")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertEqual(obj["error_code"], "INVALID_PATH")

        # toc.yaml は元（good）に復元されている
        restored = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertEqual(restored, good_content)

    def test_validation_failure_keeps_checksums(self):
        """validate 失敗時に checksums が据え置かれる。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md", title="Good A")
        self._run_merge('--key', 'rules')
        good_checksums = load_checksums(self._store_dir("rules") / CHECKSUMS_FILENAME)

        self._write_md("docs/b.md")
        self._make_invalid_pending("rules", "docs/b.md")
        self._run_merge('--key', 'rules')

        after = load_checksums(self._store_dir("rules") / CHECKSUMS_FILENAME)
        self.assertEqual(after, good_checksums)
        # b.md は checksums に入っていない（更新されていない）
        self.assertNotIn("docs/b.md", after)

    def test_validation_failure_preserves_work_dir(self):
        """validate 失敗時に .toc_work が保持され再実行可能。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md", title="Good A")
        self._run_merge('--key', 'rules')

        self._write_md("docs/b.md")
        self._make_invalid_pending("rules", "docs/b.md")
        self._run_merge('--key', 'rules')

        # work dir が残っている
        work_dir = self._work_dir("rules")
        self.assertTrue(work_dir.exists())
        yamls = [f for f in os.listdir(work_dir)
                 if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yamls), 1)

    def test_validation_failure_new_toc_removed(self):
        """新規生成（backup なし）で validate 失敗時、無効 toc.yaml は除去され不在へ戻る。"""
        self._write_md("docs/b.md")
        self._make_invalid_pending("rules", "docs/b.md")
        proc = self._run_merge('--key', 'rules')
        self.assertNotEqual(proc.returncode, 0)
        # 新規生成だったので toc.yaml は不在に戻る
        self.assertFalse(self._toc_path("rules").exists())


# ===========================================================================
# 成功時の cleanup（§6.5）
# ===========================================================================

class TestSuccessCleanup(MergeTestBase):
    def test_work_dir_removed_on_success(self):
        """merge 成功時に .toc_work が削除される。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._run_merge('--key', 'rules')
        self.assertFalse(self._work_dir("rules").exists())

    def test_checksums_updated_on_success(self):
        """merge 成功時に checksums が最終 docs から更新される。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._run_merge('--key', 'rules')
        cks = load_checksums(self._store_dir("rules") / CHECKSUMS_FILENAME)
        expected = calculate_file_hash(self.project_root / "docs/a.md")
        self.assertEqual(cks.get("docs/a.md"), expected)

    def test_backup_removed_on_success(self):
        """成功後に .bak が残らない。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md")
        self._run_merge('--key', 'rules')
        # 2 回目（backup が作られる経路）
        self._write_completed_pending("rules", "docs/a.md", title="A v2")
        self._run_merge('--key', 'rules')
        bak = self._toc_path("rules").with_name("toc.yaml.bak")
        self.assertFalse(bak.exists())


# ===========================================================================
# docs 順序の決定性 / 原子的書き込み
# ===========================================================================

class TestDocsOrderingAndAtomic(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_docs_sorted_by_path(self):
        """docs が path 昇順で出力される（決定的順序 / FR-N05-2 整合）。"""
        docs = {
            "docs/zeta.md": {"title": "Z", "purpose": "z",
                             "content_details": ["x"], "applicable_tasks": ["t"],
                             "keywords": ["k"]},
            "docs/alpha.md": {"title": "A", "purpose": "a",
                              "content_details": ["x"], "applicable_tasks": ["t"],
                              "keywords": ["k"]},
            "docs/mid.md": {"title": "M", "purpose": "m",
                            "content_details": ["x"], "applicable_tasks": ["t"],
                            "keywords": ["k"]},
        }
        body = render_toc_yaml(docs, key="rules", toc_rel="x/toc.yaml")
        i_alpha = body.index("docs/alpha.md")
        i_mid = body.index("docs/mid.md")
        i_zeta = body.index("docs/zeta.md")
        self.assertLess(i_alpha, i_mid)
        self.assertLess(i_mid, i_zeta)

    def test_metadata_has_key(self):
        """metadata に key が含まれる（§7.2）。"""
        docs = {"docs/a.md": {"title": "A", "purpose": "a",
                              "content_details": ["x"], "applicable_tasks": ["t"],
                              "keywords": ["k"]}}
        body = render_toc_yaml(docs, key="mykey", toc_rel="x/toc.yaml")
        self.assertIn("key: mykey", body)
        self.assertIn("file_count: 1", body)

    def test_atomic_write_creates_file(self):
        """write_toc_atomic が os.replace 経由でファイルを生成する。"""
        out = self.project_root / "sub" / "toc.yaml"
        docs = {"docs/a.md": {"title": "A", "purpose": "a",
                              "content_details": ["x"], "applicable_tasks": ["t"],
                              "keywords": ["k"]}}
        ok = write_toc_atomic(docs, out, key="rules", toc_rel="sub/toc.yaml")
        self.assertTrue(ok)
        self.assertTrue(out.exists())
        # 一時ファイルが残っていない
        leftovers = [f for f in os.listdir(out.parent) if f.startswith('.toc_')]
        self.assertEqual(leftovers, [])


# ===========================================================================
# in-process ヘルパ単体
# ===========================================================================

class TestHelpers(MergeTestBase):
    def test_load_completed_pendings(self):
        self._write_completed_pending("rules", "docs/a.md", title="A")
        self._write_pending_status("rules", "docs/b.md", "pending")
        entries, provenance, errors = load_completed_pendings(self._work_dir("rules"))
        self.assertIn("docs/a.md", entries)
        self.assertNotIn("docs/b.md", entries)
        self.assertTrue(any("docs/b.md" in e or "b.md" in e or "not completed" in e
                            for e in errors) or len(errors) >= 1)
        # provenance は completed な pending のみ。extracted_by 無しは None（DES-008 §8.2）
        self.assertEqual(set(provenance.keys()), {"docs/a.md"})
        self.assertIsNone(provenance["docs/a.md"])

    def test_load_completed_pendings_provenance(self):
        """_meta.extracted_by が provenance として返る（entries の意味は不変）。"""
        self._write_completed_pending(
            "rules", "docs/ai.md", title="AI", extracted_by="ai"
        )
        self._write_completed_pending(
            "rules", "docs/fm.md", title="FM", extracted_by="frontmatter"
        )
        entries, provenance, _ = load_completed_pendings(self._work_dir("rules"))
        self.assertEqual(set(entries.keys()), {"docs/ai.md", "docs/fm.md"})
        self.assertEqual(provenance["docs/ai.md"], "ai")
        self.assertEqual(provenance["docs/fm.md"], "frontmatter")

    def test_load_completed_pendings_missing_work_dir(self):
        entries, provenance, errors = load_completed_pendings(self._work_dir("rules"))
        self.assertEqual(entries, {})
        self.assertEqual(provenance, {})
        self.assertEqual(errors, [])

    def test_load_deleted_sidecar(self):
        self._write_sidecar("rules", ["docs/x.md", "docs/y.md"])
        deleted = load_deleted_sidecar(self._work_dir("rules"))
        self.assertEqual(set(deleted), {"docs/x.md", "docs/y.md"})

    def test_load_deleted_sidecar_missing(self):
        deleted = load_deleted_sidecar(self._work_dir("rules"))
        self.assertEqual(deleted, [])

    def test_detect_deleted_combines_sources(self):
        self._write_md("docs/keep.md")
        docs = {"docs/keep.md": {}, "docs/stale.md": {}}
        prev = {"docs/keep.md": "h", "docs/sidecar.md": "h"}
        deleted = detect_deleted(
            docs, prev, ["docs/sidecar.md"], self.project_root
        )
        # stale（実体不在）と sidecar の両方が deleted
        self.assertIn("docs/stale.md", deleted)
        self.assertIn("docs/sidecar.md", deleted)
        self.assertNotIn("docs/keep.md", deleted)


# ===========================================================================
# AI 抽出結果の書き戻し候補の集約（DES-008 §8.2 / DES-005 §8.2）
# ===========================================================================

class TestAiExtractedPaths(MergeTestBase):
    """merge の JSON が ai_extracted_paths を出す（toc.yaml には出さない）。"""

    def test_only_ai_extracted_paths_listed(self):
        """extracted_by: ai の source_file のみが並ぶ（転記由来は含まれない）。"""
        self._write_md("docs/ai1.md")
        self._write_md("docs/ai2.md")
        self._write_md("docs/fm.md")
        self._write_completed_pending("rules", "docs/ai2.md", extracted_by="ai")
        self._write_completed_pending("rules", "docs/ai1.md", extracted_by="ai")
        self._write_completed_pending("rules", "docs/fm.md", extracted_by="frontmatter")

        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        # 昇順で決定的に並ぶ
        self.assertEqual(obj["ai_extracted_paths"], ["docs/ai1.md", "docs/ai2.md"])
        self.assertNotIn("docs/fm.md", obj["ai_extracted_paths"])

    def test_pending_without_extracted_by_excluded(self):
        """extracted_by を持たない pending は候補に含めない（決定論的）。"""
        self._write_md("docs/legacy.md")
        self._write_md("docs/ai.md")
        self._write_completed_pending("rules", "docs/legacy.md")  # extracted_by なし
        self._write_completed_pending("rules", "docs/ai.md", extracted_by="ai")

        obj = self._parse_stdout(self._run_merge('--key', 'rules'))
        self.assertEqual(obj["ai_extracted_paths"], ["docs/ai.md"])

    def test_no_ai_extraction_yields_empty_array(self):
        """AI 抽出が 1 件も無ければ空配列（フィールド自体は出る）。"""
        self._write_md("docs/fm.md")
        self._write_completed_pending("rules", "docs/fm.md", extracted_by="frontmatter")
        obj = self._parse_stdout(self._run_merge('--key', 'rules'))
        self.assertEqual(obj["ai_extracted_paths"], [])

    def test_delete_only_yields_empty_array(self):
        """--delete-only は pending を統合しないため常に空配列。"""
        self._write_md("docs/a.md")
        self._write_md("docs/b.md")
        self._write_completed_pending("rules", "docs/a.md", extracted_by="ai")
        self._write_completed_pending("rules", "docs/b.md", extracted_by="ai")
        self._run_merge('--key', 'rules')

        os.remove(self.project_root / "docs/b.md")
        obj = self._parse_stdout(self._run_merge('--key', 'rules', '--delete-only'))
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["ai_extracted_paths"], [])

    def test_toc_yaml_has_no_provenance_fields(self):
        """toc.yaml に ai_extracted_paths も extracted_by も出ない（DES-008 §4.3）。"""
        self._write_md("docs/ai.md")
        self._write_completed_pending("rules", "docs/ai.md", extracted_by="ai")
        self._run_merge('--key', 'rules')

        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("ai_extracted_paths", content)
        self.assertNotIn("extracted_by", content)

    def test_validation_failure_omits_aggregation(self):
        """validation 失敗（ToC 未完成）では候補を出さない。"""
        self._write_md("docs/bad.md")
        work_dir = self._work_dir("rules")
        work_dir.mkdir(parents=True, exist_ok=True)
        import hashlib
        name = hashlib.sha256(b"docs/bad.md").hexdigest()[:16] + '.yaml'
        (work_dir / name).write_text(
            """\
_meta:
  source_file: docs/bad.md
  status: completed
  updated_at: "2026-01-31T00:00:00Z"
  extracted_by: ai

title: Bad Entry
purpose: Bad purpose
content_details: []
applicable_tasks: []
keywords: []
""",
            encoding='utf-8',
        )

        proc = self._run_merge('--key', 'rules')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertNotIn(
            "ai_extracted_paths", obj,
            "ToC 生成が完了していない経路では書き戻し候補を提示しない",
        )


# ===========================================================================
# JSON 契約（status / error_code enum）
# ===========================================================================

class TestJsonContract(MergeTestBase):
    def test_status_and_error_code_enum(self):
        """status / error_code が enum に含まれる。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("rules", "docs/a.md")
        proc = self._run_merge('--key', 'rules')
        obj = self._parse_stdout(proc)
        self.assertIn(obj["status"], STATUSES)
        self.assertTrue(obj["error_code"] is None or obj["error_code"] in ERROR_CODES)

    def test_explicit_all_rejected(self):
        """--key all は KEY_RESERVED で reject。"""
        proc = self._run_merge('--key', 'all')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "KEY_RESERVED")

    def test_empty_key_rejected(self):
        """空 key は KEY_EMPTY で reject。"""
        proc = self._run_merge('--key', '')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "KEY_EMPTY")

    def test_no_targets_when_nothing(self):
        """pending も既存 toc も無い場合 NO_TARGETS。"""
        proc = self._run_merge('--key', 'rules')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "NO_TARGETS")

    def test_key_omitted_resolves_all(self):
        """--key 省略で予約 key all に解決する。"""
        self._write_md("docs/a.md")
        self._write_completed_pending("all", "docs/a.md")
        proc = self._run_merge()
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["key"], "all")


# ===========================================================================
# prepare → write_pending → merge 協調フロー（§13 統合）
# ===========================================================================

class TestCoordinationFlow(MergeTestBase):
    def test_prepare_write_pending_merge(self):
        """prepare → write_pending → merge で toc.yaml が生成される。"""
        self._write_md("docs/guide.md", content='# Guide\n\nGuide body content here.\n')

        # 1. prepare（key 指定、明示 paths）
        proc = self._run(
            PREPARE_SCRIPT, '--key', 'rules', '--paths-json', '["docs/guide.md"]'
        )
        self.assertEqual(proc.returncode, 0, f"prepare stderr: {proc.stderr}")
        prep = self._parse_stdout(proc)
        self.assertEqual(prep["counts"]["added"], 1)

        # 2. 生成された pending YAML を取得
        work_dir = self._work_dir("rules")
        yamls = [f for f in os.listdir(work_dir)
                 if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yamls), 1)
        entry_rel = os.path.relpath(
            str(work_dir / yamls[0]), str(self.project_root)
        )

        # 3. write_pending で充填（agent 役）
        proc = self._run(
            WRITE_PENDING_SCRIPT, '--key', 'rules',
            '--entry-file', entry_rel,
            '--title', 'Guide',
            '--purpose', 'Guide purpose',
            '--content-details', 'a ||| b ||| c ||| d ||| e',
            '--applicable-tasks', 'task1',
            '--keywords', 'k1 ||| k2 ||| k3 ||| k4 ||| k5',
        )
        self.assertEqual(proc.returncode, 0, f"write_pending stderr: {proc.stderr}")

        # 4. merge
        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"merge stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["counts"]["added"], 1)

        # 5. toc.yaml の内容確認
        docs = load_existing_toc(self._toc_path("rules"))
        self.assertIn("docs/guide.md", docs)
        self.assertEqual(docs["docs/guide.md"]["title"], "Guide")

    def test_prepare_deletes_via_sidecar_then_merge(self):
        """prepare が部分配列で deleted サイドカーを残し、merge が反映する。"""
        self._write_md("docs/a.md", content='# A\n\nbody a.\n')
        self._write_md("docs/b.md", content='# B\n\nbody b.\n')

        # 1. a, b 両方を prepare + 充填 + merge して toc に入れる
        for name in ("docs/a.md", "docs/b.md"):
            self._write_completed_pending("rules", name, title=name)
        self._run_merge('--key', 'rules')
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertIn("docs/b.md", content)

        # 2. desired を a のみにして prepare（b はファイル存在のまま desired から外す）
        proc = self._run(
            PREPARE_SCRIPT, '--key', 'rules', '--paths-json', '["docs/a.md"]'
        )
        self.assertEqual(proc.returncode, 0, f"prepare stderr: {proc.stderr}")
        prep = self._parse_stdout(proc)
        self.assertEqual(prep["counts"]["deleted"], 1)

        # 3. merge（a は unchanged で pending なし、b は sidecar で削除）
        proc = self._run_merge('--key', 'rules')
        self.assertEqual(proc.returncode, 0, f"merge stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertIn("docs/b.md", obj["deleted_paths"])
        content = self._toc_path("rules").read_text(encoding='utf-8')
        self.assertNotIn("docs/b.md", content)
        self.assertIn("docs/a.md", content)


class TestComputeChecksumsCarryForward(unittest.TestCase):
    """compute_checksums_for_docs: completed のみ現内容、持ち越しは前回値引き継ぎ（Issue #22）。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel, content):
        p = self.root / rel
        p.write_text(content, encoding="utf-8")
        return calculate_file_hash(p)

    def test_completed_uses_current_hash(self):
        cur = self._write("docs/a.md", "new content")
        docs = {"docs/a.md": {"title": "A"}}
        cs = compute_checksums_for_docs(
            docs, self.root, completed_paths={"docs/a.md"}, prev_checksums={"docs/a.md": "OLD"}
        )
        self.assertEqual(cs["docs/a.md"], cur)  # 充填済み→現内容

    def test_carried_over_keeps_prev_not_current(self):
        # 改訂されたが充填失敗（completed でない）→ 現内容ではなく前回(旧)値を残す。
        self._write("docs/a.md", "MODIFIED content")
        docs = {"docs/a.md": {"title": "A(old)"}}
        cs = compute_checksums_for_docs(
            docs, self.root, completed_paths=set(), prev_checksums={"docs/a.md": "OLDHASH"}
        )
        # 現内容ハッシュ（MODIFIED）を詐称せず、旧値を残す → 次回 prepare が「変更あり」と検知
        self.assertEqual(cs["docs/a.md"], "OLDHASH")

    def test_carried_over_without_prev_falls_back_to_current(self):
        cur = self._write("docs/a.md", "x")
        docs = {"docs/a.md": {"title": "A"}}
        cs = compute_checksums_for_docs(
            docs, self.root, completed_paths=set(), prev_checksums={}
        )
        self.assertEqual(cs["docs/a.md"], cur)

    def test_legacy_none_completed_all_current(self):
        # 旧 API 互換: completed_paths=None なら全件現内容（後方互換）。
        cur = self._write("docs/a.md", "y")
        docs = {"docs/a.md": {"title": "A"}}
        cs = compute_checksums_for_docs(docs, self.root)
        self.assertEqual(cs["docs/a.md"], cur)


if __name__ == '__main__':
    unittest.main()
