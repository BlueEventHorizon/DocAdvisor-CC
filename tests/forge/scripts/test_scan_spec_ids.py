#!/usr/bin/env python3
"""
scan_spec_ids.py のテスト

git 操作を mock して、ブランチスキャン・ID 抽出・重複検出をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.scripts.test_scan_spec_ids -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'skills'
                       / 'next-spec-id' / 'scripts'))

from scan_spec_ids import (
    _normalize_glob_to_prefix,
    _run_git,
    detect_base_branch,
    find_duplicates,
    get_scan_branches,
    get_specs_root_dirs,
    scan_ids_in_branch,
    scan_spec_ids,
)


class TestNormalizeGlobToPrefix(unittest.TestCase):
    """_normalize_glob_to_prefix のテスト"""

    def test_simple_path(self):
        self.assertEqual(_normalize_glob_to_prefix('specs/'), 'specs/')

    def test_single_glob(self):
        self.assertEqual(
            _normalize_glob_to_prefix('docs/specs/*/requirements/'),
            'docs/specs/',
        )

    def test_double_glob(self):
        self.assertEqual(
            _normalize_glob_to_prefix('docs/specs/**/design/'),
            'docs/specs/',
        )

    def test_glob_at_start(self):
        self.assertEqual(_normalize_glob_to_prefix('**/specs/'), '')

    def test_no_trailing_slash(self):
        self.assertEqual(
            _normalize_glob_to_prefix('docs/specs/**/design'),
            'docs/specs/',
        )


class TestFindDuplicates(unittest.TestCase):
    """find_duplicates のテスト"""

    def test_no_duplicates(self):
        pairs = [
            ('SCR-001', 'main'),
            ('SCR-002', 'main'),
            ('SCR-003', 'feature/foo'),
        ]
        self.assertEqual(find_duplicates(pairs), [])

    def test_same_id_same_branch(self):
        pairs = [
            ('SCR-001', 'main'),
            ('SCR-001', 'main'),
        ]
        self.assertEqual(find_duplicates(pairs), [])

    def test_duplicate_across_branches(self):
        pairs = [
            ('SCR-001', 'main'),
            ('SCR-001', 'feature/foo'),
            ('SCR-002', 'main'),
        ]
        result = find_duplicates(pairs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'SCR-001')
        self.assertIn('main', result[0]['branches'])
        self.assertIn('feature/foo', result[0]['branches'])

    def test_multiple_duplicates(self):
        pairs = [
            ('SCR-013', 'feature/a'),
            ('SCR-013', 'origin/feature/b'),
            ('SCR-014', 'feature/a'),
            ('SCR-014', 'origin/feature/b'),
        ]
        result = find_duplicates(pairs)
        self.assertEqual(len(result), 2)
        ids = [d['id'] for d in result]
        self.assertIn('SCR-013', ids)
        self.assertIn('SCR-014', ids)

    def test_empty_input(self):
        self.assertEqual(find_duplicates([]), [])


class TestGetSpecsRootDirs(unittest.TestCase):
    """get_specs_root_dirs のテスト"""

    def test_fallback_when_no_doc_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_specs_root_dirs(tmpdir)
            self.assertEqual(result, ['specs/'])

    def test_reads_from_doc_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            doc_structure = os.path.join(tmpdir, '.doc_structure.yaml')
            with open(doc_structure, 'w') as f:
                f.write(
                    '# doc_structure_version: 4.0\n'
                    'specs:\n'
                    '  root_dirs:\n'
                    '    - "docs/specs/**/design/"\n'
                    '    - "docs/specs/**/requirements/"\n'
                )
            result = get_specs_root_dirs(tmpdir)
            self.assertEqual(len(result), 2)
            self.assertIn('docs/specs/**/design/', result)
            self.assertIn('docs/specs/**/requirements/', result)


class TestDetectBaseBranch(unittest.TestCase):
    """detect_base_branch のテスト"""

    @patch('scan_spec_ids.subprocess.run')
    def test_develop_local(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = detect_base_branch(cwd='/tmp')
        self.assertEqual(result, 'develop')

    @patch('scan_spec_ids.subprocess.run')
    def test_main_fallback(self, mock_run):
        def side_effect(args, **kwargs):
            ref = args[3] if len(args) > 3 else ''
            mock = MagicMock()
            if 'main' in ref and 'remotes' not in ref:
                mock.returncode = 0
            else:
                mock.returncode = 1
            return mock
        mock_run.side_effect = side_effect
        result = detect_base_branch(cwd='/tmp')
        self.assertEqual(result, 'main')


class TestScanIdsInBranch(unittest.TestCase):
    """scan_ids_in_branch のテスト"""

    @patch('scan_spec_ids._run_git')
    def test_extracts_ids(self, mock_git):
        mock_git.return_value = (
            'specs/requirements/SCR-001_user_list_spec.md\n'
            'specs/requirements/SCR-002_user_detail_spec.md\n'
            'specs/requirements/FNC-001_auth_spec.md\n'
            'specs/design/DES-001_user_list_design.md'
        )
        result = scan_ids_in_branch(
            'main', 'SCR', ['specs/'], cwd='/tmp'
        )
        self.assertEqual(len(result), 2)
        ids = [r[0] for r in result]
        self.assertIn('SCR-001', ids)
        self.assertIn('SCR-002', ids)

    @patch('scan_spec_ids._run_git')
    def test_no_matches(self, mock_git):
        mock_git.return_value = (
            'specs/requirements/FNC-001_auth_spec.md\n'
            'specs/design/DES-001_user_list_design.md'
        )
        result = scan_ids_in_branch(
            'main', 'SCR', ['specs/'], cwd='/tmp'
        )
        self.assertEqual(result, [])

    @patch('scan_spec_ids._run_git')
    def test_empty_branch(self, mock_git):
        mock_git.return_value = ''
        result = scan_ids_in_branch(
            'main', 'SCR', ['specs/'], cwd='/tmp'
        )
        self.assertEqual(result, [])

    @patch('scan_spec_ids._run_git')
    def test_glob_dirs_collapsed(self, mock_git):
        """異なる glob パターンが同じプレフィックスに集約される"""
        mock_git.return_value = (
            'docs/specs/auth/requirements/SCR-001_login_spec.md\n'
            'docs/specs/auth/design/DES-001_login_design.md'
        )
        result = scan_ids_in_branch(
            'main', 'SCR',
            ['docs/specs/**/requirements/', 'docs/specs/**/design/'],
            cwd='/tmp',
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'SCR-001')

    @patch('scan_spec_ids._run_git')
    def test_zero_padded_ids(self, mock_git):
        mock_git.return_value = (
            'specs/SCR-001_a.md\n'
            'specs/SCR-015_b.md\n'
            'specs/SCR-100_c.md'
        )
        result = scan_ids_in_branch(
            'main', 'SCR', ['specs/'], cwd='/tmp'
        )
        self.assertEqual(len(result), 3)
        ids = sorted([r[0] for r in result])
        self.assertEqual(ids, ['SCR-001', 'SCR-015', 'SCR-100'])


class TestScanSpecIds(unittest.TestCase):
    """scan_spec_ids 統合テスト（git 操作を mock）"""

    @patch('scan_spec_ids.get_scan_branches')
    @patch('scan_spec_ids.detect_base_branch')
    @patch('scan_spec_ids._run_git')
    @patch('scan_spec_ids.get_specs_root_dirs')
    def test_basic_flow(self, mock_dirs, mock_git, mock_base, mock_branches):
        mock_dirs.return_value = ['specs/']
        mock_base.return_value = 'main'
        mock_branches.return_value = ['main', 'feature/foo']

        def git_side_effect(*args, cwd=None):
            if args[0] == 'fetch':
                return ''
            if args[0] == 'ls-tree':
                branch = args[3]
                if branch == 'main':
                    return (
                        'specs/SCR-001_a.md\n'
                        'specs/SCR-002_b.md\n'
                        'specs/SCR-003_c.md'
                    )
                elif branch == 'feature/foo':
                    return (
                        'specs/SCR-001_a.md\n'
                        'specs/SCR-004_d.md'
                    )
            return ''
        mock_git.side_effect = git_side_effect

        result = scan_spec_ids('SCR', '/tmp/project', cwd='/tmp/project')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['next_id'], 'SCR-005')
        self.assertEqual(result['prefix'], 'SCR')
        self.assertEqual(result['max_number'], 4)
        self.assertEqual(result['base_branch'], 'main')
        self.assertEqual(result['branches_scanned'], 2)
        self.assertEqual(result['ids_found'], 4)
        # SCR-001 exists on both main and feature/foo (inherited via branch)
        self.assertEqual(len(result['duplicates']), 1)
        self.assertEqual(result['duplicates'][0]['id'], 'SCR-001')

    @patch('scan_spec_ids.get_scan_branches')
    @patch('scan_spec_ids.detect_base_branch')
    @patch('scan_spec_ids._run_git')
    @patch('scan_spec_ids.get_specs_root_dirs')
    def test_detects_duplicates(self, mock_dirs, mock_git, mock_base,
                                mock_branches):
        mock_dirs.return_value = ['specs/']
        mock_base.return_value = 'develop'
        mock_branches.return_value = ['develop', 'feature/a', 'feature/b']

        def git_side_effect(*args, cwd=None):
            if args[0] == 'fetch':
                return ''
            if args[0] == 'ls-tree':
                branch = args[3]
                if branch == 'develop':
                    return 'specs/SCR-001_a.md\nspecs/SCR-002_b.md'
                elif branch == 'feature/a':
                    return 'specs/SCR-003_c.md'
                elif branch == 'feature/b':
                    return 'specs/SCR-003_d.md'
            return ''
        mock_git.side_effect = git_side_effect

        result = scan_spec_ids('SCR', '/tmp/project', cwd='/tmp/project')

        self.assertEqual(result['next_id'], 'SCR-004')
        self.assertEqual(len(result['duplicates']), 1)
        self.assertEqual(result['duplicates'][0]['id'], 'SCR-003')
        self.assertIn('feature/a', result['duplicates'][0]['branches'])
        self.assertIn('feature/b', result['duplicates'][0]['branches'])

    @patch('scan_spec_ids.get_scan_branches')
    @patch('scan_spec_ids.detect_base_branch')
    @patch('scan_spec_ids._run_git')
    @patch('scan_spec_ids.get_specs_root_dirs')
    def test_no_existing_ids(self, mock_dirs, mock_git, mock_base,
                             mock_branches):
        mock_dirs.return_value = ['specs/']
        mock_base.return_value = 'main'
        mock_branches.return_value = ['main']
        mock_git.return_value = ''

        result = scan_spec_ids('SCR', '/tmp/project', cwd='/tmp/project')

        self.assertEqual(result['next_id'], 'SCR-001')
        self.assertEqual(result['max_number'], 0)
        self.assertEqual(result['ids_found'], 0)

    @patch('scan_spec_ids.get_scan_branches')
    @patch('scan_spec_ids.detect_base_branch')
    @patch('scan_spec_ids._run_git')
    @patch('scan_spec_ids.get_specs_root_dirs')
    def test_custom_prefix(self, mock_dirs, mock_git, mock_base,
                           mock_branches):
        mock_dirs.return_value = ['specs/']
        mock_base.return_value = 'main'
        mock_branches.return_value = ['main']

        def git_side_effect(*args, cwd=None):
            if args[0] == 'ls-tree':
                return (
                    'specs/CUSTOM-001_a.md\n'
                    'specs/CUSTOM-002_b.md\n'
                    'specs/SCR-001_c.md'
                )
            return ''
        mock_git.side_effect = git_side_effect

        result = scan_spec_ids('CUSTOM', '/tmp/project', cwd='/tmp/project')

        self.assertEqual(result['next_id'], 'CUSTOM-003')
        self.assertEqual(result['prefix'], 'CUSTOM')
        self.assertEqual(result['max_number'], 2)
        self.assertEqual(result['ids_found'], 2)

    @patch('scan_spec_ids.get_scan_branches')
    @patch('scan_spec_ids.detect_base_branch')
    @patch('scan_spec_ids._run_git')
    @patch('scan_spec_ids.get_specs_root_dirs')
    def test_high_numbers(self, mock_dirs, mock_git, mock_base,
                          mock_branches):
        """3桁以上の番号も正しく処理する"""
        mock_dirs.return_value = ['specs/']
        mock_base.return_value = 'main'
        mock_branches.return_value = ['main']

        def git_side_effect(*args, cwd=None):
            if args[0] == 'ls-tree':
                return 'specs/SCR-100_a.md\nspecs/SCR-099_b.md'
            return ''
        mock_git.side_effect = git_side_effect

        result = scan_spec_ids('SCR', '/tmp/project', cwd='/tmp/project')

        self.assertEqual(result['next_id'], 'SCR-101')
        self.assertEqual(result['max_number'], 100)


if __name__ == '__main__':
    unittest.main()
