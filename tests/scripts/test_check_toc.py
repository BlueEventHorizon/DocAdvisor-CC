#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_toc.py のユニットテスト（REQ-005 / DES-009 §8）。

テスト対象:
- judge（FR-C02 の 5 判定・境界値・skew 内外の未来時刻・age_seconds の丸め）
- parse_generated_at（Z 付き UTC / offset 付き / tz なし / 空 / 非日時）
- read_toc_metadata（docs: 到達で打ち切ること。docs 以降が壊れていても成功すること）
- parse_args / resolve_max_age（--max-age 不正・未知引数の拒否）
- main（JSON 契約・exit code・ToC 不在時の status=ok・読み取り不能時の error）
- 副作用なし（実行後に ToC / .toc_work / checksums が変化しない）

テスト方針:
- 判定は in-process import（judge / parse_generated_at は純関数のため実時刻に依存しない）
- 判定時刻は main(argv, now=...) で注入し、実時刻へ依存させない（NFR-C03）
- CLI 契約（status / error_code / freshness / exit code）は subprocess で確認する
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from check_toc import (
    ArgError,
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    FUTURE_SKEW,
    REASON_GENERATED_AT_FUTURE,
    REASON_GENERATED_AT_INVALID,
    REASON_MISSING,
    REASON_OUTDATED,
    judge,
    main,
    parse_args,
    parse_generated_at,
    read_toc_metadata,
    resolve_max_age,
)
from toc_store import (
    ERROR_CODES,
    STATUSES,
    STATUS_ERROR,
    STATUS_OK,
    ErrorCode,
    resolve_store_dir,
)

CHECK_TOC_SCRIPT = os.path.join(SCRIPTS_DIR, 'check_toc.py')

# 判定の基準時刻（固定。実時刻に依存させない）
NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
DAY = 86400

SAMPLE_TOC_YAML = """\
# .claude/.doc-advisor/toc/<slug>/toc.yaml
# Auto-generated - Do not edit directly

metadata:
  name: Sample ToC
  key: docs
  generated_at: 2026-07-29T00:00:00Z
  file_count: 1

docs:
  docs/a.md:
    title: A Doc
    purpose: alpha purpose
"""


# ===========================================================================
# judge（FR-C02）
# ===========================================================================

class JudgeTest(unittest.TestCase):

    def test_within_max_age_is_fresh(self):
        generated_at = NOW - timedelta(seconds=100)
        freshness, reason, age = judge(generated_at, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_FRESH)
        self.assertIsNone(reason)
        self.assertEqual(age, 100)

    def test_boundary_equal_to_max_age_is_fresh(self):
        """境界値（差 = max_age）は fresh（FR-C02-4）。"""
        generated_at = NOW - timedelta(seconds=DAY)
        freshness, reason, age = judge(generated_at, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_FRESH)
        self.assertIsNone(reason)
        self.assertEqual(age, DAY)

    def test_one_second_over_max_age_is_stale(self):
        generated_at = NOW - timedelta(seconds=DAY + 1)
        freshness, reason, age = judge(generated_at, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_STALE)
        self.assertEqual(reason, REASON_OUTDATED)
        self.assertEqual(age, DAY + 1)

    def test_unparsable_generated_at_is_stale(self):
        freshness, reason, age = judge(None, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_STALE)
        self.assertEqual(reason, REASON_GENERATED_AT_INVALID)
        self.assertIsNone(age)

    def test_future_within_skew_is_fresh_with_age_zero(self):
        """skew 内の未来時刻は fresh。age_seconds は 0 へ丸める（DES-009 §4.2）。"""
        generated_at = NOW + timedelta(seconds=30)
        freshness, reason, age = judge(generated_at, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_FRESH)
        self.assertIsNone(reason)
        self.assertEqual(age, 0)

    def test_future_beyond_skew_is_stale(self):
        generated_at = NOW + FUTURE_SKEW + timedelta(seconds=1)
        freshness, reason, age = judge(generated_at, NOW, DAY)
        self.assertEqual(freshness, FRESHNESS_STALE)
        self.assertEqual(reason, REASON_GENERATED_AT_FUTURE)
        self.assertLess(age, 0)

    def test_skew_is_sixty_seconds(self):
        """許容 skew の値を固定する（REQ-005 TBD-C01 の確定値）。"""
        self.assertEqual(FUTURE_SKEW, timedelta(seconds=60))


# ===========================================================================
# parse_generated_at（DES-009 §4.3）
# ===========================================================================

class ParseGeneratedAtTest(unittest.TestCase):

    def test_utc_z_suffix(self):
        parsed = parse_generated_at("2026-07-29T00:00:00Z")
        self.assertEqual(parsed, datetime(2026, 7, 29, tzinfo=timezone.utc))

    def test_offset_suffix(self):
        parsed = parse_generated_at("2026-07-29T09:00:00+09:00")
        self.assertEqual(parsed, datetime(2026, 7, 29, tzinfo=timezone.utc))

    def test_naive_is_treated_as_utc(self):
        parsed = parse_generated_at("2026-07-29T00:00:00")
        self.assertEqual(parsed, datetime(2026, 7, 29, tzinfo=timezone.utc))

    def test_empty_and_none(self):
        self.assertIsNone(parse_generated_at(""))
        self.assertIsNone(parse_generated_at("   "))
        self.assertIsNone(parse_generated_at(None))

    def test_non_datetime_text(self):
        self.assertIsNone(parse_generated_at("not-a-datetime"))


# ===========================================================================
# read_toc_metadata（NFR-C02 / DES-009 §2.3）
# ===========================================================================

class ReadTocMetadataTest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, content):
        path = Path(self.tmpdir) / "toc.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_reads_metadata_scalars(self):
        metadata = read_toc_metadata(self._write(SAMPLE_TOC_YAML))
        self.assertEqual(metadata["key"], "docs")
        self.assertEqual(metadata["generated_at"], "2026-07-29T00:00:00Z")
        self.assertEqual(metadata["file_count"], "1")

    def test_stops_at_docs_section(self):
        """docs: 到達で打ち切るため、docs 配下のキーは metadata に混入しない。"""
        metadata = read_toc_metadata(self._write(SAMPLE_TOC_YAML))
        self.assertNotIn("title", metadata)
        self.assertNotIn("purpose", metadata)

    def test_succeeds_even_if_docs_section_is_broken(self):
        """docs: 以降が壊れていても判定は成立する（打ち切りの観測可能な検証）。"""
        broken = SAMPLE_TOC_YAML + "\n  : : : not valid yaml : : :\n\t\x00broken\n"
        metadata = read_toc_metadata(self._write(broken))
        self.assertEqual(metadata["generated_at"], "2026-07-29T00:00:00Z")

    def test_missing_metadata_block(self):
        metadata = read_toc_metadata(self._write("docs:\n  docs/a.md:\n    title: A\n"))
        self.assertEqual(metadata, {})


# ===========================================================================
# 引数（FR-C01）
# ===========================================================================

class ArgsTest(unittest.TestCase):

    def test_resolve_max_age_accepts_positive_int(self):
        self.assertEqual(resolve_max_age("86400"), DAY)
        self.assertEqual(resolve_max_age(" 60 "), 60)

    def test_resolve_max_age_rejects_invalid(self):
        for raw in (None, "", "abc", "0", "-1", "1.5"):
            with self.subTest(raw=raw):
                self.assertIsNone(resolve_max_age(raw))

    def test_parse_args_accepts_key_and_all(self):
        args = parse_args(["--key", "specs", "--max-age", "86400"])
        self.assertEqual(args.key, "specs")
        self.assertFalse(args.all)
        args = parse_args(["--all", "--max-age", "86400"])
        self.assertTrue(args.all)

    def test_parse_args_rejects_unknown_argument(self):
        """未知の引数は ArgError（SystemExit ではない / FR-C01-4）。"""
        with self.assertRaises(ArgError):
            parse_args(["--key", "specs", "--max-age", "86400",
                        "--paths", "docs/a.md"])

    def test_parse_args_rejects_key_with_all(self):
        """--key と --all は排他（--all が黙って優先されるのを防ぐ）。"""
        with self.assertRaises(ArgError):
            parse_args(["--key", "specs", "--all", "--max-age", "86400"])

    def test_parse_args_rejects_missing_value(self):
        with self.assertRaises(ArgError):
            parse_args(["--key", "specs", "--max-age"])


# ===========================================================================
# CLI（FR-C03 / 副作用なし）
# ===========================================================================

class MainTest(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        os.makedirs(self.project_root / '.git', exist_ok=True)
        self._prev_cwd = os.getcwd()
        self._prev_env = os.environ.get('CLAUDE_PROJECT_DIR')
        os.environ['CLAUDE_PROJECT_DIR'] = str(self.project_root)

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self._prev_env
        os.chdir(self._prev_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _write_toc(self, key, content=SAMPLE_TOC_YAML):
        store_dir = self._store_dir(key)
        store_dir.mkdir(parents=True, exist_ok=True)
        toc_path = store_dir / "toc.yaml"
        toc_path.write_text(content, encoding="utf-8")
        return toc_path

    def _main(self, argv, now=NOW):
        """main を in-process 実行し (exit_code, payload) を返す。"""
        buf = io.StringIO()
        prev = sys.stdout
        sys.stdout = buf
        try:
            code = main(argv, now=now)
        finally:
            sys.stdout = prev
        return code, json.loads(buf.getvalue())

    def test_fresh(self):
        self._write_toc("docs")
        code, obj = self._main(["--key", "docs", "--max-age", str(DAY)])
        self.assertEqual(code, 0)
        self.assertEqual(obj["status"], STATUS_OK)
        self.assertIsNone(obj["error_code"])
        self.assertEqual(obj["freshness"], FRESHNESS_FRESH)
        self.assertIsNone(obj["reason"])
        self.assertEqual(obj["generated_at"], "2026-07-29T00:00:00Z")
        self.assertEqual(obj["age_seconds"], 12 * 3600)
        self.assertEqual(obj["max_age_seconds"], DAY)
        self.assertEqual(obj["key"], "docs")

    def test_stale_outdated(self):
        self._write_toc("docs")
        code, obj = self._main(["--key", "docs", "--max-age", "60"])
        self.assertEqual(code, 0)
        self.assertEqual(obj["status"], STATUS_OK)
        self.assertEqual(obj["freshness"], FRESHNESS_STALE)
        self.assertEqual(obj["reason"], REASON_OUTDATED)

    def test_missing_toc_is_ok_and_stale(self):
        """ToC 不在は error ではない（FR-C03-3）。"""
        code, obj = self._main(["--key", "absent", "--max-age", str(DAY)])
        self.assertEqual(code, 0)
        self.assertEqual(obj["status"], STATUS_OK)
        self.assertIsNone(obj["error_code"])
        self.assertEqual(obj["freshness"], FRESHNESS_STALE)
        self.assertEqual(obj["reason"], REASON_MISSING)
        self.assertIsNone(obj["generated_at"])
        self.assertIsNone(obj["age_seconds"])
        self.assertTrue(obj["toc_path"].endswith("toc.yaml"))

    def test_generated_at_invalid_is_stale(self):
        self._write_toc("docs", SAMPLE_TOC_YAML.replace(
            "2026-07-29T00:00:00Z", "not-a-datetime"))
        code, obj = self._main(["--key", "docs", "--max-age", str(DAY)])
        self.assertEqual(code, 0)
        self.assertEqual(obj["freshness"], FRESHNESS_STALE)
        self.assertEqual(obj["reason"], REASON_GENERATED_AT_INVALID)
        self.assertIsNone(obj["generated_at"])

    def test_invalid_max_age(self):
        code, obj = self._main(["--key", "docs", "--max-age", "0"])
        self.assertEqual(code, 1)
        self.assertEqual(obj["status"], STATUS_ERROR)
        self.assertEqual(obj["error_code"], ErrorCode.INVALID_MAX_AGE)

    def test_missing_max_age(self):
        code, obj = self._main(["--key", "docs"])
        self.assertEqual(code, 1)
        self.assertEqual(obj["error_code"], ErrorCode.INVALID_MAX_AGE)

    def test_reserved_key_rejected(self):
        code, obj = self._main(["--key", "all", "--max-age", str(DAY)])
        self.assertEqual(code, 1)
        self.assertEqual(obj["status"], STATUS_ERROR)
        self.assertEqual(obj["error_code"], ErrorCode.KEY_RESERVED)

    def test_all_mode_resolves_reserved_key(self):
        code, obj = self._main(["--all", "--max-age", str(DAY)])
        self.assertEqual(code, 0)
        self.assertEqual(obj["key"], "all")
        self.assertEqual(obj["freshness"], FRESHNESS_STALE)
        self.assertEqual(obj["reason"], REASON_MISSING)

    def test_read_error(self):
        """toc.yaml がディレクトリ等で読めない場合は TOC_READ_ERROR。"""
        store_dir = self._store_dir("docs")
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "toc.yaml").mkdir()
        code, obj = self._main(["--key", "docs", "--max-age", str(DAY)])
        self.assertEqual(code, 1)
        self.assertEqual(obj["status"], STATUS_ERROR)
        self.assertEqual(obj["error_code"], ErrorCode.TOC_READ_ERROR)

    def test_json_contract(self):
        """status / error_code は enum の値域に収まる。"""
        self._write_toc("docs")
        _, obj = self._main(["--key", "docs", "--max-age", str(DAY)])
        self.assertIn(obj["status"], STATUSES)
        self.assertIn(obj["error_code"], set(ERROR_CODES) | {None})

    def test_no_side_effects(self):
        """実行後に ToC / .toc_work / checksums が変化しない（FR-C04-3）。"""
        toc_path = self._write_toc("docs")
        before = toc_path.read_text(encoding="utf-8")
        store_dir = self._store_dir("docs")
        entries_before = sorted(p.name for p in store_dir.iterdir())

        self._main(["--key", "docs", "--max-age", str(DAY)])

        self.assertEqual(toc_path.read_text(encoding="utf-8"), before)
        self.assertEqual(sorted(p.name for p in store_dir.iterdir()), entries_before)

    def test_subprocess_exit_code_and_stdout(self):
        """CLI として単一 JSON を stdout に出し、exit code が status に対応する。"""
        self._write_toc("docs")
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR

        proc = subprocess.run(
            [sys.executable, CHECK_TOC_SCRIPT, "--key", "docs", "--max-age", str(DAY)],
            capture_output=True, text=True, env=env, cwd=str(self.project_root),
        )
        self.assertEqual(proc.returncode, 0)
        obj = json.loads(proc.stdout)
        self.assertEqual(obj["status"], STATUS_OK)
        self.assertIn(obj["freshness"], (FRESHNESS_FRESH, FRESHNESS_STALE))

        proc = subprocess.run(
            [sys.executable, CHECK_TOC_SCRIPT, "--key", "docs", "--max-age", "bad"],
            capture_output=True, text=True, env=env, cwd=str(self.project_root),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["error_code"], ErrorCode.INVALID_MAX_AGE)

    def test_subprocess_argparse_errors_are_json(self):
        """未知引数・排他違反も stdout の単一 JSON と exit code 1 に正規化する。

        argparse 既定の stderr + exit code 2 は「常に JSON を返す」契約
        （FR-C03 / SKILL の出力契約）を破るため、subprocess 経路で固定する。
        """
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR

        cases = (
            ["--key", "docs", "--max-age", "60", "--unexpected"],
            ["--key", "docs", "--all", "--max-age", "60"],
            ["--key", "docs", "--max-age"],
            # --help は add_help=False で無効化済み。help テキストを stdout へ出して
            # exit 0 する経路を作らない（FR-C03-4）
            ["--help"],
            ["-h"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                proc = subprocess.run(
                    [sys.executable, CHECK_TOC_SCRIPT] + argv,
                    capture_output=True, text=True, env=env,
                    cwd=str(self.project_root),
                )
                self.assertEqual(proc.returncode, 1)
                obj = json.loads(proc.stdout)
                self.assertEqual(obj["status"], STATUS_ERROR)
                self.assertEqual(obj["error_code"], ErrorCode.UNSUPPORTED_ARG)
                self.assertNotIn("freshness", obj)


if __name__ == '__main__':
    unittest.main()
