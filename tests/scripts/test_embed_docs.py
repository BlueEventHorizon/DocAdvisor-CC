#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embed_docs.py のユニットテスト。

テスト対象:
- build_embedding_text() のテスト（API 呼び出しなし）
- get_index_path() のパス生成テスト
- インデックス JSON の読み書きラウンドトリップテスト
- call_embedding_api() の API モックテスト
- --check モードの stale/fresh 出力テスト
- CLI 統合テスト（subprocess 経由）
"""

import json
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

EMBED_DOCS_SCRIPT = os.path.join(SCRIPTS_DIR, 'embed_docs.py')

# テスト用一時ディレクトリのベースパス（/tmp 不可環境でも動作するようプロジェクト内に配置）
_TEST_TEMP_BASE = Path(__file__).parent / ".temp"

import embed_docs
from embed_docs import (
    build_index,
    extract_title,
    get_index_path,
    load_index,
    read_file_content,
    save_index,
    truncate_to_token_limit,
)


# 固定テストベクトル（1536 次元）
FIXED_VECTOR = [1.0] + [0.0] * 1535
FIXED_VECTOR_2 = [0.0] + [1.0] + [0.0] * 1534


# ===========================================================================
# read_file_content() / extract_title() / truncate_to_token_limit() テスト
# ===========================================================================

class TestReadFileContent(unittest.TestCase):
    """read_file_content() の単体テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_read_normal_md_file(self):
        """通常の .md ファイル本文が読めること"""
        p = Path(self.tmpdir) / "test.md"
        p.write_text("# タイトル\n\n本文です。\n", encoding="utf-8")
        result = read_file_content(p)
        self.assertIn("# タイトル", result)
        self.assertIn("本文です。", result)

    def test_read_empty_file(self):
        """空ファイルは空文字列を返す"""
        p = Path(self.tmpdir) / "empty.md"
        p.write_text("", encoding="utf-8")
        result = read_file_content(p)
        self.assertEqual(result, "")

    def test_read_file_with_frontmatter(self):
        """frontmatter 付きファイルの全文が読めること"""
        content = "---\ntitle: テスト\n---\n# 見出し\n\n本文\n"
        p = Path(self.tmpdir) / "fm.md"
        p.write_text(content, encoding="utf-8")
        result = read_file_content(p)
        self.assertEqual(result, content)


class TestExtractTitle(unittest.TestCase):
    """extract_title() の単体テスト。"""

    def test_extract_title_from_heading(self):
        """最初の # 見出しからタイトルを抽出"""
        content = "# 設計書タイトル\n\n本文です。\n"
        result = extract_title(content, "fallback.md")
        self.assertEqual(result, "設計書タイトル")

    def test_extract_title_from_frontmatter(self):
        """YAML frontmatter の title からタイトルを抽出"""
        content = '---\ntitle: "FM タイトル"\n---\n# 見出し\n'
        result = extract_title(content, "fallback.md")
        self.assertEqual(result, "FM タイトル")

    def test_frontmatter_priority_over_heading(self):
        """frontmatter が # 見出しより優先される"""
        content = "---\ntitle: 優先タイトル\n---\n# 見出しタイトル\n"
        result = extract_title(content, "fallback.md")
        self.assertEqual(result, "優先タイトル")

    def test_extract_title_fallback(self):
        """タイトルが見つからない場合はフォールバック名を返す"""
        content = "本文のみ。見出しなし。\n"
        result = extract_title(content, "docs/rules/test.md")
        self.assertEqual(result, "docs/rules/test.md")

    def test_extract_title_empty_content(self):
        """空コンテンツの場合はフォールバック名を返す"""
        result = extract_title("", "fallback.md")
        self.assertEqual(result, "fallback.md")

    def test_extract_title_h2_not_used(self):
        """## 見出しはタイトルとして使わない"""
        content = "## サブ見出し\n\n本文\n"
        result = extract_title(content, "fallback.md")
        self.assertEqual(result, "fallback.md")


class TestTruncateToTokenLimit(unittest.TestCase):
    """truncate_to_token_limit() の単体テスト。"""

    def test_short_text_unchanged(self):
        """短いテキストはそのまま返される"""
        text = "短いテキスト"
        result = truncate_to_token_limit(text)
        self.assertEqual(result, text)

    def test_long_text_truncated(self):
        """長いテキストは max_chars で切り詰められる"""
        text = "あ" * 10000
        result = truncate_to_token_limit(text)
        self.assertEqual(len(result), embed_docs.EMBEDDING_MAX_CHARS)

    def test_exact_limit_unchanged(self):
        """ちょうど max_chars のテキストはそのまま"""
        text = "x" * embed_docs.EMBEDDING_MAX_CHARS
        result = truncate_to_token_limit(text)
        self.assertEqual(len(result), embed_docs.EMBEDDING_MAX_CHARS)

    def test_custom_max_chars(self):
        """カスタム max_chars が使える"""
        text = "あ" * 200
        result = truncate_to_token_limit(text, max_chars=100)
        self.assertEqual(len(result), 100)


# ===========================================================================
# get_index_path() テスト
# ===========================================================================

class TestGetIndexPath(unittest.TestCase):
    """get_index_path() のパス生成テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)
        self.original_env = {}
        for key in ('CLAUDE_PROJECT_DIR',):
            self.original_env[key] = os.environ.get(key)
        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self.original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def test_specs_path_default(self):
        """specs カテゴリのデフォルトインデックスパス"""
        root = Path(self.tmpdir)
        result = get_index_path("specs", root)
        expected = root / ".claude/doc-advisor/index/specs/specs_index.json"
        self.assertEqual(result, expected)

    def test_rules_path_default(self):
        """rules カテゴリのデフォルトインデックスパス"""
        root = Path(self.tmpdir)
        result = get_index_path("rules", root)
        expected = root / ".claude/doc-advisor/index/rules/rules_index.json"
        self.assertEqual(result, expected)

    def test_custom_output_dir(self):
        """output_dir 設定時にカスタムパスが返る"""
        doc_structure = """\
# doc_structure_version: 3.0

rules:
  output_dir: custom/base/
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""
        with open(os.path.join(self.tmpdir, '.doc_structure.yaml'), 'w') as f:
            f.write(doc_structure)

        root = Path(self.tmpdir)
        result = get_index_path("rules", root)
        expected = root / "custom/base/index/rules/rules_index.json"
        self.assertEqual(result, expected)


# ===========================================================================
# load_index / save_index ラウンドトリップテスト
# ===========================================================================

class TestLoadSaveIndex(unittest.TestCase):
    """インデックス JSON の読み書きラウンドトリップテスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_roundtrip(self):
        """保存したインデックスを正しく読み込めること"""
        index_path = Path(self.tmpdir) / "test_index.json"
        original = {
            "metadata": {
                "category": "specs",
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "generated_at": "2026-03-30T12:00:00Z",
                "file_count": 1,
            },
            "entries": {
                "docs/test.md": {
                    "title": "テスト文書",
                    "embedding": FIXED_VECTOR,
                    "checksum": "abc123",
                },
            },
        }
        save_index(original, index_path)
        loaded = load_index(index_path)

        self.assertEqual(loaded["metadata"]["category"], "specs")
        self.assertEqual(loaded["metadata"]["dimensions"], 1536)
        self.assertEqual(loaded["entries"]["docs/test.md"]["title"], "テスト文書")
        self.assertEqual(len(loaded["entries"]["docs/test.md"]["embedding"]), 1536)

    def test_load_nonexistent_returns_empty(self):
        """存在しないファイルの読み込みは空 dict を返す"""
        result = load_index(Path(self.tmpdir) / "nonexistent.json")
        self.assertEqual(result, {})

    def test_load_corrupted_raises_error(self):
        """破損 JSON はValueError を発生させる"""
        bad_path = Path(self.tmpdir) / "bad.json"
        bad_path.write_text("{invalid json", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_index(bad_path)

    def test_save_creates_parent_dirs(self):
        """save_index は親ディレクトリを自動作成する"""
        deep_path = Path(self.tmpdir) / "a" / "b" / "c" / "index.json"
        save_index({"entries": {}}, deep_path)
        self.assertTrue(deep_path.exists())

    def test_roundtrip_multiple_entries(self):
        """複数エントリのラウンドトリップ"""
        index_path = Path(self.tmpdir) / "multi.json"
        original = {
            "metadata": {"category": "rules", "file_count": 2},
            "entries": {
                "docs/a.md": {"title": "A", "embedding": FIXED_VECTOR, "checksum": "aaa"},
                "docs/b.md": {"title": "B", "embedding": FIXED_VECTOR_2, "checksum": "bbb"},
            },
        }
        save_index(original, index_path)
        loaded = load_index(index_path)
        self.assertEqual(len(loaded["entries"]), 2)
        self.assertEqual(loaded["entries"]["docs/a.md"]["embedding"][0], 1.0)
        self.assertEqual(loaded["entries"]["docs/b.md"]["embedding"][1], 1.0)


# ===========================================================================
# --check モードのテスト（subprocess 経由）
# ===========================================================================

class TestRunCheckMode(unittest.TestCase):
    """--check モードの stale/fresh 出力テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)
        self.project_root = self.tmpdir

        # .git ディレクトリ作成
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

        # インデックスディレクトリ作成
        self.index_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'index', 'rules'
        )
        os.makedirs(self.index_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_rule_file(self, rel_path, content='# Test Rule\n\nThis is a test rule.\n'):
        """rules/ 配下にテスト用 .md ファイルを作成"""
        full_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        return full_path

    def _run_embed_docs(self, *extra_args, category='rules'):
        """embed_docs.py を subprocess で実行"""
        cmd = [
            sys.executable, EMBED_DOCS_SCRIPT,
            '--category', category,
        ] + list(extra_args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        # API キーを除去（--check モードでは不要）
        env.pop('OPENAI_API_DOCDB_KEY', None)
        env.pop('OPENAI_API_KEY', None)
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )
        return result

    def test_check_no_index(self):
        """インデックスが存在しない場合は stale を返す"""
        self._create_rule_file('rules/test.md')
        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "stale")
        self.assertEqual(output["reason"], "index_not_found")

    def test_check_no_checksums(self):
        """チェックサムファイルがない場合は stale を返す"""
        self._create_rule_file('rules/test.md')

        # インデックスだけ作成（チェックサムなし）
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        with open(index_path, 'w') as f:
            json.dump({"metadata": {}, "entries": {}}, f)

        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "stale")
        self.assertEqual(output["reason"], "checksums_not_found")

    def test_check_fresh(self):
        """全ファイルのチェックサムが一致する場合は fresh を返す"""
        file_path = self._create_rule_file('rules/test.md')

        # インデックス作成
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        with open(index_path, 'w') as f:
            json.dump({"metadata": {}, "entries": {}}, f)

        # チェックサム作成（実際のハッシュ値を使用）
        import hashlib
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            sha256.update(f.read())
        file_hash = sha256.hexdigest()

        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write(f"checksums:\n  rules/test.md: {file_hash}\n")

        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "fresh")

    def test_check_stale_new_file(self):
        """新しいファイルが追加された場合は stale を返す"""
        self._create_rule_file('rules/existing.md')
        self._create_rule_file('rules/new_file.md')

        # インデックス作成
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        with open(index_path, 'w') as f:
            json.dump({"metadata": {}, "entries": {}}, f)

        # チェックサムには existing.md のみ登録
        import hashlib
        sha256 = hashlib.sha256()
        existing_path = os.path.join(self.project_root, 'rules', 'existing.md')
        with open(existing_path, 'rb') as f:
            sha256.update(f.read())
        file_hash = sha256.hexdigest()

        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write(f"checksums:\n  rules/existing.md: {file_hash}\n")

        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "stale")
        self.assertIn("1 new", output["reason"])

    def test_check_stale_modified_file(self):
        """ファイルが変更された場合は stale を返す"""
        self._create_rule_file('rules/test.md', content='# Original\n\nOriginal content.\n')

        # インデックス作成
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        with open(index_path, 'w') as f:
            json.dump({"metadata": {}, "entries": {}}, f)

        # 古いチェックサム（不一致なハッシュ）
        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write("checksums:\n  rules/test.md: old_hash_value\n")

        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "stale")
        self.assertIn("1 modified", output["reason"])

    def test_check_stale_deleted_file(self):
        """ファイルが削除された場合は stale を返す"""
        # rules/ ディレクトリは作成するがファイルなし
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)

        # インデックス作成
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        with open(index_path, 'w') as f:
            json.dump({"metadata": {}, "entries": {}}, f)

        # 存在しないファイルのチェックサムを登録
        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write("checksums:\n  rules/deleted.md: some_hash\n")

        result = self._run_embed_docs('--check')

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "stale")
        self.assertIn("1 deleted", output["reason"])


# ===========================================================================
# CLI 統合テスト（subprocess 経由）
# ===========================================================================

class TestEmbedDocsCli(unittest.TestCase):
    """embed_docs.py の CLI 統合テスト。"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = tempfile.mkdtemp(dir=_TEST_TEMP_BASE)
        self.project_root = self.tmpdir

        # .git ディレクトリ作成
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

        # rules/ ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)

        # インデックスディレクトリ作成
        self.index_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'index', 'rules'
        )
        os.makedirs(self.index_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_rule_file(self, rel_path, content='# Test Rule\n\nThis is a test rule.\n'):
        """rules/ 配下にテスト用 .md ファイルを作成"""
        full_path = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        return full_path

    def _run_embed_docs(self, *extra_args, category='rules', env_override=None):
        """embed_docs.py を subprocess で実行"""
        cmd = [
            sys.executable, EMBED_DOCS_SCRIPT,
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

    def test_no_api_key_error(self):
        """OPENAI_API_DOCDB_KEY / OPENAI_API_KEY とも未設定時にエラー JSON を出力する"""
        self._create_rule_file('rules/test.md')

        # API キー（DOCDB + フォールバック）を除去
        env_clean = os.environ.copy()
        env_clean.pop('OPENAI_API_DOCDB_KEY', None)
        env_clean.pop('OPENAI_API_KEY', None)
        env_clean['CLAUDE_PROJECT_DIR'] = self.project_root

        cmd = [
            sys.executable, EMBED_DOCS_SCRIPT,
            '--category', 'rules',
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env_clean
        )

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "error")
        # DES-028 §3.4.3 のテンプレートに準拠したエラーメッセージを期待
        self.assertIn("OPENAI_API_DOCDB_KEY", output["error"])

    def test_full_mode_with_mock_api(self):
        """--full モードで API をモックしてインデックスが生成されること（直接呼び出し）"""
        self._create_rule_file('rules/test.md', content='# Test Rule\n\nテスト用ルール文書。\n')

        # 直接モジュール関数を呼び出してテスト（API をモック）
        with patch("embed_docs.call_embedding_api") as mock_api:
            mock_api.return_value = [FIXED_VECTOR]

            # 環境変数を設定
            original_env = os.environ.get('CLAUDE_PROJECT_DIR')
            os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

            try:
                from toc_utils import init_common_config as toc_init

                common = toc_init('rules')
                project_root = common['project_root']
                config = common['config']

                index_path = get_index_path('rules', project_root)
                checksums_file = index_path.parent / embed_docs.EMBEDDING_CHECKSUMS_FILENAME

                exit_code = build_index('rules', common, index_path, checksums_file, True, 'fake-key')
            finally:
                if original_env is None:
                    os.environ.pop('CLAUDE_PROJECT_DIR', None)
                else:
                    os.environ['CLAUDE_PROJECT_DIR'] = original_env

        self.assertEqual(exit_code, 0)
        # インデックスが作成されたことを確認
        self.assertTrue(index_path.exists())
        with open(index_path, 'r') as f:
            index = json.load(f)
        self.assertEqual(index["metadata"]["category"], "rules")
        self.assertIn("rules/test.md", index["entries"])
        self.assertEqual(len(index["entries"]["rules/test.md"]["embedding"]), 1536)
        # API が呼ばれたことを確認
        mock_api.assert_called_once()

    def test_diff_mode_detects_changes(self):
        """差分モードで新規・変更・削除を検出してインデックスを更新すること"""
        self._create_rule_file('rules/existing.md', content='# Existing\n\nExisting content.\n')
        self._create_rule_file('rules/new_file.md', content='# New\n\nNew content.\n')

        # 既存インデックスを作成（existing.md と deleted.md がある状態）
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        existing_index = {
            "metadata": {"category": "rules", "model": "text-embedding-3-small", "dimensions": 1536, "file_count": 2},
            "entries": {
                "rules/existing.md": {"title": "Existing", "embedding": FIXED_VECTOR, "checksum": "old_hash"},
                "rules/deleted.md": {"title": "Deleted", "embedding": FIXED_VECTOR, "checksum": "deleted_hash"},
            },
        }
        with open(index_path, 'w') as f:
            json.dump(existing_index, f)

        # チェックサム（existing.md は古いハッシュ、deleted.md も登録）
        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write("checksums:\n  rules/existing.md: old_hash\n  rules/deleted.md: deleted_hash\n")

        with patch("embed_docs.call_embedding_api") as mock_api:
            mock_api.return_value = [FIXED_VECTOR, FIXED_VECTOR_2]

            original_env = os.environ.get('CLAUDE_PROJECT_DIR')
            os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

            try:
                from toc_utils import init_common_config as toc_init
                common = toc_init('rules')
                project_root = common['project_root']
                idx_path = get_index_path('rules', project_root)
                checksums_file = idx_path.parent / embed_docs.EMBEDDING_CHECKSUMS_FILENAME

                exit_code = embed_docs.build_index('rules', common, idx_path, checksums_file, False, 'fake-key')
            finally:
                if original_env is None:
                    os.environ.pop('CLAUDE_PROJECT_DIR', None)
                else:
                    os.environ['CLAUDE_PROJECT_DIR'] = original_env

        self.assertEqual(exit_code, 0)
        with open(idx_path, 'r') as f:
            index = json.load(f)
        # deleted.md は削除されている
        self.assertNotIn("rules/deleted.md", index["entries"])
        # existing.md と new_file.md がある
        self.assertIn("rules/existing.md", index["entries"])
        self.assertIn("rules/new_file.md", index["entries"])
        # API が呼ばれた（2ファイル分）
        mock_api.assert_called_once()

    def test_diff_mode_removes_deleted_file_checksum(self):
        """差分モードで削除されたファイルのチェックサムが更新後のファイルに含まれないこと"""
        self._create_rule_file('rules/kept.md', content='# Kept\n\nKept content.\n')

        # 既存インデックス（kept.md と removed.md）
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        existing_index = {
            "metadata": {"category": "rules", "model": "text-embedding-3-small", "dimensions": 1536, "file_count": 2},
            "entries": {
                "rules/kept.md": {"title": "Kept", "embedding": FIXED_VECTOR, "checksum": "old_hash"},
                "rules/removed.md": {"title": "Removed", "embedding": FIXED_VECTOR, "checksum": "removed_hash"},
            },
        }
        with open(index_path, 'w') as f:
            json.dump(existing_index, f)

        # チェックサム（kept.md と removed.md が登録済み）
        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write("checksums:\n  rules/kept.md: old_hash\n  rules/removed.md: removed_hash\n")

        with patch("embed_docs.call_embedding_api") as mock_api:
            mock_api.return_value = [FIXED_VECTOR]

            original_env = os.environ.get('CLAUDE_PROJECT_DIR')
            os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

            try:
                from toc_utils import init_common_config as toc_init
                common = toc_init('rules')
                project_root = common['project_root']
                idx_path = get_index_path('rules', project_root)
                checksums_file = idx_path.parent / embed_docs.EMBEDDING_CHECKSUMS_FILENAME

                exit_code = embed_docs.build_index('rules', common, idx_path, checksums_file, False, 'fake-key')
            finally:
                if original_env is None:
                    os.environ.pop('CLAUDE_PROJECT_DIR', None)
                else:
                    os.environ['CLAUDE_PROJECT_DIR'] = original_env

        self.assertEqual(exit_code, 0)
        # チェックサムファイルを読んで removed.md が含まれないことを確認
        with open(checksums_file, 'r') as f:
            checksums_content = f.read()
        self.assertNotIn("rules/removed.md", checksums_content)
        self.assertIn("rules/kept.md", checksums_content)

    def test_diff_mode_auto_full_when_no_index(self):
        """インデックス未作成時に差分モード（--full なし）で呼ぶと自動フルビルドされること"""
        self._create_rule_file('rules/test.md', content='# Auto Full\n\nAuto full build test.\n')

        # インデックスファイルが存在しないことを確認
        index_path_file = os.path.join(self.index_dir, 'rules_index.json')
        self.assertFalse(os.path.exists(index_path_file))

        with patch("embed_docs.call_embedding_api") as mock_api:
            mock_api.return_value = [FIXED_VECTOR]

            original_env = os.environ.get('CLAUDE_PROJECT_DIR')
            os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

            try:
                from toc_utils import init_common_config as toc_init
                common = toc_init('rules')
                project_root = common['project_root']
                idx_path = get_index_path('rules', project_root)
                checksums_file = idx_path.parent / embed_docs.EMBEDDING_CHECKSUMS_FILENAME

                # --full なし（False）で呼び出し
                exit_code = embed_docs.build_index('rules', common, idx_path, checksums_file, False, 'fake-key')
            finally:
                if original_env is None:
                    os.environ.pop('CLAUDE_PROJECT_DIR', None)
                else:
                    os.environ['CLAUDE_PROJECT_DIR'] = original_env

        self.assertEqual(exit_code, 0)
        # インデックスが作成されたことを確認
        self.assertTrue(idx_path.exists())
        with open(idx_path, 'r') as f:
            index = json.load(f)
        self.assertIn("rules/test.md", index["entries"])
        self.assertEqual(len(index["entries"]["rules/test.md"]["embedding"]), 1536)
        # API が呼ばれたことを確認
        mock_api.assert_called_once()

    def test_diff_mode_no_changes_skips_api(self):
        """変更なしの場合は API を呼ばずにスキップすること"""
        file_path = self._create_rule_file('rules/test.md', content='# No Change\n\nNo change test.\n')

        # 既存インデックスを作成
        index_path = os.path.join(self.index_dir, 'rules_index.json')
        existing_index = {
            "metadata": {"category": "rules", "model": "text-embedding-3-small", "dimensions": 1536, "file_count": 1},
            "entries": {
                "rules/test.md": {"title": "No Change", "embedding": FIXED_VECTOR, "checksum": "dummy"},
            },
        }
        with open(index_path, 'w') as f:
            json.dump(existing_index, f)

        # 現在のファイルハッシュでチェックサムを作成
        import hashlib
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            sha256.update(f.read())
        file_hash = sha256.hexdigest()

        checksums_path = os.path.join(self.index_dir, '.embedding_checksums.yaml')
        with open(checksums_path, 'w') as f:
            f.write(f"checksums:\n  rules/test.md: {file_hash}\n")

        with patch("embed_docs.call_embedding_api") as mock_api:
            original_env = os.environ.get('CLAUDE_PROJECT_DIR')
            os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

            try:
                from toc_utils import init_common_config as toc_init
                common = toc_init('rules')
                project_root = common['project_root']
                idx_path = get_index_path('rules', project_root)
                checksums_file = idx_path.parent / embed_docs.EMBEDDING_CHECKSUMS_FILENAME

                exit_code = embed_docs.build_index('rules', common, idx_path, checksums_file, False, 'fake-key')
            finally:
                if original_env is None:
                    os.environ.pop('CLAUDE_PROJECT_DIR', None)
                else:
                    os.environ['CLAUDE_PROJECT_DIR'] = original_env

        self.assertEqual(exit_code, 0)
        # API が呼ばれていないことを確認
        mock_api.assert_not_called()

    def test_config_not_ready_error(self):
        """doc_structure.yaml が未設定の場合にエラー JSON を返す"""
        # .doc_structure.yaml を削除し、デフォルト rules/ ディレクトリも削除
        os.remove(os.path.join(self.project_root, '.doc_structure.yaml'))
        rules_dir = os.path.join(self.project_root, 'rules')
        if os.path.exists(rules_dir):
            shutil.rmtree(rules_dir)

        env_clean = os.environ.copy()
        env_clean.pop('OPENAI_API_DOCDB_KEY', None)
        env_clean.pop('OPENAI_API_KEY', None)
        env_clean['CLAUDE_PROJECT_DIR'] = self.project_root

        cmd = [
            sys.executable, EMBED_DOCS_SCRIPT,
            '--category', 'rules', '--check',
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env_clean
        )

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout.strip())
        self.assertEqual(output["status"], "error")


if __name__ == '__main__':
    unittest.main()
