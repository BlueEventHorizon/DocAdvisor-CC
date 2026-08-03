#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
script 層 統合テスト（key + path I/F / DES-005 §13 統合テスト対象）。

検証する協調フロー（FR-N07-3 / DES-005 §6.1）:
    prepare_toc.py --key K --paths-json [...]
        → .toc_work/ の pending を write_pending.py --key K で充填（status: completed）
        → merge_toc.py --key K
        → store_dir/toc.yaml が docs 付きで生成され validate_toc が valid、
          metadata.key が original key と一致する

加えて以下を固定する:
- remove_toc.py --key K で store_dir が削除される（FR-N06-1）
- 単体モード（--all）prepare → 充填 → merge で toc.yaml 生成（FR-N04）
- FR-N07-1: prepare/merge/get/remove の各 script が単体でメタデータ抽出をしない
  （prepare 直後の pending は status: pending でメタデータ未充填。充填は
  write_pending 経路のみ。merge は充填済み pending のみ統合）
- FR-N08-2: 全 script の stdout が単一 JSON で status / error_code が enum に収まる
- REQ-006 制約: prepare → fm_to_pending → write_pending → merge を流した前後で
  原本の文書がバイト単位で不変（索引の生成は原本を書き換えない）。あわせて merge の
  `ai_extracted_paths` に AI 抽出経路の文書のみが並ぶこと（DES-008 §8.2）
- 戦略書 R9: `body_hash` の打刻でファイル全体ハッシュが変わり `updated` となった文書が、
  転記 → merge を経て次回 prepare で `unchanged` に収束すること（DES-008 §7.2）

各 script は subprocess 経由で呼び、stdout の単一 JSON 契約（FR-N08-1）も同時に検証する。
標準ライブラリのみ使用（NFR-N01）。
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
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import MARKER, compute_body_hash
from toc_store import (
    resolve_store_dir,
    CHECKSUMS_FILENAME,
    WORK_DIRNAME,
    STATUSES,
    ERROR_CODES,
)
from toc_utils import (
    calculate_file_hash,
    load_checksums,
    load_existing_toc,
    parse_simple_yaml,
)

PREPARE_SCRIPT = os.path.join(SCRIPTS_DIR, 'prepare_toc.py')
MERGE_SCRIPT = os.path.join(SCRIPTS_DIR, 'merge_toc.py')
WRITE_PENDING_SCRIPT = os.path.join(SCRIPTS_DIR, 'write_pending.py')
GET_SCRIPT = os.path.join(SCRIPTS_DIR, 'get_toc.py')
REMOVE_SCRIPT = os.path.join(SCRIPTS_DIR, 'remove_toc.py')
VALIDATE_SCRIPT = os.path.join(SCRIPTS_DIR, 'validate_toc.py')
FM_TO_PENDING_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_to_pending.py')
FM_WRITE_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_write.py')

# write_pending の最小充填件数を満たすサンプルメタデータ
SAMPLE_TITLE = "Coding Standards"
SAMPLE_PURPOSE = "Defines the coding rules used across the project."
SAMPLE_CONTENT = " ||| ".join(f"detail-{i}" for i in range(1, 6))      # 5 items
SAMPLE_TASKS = " ||| ".join(f"task-{i}" for i in range(1, 3))          # 2 items
SAMPLE_KEYWORDS = " ||| ".join(f"keyword-{i}" for i in range(1, 6))    # 5 items

# 信頼判定（DES-008 §5.1）が真になるフロントマターの内容
TRUSTED_BODY = "# Trusted\n\nBody of a document that carries its own metadata.\n"
TRUSTED_METADATA = {
    'title': 'Trusted Document',
    'purpose': 'Carries doc-advisor metadata in its own frontmatter.',
    'content_details': ['detail A', 'detail B'],
    'applicable_tasks': ['task A'],
    'keywords': ['Trusted', 'frontmatter'],
}


def trusted_document(body=TRUSTED_BODY):
    """信頼できる doc-advisor フロントマターを持つ文書を組み立てる。

    Args:
        body: 本文（body_hash はこの本文から算出する）

    Returns:
        str: 文書全体
    """
    lines = ["---", f"type: {MARKER}"]
    for key, value in TRUSTED_METADATA.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f'  - "{item}"')
        else:
            lines.append(f'{key}: "{value}"')
    lines.append(f"body_hash: {compute_body_hash(body)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


class PipelineTestBase(unittest.TestCase):
    """一時 project root と subprocess 実行ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        # .git で project root を明確化（get_project_root は CLAUDE_PROJECT_DIR を使うが防御的に）
        os.makedirs(self.project_root / '.git', exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_md(self, rel_path, content='# Title\n\nThis is body content.\n'):
        """project root 配下に Markdown を作成する。"""
        full = self.project_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
        return full

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _run(self, script, *args):
        cmd = [sys.executable, script] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )

    def _parse_json(self, proc):
        """stdout が単一 JSON であることを検証して dict を返す（FR-N08-1）。"""
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(
            len(out.split("\n")), 1,
            f"stdout must be single JSON line: {out!r}",
        )
        payload = json.loads(out)
        # FR-N08-2: status / error_code が enum に収まる
        self.assertIn("status", payload)
        self.assertIn("error_code", payload)
        self.assertIn(payload["status"], STATUSES)
        self.assertTrue(
            payload["error_code"] is None or payload["error_code"] in ERROR_CODES,
            f"error_code not in enum: {payload['error_code']}",
        )
        return payload

    def _pending_files(self, key):
        """store_dir/.toc_work/ の pending YAML（隠しファイル除く）を返す。"""
        work_dir = self._store_dir(key) / WORK_DIRNAME
        if not work_dir.exists():
            return []
        return sorted(
            f for f in work_dir.glob("*.yaml") if not f.name.startswith(".")
        )

    def _key_args(self, key):
        """key を CLI 引数へ変換する。予約 key 'all' は単体モード入口（--all）を使う。

        'all' はユーザー任意 key としては reject されるため（FR-N01-5）、
        単体モードでは --all を渡す必要がある（FR-N04-4）。
        """
        return ["--all"] if key == "all" else ["--key", key]

    def _fill_pending(self, key, entry_file, *, title=SAMPLE_TITLE):
        """write_pending.py で pending を充填する（AI 層の役割を代替）。"""
        proc = self._run(
            WRITE_PENDING_SCRIPT,
            *self._key_args(key),
            "--entry-file", str(entry_file),
            "--title", title,
            "--purpose", SAMPLE_PURPOSE,
            "--content-details", SAMPLE_CONTENT,
            "--applicable-tasks", SAMPLE_TASKS,
            "--keywords", SAMPLE_KEYWORDS,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"write_pending failed: stdout={proc.stdout} stderr={proc.stderr}",
        )
        return proc


# ===========================================================================
# 協調フロー: prepare → write_pending → merge（DES-005 §6.1 / §13）
# ===========================================================================

class TestPrepareFillMergePipeline(PipelineTestBase):
    """prepare → 充填 → merge で toc.yaml が docs 付きで生成される。"""

    def test_full_pipeline_generates_valid_toc(self):
        key = "rules"
        self._write_md(
            "docs/coding_standards.md",
            "# Coding Standards\n\nUse 4 spaces for indentation.\n",
        )

        # 1. prepare（差分検出 + pending 生成）
        prep = self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/coding_standards.md"]),
        )
        prep_json = self._parse_json(prep)
        self.assertEqual(prep_json["status"], "ok")
        self.assertEqual(prep_json["counts"]["added"], 1)
        self.assertEqual(prep_json["key"], key)

        # pending が 1 件生成されている
        pendings = self._pending_files(key)
        self.assertEqual(len(pendings), 1)

        # 2. メタデータ充填（AI 層の役割を write_pending で代替）
        self._fill_pending(key, pendings[0])

        # 3. merge（統合 → toc.yaml 書き出し + 内部 validate）
        merge = self._run(MERGE_SCRIPT, "--key", key)
        merge_json = self._parse_json(merge)
        self.assertEqual(
            merge_json["status"], "ok",
            f"merge not ok: {merge_json}",
        )
        self.assertEqual(merge_json["counts"]["added"], 1)

        # 4. toc.yaml が docs 付きで生成されている
        toc_path = self._store_dir(key) / "toc.yaml"
        self.assertTrue(toc_path.exists(), "toc.yaml not generated")
        docs = load_existing_toc(toc_path)
        self.assertIn("docs/coding_standards.md", docs)
        entry = docs["docs/coding_standards.md"]
        self.assertEqual(entry["title"], SAMPLE_TITLE)
        self.assertEqual(entry["purpose"], SAMPLE_PURPOSE)
        self.assertEqual(len(entry["keywords"]), 5)

        # 5. metadata.key が original key と一致する（§7.2）
        toc_text = toc_path.read_text(encoding="utf-8")
        self.assertIn(f"  key: {key}", toc_text.split("\n"))

        # 6. validate_toc が valid（merge 内部検証と独立に再確認）
        val = self._run(VALIDATE_SCRIPT, "--key", key)
        self.assertEqual(
            val.returncode, 0,
            f"validate_toc failed: stdout={val.stdout} stderr={val.stderr}",
        )

        # 7. get_toc が定義順を保持し score/rank を持たない（FR-N05-2）
        get = self._run(GET_SCRIPT, "--key", key)
        get_json = self._parse_json(get)
        self.assertEqual(get_json["status"], "ok")
        self.assertNotIn("score", json.dumps(get_json))
        self.assertNotIn("rank", json.dumps(get_json))

    def test_partial_array_deletes_remainder_through_pipeline(self):
        """部分配列を渡すと前回 ToC の残りが削除される（desired-state 破壊性 / §6.3）。"""
        key = "rules"
        self._write_md("docs/a.md", "# A\n\nbody a\n")
        self._write_md("docs/b.md", "# B\n\nbody b\n")

        # 1 回目: a.md + b.md を索引
        self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/a.md", "docs/b.md"]),
        )
        for pending in self._pending_files(key):
            self._fill_pending(key, pending)
        self._run(MERGE_SCRIPT, "--key", key)

        toc_path = self._store_dir(key) / "toc.yaml"
        docs = load_existing_toc(toc_path)
        self.assertEqual(set(docs.keys()), {"docs/a.md", "docs/b.md"})

        # 2 回目: a.md のみ（b.md は desired から外れる → 削除されるべき）
        prep2 = self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/a.md"]),
        )
        prep2_json = self._parse_json(prep2)
        self.assertEqual(prep2_json["counts"]["deleted"], 1)

        merge2 = self._run(MERGE_SCRIPT, "--key", key)
        merge2_json = self._parse_json(merge2)
        self.assertEqual(merge2_json["counts"]["deleted"], 1)

        docs2 = load_existing_toc(toc_path)
        self.assertEqual(set(docs2.keys()), {"docs/a.md"})
        self.assertNotIn("docs/b.md", docs2)


# ===========================================================================
# 単体モード（--all）の協調フロー（FR-N04 / DES-005 §9.3）
# ===========================================================================

class TestSingleModePipeline(PipelineTestBase):
    """--all 単体モードで prepare → 充填 → merge → toc.yaml 生成。"""

    def test_all_mode_pipeline(self):
        self._write_md("README.md", "# Readme\n\nproject readme body\n")
        self._write_md("docs/guide.md", "# Guide\n\nguide body\n")

        prep = self._run(PREPARE_SCRIPT, "--all")
        prep_json = self._parse_json(prep)
        self.assertEqual(prep_json["status"], "ok")
        self.assertEqual(prep_json["key"], "all")
        self.assertEqual(prep_json["counts"]["added"], 2)

        for pending in self._pending_files("all"):
            self._fill_pending("all", pending)

        merge = self._run(MERGE_SCRIPT, "--all")
        merge_json = self._parse_json(merge)
        self.assertEqual(merge_json["status"], "ok")

        toc_path = self._store_dir("all") / "toc.yaml"
        docs = load_existing_toc(toc_path)
        self.assertEqual(set(docs.keys()), {"README.md", "docs/guide.md"})


# ===========================================================================
# 空 repo / 対象 0 件の冪等空出力（DES-005 §9.2 / §9.3 / REQ-001 NFR-N05 / 受け入れ基準）
# ===========================================================================

class TestEmptyRepoPipeline(PipelineTestBase):
    """空 repo（対象 0 件）で prepare → merge → get が error にならず空 ToC を冪等出力する。

    REQ-001 受け入れ基準「空 repo で空 ToC を冪等出力する（error にしない）」/
    DES-005 §9.2「status: ok, file_count: 0」を固定する。
    """

    def test_all_mode_empty_repo_emits_empty_toc(self):
        """--all で Markdown が 1 件も無い場合、全段 status ok / exit 0 で空 toc.yaml を生成。"""
        # setUp は .git のみ作成済み（Markdown なし）

        # 1. prepare --all: 対象 0 件でも status ok / counts 全 0
        prep = self._run(PREPARE_SCRIPT, "--all")
        prep_json = self._parse_json(prep)
        self.assertEqual(prep.returncode, 0, f"prepare not exit 0: {prep.stderr}")
        self.assertEqual(prep_json["status"], "ok", f"prepare not ok: {prep_json}")
        self.assertEqual(prep_json["key"], "all")
        self.assertEqual(prep_json["counts"]["added"], 0)
        self.assertEqual(prep_json["counts"]["deleted"], 0)
        # pending は 1 件も生成されない
        self.assertEqual(self._pending_files("all"), [])

        # 2. merge --all: NO_TARGETS にならず空 toc.yaml を冪等出力（status ok / exit 0）
        merge = self._run(MERGE_SCRIPT, "--all")
        merge_json = self._parse_json(merge)
        self.assertEqual(merge.returncode, 0, f"merge not exit 0: {merge.stderr}")
        self.assertEqual(
            merge_json["status"], "ok",
            f"merge not ok (expected empty-ToC idempotent output): {merge_json}",
        )
        self.assertIsNone(merge_json["error_code"])

        # 3. toc.yaml が file_count 0 で生成されている
        toc_path = self._store_dir("all") / "toc.yaml"
        self.assertTrue(toc_path.exists(), "empty toc.yaml not generated")
        toc_text = toc_path.read_text(encoding="utf-8")
        self.assertIn("  file_count: 0", toc_text.split("\n"))
        self.assertEqual(load_existing_toc(toc_path), {})

        # 4. get_toc --all は空 docs を status ok / exit 0 で返す（TOC_NOT_FOUND にならない）
        get = self._run(GET_SCRIPT, "--all")
        get_json = self._parse_json(get)
        self.assertEqual(get.returncode, 0, f"get_toc not exit 0: {get.stderr}")
        self.assertEqual(get_json["status"], "ok", f"get_toc not ok: {get_json}")
        self.assertEqual(get_json["file_count"], 0)
        self.assertEqual(get_json["docs"], {})

    def test_all_mode_empty_repo_idempotent(self):
        """空 repo パイプラインを 2 回繰り返しても同一の空 ToC を冪等に再生成する。"""
        for _ in range(2):
            prep = self._run(PREPARE_SCRIPT, "--all")
            self.assertEqual(self._parse_json(prep)["status"], "ok")
            merge = self._run(MERGE_SCRIPT, "--all")
            merge_json = self._parse_json(merge)
            self.assertEqual(merge.returncode, 0, f"merge not exit 0: {merge.stderr}")
            self.assertEqual(merge_json["status"], "ok")

        toc_path = self._store_dir("all") / "toc.yaml"
        self.assertTrue(toc_path.exists())
        self.assertEqual(load_existing_toc(toc_path), {})

    def test_explicit_empty_paths_emits_empty_toc(self):
        """--key K で空配列 paths を渡しても error にならず空 toc.yaml を冪等出力する。"""
        key = "rules"
        prep = self._run(
            PREPARE_SCRIPT, "--key", key, "--paths-json", json.dumps([]),
        )
        prep_json = self._parse_json(prep)
        self.assertEqual(prep_json["status"], "ok")
        self.assertEqual(prep_json["counts"]["added"], 0)

        merge = self._run(MERGE_SCRIPT, "--key", key)
        merge_json = self._parse_json(merge)
        self.assertEqual(merge.returncode, 0, f"merge not exit 0: {merge.stderr}")
        self.assertEqual(merge_json["status"], "ok")

        toc_path = self._store_dir(key) / "toc.yaml"
        self.assertTrue(toc_path.exists())
        self.assertEqual(load_existing_toc(toc_path), {})

    def test_no_prepare_then_merge_still_no_targets(self):
        """prepare を経ずに素で merge した場合は従来どおり NO_TARGETS（取り違え防止）。"""
        merge = self._run(MERGE_SCRIPT, "--key", "ghost")
        merge_json = self._parse_json(merge)
        self.assertNotEqual(merge.returncode, 0)
        self.assertEqual(merge_json["status"], "error")
        self.assertEqual(merge_json["error_code"], "NO_TARGETS")


# ===========================================================================
# 削除（remove --key / FR-N06-1 / DES-005 §13）
# ===========================================================================

class TestRemovePipeline(PipelineTestBase):
    """remove --key で store_dir が削除される。"""

    def test_remove_key_deletes_store_dir(self):
        key = "rules"
        self._write_md("docs/a.md", "# A\n\nbody a\n")
        self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/a.md"]),
        )
        for pending in self._pending_files(key):
            self._fill_pending(key, pending)
        self._run(MERGE_SCRIPT, "--key", key)

        store_dir = self._store_dir(key)
        self.assertTrue(store_dir.exists(), "store_dir not created before remove")

        rm = self._run(REMOVE_SCRIPT, "--key", key)
        rm_json = self._parse_json(rm)
        self.assertEqual(rm_json["status"], "ok", f"remove not ok: {rm_json}")
        self.assertFalse(
            store_dir.exists(),
            f"store_dir should be deleted: {store_dir}",
        )


# ===========================================================================
# FR-N07-1: script 単体がメタデータ抽出をしない（充填は agent 経路のみ）
# ===========================================================================

class TestNoMetadataExtractionByScript(PipelineTestBase):
    """prepare/merge/get/remove は単体でメタデータを生成しない。

    観測可能な固定:
    - prepare 直後の pending は status: pending かつ title/purpose が null、
      content_details/applicable_tasks/keywords が空（script は抽出しない）
    - merge は status: pending（未充填）の pending を toc.yaml に取り込まない
      （充填済み = completed のみ統合する）
    """

    def _read_pending(self, pending_path):
        """pending YAML を (meta, fields) に分解して返す。"""
        return parse_simple_yaml(pending_path.read_text(encoding="utf-8"))

    def test_prepare_emits_unfilled_pending(self):
        key = "rules"
        self._write_md(
            "docs/coding_standards.md",
            "# Coding Standards\n\nUse spaces, not tabs.\n",
        )
        self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/coding_standards.md"]),
        )
        pendings = self._pending_files(key)
        self.assertEqual(len(pendings), 1)

        meta, fields = self._read_pending(pendings[0])
        # script は status を pending のまま生成する（completed にしない）
        self.assertEqual(meta.get("status"), "pending")
        # メタデータは未充填（script は title/purpose/keywords を生成しない）。
        # テンプレートは "title: null" のためパーサは文字列 "null" を返す。
        self.assertIn(fields.get("title"), (None, "null"))
        self.assertIn(fields.get("purpose"), (None, "null"))
        self.assertEqual(fields.get("content_details") or [], [])
        self.assertEqual(fields.get("applicable_tasks") or [], [])
        self.assertEqual(fields.get("keywords") or [], [])
        # source_file（決定的に分かる情報）のみ保持されている
        self.assertEqual(meta.get("source_file"), "docs/coding_standards.md")

    def test_merge_ignores_unfilled_pending(self):
        """status: pending（未充填）の pending は merge で統合されない。"""
        key = "rules"
        self._write_md("docs/a.md", "# A\n\nbody a\n")
        self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps(["docs/a.md"]),
        )
        # 充填せずに merge を実行
        merge = self._run(MERGE_SCRIPT, "--key", key)
        merge_json = self._parse_json(merge)

        # 未充填 pending は統合されない → toc.yaml の docs は空、added=0
        self.assertEqual(merge_json["counts"]["added"], 0)
        toc_path = self._store_dir(key) / "toc.yaml"
        if toc_path.exists():
            docs = load_existing_toc(toc_path)
            self.assertNotIn("docs/a.md", docs)


# ===========================================================================
# REQ-006 制約: 索引の生成は原本の文書を書き換えない
# ===========================================================================

class TestIndexingDoesNotModifySources(PipelineTestBase):
    """prepare → fm_to_pending → write_pending → merge が原本を 1 バイトも変えない。

    REQ-006 の制約「索引の生成は、原本の文書を書き換えない。原本への書き込みは
    利用者が明示的に指示した場合にのみ行う」の回帰テスト。原本への書き込みは
    `write-frontmatter` SKILL（`fm_write.py`）の責務であり、索引経路には無い。

    転記経路（フロントマターあり）と AI 抽出経路（フロントマターなし）の双方を
    通し、merge の JSON が AI 抽出だった対象のみを `ai_extracted_paths` に
    集約することも同時に固定する（DES-008 §8.2）。
    """

    def _remaining_pendings(self, key):
        """status が completed でない pending（AI 抽出待ち）を返す。"""
        remaining = []
        for pending in self._pending_files(key):
            meta, _ = parse_simple_yaml(pending.read_text(encoding="utf-8"))
            if meta.get("status") != "completed":
                remaining.append(pending)
        return remaining

    def test_pipeline_leaves_source_documents_untouched(self):
        key = "rules"
        fm_rel = "docs/with_frontmatter.md"
        plain_rel = "docs/without_frontmatter.md"

        self._write_md(fm_rel, trusted_document())
        self._write_md(plain_rel, "# Plain\n\nNo frontmatter here.\n")

        before = {
            rel: (self.project_root / rel).read_bytes()
            for rel in (fm_rel, plain_rel)
        }

        # 1. prepare
        prep_json = self._parse_json(self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps([fm_rel, plain_rel]),
        ))
        self.assertEqual(prep_json["status"], "ok")
        self.assertEqual(prep_json["counts"]["added"], 2)

        # 2. 転記フェーズ（フロントマターを持つ 1 件のみ completed になる）
        work_dir = self._store_dir(key) / WORK_DIRNAME
        fm_json = self._parse_json(self._run(
            FM_TO_PENDING_SCRIPT, "--work-dir", str(work_dir),
        ))
        self.assertEqual(fm_json["counts"]["transcribed"], 1)

        # 3. 残った pending を AI 抽出（write_pending）で充填
        remaining = self._remaining_pendings(key)
        self.assertEqual(len(remaining), 1)
        self._fill_pending(key, remaining[0])

        # 4. merge
        merge_json = self._parse_json(self._run(MERGE_SCRIPT, "--key", key))
        self.assertEqual(merge_json["status"], "ok", f"merge not ok: {merge_json}")
        self.assertEqual(merge_json["counts"]["added"], 2)
        # AI 抽出だった対象のみが書き戻し候補になる（転記側は含まれない）
        self.assertEqual(merge_json["ai_extracted_paths"], [plain_rel])

        # 5. 両経路が toc.yaml に載っている（索引としては成立している）
        docs = load_existing_toc(self._store_dir(key) / "toc.yaml")
        self.assertEqual(set(docs.keys()), {fm_rel, plain_rel})

        # 6. 原本はバイト列が一致する（索引は原本を書き換えない）
        for rel, original in before.items():
            self.assertEqual(
                (self.project_root / rel).read_bytes(), original,
                f"索引の実行で原本が変更された: {rel}",
            )


# ===========================================================================
# 戦略書 R9: 打刻によるファイル全体ハッシュ変化が一巡で収束する
# ===========================================================================

class TestStampedFileConvergesInOneCycle(PipelineTestBase):
    """打刻 → prepare(updated) → 転記 → merge → 再 prepare(unchanged) の収束。

    `body_hash` の打刻はファイル全体のバイト列を変えるため、`.toc_checksums.yaml`
    は次回 prepare で `updated` を出す。これは設計上の想定内であり（DES-008 §7.2）、
    戦略書 R9 の緩和策は「`updated` も転記経路で処理されるため一巡で収束する」
    ことを根拠としている。本テストはその収束（`updated` が無限に繰り返されず、
    1 回の索引で `unchanged` に落ち着くこと）を固定する。

    収束の機構は `merge_toc.compute_checksums_for_docs` にある。今回の run で
    充填（転記を含む）された doc には現内容ハッシュ = 打刻後のハッシュを書くため、
    次回 prepare は差分を検出しない。
    """

    # 打刻するメタデータ（DES-008 §4.4 により英語。§5.1 の型・件数・文字数に適合）
    STAMP_METADATA = {
        'title': 'Release Checklist',
        'purpose': 'Lists the steps to follow before publishing a release.',
        'content_details': [
            'Version bump order',
            'Changelog entry format',
            'Tag naming convention',
        ],
        'applicable_tasks': [
            'Preparing a release',
            'Reviewing a release commit',
        ],
        'keywords': ['release', 'checklist', 'version bump', 'tag'],
    }

    def _checksum_of(self, key, rel_path):
        """`.toc_checksums.yaml` に記録された rel_path のハッシュを返す。"""
        checksums = load_checksums(self._store_dir(key) / CHECKSUMS_FILENAME)
        self.assertIn(
            rel_path, checksums,
            f"checksums に記録が無い: {rel_path} / {checksums}",
        )
        return checksums[rel_path]

    def test_body_hash_stamp_converges_after_one_indexing_cycle(self):
        key = "rules"
        rel = "docs/release_checklist.md"
        body = "# Release Checklist\n\nBump the version, then tag the commit.\n"
        self._write_md(rel, body)

        # ------------------------------------------------------------------
        # 1. フロントマターを持たない状態で 1 巡（AI 抽出経路 = write_pending）
        # ------------------------------------------------------------------
        prep1 = self._parse_json(self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps([rel]),
        ))
        self.assertEqual(prep1["status"], "ok")
        self.assertEqual(prep1["counts"]["added"], 1)

        pendings = self._pending_files(key)
        self.assertEqual(len(pendings), 1)
        self._fill_pending(key, pendings[0])

        merge1 = self._parse_json(self._run(MERGE_SCRIPT, "--key", key))
        self.assertEqual(merge1["status"], "ok", f"merge not ok: {merge1}")
        self.assertEqual(merge1["counts"]["added"], 1)

        # 打刻前のファイル全体ハッシュ（= hash A）
        hash_a = self._checksum_of(key, rel)
        self.assertEqual(hash_a, calculate_file_hash(self.project_root / rel))

        # ------------------------------------------------------------------
        # 2. fm_write.py でフロントマターを付与・打刻する
        # ------------------------------------------------------------------
        write = self._parse_json(self._run(
            FM_WRITE_SCRIPT,
            "--entries-json", json.dumps([
                {"path": rel, "metadata": self.STAMP_METADATA},
            ]),
        ))
        self.assertEqual(write["status"], "ok", f"fm_write not ok: {write}")
        self.assertEqual(write["counts"]["written"], 1)
        self.assertTrue(write["results"][0]["changed"])

        # 打刻でファイル全体のハッシュが変わる（= hash B / 戦略書 R9 の前提）
        hash_b = calculate_file_hash(self.project_root / rel)
        self.assertNotEqual(
            hash_b, hash_a,
            "打刻でファイル全体のハッシュが変わるはずである（R9 の前提）",
        )

        # 補助確認: body_hash は本文のみを対象とするため打刻の前後で不変（§4.2）
        self.assertEqual(
            write["results"][0]["body_hash"], compute_body_hash(body),
            "打刻された body_hash が打刻前の本文から算出した値と一致しない",
        )

        # ------------------------------------------------------------------
        # 3. prepare は updated を検出する（R9 が予測する現象 / DES-008 §7.2）
        # ------------------------------------------------------------------
        prep2 = self._parse_json(self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps([rel]),
        ))
        self.assertEqual(prep2["status"], "ok")
        self.assertEqual(
            prep2["counts"]["updated"], 1,
            f"打刻後の prepare は updated=1 を出すはずである: {prep2}",
        )
        self.assertEqual(prep2["counts"]["unchanged"], 0)

        # ------------------------------------------------------------------
        # 4. 転記フェーズで完了化する（Agent 起動ゼロ / DES-008 §7.1）
        # ------------------------------------------------------------------
        work_dir = self._store_dir(key) / WORK_DIRNAME
        fm_json = self._parse_json(self._run(
            FM_TO_PENDING_SCRIPT, "--work-dir", str(work_dir),
        ))
        self.assertEqual(fm_json["status"], "ok", f"fm_to_pending not ok: {fm_json}")
        self.assertEqual(
            fm_json["counts"]["transcribed"], 1,
            f"打刻済み文書は転記のみで完了化されるはずである: {fm_json}",
        )
        self.assertEqual(fm_json["counts"]["failed"], 0)

        # ------------------------------------------------------------------
        # 5. merge が成功し、checksums が hash B へ更新される
        # ------------------------------------------------------------------
        merge2 = self._parse_json(self._run(MERGE_SCRIPT, "--key", key))
        self.assertEqual(merge2["status"], "ok", f"merge not ok: {merge2}")
        self.assertEqual(merge2["counts"]["updated"], 1)
        self.assertEqual(
            self._checksum_of(key, rel), hash_b,
            "merge 後の checksums が打刻後のハッシュ（hash B）になっていない",
        )
        # 転記由来なので AI 抽出の書き戻し候補には現れない（DES-008 §8.2）
        self.assertEqual(merge2["ai_extracted_paths"], [])
        # 転記されたメタデータが toc.yaml に載っている
        docs = load_existing_toc(self._store_dir(key) / "toc.yaml")
        self.assertEqual(docs[rel]["title"], self.STAMP_METADATA["title"])

        # ------------------------------------------------------------------
        # 6. 再度の prepare は unchanged（= 一巡で収束。本テストの主張）
        # ------------------------------------------------------------------
        prep3 = self._parse_json(self._run(
            PREPARE_SCRIPT, "--key", key,
            "--paths-json", json.dumps([rel]),
        ))
        self.assertEqual(prep3["status"], "ok")
        self.assertEqual(
            prep3["counts"]["unchanged"], 1,
            f"打刻による updated は一巡で収束するはずである: {prep3}",
        )
        self.assertEqual(prep3["counts"]["updated"], 0)
        self.assertEqual(prep3["counts"]["added"], 0)
        # 収束しているため pending も生成されない（再抽出・再転記が走らない）
        self.assertEqual(self._pending_files(key), [])


# ===========================================================================
# JSON 契約 / enum 固定（FR-N08-2）— 異常系も含めて enum に収まる
# ===========================================================================

class TestJsonContractEnums(PipelineTestBase):
    """全 script の stdout が単一 JSON で status / error_code が enum に収まる。"""

    def test_prepare_reserved_key_error_code(self):
        """--key all（任意指定）は KEY_RESERVED で reject される。"""
        prep = self._run(
            PREPARE_SCRIPT, "--key", "all",
            "--paths-json", json.dumps(["docs/a.md"]),
        )
        prep_json = self._parse_json(prep)  # enum 検証は _parse_json 内
        self.assertEqual(prep_json["status"], "error")
        self.assertEqual(prep_json["error_code"], "KEY_RESERVED")

    def test_prepare_rejects_traversal_path(self):
        """traversal path は rejected_paths に列挙され partial になる。"""
        self._write_md("docs/a.md", "# A\n\nbody a\n")
        prep = self._run(
            PREPARE_SCRIPT, "--key", "rules",
            "--paths-json", json.dumps(["docs/a.md", "../evil.md"]),
        )
        prep_json = self._parse_json(prep)
        self.assertEqual(prep_json["status"], "partial")
        reasons = {r["reason"] for r in prep_json.get("rejected_paths", [])}
        self.assertTrue(reasons.issubset(ERROR_CODES))
        self.assertIn("PATH_TRAVERSAL", reasons)

    def test_remove_missing_key_toc_not_found(self):
        """存在しない key の path 個別削除は TOC_NOT_FOUND。"""
        rm = self._run(
            REMOVE_SCRIPT, "--key", "ghost",
            "--paths-json", json.dumps(["docs/x.md"]),
        )
        rm_json = self._parse_json(rm)
        self.assertEqual(rm_json["status"], "error")
        self.assertEqual(rm_json["error_code"], "TOC_NOT_FOUND")

    def test_get_missing_toc_error_code(self):
        """存在しない key の get は TOC_NOT_FOUND を返す。"""
        get = self._run(GET_SCRIPT, "--key", "ghost")
        get_json = self._parse_json(get)
        self.assertEqual(get_json["status"], "error")
        self.assertEqual(get_json["error_code"], "TOC_NOT_FOUND")


if __name__ == '__main__':
    unittest.main()
