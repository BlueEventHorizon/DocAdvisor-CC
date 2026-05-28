#!/usr/bin/env python3
"""
scan_version_targets.py のテスト

バージョンファイル検出、形式判定、メタデータ収集をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.setup-version-config.test_scan_version_targets -v
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'skills'
                       / 'setup-version-config' / 'scripts'))

from scan_version_targets import (
    SKIP_DIRS,
    extract_version_from_json,
    extract_version_from_toml,
    get_version_file_type,
    scan_version_files,
    scan_catalog_files,
    scan_readme_files,
    scan_version_ref_files,
    scan_changelog,
    detect_changelog_format,
    output_scan,
)


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテストの基底クラス"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, rel_path, content=''):
        p = self.tmpdir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p


# =========================================================================
# 1. JSON バージョン抽出テスト
# =========================================================================

class TestExtractVersionFromJson(_FsTestCase):
    """extract_version_from_json のテスト"""

    def test_plugin_json_with_name_and_version(self):
        """plugin.json から name と version を抽出"""
        f = self._write_file('plugin.json', '{"name": "forge", "version": "999.88.7"}')
        result = extract_version_from_json(f)
        self.assertEqual(result['name'], 'forge')
        self.assertEqual(result['version'], '999.88.7')

    def test_package_json_version_only(self):
        """package.json は version のみ（name はない場合も）"""
        f = self._write_file('package.json', '{"version": "1.2.3", "description": "test"}')
        result = extract_version_from_json(f)
        self.assertEqual(result['version'], '1.2.3')

    def test_no_version_field(self):
        """version フィールドがない場合は None"""
        f = self._write_file('plugin.json', '{"name": "no-version"}')
        result = extract_version_from_json(f)
        self.assertIsNone(result['version'])
        self.assertEqual(result['name'], 'no-version')

    def test_invalid_json(self):
        """不正な JSON は None を返す"""
        f = self._write_file('plugin.json', 'not json {{{')
        result = extract_version_from_json(f)
        self.assertIsNone(result['name'])
        self.assertIsNone(result['version'])

    def test_nonexistent_file(self):
        """存在しないファイルは None を返す"""
        result = extract_version_from_json(self.tmpdir / 'nonexistent.json')
        self.assertIsNone(result['name'])
        self.assertIsNone(result['version'])

    def test_version_not_string(self):
        """version が文字列でない場合は None"""
        f = self._write_file('plugin.json', '{"version": 123}')
        result = extract_version_from_json(f)
        self.assertIsNone(result['version'])


# =========================================================================
# 2. TOML バージョン抽出テスト
# =========================================================================

class TestExtractVersionFromToml(_FsTestCase):
    """extract_version_from_toml のテスト"""

    def test_cargo_toml(self):
        """Cargo.toml から name と version を抽出"""
        content = '[package]\nname = "my-crate"\nversion = "0.1.0"\nedition = "2021"\n'
        f = self._write_file('Cargo.toml', content)
        result = extract_version_from_toml(f)
        self.assertEqual(result['name'], 'my-crate')
        self.assertEqual(result['version'], '0.1.0')

    def test_pyproject_toml(self):
        """pyproject.toml から version を抽出"""
        content = '[tool.poetry]\nname = "my-package"\nversion = "2.3.4"\n'
        f = self._write_file('pyproject.toml', content)
        result = extract_version_from_toml(f)
        # [package] セクションがないので None（[tool.poetry] は別セクション）
        self.assertIsNone(result['version'])

    def test_pyproject_with_package_section(self):
        """pyproject.toml で [package] セクションがある場合"""
        content = '[package]\nname = "my-lib"\nversion = "1.0.0"\n'
        f = self._write_file('pyproject.toml', content)
        result = extract_version_from_toml(f)
        self.assertEqual(result['version'], '1.0.0')

    def test_single_quotes(self):
        """シングルクォートの version も抽出"""
        content = "[package]\nname = 'pkg'\nversion = '0.2.0'\n"
        f = self._write_file('Cargo.toml', content)
        result = extract_version_from_toml(f)
        self.assertEqual(result['version'], '0.2.0')

    def test_no_package_section(self):
        """[package] セクションがない場合は None"""
        content = '[dependencies]\nhttps = "0.2"\n'
        f = self._write_file('Cargo.toml', content)
        result = extract_version_from_toml(f)
        self.assertIsNone(result['version'])

    def test_nonexistent_file(self):
        """存在しないファイルは None を返す"""
        result = extract_version_from_toml(self.tmpdir / 'nonexistent.toml')
        self.assertIsNone(result['version'])

    def test_pyproject_with_project_section(self):
        """PEP 621 の [project] セクションから name と version を抽出"""
        content = '[project]\nname = "my-app"\nversion = "3.0.0"\n\n[tool.setuptools]\npackages = ["src"]\n'
        f = self._write_file('pyproject.toml', content)
        result = extract_version_from_toml(f)
        self.assertEqual(result['name'], 'my-app')
        self.assertEqual(result['version'], '3.0.0')

    def test_package_preferred_over_project(self):
        """[package] と [project] の両方がある場合、先に現れた方を使用"""
        content = '[package]\nname = "crate"\nversion = "1.0.0"\n\n[project]\nname = "py-app"\nversion = "2.0.0"\n'
        f = self._write_file('pyproject.toml', content)
        result = extract_version_from_toml(f)
        self.assertEqual(result['name'], 'crate')
        self.assertEqual(result['version'], '1.0.0')


# =========================================================================
# 3. バージョンファイルスキャンテスト
# =========================================================================

class TestScanVersionFiles(_FsTestCase):
    """scan_version_files のテスト"""

    def test_detect_plugin_json(self):
        """plugin.json を検出する"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        result = scan_version_files(str(self.tmpdir))
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry['type'], 'plugin.json')
        self.assertEqual(entry['detected_name'], 'forge')
        self.assertEqual(entry['current_version'], '999.88.7')

    def test_detect_package_json(self):
        """package.json を検出する"""
        self._write_file('package.json', '{"name": "my-app", "version": "1.0.0"}')
        result = scan_version_files(str(self.tmpdir))
        types = [e['type'] for e in result]
        self.assertIn('package.json', types)

    def test_detect_cargo_toml(self):
        """Cargo.toml を検出する"""
        self._write_file('Cargo.toml', '[package]\nname = "my-crate"\nversion = "0.1.0"\n')
        result = scan_version_files(str(self.tmpdir))
        types = [e['type'] for e in result]
        self.assertIn('Cargo.toml', types)

    def test_skip_node_modules(self):
        """node_modules 内の package.json はスキップ"""
        self._write_file('node_modules/dep/package.json',
                         '{"name": "dep", "version": "1.0.0"}')
        self._write_file('package.json', '{"name": "my-app", "version": "2.0.0"}')
        result = scan_version_files(str(self.tmpdir))
        paths = [e['path'] for e in result]
        self.assertIn('package.json', paths)
        node_paths = [p for p in paths if 'node_modules' in p]
        self.assertEqual(len(node_paths), 0)

    def test_skip_git_dir(self):
        """.git 内のファイルはスキップ"""
        self._write_file('.git/hooks/plugin.json', '{"name": "x", "version": "1.0.0"}')
        result = scan_version_files(str(self.tmpdir))
        git_paths = [e for e in result if '.git' in e['path']]
        self.assertEqual(len(git_paths), 0)

    def test_no_version_files(self):
        """バージョンファイルがない場合は空リスト"""
        self._write_file('README.md', '# Project')
        result = scan_version_files(str(self.tmpdir))
        self.assertEqual(result, [])

    def test_version_none_when_field_missing(self):
        """version フィールドがない plugin.json は current_version が None"""
        self._write_file('plugin.json', '{"name": "no-version-field"}')
        result = scan_version_files(str(self.tmpdir))
        # name はあるので検出される
        entry = next((e for e in result if e['type'] == 'plugin.json'), None)
        self.assertIsNotNone(entry)
        self.assertIsNone(entry['current_version'])
        self.assertEqual(entry['detected_name'], 'no-version-field')

    def test_multiple_plugins(self):
        """複数の plugin.json を検出"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('plugins/anvil/.claude-plugin/plugin.json',
                         '{"name": "anvil", "version": "888.77.6"}')
        result = scan_version_files(str(self.tmpdir))
        names = {e['detected_name'] for e in result}
        self.assertIn('forge', names)
        self.assertIn('anvil', names)

    def test_hidden_claude_plugin_dir_not_skipped(self):
        """.claude-plugin/ は SKIP_DIRS に含まれないので検出される"""
        self._write_file('.claude-plugin/marketplace.json',
                         '{"name": "test", "version": "1.0.0"}')
        # marketplace.json は scan_catalog_files で処理するが、
        # scan_version_files は VERSION_FILE_NAMES に基づくためスキャン対象外
        result = scan_version_files(str(self.tmpdir))
        # marketplace.json は VERSION_FILE_NAMES に含まれないので version_files には出ない
        self.assertEqual(result, [])

    def test_relative_paths(self):
        """path フィールドがプロジェクトルートからの相対パス"""
        self._write_file('plugins/test/.claude-plugin/plugin.json',
                         '{"name": "test", "version": "1.0.0"}')
        result = scan_version_files(str(self.tmpdir))
        self.assertEqual(len(result), 1)
        # パス区切りは OS に依存しない（Path で正規化）
        self.assertIn('plugin.json', result[0]['path'])
        self.assertNotIn(str(self.tmpdir), result[0]['path'])


# =========================================================================
# 4. カタログファイルスキャンテスト
# =========================================================================

class TestScanCatalogFiles(_FsTestCase):
    """scan_catalog_files のテスト"""

    def test_detect_marketplace_json(self):
        """.claude-plugin/marketplace.json を検出"""
        self._write_file('.claude-plugin/marketplace.json', '{}')
        result = scan_catalog_files(str(self.tmpdir))
        paths = [e['path'] for e in result]
        self.assertIn('.claude-plugin/marketplace.json', paths)

    def test_no_catalog_files(self):
        """カタログファイルがない場合は空リスト"""
        result = scan_catalog_files(str(self.tmpdir))
        self.assertEqual(result, [])

    def test_root_marketplace_json(self):
        """ルートの marketplace.json も検出"""
        self._write_file('marketplace.json', '{}')
        result = scan_catalog_files(str(self.tmpdir))
        paths = [e['path'] for e in result]
        self.assertIn('marketplace.json', paths)


# =========================================================================
# 5. README スキャンテスト
# =========================================================================

class TestScanReadmeFiles(_FsTestCase):
    """scan_readme_files のテスト"""

    def test_detect_readme_md(self):
        """README.md を検出"""
        self._write_file('README.md', '# Project')
        result = scan_readme_files(str(self.tmpdir))
        self.assertIn('README.md', result)

    def test_detect_readme_en(self):
        """README_en.md も検出"""
        self._write_file('README.md', '# プロジェクト')
        self._write_file('README_en.md', '# Project')
        result = scan_readme_files(str(self.tmpdir))
        self.assertIn('README.md', result)
        self.assertIn('README_en.md', result)

    def test_deep_readme_not_detected(self):
        """サブディレクトリの README は対象外"""
        self._write_file('docs/README.md', '# Docs')
        result = scan_readme_files(str(self.tmpdir))
        self.assertNotIn('docs/README.md', result)

    def test_no_readme(self):
        """README がない場合は空リスト"""
        result = scan_readme_files(str(self.tmpdir))
        self.assertEqual(result, [])

    def test_readme_without_extension_not_detected(self):
        """拡張子なしの README ファイルは検出されない"""
        self._write_file('README', '# Project')
        result = scan_readme_files(str(self.tmpdir))
        self.assertNotIn('README', result)


# =========================================================================
# 5b. バージョン参照ファイル検出テスト
# =========================================================================

class TestScanVersionRefFiles(_FsTestCase):
    """scan_version_ref_files のテスト"""

    def test_detect_any_root_file_with_version(self):
        """ルートのテキストファイルからバージョン参照を自動検出"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('CLAUDE.md',
                         '# CLAUDE.md\n\n- **forge** (v999.88.7) — ツール\n')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['path'], 'CLAUDE.md')
        self.assertEqual(len(result[0]['references']), 1)
        self.assertEqual(result[0]['references'][0]['name'], 'forge')

    def test_detect_unknown_file_with_version(self):
        """事前登録なしのファイルでもバージョン参照を検出"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "1.2.3"}')
        self._write_file('CONTRIBUTING.md', '# Contributing\n\nCurrent: 1.2.3\n')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        paths = [r['path'] for r in result]
        self.assertIn('CONTRIBUTING.md', paths)

    def test_no_version_reference(self):
        """バージョン参照がないファイルは検出しない"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('CLAUDE.md', '# CLAUDE.md\n\nバージョン参照なし\n')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        self.assertEqual(result, [])

    def test_no_root_text_files(self):
        """ルートにテキストファイルがない場合は空"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        self.assertEqual(result, [])

    def test_skip_readme_files(self):
        """readme_files で既に検出済みのファイルは除外"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('README.md', '# Project\n\nforge 999.88.7\n')
        self._write_file('CLAUDE.md', '# CLAUDE\n\nforge 999.88.7\n')
        version_files = scan_version_files(str(self.tmpdir))
        readme_files = ['README.md']
        result = scan_version_ref_files(str(self.tmpdir), version_files,
                                        readme_files=readme_files)
        paths = [r['path'] for r in result]
        self.assertNotIn('README.md', paths)
        self.assertIn('CLAUDE.md', paths)

    def test_skip_changelog(self):
        """CHANGELOG は除外（changelog カテゴリで処理）"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('CHANGELOG.md', '## [999.88.7]\n\n- feature\n')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        paths = [r['path'] for r in result]
        self.assertNotIn('CHANGELOG.md', paths)

    def test_multiple_target_references(self):
        """複数 target のバージョン参照を検出"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('plugins/anvil/.claude-plugin/plugin.json',
                         '{"name": "anvil", "version": "888.77.6"}')
        self._write_file('CLAUDE.md',
                         '# CLAUDE\n\n- forge (v999.88.7)\n- anvil (v888.77.6)\n')
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        self.assertEqual(len(result), 1)
        names = {r['name'] for r in result[0]['references']}
        self.assertEqual(names, {'forge', 'anvil'})

    def test_empty_version_files(self):
        """version_files が空の場合は空"""
        self._write_file('CLAUDE.md', '# CLAUDE.md\n')
        result = scan_version_ref_files(str(self.tmpdir), [])
        self.assertEqual(result, [])

    def test_skip_non_text_extensions(self):
        """テキスト拡張子以外のファイルはスキップ"""
        self._write_file('plugins/forge/.claude-plugin/plugin.json',
                         '{"name": "forge", "version": "999.88.7"}')
        self._write_file('image.png', '999.88.7')  # バイナリ想定
        version_files = scan_version_files(str(self.tmpdir))
        result = scan_version_ref_files(str(self.tmpdir), version_files)
        paths = [r['path'] for r in result]
        self.assertNotIn('image.png', paths)


# =========================================================================
# 6. CHANGELOG 検出テスト
# =========================================================================

class TestScanChangelog(_FsTestCase):
    """scan_changelog のテスト"""

    def test_detect_keep_a_changelog(self):
        """keep-a-changelog 形式を正しく判定"""
        content = '# Changelog\n\n## [999.88.7] - 2026-01-01\n\n### Added\n\n- Feature\n'
        self._write_file('CHANGELOG.md', content)
        result = scan_changelog(str(self.tmpdir))
        self.assertIsNotNone(result)
        self.assertEqual(result['file'], 'CHANGELOG.md')
        self.assertEqual(result['format'], 'keep-a-changelog')

    def test_detect_simple_format(self):
        """シンプルな形式も判定"""
        content = '# Changelog\n\n## v1.0.0\n\n- Initial release\n'
        self._write_file('CHANGELOG.md', content)
        result = scan_changelog(str(self.tmpdir))
        self.assertIsNotNone(result)
        self.assertEqual(result['format'], 'simple')

    def test_no_changelog(self):
        """CHANGELOG がない場合は None"""
        result = scan_changelog(str(self.tmpdir))
        self.assertIsNone(result)

    def test_history_md_detected(self):
        """HISTORY.md も検出対象"""
        content = '# History\n\n## [1.0.0]\n\n- Initial\n'
        self._write_file('HISTORY.md', content)
        result = scan_changelog(str(self.tmpdir))
        self.assertIsNotNone(result)
        self.assertEqual(result['file'], 'HISTORY.md')


# =========================================================================
# 7. output_scan テスト
# =========================================================================

class TestOutputScan(unittest.TestCase):
    """output_scan のテスト"""

    def _capture(self, project_root, version_files, catalog_files, readme_files, changelog):
        buf = io.StringIO()
        with redirect_stdout(buf):
            output_scan(project_root, version_files, catalog_files, readme_files, changelog)
        return buf.getvalue()

    def test_valid_json_output(self):
        """出力が有効な JSON"""
        output = self._capture('/tmp/project', [], [], [], None)
        parsed = json.loads(output)
        self.assertIn('project_root', parsed)
        self.assertIn('version_files', parsed)
        self.assertIn('catalog_files', parsed)
        self.assertIn('readme_files', parsed)
        self.assertIn('version_ref_files', parsed)
        self.assertIn('changelog', parsed)

    def test_output_with_data(self):
        """データを含む出力"""
        version_files = [{'path': 'plugin.json', 'type': 'plugin.json',
                           'detected_name': 'test', 'current_version': '1.0.0'}]
        output = self._capture('/tmp/project', version_files, [], ['README.md'],
                               {'file': 'CHANGELOG.md', 'format': 'keep-a-changelog'})
        parsed = json.loads(output)
        self.assertEqual(len(parsed['version_files']), 1)
        self.assertEqual(parsed['version_files'][0]['detected_name'], 'test')
        self.assertEqual(parsed['changelog']['format'], 'keep-a-changelog')

    def test_ensure_ascii_false(self):
        """日本語が正しく出力される"""
        output = self._capture('/tmp/プロジェクト', [], [], [], None)
        self.assertIn('プロジェクト', output)


# =========================================================================
# 8. 定数の健全性テスト
# =========================================================================

class TestConstants(unittest.TestCase):
    """定数の健全性を検証"""

    def test_skip_dirs_no_path_separator(self):
        """SKIP_DIRS にパス区切りが含まれていない"""
        for d in SKIP_DIRS:
            self.assertFalse('/' in d, f'SKIP_DIRS にパス区切り: {d}')

    def test_node_modules_in_skip_dirs(self):
        """node_modules が SKIP_DIRS に含まれている"""
        self.assertIn('node_modules', SKIP_DIRS)

    def test_git_in_skip_dirs(self):
        """.git が SKIP_DIRS に含まれている"""
        self.assertIn('.git', SKIP_DIRS)


class TestGetVersionFileType(unittest.TestCase):
    """get_version_file_type のテスト"""

    def test_plugin_json(self):
        """plugin.json → 'plugin.json' を返す"""
        self.assertEqual(get_version_file_type('plugin.json'), 'plugin.json')

    def test_package_json(self):
        """package.json → 'package.json' を返す"""
        self.assertEqual(get_version_file_type('package.json'), 'package.json')

    def test_cargo_toml(self):
        """Cargo.toml → 'Cargo.toml' を返す"""
        self.assertEqual(get_version_file_type('Cargo.toml'), 'Cargo.toml')

    def test_pyproject_toml(self):
        """pyproject.toml → 'pyproject.toml' を返す"""
        self.assertEqual(get_version_file_type('pyproject.toml'), 'pyproject.toml')

    def test_unknown_json(self):
        """不明なファイル名 unknown.json → None を返す"""
        self.assertIsNone(get_version_file_type('unknown.json'))

    def test_setup_cfg(self):
        """不明なファイル名 setup.cfg → None を返す"""
        self.assertIsNone(get_version_file_type('setup.cfg'))


if __name__ == '__main__':
    unittest.main()
