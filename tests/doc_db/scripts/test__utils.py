#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_utils.py のユニットテスト。

検証対象（DES-026 §3.1 / TASK-001 検証要件）:
- calculate_file_hash の安定性（同一内容→同一 hash、内容変更→異 hash）
- normalize_path の NFC 正規化
- rglob_follow_symlinks の通常列挙とシンボリックリンク追跡
- load_checksums / write_checksums_yaml の往復一貫性
- should_exclude の基本パターン
"""

import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

# テスト対象モジュールの import パス（plugins/doc-db/scripts）
SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-db', 'scripts'
))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import _utils  # noqa: E402


class TestCalculateFileHash(unittest.TestCase):
    """calculate_file_hash の安定性テスト。"""

    def test_same_content_same_hash(self):
        """同一内容のファイルは同一ハッシュを返す。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / 'a.md'
            f2 = Path(tmpdir) / 'b.md'
            f1.write_text('hello world\n', encoding='utf-8')
            f2.write_text('hello world\n', encoding='utf-8')
            self.assertEqual(
                _utils.calculate_file_hash(f1),
                _utils.calculate_file_hash(f2),
            )

    def test_different_content_different_hash(self):
        """内容が異なればハッシュも異なる。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / 'a.md'
            f2 = Path(tmpdir) / 'b.md'
            f1.write_text('hello\n', encoding='utf-8')
            f2.write_text('world\n', encoding='utf-8')
            self.assertNotEqual(
                _utils.calculate_file_hash(f1),
                _utils.calculate_file_hash(f2),
            )

    def test_idempotent(self):
        """同じファイルを2回計算しても同じ値を返す。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / 'a.md'
            f.write_text('content\n', encoding='utf-8')
            h1 = _utils.calculate_file_hash(f)
            h2 = _utils.calculate_file_hash(f)
            self.assertEqual(h1, h2)
            # SHA-256 は 64 文字 hex
            self.assertEqual(len(h1), 64)

    def test_missing_file_returns_none(self):
        """存在しないファイルは None を返す（log は stderr に出力）。"""
        result = _utils.calculate_file_hash('/nonexistent/path/to/file.md')
        self.assertIsNone(result)

    def test_chunk_size_variation(self):
        """chunk_size が異なっても同じハッシュ値を返す。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / 'a.md'
            # 64KB を超える内容で chunk 境界を跨がせる
            f.write_text('x' * (65536 * 2 + 100), encoding='utf-8')
            h_default = _utils.calculate_file_hash(f)
            h_small = _utils.calculate_file_hash(f, chunk_size=1024)
            self.assertEqual(h_default, h_small)


class TestNormalizePath(unittest.TestCase):
    """normalize_path の NFC 正規化テスト。"""

    def test_ascii_unchanged(self):
        self.assertEqual(_utils.normalize_path('docs/rules/'), 'docs/rules/')

    def test_nfc_from_nfd(self):
        """NFD（分解形）入力は NFC（合成形）に正規化される。"""
        nfd = unicodedata.normalize('NFD', 'プラグイン')
        result = _utils.normalize_path(nfd)
        self.assertEqual(result, unicodedata.normalize('NFC', 'プラグイン'))

    def test_nfc_idempotent(self):
        """NFC 入力はそのまま返る（恒等性）。"""
        nfc = unicodedata.normalize('NFC', 'ドキュメント')
        self.assertEqual(_utils.normalize_path(nfc), nfc)

    def test_dakuten_handakuten(self):
        """濁点・半濁点を含む文字列が NFC に統一される。"""
        # NFD: フ + ゜ → NFC: プ
        nfd = 'フ' + '゚'  # フ + 結合半濁点
        result = _utils.normalize_path(nfd)
        self.assertEqual(result, 'プ')

    def test_path_object_input(self):
        """Path オブジェクトも文字列に変換して NFC 正規化する。"""
        result = _utils.normalize_path(Path('docs/rules/a.md'))
        self.assertEqual(result, 'docs/rules/a.md')


class TestRglobFollowSymlinks(unittest.TestCase):
    """rglob_follow_symlinks のファイル列挙テスト。"""

    def test_basic_recursive(self):
        """**/*.md パターンで再帰的にファイルを列挙する。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'a.md').write_text('a', encoding='utf-8')
            (root / 'sub').mkdir()
            (root / 'sub' / 'b.md').write_text('b', encoding='utf-8')
            (root / 'sub' / 'deep').mkdir()
            (root / 'sub' / 'deep' / 'c.md').write_text('c', encoding='utf-8')

            files = sorted(_utils.rglob_follow_symlinks(root, '**/*.md'))
            self.assertEqual(len(files), 3)
            self.assertEqual([f.name for f in files], ['a.md', 'b.md', 'c.md'])

    def test_filters_by_extension(self):
        """拡張子が違うファイルは除外される。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'a.md').write_text('a', encoding='utf-8')
            (root / 'b.txt').write_text('b', encoding='utf-8')

            files = list(_utils.rglob_follow_symlinks(root, '**/*.md'))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, 'a.md')

    def test_non_recursive(self):
        """** を含まないパターンは直下のみ列挙する。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'a.md').write_text('a', encoding='utf-8')
            (root / 'sub').mkdir()
            (root / 'sub' / 'b.md').write_text('b', encoding='utf-8')

            files = list(_utils.rglob_follow_symlinks(root, '*.md'))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, 'a.md')

    def test_follows_symlinks(self):
        """シンボリックリンク経由のディレクトリも列挙する（環境依存はスキップ）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            real_dir = root / 'real'
            real_dir.mkdir()
            (real_dir / 'r.md').write_text('r', encoding='utf-8')

            link_dir = root / 'link'
            try:
                link_dir.symlink_to(real_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('symlink not supported in this environment')

            files = sorted(_utils.rglob_follow_symlinks(root, '**/*.md'))
            # 実体が同じファイルへの複数経路は重複排除される（inode 検査）
            # よって r.md は 1 件のみ列挙されるはず
            self.assertEqual(len(files), 1)


class TestChecksumRoundTrip(unittest.TestCase):
    """write_checksums_yaml / load_checksums の往復一貫性。"""

    def test_round_trip_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'checksums.yaml'
            checksums = {
                'docs/a.md': 'a' * 64,
                'docs/sub/b.md': 'b' * 64,
                'specs/c.md': 'c' * 64,
            }
            self.assertTrue(_utils.write_checksums_yaml(
                checksums, output, header_comment='test'
            ))
            self.assertTrue(output.exists())

            loaded = _utils.load_checksums(output)
            self.assertEqual(loaded, checksums)

    def test_load_missing_file_returns_empty(self):
        """存在しないファイルは空 dict を返す（クラッシュしない）。"""
        result = _utils.load_checksums('/nonexistent/checksums.yaml')
        self.assertEqual(result, {})

    def test_round_trip_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'checksums.yaml'
            self.assertTrue(_utils.write_checksums_yaml({}, output))
            loaded = _utils.load_checksums(output)
            self.assertEqual(loaded, {})

    def test_creates_parent_dir(self):
        """親ディレクトリが存在しなくても作成する。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'nested' / 'dir' / 'checksums.yaml'
            self.assertTrue(_utils.write_checksums_yaml(
                {'a.md': 'h' * 64}, output
            ))
            self.assertTrue(output.exists())


class TestShouldExclude(unittest.TestCase):
    """should_exclude の基本パターンマッチ。"""

    def test_no_pattern_means_no_exclude(self):
        self.assertFalse(_utils.should_exclude(
            Path('/root/docs/a.md'), Path('/root'), []
        ))

    def test_dir_name_match(self):
        """exclude に一致するディレクトリ配下のファイルは除外される。"""
        self.assertTrue(_utils.should_exclude(
            Path('/root/docs/archived/a.md'),
            Path('/root'),
            ['archived'],
        ))

    def test_dir_name_no_match(self):
        self.assertFalse(_utils.should_exclude(
            Path('/root/docs/active/a.md'),
            Path('/root'),
            ['archived'],
        ))

    def test_filename_not_excluded(self):
        """ファイル名 'archived.md' は archived パターンで除外されない（ディレクトリ名のみマッチ）。"""
        self.assertFalse(_utils.should_exclude(
            Path('/root/docs/archived.md'),
            Path('/root'),
            ['archived'],
        ))

    def test_path_substring_pattern(self):
        """パターンに / を含む場合はパス部分文字列でマッチ。"""
        self.assertTrue(_utils.should_exclude(
            Path('/root/docs/old/archive/a.md'),
            Path('/root'),
            ['old/archive'],
        ))

    def test_partial_word_not_matched(self):
        """plan が planning.md（ディレクトリ名 'plan' でない）に対しては除外しない。"""
        # planning というディレクトリは plan に部分一致しない
        self.assertFalse(_utils.should_exclude(
            Path('/root/docs/planning/a.md'),
            Path('/root'),
            ['plan'],
        ))


if __name__ == '__main__':
    unittest.main()
