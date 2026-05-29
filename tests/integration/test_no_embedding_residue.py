#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Embedding 削除契約の回帰防止テスト（Issue #13）。

doc-advisor から Embedding 検索機能を削除し ToC 専用に戻した（Issue #13）。
本テストは、Embedding 関連の実装・設定・ドキュメントが active tree に
再混入していないことを静的に検査する。

検査対象（再混入を防ぐ削除契約）:
- Embedding 関連スクリプトが存在しない
- query_index_workflow.md が存在しない
- toc_utils.py に index_file 設定面が残っていない
- query-* SKILL に --index / --toc / auto モード / embedding / API key 記述がない
- plugin.json の keywords に embedding がない
- ランタイム文書（workflows / formats）に Embedding スクリプト参照がない

Embedding 実装は今後 query-docs プラグイン側で再構築予定（bw-cc-plugins#77）。
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Embedding 実行経路を構成していたスクリプト（削除済み）
EMBEDDING_SCRIPTS = [
    "embed_docs.py",
    "search_docs.py",
    "embedding_api.py",
    "grep_docs.py",
]

# Embedding スクリプトの basename 参照（拡張子なし）
EMBEDDING_SCRIPT_REFS = ["embed_docs", "search_docs", "embedding_api", "grep_docs"]

# query-* SKILL に残ってはならない Embedding / mode フラグ由来の語
QUERY_SKILL_FORBIDDEN = [
    "--index",
    "--toc",
    "auto モード",
    "embedding",
    "Embedding",
    "semantic",
    "セマンティック",
    "OPENAI",
]

QUERY_SKILLS = ["query-rules", "query-specs"]


class TestNoEmbeddingResidue(unittest.TestCase):
    """Embedding 削除契約が守られていることを検査する。"""

    def test_embedding_scripts_absent(self):
        """Embedding 関連スクリプトが scripts/ に存在しない。"""
        for name in EMBEDDING_SCRIPTS:
            path = REPO_ROOT / "scripts" / name
            self.assertFalse(
                path.exists(),
                f"Embedding スクリプト {name} が再混入している: {path}",
            )

    def test_code_index_dir_absent(self):
        """旧 code_index/ ディレクトリが存在しない。"""
        self.assertFalse(
            (REPO_ROOT / "scripts" / "code_index").exists(),
            "scripts/code_index/ が再混入している",
        )

    def test_index_workflow_absent(self):
        """Embedding 検索ワークフローが存在しない。"""
        self.assertFalse(
            (REPO_ROOT / "workflows" / "query_index_workflow.md").exists(),
            "workflows/query_index_workflow.md が再混入している",
        )

    def test_toc_utils_has_no_index_file(self):
        """toc_utils.py に index_file 設定面が残っていない。"""
        content = (REPO_ROOT / "scripts" / "toc_utils.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "index_file",
            content,
            "toc_utils.py に index_file 設定面（Embedding index 由来）が残っている",
        )

    def test_query_skills_have_no_embedding_flags(self):
        """query-* SKILL に Embedding / mode フラグ記述がない。"""
        for skill in QUERY_SKILLS:
            body = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            for forbidden in QUERY_SKILL_FORBIDDEN:
                self.assertNotIn(
                    forbidden,
                    body,
                    f"skills/{skill}/SKILL.md に Embedding 由来の語 '{forbidden}' が残っている",
                )

    def test_plugin_manifest_keywords_have_no_embedding(self):
        """plugin.json の keywords に embedding がない。"""
        data = json.loads(
            (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        keywords = data.get("keywords", [])
        self.assertNotIn(
            "embedding",
            keywords,
            "plugin.json の keywords に 'embedding' が残っている",
        )

    def test_runtime_docs_have_no_embedding_script_refs(self):
        """ランタイム文書（workflows / formats）に Embedding スクリプト参照がない。"""
        for subdir in ("workflows", "formats"):
            for path in (REPO_ROOT / subdir).glob("*.md"):
                body = path.read_text(encoding="utf-8")
                for ref in EMBEDDING_SCRIPT_REFS:
                    self.assertNotIn(
                        ref,
                        body,
                        f"{subdir}/{path.name} に Embedding スクリプト参照 '{ref}' が残っている",
                    )

    def test_scripts_have_no_embedding_script_refs(self):
        """残存スクリプトが Embedding スクリプトを参照していない。"""
        for path in (REPO_ROOT / "scripts").glob("*.py"):
            body = path.read_text(encoding="utf-8")
            for ref in EMBEDDING_SCRIPT_REFS:
                # 自分自身のファイル名は対象外（該当ファイルは削除済みのため通常起きない）
                self.assertNotIn(
                    ref,
                    body,
                    f"scripts/{path.name} に Embedding スクリプト参照 '{ref}' が残っている",
                )


if __name__ == "__main__":
    unittest.main()
