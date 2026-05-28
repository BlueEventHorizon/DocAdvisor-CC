#!/usr/bin/env python3
"""select_backend.py のユニットテスト。

DES-001 §2.3 分岐テーブル A/B、§1.5.1 API キー判定式、§5.1 エラーメッセージを
ゴールデン網羅する。read-only 性は tmp ディレクトリの checksum で確認する。

実行:
  python3 -m unittest tests.forge.scripts.test_backend_selection -v
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / "plugins" / "forge" / "scripts" / "backend_selection"
SCRIPT_PATH = SCRIPT_DIR / "select_backend.py"

sys.path.insert(0, str(SCRIPT_DIR))

from select_backend import (  # noqa: E402
    BACKEND_NOT_FOUND_ERROR,
    SKILL_TABLE,
    build_result,
    has_api_key,
    main,
    parse_available,
    select_backend,
)


# DES-001 §5.1 のエラーメッセージ全文。ここを契約として固定する。
EXPECTED_ERROR_MESSAGE = (
    "ERROR: 文書検索バックエンドが見つかりません\n"
    "       doc-db または doc-advisor のいずれかをインストールしてください\n"
    "\n"
    "       /plugin install doc-db@bw-cc-plugins\n"
    "       /plugin install doc-advisor@bw-cc-plugins"
)


class TestParseAvailable(unittest.TestCase):
    """parse_available: CSV → set 変換"""

    def test_empty_string(self):
        self.assertEqual(parse_available(""), set())

    def test_single(self):
        self.assertEqual(parse_available("doc-db"), {"doc-db"})

    def test_multiple(self):
        self.assertEqual(
            parse_available("doc-db,doc-advisor"), {"doc-db", "doc-advisor"}
        )

    def test_strip_whitespace(self):
        self.assertEqual(
            parse_available(" doc-db , doc-advisor "), {"doc-db", "doc-advisor"}
        )

    def test_drop_empty_tokens(self):
        self.assertEqual(parse_available("doc-db,,"), {"doc-db"})
        self.assertEqual(parse_available(",,"), set())


class TestHasApiKey(unittest.TestCase):
    """DES-001 §1.5.1 API キー判定式"""

    def test_neither_set(self):
        self.assertFalse(has_api_key({}))

    def test_both_empty_string(self):
        self.assertFalse(
            has_api_key({"OPENAI_API_DOCDB_KEY": "", "OPENAI_API_KEY": ""})
        )

    def test_only_docdb_set(self):
        self.assertTrue(has_api_key({"OPENAI_API_DOCDB_KEY": "sk-xxx"}))

    def test_only_api_set(self):
        self.assertTrue(has_api_key({"OPENAI_API_KEY": "sk-xxx"}))

    def test_docdb_empty_api_set(self):
        # DOCDB が空でも API_KEY が有効ならフォールバックで True
        self.assertTrue(
            has_api_key({"OPENAI_API_DOCDB_KEY": "", "OPENAI_API_KEY": "sk-xxx"})
        )

    def test_docdb_set_api_empty(self):
        self.assertTrue(
            has_api_key({"OPENAI_API_DOCDB_KEY": "sk-xxx", "OPENAI_API_KEY": ""})
        )

    def test_both_set(self):
        self.assertTrue(
            has_api_key({"OPENAI_API_DOCDB_KEY": "sk-a", "OPENAI_API_KEY": "sk-b"})
        )

    def test_default_reads_os_environ(self):
        # 引数省略時は os.environ を読む。値は環境依存だが bool 評価が落ちないこと。
        result = has_api_key()
        self.assertIsInstance(result, bool)


class TestSelectBackend(unittest.TestCase):
    """DES-001 §2.3 分岐テーブル A: 採用バックエンド決定 (5 行)"""

    def test_both_with_api_key_picks_doc_db(self):
        self.assertEqual(
            select_backend({"doc-db", "doc-advisor"}, api_key_present=True), "doc-db"
        )

    def test_both_without_api_key_picks_doc_advisor(self):
        self.assertEqual(
            select_backend({"doc-db", "doc-advisor"}, api_key_present=False),
            "doc-advisor",
        )

    def test_only_doc_db(self):
        # API キー有無に依らず doc-db
        self.assertEqual(select_backend({"doc-db"}, api_key_present=True), "doc-db")
        self.assertEqual(select_backend({"doc-db"}, api_key_present=False), "doc-db")

    def test_only_doc_advisor(self):
        self.assertEqual(
            select_backend({"doc-advisor"}, api_key_present=True), "doc-advisor"
        )
        self.assertEqual(
            select_backend({"doc-advisor"}, api_key_present=False), "doc-advisor"
        )

    def test_neither_returns_none(self):
        self.assertIsNone(select_backend(set(), api_key_present=True))
        self.assertIsNone(select_backend(set(), api_key_present=False))


class TestBuildResultSkillTable(unittest.TestCase):
    """DES-001 §2.3 分岐テーブル B: 8 行ゴールデン (backend × category × operation)"""

    # (available, api_key, category, operation) → (backend, skill)
    # skill 値は plugin:skill 形式 (スラッシュなし)。Skill ツール呼出時にそのまま渡す。
    GOLDEN = [
        # doc-db 採用パス (両方あり + API キー、または doc-db 単独)
        (
            {"doc-db", "doc-advisor"},
            True,
            "rules",
            "query",
            "doc-db",
            "doc-db:query",
        ),
        (
            {"doc-db", "doc-advisor"},
            True,
            "specs",
            "query",
            "doc-db",
            "doc-db:query",
        ),
        (
            {"doc-db", "doc-advisor"},
            True,
            "rules",
            "update",
            "doc-db",
            "doc-db:build-index",
        ),
        (
            {"doc-db", "doc-advisor"},
            True,
            "specs",
            "update",
            "doc-db",
            "doc-db:build-index",
        ),
        # doc-advisor 採用パス (両方あり + API キーなし)
        (
            {"doc-db", "doc-advisor"},
            False,
            "rules",
            "query",
            "doc-advisor",
            "doc-advisor:query-rules",
        ),
        (
            {"doc-db", "doc-advisor"},
            False,
            "specs",
            "query",
            "doc-advisor",
            "doc-advisor:query-specs",
        ),
        (
            {"doc-db", "doc-advisor"},
            False,
            "rules",
            "update",
            "doc-advisor",
            "doc-advisor:create-rules-toc",
        ),
        (
            {"doc-db", "doc-advisor"},
            False,
            "specs",
            "update",
            "doc-advisor",
            "doc-advisor:create-specs-toc",
        ),
    ]

    def test_skill_table_size(self):
        # 分岐テーブル B は 8 行ちょうど (2 backends × 2 categories × 2 operations)
        self.assertEqual(len(SKILL_TABLE), 8)

    def test_golden_paths(self):
        for available, api_key, category, operation, exp_backend, exp_skill in (
            self.GOLDEN
        ):
            with self.subTest(
                available=available,
                api_key=api_key,
                category=category,
                operation=operation,
            ):
                result = build_result(available, category, operation, api_key)
                self.assertEqual(result["backend"], exp_backend)
                self.assertEqual(result["skill"], exp_skill)
                self.assertIsNone(result["error"])

    def test_single_backend_doc_db(self):
        # doc-db 単独でも分岐テーブル B の 4 行を満たす
        for category in ("rules", "specs"):
            for operation in ("query", "update"):
                result = build_result({"doc-db"}, category, operation, False)
                self.assertEqual(result["backend"], "doc-db")
                self.assertEqual(
                    result["skill"], SKILL_TABLE[("doc-db", category, operation)]
                )
                self.assertIsNone(result["error"])

    def test_single_backend_doc_advisor(self):
        for category in ("rules", "specs"):
            for operation in ("query", "update"):
                result = build_result({"doc-advisor"}, category, operation, True)
                self.assertEqual(result["backend"], "doc-advisor")
                self.assertEqual(
                    result["skill"],
                    SKILL_TABLE[("doc-advisor", category, operation)],
                )
                self.assertIsNone(result["error"])


class TestErrorMessage(unittest.TestCase):
    """DES-001 §5.1 エラーメッセージ完全一致"""

    def test_constant_matches_spec(self):
        self.assertEqual(BACKEND_NOT_FOUND_ERROR, EXPECTED_ERROR_MESSAGE)

    def test_build_result_error_path(self):
        result = build_result(set(), "rules", "query", api_key_present=True)
        self.assertIsNone(result["backend"])
        self.assertIsNone(result["skill"])
        self.assertEqual(result["error"], EXPECTED_ERROR_MESSAGE)

    def test_error_independent_of_category_operation(self):
        # バックエンド不在のときは category / operation に依らず同じエラー
        for category in ("rules", "specs"):
            for operation in ("query", "update"):
                with self.subTest(category=category, operation=operation):
                    result = build_result(set(), category, operation, False)
                    self.assertEqual(result["error"], EXPECTED_ERROR_MESSAGE)


class TestCli(unittest.TestCase):
    """main / CLI 経由の JSON 出力契約"""

    def _run(self, *args, env=None):
        proc_env = os.environ.copy()
        # API キー判定のテストでは環境を明示制御
        proc_env.pop("OPENAI_API_DOCDB_KEY", None)
        proc_env.pop("OPENAI_API_KEY", None)
        if env:
            proc_env.update(env)
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            env=proc_env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result

    def test_cli_doc_db_with_api_key(self):
        result = self._run(
            "--available",
            "doc-db,doc-advisor",
            "--category",
            "rules",
            "--operation",
            "query",
            env={"OPENAI_API_DOCDB_KEY": "sk-test"},
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "doc-db")
        self.assertEqual(payload["skill"], "doc-db:query")
        self.assertIsNone(payload["error"])

    def test_cli_doc_advisor_without_api_key(self):
        result = self._run(
            "--available",
            "doc-db,doc-advisor",
            "--category",
            "specs",
            "--operation",
            "update",
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "doc-advisor")
        self.assertEqual(payload["skill"], "doc-advisor:create-specs-toc")

    def test_cli_backend_missing_emits_full_error(self):
        result = self._run(
            "--available",
            "",
            "--category",
            "rules",
            "--operation",
            "query",
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["backend"])
        self.assertIsNone(payload["skill"])
        self.assertEqual(payload["error"], EXPECTED_ERROR_MESSAGE)

    def test_cli_rejects_invalid_category(self):
        result = self._run(
            "--available",
            "doc-db",
            "--category",
            "unknown",
            "--operation",
            "query",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cli_rejects_invalid_operation(self):
        result = self._run(
            "--available",
            "doc-db",
            "--category",
            "rules",
            "--operation",
            "delete",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_main_returns_zero(self):
        rc = main(
            [
                "--available",
                "doc-db",
                "--category",
                "rules",
                "--operation",
                "query",
            ]
        )
        self.assertEqual(rc, 0)


class TestReadOnly(unittest.TestCase):
    """read-only 性: tmp ディレクトリのファイル増減・チェックサム不変を確認"""

    @staticmethod
    def _snapshot(root: Path) -> dict[str, str]:
        snap: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                snap[str(path.relative_to(root))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return snap

    def test_no_writes_during_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # seed file: 実行で改変されていないことの基準
            seed = root / "seed.txt"
            seed.write_text("seed", encoding="utf-8")

            before = self._snapshot(root)

            original_cwd = os.getcwd()
            try:
                os.chdir(root)
                for category in ("rules", "specs"):
                    for operation in ("query", "update"):
                        rc = main(
                            [
                                "--available",
                                "doc-db,doc-advisor",
                                "--category",
                                category,
                                "--operation",
                                operation,
                            ]
                        )
                        self.assertEqual(rc, 0)
                # エラーパスでも書き込まない
                rc = main(
                    [
                        "--available",
                        "",
                        "--category",
                        "rules",
                        "--operation",
                        "query",
                    ]
                )
                self.assertEqual(rc, 0)
            finally:
                os.chdir(original_cwd)

            after = self._snapshot(root)
            self.assertEqual(
                before, after, "select_backend.py が tmp ディレクトリを変更している"
            )


if __name__ == "__main__":
    unittest.main()
