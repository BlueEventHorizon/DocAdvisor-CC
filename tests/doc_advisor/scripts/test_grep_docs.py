#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grep_docs.py のユニットテスト。

テスト対象:
- search_files() 関数の単体テスト（TestSearchFiles）
- CLI 経由の統合テスト（TestGrepDocsCli）
- エッジケース（TestGrepDocsEdgeCases）

テスト方針:
- tmpdir に仮文書を配置し、CLAUDE_PROJECT_DIR 環境変数でルートを指定
- OPENAI_API_KEY 不要（grep_docs.py はローカル検索のみ）
- 既存テスト test_create_pending.py のパターンを踏襲
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
GREP_DOCS_SCRIPT = os.path.join(SCRIPTS_DIR, 'grep_docs.py')


class GrepDocsTestBase(unittest.TestCase):
    """テスト用の共通セットアップ"""

    def setUp(self):
        """一時ディレクトリとテスト用プロジェクト構造を作成"""
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        # .git ディレクトリ作成（get_project_root() が認識するため）
        os.makedirs(os.path.join(self.project_root, '.git'))

        # .doc_structure.yaml 作成
        self._write_doc_structure()

        # rules/ ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)

        # specs/ ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'specs'), exist_ok=True)

        # ToC ディレクトリ作成（init_common_config が参照する場合あり）
        os.makedirs(
            os.path.join(self.project_root, '.claude', 'doc-advisor', 'toc', 'rules'),
            exist_ok=True,
        )
        os.makedirs(
            os.path.join(self.project_root, '.claude', 'doc-advisor', 'toc', 'specs'),
            exist_ok=True,
        )

        # 環境変数の保存と設定
        self._original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self._original_env[key] = os.environ.get(key)
        os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

        # sys.path にスクリプトディレクトリを追加（直接 import 用）
        # doc-db 側 tests が先に plugins/doc-db/scripts を path 先頭に載せた場合、
        # grep_docs が doc-db 実装として import 済みになる。常に doc-advisor 版を先頭にし、
        # キャッシュを捨ててから読み込む。
        while SCRIPTS_DIR in sys.path:
            sys.path.remove(SCRIPTS_DIR)
        sys.path.insert(0, SCRIPTS_DIR)
        sys.modules.pop('grep_docs', None)

    def tearDown(self):
        """一時ディレクトリを削除、環境変数を復元"""
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self._original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _write_doc_structure(self):
        """テスト用 .doc_structure.yaml を作成"""
        content = """\
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
            f.write(content)

    def _create_doc(self, rel_path, content):
        """指定パスにテスト用文書を作成"""
        full_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return full_path

    def _run_grep_docs(self, *extra_args, category='rules'):
        """grep_docs.py を subprocess で実行"""
        cmd = [
            sys.executable, GREP_DOCS_SCRIPT,
            '--category', category,
        ] + list(extra_args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )
        return result


# ===========================================================================
# search_files() 関数の単体テスト
# ===========================================================================

class TestSearchFiles(GrepDocsTestBase):
    """search_files() 関数の単体テスト"""

    def _get_search_files(self):
        """search_files と init_common_config をインポートして返す"""
        from grep_docs import search_files
        from toc_utils import init_common_config
        return search_files, init_common_config

    def test_keyword_body_match(self):
        """本文にキーワードを含むファイルがマッチする"""
        self._create_doc('rules/auth.md', '# 認証ルール\n\nユーザー認証には OAuth2 を使用する。\n')
        self._create_doc('rules/deploy.md', '# デプロイルール\n\nCI/CD パイプラインの設定。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('OAuth2', common_config)

        self.assertEqual(len(results), 1)
        self.assertIn('rules/auth.md', results[0])

    def test_case_insensitive(self):
        """大文字小文字を区別しない検索"""
        self._create_doc('rules/guide.md', '# ガイド\n\nDockerfile のベストプラクティス。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')

        # 小文字で検索しても大文字の Dockerfile にマッチする
        results_lower = search_files('dockerfile', common_config)
        self.assertEqual(len(results_lower), 1)

        # 大文字で検索しても同様
        results_upper = search_files('DOCKERFILE', common_config)
        self.assertEqual(len(results_upper), 1)

        # 結果は同じ
        self.assertEqual(results_lower, results_upper)

    def test_partial_match(self):
        """部分一致で検索される"""
        self._create_doc('rules/naming.md', '# 命名規則\n\ndoc_structure.yaml の命名ルール。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')

        # 'doc_structure' で部分一致する
        results = search_files('doc_structure', common_config)
        self.assertEqual(len(results), 1)

        # 'structure' だけでも部分一致する
        results_partial = search_files('structure', common_config)
        self.assertEqual(len(results_partial), 1)

    def test_no_match_returns_empty(self):
        """該当なしの場合は空リストを返す"""
        self._create_doc('rules/basic.md', '# 基本ルール\n\nコーディング規約。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('存在しないキーワード_xyz123', common_config)

        self.assertEqual(results, [])

    def test_multiple_matches_sorted(self):
        """複数ファイルがマッチした場合、パスがソートされる"""
        self._create_doc('rules/z_rule.md', '# Z ルール\n\nテスト用のキーワード。\n')
        self._create_doc('rules/a_rule.md', '# A ルール\n\nテスト用のキーワード。\n')
        self._create_doc('rules/m_rule.md', '# M ルール\n\nテスト用のキーワード。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('キーワード', common_config)

        self.assertEqual(len(results), 3)
        # ソート順を確認
        self.assertTrue(results[0] < results[1] < results[2])

    def test_specs_category(self):
        """specs カテゴリでの検索"""
        self._create_doc('specs/api.md', '# API 設計\n\nREST API のエンドポイント定義。\n')
        self._create_doc('rules/api_rule.md', '# API ルール\n\nAPI の命名規約。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('specs')
        results = search_files('API', common_config)

        # specs カテゴリのみ検索される
        self.assertEqual(len(results), 1)
        self.assertIn('specs/api.md', results[0])


# ===========================================================================
# CLI 統合テスト
# ===========================================================================

class TestGrepDocsCli(GrepDocsTestBase):
    """grep_docs.py の CLI 統合テスト"""

    def test_output_json_format(self):
        """出力が正しい JSON 形式であること"""
        self._create_doc('rules/test.md', '# テスト\n\nサンプルコンテンツ。\n')

        result = self._run_grep_docs('--keyword', 'サンプル')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'ok')
        self.assertEqual(output['keyword'], 'サンプル')
        self.assertIsInstance(output['results'], list)
        self.assertEqual(len(output['results']), 1)
        # results の各要素は {"path": "..."} 形式
        self.assertIn('path', output['results'][0])
        self.assertIn('rules/test.md', output['results'][0]['path'])

    def test_no_match_json(self):
        """該当なしでも正しい JSON が返る"""
        self._create_doc('rules/test.md', '# テスト\n\n何もない文書。\n')

        result = self._run_grep_docs('--keyword', 'nonexistent_keyword_xyz')

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'ok')
        self.assertEqual(output['results'], [])

    def test_missing_keyword_error(self):
        """--keyword 未指定でエラーになること"""
        result = self._run_grep_docs()

        # argparse が --keyword 必須で弾く
        self.assertNotEqual(result.returncode, 0)

    def test_empty_keyword_error_json(self):
        """--keyword が空文字列の場合、エラー JSON が返る"""
        result = self._run_grep_docs('--keyword', '   ')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'error')
        self.assertIn('empty', output['error'].lower())

    def test_specs_category_cli(self):
        """--category specs での CLI 実行"""
        self._create_doc('specs/design.md', '# 設計書\n\nアーキテクチャ設計。\n')

        result = self._run_grep_docs('--keyword', 'アーキテクチャ', category='specs')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'ok')
        self.assertEqual(len(output['results']), 1)

    def test_config_required_without_doc_structure(self):
        """root_dirs のディレクトリが存在しない場合は config_required"""
        # rules/ ディレクトリを削除
        shutil.rmtree(os.path.join(self.project_root, 'rules'))

        result = self._run_grep_docs('--keyword', 'test')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'config_required')


# ===========================================================================
# エッジケース
# ===========================================================================

class TestGrepDocsEdgeCases(GrepDocsTestBase):
    """grep_docs.py のエッジケーステスト"""

    def test_japanese_keyword(self):
        """日本語キーワードでの検索"""
        self._create_doc('rules/jp.md', '# 日本語ドキュメント\n\n認証フロー設計の概要。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('認証フロー', common_config)

        self.assertEqual(len(results), 1)

    def _get_search_files(self):
        from grep_docs import search_files
        from toc_utils import init_common_config
        return search_files, init_common_config

    def test_file_with_special_characters_in_content(self):
        """特殊文字を含む本文の検索"""
        self._create_doc(
            'rules/special.md',
            '# 特殊文字\n\n設定は `.doc_structure.yaml` に記述する。\n'
        )

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('.doc_structure.yaml', common_config)

        self.assertEqual(len(results), 1)

    def test_empty_file_not_matched(self):
        """空ファイルはキーワードにマッチしない"""
        self._create_doc('rules/empty.md', '')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('何か', common_config)

        self.assertEqual(results, [])

    def test_subdirectory_files(self):
        """サブディレクトリ内のファイルも検索対象になる"""
        self._create_doc('rules/sub/deep/nested.md', '# ネスト\n\n深い階層のファイル。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('深い階層', common_config)

        self.assertEqual(len(results), 1)
        self.assertIn('rules/sub/deep/nested.md', results[0])

    def test_keyword_in_heading_matches(self):
        """見出し内のキーワードもマッチする"""
        self._create_doc('rules/heading.md', '# デプロイメント手順\n\n本文はここ。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('デプロイメント', common_config)

        self.assertEqual(len(results), 1)

    def test_non_md_files_ignored(self):
        """*.md 以外のファイルは検索対象外（.md のみがヒットすることを検証）"""
        self._create_doc('rules/readme.txt', 'このファイルにはキーワードがある。\n')
        self._create_doc('rules/data.json', '{"keyword": "テスト"}')
        # .md にもキーワードを含める。.txt/.json が除外されなければ余分な結果が混入する
        self._create_doc('rules/actual.md', '# ルール\n\nこのファイルにはキーワードがある。\n')

        search_files, init_common_config = self._get_search_files()
        common_config = init_common_config('rules')
        results = search_files('キーワード', common_config)

        # .md のみがヒットし、.txt と .json は除外される
        self.assertEqual(len(results), 1)
        self.assertIn('rules/actual.md', results[0])


if __name__ == '__main__':
    unittest.main()
