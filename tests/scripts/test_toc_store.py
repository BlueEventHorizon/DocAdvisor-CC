#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""toc_store.py のユニットテスト（DES-005 §13 / REQ-001 NFR-N03）。

テスト対象:
- resolve_store_dir: slug 化・hash サフィックス・予約 key all・空 slug→"k"・
  過長/Unicode key・同一 key の決定的解決・slug 衝突時の別ディレクトリ解決
- key 検証: validate_user_key（KEY_EMPTY / 任意 all の KEY_RESERVED）・is_reserved_key
- emit_json: JSON 契約（status / error_code enum）
- promote / clean: 冪等動作（in-process）
- CLI: subprocess での JSON 契約（空 key / 任意 all / promote / clean）

テスト方針:
- in-process import（test_toc_utils.py パターン）と
  subprocess JSON 契約（test_filter_toc.py パターン）の両方を使う。
"""

import io
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

import toc_store
from toc_store import (
    DEFAULT_KEY,
    STORE_ROOT_REL,
    ErrorCode,
    ERROR_CODES,
    STATUSES,
    STATUS_OK,
    STATUS_ERROR,
    KeyError_,
    resolve_store_dir,
    is_reserved_key,
    validate_user_key,
    emit_json,
    promote_pending,
    clean_work_dir,
    work_status,
)

TOC_STORE_SCRIPT = os.path.join(SCRIPTS_DIR, 'toc_store.py')


# ===========================================================================
# resolve_store_dir（DES-005 §3.1 / FR-N01-3）
# ===========================================================================

class TestResolveStoreDir(unittest.TestCase):
    """key → store_dir の決定的変換テスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_under_store_root(self):
        """store_dir は keys/ 配下に解決される。"""
        d = resolve_store_dir("rules", project_root=self.root)
        expected_parent = self.root / STORE_ROOT_REL
        self.assertEqual(d.parent, expected_parent)

    def test_slug_and_hash_suffix_format(self):
        """{slug}-{12桁hex} の形式になる。"""
        d = resolve_store_dir("rules", project_root=self.root)
        name = d.name
        self.assertTrue(name.startswith("rules-"), name)
        suffix = name.rsplit("-", 1)[1]
        self.assertEqual(len(suffix), 12)
        self.assertRegex(suffix, r'^[0-9a-f]{12}$')

    def test_deterministic(self):
        """同一 key は常に同一 store_dir へ解決される。"""
        d1 = resolve_store_dir("my-key", project_root=self.root)
        d2 = resolve_store_dir("my-key", project_root=self.root)
        self.assertEqual(d1, d2)

    def test_slugify_lowercases_and_replaces(self):
        """大文字・記号を含む key の slug は英小文字 + '_' になる。"""
        d = resolve_store_dir("My Rules!Key", project_root=self.root)
        slug = d.name.rsplit("-", 1)[0]
        self.assertEqual(slug, "my_rules_key")

    def test_consecutive_underscore_compressed(self):
        """連続する非許可文字は単一 '_' に圧縮される。"""
        d = resolve_store_dir("a   b///c", project_root=self.root)
        slug = d.name.rsplit("-", 1)[0]
        self.assertEqual(slug, "a_b_c")

    def test_symbol_only_key_slug_is_k(self):
        """記号のみ key の slug は 'k' になり、識別はサフィックスが担う。"""
        d = resolve_store_dir("!!!///", project_root=self.root)
        slug = d.name.rsplit("-", 1)[0]
        self.assertEqual(slug, "k")

    def test_empty_string_slug_is_k(self):
        """空文字 key（決定的変換のみ）でも slug は 'k'。"""
        d = resolve_store_dir("", project_root=self.root)
        slug = d.name.rsplit("-", 1)[0]
        self.assertEqual(slug, "k")

    def test_long_key_slug_truncated(self):
        """過長 key は slug が 40 文字に切り詰められ、reject されない。"""
        long_key = "a" * 200
        d = resolve_store_dir(long_key, project_root=self.root)
        slug = d.name.rsplit("-", 1)[0]
        self.assertLessEqual(len(slug), 40)
        self.assertEqual(slug, "a" * 40)

    def test_long_keys_differ_by_suffix(self):
        """slug が同じになる過長 key 同士もサフィックスで別ディレクトリになる。"""
        d1 = resolve_store_dir("a" * 60, project_root=self.root)
        d2 = resolve_store_dir("a" * 61, project_root=self.root)
        slug1 = d1.name.rsplit("-", 1)[0]
        slug2 = d2.name.rsplit("-", 1)[0]
        self.assertEqual(slug1, slug2)
        self.assertNotEqual(d1, d2)

    def test_slug_collision_resolves_to_distinct_dirs(self):
        """slug が衝突する異なる key は別ディレクトリに解決される。"""
        d1 = resolve_store_dir("foo bar", project_root=self.root)
        d2 = resolve_store_dir("foo/bar", project_root=self.root)
        slug1 = d1.name.rsplit("-", 1)[0]
        slug2 = d2.name.rsplit("-", 1)[0]
        self.assertEqual(slug1, slug2)
        self.assertNotEqual(d1, d2)

    def test_unicode_key_nfc_normalized_deterministic(self):
        """Unicode key（NFC/NFD 差）は同一 store_dir に解決される。"""
        import unicodedata
        nfc = unicodedata.normalize('NFC', 'プラグイン')
        nfd = unicodedata.normalize('NFD', 'プラグイン')
        self.assertNotEqual(nfc, nfd)
        d_nfc = resolve_store_dir(nfc, project_root=self.root)
        d_nfd = resolve_store_dir(nfd, project_root=self.root)
        self.assertEqual(d_nfc, d_nfd)

    def test_reserved_key_all_resolves(self):
        """予約 key 'all' も決定的に解決される（resolve は検証しない）。"""
        d = resolve_store_dir(DEFAULT_KEY, project_root=self.root)
        self.assertTrue(d.name.startswith("all-"))


# ===========================================================================
# key 検証（DES-005 §3.3 / FR-N01-5）
# ===========================================================================

class TestKeyValidation(unittest.TestCase):
    """validate_user_key / is_reserved_key のテスト。"""

    def test_is_reserved_key_true(self):
        self.assertTrue(is_reserved_key("all"))

    def test_is_reserved_key_false(self):
        self.assertFalse(is_reserved_key("rules"))
        self.assertFalse(is_reserved_key(None))

    def test_empty_key_rejected(self):
        with self.assertRaises(KeyError_) as cm:
            validate_user_key("")
        self.assertEqual(cm.exception.error_code, ErrorCode.KEY_EMPTY)

    def test_whitespace_key_rejected_as_empty(self):
        with self.assertRaises(KeyError_) as cm:
            validate_user_key("   ")
        self.assertEqual(cm.exception.error_code, ErrorCode.KEY_EMPTY)

    def test_none_key_rejected_as_empty(self):
        with self.assertRaises(KeyError_) as cm:
            validate_user_key(None)
        self.assertEqual(cm.exception.error_code, ErrorCode.KEY_EMPTY)

    def test_explicit_all_rejected_as_reserved(self):
        with self.assertRaises(KeyError_) as cm:
            validate_user_key("all")
        self.assertEqual(cm.exception.error_code, ErrorCode.KEY_RESERVED)

    def test_normal_key_accepted(self):
        self.assertEqual(validate_user_key("rules"), "rules")

    def test_long_unicode_key_accepted(self):
        """過長 / Unicode key は reject されない（吸収される）。"""
        long_unicode = "仕様" * 100
        result = validate_user_key(long_unicode)
        self.assertTrue(result)  # 例外を投げない


# ===========================================================================
# emit_json（DES-005 §8 / FR-N08）
# ===========================================================================

class TestEmitJson(unittest.TestCase):
    """emit_json の JSON 契約テスト。"""

    def _emit(self, *args, **kwargs):
        buf = io.StringIO()
        emit_json(*args, stream=buf, **kwargs)
        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 1, "stdout は単一 JSON でなければならない")
        return json.loads(lines[0])

    def test_status_and_error_code_required(self):
        """status / error_code は必須フィールド。"""
        obj = self._emit(STATUS_OK, error_code=None)
        self.assertIn("status", obj)
        self.assertIn("error_code", obj)
        self.assertEqual(obj["status"], STATUS_OK)
        self.assertIsNone(obj["error_code"])

    def test_status_enum_valid(self):
        obj = self._emit(STATUS_ERROR, error_code=ErrorCode.KEY_EMPTY)
        self.assertIn(obj["status"], STATUSES)

    def test_error_code_enum_valid(self):
        obj = self._emit(STATUS_ERROR, error_code=ErrorCode.KEY_RESERVED)
        self.assertIn(obj["error_code"], ERROR_CODES)

    def test_optional_fields_only_when_given(self):
        """指定しないフィールドは出力されない。"""
        obj = self._emit(STATUS_OK, error_code=None)
        for f in ("message", "key", "toc_path", "normalized_paths",
                  "rejected_paths", "counts", "warnings"):
            self.assertNotIn(f, obj)

    def test_optional_fields_emitted(self):
        obj = self._emit(
            STATUS_OK, error_code=None, key="rules",
            toc_path="x/toc.yaml", counts={"added": 1},
        )
        self.assertEqual(obj["key"], "rules")
        self.assertEqual(obj["toc_path"], "x/toc.yaml")
        self.assertEqual(obj["counts"], {"added": 1})

    def test_error_codes_enum_fixed(self):
        """error_code enum の集合を固定する（FR-N08-2）。"""
        expected = {
            "INVALID_PATH", "PATH_TRAVERSAL", "ABSOLUTE_PATH", "OUTSIDE_ROOT",
            "NOT_FOUND", "NOT_MARKDOWN", "KEY_EMPTY", "KEY_RESERVED",
            "TOC_NOT_FOUND", "NO_TARGETS", "UNSUPPORTED_ARG",
        }
        self.assertEqual(set(ERROR_CODES), expected)

    def test_status_enum_fixed(self):
        self.assertEqual(
            set(STATUSES), {"ok", "error", "partial", "needs_confirmation"}
        )


# ===========================================================================
# promote / clean（in-process / DES-005 §4.1）
# ===========================================================================

class TestPromoteAndClean(unittest.TestCase):
    """promote_pending / clean_work_dir の冪等動作テスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_dir = Path(self.tmpdir) / "store"
        self.work_dir = self.store_dir / toc_store.WORK_DIRNAME

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_pending(self, content="checksums:\n  rules/a.md: abc123\n"):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        pending = self.work_dir / toc_store.PENDING_CHECKSUMS_FILENAME
        with open(pending, "w", encoding="utf-8") as f:
            f.write(content)

    def test_promote_copies_pending(self):
        self._make_pending()
        self.assertTrue(promote_pending(self.store_dir))
        checksums = self.store_dir / toc_store.CHECKSUMS_FILENAME
        self.assertTrue(checksums.exists())
        self.assertIn("abc123", checksums.read_text(encoding="utf-8"))

    def test_promote_fails_without_pending(self):
        self.assertFalse(promote_pending(self.store_dir))

    def test_clean_removes_work_dir(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "dummy.yaml").write_text("x", encoding="utf-8")
        self.assertTrue(clean_work_dir(self.store_dir))
        self.assertFalse(self.work_dir.exists())

    def test_clean_idempotent_when_absent(self):
        """work dir 不在でも冪等に成功する。"""
        self.assertFalse(self.work_dir.exists())
        self.assertTrue(clean_work_dir(self.store_dir))


# ===========================================================================
# work_status（index-docs Step 0/2 の決定論判定 / Issue #22 A1）
# ===========================================================================

class TestWorkStatus(unittest.TestCase):
    """work_status の継続判定・pending 列挙・completed/error 分類テスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.store_dir = self.root / "store"
        self.work_dir = self.store_dir / toc_store.WORK_DIRNAME

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_entry(self, name, *, status="pending", source_file="rules/a.md",
                     error_message=None):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        lines = ["_meta:", f"  source_file: {source_file}", f"  status: {status}"]
        if error_message is not None:
            lines.append(f"  error_message: {error_message}")
        lines.append("title: T")
        (self.work_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_no_work_dir_means_prepare(self):
        r = work_status(self.store_dir, self.root)
        self.assertFalse(r["has_work_dir"])
        self.assertEqual(r["next_action"], "prepare")
        self.assertEqual(r["pending"], [])

    def test_pending_means_fill_and_lists_entry_files(self):
        self._write_entry("aaa.yaml", status="pending", source_file="rules/a.md")
        self._write_entry("bbb.yaml", status="completed", source_file="rules/b.md")
        r = work_status(self.store_dir, self.root)
        self.assertTrue(r["has_work_dir"])
        self.assertEqual(r["next_action"], "fill")
        self.assertEqual(r["completed"], 1)
        # entry_file は project-root 相対で列挙される
        self.assertEqual(r["pending"], ["store/.toc_work/aaa.yaml"])

    def test_all_completed_means_merge(self):
        self._write_entry("aaa.yaml", status="completed")
        self._write_entry("bbb.yaml", status="completed")
        r = work_status(self.store_dir, self.root)
        self.assertEqual(r["next_action"], "merge")
        self.assertEqual(r["completed"], 2)
        self.assertEqual(r["pending"], [])

    def test_error_pending_classified_and_not_blocking_merge(self):
        self._write_entry("aaa.yaml", status="completed")
        self._write_entry("err.yaml", status="pending",
                          error_message="extraction failed")
        r = work_status(self.store_dir, self.root)
        self.assertEqual(r["completed"], 1)
        self.assertEqual(len(r["error_pending"]), 1)
        self.assertEqual(r["error_pending"][0]["entry_file"], "store/.toc_work/err.yaml")
        self.assertEqual(r["pending"], [])
        # 充填可能 pending が無いので merge へ（error は試行済み）
        self.assertEqual(r["next_action"], "merge")

    def test_hidden_files_excluded(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / toc_store.PENDING_CHECKSUMS_FILENAME).write_text(
            "checksums: {}\n", encoding="utf-8")
        (self.work_dir / ".deleted.json").write_text("[]", encoding="utf-8")
        r = work_status(self.store_dir, self.root)
        # 隠しファイルは entry でないため pending/completed に数えない → merge
        self.assertEqual(r["pending"], [])
        self.assertEqual(r["completed"], 0)
        self.assertEqual(r["next_action"], "merge")


# ===========================================================================
# CLI（subprocess JSON 契約 / DES-005 §8）
# ===========================================================================

class TestCli(unittest.TestCase):
    """toc_store.py CLI の JSON 契約テスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir
        os.makedirs(os.path.join(self.tmpdir, '.git'), exist_ok=True)
        self._original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self._original_env[key] = os.environ.get(key)
        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self._original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run(self, *args):
        cmd = [sys.executable, TOC_STORE_SCRIPT] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )

    def _parse_stdout(self, proc):
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        # 単一 JSON
        self.assertEqual(len(out.split("\n")), 1, f"stdout must be single JSON: {out}")
        return json.loads(out)

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=Path(self.project_root))

    def test_explicit_all_rejected_key_reserved(self):
        """--key all は KEY_RESERVED で reject される。"""
        proc = self._run('--key', 'all', '--clean-work-dir')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertEqual(obj["error_code"], "KEY_RESERVED")

    def test_empty_key_rejected(self):
        """空 key は KEY_EMPTY で reject される。"""
        proc = self._run('--key', '', '--clean-work-dir')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "KEY_EMPTY")

    def test_no_action_rejected(self):
        """アクション未指定は NO_TARGETS で error。"""
        proc = self._run('--key', 'rules')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["error_code"], "NO_TARGETS")

    def test_all_flag_resolves_reserved_key(self):
        """--all は予約 key 'all' に解決し reject されない（clean は冪等成功）。"""
        proc = self._run('--all', '--clean-work-dir')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertEqual(obj["key"], "all")

    def test_key_omitted_resolves_reserved_key(self):
        """--key 省略でも予約 key 'all' に解決する。"""
        proc = self._run('--clean-work-dir')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["key"], "all")

    def test_clean_idempotent(self):
        """--clean-work-dir は work dir 不在でも成功する。"""
        proc = self._run('--key', 'rules', '--clean-work-dir')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")

    def test_promote_copies_pending_via_cli(self):
        """--promote-pending が pending を active checksums に昇格する。"""
        store_dir = self._store_dir("rules")
        work_dir = store_dir / toc_store.WORK_DIRNAME
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / toc_store.PENDING_CHECKSUMS_FILENAME).write_text(
            "checksums:\n  rules/a.md: deadbeef\n", encoding="utf-8"
        )
        proc = self._run('--key', 'rules', '--promote-pending')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        checksums = store_dir / toc_store.CHECKSUMS_FILENAME
        self.assertTrue(checksums.exists())
        self.assertIn("deadbeef", checksums.read_text(encoding="utf-8"))

    def test_promote_fails_without_pending_via_cli(self):
        """pending 不在の --promote-pending は error 終了。"""
        proc = self._run('--key', 'rules', '--promote-pending')
        self.assertNotEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")

    def test_toc_path_in_output(self):
        """成功時の JSON に toc_path が含まれる。"""
        proc = self._run('--key', 'rules', '--clean-work-dir')
        obj = self._parse_stdout(proc)
        self.assertIn("toc_path", obj)
        self.assertIn(STORE_ROOT_REL, obj["toc_path"])
        self.assertTrue(obj["toc_path"].endswith("toc.yaml"))


if __name__ == '__main__':
    unittest.main()
