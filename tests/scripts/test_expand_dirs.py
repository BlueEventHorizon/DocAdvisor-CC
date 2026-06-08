#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""expand_dirs.py のユニットテスト（FR-N09 / REQ-001 NFR-N03）。

テスト対象:
- 通常展開（ディレクトリ内 Markdown が列挙される）
- --exclude-json でファイル・サブディレクトリを除外
- --paths-json との併用・重複除去
- システム固定除外（node_modules 等）が常時適用される
- 不在ディレクトリが rejected_dirs に列挙される（処理継続）
- root 外 symlink は prepare_toc.py の承認フローに渡される
- JSON 出力契約（status / paths / rejected_dirs / warnings）
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

from expand_dirs import expand

EXPAND_SCRIPT = os.path.join(SCRIPTS_DIR, 'expand_dirs.py')
PREPARE_SCRIPT = os.path.join(SCRIPTS_DIR, 'prepare_toc.py')


# ===========================================================================
# 共通基盤
# ===========================================================================

class ExpandTestBase(unittest.TestCase):
    """一時 project root と subprocess 実行ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_md(self, rel_path, content='# Title\n\nBody.\n'):
        full = self.project_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
        return full

    def _run(self, *args):
        cmd = [sys.executable, EXPAND_SCRIPT] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.project_root), env=env)

    def _run_prepare(self, *args):
        cmd = [sys.executable, PREPARE_SCRIPT] + list(args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = SCRIPTS_DIR
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.project_root), env=env)

    def _parse_stdout(self, proc):
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        return json.loads(out)


# ===========================================================================
# expand() in-process テスト
# ===========================================================================

class TestExpandBasic(ExpandTestBase):
    """基本的な展開動作。"""

    def test_single_dir_returns_markdown_files(self):
        """ディレクトリ内の Markdown ファイルが列挙される。"""
        self._write_md("docs/a.md")
        self._write_md("docs/b.md")
        result = expand(["docs/"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertIn("docs/b.md", result["paths"])
        self.assertEqual(result["rejected_dirs"], [])

    def test_non_markdown_files_not_included(self):
        """Markdown 以外（.txt, .py 等）は含まれない。"""
        self._write_md("docs/a.md")
        (self.project_root / "docs/b.txt").write_text("text", encoding="utf-8")
        result = expand(["docs/"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertNotIn("docs/b.txt", result["paths"])

    def test_nested_dirs_included(self):
        """サブディレクトリの Markdown も再帰的に含まれる。"""
        self._write_md("docs/sub/c.md")
        result = expand(["docs/"], project_root=self.project_root)
        self.assertIn("docs/sub/c.md", result["paths"])

    def test_multiple_dirs(self):
        """複数ディレクトリを同時指定できる。"""
        self._write_md("rules/r.md")
        self._write_md("specs/s.md")
        result = expand(["rules/", "specs/"], project_root=self.project_root)
        self.assertIn("rules/r.md", result["paths"])
        self.assertIn("specs/s.md", result["paths"])

    def test_paths_sorted(self):
        """出力パスは昇順ソート。"""
        self._write_md("docs/b.md")
        self._write_md("docs/a.md")
        result = expand(["docs/"], project_root=self.project_root)
        self.assertEqual(result["paths"], sorted(result["paths"]))

    def test_empty_dir_returns_empty_paths(self):
        """空ディレクトリは空リストを返す（エラーにしない）。"""
        (self.project_root / "empty").mkdir()
        result = expand(["empty/"], project_root=self.project_root)
        self.assertEqual(result["paths"], [])
        self.assertEqual(result["rejected_dirs"], [])


# ===========================================================================
# exclude テスト
# ===========================================================================

class TestExpandExclude(ExpandTestBase):
    """除外動作のテスト。"""

    def test_exclude_file(self):
        """--exclude-json で特定ファイルを除外できる。"""
        self._write_md("docs/keep.md")
        self._write_md("docs/drop.md")
        result = expand(["docs/"], exclude_json=["docs/drop.md"], project_root=self.project_root)
        self.assertIn("docs/keep.md", result["paths"])
        self.assertNotIn("docs/drop.md", result["paths"])

    def test_exclude_subdirectory(self):
        """--exclude-json でサブディレクトリを除外できる。"""
        self._write_md("docs/main.md")
        self._write_md("docs/draft/wip.md")
        result = expand(["docs/"], exclude_json=["docs/draft"], project_root=self.project_root)
        self.assertIn("docs/main.md", result["paths"])
        self.assertNotIn("docs/draft/wip.md", result["paths"])

    def test_exclude_trailing_slash_normalized(self):
        """--exclude-json の末尾スラッシュは正規化される。"""
        self._write_md("docs/keep.md")
        self._write_md("docs/draft/wip.md")
        result = expand(["docs/"], exclude_json=["docs/draft/"], project_root=self.project_root)
        self.assertNotIn("docs/draft/wip.md", result["paths"])

    def test_system_exclude_always_applied(self):
        """SYSTEM_EXCLUDE_PATTERNS は --exclude-json 指定なしでも常時適用される。"""
        self._write_md("docs/a.md")
        (self.project_root / "node_modules").mkdir()
        self._write_md("node_modules/pkg.md")
        result = expand(["docs/", "node_modules/"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertNotIn("node_modules/pkg.md", result["paths"])

    def test_system_exclude_applied_even_with_user_exclude(self):
        """--exclude-json を指定してもシステム固定除外は機能する。"""
        self._write_md("docs/a.md")
        (self.project_root / "node_modules").mkdir()
        self._write_md("node_modules/pkg.md")
        result = expand(["docs/", "node_modules/"], exclude_json=["docs/draft/"], project_root=self.project_root)
        self.assertNotIn("node_modules/pkg.md", result["paths"])

    def test_exclude_bare_name_matches_any_level(self):
        """裸名は任意階層のディレクトリ名にマッチする（Issue #30: should_exclude と統一）。"""
        self._write_md("docs/specs/forge/plan/roadmap.md")
        self._write_md("docs/specs/base/design/d.md")
        result = expand(["docs/"], exclude_json=["plan"], project_root=self.project_root)
        self.assertIn("docs/specs/base/design/d.md", result["paths"])
        self.assertNotIn("docs/specs/forge/plan/roadmap.md", result["paths"])

    def test_exclude_bare_name_does_not_match_filename(self):
        """裸名はファイル名にはマッチしない（'plan' が 'planning.md' を除外しない）。"""
        self._write_md("docs/planning.md")
        self._write_md("docs/deployment_plan.md")
        result = expand(["docs/"], exclude_json=["plan"], project_root=self.project_root)
        self.assertIn("docs/planning.md", result["paths"])
        self.assertIn("docs/deployment_plan.md", result["paths"])

    def test_exclude_path_pattern_segment_boundary(self):
        """'/' 含みパターンはセグメント境界でマッチし、前方部分一致で誤爆しない。"""
        self._write_md("docs/specs/keep.md")
        self._write_md("docs/spec/drop.md")
        # パターン 'docs/spec' は 'docs/specs/...' に誤爆せず、'docs/spec/...' のみ除外する
        result = expand(["docs/"], exclude_json=["docs/spec"], project_root=self.project_root)
        self.assertIn("docs/specs/keep.md", result["paths"])
        self.assertNotIn("docs/spec/drop.md", result["paths"])


# ===========================================================================
# --paths-json 併用テスト
# ===========================================================================

class TestExpandWithPathsJson(ExpandTestBase):
    """--paths-json との結合・重複除去。"""

    def test_paths_json_merged(self):
        """--paths-json のファイルが結果に含まれる。"""
        self._write_md("docs/a.md")
        self._write_md("extra.md")
        result = expand(["docs/"], paths_json=["extra.md"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertIn("extra.md", result["paths"])

    def test_duplicate_paths_deduplicated(self):
        """--dirs-json 展開と --paths-json が重複していても1件になる。"""
        self._write_md("docs/a.md")
        result = expand(["docs/"], paths_json=["docs/a.md"], project_root=self.project_root)
        self.assertEqual(result["paths"].count("docs/a.md"), 1)

    def test_paths_json_without_dirs_json(self):
        """--dirs-json に空リストを渡し --paths-json のみでも動作する。"""
        self._write_md("docs/a.md")
        result = expand([], paths_json=["docs/a.md"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])


# ===========================================================================
# rejected_dirs テスト
# ===========================================================================

class TestRejectedDirs(ExpandTestBase):
    """不正なディレクトリ指定の処理。"""

    def test_missing_dir_in_rejected_dirs(self):
        """不在ディレクトリは rejected_dirs に列挙され、処理は継続する。"""
        self._write_md("docs/a.md")
        result = expand(["docs/", "missing/"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        rejected = [r["dir"] for r in result["rejected_dirs"]]
        self.assertIn("missing/", rejected)

    def test_file_as_dir_rejected(self):
        """ファイルをディレクトリとして指定すると rejected_dirs に列挙される。"""
        self._write_md("docs/a.md")
        result = expand(["docs/a.md"], project_root=self.project_root)
        rejected = [r["dir"] for r in result["rejected_dirs"]]
        self.assertIn("docs/a.md", rejected)

    def test_absolute_path_rejected(self):
        """絶対パスのディレクトリ指定は rejected_dirs に列挙される。"""
        result = expand(["/tmp"], project_root=self.project_root)
        self.assertEqual(len(result["rejected_dirs"]), 1)


# ===========================================================================
# symlink テスト
# ===========================================================================

class TestSymlinks(ExpandTestBase):
    """root 外 symlink は後段の承認フローに渡す。"""

    def test_file_symlink_outside_root_passed_to_prepare(self):
        """root 外を指す file symlink は論理 path のまま展開される。"""
        outside = Path(tempfile.mkdtemp()).resolve()
        try:
            target = outside / "secret.md"
            target.write_text("# secret\n\nBody.\n", encoding="utf-8")
            (self.project_root / "docs").mkdir()
            link = self.project_root / "docs" / "link.md"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            result = expand(["docs/"], project_root=self.project_root)
            self.assertIn("docs/link.md", result["paths"])
            self.assertEqual(result["warnings"], [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_dir_symlink_outside_root_passed_to_prepare(self):
        """root 外を指す directory symlink 配下の Markdown も論理 path で展開される。"""
        outside = Path(tempfile.mkdtemp()).resolve()
        try:
            target = outside / "secret.md"
            target.write_text("# secret\n\nBody.\n", encoding="utf-8")
            (self.project_root / "docs").mkdir()
            link = self.project_root / "docs" / "external"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            result = expand(["docs/"], project_root=self.project_root)
            self.assertIn("docs/external/secret.md", result["paths"])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_external_symlink_dir_can_be_dirs_json_root(self):
        """--dirs-json が外部 symlink ディレクトリ自体でも traversal reject せず展開する。"""
        outside = Path(tempfile.mkdtemp()).resolve()
        try:
            target = outside / "secret.md"
            target.write_text("# secret\n\nBody.\n", encoding="utf-8")
            link = self.project_root / "external"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")
            result = expand(["external/"], project_root=self.project_root)
            self.assertIn("external/secret.md", result["paths"])
            self.assertEqual(result["rejected_dirs"], [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_expanded_external_symlink_triggers_prepare_confirmation(self):
        """展開結果を prepare_toc.py に渡すと needs_confirmation になる。"""
        outside = Path(tempfile.mkdtemp()).resolve()
        try:
            target = outside / "secret.md"
            target.write_text("# secret\n\nBody.\n", encoding="utf-8")
            (self.project_root / "docs").mkdir()
            link = self.project_root / "docs" / "external"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not supported")

            expanded = expand(["docs/"], project_root=self.project_root)
            proc = self._run_prepare(
                "--key", "rules",
                "--paths-json", json.dumps(expanded["paths"]),
            )
            self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
            obj = self._parse_stdout(proc)
            self.assertEqual(obj["status"], "needs_confirmation")
            self.assertEqual(obj["external_pending"][0]["symlink"], "docs/external")
        finally:
            shutil.rmtree(outside, ignore_errors=True)


# ===========================================================================
# グロブパターンテスト（FR-N09-2）
# ===========================================================================

class TestExpandGlob(ExpandTestBase):
    """--dirs-json のグロブメタ文字（* ? [）展開。"""

    def test_dir_glob_matches_multiple_dirs(self):
        """docs/specs/**/design/ が任意深さの design/ にマッチし配下を収集する。"""
        self._write_md("docs/specs/base/design/DES-001.md")
        self._write_md("docs/specs/common/design/COMMON-DES-001.md")
        self._write_md("docs/specs/base/requirements/REQ-001.md")  # design 外
        result = expand(["docs/specs/**/design/"], project_root=self.project_root)
        self.assertIn("docs/specs/base/design/DES-001.md", result["paths"])
        self.assertIn("docs/specs/common/design/COMMON-DES-001.md", result["paths"])
        self.assertNotIn("docs/specs/base/requirements/REQ-001.md", result["paths"])
        self.assertEqual(result["rejected_dirs"], [])

    def test_dir_glob_recurses_matched_dir(self):
        """グロブでマッチしたディレクトリ配下はサブディレクトリも再帰収集する。"""
        self._write_md("docs/specs/base/design/sub/nested.md")
        result = expand(["docs/specs/**/design/"], project_root=self.project_root)
        self.assertIn("docs/specs/base/design/sub/nested.md", result["paths"])

    def test_file_glob_matches_markdown_directly(self):
        """docs/**/*.md がファイルに直接マッチして採用される。"""
        self._write_md("docs/a.md")
        self._write_md("docs/sub/b.md")
        (self.project_root / "docs/c.txt").write_text("text", encoding="utf-8")
        result = expand(["docs/**/*.md"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertIn("docs/sub/b.md", result["paths"])
        self.assertNotIn("docs/c.txt", result["paths"])

    def test_single_star_matches_direct_children_only(self):
        """docs/*/design/ は直下1階層の design のみ（** ではない）。"""
        self._write_md("docs/base/design/d.md")
        self._write_md("docs/x/y/design/deep.md")
        result = expand(["docs/*/design/"], project_root=self.project_root)
        self.assertIn("docs/base/design/d.md", result["paths"])
        self.assertNotIn("docs/x/y/design/deep.md", result["paths"])

    def test_glob_no_match_returns_empty_with_warning(self):
        """マッチ無しグロブは空 paths + warning（エラーにしない）。"""
        self._write_md("docs/a.md")
        result = expand(["docs/specs/**/design/"], project_root=self.project_root)
        self.assertEqual(result["paths"], [])
        self.assertEqual(result["rejected_dirs"], [])
        self.assertTrue(any("design" in w for w in result["warnings"]))

    def test_glob_with_traversal_rejected(self):
        """'..' を含むグロブは rejected_dirs に列挙される。"""
        self._write_md("docs/a.md")
        result = expand(["../**/*.md"], project_root=self.project_root)
        rejected = [r["dir"] for r in result["rejected_dirs"]]
        self.assertIn("../**/*.md", rejected)

    def test_absolute_glob_rejected(self):
        """絶対パスのグロブは rejected_dirs に列挙される。"""
        result = expand(["/tmp/**/*.md"], project_root=self.project_root)
        rejected = [r["dir"] for r in result["rejected_dirs"]]
        self.assertIn("/tmp/**/*.md", rejected)

    def test_glob_respects_user_exclude(self):
        """グロブ収集にも --exclude-json が適用される。"""
        self._write_md("docs/specs/base/design/keep.md")
        self._write_md("docs/specs/base/design/drop.md")
        result = expand(
            ["docs/specs/**/design/"],
            exclude_json=["docs/specs/base/design/drop.md"],
            project_root=self.project_root,
        )
        self.assertIn("docs/specs/base/design/keep.md", result["paths"])
        self.assertNotIn("docs/specs/base/design/drop.md", result["paths"])

    def test_glob_respects_bare_name_exclude(self):
        """グロブ収集でも裸名は任意階層のディレクトリ名にマッチする。"""
        self._write_md("docs/specs/base/design/keep.md")
        self._write_md("docs/specs/base/design/drafts/drop.md")
        result = expand(
            ["docs/specs/**/design/"],
            exclude_json=["drafts"],
            project_root=self.project_root,
        )
        self.assertIn("docs/specs/base/design/keep.md", result["paths"])
        self.assertNotIn("docs/specs/base/design/drafts/drop.md", result["paths"])

    def test_glob_respects_system_exclude(self):
        """グロブが node_modules 等にマッチしてもシステム固定除外が効く。"""
        self._write_md("node_modules/pkg/design/x.md")
        self._write_md("docs/base/design/y.md")
        result = expand(["**/design/"], project_root=self.project_root)
        self.assertIn("docs/base/design/y.md", result["paths"])
        self.assertNotIn("node_modules/pkg/design/x.md", result["paths"])

    def test_glob_and_literal_dir_combined(self):
        """グロブと従来のリテラルディレクトリを同一 --dirs-json に混在できる。"""
        self._write_md("docs/specs/base/design/d.md")
        self._write_md("docs/rules/r.md")
        result = expand(
            ["docs/specs/**/design/", "docs/rules/"],
            project_root=self.project_root,
        )
        self.assertIn("docs/specs/base/design/d.md", result["paths"])
        self.assertIn("docs/rules/r.md", result["paths"])

    def test_glob_dedup_with_paths_json(self):
        """グロブ展開結果と --paths-json が重複しても1件に集約される。"""
        self._write_md("docs/a.md")
        result = expand(
            ["docs/**/*.md"],
            paths_json=["docs/a.md"],
            project_root=self.project_root,
        )
        self.assertEqual(result["paths"].count("docs/a.md"), 1)

    def test_literal_dir_with_bracket_not_treated_as_glob_when_missing(self):
        """グロブメタ無しの通常ディレクトリは従来どおりリテラル扱い（回帰）。"""
        self._write_md("docs/a.md")
        result = expand(["docs/"], project_root=self.project_root)
        self.assertIn("docs/a.md", result["paths"])
        self.assertEqual(result["rejected_dirs"], [])


# ===========================================================================
# CLI subprocess テスト
# ===========================================================================

class TestExpandCli(ExpandTestBase):
    """CLI（subprocess）の JSON 契約テスト。"""

    def test_cli_basic(self):
        """CLI が正常に動作し status:ok を返す。"""
        self._write_md("docs/a.md")
        proc = self._run("--dirs-json", '["docs/"]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertIn("docs/a.md", obj["paths"])

    def test_cli_with_exclude(self):
        """CLI で --exclude-json が機能する。"""
        self._write_md("docs/keep.md")
        self._write_md("docs/drop.md")
        proc = self._run("--dirs-json", '["docs/"]', "--exclude-json", '["docs/drop.md"]')
        self.assertEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertIn("docs/keep.md", obj["paths"])
        self.assertNotIn("docs/drop.md", obj["paths"])

    def test_cli_invalid_json(self):
        """--dirs-json が不正 JSON の場合 status:error を返す。"""
        proc = self._run("--dirs-json", "not-json")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "error")
        self.assertEqual(obj["error_code"], "INVALID_JSON")

    def test_cli_stdout_is_single_line_json(self):
        """stdout は改行なしの単一 JSON。"""
        self._write_md("docs/a.md")
        proc = self._run("--dirs-json", '["docs/"]')
        lines = [l for l in proc.stdout.strip().split("\n") if l]
        self.assertEqual(len(lines), 1)
        json.loads(lines[0])

    def test_cli_dir_glob(self):
        """CLI で --dirs-json のグロブが展開される。"""
        self._write_md("docs/specs/base/design/d.md")
        self._write_md("docs/specs/common/design/c.md")
        proc = self._run("--dirs-json", '["docs/specs/**/design/"]')
        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertIn("docs/specs/base/design/d.md", obj["paths"])
        self.assertIn("docs/specs/common/design/c.md", obj["paths"])

    def test_cli_rejected_dirs_in_output(self):
        """不在ディレクトリが rejected_dirs に含まれる。"""
        self._write_md("docs/a.md")
        proc = self._run("--dirs-json", '["docs/", "missing/"]')
        self.assertEqual(proc.returncode, 0)
        obj = self._parse_stdout(proc)
        self.assertEqual(obj["status"], "ok")
        self.assertIn("docs/a.md", obj["paths"])
        rejected = [r["dir"] for r in obj["rejected_dirs"]]
        self.assertIn("missing/", rejected)


if __name__ == "__main__":
    unittest.main()
