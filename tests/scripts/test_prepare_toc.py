#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_toc.py のユニットテスト（DES-005 §13 / REQ-001 NFR-N03）。

テスト対象:
- desired-state 差分検出（added / updated / unchanged / deleted）
  * 部分配列 → 残りが deleted になる固定（REQ-001 受け入れ基準）
- --dry-run（書き込みなしで予定提示）
- 空 repo / 対象 0 件の冪等空出力（status ok）
- --all 単体モード（固定除外・root 外 symlink 除外）
- path 検証 reject（絶対 / traversal / 不在 / 非 Markdown）
- JSON 契約（status / error_code enum）
- has_substantive_content（空ファイル skip）

移行元: test_create_pending.py（create_pending_yaml.py のテスト）。
新 I/F へ作り替え、category / doc_type 依存テストは廃止。

テスト方針:
- in-process import（compute_diff / validate_paths / collect_all_markdown 等）
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

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from prepare_toc import (
    has_substantive_content,
    get_yaml_filename,
    validate_paths,
    collect_all_markdown,
    compute_diff,
    SYSTEM_EXCLUDE_PATTERNS,
    MAX_FILES_WARN_THRESHOLD,
)
from toc_store import resolve_store_dir, WORK_DIRNAME, CHECKSUMS_FILENAME

PREPARE_SCRIPT = os.path.join(SCRIPTS_DIR, 'prepare_toc.py')


# ===========================================================================
# 共通基盤（subprocess 実行 + 一時 project root）
# ===========================================================================

class PrepareTestBase(unittest.TestCase):
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

    def _write_prev_checksums(self, key, mapping):
        """store_dir/.toc_checksums.yaml に prev checksums を書き出す。"""
        store_dir = self._store_dir(key)
        store_dir.mkdir(parents=True, exist_ok=True)
        lines = ["checksums:"]
        for path, h in mapping.items():
            lines.append(f"  {path}: {h}")
        (store_dir / CHECKSUMS_FILENAME).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _run(self, *args):
        cmd = [sys.executable, PREPARE_SCRIPT] + list(args)
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
# desired-state 差分検出（DES-005 §6.2）— in-process
# ===========================================================================

class TestComputeDiff(PrepareTestBase):
    """compute_diff の added / updated / unchanged / deleted 算出テスト。"""

    def _hash(self, rel_path):
        from toc_utils import calculate_file_hash
        return calculate_file_hash(self.project_root / rel_path)

    def test_added_when_not_in_prev(self):
        self._write_md("docs/a.md")
        diff = compute_diff(["docs/a.md"], {}, self.project_root)
        self.assertEqual(diff["added"], ["docs/a.md"])
        self.assertEqual(diff["updated"], [])
        self.assertEqual(diff["unchanged"], [])
        self.assertEqual(diff["deleted"], [])

    def test_unchanged_when_hash_matches(self):
        self._write_md("docs/a.md")
        prev = {"docs/a.md": self._hash("docs/a.md")}
        diff = compute_diff(["docs/a.md"], prev, self.project_root)
        self.assertEqual(diff["unchanged"], ["docs/a.md"])
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["updated"], [])

    def test_updated_when_hash_differs(self):
        self._write_md("docs/a.md")
        prev = {"docs/a.md": "stale-hash-value"}
        diff = compute_diff(["docs/a.md"], prev, self.project_root)
        self.assertEqual(diff["updated"], ["docs/a.md"])
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["unchanged"], [])

    def test_deleted_when_in_prev_not_in_desired(self):
        """prev にあり desired に無い path は deleted。"""
        self._write_md("docs/a.md")
        prev = {
            "docs/a.md": self._hash("docs/a.md"),
            "docs/gone.md": "old-hash",
        }
        diff = compute_diff(["docs/a.md"], prev, self.project_root)
        self.assertEqual(diff["deleted"], ["docs/gone.md"])
        self.assertEqual(diff["unchanged"], ["docs/a.md"])

    def test_partial_array_deletes_remainder(self):
        """部分配列を渡すと prev の残りが deleted になる（REQ-001 受け入れ基準・回帰固定）。"""
        self._write_md("docs/a.md")
        self._write_md("docs/b.md")
        # prev には a/b/c が記録されている
        prev = {
            "docs/a.md": self._hash("docs/a.md"),
            "docs/b.md": self._hash("docs/b.md"),
            "docs/c.md": "old-hash-c",
        }
        # 今回 desired として a と b のみを渡す → c は deleted になるべき
        diff = compute_diff(["docs/a.md", "docs/b.md"], prev, self.project_root)
        self.assertEqual(diff["deleted"], ["docs/c.md"])
        self.assertNotIn("docs/a.md", diff["deleted"])
        self.assertNotIn("docs/b.md", diff["deleted"])

    def test_empty_desired_with_prev_deletes_all(self):
        """desired が空で prev に履歴がある場合、全削除になる。"""
        prev = {"docs/a.md": "h1", "docs/b.md": "h2"}
        diff = compute_diff([], prev, self.project_root)
        self.assertEqual(set(diff["deleted"]), {"docs/a.md", "docs/b.md"})
        self.assertEqual(diff["added"], [])

    def test_empty_desired_empty_prev(self):
        """空 repo（desired 空 + prev 空）は全カテゴリ空。"""
        diff = compute_diff([], {}, self.project_root)
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["updated"], [])
        self.assertEqual(diff["unchanged"], [])
        self.assertEqual(diff["deleted"], [])


# ===========================================================================
# CLI: 差分検出 → pending 生成（subprocess JSON 契約）
# ===========================================================================

class TestPrepareCli(PrepareTestBase):
    """prepare_toc.py CLI の JSON 契約・pending 生成テスト。"""

    def test_added_creates_pending(self):
        """新規 path で pending YAML が生成され counts.added が立つ。"""
        self._write_md("docs/a.md")
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertIsNone(obj["error_code"])
        self.assertEqual(obj["counts"]["added"], 1)
        self.assertEqual(obj["normalized_paths"], ["docs/a.md"])

        # pending YAML が work dir に生成されること
        work_dir = self._store_dir("rules") / WORK_DIRNAME
        self.assertTrue(work_dir.is_dir())
        yamls = [f for f in os.listdir(work_dir) if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yamls), 1)
        content = (work_dir / yamls[0]).read_text(encoding='utf-8')
        self.assertIn("source_file: docs/a.md", content)
        self.assertIn("status: pending", content)
        # doc_type は除去されている（DES-005 §7.1）
        self.assertNotIn("doc_type", content)

    def test_meta_yaml_written(self):
        """prepare 後に meta.yaml に original key が保持される。"""
        self._write_md("docs/a.md")
        self._run('--key', 'rules', '--paths-json', '["docs/a.md"]')
        meta = self._store_dir("rules") / "meta.yaml"
        self.assertTrue(meta.exists())
        self.assertIn("original_key: rules", meta.read_text(encoding='utf-8'))

    def test_updated_detected_against_prev(self):
        """prev と hash 不一致なら updated になる。"""
        self._write_md("docs/a.md")
        self._write_prev_checksums("rules", {"docs/a.md": "stale-hash"})
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]')
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["updated"], 1)
        self.assertEqual(obj["counts"]["added"], 0)

    def test_unchanged_no_pending(self):
        """hash 一致なら unchanged で pending を生成しない。"""
        from toc_utils import calculate_file_hash
        self._write_md("docs/a.md")
        h = calculate_file_hash(self.project_root / "docs/a.md")
        self._write_prev_checksums("rules", {"docs/a.md": h})
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]')
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["unchanged"], 1)
        self.assertEqual(obj["counts"]["added"], 0)
        self.assertEqual(obj["counts"]["updated"], 0)
        # work dir は作られない（targets が空）
        work_dir = self._store_dir("rules") / WORK_DIRNAME
        if work_dir.exists():
            yamls = [f for f in os.listdir(work_dir) if f.endswith('.yaml') and not f.startswith('.')]
            self.assertEqual(len(yamls), 0)

    def test_partial_array_deletes_remainder_cli(self):
        """CLI でも部分配列 → 残りが deleted になる（回帰固定）。"""
        from toc_utils import calculate_file_hash
        self._write_md("docs/a.md")
        self._write_md("docs/b.md")
        ha = calculate_file_hash(self.project_root / "docs/a.md")
        hb = calculate_file_hash(self.project_root / "docs/b.md")
        self._write_prev_checksums("rules", {
            "docs/a.md": ha, "docs/b.md": hb, "docs/c.md": "old-c",
        })
        # desired として a/b のみ → c は deleted
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md", "docs/b.md"]')
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["deleted"], 1)
        self.assertEqual(obj["counts"]["unchanged"], 2)

    def test_skips_empty_files(self):
        """空ファイル（実体なし）は skip され pending を生成しない。"""
        self._write_md("docs/empty.md", content='')
        self._write_md("docs/headers.md", content='# Header\n\n## Sub\n')
        self._write_md("docs/valid.md", content='# T\n\nBody.\n')
        proc = self._run(
            '--key', 'rules',
            '--paths-json', '["docs/empty.md", "docs/headers.md", "docs/valid.md"]',
        )
        obj = self._parse_stdout(proc)
        # 3 件すべて added 判定（差分検出は内容に関わらず added）
        self.assertEqual(obj["counts"]["added"], 3)
        # pending YAML は valid.md のみ（空/ヘッダのみは skip）
        work_dir = self._store_dir("rules") / WORK_DIRNAME
        yamls = [f for f in os.listdir(work_dir) if f.endswith('.yaml') and not f.startswith('.')]
        self.assertEqual(len(yamls), 1)


# ===========================================================================
# --dry-run（FR-N02-5）
# ===========================================================================

class TestDryRun(PrepareTestBase):
    """--dry-run は書き込みをしない。"""

    def test_dry_run_no_write(self):
        self._write_md("docs/a.md")
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]', '--dry-run')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["counts"]["added"], 1)
        self.assertEqual(obj["normalized_paths"], ["docs/a.md"])
        # work dir も meta.yaml も作られない
        store_dir = self._store_dir("rules")
        self.assertFalse((store_dir / WORK_DIRNAME).exists())
        self.assertFalse((store_dir / "meta.yaml").exists())

    def test_dry_run_reports_deleted(self):
        """--dry-run で deleted 予定が提示される。"""
        from toc_utils import calculate_file_hash
        self._write_md("docs/a.md")
        ha = calculate_file_hash(self.project_root / "docs/a.md")
        self._write_prev_checksums("rules", {"docs/a.md": ha, "docs/old.md": "h"})
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]', '--dry-run')
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["deleted"], 1)


# ===========================================================================
# 空 repo / 対象 0 件 冪等空出力（DES-005 §9.2）
# ===========================================================================

class TestEmptyRepo(PrepareTestBase):
    """空 repo / 対象 0 件は error ではなく status ok の空出力。"""

    def test_all_empty_repo_ok(self):
        """--all で対象 0 件でも status ok / counts 全 0。"""
        proc = self._run('--all')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["key"], "all")
        self.assertEqual(obj["counts"]["added"], 0)
        self.assertEqual(obj["normalized_paths"], [])

    def test_empty_paths_json_ok(self):
        """空 paths 配列は error ではなく status ok。"""
        proc = self._run('--key', 'rules', '--paths-json', '[]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["counts"]["added"], 0)

    def test_all_idempotent(self):
        """--all を 2 回流しても 2 回目は unchanged（冪等）。"""
        from toc_utils import calculate_file_hash
        self._write_md("README.md")
        # 1 回目: prev なし → added
        proc1 = self._run('--all')
        obj1 = self._parse_stdout(proc1)
        self.assertEqual(obj1["counts"]["added"], 1)
        # prev checksums を 1 回目相当で用意し直して unchanged を確認
        h = calculate_file_hash(self.project_root / "README.md")
        self._write_prev_checksums("all", {"README.md": h})
        proc2 = self._run('--all')
        obj2 = self._parse_stdout(proc2)
        self.assertEqual(obj2["counts"]["unchanged"], 1)
        self.assertEqual(obj2["counts"]["added"], 0)


# ===========================================================================
# --all 単体モード: 固定除外 / root 外 symlink 除外（DES-005 §9.1 / §5.3）
# ===========================================================================

class TestSingleModeCollection(PrepareTestBase):
    """collect_all_markdown の固定除外・root 外 symlink 除外（in-process）。"""

    def test_fixed_exclude_list_covers_spec(self):
        """固定除外リストが DES-005 §9.1 の必須項目を含む。"""
        required = {
            ".git", ".claude", ".codex", "node_modules", "vendor", "dist",
            "build", "__pycache__", ".venv", "target", "coverage",
            ".pytest_cache", ".mypy_cache",
        }
        self.assertTrue(required.issubset(set(SYSTEM_EXCLUDE_PATTERNS)))

    def test_fixed_exclusions_applied(self):
        """固定除外ディレクトリ配下の Markdown は収集されない。"""
        self._write_md("docs/keep.md")
        self._write_md(".git/should_skip.md")
        self._write_md("node_modules/pkg/skip.md")
        self._write_md(".claude/state/skip.md")
        self._write_md("__pycache__/skip.md")
        result = collect_all_markdown(self.project_root)
        self.assertIn("docs/keep.md", result)
        self.assertNotIn(".git/should_skip.md", result)
        self.assertNotIn("node_modules/pkg/skip.md", result)
        self.assertNotIn(".claude/state/skip.md", result)
        self.assertNotIn("__pycache__/skip.md", result)

    def test_generated_toc_excluded(self):
        """生成済み ToC / work files（.claude 配下）は除外される。"""
        self._write_md("docs/keep.md")
        # 生成済み store ファイル相当
        store = self._store_dir("rules")
        (store / WORK_DIRNAME).mkdir(parents=True, exist_ok=True)
        (store / WORK_DIRNAME / "pending.md").write_text("# x\n\nbody\n", encoding="utf-8")
        result = collect_all_markdown(self.project_root)
        self.assertIn("docs/keep.md", result)
        self.assertFalse(any(".claude" in p for p in result))

    def test_root_external_symlink_excluded(self):
        """root 外実体を指す symlink は除外される（§5.3）。"""
        if not hasattr(Path, "is_relative_to"):
            self.skipTest("Python 3.9+ required")
        # project root 外に実体を作る
        outside_dir = tempfile.mkdtemp()
        try:
            outside_md = Path(outside_dir) / "external.md"
            outside_md.write_text("# External\n\nbody\n", encoding="utf-8")
            self._write_md("docs/keep.md")
            link = self.project_root / "docs" / "linked.md"
            try:
                os.symlink(str(outside_md), str(link))
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported on this platform")
            result = collect_all_markdown(self.project_root)
            self.assertIn("docs/keep.md", result)
            # root 外実体を指す symlink は除外
            self.assertNotIn("docs/linked.md", result)
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_internal_symlink_included(self):
        """root 内実体を指す symlink は収集対象（重複排除は inode で行われる）。"""
        if not hasattr(Path, "is_relative_to"):
            self.skipTest("Python 3.9+ required")
        target = self._write_md("docs/real.md")
        link = self.project_root / "alias.md"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlink not supported on this platform")
        result = collect_all_markdown(self.project_root)
        # real.md か alias.md のいずれか（inode 重複排除で 1 つ）が含まれる
        self.assertTrue("docs/real.md" in result or "alias.md" in result)

    def test_max_files_warning_via_cli(self):
        """最大ファイル数超過時に warnings に追加され処理継続（NFR-N05 / 閾値 100）。"""
        # 閾値 100 を超える 101 件を作成
        for i in range(MAX_FILES_WARN_THRESHOLD + 1):
            self._write_md(f"docs/f{i:04d}.md")
        proc = self._run('--all')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertGreater(obj["counts"]["added"], MAX_FILES_WARN_THRESHOLD)
        self.assertTrue(
            any("exceeds threshold" in w for w in obj["warnings"]),
            f"warnings: {obj['warnings']}",
        )


# ===========================================================================
# path 検証 reject（DES-005 §5.1 / FR-N03）
# ===========================================================================

class TestPathValidation(PrepareTestBase):
    """validate_paths と CLI reject のテスト。"""

    def test_absolute_path_rejected(self):
        norm, rejected = validate_paths(["/etc/passwd.md"], self.project_root)
        self.assertEqual(norm, [])
        self.assertEqual(rejected[0]["reason"], "ABSOLUTE_PATH")

    def test_traversal_rejected(self):
        norm, rejected = validate_paths(["../outside.md"], self.project_root)
        self.assertEqual(norm, [])
        self.assertEqual(rejected[0]["reason"], "PATH_TRAVERSAL")

    def test_nonexistent_rejected(self):
        norm, rejected = validate_paths(["docs/missing.md"], self.project_root)
        self.assertEqual(norm, [])
        self.assertEqual(rejected[0]["reason"], "NOT_FOUND")

    def test_non_markdown_rejected(self):
        self._write_md("docs/note.txt", content='plain text')
        norm, rejected = validate_paths(["docs/note.txt"], self.project_root)
        self.assertEqual(norm, [])
        self.assertEqual(rejected[0]["reason"], "NOT_MARKDOWN")

    def test_valid_path_normalized(self):
        self._write_md("docs/a.md")
        norm, rejected = validate_paths(["./docs/a.md"], self.project_root)
        self.assertEqual(norm, ["docs/a.md"])
        self.assertEqual(rejected, [])

    def test_duplicate_paths_deduped(self):
        self._write_md("docs/a.md")
        norm, rejected = validate_paths(["docs/a.md", "./docs/a.md"], self.project_root)
        self.assertEqual(norm, ["docs/a.md"])

    def test_cli_rejected_paths_partial_status(self):
        """一部 reject があると status partial で rejected_paths に列挙される。"""
        self._write_md("docs/a.md")
        proc = self._run(
            '--key', 'rules',
            '--paths-json', '["docs/a.md", "../escape.md", "/abs.md"]',
        )
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "partial")
        reasons = {r["reason"] for r in obj["rejected_paths"]}
        self.assertIn("PATH_TRAVERSAL", reasons)
        self.assertIn("ABSOLUTE_PATH", reasons)
        self.assertEqual(obj["counts"]["added"], 1)


# ===========================================================================
# key 解決・JSON 契約（DES-005 §3.3 / §8）
# ===========================================================================

class TestKeyAndJsonContract(PrepareTestBase):
    """key 解決規則と JSON enum 契約。"""

    def test_explicit_all_rejected(self):
        """--key all は KEY_RESERVED で reject される。"""
        proc = self._run('--key', 'all', '--paths-json', '[]')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertEqual(obj["error_code"], "KEY_RESERVED")

    def test_empty_key_rejected(self):
        proc = self._run('--key', '', '--paths-json', '[]')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "KEY_EMPTY")

    def test_key_omitted_resolves_all(self):
        """--key 省略は予約 key 'all' に解決する。"""
        proc = self._run()  # 引数なし → 単体モード all
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["key"], "all")

    def test_invalid_json_rejected(self):
        proc = self._run('--key', 'rules', '--paths-json', 'not-json')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "INVALID_PATH")

    def test_paths_file_input(self):
        """--paths-file から JSON を読み込める。"""
        self._write_md("docs/a.md")
        paths_file = self.project_root / "paths.json"
        paths_file.write_text('["docs/a.md"]', encoding="utf-8")
        proc = self._run('--key', 'rules', '--paths-file', str(paths_file))
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["counts"]["added"], 1)

    def test_status_and_error_code_present(self):
        """全 JSON 出力に status / error_code が含まれる。"""
        self._write_md("docs/a.md")
        proc = self._run('--key', 'rules', '--paths-json', '["docs/a.md"]')
        obj = self._parse_stdout(proc)
        self.assertIn("status", obj)
        self.assertIn("error_code", obj)
        self.assertIn(obj["status"], {"ok", "error", "partial"})


# ===========================================================================
# work file 名（DES-005 §6.4）
# ===========================================================================

class TestYamlFilename(unittest.TestCase):
    """get_yaml_filename は sha256(source)[:16].yaml。"""

    def test_filename_format(self):
        name = get_yaml_filename("docs/a.md")
        self.assertTrue(name.endswith(".yaml"))
        stem = name[:-5]
        self.assertEqual(len(stem), 16)
        self.assertRegex(stem, r'^[0-9a-f]{16}$')

    def test_deterministic(self):
        self.assertEqual(get_yaml_filename("docs/a.md"), get_yaml_filename("docs/a.md"))

    def test_distinct_sources_distinct_names(self):
        self.assertNotEqual(get_yaml_filename("docs/a.md"), get_yaml_filename("docs/b.md"))


# ===========================================================================
# has_substantive_content（旧 create_pending から移行 / §12）
# ===========================================================================

class TestHasSubstantiveContent(unittest.TestCase):
    """has_substantive_content の判定テスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, content):
        path = os.path.join(self.tmpdir, 'test.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_empty_file(self):
        self.assertFalse(has_substantive_content(self._write_file('')))

    def test_whitespace_only(self):
        self.assertFalse(has_substantive_content(self._write_file('   \n\n  \n')))

    def test_frontmatter_only(self):
        self.assertFalse(has_substantive_content(
            self._write_file('---\ntitle: Test\ndate: 2024-01-01\n---\n')
        ))

    def test_frontmatter_and_headers_only(self):
        self.assertFalse(has_substantive_content(
            self._write_file('---\ntitle: Test\n---\n\n# Header\n\n## Sub Header\n')
        ))

    def test_frontmatter_with_body(self):
        self.assertTrue(has_substantive_content(
            self._write_file('---\ntitle: Test\n---\n\n# Header\n\nSome actual content here.\n')
        ))

    def test_no_frontmatter_with_body(self):
        self.assertTrue(has_substantive_content(
            self._write_file('# Header\n\nThis is body content.\n')
        ))

    def test_unclosed_frontmatter(self):
        self.assertFalse(has_substantive_content(
            self._write_file('---\ntitle: Test\nkey: value\nmore: data\n')
        ))

    def test_headers_only_no_frontmatter(self):
        self.assertFalse(has_substantive_content(
            self._write_file('# Header\n\n## Sub Header\n')
        ))

    def test_leading_blank_lines_before_frontmatter(self):
        self.assertTrue(has_substantive_content(
            self._write_file('\n\n---\ntitle: Test\n---\n\nBody text.\n')
        ))

    def test_nonexistent_file(self):
        self.assertFalse(has_substantive_content('/nonexistent/path/file.md'))


if __name__ == '__main__':
    unittest.main()
