#!/usr/bin/env python3
"""
update_version_files.py のテスト

実行:
    python3 -m unittest tests.forge.update-version.test_update_version_files -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills' / 'update-version' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from update_version_files import update_version_in_text


class TestSimpleReplace(unittest.TestCase):
    """シンプルな置換テスト"""

    def test_json_quoted(self):
        """JSON のクォート付きバージョン置換"""
        content = '{\n  "version": "999.88.7"\n}'
        result = update_version_in_text(content, "999.88.7", "999.88.8")
        self.assertIn('"999.88.8"', result)
        self.assertNotIn('"999.88.7"', result)

    def test_toml_unquoted(self):
        """TOML のバージョン置換"""
        content = '[package]\nversion = "999.88.7"\n'
        result = update_version_in_text(content, "999.88.7", "999.88.8")
        self.assertIn("999.88.8", result)

    def test_not_found(self):
        """バージョンが見つからない"""
        content = '{"version": "1.0.0"}'
        with self.assertRaises(ValueError):
            update_version_in_text(content, "999.88.7", "999.88.8")

    def test_first_occurrence_only(self):
        """最初の出現のみ置換"""
        content = '"version": "999.88.7"\n"other": "999.88.7"'
        result = update_version_in_text(content, "999.88.7", "999.88.8")
        self.assertEqual(result.count("999.88.8"), 1)
        self.assertEqual(result.count("999.88.7"), 1)

    def test_preserves_formatting(self):
        """JSON フォーマットを保持"""
        content = '{\n  "name": "forge",\n  "version": "999.88.7",\n  "author": "moons"\n}'
        result = update_version_in_text(content, "999.88.7", "999.88.8")
        self.assertIn('"name": "forge"', result)
        self.assertIn('"author": "moons"', result)
        self.assertIn('"999.88.8"', result)


class TestVersionPath(unittest.TestCase):
    """version_path 指定のテスト"""

    def test_top_level_version(self):
        """トップレベルの version フィールド"""
        content = '{\n  "version": "999.88.7"\n}'
        result = update_version_in_text(content, "999.88.7", "999.88.8", version_path="version")
        self.assertIn('"999.88.8"', result)

    def test_nested_path(self):
        """ネストパス package.version"""
        content = '{\n  "package": {\n    "version": "999.88.7"\n  }\n}'
        result = update_version_in_text(content, "999.88.7", "999.88.8", version_path="package.version")
        self.assertIn('"999.88.8"', result)

    def test_path_not_found(self):
        """パスが見つからない"""
        content = '{"name": "test"}'
        with self.assertRaises(ValueError):
            update_version_in_text(content, "999.88.7", "999.88.8", version_path="version")


class TestFilterPattern(unittest.TestCase):
    """filter パターンのテスト"""

    def test_filter_match(self):
        """フィルタパターンにマッチするブロック内のみ置換"""
        content = '| **forge** | 999.88.7 | desc |\n| **anvil** | 888.77.6 | desc |'
        result = update_version_in_text(content, "999.88.7", "999.88.8", filter_pattern="**forge**")
        self.assertIn("999.88.8", result)
        self.assertIn("888.77.6", result)

    def test_filter_no_match(self):
        """フィルタパターンにマッチしない"""
        content = '| **anvil** | 888.77.6 | desc |'
        with self.assertRaises(ValueError):
            update_version_in_text(content, "999.88.7", "999.88.8", filter_pattern="**forge**")

    def test_filter_max_distance_exceeded(self):
        """max_distance 超過時はブロックがリセットされバージョン未発見エラー"""
        # filter 行から 11 行以上離れた位置にバージョンがある場合（max_distance=10）
        lines = ['| **forge** | header |']
        lines += ['filler line'] * 11
        lines += ['999.88.7']
        content = '\n'.join(lines)
        with self.assertRaises(ValueError):
            update_version_in_text(content, "999.88.7", "999.88.8", filter_pattern="**forge**")

    def test_filter_version_on_different_line(self):
        """filter 行とバージョン行が異なる行（JSON ブロック内探索パターン）"""
        content = (
            '{\n'
            '  "plugins": [\n'
            '    {\n'
            '      "name": "forge",\n'
            '      "description": "tools",\n'
            '      "version": "999.88.7"\n'
            '    }\n'
            '  ]\n'
            '}'
        )
        result = update_version_in_text(
            content, "999.88.7", "999.88.8", filter_pattern='"name": "forge"'
        )
        self.assertIn('"999.88.8"', result)
        self.assertNotIn('"999.88.7"', result)

    def test_filter_consecutive_blocks_first_no_version(self):
        """2つの filter ブロックが連続し、1つ目にはバージョンがない場合"""
        content = (
            '{\n'
            '  "name": "anvil",\n'
            '  "description": "other tool"\n'
            '},\n'
            '{\n'
            '  "name": "forge",\n'
            '  "version": "999.88.7"\n'
            '}'
        )
        result = update_version_in_text(
            content, "999.88.7", "999.88.8", filter_pattern='"name": "forge"'
        )
        self.assertIn('"999.88.8"', result)

    def test_filter_within_max_distance(self):
        """max_distance ちょうどの行数でバージョンが見つかる場合"""
        lines = ['| **forge** | header |']
        lines += ['filler line'] * 9  # 9行のフィラー（filter 行から10行目にバージョン）
        lines += ['999.88.7']
        content = '\n'.join(lines)
        result = update_version_in_text(
            content, "999.88.7", "999.88.8", filter_pattern="**forge**"
        )
        self.assertIn("999.88.8", result)


class TestVersionPathToml(unittest.TestCase):
    """TOML 形式の path モードテスト"""

    def test_toml_top_level_version(self):
        """TOML のトップレベル version フィールド"""
        content = '[package]\nname = "my-crate"\nversion = "999.88.7"\n'
        result = update_version_in_text(
            content, "999.88.7", "999.88.8", version_path="version"
        )
        self.assertIn('"999.88.8"', result)
        self.assertNotIn('999.88.7', result)

    def test_toml_preserves_surrounding(self):
        """TOML の version 置換で前後のフィールドが保持される"""
        content = '[package]\nname = "my-crate"\nversion = "999.88.7"\nedition = "2021"\n'
        result = update_version_in_text(
            content, "999.88.7", "999.88.8", version_path="version"
        )
        self.assertIn('name = "my-crate"', result)
        self.assertIn('edition = "2021"', result)
        self.assertIn('"999.88.8"', result)


class TestEmptyVersionValidation(unittest.TestCase):
    """空文字列バリデーションのテスト"""

    def test_empty_old_version(self):
        """old_version が空文字列の場合 ValueError"""
        with self.assertRaises(ValueError) as ctx:
            update_version_in_text('{"version": "1.0.0"}', "", "1.0.1")
        self.assertIn("old_version", str(ctx.exception))

    def test_empty_new_version(self):
        """new_version が空文字列の場合 ValueError"""
        with self.assertRaises(ValueError) as ctx:
            update_version_in_text('{"version": "1.0.0"}', "1.0.0", "")
        self.assertIn("new_version", str(ctx.exception))


class TestCLI(unittest.TestCase):
    """CLI インターフェースのテスト"""

    def _run(self, content, *args):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            tmp_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / 'update_version_files.py'), tmp_path] + list(args),
                capture_output=True, text=True, timeout=10,
            )
            return result
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_basic_cli(self):
        content = '{"version": "999.88.7"}'
        result = self._run(content, "999.88.7", "999.88.8")
        self.assertEqual(result.returncode, 0)
        self.assertIn('"999.88.8"', result.stdout)
        status = json.loads(result.stderr)
        self.assertEqual(status["status"], "ok")

    def test_not_found_cli(self):
        content = '{"version": "1.0.0"}'
        result = self._run(content, "999.88.7", "999.88.8")
        self.assertEqual(result.returncode, 1)

    def test_optional_pattern_not_found_cli(self):
        """--optional でパターン未マッチ時に exit 0 + status: skipped"""
        content = '| **anvil** | 888.77.6 | desc |'
        result = self._run(content, "999.88.7", "999.88.8", "--filter", "**forge**", "--optional")
        self.assertEqual(result.returncode, 0)
        # stdout は空（Write すべき内容がない）
        self.assertEqual(result.stdout, "")
        status = json.loads(result.stderr)
        self.assertEqual(status["status"], "skipped")

    def test_optional_not_set_pattern_not_found_cli(self):
        """--optional なしでパターン未マッチ時は従来通り exit 1"""
        content = '| **anvil** | 888.77.6 | desc |'
        result = self._run(content, "999.88.7", "999.88.8", "--filter", "**forge**")
        self.assertEqual(result.returncode, 1)

    def test_file_not_found_cli(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / 'update_version_files.py'),
             '/nonexistent.json', '999.88.7', '999.88.8'],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)

    def test_version_path_cli(self):
        content = '{"version": "999.88.7"}'
        result = self._run(content, "999.88.7", "999.88.8", "--version-path", "version")
        self.assertEqual(result.returncode, 0)
        self.assertIn('"999.88.8"', result.stdout)


if __name__ == '__main__':
    unittest.main()
