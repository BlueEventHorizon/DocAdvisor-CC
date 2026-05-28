#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config フォーマットマイグレーション（v1→v2→v3）テスト。

test_migration.sh からの移行:
- バージョン検出（v1, v2, v3, v4）
- v1→v3 チェーンマイグレーション
- v2→v3 内部フィールド除去
- v3→v3 no-op
- 冪等性（2回適用で同結果）
- ロールバック（マイグレーション失敗時に元データ返却）
- load_config() の v1 形式ファイル統合テスト
"""

import copy
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import toc_utils


class TestVersionDetection(unittest.TestCase):
    """バージョン検出テスト"""

    def test_no_version_comment_returns_v1(self):
        """バージョンコメントなし → v1"""
        content = 'rules:\n  rule:\n    paths:\n      - rules/'
        self.assertEqual(toc_utils._detect_version(content), 1)

    def test_version_2(self):
        """# doc_structure_version: 2.0 → 2"""
        content = '# doc_structure_version: 2.0\nrules:\n'
        self.assertEqual(toc_utils._detect_version(content), 2)

    def test_version_3(self):
        """# doc_structure_version: 3.0 → 3"""
        content = '# doc_structure_version: 3.0\nrules:\n'
        self.assertEqual(toc_utils._detect_version(content), 3)

    def test_version_4_future(self):
        """# doc_structure_version: 4.0 → 4"""
        content = '# doc_structure_version: 4.0\nrules:\n'
        self.assertEqual(toc_utils._detect_version(content), 4)

    def test_version_comment_with_extra_spaces(self):
        """バージョンコメントにスペースが含まれていても検出"""
        content = '#  doc_structure_version:  3.0\nrules:\n'
        # 正規表現 r'^#\s*doc_structure_version:\s*(\d+)' でマッチ
        self.assertEqual(toc_utils._detect_version(content), 3)

    def test_version_comment_after_yaml_body_detected(self):
        """YAML本文行後のバージョンコメントも検出される（全行走査）"""
        content = 'rules:\n  root_dirs:\n    - rules/\n# doc_structure_version: 3.0\n'
        # 全行走査により位置に関わらずバージョンコメントを検出する
        self.assertEqual(toc_utils._detect_version(content), 3)


class TestV1ToV3ChainMigration(unittest.TestCase):
    """v1→v3 チェーンマイグレーションテスト"""

    def test_single_category(self):
        """v1 単一カテゴリ → v3"""
        v1_content = 'rules:\n  rule:\n    paths:\n      - rules/'
        parsed = toc_utils._parse_config_yaml(v1_content)
        result = toc_utils.apply_migrations(parsed, 1)

        self.assertEqual(result['rules']['root_dirs'], ['rules/'])
        self.assertEqual(result['rules']['doc_types_map'], {'rules/': 'rule'})
        # v3: 内部フィールドなし
        self.assertNotIn('toc_file', result.get('rules', {}))
        self.assertNotIn('common', result)

    def test_multiple_paths(self):
        """v1 複数パス → v3"""
        v1_content = (
            'rules:\n  rule:\n    paths:\n      - rules/\n      - guidelines/\n'
            'specs:\n  requirement:\n    paths:\n      - specs/requirements/\n'
            '  design:\n    paths:\n      - specs/design/'
        )
        parsed = toc_utils._parse_config_yaml(v1_content)
        result = toc_utils.apply_migrations(parsed, 1)

        # rules
        self.assertEqual(result['rules']['root_dirs'], ['rules/', 'guidelines/'])
        self.assertEqual(
            result['rules']['doc_types_map'],
            {'rules/': 'rule', 'guidelines/': 'rule'}
        )
        # specs
        self.assertIn('specs/requirements/', result['specs']['root_dirs'])
        self.assertIn('specs/design/', result['specs']['root_dirs'])
        self.assertEqual(
            result['specs']['doc_types_map']['specs/requirements/'],
            'requirement'
        )
        self.assertEqual(
            result['specs']['doc_types_map']['specs/design/'],
            'design'
        )


class TestV2ToV3Migration(unittest.TestCase):
    """v2→v3 内部フィールド除去テスト"""

    def test_internal_fields_removed(self):
        """v2 の内部フィールド（toc_file, checksums_file, work_dir, output）が除去される"""
        v2_content = (
            '# doc_structure_version: 2.0\n'
            'rules:\n'
            '  root_dirs:\n    - rules/\n'
            '  doc_types_map:\n    rules/: rule\n'
            '  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml\n'
            '  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml\n'
            '  work_dir: .claude/doc-advisor/toc/rules/.toc_work/\n'
            '  output:\n    header_comment: test\n'
            'common:\n  parallel:\n    max_workers: 5'
        )
        parsed = toc_utils._parse_config_yaml(v2_content)
        result = toc_utils.apply_migrations(parsed, 2)

        self.assertNotIn('toc_file', result.get('rules', {}))
        self.assertNotIn('checksums_file', result.get('rules', {}))
        self.assertNotIn('work_dir', result.get('rules', {}))
        self.assertNotIn('output', result.get('rules', {}))
        self.assertNotIn('common', result)
        # 構造は保持
        self.assertEqual(result['rules']['root_dirs'], ['rules/'])
        self.assertEqual(result['rules']['doc_types_map'], {'rules/': 'rule'})


class TestV3NoOp(unittest.TestCase):
    """v3→v3 no-op テスト"""

    def test_v3_unchanged(self):
        """v3 形式にマイグレーションを適用してもデータは変わらない"""
        v3_content = (
            '# doc_structure_version: 3.0\n'
            'rules:\n'
            '  root_dirs:\n    - rules/\n'
            '  doc_types_map:\n    rules/: rule\n'
            '  patterns:\n    target_glob: "**/*.md"\n    exclude: []'
        )
        parsed = toc_utils._parse_config_yaml(v3_content)
        original = copy.deepcopy(parsed)
        result = toc_utils.apply_migrations(parsed, 3)

        self.assertEqual(result, original)

    def test_future_version_unchanged(self):
        """v4（未来バージョン）でもデータは変わらない"""
        data = {'rules': {'root_dirs': ['rules/']}}
        result = toc_utils.apply_migrations(data, 4)
        self.assertEqual(result, data)
        self.assertIn('root_dirs', result.get('rules', {}))


class TestIdempotency(unittest.TestCase):
    """冪等性テスト（2回適用で同結果）"""

    def test_v1_migration_idempotent(self):
        """v1 マイグレーションを2回適用しても結果が同じ"""
        v1_content = 'rules:\n  rule:\n    paths:\n      - rules/'
        parsed = toc_utils._parse_config_yaml(v1_content)
        first = toc_utils.apply_migrations(copy.deepcopy(parsed), 1)
        second = toc_utils.apply_migrations(copy.deepcopy(first), 1)

        self.assertEqual(first, second)

    def test_v2_migration_idempotent(self):
        """v2 マイグレーションを2回適用しても結果が同じ"""
        v2_data = {
            'rules': {
                'root_dirs': ['rules/'],
                'doc_types_map': {'rules/': 'rule'},
                'toc_file': 'test.yaml',
            },
            'common': {'parallel': {'max_workers': 5}},
        }
        first = toc_utils.apply_migrations(copy.deepcopy(v2_data), 2)
        second = toc_utils.apply_migrations(copy.deepcopy(first), 2)

        self.assertEqual(first, second)


class TestRollback(unittest.TestCase):
    """ロールバックテスト（マイグレーション失敗時に元データ返却）"""

    def test_rollback_on_failure(self):
        """マイグレーション失敗時にオリジナルデータが返される"""
        v1_content = 'rules:\n  rule:\n    paths:\n      - custom_rules/'
        parsed = toc_utils._parse_config_yaml(v1_content)
        original_copy = copy.deepcopy(parsed)

        # v3 マイグレーションを失敗させる
        def _fail_migration(p):
            raise RuntimeError('テスト用の意図的な失敗')

        saved_migrations = dict(toc_utils.MIGRATIONS)
        toc_utils.MIGRATIONS[3] = _fail_migration

        try:
            result = toc_utils.apply_migrations(parsed, 1)
            # オリジナルデータが返されること
            self.assertEqual(result, original_copy)
        finally:
            toc_utils.MIGRATIONS.clear()
            toc_utils.MIGRATIONS.update(saved_migrations)


class TestLoadConfigV1Integration(unittest.TestCase):
    """load_config() の v1 形式ファイル統合テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, '.git'))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_v1_file_migrated_and_defaults_merged(self):
        """v1 形式の .doc_structure.yaml が load_config で正しく処理される"""
        v1_content = (
            'rules:\n  rule:\n    paths:\n      - rules/\n'
            'specs:\n  requirement:\n    paths:\n      - docs/requirements/\n'
            '  design:\n    paths:\n      - docs/design/'
        )
        with open(os.path.join(self.tmpdir, '.doc_structure.yaml'), 'w') as f:
            f.write(v1_content)

        with patch.object(Path, 'cwd', return_value=Path(self.tmpdir)):
            config = toc_utils.load_config('rules')

        # v1→v3 マイグレーション済み
        self.assertIn('root_dirs', config)
        self.assertEqual(config['root_dirs'], ['rules/'])
        # コードデフォルトがマージされている
        self.assertIn('toc_file', config)

    def test_v2_file_migrated(self):
        """v2 形式の .doc_structure.yaml が load_config で正しく処理される"""
        v2_content = (
            '# doc_structure_version: 2.0\n'
            'rules:\n'
            '  root_dirs:\n    - my_rules/\n'
            '  doc_types_map:\n    my_rules/: rule\n'
            '  toc_file: old_path.yaml\n'
            '  checksums_file: old_checksums.yaml\n'
        )
        with open(os.path.join(self.tmpdir, '.doc_structure.yaml'), 'w') as f:
            f.write(v2_content)

        with patch.object(Path, 'cwd', return_value=Path(self.tmpdir)):
            config = toc_utils.load_config('rules')

        self.assertEqual(config['root_dirs'], ['my_rules/'])
        # v2→v3 で内部フィールドが除去され、コードデフォルトがマージされる
        # toc_file はコードデフォルト値
        self.assertEqual(
            config['toc_file'],
            '.claude/doc-advisor/toc/rules/rules_toc.yaml'
        )


if __name__ == '__main__':
    unittest.main()
