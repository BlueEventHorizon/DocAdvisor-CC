#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シンボリックリンク対応テスト。

test_symlink.sh からの移行:
- シンボリックリンク経由のファイル検出
- ループ検出（自己参照リンク）→ タイムアウトしない
- 重複ファイルの重複排除
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールの import
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
)
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import toc_utils


class TestSymlinkFileDetection(unittest.TestCase):
    """シンボリックリンク経由のファイル検出テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # メインディレクトリ
        self.rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(self.rules_dir)
        with open(os.path.join(self.rules_dir, 'local_rule.md'), 'w') as f:
            f.write('# Local Rule\n')

        # 外部ディレクトリ（シンボリックリンク先）
        self.external_dir = os.path.join(self.tmpdir, 'external')
        os.makedirs(os.path.join(self.external_dir, 'external_rules'))
        with open(
            os.path.join(self.external_dir, 'external_rules', 'external_rule.md'),
            'w'
        ) as f:
            f.write('# External Rule\n')

        # シンボリックリンクを作成
        os.symlink(
            os.path.join(self.external_dir, 'external_rules'),
            os.path.join(self.rules_dir, 'linked_rules')
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_symlinked_file_found(self):
        """シンボリックリンク経由のファイルが検出される"""
        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        filenames = [f.name for f in files]
        self.assertIn('local_rule.md', filenames)
        self.assertIn('external_rule.md', filenames)

    def test_symlinked_directory_traversed(self):
        """シンボリックリンクディレクトリが正しくトラバースされる"""
        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        # ローカル1つ + 外部1つ = 2つ
        self.assertEqual(len(files), 2)


class TestSymlinkLoopDetection(unittest.TestCase):
    """シンボリックリンクループ検出テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(self.rules_dir)
        with open(os.path.join(self.rules_dir, 'normal.md'), 'w') as f:
            f.write('# Normal\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_self_referencing_symlink_no_hang(self):
        """自己参照シンボリックリンクでハングしない"""
        loop_dir = os.path.join(self.rules_dir, 'loop_test')
        os.makedirs(loop_dir)
        # loop_test/self_loop → loop_test（ループ）
        os.symlink(loop_dir, os.path.join(loop_dir, 'self_loop'))

        # タイムアウトせずに完了すること
        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        # 少なくとも normal.md は見つかる
        filenames = [f.name for f in files]
        self.assertIn('normal.md', filenames)

    def test_mutual_symlink_loop_no_hang(self):
        """相互参照シンボリックリンクでハングしない"""
        dir_a = os.path.join(self.rules_dir, 'dir_a')
        dir_b = os.path.join(self.rules_dir, 'dir_b')
        os.makedirs(dir_a)
        os.makedirs(dir_b)
        # dir_a/link_to_b → dir_b, dir_b/link_to_a → dir_a
        os.symlink(dir_b, os.path.join(dir_a, 'link_to_b'))
        os.symlink(dir_a, os.path.join(dir_b, 'link_to_a'))

        with open(os.path.join(dir_a, 'a.md'), 'w') as f:
            f.write('# A\n')
        with open(os.path.join(dir_b, 'b.md'), 'w') as f:
            f.write('# B\n')

        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        filenames = [f.name for f in files]
        self.assertIn('normal.md', filenames)
        self.assertIn('a.md', filenames)
        self.assertIn('b.md', filenames)


class TestSymlinkDeduplication(unittest.TestCase):
    """シンボリックリンクによる重複ファイルの排除テスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.rules_dir = os.path.join(self.tmpdir, 'rules')
        os.makedirs(self.rules_dir)

        # 外部ディレクトリにファイルを作成
        self.external_dir = os.path.join(self.tmpdir, 'external_rules')
        os.makedirs(self.external_dir)
        with open(os.path.join(self.external_dir, 'shared_rule.md'), 'w') as f:
            f.write('# Shared Rule\n')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_duplicate_symlinks_deduplicated(self):
        """同じディレクトリへの複数シンボリックリンクで重複排除される"""
        # 同じ外部ディレクトリへ2つのシンボリックリンクを作成
        os.symlink(self.external_dir, os.path.join(self.rules_dir, 'link1'))
        os.symlink(self.external_dir, os.path.join(self.rules_dir, 'link2'))

        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        # shared_rule.md は1回だけ出現すべき（inode ベースの重複排除）
        filenames = [f.name for f in files]
        self.assertEqual(filenames.count('shared_rule.md'), 1)

    def test_same_file_different_symlinks(self):
        """ファイルへの直接シンボリックリンクでも重複排除される"""
        src_file = os.path.join(self.external_dir, 'shared_rule.md')
        os.symlink(src_file, os.path.join(self.rules_dir, 'link_a.md'))
        os.symlink(src_file, os.path.join(self.rules_dir, 'link_b.md'))

        files = list(toc_utils.rglob_follow_symlinks(
            Path(self.rules_dir), '**/*.md'
        ))
        # inode ベースの重複排除で1つのみ
        self.assertEqual(len(files), 1)


if __name__ == '__main__':
    unittest.main()
