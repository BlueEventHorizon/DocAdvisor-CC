#!/usr/bin/env python3
"""
calculate_version.py のテスト

実行:
    python3 -m unittest tests.forge.update-version.test_calculate_version -v
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills' / 'update-version' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from calculate_version import bump_version, parse_semver


class TestParseSemver(unittest.TestCase):
    """parse_semver のテスト"""

    def test_normal(self):
        self.assertEqual(parse_semver("1.2.3"), (1, 2, 3))

    def test_zeros(self):
        self.assertEqual(parse_semver("0.0.0"), (0, 0, 0))

    def test_large_numbers(self):
        self.assertEqual(parse_semver("10.20.30"), (10, 20, 30))

    def test_invalid_two_parts(self):
        with self.assertRaises(ValueError):
            parse_semver("1.2")

    def test_invalid_text(self):
        with self.assertRaises(ValueError):
            parse_semver("abc")

    def test_invalid_four_parts(self):
        with self.assertRaises(ValueError):
            parse_semver("1.2.3.4")

    def test_invalid_with_prefix(self):
        with self.assertRaises(ValueError):
            parse_semver("v1.2.3")

    def test_empty(self):
        with self.assertRaises(ValueError):
            parse_semver("")

    def test_whitespace_trimmed(self):
        self.assertEqual(parse_semver("  1.2.3  "), (1, 2, 3))


class TestBumpVersion(unittest.TestCase):
    """bump_version のテスト"""

    def test_patch(self):
        result = bump_version("999.88.7", "patch")
        self.assertEqual(result["new"], "999.88.8")
        self.assertEqual(result["spec"], "patch")
        self.assertNotIn("warning", result)

    def test_minor(self):
        result = bump_version("999.88.7", "minor")
        self.assertEqual(result["new"], "999.89.0")

    def test_major(self):
        result = bump_version("999.88.7", "major")
        self.assertEqual(result["new"], "1000.0.0")

    def test_patch_carry(self):
        """0.9.9 → 0.9.10（パッチは桁上げなし）"""
        result = bump_version("0.9.9", "patch")
        self.assertEqual(result["new"], "0.9.10")

    def test_minor_carry(self):
        """0.9.9 → 0.10.0"""
        result = bump_version("0.9.9", "minor")
        self.assertEqual(result["new"], "0.10.0")

    def test_direct_higher(self):
        """直接指定（高いバージョン）"""
        result = bump_version("999.88.7", "1000.0.0")
        self.assertEqual(result["new"], "1000.0.0")
        self.assertNotIn("warning", result)

    def test_direct_same(self):
        """直接指定（同じバージョン → warning）"""
        result = bump_version("1.0.0", "1.0.0")
        self.assertEqual(result["warning"], "new <= current")

    def test_direct_lower(self):
        """直接指定（低いバージョン → warning）"""
        result = bump_version("2.0.0", "1.0.0")
        self.assertEqual(result["warning"], "new <= current")

    def test_direct_invalid_format(self):
        """直接指定で不正形式"""
        with self.assertRaises(ValueError):
            bump_version("1.0.0", "abc")

    def test_current_invalid(self):
        """現バージョンが不正形式"""
        with self.assertRaises(ValueError):
            bump_version("invalid", "patch")

    def test_current_preserved(self):
        """current が正しく保持される"""
        result = bump_version("999.88.7", "patch")
        self.assertEqual(result["current"], "999.88.7")


class TestCLI(unittest.TestCase):
    """CLI インターフェースのテスト"""

    def _run(self, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / 'calculate_version.py')] + list(args),
            capture_output=True, text=True, timeout=10,
        )
        return result

    def test_patch_cli(self):
        result = self._run("999.88.7", "patch")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["new"], "999.88.8")

    def test_invalid_cli(self):
        result = self._run("invalid", "patch")
        self.assertEqual(result.returncode, 1)

    def test_no_args_cli(self):
        result = self._run()
        self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
