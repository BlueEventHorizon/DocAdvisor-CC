#!/usr/bin/env python3
"""
resolve_doc_references.py のテスト

resolve_doc_structure.py に委譲後のパス解決・CLI 動作をテストする。
.doc_structure.yaml は config.yaml 互換フォーマットを使用。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.doc_structure.test_resolve_doc_references -v
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

# テスト共通ヘルパー
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from forge.helpers import _FsTestCase as _FsTestCaseBase

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'scripts' / 'doc_structure'))

from resolve_doc_references import (
    find_project_root,
    resolve_references,
)


# ---------------------------------------------------------------------------
# テスト基底クラス
# ---------------------------------------------------------------------------

class _FsTestCase(_FsTestCaseBase):
    """ファイルシステムを使うテストの基底クラス。"""

    def _write_doc_structure(self, content):
        """.doc_structure.yaml を tmpdir に作成する。"""
        return self._write_file('.doc_structure.yaml', content)


# =========================================================================
# 1. resolve_references のテスト
# =========================================================================

class TestResolveReferences(_FsTestCase):
    """resolve_references のテスト（統合テスト）。"""

    def test_rules_category(self):
        """--type rules で rules カテゴリのファイルが解決される。"""
        self._write_file('docs/rules/coding.md', '# コーディング規約')
        self._write_doc_structure("""\
rules:
  root_dirs:
    - docs/rules/

specs:
  root_dirs:
    - specs/
""")
        result = resolve_references('rules', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('rules', result)
        self.assertNotIn('specs', result)
        self.assertIn('docs/rules/coding.md', result['rules'])

    def test_specs_category(self):
        """--type specs で specs カテゴリのファイルが解決される。"""
        self._write_file('specs/requirements/req.md', '# 要件定義書')
        self._write_doc_structure("""\
specs:
  root_dirs:
    - specs/requirements/

rules:
  root_dirs:
    - docs/rules/
""")
        result = resolve_references('specs', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('specs', result)
        self.assertNotIn('rules', result)
        self.assertIn('specs/requirements/req.md', result['specs'])

    def test_all_category(self):
        """--type all で rules / specs 両方が解決される。"""
        self._write_file('docs/rules/coding.md', '# コーディング規約')
        self._write_file('specs/requirements/req.md', '# 要件定義書')
        self._write_doc_structure("""\
specs:
  root_dirs:
    - specs/requirements/

rules:
  root_dirs:
    - docs/rules/
""")
        result = resolve_references('all', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('rules', result)
        self.assertIn('specs', result)
        self.assertIn('docs/rules/coding.md', result['rules'])
        self.assertIn('specs/requirements/req.md', result['specs'])

    def test_missing_doc_structure(self):
        """.doc_structure.yaml が存在しない場合に status: error を返す。"""
        result = resolve_references('all', str(self.tmpdir))
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
        self.assertIn('.doc_structure.yaml', result['message'])

    def test_project_root_in_result(self):
        """結果に project_root が含まれる。"""
        self._write_doc_structure("# 空の設定\n")
        result = resolve_references('all', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['project_root'], str(self.tmpdir))

    def test_glob_pattern_with_exclude(self):
        """glob パターン + exclude の組み合わせが正しく動作する。"""
        self._write_file('specs/login/requirements/req.md', '# ログイン要件')
        self._write_file('specs/archived/requirements/old.md', '# 旧仕様')
        self._write_doc_structure("""\
specs:
  root_dirs:
    - specs/*/requirements/
  patterns:
    exclude:
      - archived
""")
        result = resolve_references('specs', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('specs/login/requirements/req.md', result['specs'])
        self.assertNotIn('specs/archived/requirements/old.md', result['specs'])

    def test_custom_doc_structure_path(self):
        """--doc-structure オプションで任意のパスを指定できる。"""
        self._write_file('docs/rules/rule.md', '# ルール')
        custom_yaml = self.tmpdir / 'custom_structure.yaml'
        custom_yaml.write_text("""\
rules:
  root_dirs:
    - docs/rules/
""", encoding='utf-8')

        result = resolve_references(
            'rules',
            str(self.tmpdir),
            doc_structure_path=str(custom_yaml),
        )
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('docs/rules/rule.md', result['rules'])

    def test_multiple_root_dirs(self):
        """複数の root_dirs が正しく処理される。"""
        self._write_file('docs/rules/coding.md', '# コーディング規約')
        self._write_file('extra/rules/naming.md', '# 命名規則')
        self._write_doc_structure("""\
rules:
  root_dirs:
    - docs/rules/
    - extra/rules/
""")
        result = resolve_references('rules', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertIn('docs/rules/coding.md', result['rules'])
        self.assertIn('extra/rules/naming.md', result['rules'])

    def test_empty_root_dirs(self):
        """root_dirs が空でもエラーにならない。"""
        self._write_doc_structure("""\
rules:
  root_dirs: []
""")
        result = resolve_references('rules', str(self.tmpdir))
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['rules'], [])


# =========================================================================
# 2. find_project_root のテスト
# =========================================================================

class TestFindProjectRoot(_FsTestCase):
    """find_project_root のテスト。"""

    def test_returns_explicit_path(self):
        """引数指定時はそのパスを resolve して返す。"""
        result = find_project_root(str(self.tmpdir))
        self.assertEqual(
            Path(result).resolve(),
            self.tmpdir.resolve(),
        )

    def test_returns_cwd_without_args(self):
        """引数なしの場合は cwd を返す。"""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(self.tmpdir))
            result = find_project_root()
            self.assertEqual(
                Path(result).resolve(),
                self.tmpdir.resolve(),
            )
        finally:
            os.chdir(original_cwd)


# =========================================================================
# 3. CLI 統合テスト
# =========================================================================

class TestCLI(_FsTestCase):
    """subprocess で CLI を呼び出すテスト。"""

    SCRIPT = str(Path(__file__).resolve().parents[3]
                 / 'plugins' / 'forge' / 'scripts' / 'doc_structure'
                 / 'resolve_doc_references.py')

    def _run(self, *cli_args):
        """スクリプトを subprocess で実行して結果を返す。"""
        return subprocess.run(
            [sys.executable, self.SCRIPT] + list(cli_args),
            capture_output=True,
            text=True,
            cwd=self.tmpdir,
        )

    def _make_project(self):
        """テスト用プロジェクト構造を作成する（config.yaml 互換フォーマット）。"""
        self._write_file('docs/rules/coding.md', '# コーディング規約')
        self._write_file('specs/requirements/req.md', '# 要件定義書')
        self._write_doc_structure("""\
specs:
  root_dirs:
    - specs/requirements/

rules:
  root_dirs:
    - docs/rules/
""")

    def test_type_rules(self):
        """--type rules で rules のみが返る。"""
        self._make_project()
        r = self._run('--type', 'rules', '--project-root', str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'resolved')
        self.assertIn('rules', data)
        self.assertNotIn('specs', data)
        self.assertIn('docs/rules/coding.md', data['rules'])

    def test_type_specs(self):
        """--type specs で specs のみが返る。"""
        self._make_project()
        r = self._run('--type', 'specs', '--project-root', str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'resolved')
        self.assertIn('specs', data)
        self.assertNotIn('rules', data)
        self.assertIn('specs/requirements/req.md', data['specs'])

    def test_type_all(self):
        """--type all で rules / specs 両方が返る。"""
        self._make_project()
        r = self._run('--type', 'all', '--project-root', str(self.tmpdir))
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'resolved')
        self.assertIn('rules', data)
        self.assertIn('specs', data)

    def test_error_no_doc_structure(self):
        """.doc_structure.yaml がない場合に status: error かつ exit code 1。"""
        r = self._run('--type', 'all', '--project-root', str(self.tmpdir))
        self.assertEqual(r.returncode, 1)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'error')
        self.assertIn('.doc_structure.yaml', data['message'])

    def test_custom_doc_structure_path(self):
        """--doc-structure で任意パスを指定できる。"""
        self._write_file('docs/rules/rule.md', '# ルール')
        custom_yaml = self.tmpdir / 'custom.yaml'
        custom_yaml.write_text("""\
rules:
  root_dirs:
    - docs/rules/
""", encoding='utf-8')

        r = self._run(
            '--type', 'rules',
            '--project-root', str(self.tmpdir),
            '--doc-structure', str(custom_yaml),
        )
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data['status'], 'resolved')
        self.assertIn('docs/rules/rule.md', data['rules'])

    def test_output_is_valid_json(self):
        """出力が常に有効な JSON である。"""
        r = self._run('--type', 'all', '--project-root', str(self.tmpdir))
        # エラー時でも JSON として解析できること
        try:
            json.loads(r.stdout)
        except json.JSONDecodeError:
            self.fail('出力が有効な JSON ではありません')

    def test_missing_type_arg(self):
        """--type を省略すると exit code != 0 になる。"""
        r = self._run('--project-root', str(self.tmpdir))
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
