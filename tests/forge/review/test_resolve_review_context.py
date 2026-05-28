#!/usr/bin/env python3
"""
resolve_review_context.py のテスト

config.yaml 互換形式の .doc_structure.yaml を使用した種別判定、
Feature 検出、exclude 判定をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.review.test_resolve_review_context -v
"""

import io
import json
import os
import sys
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'skills' / 'review' / 'scripts'))

import resolve_review_context as rrc
from resolve_review_context import (
    parse_doc_structure,
    parse_args,
    get_uncommitted_changed_files,
    _is_excluded,
    _get_all_excludes,
    _doc_type_to_review_type,
    detect_type_from_doc_structure,
    detect_type_from_path,
    detect_type_from_dir,
    detect_features_from_doc_structure,
    get_rules_paths,
    get_specs_paths_by_type,
    _detect_generic_type,
    find_feature_subdirs,
    find_target_files,
)


# ---------------------------------------------------------------------------
# テスト用 config.yaml 互換テンプレート
# ---------------------------------------------------------------------------

CONFIG_WITH_EXCLUDE = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
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
    - "specs/*/requirements/"
    - "specs/*/design/"
  doc_types_map:
    "specs/*/requirements/": requirement
    "specs/*/design/": design
  toc_file: .claude/doc-advisor/toc/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/toc/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/specs/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude:
      - archived
      - _template
  output:
    header_comment: "Project specification document search index for query-specs skill"
    metadata_name: "Project Specification Document Search Index"

common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
"""

CONFIG_NO_EXCLUDE = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
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
    - "specs/*/requirements/"
    - specs/design/
  doc_types_map:
    "specs/*/requirements/": requirement
    specs/design/: design
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
"""

CONFIG_FLAT = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
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
    - specs/requirements/
    - specs/design/
    - specs/plan/
  doc_types_map:
    specs/requirements/: requirement
    specs/design/: design
    specs/plan/: plan
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
"""

CONFIG_MIXED_EXCLUDE = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/rules/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude:
      - deprecated
  output:
    header_comment: "Development documentation search index for query-rules skill"
    metadata_name: "Development Documentation Search Index"

specs:
  root_dirs:
    - "specs/*/requirements/"
    - "modules/*/requirements/"
    - "specs/*/design/"
  doc_types_map:
    "specs/*/requirements/": requirement
    "modules/*/requirements/": requirement
    "specs/*/design/": design
  toc_file: .claude/doc-advisor/toc/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/toc/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/specs/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude:
      - archived
      - _template
      - deprecated
  output:
    header_comment: "Project specification document search index for query-specs skill"
    metadata_name: "Project Specification Document Search Index"

common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
"""


class _YamlFileTestCase(unittest.TestCase):
    """YAML ファイルを tmpdir に書き出すヘルパー付きの基底クラス"""

    def setUp(self):
        self.tmpdir = Path(os.path.realpath(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_yaml(self, content, filename='.doc_structure.yaml'):
        path = self.tmpdir / filename
        path.write_text(content, encoding='utf-8')
        return path

    def _load_config(self, content):
        """config.yaml 互換形式を書き出してパースする"""
        self._write_yaml(content)
        return parse_doc_structure(self.tmpdir)


# =========================================================================
# 1. パーサーテスト（parse_doc_structure 経由）
# =========================================================================

class TestParseDocStructure(_YamlFileTestCase):
    """parse_doc_structure のテスト"""

    def test_config_with_exclude(self):
        """exclude 付き config をパースできる"""
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        self.assertIsNotNone(ds)
        self.assertIn('specs', ds)
        self.assertIn('rules', ds)

    def test_specs_root_dirs(self):
        """specs の root_dirs が正しくパースされる"""
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        root_dirs = ds['specs']['root_dirs']
        self.assertIn('specs/*/requirements/', root_dirs)
        self.assertIn('specs/*/design/', root_dirs)

    def test_specs_doc_types_map(self):
        """specs の doc_types_map が正しくパースされる"""
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        dtm = ds['specs']['doc_types_map']
        self.assertEqual(dtm['specs/*/requirements/'], 'requirement')
        self.assertEqual(dtm['specs/*/design/'], 'design')

    def test_specs_exclude(self):
        """specs の patterns.exclude が正しくパースされる"""
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        exclude = ds['specs']['patterns']['exclude']
        self.assertIn('archived', exclude)
        self.assertIn('_template', exclude)

    def test_rules_root_dirs(self):
        """rules の root_dirs が正しくパースされる"""
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        self.assertEqual(ds['rules']['root_dirs'], ['rules/'])

    def test_no_exclude(self):
        """exclude が空の config が正しくパースされる"""
        ds = self._load_config(CONFIG_NO_EXCLUDE)
        exclude = ds['specs']['patterns']['exclude']
        self.assertEqual(exclude, [])

    def test_flat_structure(self):
        """フラット構造の config をパース"""
        ds = self._load_config(CONFIG_FLAT)
        self.assertIn('specs/plan/', ds['specs']['root_dirs'])
        self.assertEqual(ds['specs']['doc_types_map']['specs/plan/'], 'plan')

    def test_nonexistent_returns_none(self):
        """存在しないディレクトリではパースが None を返す"""
        result = parse_doc_structure(self.tmpdir / 'nonexistent')
        self.assertIsNone(result)


# =========================================================================
# 2. Exclude 判定テスト
# =========================================================================

class TestIsExcluded(unittest.TestCase):
    """_is_excluded のテスト"""

    def test_excluded_component(self):
        self.assertTrue(
            _is_excluded('specs/archived/requirements/req.md',
                         ['archived', '_template']))

    def test_excluded_template(self):
        self.assertTrue(
            _is_excluded('specs/_template/requirements/req.md',
                         ['archived', '_template']))

    def test_not_excluded(self):
        self.assertFalse(
            _is_excluded('specs/login/requirements/req.md',
                         ['archived', '_template']))

    def test_empty_list(self):
        self.assertFalse(
            _is_excluded('specs/archived/requirements/req.md', []))

    def test_none_list(self):
        self.assertFalse(
            _is_excluded('specs/archived/requirements/req.md', None))

    def test_deep_nested_excluded(self):
        """パスの深い位置にある exclude 名もマッチする"""
        self.assertTrue(
            _is_excluded('a/b/c/archived/d/e.md', ['archived']))

    def test_partial_name_not_excluded(self):
        """部分一致はマッチしない（archived_v2 != archived）"""
        self.assertFalse(
            _is_excluded('specs/archived_v2/requirements/req.md',
                         ['archived']))

    def test_backslash_path(self):
        """Windows パス区切りもサポート"""
        self.assertTrue(
            _is_excluded('specs\\archived\\requirements\\req.md',
                         ['archived']))


class TestGetAllExcludes(_YamlFileTestCase):
    """_get_all_excludes のテスト"""

    def test_specs_excludes(self):
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        excludes = _get_all_excludes(ds, 'specs')
        self.assertEqual(excludes, {'archived', '_template'})

    def test_rules_no_excludes(self):
        ds = self._load_config(CONFIG_WITH_EXCLUDE)
        excludes = _get_all_excludes(ds, 'rules')
        self.assertEqual(excludes, set())

    def test_rules_with_excludes(self):
        ds = self._load_config(CONFIG_MIXED_EXCLUDE)
        excludes = _get_all_excludes(ds, 'rules')
        self.assertEqual(excludes, {'deprecated'})

    def test_none_doc_structure(self):
        excludes = _get_all_excludes(None, 'specs')
        self.assertEqual(excludes, set())


# =========================================================================
# 3. 種別判定テスト
# =========================================================================

class TestDocTypeToReviewType(unittest.TestCase):
    """_doc_type_to_review_type のテスト"""

    def test_requirement(self):
        self.assertEqual(_doc_type_to_review_type('requirement'), 'requirement')

    def test_design(self):
        self.assertEqual(_doc_type_to_review_type('design'), 'design')

    def test_plan(self):
        self.assertEqual(_doc_type_to_review_type('plan'), 'plan')

    def test_unknown(self):
        self.assertEqual(_doc_type_to_review_type('unknown'), 'generic')

    def test_rule(self):
        self.assertEqual(_doc_type_to_review_type('rule'), 'generic')


class TestDetectTypeFromDocStructure(_YamlFileTestCase):
    """detect_type_from_doc_structure のテスト"""

    def _get_ds(self, config_content=CONFIG_WITH_EXCLUDE):
        return self._load_config(config_content)

    def _setup_dirs(self):
        """テスト用のディレクトリ構造を作成"""
        for d in ['specs/login/requirements', 'specs/login/design', 'rules']:
            (self.tmpdir / d).mkdir(parents=True, exist_ok=True)

    def test_normal_path_requirement(self):
        self._setup_dirs()
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_doc_structure(
                'specs/login/requirements/req.md', ds, self.tmpdir),
            'requirement')

    def test_normal_path_design(self):
        self._setup_dirs()
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_doc_structure(
                'specs/login/design/design.md', ds, self.tmpdir),
            'design')

    def test_rules_path(self):
        """rules にマッチするパスは generic を返す"""
        self._setup_dirs()
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_doc_structure('rules/coding.md', ds, self.tmpdir),
            'generic')

    def test_none_doc_structure(self):
        self.assertIsNone(
            detect_type_from_doc_structure('specs/login/requirements/req.md', None, self.tmpdir))


class TestDetectGenericType(_YamlFileTestCase):
    """_detect_generic_type のテスト"""

    def _get_ds(self, config_content=CONFIG_MIXED_EXCLUDE):
        return self._load_config(config_content)

    def test_rules_path(self):
        ds = self._get_ds(CONFIG_WITH_EXCLUDE)
        self.assertEqual(_detect_generic_type('rules/coding.md', ds), 'generic')

    def test_rules_excluded(self):
        """rules に exclude があるとき、除外パスは generic にならない"""
        ds = self._get_ds(CONFIG_MIXED_EXCLUDE)
        self.assertIsNone(
            _detect_generic_type('rules/deprecated/old_rule.md', ds))

    def test_rules_not_excluded(self):
        ds = self._get_ds(CONFIG_MIXED_EXCLUDE)
        self.assertEqual(
            _detect_generic_type('rules/coding/style.md', ds), 'generic')

    def test_skills_path(self):
        self.assertEqual(
            _detect_generic_type('.claude/skills/my-skill/SKILL.md'), 'generic')

    def test_root_readme(self):
        self.assertEqual(_detect_generic_type('README.md'), 'generic')

    def test_nested_readme(self):
        """ルート以外の README.md は generic にならない"""
        self.assertIsNone(_detect_generic_type('docs/README.md'))

    def test_no_doc_structure(self):
        """doc_structure なしでもデフォルト rules/ でマッチ"""
        self.assertEqual(_detect_generic_type('rules/coding.md'), 'generic')


class TestGetRulesAndSpecsPaths(_YamlFileTestCase):
    """get_rules_paths / get_specs_paths_by_type のテスト"""

    def test_get_rules_paths(self):
        ds = self._load_config(CONFIG_FLAT)
        self.assertEqual(get_rules_paths(ds), ['rules/'])

    def test_get_rules_paths_none(self):
        self.assertEqual(get_rules_paths(None), [])

    def test_get_specs_paths_requirement(self):
        ds = self._load_config(CONFIG_FLAT)
        self.assertEqual(get_specs_paths_by_type(ds, 'requirement'),
                         ['specs/requirements/'])

    def test_get_specs_paths_design(self):
        ds = self._load_config(CONFIG_FLAT)
        self.assertEqual(get_specs_paths_by_type(ds, 'design'),
                         ['specs/design/'])

    def test_get_specs_paths_none(self):
        self.assertEqual(get_specs_paths_by_type(None, 'requirement'), [])


# =========================================================================
# 4. Feature 検出テスト（ファイルシステム必要）
# =========================================================================

class TestDetectFeaturesFromDocStructure(_YamlFileTestCase):
    """detect_features_from_doc_structure のテスト"""

    def _setup_feature_dirs(self, feature_names, excluded_names=None):
        """テスト用のディレクトリ構造を作成"""
        for name in feature_names:
            (self.tmpdir / 'specs' / name / 'requirements').mkdir(parents=True)
            (self.tmpdir / 'specs' / name / 'requirements' / 'req.md').touch()
        for name in (excluded_names or []):
            (self.tmpdir / 'specs' / name / 'requirements').mkdir(parents=True)
            (self.tmpdir / 'specs' / name / 'requirements' / 'req.md').touch()

    def _make_config(self, exclude=None):
        """config.yaml 互換形式の config dict を作成"""
        config = {
            'specs': {
                'root_dirs': ['specs/*/requirements/'],
                'doc_types_map': {'specs/*/requirements/': 'requirement'},
                'patterns': {
                    'target_glob': '**/*.md',
                    'exclude': exclude or [],
                },
            },
            'rules': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
        }
        return config

    def test_features_detected(self):
        self._setup_feature_dirs(['login', 'auth'])
        ds = self._make_config()
        features = detect_features_from_doc_structure(self.tmpdir, ds)
        self.assertEqual(sorted(features), ['auth', 'login'])

    def test_excluded_features_not_detected(self):
        """exclude に含まれるディレクトリは Feature に現れない"""
        self._setup_feature_dirs(['login', 'auth'], ['archived', '_template'])
        ds = self._make_config(exclude=['archived', '_template'])
        features = detect_features_from_doc_structure(self.tmpdir, ds)
        self.assertEqual(sorted(features), ['auth', 'login'])
        self.assertNotIn('archived', features)
        self.assertNotIn('_template', features)

    def test_no_exclude_includes_all(self):
        """exclude なしなら全ディレクトリが Feature に含まれる"""
        self._setup_feature_dirs(['login', 'archived'])
        ds = self._make_config()
        features = detect_features_from_doc_structure(self.tmpdir, ds)
        self.assertIn('archived', features)
        self.assertIn('login', features)

    def test_none_doc_structure(self):
        features = detect_features_from_doc_structure(self.tmpdir, None)
        self.assertEqual(features, [])

    def test_no_glob_pattern(self):
        """glob なしのパスからは Feature を検出しない"""
        (self.tmpdir / 'specs' / 'requirements').mkdir(parents=True)
        ds = {
            'specs': {
                'root_dirs': ['specs/requirements/'],
                'doc_types_map': {'specs/requirements/': 'requirement'},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
            'rules': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
        }
        features = detect_features_from_doc_structure(self.tmpdir, ds)
        self.assertEqual(features, [])


# =========================================================================
# 5. Feature 解決テスト（ファイルシステム必要）
# =========================================================================

class TestFindFeatureSubdirs(_YamlFileTestCase):
    """find_feature_subdirs のテスト"""

    def _setup_feature(self, feature, subdirs):
        for sub in subdirs:
            d = self.tmpdir / 'specs' / feature / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / 'doc.md').touch()

    def _make_config(self, doc_types, exclude=None):
        """doc_types: {'requirements': 'requirement', 'design': 'design'} 形式"""
        root_dirs = [f'specs/*/{k}/' for k in doc_types]
        dtm = {f'specs/*/{k}/': v for k, v in doc_types.items()}
        return {
            'specs': {
                'root_dirs': root_dirs,
                'doc_types_map': dtm,
                'patterns': {
                    'target_glob': '**/*.md',
                    'exclude': exclude or [],
                },
            },
            'rules': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
        }

    def test_feature_with_requirement(self):
        self._setup_feature('login', ['requirements'])
        ds = self._make_config({'requirements': 'requirement'})
        types = find_feature_subdirs(self.tmpdir, ds, 'login')
        self.assertEqual(types, ['requirement'])

    def test_excluded_feature_returns_empty(self):
        """exclude に含まれる Feature 名は結果に含まれない"""
        self._setup_feature('archived', ['requirements'])
        ds = self._make_config({'requirements': 'requirement'}, exclude=['archived'])
        types = find_feature_subdirs(self.tmpdir, ds, 'archived')
        self.assertEqual(types, [])

    def test_none_doc_structure(self):
        self.assertEqual(find_feature_subdirs(self.tmpdir, None, 'login'), [])


class TestFindTargetFiles(_YamlFileTestCase):
    """find_target_files のテスト"""

    def _setup_feature_files(self, feature, subdir, filenames):
        d = self.tmpdir / 'specs' / feature / subdir
        d.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            (d / name).touch()

    def _make_config(self, doc_types, exclude=None):
        root_dirs = [f'specs/*/{k}/' for k in doc_types]
        dtm = {f'specs/*/{k}/': v for k, v in doc_types.items()}
        return {
            'specs': {
                'root_dirs': root_dirs,
                'doc_types_map': dtm,
                'patterns': {
                    'target_glob': '**/*.md',
                    'exclude': exclude or [],
                },
            },
            'rules': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
        }

    def test_find_files(self):
        self._setup_feature_files('login', 'requirements', ['req1.md', 'req2.md'])
        ds = self._make_config({'requirements': 'requirement'})
        files = find_target_files(self.tmpdir, ds, 'login', 'requirement')
        self.assertEqual(len(files), 2)
        self.assertTrue(all('login/requirements' in f for f in files))

    def test_excluded_files_filtered(self):
        """exclude パスに含まれるファイルはフィルタされる"""
        self._setup_feature_files('archived', 'requirements', ['req.md'])
        self._setup_feature_files('login', 'requirements', ['req.md'])
        ds = self._make_config({'requirements': 'requirement'}, exclude=['archived'])
        files = find_target_files(self.tmpdir, ds, 'login', 'requirement')
        self.assertEqual(len(files), 1)
        self.assertIn('login', files[0])

    def test_none_doc_structure(self):
        self.assertEqual(find_target_files(self.tmpdir, None, 'login', 'requirement'), [])


# =========================================================================
# 6. 種別判定の統合テスト
# =========================================================================

class TestDetectTypeFromPath(_YamlFileTestCase):
    """detect_type_from_path の統合テスト"""

    def _get_ds(self, config_content=CONFIG_WITH_EXCLUDE):
        return self._load_config(config_content)

    def _setup_dirs(self):
        for d in ['specs/login/requirements', 'specs/login/design', 'rules']:
            (self.tmpdir / d).mkdir(parents=True, exist_ok=True)

    def test_code_by_extension(self):
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_path('src/main.swift', ds, self.tmpdir), 'code')

    def test_python_code(self):
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_path('scripts/tool.py', ds, self.tmpdir), 'code')

    def test_requirement_from_doc_structure(self):
        self._setup_dirs()
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_path(
                'specs/login/requirements/req.md', ds, self.tmpdir),
            'requirement')

    def test_generic_from_skills(self):
        ds = self._get_ds()
        self.assertEqual(
            detect_type_from_path(
                '.claude/skills/my-skill/SKILL.md', ds, self.tmpdir),
            'generic')


class TestDetectTypeFromDir(_YamlFileTestCase):
    """detect_type_from_dir のテスト"""

    def _make_empty_config(self):
        return {
            'specs': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
            'rules': {
                'root_dirs': [],
                'doc_types_map': {},
                'patterns': {'target_glob': '**/*.md', 'exclude': []},
            },
        }

    def test_code_dir(self):
        src = self.tmpdir / 'src'
        src.mkdir()
        (src / 'main.swift').touch()
        ds = self._make_empty_config()
        review_type, files = detect_type_from_dir('src', ds, self.tmpdir)
        self.assertEqual(review_type, 'code')
        self.assertTrue(len(files) > 0)

    def test_mixed_code_and_md(self):
        """コード + md 混在ディレクトリは code を返す"""
        src = self.tmpdir / 'src'
        src.mkdir()
        (src / 'main.py').touch()
        (src / 'README.md').touch()
        ds = self._make_empty_config()
        review_type, files = detect_type_from_dir('src', ds, self.tmpdir)
        self.assertEqual(review_type, 'code')

    def test_empty_dir(self):
        empty = self.tmpdir / 'empty'
        empty.mkdir()
        ds = self._make_empty_config()
        review_type, files = detect_type_from_dir('empty', ds, self.tmpdir)
        self.assertIsNone(review_type)
        self.assertEqual(files, [])

    def test_nonexistent_dir(self):
        ds = self._make_empty_config()
        review_type, files = detect_type_from_dir('nonexistent', ds, self.tmpdir)
        self.assertIsNone(review_type)
        self.assertEqual(files, [])


# =========================================================================
# 7. parse_args テスト (--files / --diff バイパス経路)
# =========================================================================

class TestParseArgs(unittest.TestCase):
    """parse_args のテスト (TASK-016: --files / --diff)"""

    def test_no_args(self):
        result = parse_args([])
        self.assertEqual(result["targets"], [])
        self.assertIsNone(result["files"])
        self.assertFalse(result["diff"])

    def test_positional_targets(self):
        result = parse_args(['a.md', 'b.md'])
        self.assertEqual(result["targets"], ['a.md', 'b.md'])
        self.assertIsNone(result["files"])
        self.assertFalse(result["diff"])

    def test_unknown_flag_ignored(self):
        """未知フラグ (--codex / --claude 等) は無視される (後方互換)"""
        result = parse_args(['--codex', 'a.md', '--auto-fix'])
        self.assertEqual(result["targets"], ['a.md'])
        self.assertIsNone(result["files"])
        self.assertFalse(result["diff"])

    def test_files_multiple_args(self):
        """--files で複数パスを空白区切りで指定"""
        result = parse_args(['--files', 'a.md', 'b.md', 'c.md'])
        self.assertEqual(result["files"], ['a.md', 'b.md', 'c.md'])
        self.assertEqual(result["targets"], [])

    def test_files_comma_separated(self):
        """--files でカンマ区切り指定"""
        result = parse_args(['--files', 'a.md,b.md,c.md'])
        self.assertEqual(result["files"], ['a.md', 'b.md', 'c.md'])

    def test_files_mixed_comma_and_space(self):
        """カンマ区切りと空白区切りの混在も対応"""
        result = parse_args(['--files', 'a.md,b.md', 'c.md'])
        self.assertEqual(result["files"], ['a.md', 'b.md', 'c.md'])

    def test_files_empty(self):
        """--files の後にパスがない場合は空リスト"""
        result = parse_args(['--files'])
        self.assertEqual(result["files"], [])

    def test_files_terminates_at_flag(self):
        """--files の収集は次の -- フラグで終わる"""
        result = parse_args(['--files', 'a.md', 'b.md', '--diff'])
        self.assertEqual(result["files"], ['a.md', 'b.md'])
        self.assertTrue(result["diff"])

    def test_diff_flag(self):
        result = parse_args(['--diff'])
        self.assertTrue(result["diff"])
        self.assertIsNone(result["files"])
        self.assertEqual(result["targets"], [])


# =========================================================================
# 8. get_uncommitted_changed_files テスト (--diff 経路の内部実装)
# =========================================================================

class TestGetUncommittedChangedFiles(unittest.TestCase):
    """get_uncommitted_changed_files のテスト (TASK-016: --diff)"""

    def setUp(self):
        self.tmpdir = Path(os.path.realpath(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _mock_runner(self, stdout, returncode=0, stderr=''):
        """subprocess.run を差し替えるための fake runner"""
        def runner(cmd, **kwargs):
            return SimpleNamespace(
                stdout=stdout, stderr=stderr, returncode=returncode
            )
        return runner

    def test_working_tree_modified(self):
        """working tree の変更 (M) を検出"""
        (self.tmpdir / 'a.md').write_text('a')
        runner = self._mock_runner(' M a.md\n')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['a.md'])

    def test_staged_modified(self):
        """staged の変更 (M ) を検出"""
        (self.tmpdir / 'b.md').write_text('b')
        runner = self._mock_runner('M  b.md\n')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['b.md'])

    def test_untracked(self):
        """untracked file (??) も検出"""
        (self.tmpdir / 'new.md').write_text('new')
        runner = self._mock_runner('?? new.md\n')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['new.md'])

    def test_mixed_staged_and_working(self):
        """staged + working tree + untracked の混在"""
        (self.tmpdir / 'a.md').write_text('a')
        (self.tmpdir / 'b.md').write_text('b')
        (self.tmpdir / 'c.md').write_text('c')
        runner = self._mock_runner(
            'M  a.md\n'
            ' M b.md\n'
            '?? c.md\n'
        )
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['a.md', 'b.md', 'c.md'])

    def test_deleted_file_skipped(self):
        """削除済みファイル (実体無し) はスキップ"""
        # ファイルを作らず、porcelain だけ ' D' を返す
        runner = self._mock_runner(' D removed.md\n')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, [])

    def test_rename_uses_new_path(self):
        """rename (R) は新しいパスを採用"""
        (self.tmpdir / 'new_name.md').write_text('content')
        runner = self._mock_runner('R  old_name.md -> new_name.md\n')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['new_name.md'])

    def test_empty_status(self):
        """変更なし"""
        runner = self._mock_runner('')
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, [])

    def test_git_failure_raises(self):
        """git 失敗 (returncode != 0) は RuntimeError"""
        runner = self._mock_runner('', returncode=128, stderr='fatal: not a git repository')
        with self.assertRaises(RuntimeError):
            get_uncommitted_changed_files(self.tmpdir, runner=runner)

    def test_sorted_and_dedup(self):
        """ソート済み・重複排除"""
        (self.tmpdir / 'a.md').write_text('a')
        (self.tmpdir / 'b.md').write_text('b')
        runner = self._mock_runner(
            ' M b.md\n'
            'M  a.md\n'
            ' M b.md\n'  # 重複
        )
        files = get_uncommitted_changed_files(self.tmpdir, runner=runner)
        self.assertEqual(files, ['a.md', 'b.md'])


# =========================================================================
# 9. main() の --files / --diff バイパス経路統合テスト
# =========================================================================

class _MainBypassTestCase(unittest.TestCase):
    """main() を呼び出して JSON 出力を検証する基底クラス"""

    def setUp(self):
        self.tmpdir = Path(os.path.realpath(tempfile.mkdtemp()))
        # find_project_root を tmpdir に固定
        self._patch_root = mock.patch.object(
            rrc, 'find_project_root', return_value=self.tmpdir
        )
        self._patch_root.start()

    def tearDown(self):
        self._patch_root.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run_main(self, argv):
        """sys.argv を差し替えて main() を実行し、JSON dict を返す"""
        buf = io.StringIO()
        with mock.patch.object(sys, 'argv', ['resolve_review_context.py'] + argv):
            with redirect_stdout(buf):
                rrc.main()
        out = buf.getvalue().strip()
        return json.loads(out) if out else None


class TestMainFilesBypass(_MainBypassTestCase):
    """--files バイパス経路のテスト (TASK-016)"""

    def test_files_single(self):
        (self.tmpdir / 'a.md').write_text('a')
        result = self._run_main(['--files', 'a.md'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md'])
        # 種別解決はバイパスされるため type は None
        self.assertIsNone(result["type"])

    def test_files_multiple(self):
        (self.tmpdir / 'a.md').write_text('a')
        (self.tmpdir / 'b.md').write_text('b')
        result = self._run_main(['--files', 'a.md', 'b.md'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md', 'b.md'])

    def test_files_comma_separated(self):
        (self.tmpdir / 'a.md').write_text('a')
        (self.tmpdir / 'b.md').write_text('b')
        result = self._run_main(['--files', 'a.md,b.md'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md', 'b.md'])

    def test_files_missing_is_error(self):
        """指定ファイルが存在しない場合は error (early validation)"""
        result = self._run_main(['--files', 'nonexistent.md'])
        self.assertEqual(result["status"], "error")
        self.assertIn("nonexistent.md", result["error"])

    def test_files_empty_is_error(self):
        """--files が空指定の場合は error"""
        result = self._run_main(['--files'])
        self.assertEqual(result["status"], "error")
        self.assertIn("少なくとも 1 つ", result["error"])

    def test_files_bypasses_doc_structure(self):
        """.doc_structure.yaml が無くても --files は動作する (バイパス)"""
        (self.tmpdir / 'a.md').write_text('a')
        # .doc_structure.yaml を作らずに実行
        result = self._run_main(['--files', 'a.md'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md'])

    def test_files_and_diff_conflict(self):
        """--files と --diff の同時指定は error (early validation)"""
        (self.tmpdir / 'a.md').write_text('a')
        result = self._run_main(['--files', 'a.md', '--diff'])
        self.assertEqual(result["status"], "error")
        self.assertIn("同時に指定できません", result["error"])


class TestMainDiff(_MainBypassTestCase):
    """--diff バイパス経路のテスト (TASK-016 / TBD-401)"""

    def _patch_git(self, stdout, returncode=0, stderr=''):
        def fake_runner(cmd, **kwargs):
            return SimpleNamespace(
                stdout=stdout, stderr=stderr, returncode=returncode
            )
        return mock.patch.object(rrc.subprocess, 'run', side_effect=fake_runner)

    def test_diff_collects_working_and_staged(self):
        """working tree + staged + untracked の変更が target_files に入る"""
        (self.tmpdir / 'a.md').write_text('a')
        (self.tmpdir / 'b.md').write_text('b')
        (self.tmpdir / 'c.md').write_text('c')
        porcelain = (
            'M  a.md\n'
            ' M b.md\n'
            '?? c.md\n'
        )
        with self._patch_git(porcelain):
            result = self._run_main(['--diff'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md', 'b.md', 'c.md'])

    def test_diff_empty_yields_needs_input(self):
        """変更なしの場合は needs_input で質問を返す"""
        with self._patch_git(''):
            result = self._run_main(['--diff'])
        self.assertEqual(result["status"], "needs_input")
        self.assertTrue(any(q["key"] == "target" for q in result["questions"]))

    def test_diff_git_failure_is_error(self):
        """git status 失敗時は error"""
        with self._patch_git('', returncode=128, stderr='fatal'):
            result = self._run_main(['--diff'])
        self.assertEqual(result["status"], "error")
        self.assertIn("git status", result["error"])

    def test_diff_bypasses_doc_structure(self):
        """.doc_structure.yaml が無くても --diff は動作する"""
        (self.tmpdir / 'a.md').write_text('a')
        with self._patch_git(' M a.md\n'):
            result = self._run_main(['--diff'])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["target_files"], ['a.md'])


# =========================================================================
# 10. 後方互換テスト (既存経路を破壊していないか)
# =========================================================================

class TestMainLegacyPath(_MainBypassTestCase):
    """通常経路 (位置引数 / 引数なし) が引き続き動作することを確認"""

    def _write_doc_structure(self, content):
        (self.tmpdir / '.doc_structure.yaml').write_text(content, encoding='utf-8')

    def test_no_doc_structure_yields_error(self):
        """.doc_structure.yaml なしの通常経路はエラー (既存挙動維持)"""
        result = self._run_main([])
        self.assertEqual(result["status"], "error")
        self.assertIn(".doc_structure.yaml", result["error"])

    def test_positional_file_target(self):
        """位置引数 (単一ファイル) の通常経路が動作する"""
        self._write_doc_structure(CONFIG_FLAT)
        (self.tmpdir / 'rules').mkdir(exist_ok=True)
        (self.tmpdir / 'rules' / 'guide.md').write_text('rules')
        result = self._run_main(['rules/guide.md'])
        # 通常経路を通っているので features (空でも) + has_doc_structure True
        self.assertTrue(result["has_doc_structure"])
        self.assertEqual(result["target_files"], ['rules/guide.md'])
        self.assertEqual(result["type"], "generic")


if __name__ == '__main__':
    unittest.main()
