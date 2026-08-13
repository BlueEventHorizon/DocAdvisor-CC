#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""toc_utils.py のユニットテスト。

bash テスト test_should_exclude.sh, test_edge_cases.sh (yaml_escape) から移行。
"""

import os
import sys
import tempfile
import shutil
import unicodedata
import unittest
from pathlib import Path

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import toc_utils


# ===========================================================================
# should_exclude テスト（test_should_exclude.sh から移行）
# ===========================================================================

class TestShouldExclude(unittest.TestCase):
    """should_exclude() のディレクトリマッチングテスト。"""

    def test_plan_directory_excluded(self):
        """plan ディレクトリは除外される"""
        root = Path('/project/specs')
        fp = Path('/project/specs/plan/roadmap.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['plan']))

    def test_nested_plan_directory_excluded(self):
        """ネストされた plan ディレクトリは除外される"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/plan/item.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['plan']))

    def test_planning_md_not_excluded_by_plan(self):
        """planning.md は 'plan' パターンで除外されない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/requirements/planning.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['plan']))

    def test_deployment_plan_md_not_excluded(self):
        """deployment_plan.md は 'plan' パターンで除外されない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/design/deployment_plan.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['plan']))

    def test_project_plan_v2_not_excluded(self):
        """project_plan_v2.md は 'plan' パターンで除外されない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/requirements/project_plan_v2.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['plan']))

    def test_slash_pattern_archive(self):
        """パスに /archive/ を含む場合は除外（先頭末尾の / は除去される）"""
        root = Path('/project/specs')
        fp = Path('/project/specs/archive/old/doc.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['/archive/']))

    def test_archived_md_not_excluded_by_archive_slash(self):
        """archived.md は '/archive/' パターンで除外されない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/requirements/archived.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['/archive/']))

    def test_slash_pattern_file_exact(self):
        """'/' 含みパターンはファイルパス完全一致で除外する（Issue #30）"""
        root = Path('/project/specs')
        fp = Path('/project/specs/docs/drop.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['docs/drop.md']))

    def test_slash_pattern_subtree_prefix(self):
        """'/' 含みパターンはサブツリー前置きで除外する"""
        root = Path('/project/specs')
        fp = Path('/project/specs/docs/draft/wip.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['docs/draft']))

    def test_slash_pattern_no_overmatch_segment_boundary(self):
        """'/' 含みパターンはセグメント境界でマッチし、前方部分一致で誤爆しない"""
        root = Path('/project/specs')
        # パターン 'docs/spec' は 'docs/specs/...' に誤爆しない
        fp = Path('/project/specs/docs/specs/x.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['docs/spec']))

    def test_slash_pattern_no_overmatch_substring(self):
        """'/' 含みパターンは部分文字列マッチで誤爆しない（'a/b' は 'za/bc' に当たらない）"""
        root = Path('/project/specs')
        fp = Path('/project/specs/za/bc/x.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['a/b']))

    def test_slash_pattern_root_anchored(self):
        """'/' 含みパターンは root-anchored（パス途中からの部分一致はしない）"""
        root = Path('/project/specs')
        # 'design/info' は root 起点で 'docs/design/info/...' にマッチしない
        fp = Path('/project/specs/docs/design/info/readme.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['design/info']))
        # root 起点の 'docs/design' は前置きマッチする
        self.assertTrue(toc_utils.should_exclude(fp, root, ['docs/design']))

    def test_multiple_patterns_plan(self):
        """複数パターン: plan ディレクトリのファイルが除外される"""
        root = Path('/project/specs')
        fp = Path('/project/specs/plan/item.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['plan', 'draft']))

    def test_multiple_patterns_draft(self):
        """複数パターン: draft ディレクトリのファイルが除外される"""
        root = Path('/project/specs')
        fp = Path('/project/specs/draft/item.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['plan', 'draft']))

    def test_multiple_patterns_normal_file(self):
        """複数パターン: 通常ファイルは除外されない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/requirements/auth.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['plan', 'draft']))

    def test_empty_patterns(self):
        """空パターンは何も除外しない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/main/requirements/auth.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, []))

    def test_deeply_nested_plan(self):
        """深くネストされた plan ディレクトリ"""
        root = Path('/project/specs')
        fp = Path('/project/specs/a/b/c/plan/d/file.md')
        self.assertTrue(toc_utils.should_exclude(fp, root, ['plan']))

    def test_deeply_nested_planning_not_excluded(self):
        """深くネストされた planning ディレクトリは 'plan' にマッチしない"""
        root = Path('/project/specs')
        fp = Path('/project/specs/a/b/c/planning/d/file.md')
        self.assertFalse(toc_utils.should_exclude(fp, root, ['plan']))


# ===========================================================================
# yaml_escape テスト（test_edge_cases.sh から移行）
# ===========================================================================

class TestYamlEscape(unittest.TestCase):
    """yaml_escape() のクォートルールテスト。"""

    # --- クォート不要（block plain scalar safe） ---

    def test_plain_text(self):
        result = toc_utils.yaml_escape('normal text')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_comma_in_middle(self):
        result = toc_utils.yaml_escape('App Store, Google Play')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_parens_with_comma(self):
        result = toc_utils.yaml_escape('scope (App Store, Google Play)')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_parens_with_comma_2(self):
        result = toc_utils.yaml_escape('Role assignments (Yumemi, Daytona)')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_colon_without_trailing_space(self):
        result = toc_utils.yaml_escape('10:00 deadline')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_ampersand_in_middle(self):
        result = toc_utils.yaml_escape('foo&bar')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_brackets_in_middle(self):
        result = toc_utils.yaml_escape('item [1] description')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    # --- クォート必要（YAML special） ---

    def test_colon_space(self):
        result = toc_utils.yaml_escape('foo: bar')
        self.assertTrue(result.startswith('"') and result.endswith('"'),
                        f'should be quoted: {result}')

    def test_space_hash(self):
        result = toc_utils.yaml_escape('see section #3')
        self.assertTrue(result.startswith('"') and result.endswith('"'),
                        f'should be quoted: {result}')

    def test_starts_with_bracket(self):
        result = toc_utils.yaml_escape('[starts with bracket')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_brace(self):
        result = toc_utils.yaml_escape('{starts with brace')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_dash(self):
        result = toc_utils.yaml_escape('- starts with dash')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_hash(self):
        result = toc_utils.yaml_escape('#starts with hash')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_star(self):
        result = toc_utils.yaml_escape('*starts with star')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_amp(self):
        result = toc_utils.yaml_escape('&starts with amp')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_bang(self):
        result = toc_utils.yaml_escape('!starts with bang')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_trailing_colon(self):
        result = toc_utils.yaml_escape('trailing colon:')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_trailing_space(self):
        result = toc_utils.yaml_escape('trailing space ')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_leading_space(self):
        result = toc_utils.yaml_escape(' leading space')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_true(self):
        result = toc_utils.yaml_escape('true')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_false(self):
        result = toc_utils.yaml_escape('false')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_yes(self):
        result = toc_utils.yaml_escape('yes')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_no(self):
        result = toc_utils.yaml_escape('no')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_on(self):
        result = toc_utils.yaml_escape('on')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_boolean_off(self):
        result = toc_utils.yaml_escape('off')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_null_keyword(self):
        result = toc_utils.yaml_escape('null')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_none_keyword(self):
        result = toc_utils.yaml_escape('none')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_tilde(self):
        result = toc_utils.yaml_escape('~')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_integer(self):
        result = toc_utils.yaml_escape('123')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_float(self):
        result = toc_utils.yaml_escape('3.14')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_empty_string(self):
        result = toc_utils.yaml_escape('')
        self.assertEqual(result, '""')

    def test_newline(self):
        result = toc_utils.yaml_escape('line1\nline2')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')
        self.assertIn('\\n', result)

    def test_tab(self):
        result = toc_utils.yaml_escape('has\ttab')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')
        self.assertIn('\\t', result)

    def test_double_quotes_in_string(self):
        result = toc_utils.yaml_escape('has "double quotes"')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')
        # 内部の " がエスケープされていること
        self.assertIn('\\"', result)

    def test_single_quotes_in_string(self):
        result = toc_utils.yaml_escape("has 'single quotes'")
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_backslash_not_quoted(self):
        """バックスラッシュのみではクォート不要（YAML spec 上は plain scalar で有効）"""
        result = toc_utils.yaml_escape('path\\to\\file')
        self.assertFalse(result.startswith('"'), f'should not be quoted: {result}')

    def test_backslash_with_special_char_quoted(self):
        """バックスラッシュ + 改行など特殊文字でクォートされる場合はエスケープされる"""
        result = toc_utils.yaml_escape('path\\to\nfile')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')
        self.assertIn('\\\\', result)

    def test_starts_with_percent(self):
        result = toc_utils.yaml_escape('%TAG')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_at(self):
        result = toc_utils.yaml_escape('@mention')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_backtick(self):
        result = toc_utils.yaml_escape('`code`')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_pipe(self):
        result = toc_utils.yaml_escape('|literal block')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_greater_than(self):
        result = toc_utils.yaml_escape('>folded block')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_starts_with_question(self):
        result = toc_utils.yaml_escape('?mapping key')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')

    def test_carriage_return(self):
        result = toc_utils.yaml_escape('line1\rline2')
        self.assertTrue(result.startswith('"'), f'should be quoted: {result}')
        self.assertIn('\\r', result)

    def test_unicode_preserved(self):
        """Unicode 文字列はそのまま保持される"""
        result = toc_utils.yaml_escape('日本語テスト')
        self.assertEqual(result, '日本語テスト')

    def test_none_input(self):
        """None 入力は空文字列を返す"""
        result = toc_utils.yaml_escape(None)
        self.assertEqual(result, '""')


# ===========================================================================
# normalize_path テスト
# ===========================================================================

class TestNormalizePath(unittest.TestCase):
    """normalize_path() の NFC 正規化テスト。"""

    def test_ascii_unchanged(self):
        self.assertEqual(toc_utils.normalize_path('docs/rules/'), 'docs/rules/')

    def test_nfc_normalization(self):
        """NFD 形式が NFC に正規化される"""
        nfd = unicodedata.normalize('NFD', 'プラグイン')
        result = toc_utils.normalize_path(nfd)
        expected = unicodedata.normalize('NFC', 'プラグイン')
        self.assertEqual(result, expected)

    def test_already_nfc(self):
        """NFC 形式はそのまま"""
        nfc = unicodedata.normalize('NFC', 'テスト')
        result = toc_utils.normalize_path(nfc)
        self.assertEqual(result, nfc)

    def test_path_object(self):
        """Path オブジェクトも文字列に変換して処理"""
        result = toc_utils.normalize_path(Path('docs/rules'))
        self.assertEqual(result, 'docs/rules')


# ===========================================================================
# get_project_root テスト
# ===========================================================================

class TestGetProjectRoot(unittest.TestCase):
    """get_project_root() のテスト。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.original_env = os.environ.get('CLAUDE_PROJECT_DIR')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if self.original_env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self.original_env

    def test_env_var(self):
        """CLAUDE_PROJECT_DIR set → returns that path"""
        os.environ['CLAUDE_PROJECT_DIR'] = self.tmpdir
        result = toc_utils.get_project_root()
        self.assertEqual(result, Path(self.tmpdir))

    def test_invalid_env_falls_back_to_cwd(self):
        """CLAUDE_PROJECT_DIR invalid → falls back to cwd"""
        os.environ['CLAUDE_PROJECT_DIR'] = '/nonexistent/path'
        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            result = toc_utils.get_project_root()
            self.assertEqual(result, Path(self.tmpdir).resolve())
        finally:
            os.chdir(original_cwd)

    def test_no_env_returns_cwd(self):
        """No CLAUDE_PROJECT_DIR → returns cwd"""
        os.environ.pop('CLAUDE_PROJECT_DIR', None)
        original_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            result = toc_utils.get_project_root()
            self.assertEqual(result, Path(self.tmpdir).resolve())
        finally:
            os.chdir(original_cwd)


# ===========================================================================
# validate_path_within_base テスト（traversal 専用流用 / 挙動不変）
# ===========================================================================

class TestValidatePathWithinBase(unittest.TestCase):
    """validate_path_within_base() の traversal 検証テスト。

    DES-005 §5.1 / §5.2 で本関数は traversal 専用として流用し、
    docstring・論理パス検証ポリシーは変更しない。symlink 厳格化は
    resolve_within_root が担う（両者を分離）。本クラスは流用元の
    挙動が不変であることを固定する。
    """

    def test_normal_path_returns_joined(self):
        """通常パスは base/path の join を返す（例外なし）"""
        result = toc_utils.validate_path_within_base('docs/a.md', '/project')
        self.assertEqual(Path(result), Path('/project/docs/a.md'))

    def test_traversal_rejected(self):
        """.. による root 外参照は ValueError"""
        with self.assertRaises(ValueError):
            toc_utils.validate_path_within_base('../outside.md', '/project')

    def test_nested_traversal_rejected(self):
        """ネストされた .. で root を抜ける場合も ValueError"""
        with self.assertRaises(ValueError):
            toc_utils.validate_path_within_base('docs/../../escape.md', '/project')

    def test_inner_traversal_allowed(self):
        """root 内に留まる .. は許可される"""
        result = toc_utils.validate_path_within_base('docs/sub/../a.md', '/project')
        # join は正規化前のパスを返す（既存仕様）
        self.assertEqual(Path(result), Path('/project/docs/sub/../a.md'))


# ===========================================================================
# resolve_within_root テスト（新規 symlink 実体解決 / DES-005 §5.2）
# ===========================================================================

class TestResolveWithinRoot(unittest.TestCase):
    """resolve_within_root() の symlink 実体解決テスト。"""

    def setUp(self):
        # symlink の実体差を確実にするため tmpdir を resolve しておく
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.outside = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_existing_file_within_root(self):
        """root 配下の実在ファイルは resolve 済み実体を返す"""
        f = self.root / 'a.md'
        f.write_text('# a\n', encoding='utf-8')
        result = toc_utils.resolve_within_root(f, self.root)
        self.assertEqual(result, f.resolve())

    def test_missing_file_raises_filenotfound(self):
        """不在ファイルは FileNotFoundError（strict=True）"""
        with self.assertRaises(FileNotFoundError):
            toc_utils.resolve_within_root(self.root / 'missing.md', self.root)

    def test_symlink_to_outside_rejected(self):
        """root 外の実体を指す symlink は OUTSIDE_ROOT で reject"""
        target = self.outside / 'secret.md'
        target.write_text('# secret\n', encoding='utf-8')
        link = self.root / 'link.md'
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        with self.assertRaises(toc_utils.PathRejection) as ctx:
            toc_utils.resolve_within_root(link, self.root)
        self.assertEqual(ctx.exception.error_code, 'OUTSIDE_ROOT')

    def test_symlink_within_root_allowed(self):
        """root 内の実体を指す symlink は許可される"""
        target = self.root / 'real.md'
        target.write_text('# real\n', encoding='utf-8')
        link = self.root / 'alias.md'
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        result = toc_utils.resolve_within_root(link, self.root)
        self.assertEqual(result, target.resolve())


# ===========================================================================
# find_escaping_symlink テスト（越境 symlink prefix 特定 / NFR-N06）
# ===========================================================================

class TestFindEscapingSymlink(unittest.TestCase):
    """find_escaping_symlink() が越境 symlink の最上位 prefix を返すことを固定する。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.outside = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_no_symlink_returns_none(self):
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'a.md').write_text('# a\n', encoding='utf-8')
        self.assertIsNone(toc_utils.find_escaping_symlink('docs/a.md', self.root))

    def test_file_symlink_to_outside(self):
        target = self.outside / 'x.md'
        target.write_text('# x\n', encoding='utf-8')
        link = self.root / 'linked.md'
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        self.assertEqual(
            toc_utils.find_escaping_symlink('linked.md', self.root), 'linked.md'
        )

    def test_dir_symlink_returns_topmost_prefix(self):
        """ディレクトリ symlink 配下の深いパスでも、越境点（dir symlink）を返す。"""
        (self.outside / 'sub').mkdir()
        (self.outside / 'sub' / 'y.md').write_text('# y\n', encoding='utf-8')
        link = self.root / 'ext'
        try:
            link.symlink_to(self.outside)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        self.assertEqual(
            toc_utils.find_escaping_symlink('ext/sub/y.md', self.root), 'ext'
        )

    def test_internal_symlink_not_escaping(self):
        """root 内を指す symlink は越境ではない → None。"""
        (self.root / 'real.md').write_text('# r\n', encoding='utf-8')
        link = self.root / 'alias.md'
        try:
            link.symlink_to(self.root / 'real.md')
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        self.assertIsNone(toc_utils.find_escaping_symlink('alias.md', self.root))


# ===========================================================================
# validate_path テスト（検証フロー 6 系統 / DES-005 §5.1）
# ===========================================================================

class TestValidatePath(unittest.TestCase):
    """validate_path() の検証フローテスト。

    6 系統: 絶対パス / traversal / 不在 / root 外 symlink / 非 Markdown / 正常。
    加えて ./a.md ↔ a.md の同一視を固定する。error_code は
    toc_store.ErrorCode と整合する文字列。
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.outside = Path(tempfile.mkdtemp()).resolve()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.outside, ignore_errors=True)

    def _make_md(self, rel):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('# doc\n', encoding='utf-8')
        return p

    # --- 1. 絶対パス ---

    def test_absolute_path_rejected(self):
        with self.assertRaises(toc_utils.PathRejection) as ctx:
            toc_utils.validate_path('/etc/passwd.md', self.root)
        self.assertEqual(ctx.exception.error_code, 'ABSOLUTE_PATH')

    # --- 2. traversal ---

    def test_traversal_rejected(self):
        with self.assertRaises(toc_utils.PathRejection) as ctx:
            toc_utils.validate_path('../escape.md', self.root)
        self.assertEqual(ctx.exception.error_code, 'PATH_TRAVERSAL')

    # --- 3. 不在 ---

    def test_missing_file_rejected(self):
        with self.assertRaises(toc_utils.PathRejection) as ctx:
            toc_utils.validate_path('docs/missing.md', self.root)
        self.assertEqual(ctx.exception.error_code, 'NOT_FOUND')

    # --- 4. root 外 symlink（受理し、越境 prefix を通知する。NFR-N06）---

    def test_outside_root_symlink_accepted_and_reported(self):
        """越境 symlink は受理され、越境した prefix が戻り値で通知される。

        呼び出し元（上位層）が索引対象として渡したものであり、それが symlink である
        ことは渡す側が知っている。doc-advisor は塞がず、warning のために prefix を返す。
        """
        target = self.outside / 'secret.md'
        target.write_text('# secret\n', encoding='utf-8')
        link = self.root / 'link.md'
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        result, external = toc_utils.validate_path('link.md', self.root)
        self.assertEqual(result, 'link.md')
        self.assertEqual(external, 'link.md')

    def test_outside_root_symlink_via_directory_reports_the_dir(self):
        """ディレクトリ symlink 経由なら、通知される prefix はそのディレクトリである。"""
        (self.outside / 'shared').mkdir(parents=True, exist_ok=True)
        (self.outside / 'shared' / 'spec.md').write_text('# spec\n', encoding='utf-8')
        link = self.root / 'shared'
        try:
            link.symlink_to(self.outside / 'shared', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        result, external = toc_utils.validate_path('shared/spec.md', self.root)
        self.assertEqual(result, 'shared/spec.md')
        self.assertEqual(external, 'shared')

    def test_internal_symlink_reports_no_external(self):
        """root 内で完結する symlink では external が None になる。"""
        self._make_md('docs/real.md')
        link = self.root / 'alias.md'
        try:
            link.symlink_to(self.root / 'docs' / 'real.md')
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        result, external = toc_utils.validate_path('alias.md', self.root)
        self.assertEqual(result, 'alias.md')
        self.assertIsNone(external)

    # --- 5. 非 Markdown ---

    def test_non_markdown_rejected(self):
        p = self.root / 'a.txt'
        p.write_text('not md\n', encoding='utf-8')
        with self.assertRaises(toc_utils.PathRejection) as ctx:
            toc_utils.validate_path('a.txt', self.root)
        self.assertEqual(ctx.exception.error_code, 'NOT_MARKDOWN')

    # --- 6. 正常 accept ---

    def test_valid_markdown_accepted(self):
        self._make_md('docs/a.md')
        result, external = toc_utils.validate_path('docs/a.md', self.root)
        self.assertEqual(result, 'docs/a.md')
        self.assertIsNone(external)

    def test_markdown_extension_variant_accepted(self):
        """.markdown 拡張子も受理される"""
        self._make_md('docs/b.markdown')
        result, _external = toc_utils.validate_path('docs/b.markdown', self.root)
        self.assertEqual(result, 'docs/b.markdown')

    # --- ./a.md ↔ a.md 同一視 ---

    def test_dot_slash_normalized(self):
        """./a.md は a.md に正規化されて同一視される"""
        self._make_md('a.md')
        result, _external = toc_utils.validate_path('./a.md', self.root)
        self.assertEqual(result, 'a.md')

    def test_dot_slash_matches_plain(self):
        """./a.md と a.md が同一の正規化結果になる"""
        self._make_md('docs/a.md')
        r1, _e1 = toc_utils.validate_path('docs/a.md', self.root)
        r2, _e2 = toc_utils.validate_path('./docs/a.md', self.root)
        self.assertEqual(r1, r2)


# ===========================================================================
# detect_case_collisions テスト（大小衝突 warning / DES-005 §5.2）
# ===========================================================================

class TestDetectCaseCollisions(unittest.TestCase):
    """detect_case_collisions() の case-insensitive 衝突検出テスト。"""

    def test_no_collision(self):
        warnings = toc_utils.detect_case_collisions(['docs/a.md', 'docs/b.md'])
        self.assertEqual(warnings, [])

    def test_collision_detected(self):
        """大文字小文字のみ異なる path は warning として検出される（reject しない）"""
        warnings = toc_utils.detect_case_collisions(['docs/A.md', 'docs/a.md'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('case-insensitive collision', warnings[0])

    def test_exact_duplicate_no_collision(self):
        """完全一致の重複は衝突 warning を出さない"""
        warnings = toc_utils.detect_case_collisions(['docs/a.md', 'docs/a.md'])
        self.assertEqual(warnings, [])

    def test_multiple_collisions(self):
        warnings = toc_utils.detect_case_collisions(
            ['A.md', 'a.md', 'docs/X.md', 'docs/x.md']
        )
        self.assertEqual(len(warnings), 2)


# ===========================================================================
# error_code 整合テスト（toc_store.ErrorCode との一致 / FR-N08-2）
# ===========================================================================

class TestErrorCodeIntegration(unittest.TestCase):
    """validate_path / resolve_within_root が出す error_code が
    toc_store.ErrorCode 定数（ERROR_CODES enum）に含まれることを固定する。"""

    def setUp(self):
        import toc_store
        self.toc_store = toc_store

    def test_path_error_codes_in_enum(self):
        for code in ('ABSOLUTE_PATH', 'PATH_TRAVERSAL', 'NOT_FOUND',
                     'OUTSIDE_ROOT', 'NOT_MARKDOWN'):
            self.assertIn(code, self.toc_store.ERROR_CODES,
                          f'{code} must be a defined error_code')


class TestFilterExcluded(unittest.TestCase):
    """除外を「確定した対象集合」へ適用すること。

    除外は「選び方」ではなく「選んだ結果から何を落とすか」である。ディレクトリ展開の
    内側だけで適用すると、`--dirs` を伴わない指定で黙って無視される。
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.root = Path(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_no_patterns_keeps_everything(self):
        kept, excluded = toc_utils.filter_excluded(['docs/a.md'], self.root, [])
        self.assertEqual(kept, ['docs/a.md'])
        self.assertEqual(excluded, [])

    def test_file_pattern_excludes_that_file_only(self):
        kept, excluded = toc_utils.filter_excluded(
            ['docs/a.md', 'docs/b.md'], self.root, ['docs/b.md']
        )
        self.assertEqual(kept, ['docs/a.md'])
        self.assertEqual(excluded, ['docs/b.md'])

    def test_subtree_pattern_excludes_the_subtree(self):
        kept, excluded = toc_utils.filter_excluded(
            ['docs/a.md', 'docs/draft/b.md'], self.root, ['docs/draft']
        )
        self.assertEqual(kept, ['docs/a.md'])
        self.assertEqual(excluded, ['docs/draft/b.md'])

    def test_bare_directory_name_matches_at_any_depth(self):
        kept, _excluded = toc_utils.filter_excluded(
            ['docs/a.md', 'docs/x/draft/b.md'], self.root, ['draft']
        )
        self.assertEqual(kept, ['docs/a.md'])

    def test_trailing_slash_is_normalized(self):
        kept, excluded = toc_utils.filter_excluded(
            ['docs/a.md', 'docs/draft/b.md'], self.root, ['docs/draft/']
        )
        self.assertEqual(kept, ['docs/a.md'])
        self.assertEqual(excluded, ['docs/draft/b.md'])

    def test_absolute_path_outside_root_does_not_raise(self):
        """root 配下に解決できない入力で例外を投げないこと。

        should_exclude は relative_to(root) の成立を前提とする。ここで ValueError を
        通すと、除外を伴うだけで CLI が traceback で落ちて JSON を返さなくなる
        （DES-005 §8.1 の契約違反）。不正なパスの分類は下流の責務である。
        """
        kept, excluded = toc_utils.filter_excluded(
            ['/etc/hosts.md', 'docs/a.md'], self.root, ['docs/draft']
        )
        self.assertEqual(kept, ['/etc/hosts.md', 'docs/a.md'])
        self.assertEqual(excluded, [])

    def test_absolute_path_inside_root_is_still_judged(self):
        """root 配下を指す絶対パスは従来どおり判定する（過剰な素通しを防ぐ）。"""
        inside = str(self.root / 'docs' / 'draft' / 'b.md')

        kept, excluded = toc_utils.filter_excluded(
            [inside], self.root, ['docs/draft']
        )

        self.assertEqual(kept, [])
        self.assertEqual(excluded, [inside])

    def test_parent_traversal_does_not_raise(self):
        kept, _excluded = toc_utils.filter_excluded(
            ['../outside.md'], self.root, ['docs/draft']
        )
        self.assertEqual(kept, ['../outside.md'])

    def test_semantics_match_should_exclude(self):
        """判定は should_exclude を共有する（規則を 2 実装に分けない）。"""
        paths = ['docs/a.md', 'docs/plan/b.md', 'docs/planning.md']
        kept, _excluded = toc_utils.filter_excluded(paths, self.root, ['plan'])
        self.assertEqual(
            kept, ['docs/a.md', 'docs/planning.md'],
            "裸名はディレクトリ名の完全一致であり planning.md を落とさない",
        )


class TestEnsureProjectRootCwd(unittest.TestCase):
    """cwd を project root へ揃えることで、パスの基準が 1 つになること（Issue #41）。

    project-root-relative なパスを「結合して開く」作法と「そのまま開く」作法が同じ
    実行の中で交差しており、cwd と project root が違えば別のファイルを指した。一致を
    検査して弾くのでは 2 つの作法が残るため、基準を揃えて食い違いが起こり得ない
    状態にする。
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._env = os.environ.get('CLAUDE_PROJECT_DIR')
        self._tmp = tempfile.mkdtemp()
        self.root = Path(self._tmp) / 'root'
        (self.root / 'sub').mkdir(parents=True)

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self._env
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_cwd_moves_to_project_root(self):
        os.environ['CLAUDE_PROJECT_DIR'] = str(self.root)
        os.chdir(self.root / 'sub')

        returned = toc_utils.ensure_project_root_cwd()

        self.assertEqual(Path(os.getcwd()).resolve(), self.root.resolve())
        self.assertEqual(returned, self.root.resolve())

    def test_both_conventions_resolve_to_the_same_file(self):
        """結合する作法とそのまま開く作法が同一ファイルを指すこと（本来の目的）。"""
        os.environ['CLAUDE_PROJECT_DIR'] = str(self.root)
        (self.root / 'a.md').write_text('root side', encoding='utf-8')
        (self.root / 'sub' / 'a.md').write_text('sub side', encoding='utf-8')
        os.chdir(self.root / 'sub')

        project_root = toc_utils.ensure_project_root_cwd()

        joined = (project_root / 'a.md').read_text(encoding='utf-8')
        as_is = Path('a.md').read_text(encoding='utf-8')
        self.assertEqual(joined, as_is)
        self.assertEqual(joined, 'root side')

    def test_already_at_project_root_is_a_no_op(self):
        os.environ['CLAUDE_PROJECT_DIR'] = str(self.root)
        os.chdir(self.root)

        toc_utils.ensure_project_root_cwd()

        self.assertEqual(Path(os.getcwd()).resolve(), self.root.resolve())


class TestNormalizeFieldValue(unittest.TestCase):
    """メタデータ値を、意味を変えずに値域内へ収めること（Issue #41）。

    値域から外れる文字のうち意味を保つ代替があるものは、拒否せず書き込みの入口で
    変換する。拒否すると文字 1 つのために文書のメタデータ全体が AI 再抽出へ回るが、
    原因は意味に関わらない表記であり、その費用を払う理由がない。
    """

    def _round_trips(self, value):
        emitted = toc_utils.yaml_escape(value)
        return emitted.strip().strip('"\'') == value

    def test_double_quotes_become_backticks(self):
        got, changed = toc_utils.normalize_field_value('Say "hi" now')
        self.assertEqual(got, 'Say `hi` now')
        self.assertTrue(changed)

    def test_newlines_and_tabs_become_single_spaces(self):
        got, changed = toc_utils.normalize_field_value('a\nb\tc')
        self.assertEqual(got, 'a b c')
        self.assertTrue(changed)

    def test_edge_single_quotes_become_backticks(self):
        self.assertEqual(
            toc_utils.normalize_field_value("'all' reserved key")[0],
            "`all' reserved key",
        )
        self.assertEqual(
            toc_utils.normalize_field_value("trailing quote'")[0],
            'trailing quote`',
        )

    def test_interior_single_quote_is_preserved(self):
        """変換範囲は最小に保つ（両端だけが読み側で問題になる）。"""
        got, changed = toc_utils.normalize_field_value("doesn't break")
        self.assertEqual(got, "doesn't break")
        self.assertFalse(changed)

    def test_backslash_is_not_converted(self):
        """意味を保つ代替が存在しないため変換しない（値域検証側で拒否する）。"""
        got, changed = toc_utils.normalize_field_value('a\\nb')
        self.assertEqual(got, 'a\\nb')
        self.assertFalse(changed)

    def test_round_trippable_values_are_left_untouched(self):
        for value in ('query-docs: entry point', 'a #tag', '- hyphen', 'ends with space '):
            with self.subTest(value=value):
                got, changed = toc_utils.normalize_field_value(value)
                self.assertEqual(got, value)
                self.assertFalse(changed)

    def test_normalized_values_round_trip(self):
        for raw in (
            'has "quotes"',
            "'quoted' phrase",
            "ends with quote'",
            'multi\nline\ttext',
            'plain text',
        ):
            with self.subTest(raw=raw):
                normalized, _ = toc_utils.normalize_field_value(raw)
                self.assertTrue(self._round_trips(normalized))

    def test_non_string_is_returned_as_is(self):
        self.assertEqual(toc_utils.normalize_field_value(None), (None, False))
        self.assertEqual(toc_utils.normalize_field_value(7), (7, False))


class TestSanitizeUncontrolledText(unittest.TestCase):
    """内容を統制できない値（捕捉した例外メッセージ等）を入口で正規化すること。

    メタデータ 5 フィールドは値域規則で「単一行の平文」を強制できるが、例外メッセージ
    は内容を選べないため同じ制約を課せない。そこで入口で正規化する（Issue #41）。
    エスケープに頼らないのは、読み側（parse_simple_yaml / load_existing_toc）が
    引用符を外すだけでエスケープを復元しないためである。
    """

    def _round_trips(self, value):
        emitted = toc_utils.yaml_escape(value)
        return emitted.strip().strip('"\'') == value

    def test_real_exception_message_round_trips_after_sanitize(self):
        """正規化前は壊れ、正規化後は往復することを実際の例外で固定する。"""
        try:
            open('does-not-exist-for-test.md')
        except OSError as e:
            raw = f'{e.__class__.__name__}: {e}'
        self.assertFalse(self._round_trips(raw))
        self.assertTrue(self._round_trips(toc_utils.sanitize_uncontrolled_text(raw)))

    def test_quotes_become_backticks(self):
        self.assertEqual(
            toc_utils.sanitize_uncontrolled_text('said "hi" and \'bye\''),
            'said `hi` and `bye`',
        )

    def test_newlines_and_tabs_collapse_to_single_space(self):
        self.assertEqual(
            toc_utils.sanitize_uncontrolled_text('a\nb\tc\r\nd'), 'a b c d'
        )

    def test_backslash_is_dropped(self):
        self.assertEqual(
            toc_utils.sanitize_uncontrolled_text('path\\to\\thing'), 'pathtothing'
        )

    def test_none_becomes_empty_string(self):
        self.assertEqual(toc_utils.sanitize_uncontrolled_text(None), '')

    def test_result_always_round_trips(self):
        for raw in (
            'plain text',
            'has "quotes"',
            "ends with quote'",
            'back\\slash and: colon',
            'multi\nline\ttext',
            "'edges'",
        ):
            with self.subTest(raw=raw):
                sanitized = toc_utils.sanitize_uncontrolled_text(raw)
                self.assertTrue(self._round_trips(sanitized))


if __name__ == '__main__':
    unittest.main()
