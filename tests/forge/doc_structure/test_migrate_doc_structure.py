#!/usr/bin/env python3
"""
migrate_doc_structure.py のテスト

COMMON-REQ-001 準拠のマイグレーションフレームワークと各マイグレーション関数をテストする。

実行:
    python3 -m unittest tests.forge.doc_structure.test_migrate_doc_structure -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# スクリプトのパスを追加
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'scripts' / 'doc_structure'
sys.path.insert(0, str(SCRIPTS_DIR))

from migrate_doc_structure import (
    CURRENT_VERSION,
    MIGRATIONS,
    apply_migrations,
    detect_version,
    get_migration_plan,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)

# ===========================================================================
# テストデータ
# ===========================================================================

V1_CONTENT = '''\
version: "1.0"

specs:
  design:
    paths: [docs/specs/design/]
    description: "Design specifications"
  plan:
    paths: [docs/specs/plan/]
    description: "Development plans"
  requirement:
    paths: [docs/specs/requirement/]
    description: "Requirements"

rules:
  rule:
    paths: [docs/rules/]
    description: "Development rules"
'''

V2_CONTENT = '''\
# doc_structure_version: 2.0

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/rules/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude: []
  output:
    header_comment: "Development documentation search index for query-rules skill"
    metadata_name: "Development Documentation Search Index"

specs:
  root_dirs:
    - "docs/specs/*/design/"
  doc_types_map:
    "docs/specs/*/design/": design
  toc_file: .claude/doc-advisor/toc/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/toc/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/specs/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude: []
  output:
    header_comment: "Project specification document search index for query-specs skill"
    metadata_name: "Project Specification Document Search Index"

common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
'''

V3_CONTENT = '''\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - "docs/specs/*/design/"
  doc_types_map:
    "docs/specs/*/design/": design
  patterns:
    target_glob: "**/*.md"
    exclude: []
'''

NO_VERSION_CONTENT = '''\
rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
'''


# ===========================================================================
# 1. バージョン検出テスト
# ===========================================================================

class TestDetectVersion(unittest.TestCase):
    """detect_version のテスト"""

    def test_detect_v1(self):
        """v1 形式を正しく検出する"""
        self.assertEqual(detect_version(V1_CONTENT), 1)

    def test_detect_v2(self):
        """v2 形式を正しく検出する"""
        self.assertEqual(detect_version(V2_CONTENT), 2)

    def test_detect_v3(self):
        """v3 形式を正しく検出する"""
        self.assertEqual(detect_version(V3_CONTENT), 3)

    def test_detect_no_version_fallback_to_v1(self):
        """バージョン識別子がない場合は v1 として扱う（FR-04-3）"""
        self.assertEqual(detect_version(NO_VERSION_CONTENT), 1)

    def test_detect_empty_content(self):
        """空文字列は v1 として扱う"""
        self.assertEqual(detect_version(''), 1)

    def test_detect_future_version(self):
        """将来のバージョン（v5）を正しく検出する"""
        content = '# doc_structure_version: 5.0\nrules:\n  root_dirs:\n    - rules/\n'
        self.assertEqual(detect_version(content), 5)


# ===========================================================================
# 2. migrate_v1_to_v2 テスト
# ===========================================================================

class TestMigrateV1ToV2(unittest.TestCase):
    """v1 → v2 マイグレーションのテスト"""

    def setUp(self):
        self.result = migrate_v1_to_v2(V1_CONTENT)

    def test_version_marker_added(self):
        """v2 バージョンマーカーが追加される"""
        self.assertIn('# doc_structure_version: 2.0', self.result)

    def test_old_version_field_removed(self):
        """v1 の version フィールドが削除される"""
        self.assertNotIn('version: "1.0"', self.result)

    def test_root_dirs_generated(self):
        """root_dirs が生成される"""
        self.assertIn('root_dirs:', self.result)
        self.assertIn('docs/rules/', self.result)

    def test_doc_types_map_generated(self):
        """doc_types_map が生成される"""
        self.assertIn('doc_types_map:', self.result)
        self.assertIn('docs/rules/: rule', self.result)

    def test_description_removed(self):
        """description フィールドが除去される"""
        self.assertNotIn('description:', self.result)

    def test_toc_file_added(self):
        """v2 の toc_file フィールドが追加される"""
        self.assertIn('toc_file:', self.result)

    def test_output_section_added(self):
        """v2 の output セクションが追加される"""
        self.assertIn('output:', self.result)
        self.assertIn('header_comment:', self.result)

    def test_common_section_added(self):
        """v2 の common セクションが追加される"""
        self.assertIn('common:', self.result)
        self.assertIn('max_workers: 5', self.result)

    def test_idempotent(self):
        """冪等性: 同じ入力に対して同じ出力を返す（FR-03-2）"""
        result1 = migrate_v1_to_v2(V1_CONTENT)
        result2 = migrate_v1_to_v2(V1_CONTENT)
        self.assertEqual(result1, result2)

    def test_specs_paths_converted(self):
        """specs の paths が root_dirs + doc_types_map に変換される"""
        self.assertIn('docs/specs/design/', self.result)
        self.assertIn('docs/specs/plan/', self.result)
        self.assertIn('docs/specs/requirement/', self.result)


# ===========================================================================
# 3. migrate_v2_to_v3 テスト
# ===========================================================================

class TestMigrateV2ToV3(unittest.TestCase):
    """v2 → v3 マイグレーションのテスト"""

    def setUp(self):
        self.result = migrate_v2_to_v3(V2_CONTENT)

    def test_version_marker_updated(self):
        """バージョンマーカーが 3.0 に更新される"""
        self.assertIn('# doc_structure_version: 3.0', self.result)
        self.assertNotIn('doc_structure_version: 2.0', self.result)

    def test_toc_file_removed(self):
        """toc_file が除去される"""
        self.assertNotIn('toc_file:', self.result)

    def test_checksums_file_removed(self):
        """checksums_file が除去される"""
        self.assertNotIn('checksums_file:', self.result)

    def test_work_dir_removed(self):
        """work_dir が除去される"""
        self.assertNotIn('work_dir:', self.result)

    def test_output_section_removed(self):
        """output セクションが除去される"""
        self.assertNotIn('output:', self.result)
        self.assertNotIn('header_comment:', self.result)
        self.assertNotIn('metadata_name:', self.result)

    def test_common_section_removed(self):
        """common セクションが除去される"""
        self.assertNotIn('common:', self.result)
        self.assertNotIn('max_workers:', self.result)
        self.assertNotIn('fallback_to_serial:', self.result)

    def test_root_dirs_preserved(self):
        """root_dirs は保持される"""
        self.assertIn('root_dirs:', self.result)
        self.assertIn('docs/rules/', self.result)

    def test_doc_types_map_preserved(self):
        """doc_types_map は保持される"""
        self.assertIn('doc_types_map:', self.result)

    def test_patterns_preserved(self):
        """patterns は保持される"""
        self.assertIn('patterns:', self.result)
        self.assertIn('target_glob:', self.result)
        self.assertIn('exclude:', self.result)

    def test_idempotent(self):
        """冪等性（FR-03-2）"""
        result1 = migrate_v2_to_v3(V2_CONTENT)
        result2 = migrate_v2_to_v3(V2_CONTENT)
        self.assertEqual(result1, result2)


# ===========================================================================
# 4. apply_migrations テスト（COMMON-REQ-001 コアロジック）
# ===========================================================================

class TestApplyMigrations(unittest.TestCase):
    """段階的マイグレーションのコアロジックのテスト"""

    def test_v1_to_v3_full_chain(self):
        """v1 → v3 の段階的マイグレーション（v1→v2→v3）"""
        result = apply_migrations(V1_CONTENT, 1)
        self.assertIn('# doc_structure_version: 3.0', result)
        self.assertNotIn('version: "1.0"', result)
        self.assertNotIn('toc_file:', result)
        self.assertNotIn('common:', result)
        self.assertIn('root_dirs:', result)

    def test_v2_to_v3(self):
        """v2 → v3 のマイグレーション"""
        result = apply_migrations(V2_CONTENT, 2)
        self.assertIn('# doc_structure_version: 3.0', result)
        self.assertNotIn('toc_file:', result)

    def test_v3_no_migration(self):
        """v3 はマイグレーション不要（FR-04-2 の等値ケース）"""
        result = apply_migrations(V3_CONTENT, 3)
        self.assertEqual(result, V3_CONTENT)

    def test_future_version_skip(self):
        """将来バージョン（v5）はマイグレーションスキップ（FR-04-2）"""
        future = '# doc_structure_version: 5.0\nrules:\n  root_dirs:\n    - rules/\n'
        result = apply_migrations(future, 5)
        self.assertEqual(result, future)

    def test_error_propagates(self):
        """マイグレーション関数のバグは例外として伝播する"""
        original_fn = MIGRATIONS[2]
        try:
            MIGRATIONS[2] = lambda content: 1 / 0  # ZeroDivisionError
            with self.assertRaises(ZeroDivisionError):
                apply_migrations(V1_CONTENT, 1)
        finally:
            MIGRATIONS[2] = original_fn


# ===========================================================================
# 5. get_migration_plan テスト
# ===========================================================================

class TestGetMigrationPlan(unittest.TestCase):
    """マイグレーションプラン取得のテスト"""

    def test_v1_to_v3_plan(self):
        """v1 → v3 のプランは2ステップ"""
        plan = get_migration_plan(1)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]['from'], 1)
        self.assertEqual(plan[0]['to'], 2)
        self.assertEqual(plan[1]['from'], 2)
        self.assertEqual(plan[1]['to'], 3)

    def test_v2_to_v3_plan(self):
        """v2 → v3 のプランは1ステップ"""
        plan = get_migration_plan(2)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['from'], 2)
        self.assertEqual(plan[0]['to'], 3)

    def test_v3_no_plan(self):
        """v3 は空プラン"""
        plan = get_migration_plan(3)
        self.assertEqual(plan, [])

    def test_future_no_plan(self):
        """将来バージョンは空プラン"""
        plan = get_migration_plan(5)
        self.assertEqual(plan, [])


# ===========================================================================
# 6. 定数テスト
# ===========================================================================

class TestConstants(unittest.TestCase):
    """定数の整合性テスト"""

    def test_current_version(self):
        """CURRENT_VERSION が 3 である"""
        self.assertEqual(CURRENT_VERSION, 3)

    def test_migrations_keys_match_current(self):
        """MIGRATIONS のキーが 2..CURRENT_VERSION の範囲"""
        keys = sorted(MIGRATIONS.keys())
        self.assertEqual(keys, list(range(2, CURRENT_VERSION + 1)))

    def test_all_migrations_callable(self):
        """全マイグレーション関数が呼び出し可能"""
        for v, fn in MIGRATIONS.items():
            self.assertTrue(callable(fn), f"MIGRATIONS[{v}] is not callable")


# ===========================================================================
# 7. CLI テスト
# ===========================================================================

class TestCLI(unittest.TestCase):
    """CLI インターフェースのテスト"""

    def _run(self, content, *args):
        """一時ファイルにコンテンツを書き込んで CLI を実行する"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / 'migrate_doc_structure.py'), tmp_path] + list(args),
                capture_output=True, text=True, timeout=10,
            )
            return result
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_check_v2(self):
        """--check: v2 ファイルのバージョン情報"""
        result = self._run(V2_CONTENT, '--check')
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data['detected_version'], 2)
        self.assertEqual(data['current_version'], 3)
        self.assertTrue(data['needs_migration'])

    def test_check_v3(self):
        """--check: v3 ファイルはマイグレーション不要"""
        result = self._run(V3_CONTENT, '--check')
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data['detected_version'], 3)
        self.assertFalse(data['needs_migration'])

    def test_dry_run_v2(self):
        """--dry-run: v2 → v3 のマイグレーションプラン"""
        result = self._run(V2_CONTENT, '--dry-run')
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(len(data['migrations']), 1)

    def test_dry_run_v3_no_changes(self):
        """--dry-run: v3 は変更なし（終了コード 2）"""
        result = self._run(V3_CONTENT, '--dry-run')
        self.assertEqual(result.returncode, 2)

    def test_migrate_v2_to_v3(self):
        """通常モード: v2 → v3 マイグレーション"""
        result = self._run(V2_CONTENT)
        self.assertEqual(result.returncode, 0)
        self.assertIn('# doc_structure_version: 3.0', result.stdout)
        self.assertNotIn('toc_file:', result.stdout)

    def test_migrate_v3_passthrough(self):
        """通常モード: v3 はそのまま出力"""
        result = self._run(V3_CONTENT)
        self.assertEqual(result.returncode, 0)
        self.assertIn('# doc_structure_version: 3.0', result.stdout)

    def test_file_not_found(self):
        """存在しないファイルでエラー"""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / 'migrate_doc_structure.py'), '/nonexistent.yaml'],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
