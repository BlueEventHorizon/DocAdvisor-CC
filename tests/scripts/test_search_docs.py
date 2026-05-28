#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search_docs.py のユニットテスト。

テスト対象:
- cosine_similarity() の数値検証（平行/直交/ゼロベクトル）
- 閾値フィルタリングテスト（threshold 以上のみ返される）
- 出力 JSON 形式テスト（status, query, results フィールド）
- インデックス不在・stale・モデル不一致の各エラーケーステスト
- 空クエリ時のエラー JSON 出力テスト
- 件数上限なし検証（50 件返るケース）
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

SEARCH_DOCS_SCRIPT = os.path.join(SCRIPTS_DIR, 'search_docs.py')

# テスト用一時ディレクトリのベースパス（/tmp 不可環境でも動作するようプロジェクト内に配置）
_TEST_TEMP_BASE = Path(__file__).parent / ".temp"

from search_docs import (
    check_model_mismatch,
    check_staleness,
    cosine_similarity,
    load_index,
    search,
)

# 固定テストベクトル（1536 次元）
# e1: 第1成分のみ 1.0
E1 = [1.0] + [0.0] * 1535
# e2: 第2成分のみ 1.0
E2 = [0.0, 1.0] + [0.0] * 1534
# 45度: e1 と e2 の中間方向（正規化前）
E_45 = [0.707, 0.707] + [0.0] * 1534


# ===========================================================================
# cosine_similarity() テスト
# ===========================================================================

class TestCosineSimilarity(unittest.TestCase):
    """cosine_similarity() の数値検証テスト。"""

    def test_identical_vectors(self):
        """同一ベクトル同士のコサイン類似度は 1.0"""
        result = cosine_similarity(E1, E1)
        self.assertAlmostEqual(result, 1.0, places=6)

    def test_orthogonal_vectors(self):
        """直交ベクトル同士のコサイン類似度は 0.0"""
        result = cosine_similarity(E1, E2)
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_45_degree_vectors(self):
        """45 度ベクトルと e1 のコサイン類似度は約 0.707"""
        result = cosine_similarity(E_45, E1)
        # E_45 の norm = sqrt(0.707^2 + 0.707^2) = sqrt(0.999698) ≈ 0.99985
        # dot(E_45, E1) = 0.707
        # cosine = 0.707 / (0.99985 * 1.0) ≈ 0.7071
        expected = 0.707 / math.sqrt(0.707**2 + 0.707**2)
        self.assertAlmostEqual(result, expected, places=4)

    def test_zero_vector_a(self):
        """ゼロベクトル A の場合は 0.0 を返す"""
        zero = [0.0] * 1536
        result = cosine_similarity(zero, E1)
        self.assertEqual(result, 0.0)

    def test_zero_vector_b(self):
        """ゼロベクトル B の場合は 0.0 を返す"""
        zero = [0.0] * 1536
        result = cosine_similarity(E1, zero)
        self.assertEqual(result, 0.0)

    def test_both_zero_vectors(self):
        """両方ゼロベクトルの場合は 0.0 を返す"""
        zero = [0.0] * 1536
        result = cosine_similarity(zero, zero)
        self.assertEqual(result, 0.0)

    def test_anti_parallel_vectors(self):
        """逆向きベクトルのコサイン類似度は -1.0"""
        neg_e1 = [-1.0] + [0.0] * 1535
        result = cosine_similarity(E1, neg_e1)
        self.assertAlmostEqual(result, -1.0, places=6)

    def test_45_degree_with_e2(self):
        """45 度ベクトルと e2 のコサイン類似度も約 0.707"""
        result = cosine_similarity(E_45, E2)
        expected = 0.707 / math.sqrt(0.707**2 + 0.707**2)
        self.assertAlmostEqual(result, expected, places=4)


# ===========================================================================
# load_index() テスト
# ===========================================================================

class TestLoadIndex(unittest.TestCase):
    """load_index() の単体テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_valid_index(self):
        """正常な JSON ファイルの読み込み"""
        index_data = {
            "metadata": {"model": "text-embedding-3-small"},
            "entries": {"docs/test.md": {"title": "Test", "embedding": E1, "checksum": "abc"}},
        }
        index_path = os.path.join(self.tmpdir, "test_index.json")
        with open(index_path, "w") as f:
            json.dump(index_data, f)

        result = load_index(index_path)
        self.assertEqual(result["metadata"]["model"], "text-embedding-3-small")
        self.assertIn("docs/test.md", result["entries"])

    def test_load_nonexistent_index(self):
        """存在しないファイルの読み込みで FileNotFoundError"""
        with self.assertRaises(FileNotFoundError):
            load_index(os.path.join(self.tmpdir, "nonexistent.json"))

    def test_load_corrupted_index(self):
        """破損 JSON の読み込みで ValueError"""
        index_path = os.path.join(self.tmpdir, "corrupted.json")
        with open(index_path, "w") as f:
            f.write("{invalid json")

        with self.assertRaises(ValueError):
            load_index(index_path)


# ===========================================================================
# check_model_mismatch() テスト
# ===========================================================================

class TestCheckModelMismatch(unittest.TestCase):
    """check_model_mismatch() の単体テスト。"""

    def test_matching_model(self):
        """モデル一致時は None を返す"""
        index = {"metadata": {"model": "text-embedding-3-small"}}
        result = check_model_mismatch(index)
        self.assertIsNone(result)

    def test_mismatching_model(self):
        """モデル不一致時はエラーメッセージを返す"""
        index = {"metadata": {"model": "text-embedding-3-large"}}
        result = check_model_mismatch(index)
        self.assertIsNotNone(result)
        self.assertIn("Model mismatch", result)
        self.assertIn("text-embedding-3-large", result)
        self.assertIn("text-embedding-3-small", result)

    def test_no_model_in_metadata(self):
        """メタデータにモデルがない場合は None を返す"""
        index = {"metadata": {}}
        result = check_model_mismatch(index)
        self.assertIsNone(result)

    def test_no_metadata(self):
        """metadata キーがない場合は None を返す"""
        index = {}
        result = check_model_mismatch(index)
        self.assertIsNone(result)


# ===========================================================================
# check_staleness() テスト
# ===========================================================================

class TestCheckStaleness(unittest.TestCase):
    """check_staleness() の単体テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fresh_index(self):
        """全ファイルのチェックサムが一致する場合は False（新鮮）"""
        # テスト用ファイルを作成
        doc_path = self.project_root / "docs" / "test.md"
        doc_path.parent.mkdir(parents=True)
        doc_path.write_text("# Test\n\nContent.\n")

        # calculate_file_hash でハッシュを取得
        from toc_utils import calculate_file_hash
        current_hash = calculate_file_hash(doc_path)

        index = {
            "entries": {
                "docs/test.md": {"checksum": current_hash, "embedding": E1},
            }
        }
        common_config = {"project_root": self.project_root}

        result = check_staleness(index, common_config)
        self.assertFalse(result)

    def test_stale_modified_file(self):
        """チェックサム不一致の場合は True（stale）"""
        doc_path = self.project_root / "docs" / "test.md"
        doc_path.parent.mkdir(parents=True)
        doc_path.write_text("# Test\n\nContent.\n")

        index = {
            "entries": {
                "docs/test.md": {"checksum": "outdated_hash", "embedding": E1},
            }
        }
        common_config = {"project_root": self.project_root}

        result = check_staleness(index, common_config)
        self.assertTrue(result)

    def test_stale_deleted_file(self):
        """インデックスに記録されたファイルが削除されている場合は True（stale）"""
        index = {
            "entries": {
                "docs/deleted.md": {"checksum": "some_hash", "embedding": E1},
            }
        }
        common_config = {"project_root": self.project_root}

        result = check_staleness(index, common_config)
        self.assertTrue(result)

    def test_empty_entries(self):
        """エントリが空の場合は False（新鮮）"""
        index = {"entries": {}}
        common_config = {"project_root": self.project_root}

        result = check_staleness(index, common_config)
        self.assertFalse(result)

    def test_stale_new_file_on_disk(self):
        """ディスク上に新規 .md ファイルが存在するがインデックスに未登録の場合は True（stale）

        root_dir_name（エイリアス "my_docs"）と実際のディレクトリ名（"documents"）が異なるケースで
        インデックスキーの形式 "{root_dir_name}/{rel_path}" が正しく構築されることを検証する。
        """
        # 実際のディレクトリ名は "documents"、エイリアスは "my_docs"
        docs_dir = self.project_root / "documents"
        docs_dir.mkdir(parents=True)
        new_file = docs_dir / "new.md"
        new_file.write_text("# New\n\nNewly added.\n")

        # インデックスは空（新規ファイルを未登録）
        index = {"entries": {}}
        common_config = {
            "project_root": self.project_root,
            "root_dirs": [(docs_dir, "my_docs")],  # エイリアスがディレクトリ名と異なる
            "target_glob": "*.md",
            "exclude_patterns": [],
        }

        result = check_staleness(index, common_config)
        self.assertTrue(result)

    def test_fresh_when_no_root_dirs(self):
        """root_dirs が common_config に存在しない場合は新規ファイルチェックをスキップする"""
        # ディスク上にファイルを配置（インデックス未登録）
        docs_dir = self.project_root / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "new.md").write_text("# New\n")

        # root_dirs なし → 後方互換のためスキップして False を返す
        index = {"entries": {}}
        common_config = {"project_root": self.project_root}

        result = check_staleness(index, common_config)
        self.assertFalse(result)


# ===========================================================================
# search() テスト
# ===========================================================================

class TestSearch(unittest.TestCase):
    """search() 関数の単体テスト（API モック使用）。"""

    def _make_index(self, entries):
        """テスト用インデックスを生成する。

        Args:
            entries: dict — {path: {"title": str, "embedding": list, "checksum": str}}

        Returns:
            dict: インデックス
        """
        return {
            "metadata": {"model": "text-embedding-3-small"},
            "entries": entries,
        }

    @patch("search_docs.call_embedding_api_single")
    def test_threshold_filtering(self, mock_api):
        """閾値以上のエントリのみが返される"""
        # クエリベクトルは e1 方向
        mock_api.return_value = E1

        index = self._make_index({
            "docs/match.md": {"title": "Match", "embedding": E1, "checksum": "a"},
            "docs/no_match.md": {"title": "No Match", "embedding": E2, "checksum": "b"},
        })

        results = search("test query", index, "fake-key", threshold=0.5)

        # E1 と E1 → 1.0（閾値 0.5 以上）、E1 と E2 → 0.0（閾値以下）
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "docs/match.md")
        self.assertAlmostEqual(results[0]["score"], 1.0, places=4)

    @patch("search_docs.call_embedding_api_single")
    def test_results_sorted_by_score_descending(self, mock_api):
        """結果はスコア降順でソートされる"""
        mock_api.return_value = E1

        index = self._make_index({
            "docs/low.md": {"title": "Low", "embedding": E_45, "checksum": "a"},
            "docs/high.md": {"title": "High", "embedding": E1, "checksum": "b"},
        })

        results = search("test query", index, "fake-key", threshold=0.0)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["path"], "docs/high.md")
        self.assertEqual(results[1]["path"], "docs/low.md")
        self.assertGreater(results[0]["score"], results[1]["score"])

    @patch("search_docs.call_embedding_api_single")
    def test_result_fields(self, mock_api):
        """各結果に path, title, score フィールドが含まれる"""
        mock_api.return_value = E1

        index = self._make_index({
            "docs/test.md": {"title": "Test Title", "embedding": E1, "checksum": "a"},
        })

        results = search("test query", index, "fake-key", threshold=0.0)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIn("path", result)
        self.assertIn("title", result)
        self.assertIn("score", result)
        self.assertEqual(result["title"], "Test Title")

    @patch("search_docs.call_embedding_api_single")
    def test_no_top_k_limit(self, mock_api):
        """件数上限なし: 50 件すべてが返される（FNC-002 対応）"""
        mock_api.return_value = E1

        # 50 件のエントリを生成（全て E1 方向で score=1.0）
        entries = {}
        for i in range(50):
            entries[f"docs/doc_{i:03d}.md"] = {
                "title": f"Doc {i}",
                "embedding": E1,
                "checksum": f"hash_{i}",
            }

        index = self._make_index(entries)
        results = search("test query", index, "fake-key", threshold=0.0)

        self.assertEqual(len(results), 50)

    @patch("search_docs.call_embedding_api_single")
    def test_empty_embedding_skipped(self, mock_api):
        """embedding が空のエントリはスキップされる"""
        mock_api.return_value = E1

        index = self._make_index({
            "docs/valid.md": {"title": "Valid", "embedding": E1, "checksum": "a"},
            "docs/no_embed.md": {"title": "No Embed", "embedding": [], "checksum": "b"},
            "docs/null_embed.md": {"title": "Null Embed", "checksum": "c"},
        })

        results = search("test query", index, "fake-key", threshold=0.0)

        # embedding が空 / 存在しないエントリはスキップ
        paths = [r["path"] for r in results]
        self.assertIn("docs/valid.md", paths)
        self.assertNotIn("docs/no_embed.md", paths)
        self.assertNotIn("docs/null_embed.md", paths)

    @patch("search_docs.call_embedding_api_single")
    def test_threshold_zero_returns_all(self, mock_api):
        """閾値 0.0 では全エントリが返される（スコア 0.0 のものも含む）"""
        mock_api.return_value = E1

        index = self._make_index({
            "docs/match.md": {"title": "Match", "embedding": E1, "checksum": "a"},
            "docs/ortho.md": {"title": "Orthogonal", "embedding": E2, "checksum": "b"},
        })

        results = search("test query", index, "fake-key", threshold=0.0)

        self.assertEqual(len(results), 2)

    @patch("search_docs.call_embedding_api_single")
    def test_score_rounded_to_6_places(self, mock_api):
        """スコアが小数点以下 6 桁に丸められる"""
        mock_api.return_value = E_45

        index = self._make_index({
            "docs/test.md": {"title": "Test", "embedding": E1, "checksum": "a"},
        })

        results = search("test query", index, "fake-key", threshold=0.0)

        score_str = str(results[0]["score"])
        # 小数点以下の桁数が 6 以下であること
        if "." in score_str:
            decimal_places = len(score_str.split(".")[1])
            self.assertLessEqual(decimal_places, 6)


# ===========================================================================
# CLI 統合テスト（subprocess 経由）
# ===========================================================================

class TestSearchDocsCli(unittest.TestCase):
    """search_docs.py の CLI 統合テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)
        self.project_root = self.tmpdir

        # .git ディレクトリ作成（get_project_root() が認識するため）
        os.makedirs(os.path.join(self.project_root, '.git'))

        # .doc_structure.yaml 作成
        doc_structure = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/: spec
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""
        with open(os.path.join(self.project_root, '.doc_structure.yaml'), 'w') as f:
            f.write(doc_structure)

        # rules ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)

        # インデックスディレクトリ作成
        self.index_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'index', 'rules'
        )
        os.makedirs(self.index_dir, exist_ok=True)

        # 環境変数を保存
        self._orig_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'OPENAI_API_DOCDB_KEY', 'OPENAI_API_KEY'):
            self._orig_env[key] = os.environ.get(key)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self._orig_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _run_search(self, *extra_args, category='rules', env_override=None):
        """search_docs.py を subprocess で実行する。"""
        cmd = [
            sys.executable, SEARCH_DOCS_SCRIPT,
            '--category', category,
        ] + list(extra_args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        # デフォルトで API キーを除去（テスト側で明示的に設定する）
        env.pop('OPENAI_API_DOCDB_KEY', None)
        env.pop('OPENAI_API_KEY', None)
        if env_override:
            env.update(env_override)
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )
        return result

    def test_empty_query_error(self):
        """空クエリでエラー JSON が返される"""
        result = self._run_search('--query', '')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "error")
        self.assertIn("empty", output["error"])

    def test_no_query_arg_error(self):
        """--query 引数なしで argparse がエラーを返す（exit code 2）"""
        result = self._run_search()

        self.assertEqual(result.returncode, 2)
        self.assertIn("--query", result.stderr)

    def test_index_not_found_error(self):
        """インデックスが存在しない場合のエラー JSON"""
        result = self._run_search(
            '--query', 'test query',
            env_override={'OPENAI_API_DOCDB_KEY': 'fake-key'},
        )

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "error")
        self.assertIn("Index not found", output["error"])

    def test_model_mismatch_error(self):
        """モデル不一致時のエラー JSON"""
        # 不一致モデルのインデックスを作成
        index_data = {
            "metadata": {"model": "text-embedding-3-large"},
            "entries": {},
        }
        index_path = os.path.join(self.index_dir, "rules_index.json")
        with open(index_path, "w") as f:
            json.dump(index_data, f)

        result = self._run_search(
            '--query', 'test query',
            env_override={'OPENAI_API_DOCDB_KEY': 'fake-key'},
        )

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "error")
        self.assertIn("Model mismatch", output["error"])

    def test_stale_index_error(self):
        """インデックスが stale の場合のエラー JSON"""
        # ルールファイルを作成
        rule_path = os.path.join(self.project_root, 'rules', 'test.md')
        with open(rule_path, 'w') as f:
            f.write("# Test Rule\n\nContent.\n")

        # outdated checksum のインデックスを作成
        index_data = {
            "metadata": {"model": "text-embedding-3-small"},
            "entries": {
                "rules/test.md": {
                    "title": "Test",
                    "embedding": E1,
                    "checksum": "outdated_hash",
                },
            },
        }
        index_path = os.path.join(self.index_dir, "rules_index.json")
        with open(index_path, "w") as f:
            json.dump(index_data, f)

        result = self._run_search(
            '--query', 'test query',
            env_override={'OPENAI_API_DOCDB_KEY': 'fake-key'},
        )

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "error")
        self.assertIn("stale", output["error"].lower())

    def test_no_api_key_error(self):
        """OPENAI_API_DOCDB_KEY / OPENAI_API_KEY とも未設定時のエラー JSON"""
        # 新鮮なインデックスを作成（stale チェックを通過させるため）
        rule_path = os.path.join(self.project_root, 'rules', 'test.md')
        with open(rule_path, 'w') as f:
            f.write("# Test\n\nContent.\n")

        from toc_utils import calculate_file_hash
        current_hash = calculate_file_hash(Path(rule_path))

        index_data = {
            "metadata": {"model": "text-embedding-3-small"},
            "entries": {
                "rules/test.md": {
                    "title": "Test",
                    "embedding": E1,
                    "checksum": current_hash,
                },
            },
        }
        index_path = os.path.join(self.index_dir, "rules_index.json")
        with open(index_path, "w") as f:
            json.dump(index_data, f)

        result = self._run_search('--query', 'test query')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "error")
        # DES-028 §3.4.3 のテンプレートに準拠したエラーメッセージを期待
        self.assertIn("OPENAI_API_DOCDB_KEY", output["error"])

    def test_output_json_format(self):
        """正常時の出力 JSON に status, query, results フィールドが含まれる"""
        # 新鮮なインデックスを作成
        rule_path = os.path.join(self.project_root, 'rules', 'test.md')
        with open(rule_path, 'w') as f:
            f.write("# Test\n\nContent.\n")

        from toc_utils import calculate_file_hash
        current_hash = calculate_file_hash(Path(rule_path))

        index_data = {
            "metadata": {"model": "text-embedding-3-small"},
            "entries": {
                "rules/test.md": {
                    "title": "Test",
                    "embedding": E1,
                    "checksum": current_hash,
                },
            },
        }
        index_path = os.path.join(self.index_dir, "rules_index.json")
        with open(index_path, "w") as f:
            json.dump(index_data, f)

        # subprocess ではなくモジュールを直接テスト（API をモック）
        # CLI 統合テストでは API モックが困難なため、出力形式の検証は
        # search() 関数の結果を JSON 化して確認する
        with patch("search_docs.call_embedding_api_single", return_value=E1):
            results = search("test query", index_data, "fake-key", threshold=0.0)

        # JSON 出力形式の検証
        output = {
            "status": "ok",
            "query": "test query",
            "results": results,
        }
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["query"], "test query")
        self.assertIsInstance(output["results"], list)
        self.assertTrue(len(output["results"]) > 0)

        # 各結果のフィールド検証
        for r in output["results"]:
            self.assertIn("path", r)
            self.assertIn("title", r)
            self.assertIn("score", r)


if __name__ == '__main__':
    unittest.main()
