#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_structure 廃止契約の回帰防止テスト（Issue #15 / REQ-001 / DES-005 §13・§14）。

doc-advisor を key + path 汎用 ToC Provider へ移行し、`.doc_structure.yaml` と
category（rules/specs）固定の探索・分類ロジックを clean break で全廃した
（REQ-001 §6.2 / 受け入れ基準「doc_structure 廃止」）。

本テストは、通常実行経路（scripts/ 配下の deterministic script 層）に
doc_structure 依存が再混入していないことを **静的に** 検査する。
既存の embedding-removal 回帰テスト（test_no_embedding_residue.py）の
静的検査スタイルを踏襲する（DES-005 §13: base からの継続）。

検査対象（再混入を防ぐ削除契約）:
- 通常経路スクリプトが `.doc_structure.yaml` を open / 参照しない
- 通常経路スクリプトが doc_structure 探索・config 分岐関数
  （find_config_file / load_config / init_common_config）を呼ばない
- 削除済み関数 / 例外（load_config / find_config_file / init_common_config /
  ConfigNotReadyError）が toc_utils.py に存在しない

検査対象外:
- `.claude/` 配下のローカル限定 skill。配布物でも通常実行経路でもない
  （CLAUDE.md: `.claude/` 配下はテスト対象外）。
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 通常実行経路を構成する deterministic script 層（DES-005 §4.1）。
# これらは key + paths を直接受け取り、.doc_structure.yaml を読まない。
NORMAL_PATH_SCRIPTS = [
    "toc_utils.py",
    "toc_store.py",
    "prepare_toc.py",
    "merge_toc.py",
    "get_toc.py",
    "remove_toc.py",
    "write_pending.py",
    "validate_toc.py",
]

# 通常経路スクリプトに残ってはならない doc_structure 由来の語。
# - `.doc_structure.yaml`: 廃止した config ファイル名（通常経路で読まない）
# - find_config_file / load_config / init_common_config: 廃止した探索・分岐関数
#   （REQ-001 §6.2 / DES-005 §4.2）
# - ConfigNotReadyError: doc_structure 未整備時の例外（廃止）
DOC_STRUCTURE_FORBIDDEN = [
    ".doc_structure.yaml",
    "find_config_file",
    "load_config",
    "init_common_config",
    "ConfigNotReadyError",
]

# toc_utils.py に定義が残ってはならない削除済みシンボル（DES-005 §4.2）。
REMOVED_TOC_UTILS_SYMBOLS = [
    "find_config_file",
    "load_config",
    "init_common_config",
    "ConfigNotReadyError",
]


class TestNoDocStructureResidue(unittest.TestCase):
    """doc_structure 廃止契約が守られていることを検査する。"""

    def test_normal_path_scripts_have_no_doc_structure_refs(self):
        """通常経路スクリプトに doc_structure 由来の語が残っていない。"""
        for name in NORMAL_PATH_SCRIPTS:
            path = REPO_ROOT / "scripts" / name
            self.assertTrue(
                path.exists(),
                f"通常経路スクリプト {name} が存在しない: {path}",
            )
            body = path.read_text(encoding="utf-8")
            for forbidden in DOC_STRUCTURE_FORBIDDEN:
                self.assertNotIn(
                    forbidden,
                    body,
                    f"scripts/{name} に doc_structure 由来の語 '{forbidden}' が残っている",
                )

    def test_toc_utils_has_no_removed_config_symbols(self):
        """toc_utils.py に削除済み関数 / 例外の定義が残っていない。"""
        body = (REPO_ROOT / "scripts" / "toc_utils.py").read_text(encoding="utf-8")
        for symbol in REMOVED_TOC_UTILS_SYMBOLS:
            # 関数定義 / クラス定義どちらの形でも残存させない。
            self.assertNotIn(
                f"def {symbol}",
                body,
                f"toc_utils.py に削除済み関数 'def {symbol}' が残っている",
            )
            self.assertNotIn(
                f"class {symbol}",
                body,
                f"toc_utils.py に削除済みクラス 'class {symbol}' が残っている",
            )

    def test_all_scripts_have_no_doc_structure_file_ref(self):
        """scripts/ 配下の全 .py が `.doc_structure.yaml` を参照しない。

        通常経路リストの網羅性に依存せず、scripts/ 全体で config ファイルの
        再混入を防ぐ（将来スクリプトが追加されても保護される）。
        """
        for path in (REPO_ROOT / "scripts").glob("*.py"):
            body = path.read_text(encoding="utf-8")
            self.assertNotIn(
                ".doc_structure.yaml",
                body,
                f"scripts/{path.name} に '.doc_structure.yaml' 参照が残っている",
            )


if __name__ == "__main__":
    unittest.main()
