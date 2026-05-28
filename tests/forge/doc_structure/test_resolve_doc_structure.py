#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_doc_structure.py のユニットテスト。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールの import
sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'forge',
    'skills', 'doc-structure', 'scripts'
))
import resolve_doc_structure as rds


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
  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/rules/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude: []
  output:
    header_comment: "Development documentation search index"
    metadata_name: "Development Document Search Index"

specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
  toc_file: .claude/doc-advisor/toc/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/toc/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/specs/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude: []
  output:
    header_comment: "Project specification document search index"
    metadata_name: "Project Specification Document Search Index"

common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
"""

GLOB_CONFIG = """\
# doc_structure_version: 3.0

specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirement/": requirement
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

DOUBLESTAR_GLOB_CONFIG = """\
# doc_structure_version: 3.0

specs:
  root_dirs:
    - "docs/specs/**/design/"
    - "docs/specs/**/plan/"
    - "docs/specs/**/requirements/"
  doc_types_map:
    "docs/specs/**/design/": design
    "docs/specs/**/plan/": plan
    "docs/specs/**/requirements/": requirement
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

DOUBLESTAR_EXCLUDE_CONFIG = """\
specs:
  root_dirs:
    - "docs/specs/**/design/"
  doc_types_map:
    "docs/specs/**/design/": design
  patterns:
    target_glob: "**/*.md"
    exclude:
      - archived
"""

EXCLUDE_CONFIG = """\
specs:
  root_dirs:
    - "docs/specs/*/design/"
  doc_types_map:
    "docs/specs/*/design/": design
  patterns:
    target_glob: "**/*.md"
    exclude:
      - archived
      - _template
"""

MINIMAL_CONFIG = """\
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
"""

NO_VERSION_CONFIG = """\
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
"""


# ---------------------------------------------------------------------------
# テストヘルパー
# ---------------------------------------------------------------------------

def create_test_project(tmpdir, structure):
    """テスト用ディレクトリ構造を作成する。

    Args:
        tmpdir: 一時ディレクトリのパス
        structure: ファイルパスのリスト（ディレクトリは末尾 /）
    """
    for path in structure:
        full = os.path.join(tmpdir, path)
        if path.endswith('/'):
            os.makedirs(full, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(f'# {os.path.basename(path)}\n')


# ===========================================================================
# テストクラス
# ===========================================================================

class TestGetVersion(unittest.TestCase):
    """バージョン検出のテスト"""

    def test_get_version_normal(self):
        self.assertEqual(rds.get_version(BASIC_CONFIG), '3.0')

    def test_get_version_none(self):
        self.assertIsNone(rds.get_version(NO_VERSION_CONFIG))

    def test_get_major_version(self):
        self.assertEqual(rds.get_major_version(BASIC_CONFIG), 3)

    def test_get_major_version_none(self):
        self.assertIsNone(rds.get_major_version(NO_VERSION_CONFIG))

    def test_get_version_different_versions(self):
        content = '# doc_structure_version: 3.1\nrules:\n  root_dirs:\n    - r/\n'
        self.assertEqual(rds.get_version(content), '3.1')
        self.assertEqual(rds.get_major_version(content), 3)


class TestNormalizePath(unittest.TestCase):
    """パス正規化のテスト"""

    def test_ascii_unchanged(self):
        self.assertEqual(rds.normalize_path('docs/rules/'), 'docs/rules/')

    def test_nfc_normalization(self):
        import unicodedata
        # NFD 形式の「プ」
        nfd = unicodedata.normalize('NFD', 'プラグイン')
        result = rds.normalize_path(nfd)
        self.assertEqual(result, unicodedata.normalize('NFC', 'プラグイン'))


class TestParseConfig(unittest.TestCase):
    """config.yaml パーサーのテスト"""

    def test_basic_structure(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertIn('rules', config)
        self.assertIn('specs', config)
        self.assertIn('common', config)

    def test_root_dirs(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(config['rules']['root_dirs'], ['docs/rules/'])
        self.assertEqual(
            config['specs']['root_dirs'],
            ['docs/specs/design/', 'docs/specs/plan/']
        )

    def test_doc_types_map(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(config['rules']['doc_types_map'], {'docs/rules/': 'rule'})
        self.assertEqual(
            config['specs']['doc_types_map'],
            {'docs/specs/design/': 'design', 'docs/specs/plan/': 'plan'}
        )

    def test_glob_root_dirs(self):
        config = rds.parse_config(GLOB_CONFIG)
        self.assertEqual(
            config['specs']['root_dirs'],
            ['docs/specs/*/design/', 'docs/specs/*/plan/', 'docs/specs/*/requirement/']
        )

    def test_glob_doc_types_map(self):
        config = rds.parse_config(GLOB_CONFIG)
        dtm = config['specs']['doc_types_map']
        self.assertEqual(dtm['docs/specs/*/design/'], 'design')
        self.assertEqual(dtm['docs/specs/*/plan/'], 'plan')
        self.assertEqual(dtm['docs/specs/*/requirement/'], 'requirement')

    def test_patterns_exclude(self):
        config = rds.parse_config(EXCLUDE_CONFIG)
        self.assertEqual(
            config['specs']['patterns']['exclude'],
            ['archived', '_template']
        )

    def test_patterns_empty_exclude(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(config['rules']['patterns']['exclude'], [])

    def test_scalar_values(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(config['rules']['toc_file'],
                         '.claude/doc-advisor/toc/rules/rules_toc.yaml')

    def test_common_section(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(config['common']['parallel']['max_workers'], 5)
        self.assertTrue(config['common']['parallel']['fallback_to_serial'])

    def test_inline_array(self):
        content = 'rules:\n  root_dirs: [a/, b/]\n  doc_types_map:\n    a/: rule\n'
        config = rds.parse_config(content)
        self.assertEqual(config['rules']['root_dirs'], ['a/', 'b/'])

    def test_minimal(self):
        config = rds.parse_config(MINIMAL_CONFIG)
        self.assertEqual(config['rules']['root_dirs'], ['rules/'])
        self.assertEqual(config['rules']['doc_types_map'], {'rules/': 'rule'})

    def test_comments_skipped(self):
        content = '# comment\nrules:\n  # inner comment\n  root_dirs:\n    - r/\n'
        config = rds.parse_config(content)
        self.assertEqual(config['rules']['root_dirs'], ['r/'])

    def test_empty_section(self):
        content = 'rules:\n  root_dirs:\n    - r/\nspecs:\n'
        config = rds.parse_config(content)
        self.assertIn('specs', config)

    def test_output_subsection(self):
        config = rds.parse_config(BASIC_CONFIG)
        self.assertEqual(
            config['rules']['output']['header_comment'],
            'Development documentation search index'
        )


class TestExpandGlobs(unittest.TestCase):
    """glob 展開のテスト"""

    def test_no_glob(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'docs', 'rules'))
            result = rds.expand_globs(['docs/rules/'], tmpdir)
            self.assertEqual(result, ['docs/rules/'])

    def test_glob_expansion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/',
                'docs/specs/login/design/',
            ])
            result = rds.expand_globs(['docs/specs/*/design/'], tmpdir)
            self.assertEqual(len(result), 2)
            self.assertIn('docs/specs/auth/design/', result)
            self.assertIn('docs/specs/login/design/', result)

    def test_glob_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = rds.expand_globs(['docs/specs/*/design/'], tmpdir)
            # マッチなしの場合は元のリストを返す
            self.assertEqual(result, ['docs/specs/*/design/'])

    def test_mixed_glob_and_literal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/rules/',
                'docs/specs/auth/design/',
            ])
            result = rds.expand_globs(
                ['docs/rules/', 'docs/specs/*/design/'], tmpdir
            )
            self.assertEqual(len(result), 2)
            self.assertIn('docs/rules/', result)
            self.assertIn('docs/specs/auth/design/', result)


class TestIsExcluded(unittest.TestCase):
    """exclude 判定のテスト"""

    def test_no_exclude(self):
        self.assertFalse(
            rds.is_excluded(Path('/root/docs/a.md'), Path('/root'), [])
        )

    def test_dir_name_match(self):
        self.assertTrue(
            rds.is_excluded(
                Path('/root/docs/archived/a.md'),
                Path('/root'),
                ['archived']
            )
        )

    def test_dir_name_no_match(self):
        self.assertFalse(
            rds.is_excluded(
                Path('/root/docs/active/a.md'),
                Path('/root'),
                ['archived']
            )
        )

    def test_filename_not_excluded(self):
        """ファイル名は exclude 対象外（ディレクトリ名のみ）"""
        self.assertFalse(
            rds.is_excluded(
                Path('/root/docs/archived.md'),
                Path('/root'),
                ['archived']
            )
        )

    def test_path_pattern(self):
        self.assertTrue(
            rds.is_excluded(
                Path('/root/docs/old/archive/a.md'),
                Path('/root'),
                ['old/archive']
            )
        )

    def test_multiple_patterns(self):
        self.assertTrue(
            rds.is_excluded(
                Path('/root/docs/_template/a.md'),
                Path('/root'),
                ['archived', '_template']
            )
        )


class TestCollectMdFiles(unittest.TestCase):
    """ファイル収集のテスト"""

    def test_collect_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/rules/a.md',
                'docs/rules/b.md',
                'docs/rules/c.txt',
            ])
            result = rds.collect_md_files(
                os.path.join(tmpdir, 'docs/rules'), [], tmpdir
            )
            self.assertEqual(len(result), 2)
            self.assertTrue(all(f.endswith('.md') for f in result))

    def test_collect_with_exclude(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/rules/a.md',
                'docs/rules/archived/b.md',
            ])
            result = rds.collect_md_files(
                os.path.join(tmpdir, 'docs/rules'), ['archived'], tmpdir
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], 'docs/rules/a.md')

    def test_collect_nonexistent_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = rds.collect_md_files(
                os.path.join(tmpdir, 'nonexistent'), [], tmpdir
            )
            self.assertEqual(result, [])

    def test_collect_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/rules/a.md',
                'docs/rules/sub/b.md',
                'docs/rules/sub/deep/c.md',
            ])
            result = rds.collect_md_files(
                os.path.join(tmpdir, 'docs/rules'), [], tmpdir
            )
            self.assertEqual(len(result), 3)


class TestInvertDocTypesMap(unittest.TestCase):
    """doc_types_map 逆引きのテスト"""

    def test_basic(self):
        dtm = {'docs/design/': 'design', 'docs/plan/': 'plan'}
        inverted = rds.invert_doc_types_map(dtm)
        self.assertEqual(inverted, {
            'design': ['docs/design/'],
            'plan': ['docs/plan/'],
        })

    def test_multiple_paths_same_type(self):
        dtm = {'a/': 'rule', 'b/': 'rule'}
        inverted = rds.invert_doc_types_map(dtm)
        self.assertEqual(len(inverted['rule']), 2)

    def test_empty(self):
        self.assertEqual(rds.invert_doc_types_map({}), {})


class TestMatchPathToDocType(unittest.TestCase):
    """パスから doc_type 判定のテスト"""

    def test_literal_match(self):
        dtm = {'docs/rules/': 'rule'}
        result = rds.match_path_to_doc_type('docs/rules/a.md', dtm, '/tmp')
        self.assertEqual(result, 'rule')

    def test_no_match(self):
        dtm = {'docs/rules/': 'rule'}
        result = rds.match_path_to_doc_type('src/main.py', dtm, '/tmp')
        self.assertIsNone(result)

    def test_glob_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, ['docs/specs/auth/design/'])
            dtm = {'docs/specs/*/design/': 'design'}
            result = rds.match_path_to_doc_type(
                'docs/specs/auth/design/a.md', dtm, tmpdir
            )
            self.assertEqual(result, 'design')


class TestDetectFeatures(unittest.TestCase):
    """Feature 検出のテスト"""

    def test_single_feature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/forge/design/',
                'docs/specs/forge/plan/',
            ])
            config = rds.parse_config(GLOB_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['forge'])

    def test_multiple_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/',
                'docs/specs/login/design/',
                'docs/specs/payment/plan/',
            ])
            config = rds.parse_config(GLOB_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['auth', 'login', 'payment'])

    def test_no_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = rds.parse_config(GLOB_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, [])

    def test_exclude_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/',
                'docs/specs/archived/design/',
            ])
            config = rds.parse_config(EXCLUDE_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['auth'])

    def test_no_glob_no_features(self):
        """glob パターンのない設定では Feature は検出されない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, ['docs/specs/design/'])
            config = rds.parse_config(BASIC_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, [])

    def test_doublestar_mixed_depth(self):
        """** パターンで1階層と2階層の混在から全 Feature を検出"""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/forge/design/',
                'docs/specs/forge/review-PR/design/',
                'docs/specs/doc-advisor/design/',
                'docs/specs/doc-advisor/semantic-query/design/',
            ])
            config = rds.parse_config(DOUBLESTAR_GLOB_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['doc-advisor', 'forge'])

    def test_doublestar_dedup(self):
        """同一 Feature が複数深さに存在しても重複しない"""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/forge/design/',
                'docs/specs/forge/plan/',
                'docs/specs/forge/review-PR/design/',
                'docs/specs/forge/review-PR/plan/',
            ])
            config = rds.parse_config(DOUBLESTAR_GLOB_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['forge'])

    def test_doublestar_exclude(self):
        """** パターンでも exclude が機能する"""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/',
                'docs/specs/archived/design/',
                'docs/specs/auth/sub/design/',
            ])
            config = rds.parse_config(DOUBLESTAR_EXCLUDE_CONFIG)
            features = rds.detect_features(config, tmpdir)
            self.assertEqual(features, ['auth'])


class TestExtractFeatureFromMatch(unittest.TestCase):
    """Feature 名抽出のテスト"""

    def test_basic(self):
        result = rds._extract_feature_from_match(
            'docs/specs/*/design', 'docs/specs/forge/design'
        )
        self.assertEqual(result, 'forge')

    def test_mismatch_length(self):
        result = rds._extract_feature_from_match(
            'docs/specs/*/design', 'docs/specs/forge/design/sub'
        )
        self.assertIsNone(result)

    def test_doublestar_single_depth(self):
        """** パターンで1階層マッチ"""
        result = rds._extract_feature_from_match(
            'docs/specs/**/design', 'docs/specs/forge/design'
        )
        self.assertEqual(result, 'forge')

    def test_doublestar_two_depth(self):
        """** パターンで2階層マッチ — 最初のセグメントが Feature"""
        result = rds._extract_feature_from_match(
            'docs/specs/**/design', 'docs/specs/forge/review-PR/design'
        )
        self.assertEqual(result, 'forge')

    def test_doublestar_two_depth_another(self):
        """** パターンで別の Feature の2階層マッチ"""
        result = rds._extract_feature_from_match(
            'docs/specs/**/design', 'docs/specs/doc-advisor/semantic-query/design'
        )
        self.assertEqual(result, 'doc-advisor')

    def test_doublestar_zero_capture(self):
        """** が0セグメントをキャプチャした場合は None"""
        result = rds._extract_feature_from_match(
            'docs/specs/**/design', 'docs/specs/design'
        )
        self.assertIsNone(result)

    def test_doublestar_multiple_rejected(self):
        """複数 ** を含むパターンは未対応で None"""
        result = rds._extract_feature_from_match(
            'docs/**/specs/**/design', 'docs/a/specs/b/design'
        )
        self.assertIsNone(result)

    def test_doublestar_prefix_star_priority(self):
        """prefix 内の * は ** より優先される"""
        result = rds._extract_feature_from_match(
            'docs/*/specs/**/design', 'docs/myproject/specs/forge/design'
        )
        self.assertEqual(result, 'myproject')

    def test_doublestar_suffix_star(self):
        """suffix 内の * が正しくマッチする"""
        result = rds._extract_feature_from_match(
            'docs/specs/**/*/design', 'docs/specs/forge/review-PR/design'
        )
        self.assertEqual(result, 'review-PR')

    def test_backward_compat_single_star(self):
        """従来の * パターンが変わらず動作する"""
        result = rds._extract_feature_from_match(
            'docs/specs/*/design', 'docs/specs/auth/design'
        )
        self.assertEqual(result, 'auth')

    def test_no_wildcard(self):
        """ワイルドカードなしのパターンは None"""
        result = rds._extract_feature_from_match(
            'docs/specs/design', 'docs/specs/design'
        )
        self.assertIsNone(result)


class TestResolveFiles(unittest.TestCase):
    """ファイル解決のテスト"""

    def test_basic_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/rules/a.md',
                'docs/rules/b.md',
            ])
            config = rds.parse_config(BASIC_CONFIG)
            result = rds.resolve_files(config, 'rules', tmpdir)
            self.assertEqual(len(result), 2)

    def test_glob_resolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/a.md',
                'docs/specs/login/design/b.md',
                'docs/specs/auth/plan/c.md',
            ])
            config = rds.parse_config(GLOB_CONFIG)
            result = rds.resolve_files(config, 'specs', tmpdir)
            self.assertEqual(len(result), 3)

    def test_deduplication(self):
        """同一ファイルが複数パスにマッチしても1回のみ"""
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, ['docs/rules/a.md'])
            content = 'rules:\n  root_dirs:\n    - docs/rules/\n    - docs/rules/\n  doc_types_map:\n    docs/rules/: rule\n'
            config = rds.parse_config(content)
            result = rds.resolve_files(config, 'rules', tmpdir)
            self.assertEqual(len(result), 1)

    def test_empty_category(self):
        config = rds.parse_config(MINIMAL_CONFIG)
        result = rds.resolve_files(config, 'specs', '/tmp')
        self.assertEqual(result, [])


class TestResolveFilesByDocType(unittest.TestCase):
    """doc_type 別ファイル解決のテスト"""

    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/design/a.md',
                'docs/specs/plan/b.md',
            ])
            config = rds.parse_config(BASIC_CONFIG)
            result = rds.resolve_files_by_doc_type(config, 'specs', 'design', tmpdir)
            self.assertEqual(len(result), 1)
            self.assertIn('docs/specs/design/a.md', result)

    def test_glob(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            create_test_project(tmpdir, [
                'docs/specs/auth/design/a.md',
                'docs/specs/login/design/b.md',
                'docs/specs/auth/plan/c.md',
            ])
            config = rds.parse_config(GLOB_CONFIG)
            result = rds.resolve_files_by_doc_type(config, 'specs', 'design', tmpdir)
            self.assertEqual(len(result), 2)
            self.assertTrue(all('design' in f for f in result))

    def test_nonexistent_type(self):
        config = rds.parse_config(BASIC_CONFIG)
        result = rds.resolve_files_by_doc_type(config, 'specs', 'api', '/tmp')
        self.assertEqual(result, [])


class TestLoadDocStructure(unittest.TestCase):
    """ファイル読み込みのテスト"""

    def test_load_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ds_path = os.path.join(tmpdir, '.doc_structure.yaml')
            with open(ds_path, 'w') as f:
                f.write(BASIC_CONFIG)
            config, content = rds.load_doc_structure(tmpdir)
            self.assertIn('rules', config)
            self.assertIn('doc_structure_version', content)

    def test_load_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                rds.load_doc_structure(tmpdir)

    def test_load_custom_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = os.path.join(tmpdir, 'custom.yaml')
            with open(custom, 'w') as f:
                f.write(MINIMAL_CONFIG)
            config, _ = rds.load_doc_structure(tmpdir, custom)
            self.assertIn('rules', config)


class TestFindProjectRoot(unittest.TestCase):
    """プロジェクトルート検出のテスト"""

    def test_with_explicit_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_tmpdir = os.path.realpath(tmpdir)
            result = rds.find_project_root(real_tmpdir)
            self.assertEqual(result, real_tmpdir)

    def test_without_args_returns_cwd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_tmpdir = os.path.realpath(tmpdir)
            original_cwd = os.getcwd()
            try:
                os.chdir(real_tmpdir)
                result = rds.find_project_root()
                self.assertEqual(result, real_tmpdir)
            finally:
                os.chdir(original_cwd)

    def test_resolves_symlinks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real_tmpdir = os.path.realpath(tmpdir)
            result = rds.find_project_root(tmpdir)
            self.assertEqual(result, real_tmpdir)


# ---------------------------------------------------------------------------
# テスト用 YAML データ（バリデーション用）
# ---------------------------------------------------------------------------

V1_CONFIG = """\
version: "1.0"

rules:
  - docs/rules/
specs:
  - docs/specs/
"""

V2_WITH_ROOT_DIRS_CONFIG = """\
# doc_structure_version: 2.0

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule

specs:
  root_dirs:
    - docs/specs/design/
  doc_types_map:
    docs/specs/design/: design
"""

NO_ROOT_DIRS_CONFIG = """\
# doc_structure_version: 3.0

rules:
  doc_types_map:
    docs/rules/: rule

specs:
  doc_types_map:
    docs/specs/design/: design
"""

EMPTY_ROOT_DIRS_CONFIG = """\
# doc_structure_version: 3.0

rules:
  root_dirs: []
  doc_types_map:
    docs/rules/: rule
"""


class TestValidateDocStructure(unittest.TestCase):
    """バリデーションのテスト"""

    def test_valid_v3(self):
        """v3 フォーマット → valid"""
        config = rds.parse_config(BASIC_CONFIG)
        result = rds.validate_doc_structure(config, BASIC_CONFIG)
        self.assertTrue(result['valid'])

    def test_missing_root_dirs(self):
        """root_dirs なし → invalid"""
        config = rds.parse_config(NO_ROOT_DIRS_CONFIG)
        result = rds.validate_doc_structure(config, NO_ROOT_DIRS_CONFIG)
        self.assertFalse(result['valid'])
        self.assertIn('root_dirs', result['error'])
        self.assertIn('suggestion', result)

    def test_v1_format(self):
        """v1 形式 → invalid（root_dirs が存在しない）"""
        config = rds.parse_config(V1_CONFIG)
        result = rds.validate_doc_structure(config, V1_CONFIG)
        self.assertFalse(result['valid'])
        self.assertIn('root_dirs', result['error'])

    def test_v1_format_with_comment_version(self):
        """v1 形式（コメントでバージョン明示）→ invalid + 旧フォーマットメッセージ"""
        content = "# doc_structure_version: 1.0\nrules:\n  - docs/rules/\n"
        config = rds.parse_config(content)
        result = rds.validate_doc_structure(config, content)
        self.assertFalse(result['valid'])
        self.assertIn('旧フォーマット', result['error'])
        self.assertIn('v1', result['error'])

    def test_v2_format_with_root_dirs(self):
        """v2 形式 + root_dirs あり → valid（警告付き）"""
        config = rds.parse_config(V2_WITH_ROOT_DIRS_CONFIG)
        result = rds.validate_doc_structure(config, V2_WITH_ROOT_DIRS_CONFIG)
        self.assertTrue(result['valid'])
        self.assertIn('version_warning', result)

    def test_no_version_with_root_dirs(self):
        """バージョンコメントなし + root_dirs あり → valid"""
        config = rds.parse_config(NO_VERSION_CONFIG)
        result = rds.validate_doc_structure(config, NO_VERSION_CONFIG)
        self.assertTrue(result['valid'])

    def test_no_version_no_root_dirs(self):
        """バージョンコメントなし + root_dirs なし → invalid"""
        content = "rules:\n  doc_types_map:\n    docs/: rule\n"
        config = rds.parse_config(content)
        result = rds.validate_doc_structure(config, content)
        self.assertFalse(result['valid'])
        self.assertIn('root_dirs', result['error'])

    def test_empty_root_dirs(self):
        """root_dirs が空配列 → valid（設定として正当）"""
        config = rds.parse_config(EMPTY_ROOT_DIRS_CONFIG)
        result = rds.validate_doc_structure(config, EMPTY_ROOT_DIRS_CONFIG)
        self.assertTrue(result['valid'])

    def test_cli_type_with_invalid(self):
        """--type all で旧フォーマット → exit(1) + error JSON"""
        import subprocess
        with tempfile.TemporaryDirectory() as tmpdir:
            ds_path = os.path.join(tmpdir, '.doc_structure.yaml')
            with open(ds_path, 'w') as f:
                f.write(V1_CONFIG)
            os.makedirs(os.path.join(tmpdir, '.git'))

            script = os.path.join(
                os.path.dirname(__file__), '..', '..', '..', 'plugins',
                'forge', 'skills', 'doc-structure', 'scripts',
                'resolve_doc_structure.py'
            )
            proc = subprocess.run(
                [sys.executable, script, '--type', 'all',
                 '--project-root', tmpdir],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 1)
            data = json.loads(proc.stdout)
            self.assertEqual(data['status'], 'error')
            self.assertIn('suggestion', data)


if __name__ == '__main__':
    unittest.main()
