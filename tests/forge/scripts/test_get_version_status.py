#!/usr/bin/env python3
"""
get_version_status.py のテスト

YAML パーサー、バージョン取得、バンプ分類をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.scripts.test_get_version_status -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugins" / "forge" / "scripts"))

from get_version_status import (
    _parse_version_config_yaml,
    get_version_from_json_content,
    resolve_version_path,
    classify_bump,
)

_TEST_TEMP_BASE = Path(__file__).parent / ".temp"


class TestParseVersionConfigYaml(unittest.TestCase):
    """_parse_version_config_yaml のテスト"""

    def test_parse_single_target(self):
        """単一 target を正しくパースできる"""
        yaml = """
targets:
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version
"""
        result = _parse_version_config_yaml(yaml)
        self.assertEqual(len(result["targets"]), 1)
        target = result["targets"][0]
        self.assertEqual(target["name"], "forge")
        self.assertEqual(target["version_file"], "plugins/forge/.claude-plugin/plugin.json")
        self.assertEqual(target["version_path"], "version")

    def test_parse_multiple_targets(self):
        """複数 target を正しくパースできる"""
        yaml = """
targets:
  - name: marketplace
    version_file: .claude-plugin/marketplace.json
    version_path: metadata.version
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version
  - name: anvil
    version_file: plugins/anvil/.claude-plugin/plugin.json
    version_path: version
"""
        result = _parse_version_config_yaml(yaml)
        names = [t["name"] for t in result["targets"]]
        self.assertEqual(names, ["marketplace", "forge", "anvil"])

    def test_parse_sync_files(self):
        """sync_files を正しくパースできる"""
        yaml = """
targets:
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version
    sync_files:
      - path: README.md
        filter: '| **forge**'
      - path: README_en.md
        filter: '| **forge**'
        optional: true
"""
        # 上記 YAML の sync_files 内 indent 確認:
        # sync_files: (indent 4), - path: (indent 6), filter: (indent 8)
        result = _parse_version_config_yaml(yaml)
        target = result["targets"][0]
        self.assertEqual(len(target["sync_files"]), 2)
        self.assertEqual(target["sync_files"][0]["path"], "README.md")
        self.assertEqual(target["sync_files"][1]["path"], "README_en.md")
        self.assertEqual(target["sync_files"][1]["optional"], "true")

    def test_parse_changelog_section(self):
        """changelog セクションを正しくパースできる"""
        yaml = """
targets:
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version

changelog:
  file: CHANGELOG.md
  format: keep-a-changelog
"""
        result = _parse_version_config_yaml(yaml)
        self.assertEqual(result["changelog"]["file"], "CHANGELOG.md")
        self.assertEqual(result["changelog"]["format"], "keep-a-changelog")

    def test_parse_git_section(self):
        """git セクションを正しくパースできる"""
        yaml = """
targets:
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version

git:
  auto_commit: true
  auto_tag: false
"""
        result = _parse_version_config_yaml(yaml)
        self.assertEqual(result["git"]["auto_commit"], "true")
        self.assertEqual(result["git"]["auto_tag"], "false")

    def test_parse_skips_comments(self):
        """コメント行をスキップする"""
        yaml = """
# version_config_version: 1.0

targets:
  # これはコメント
  - name: forge
    version_file: plugins/forge/.claude-plugin/plugin.json
    version_path: version
"""
        result = _parse_version_config_yaml(yaml)
        self.assertEqual(len(result["targets"]), 1)
        self.assertEqual(result["targets"][0]["name"], "forge")

    def test_parse_empty_yaml(self):
        """空の YAML で空の結果を返す"""
        result = _parse_version_config_yaml("")
        self.assertEqual(result["targets"], [])
        self.assertEqual(result["changelog"], {})
        self.assertEqual(result["git"], {})

    def test_parse_target_without_version_path(self):
        """version_path がない target も name/version_file を取得できる"""
        yaml = """
targets:
  - name: sample
    version_file: plugins/sample/.claude-plugin/plugin.json
"""
        result = _parse_version_config_yaml(yaml)
        target = result["targets"][0]
        self.assertEqual(target["name"], "sample")
        self.assertNotIn("version_path", target)


class TestResolveVersionPath(unittest.TestCase):
    """resolve_version_path のテスト"""

    def test_simple_key(self):
        """単純なキーでバージョンを取得できる"""
        data = {"version": "1.2.3"}
        self.assertEqual(resolve_version_path(data, "version"), "1.2.3")

    def test_nested_key(self):
        """ドット区切りのネストしたキーでバージョンを取得できる"""
        data = {"metadata": {"version": "0.1.5"}}
        self.assertEqual(resolve_version_path(data, "metadata.version"), "0.1.5")

    def test_missing_key(self):
        """存在しないキーで None を返す"""
        data = {"version": "1.0.0"}
        self.assertIsNone(resolve_version_path(data, "metadata.version"))

    def test_missing_nested_key(self):
        """中間キーが存在しない場合に None を返す"""
        data = {}
        self.assertIsNone(resolve_version_path(data, "a.b.c"))


class TestGetVersionFromJsonContent(unittest.TestCase):
    """get_version_from_json_content のテスト"""

    def test_simple_version(self):
        """単純な JSON からバージョンを取得できる"""
        content = json.dumps({"version": "0.0.29"})
        result = get_version_from_json_content(content, "version")
        self.assertEqual(result, "0.0.29")

    def test_nested_version(self):
        """ネストした JSON からバージョンを取得できる"""
        content = json.dumps({"metadata": {"version": "0.1.1"}})
        result = get_version_from_json_content(content, "metadata.version")
        self.assertEqual(result, "0.1.1")

    def test_invalid_json(self):
        """不正な JSON で None を返す"""
        result = get_version_from_json_content("not json", "version")
        self.assertIsNone(result)

    def test_empty_string(self):
        """空文字列で None を返す"""
        result = get_version_from_json_content("", "version")
        self.assertIsNone(result)


class TestClassifyBump(unittest.TestCase):
    """classify_bump のテスト"""

    def test_same_version(self):
        self.assertEqual(classify_bump("1.0.0", "1.0.0"), "same")

    def test_patch_bump(self):
        self.assertEqual(classify_bump("0.0.1", "0.0.2"), "patch")

    def test_minor_bump(self):
        self.assertEqual(classify_bump("0.0.9", "0.1.0"), "minor")

    def test_major_bump(self):
        self.assertEqual(classify_bump("0.9.9", "1.0.0"), "major")

    def test_downgrade(self):
        self.assertEqual(classify_bump("1.0.0", "0.9.9"), "downgrade")

    def test_none_base(self):
        """base が None のとき unknown を返す"""
        self.assertEqual(classify_bump(None, "1.0.0"), "unknown")

    def test_none_current(self):
        """current が None のとき unknown を返す"""
        self.assertEqual(classify_bump("1.0.0", None), "unknown")

    def test_invalid_semver(self):
        """semver 形式でないとき unknown を返す"""
        self.assertEqual(classify_bump("v1.0.0", "v1.0.1"), "unknown")

    def test_minor_bump_with_patch_reset(self):
        """minor バンプで patch がリセットされたバージョン"""
        self.assertEqual(classify_bump("0.1.4", "0.1.5"), "patch")
        self.assertEqual(classify_bump("0.1.4", "0.2.0"), "minor")


def _run_main_with_mocks(project_root, mock_git_show, mock_branch="feature/test"):
    """main() をモックありで実行し、JSON 出力を返すヘルパー"""
    import io
    import sys
    from contextlib import redirect_stdout
    from get_version_status import main as _main

    buf = io.StringIO()
    saved_argv = sys.argv
    try:
        sys.argv = ["get_version_status.py"]
        with patch("get_version_status.find_project_root", return_value=project_root), \
             patch("get_version_status.get_file_content_from_branch", side_effect=mock_git_show), \
             patch("get_version_status.get_current_branch", return_value=mock_branch):
            with redirect_stdout(buf):
                _main()
    finally:
        sys.argv = saved_argv

    return json.loads(buf.getvalue())


class TestMainIntegration(unittest.TestCase):
    """main() の統合テスト（ファイルシステム + git show をモック）"""

    def setUp(self):
        _TEST_TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.tmpdir = Path(tempfile.mkdtemp(dir=_TEST_TEMP_BASE))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_plugin_json(self, version: str, path: str) -> Path:
        """テスト用 plugin.json を作成する"""
        full_path = self.tmpdir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(json.dumps({"version": version}), encoding="utf-8")
        return full_path

    def _write_config(self, content: str):
        """テスト用 .version-config.yaml を書き込む"""
        (self.tmpdir / ".version-config.yaml").write_text(content, encoding="utf-8")

    def test_changed_target_detected(self):
        """main branch より current が上がっている target を検出できる"""
        self._make_plugin_json("0.0.2", "plugins/forge/.claude-plugin/plugin.json")
        self._write_config(
            "targets:\n"
            "  - name: forge\n"
            "    version_file: plugins/forge/.claude-plugin/plugin.json\n"
            "    version_path: version\n"
        )

        output = _run_main_with_mocks(
            self.tmpdir,
            lambda branch, path: json.dumps({"version": "0.0.1"}),
        )

        self.assertEqual(output["status"], "ok")
        self.assertEqual(len(output["targets"]), 1)
        target = output["targets"][0]
        self.assertEqual(target["name"], "forge")
        self.assertEqual(target["base"], "0.0.1")
        self.assertEqual(target["current"], "0.0.2")
        self.assertTrue(target["changed"])
        self.assertEqual(target["bump_type"], "patch")

    def test_unchanged_target(self):
        """main と同じバージョンの target は changed=False"""
        self._make_plugin_json("0.0.1", "plugins/forge/.claude-plugin/plugin.json")
        self._write_config(
            "targets:\n"
            "  - name: forge\n"
            "    version_file: plugins/forge/.claude-plugin/plugin.json\n"
            "    version_path: version\n"
        )

        output = _run_main_with_mocks(
            self.tmpdir,
            lambda branch, path: json.dumps({"version": "0.0.1"}),
        )

        target = output["targets"][0]
        self.assertFalse(target["changed"])
        self.assertNotIn("bump_type", target)

    def test_new_target_not_on_base(self):
        """base ブランチに存在しない target に note が付く"""
        self._make_plugin_json("0.0.1", "plugins/doc-advisor/.claude-plugin/plugin.json")
        self._write_config(
            "targets:\n"
            "  - name: doc-advisor\n"
            "    version_file: plugins/doc-advisor/.claude-plugin/plugin.json\n"
            "    version_path: version\n"
        )

        # base ブランチにはファイルが存在しない
        output = _run_main_with_mocks(
            self.tmpdir,
            lambda branch, path: None,
        )

        target = output["targets"][0]
        self.assertFalse(target["changed"])
        self.assertIn("note", target)

    def test_marketplace_needs_bump(self):
        """プラグインが更新されているが marketplace が変わっていない場合に marketplace_needs_bump=true"""
        (self.tmpdir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (self.tmpdir / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"metadata": {"version": "0.1.0"}}), encoding="utf-8"
        )
        self._make_plugin_json("0.0.2", "plugins/forge/.claude-plugin/plugin.json")
        self._write_config(
            "targets:\n"
            "  - name: marketplace\n"
            "    version_file: .claude-plugin/marketplace.json\n"
            "    version_path: metadata.version\n"
            "  - name: forge\n"
            "    version_file: plugins/forge/.claude-plugin/plugin.json\n"
            "    version_path: version\n"
        )

        def mock_git_show(branch, path):
            if "marketplace" in path:
                return json.dumps({"metadata": {"version": "0.1.0"}})
            return json.dumps({"version": "0.0.1"})

        output = _run_main_with_mocks(self.tmpdir, mock_git_show)

        self.assertFalse(output["summary"]["marketplace_bumped"])
        self.assertTrue(output["summary"]["marketplace_needs_bump"])

    def test_marketplace_bumped_no_need(self):
        """marketplace も更新されている場合に marketplace_needs_bump=false"""
        (self.tmpdir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (self.tmpdir / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"metadata": {"version": "0.1.1"}}), encoding="utf-8"
        )
        self._make_plugin_json("0.0.2", "plugins/forge/.claude-plugin/plugin.json")
        self._write_config(
            "targets:\n"
            "  - name: marketplace\n"
            "    version_file: .claude-plugin/marketplace.json\n"
            "    version_path: metadata.version\n"
            "  - name: forge\n"
            "    version_file: plugins/forge/.claude-plugin/plugin.json\n"
            "    version_path: version\n"
        )

        def mock_git_show(branch, path):
            if "marketplace" in path:
                return json.dumps({"metadata": {"version": "0.1.0"}})
            return json.dumps({"version": "0.0.1"})

        output = _run_main_with_mocks(self.tmpdir, mock_git_show)

        self.assertTrue(output["summary"]["marketplace_bumped"])
        self.assertFalse(output["summary"]["marketplace_needs_bump"])


if __name__ == "__main__":
    unittest.main()
