#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_structure.py のユニットテスト（doc-db 側）。

検証対象:
- load_doc_structure / parse_config による YAML 読み込み
- resolve_files（root_dirs ベース）の基本動作
- resolve_files_by_doc_type（doc_types_map 逆引き）の基本動作
- invert_doc_types_map の逆引き

forge 側のテストから移植した「コア機能のみの最小ケース」。
import パスは plugins/doc-db/scripts に切り替え、`import doc_structure as ds` で読み込む。
"""

import os
import sys
import tempfile
import unittest

# テスト対象モジュールの import パス
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-db', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import doc_structure as ds  # noqa: E402


# ---------------------------------------------------------------------------
# テスト用 YAML データ
# ---------------------------------------------------------------------------

BASIC_CONFIG = """\
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
    - docs/specs/design/
    - docs/specs/plan/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""

GLOB_CONFIG = """\
# doc_structure_version: 3.0

specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/requirements/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""


def _make_files(tmpdir, paths):
    """テスト用のディレクトリ構造とファイルを作成する。"""
    for path in paths:
        full = os.path.join(tmpdir, path)
        if path.endswith('/'):
            os.makedirs(full, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(f'# {os.path.basename(path)}\n')


class TestParseConfig(unittest.TestCase):
    """parse_config の基本動作。"""

    def test_basic_structure(self):
        config = ds.parse_config(BASIC_CONFIG)
        self.assertIn('rules', config)
        self.assertIn('specs', config)
        self.assertEqual(config['rules']['root_dirs'], ['docs/rules/'])
        self.assertEqual(
            config['specs']['root_dirs'],
            ['docs/specs/design/', 'docs/specs/plan/'],
        )

    def test_doc_types_map(self):
        config = ds.parse_config(BASIC_CONFIG)
        self.assertEqual(
            config['specs']['doc_types_map'],
            {'docs/specs/design/': 'design', 'docs/specs/plan/': 'plan'},
        )


class TestLoadDocStructure(unittest.TestCase):
    """load_doc_structure の基本動作。"""

    def test_load_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ds_path = os.path.join(tmpdir, '.doc_structure.yaml')
            with open(ds_path, 'w') as f:
                f.write(BASIC_CONFIG)
            config, content = ds.load_doc_structure(tmpdir)
            self.assertIn('rules', config)
            self.assertIn('doc_structure_version', content)

    def test_load_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                ds.load_doc_structure(tmpdir)


class TestResolveFiles(unittest.TestCase):
    """resolve_files（カテゴリ単位）の基本動作。"""

    def test_basic_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_files(tmpdir, [
                'docs/rules/a.md',
                'docs/rules/b.md',
            ])
            config = ds.parse_config(BASIC_CONFIG)
            result = ds.resolve_files(config, 'rules', tmpdir)
            self.assertEqual(len(result), 2)

    def test_glob_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_files(tmpdir, [
                'docs/specs/auth/design/a.md',
                'docs/specs/login/design/b.md',
                'docs/specs/auth/requirements/c.md',
            ])
            config = ds.parse_config(GLOB_CONFIG)
            result = ds.resolve_files(config, 'specs', tmpdir)
            self.assertEqual(len(result), 3)


class TestResolveFilesByDocType(unittest.TestCase):
    """resolve_files_by_doc_type の基本動作。"""

    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_files(tmpdir, [
                'docs/specs/design/a.md',
                'docs/specs/plan/b.md',
            ])
            config = ds.parse_config(BASIC_CONFIG)
            result = ds.resolve_files_by_doc_type(
                config, 'specs', 'design', tmpdir
            )
            self.assertEqual(len(result), 1)
            self.assertIn('docs/specs/design/a.md', result)

    def test_glob_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_files(tmpdir, [
                'docs/specs/auth/design/a.md',
                'docs/specs/login/design/b.md',
                'docs/specs/auth/requirements/c.md',
            ])
            config = ds.parse_config(GLOB_CONFIG)
            result = ds.resolve_files_by_doc_type(
                config, 'specs', 'design', tmpdir
            )
            self.assertEqual(len(result), 2)
            self.assertTrue(all('design' in f for f in result))

    def test_unknown_type(self):
        config = ds.parse_config(BASIC_CONFIG)
        result = ds.resolve_files_by_doc_type(
            config, 'specs', 'nonexistent', '/tmp'
        )
        self.assertEqual(result, [])


class TestInvertDocTypesMap(unittest.TestCase):
    """invert_doc_types_map（path→type → type→paths）の動作。"""

    def test_basic(self):
        dtm = {'docs/design/': 'design', 'docs/plan/': 'plan'}
        inverted = ds.invert_doc_types_map(dtm)
        self.assertEqual(inverted, {
            'design': ['docs/design/'],
            'plan': ['docs/plan/'],
        })

    def test_multiple_paths_same_type(self):
        dtm = {'a/': 'rule', 'b/': 'rule'}
        inverted = ds.invert_doc_types_map(dtm)
        self.assertEqual(len(inverted['rule']), 2)

    def test_empty(self):
        self.assertEqual(ds.invert_doc_types_map({}), {})


if __name__ == '__main__':
    unittest.main()
