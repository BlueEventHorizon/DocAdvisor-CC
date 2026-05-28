#!/usr/bin/env python3
"""
output_dir リダイレクションの E2E テスト。

swap-doc-config SKILL で .doc_structure.yaml を差し替えると、doc-advisor の
スクリプト群（filter_toc.py / search_docs.py 等）が **新しい設定の** ToC・Index
パスを参照することを検証する。

検証戦略:
1. tmpdir を擬似プロジェクトルート (CLAUDE_PROJECT_DIR) として用意
2. 「元の」.doc_structure.yaml と、「差し替える」設定 YAML を配置
3. 両方の出力先（既定の .claude/doc-advisor/ と output_dir 指定先）に **異なる内容の**
   ToC YAML を事前配置する
4. swap-doc-config --store → filter_toc.py を実行 → 差し替え先の ToC が読まれることを確認
5. swap-doc-config --restore → filter_toc.py を実行 → 既定先の ToC が読まれることを確認
6. search_docs.py についても、新 Index パスを参照していることを Index 不在エラーで確認

これにより:
- `output_dir` の効果が runtime で機能していること
- swap が確かに doc-advisor スクリプトの挙動を変えること
- restore が確かに元の挙動に戻すこと
を SKILL の境界（CLI）越しに検証する。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SWAP_SCRIPT = REPO_ROOT / ".claude" / "skills" / "swap-doc-config" / "scripts" / "swap_doc_config.py"
DOC_ADVISOR_SCRIPTS = REPO_ROOT / "plugins" / "doc-advisor" / "scripts"
FILTER_TOC = DOC_ADVISOR_SCRIPTS / "filter_toc.py"
SEARCH_DOCS = DOC_ADVISOR_SCRIPTS / "search_docs.py"

TEMP_BASE = Path(__file__).resolve().parent / ".temp"


ORIGINAL_DOC_STRUCTURE = """\
# doc_structure_version: 3.0
rules:
  root_dirs:
    - default_rules/
  doc_types_map:
    default_rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""

REDIRECTED_DOC_STRUCTURE = """\
# doc_structure_version: 3.0
rules:
  output_dir: test_outputs/
  root_dirs:
    - test_docs/rules/
  doc_types_map:
    test_docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""

DEFAULT_TOC_YAML = """\
# Default location ToC (.claude/doc-advisor/toc/rules/rules_toc.yaml)
metadata:
  name: Default ToC
  file_count: 1
docs:
  default_rules/from_default.md:
    doc_type: rule
    title: From Default Location
    purpose: Identifies the default ToC location
    keywords:
      - default
"""

REDIRECTED_TOC_YAML = """\
# Redirected location ToC (test_outputs/toc/rules/rules_toc.yaml)
metadata:
  name: Redirected ToC
  file_count: 1
docs:
  test_docs/rules/from_redirect.md:
    doc_type: rule
    title: From Redirected Location
    purpose: Identifies the output_dir redirected ToC location
    keywords:
      - redirected
"""


class OutputDirRedirectionBase(unittest.TestCase):
    """擬似プロジェクトルートに 2 つの ToC を配置して swap で参照先を切替える共通基盤。"""

    def setUp(self):
        TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(tempfile.mkdtemp(dir=str(TEMP_BASE)))
        (self.project_root / ".git").mkdir()  # get_project_root() 判定用

        # root_dirs が参照するディレクトリ実体を作成
        (self.project_root / "default_rules").mkdir()
        (self.project_root / "default_rules" / "from_default.md").write_text(
            "# From Default Location\n\nDummy content.\n", encoding="utf-8"
        )
        (self.project_root / "test_docs" / "rules").mkdir(parents=True)
        (self.project_root / "test_docs" / "rules" / "from_redirect.md").write_text(
            "# From Redirected Location\n\nDummy content.\n", encoding="utf-8"
        )

        # 既定の ToC を .claude/doc-advisor/toc/rules/ に配置
        default_toc = (
            self.project_root
            / ".claude" / "doc-advisor" / "toc" / "rules" / "rules_toc.yaml"
        )
        default_toc.parent.mkdir(parents=True)
        default_toc.write_text(DEFAULT_TOC_YAML, encoding="utf-8")

        # 差し替え先 ToC を test_outputs/toc/rules/ に配置
        redirected_toc = (
            self.project_root
            / "test_outputs" / "toc" / "rules" / "rules_toc.yaml"
        )
        redirected_toc.parent.mkdir(parents=True)
        redirected_toc.write_text(REDIRECTED_TOC_YAML, encoding="utf-8")

        # 元の .doc_structure.yaml
        self.original_config = self.project_root / ".doc_structure.yaml"
        self.original_config.write_text(ORIGINAL_DOC_STRUCTURE, encoding="utf-8")

        # 差し替え用 YAML
        self.target_config = self.project_root / "redirected_doc_structure.yaml"
        self.target_config.write_text(REDIRECTED_DOC_STRUCTURE, encoding="utf-8")

        self.backup_dir = self.project_root / ".backup"

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _env(self):
        return {**os.environ, "CLAUDE_PROJECT_DIR": str(self.project_root)}

    def _swap(self, *args):
        return subprocess.run(
            [sys.executable, str(SWAP_SCRIPT), *args],
            capture_output=True, text=True,
            cwd=str(self.project_root), env=self._env(),
        )

    def _run_filter_toc(self, *paths):
        return subprocess.run(
            [sys.executable, str(FILTER_TOC),
             "--category", "rules",
             "--paths", ",".join(paths)],
            capture_output=True, text=True,
            cwd=str(self.project_root), env=self._env(),
        )

    def _run_search_docs(self, query):
        env = self._env()
        env["OPENAI_API_DOCDB_KEY"] = "fake-key"
        return subprocess.run(
            [sys.executable, str(SEARCH_DOCS),
             "--category", "rules",
             "--query", query,
             "--skip-stale-check"],
            capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )


class TestFilterTocFollowsOutputDir(OutputDirRedirectionBase):
    """filter_toc.py が swap 後/前で参照先 ToC を切替えること。"""

    def test_before_swap_reads_default_toc(self):
        """swap 前は既定 ToC を参照する。"""
        result = self._run_filter_toc("default_rules/from_default.md", "test_docs/rules/from_redirect.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        # 既定 ToC のエントリだけがヒットする
        self.assertIn("default_rules/from_default.md", result.stdout)
        self.assertNotIn("test_docs/rules/from_redirect.md:", result.stdout)
        # メタデータコメント or missing_paths でリダイレクト側エントリが「見つからない」扱い
        self.assertIn("missing_paths", result.stdout)
        self.assertIn("test_docs/rules/from_redirect.md", result.stdout)

    def test_after_store_reads_redirected_toc(self):
        """swap --store 後は output_dir 配下の ToC を参照する。"""
        r = self._swap(
            "--store",
            "--target", str(self.target_config),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

        result = self._run_filter_toc("default_rules/from_default.md", "test_docs/rules/from_redirect.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        # リダイレクト ToC のエントリだけがヒットする
        self.assertIn("test_docs/rules/from_redirect.md", result.stdout)
        self.assertNotIn("default_rules/from_default.md:", result.stdout)
        self.assertIn("missing_paths", result.stdout)
        self.assertIn("default_rules/from_default.md", result.stdout)

    def test_after_restore_reads_default_toc_again(self):
        """swap --restore 後は再び既定 ToC を参照する。"""
        r1 = self._swap(
            "--store",
            "--target", str(self.target_config),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertEqual(r2.returncode, 0, r2.stderr)

        result = self._run_filter_toc("default_rules/from_default.md", "test_docs/rules/from_redirect.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        # 再び既定 ToC が使われる
        self.assertIn("default_rules/from_default.md", result.stdout)
        self.assertNotIn("test_docs/rules/from_redirect.md:", result.stdout)


class TestSearchDocsFollowsOutputDir(OutputDirRedirectionBase):
    """search_docs.py が swap 後で新 Index パスを参照すること（Index 不在エラーで判定）。"""

    def setUp(self):
        super().setUp()
        # 既定 Index を .claude/doc-advisor/index/rules/ に配置
        # （内容は問わない — 「ここを見ていない」ことの証拠用）
        default_idx = (
            self.project_root
            / ".claude" / "doc-advisor" / "index" / "rules" / "rules_index.json"
        )
        default_idx.parent.mkdir(parents=True)
        default_idx.write_text(
            json.dumps({
                "metadata": {"model": "text-embedding-3-small"},
                "entries": {},
            }),
            encoding="utf-8",
        )

    def test_after_store_search_looks_at_redirected_index_path(self):
        """swap --store 後、search_docs は output_dir 配下の Index を探し、
        そこに Index が無いため「Index not found」を返す（既定 Index は読まない）。
        """
        r = self._swap(
            "--store",
            "--target", str(self.target_config),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(r.returncode, 0, r.stderr)

        # test_outputs/index/rules/ には Index を配置していない
        result = self._run_search_docs("test query")
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("Index not found", payload["error"])

    def test_before_swap_search_finds_default_index(self):
        """swap 前は既定 Index（空）を見つけて、Index 自体は読めるが
        他のエラー（モデル一致 / API キー判定など）に進む。

        ここでは Index 不在エラーに **ならない** ことだけ確認する
        （≒ 既定パスに到達できている）。
        """
        result = self._run_search_docs("test query")
        # status は error の可能性が高い（空 Index で API キー検証→検索結果なし等）が、
        # 「Index not found」エラーにはならない
        if result.returncode != 0:
            payload = json.loads(result.stdout)
            self.assertNotIn("Index not found", payload.get("error", ""))


class TestSwapDoesNotPolluteRealDocStructure(OutputDirRedirectionBase):
    """tmpdir 内で完結し、実 repo の .doc_structure.yaml は影響を受けない。"""

    def test_real_repo_doc_structure_untouched(self):
        real_config = REPO_ROOT / ".doc_structure.yaml"
        if not real_config.exists():
            self.skipTest("実 repo に .doc_structure.yaml が存在しないため検証不能")
        before = real_config.read_bytes()

        # store / 各種 script 実行 / restore のフルサイクル
        r1 = self._swap(
            "--store",
            "--target", str(self.target_config),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self._run_filter_toc("test_docs/rules/from_redirect.md")
        r2 = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertEqual(r2.returncode, 0, r2.stderr)

        after = real_config.read_bytes()
        self.assertEqual(before, after, "実 repo の .doc_structure.yaml が変更された")


if __name__ == "__main__":
    unittest.main()
