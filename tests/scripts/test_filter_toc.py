#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filter_toc.py のユニットテスト。

テスト対象:
- render_subset_yaml() 関数の単体テスト（TestRenderSubsetYaml）
- CLI 経由の統合テスト（TestFilterTocCli）
- エッジケース（TestFilterTocEdgeCases）

テスト方針:
- tmpdir に仮 ToC YAML を配置し、CLAUDE_PROJECT_DIR でルートを指定
- OPENAI_API_KEY 不要（filter_toc.py はローカル抽出のみ）
- 既存テスト test_grep_docs.py のパターンを踏襲
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
FILTER_TOC_SCRIPT = os.path.join(SCRIPTS_DIR, 'filter_toc.py')


SAMPLE_TOC_YAML = """\
# .claude/doc-advisor/toc/specs/specs_toc.yaml

metadata:
  name: Project Specification Document Search Index
  generated_at: 2026-04-28T00:00:00Z
  file_count: 3

docs:
  specs/design/auth_design.md:
    doc_type: design
    title: Auth Design
    purpose: Defines authentication architecture
    content_details:
      - OAuth2 flow
      - Token refresh
    applicable_tasks:
      - Auth implementation
      - Security review
    keywords:
      - OAuth2
      - JWT
      - authentication
  specs/requirements/login_req.md:
    doc_type: requirement
    title: Login Requirements
    purpose: Specifies login feature requirements
    content_details:
      - Login form fields
      - Error states
    applicable_tasks:
      - Login implementation
    keywords:
      - login
      - form
  specs/design/payment_design.md:
    doc_type: design
    title: Payment Design
    purpose: Defines payment processing architecture
    content_details:
      - Stripe integration
      - Webhook handling
    applicable_tasks:
      - Payment implementation
    keywords:
      - payment
      - Stripe
"""


class FilterTocTestBase(unittest.TestCase):
    """テスト用の共通セットアップ"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = self.tmpdir

        os.makedirs(os.path.join(self.project_root, '.git'))
        self._write_doc_structure()

        # ディレクトリ作成
        os.makedirs(os.path.join(self.project_root, 'specs'), exist_ok=True)
        os.makedirs(os.path.join(self.project_root, 'rules'), exist_ok=True)
        self.specs_toc_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'toc', 'specs'
        )
        self.rules_toc_dir = os.path.join(
            self.project_root, '.claude', 'doc-advisor', 'toc', 'rules'
        )
        os.makedirs(self.specs_toc_dir, exist_ok=True)
        os.makedirs(self.rules_toc_dir, exist_ok=True)

        # 環境変数の保存と設定
        self._original_env = {}
        for key in ('CLAUDE_PROJECT_DIR', 'CLAUDE_PLUGIN_ROOT'):
            self._original_env[key] = os.environ.get(key)
        os.environ['CLAUDE_PROJECT_DIR'] = self.project_root

        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        for key, val in self._original_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _write_doc_structure(self):
        content = """\
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/: spec
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""
        with open(os.path.join(self.project_root, '.doc_structure.yaml'), 'w') as f:
            f.write(content)

    def _write_specs_toc(self, content=SAMPLE_TOC_YAML):
        path = os.path.join(self.specs_toc_dir, 'specs_toc.yaml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def _run_filter_toc(self, *extra_args, category='specs'):
        cmd = [
            sys.executable, FILTER_TOC_SCRIPT,
            '--category', category,
        ] + list(extra_args)
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = self.project_root
        return subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.project_root, env=env
        )


# ===========================================================================
# render_subset_yaml() の単体テスト
# ===========================================================================

class TestRenderSubsetYaml(FilterTocTestBase):
    """render_subset_yaml() 関数の単体テスト"""

    def _get_renderer(self):
        from filter_toc import render_subset_yaml
        return render_subset_yaml

    def test_renders_filtered_entries(self):
        render = self._get_renderer()
        filtered = {
            'specs/design/auth_design.md': {
                'doc_type': 'design',
                'title': 'Auth Design',
                'purpose': 'Defines authentication architecture',
                'content_details': ['OAuth2 flow'],
                'applicable_tasks': ['Auth implementation'],
                'keywords': ['OAuth2'],
            },
        }
        output = render('specs', filtered, 3, ['specs/design/auth_design.md'])
        self.assertIn('specs/design/auth_design.md:', output)
        self.assertIn('doc_type: design', output)
        self.assertIn('Auth Design', output)
        self.assertIn('OAuth2 flow', output)
        self.assertIn('original_count: 3', output)
        self.assertIn('filtered_count: 1', output)
        self.assertIn('missing_count: 0', output)

    def test_lists_missing_paths(self):
        """ToC に存在しないパスは missing_paths として記録する"""
        render = self._get_renderer()
        filtered = {}
        output = render(
            'specs', filtered, 3,
            ['specs/missing/a.md', 'specs/missing/b.md'],
        )
        self.assertIn('missing_count: 2', output)
        self.assertIn('specs/missing/a.md', output)
        self.assertIn('specs/missing/b.md', output)

    def test_empty_filtered_emits_empty_docs(self):
        """フィルタ結果が空でも docs: {} で valid YAML"""
        render = self._get_renderer()
        output = render('specs', {}, 3, ['specs/missing.md'])
        self.assertIn('docs:', output)
        self.assertIn('{}', output)

    def test_metadata_includes_category(self):
        render = self._get_renderer()
        output = render('rules', {}, 0, [])
        self.assertIn('Filtered ToC Subset (rules)', output)

    def test_alphabetical_doc_order(self):
        """docs は path のアルファベット順で出力される"""
        render = self._get_renderer()
        filtered = {
            'specs/z.md': {'doc_type': 'design', 'title': 'Z'},
            'specs/a.md': {'doc_type': 'design', 'title': 'A'},
            'specs/m.md': {'doc_type': 'design', 'title': 'M'},
        }
        output = render('specs', filtered, 3, list(filtered.keys()))
        a_pos = output.index('specs/a.md')
        m_pos = output.index('specs/m.md')
        z_pos = output.index('specs/z.md')
        self.assertLess(a_pos, m_pos)
        self.assertLess(m_pos, z_pos)


# ===========================================================================
# CLI 統合テスト
# ===========================================================================

class TestFilterTocCli(FilterTocTestBase):
    """filter_toc.py の CLI 統合テスト"""

    def test_filters_existing_paths(self):
        """指定パスのエントリだけ抽出される"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths', 'specs/design/auth_design.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        out = result.stdout
        self.assertIn('specs/design/auth_design.md:', out)
        self.assertIn('Auth Design', out)
        # 他のエントリは含まれない
        self.assertNotIn('payment_design.md', out)
        self.assertNotIn('login_req.md', out)
        self.assertIn('filtered_count: 1', out)
        self.assertIn('original_count: 3', out)

    def test_multiple_paths(self):
        """複数パスが抽出される"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths',
            'specs/design/auth_design.md,specs/requirements/login_req.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        out = result.stdout
        self.assertIn('auth_design.md', out)
        self.assertIn('login_req.md', out)
        self.assertNotIn('payment_design.md', out)
        self.assertIn('filtered_count: 2', out)

    def test_missing_path_recorded(self):
        """ToC に存在しないパスは missing として記録される"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths', 'specs/design/auth_design.md,specs/nonexistent.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        out = result.stdout
        self.assertIn('filtered_count: 1', out)
        self.assertIn('missing_count: 1', out)
        self.assertIn('specs/nonexistent.md', out)

    def test_empty_paths_error(self):
        """--paths が空の場合はエラー"""
        self._write_specs_toc()

        result = self._run_filter_toc('--paths', '   ,  ')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'error')

    def test_missing_paths_argument(self):
        """--paths 未指定で argparse エラー"""
        self._write_specs_toc()

        result = self._run_filter_toc()

        self.assertNotEqual(result.returncode, 0)

    def test_toc_not_found(self):
        """ToC ファイルが存在しない場合はエラー"""
        # ToC を作成しない

        result = self._run_filter_toc('--paths', 'specs/x.md')

        self.assertEqual(result.returncode, 1)
        output = json.loads(result.stdout)
        self.assertEqual(output['status'], 'error')
        self.assertIn('not found', output['error'].lower())

    def test_duplicate_paths_deduplicated(self):
        """同一パスを複数指定しても 1 件として扱う"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths',
            'specs/design/auth_design.md,specs/design/auth_design.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn('filtered_count: 1', result.stdout)

    def test_whitespace_paths_trimmed(self):
        """パス前後の空白は除去される"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths',
            ' specs/design/auth_design.md , specs/requirements/login_req.md ',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn('filtered_count: 2', result.stdout)


# ===========================================================================
# エッジケース
# ===========================================================================

class TestFilterTocEdgeCases(FilterTocTestBase):
    """filter_toc.py のエッジケース"""

    def test_all_paths_missing(self):
        """すべてのパスが ToC に存在しない場合は filtered_count=0"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths', 'specs/x.md,specs/y.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        out = result.stdout
        self.assertIn('filtered_count: 0', out)
        self.assertIn('missing_count: 2', out)
        self.assertIn('docs:', out)

    def test_output_is_valid_yaml_structure(self):
        """出力が YAML として有効な階層構造になっている"""
        self._write_specs_toc()

        result = self._run_filter_toc(
            '--paths', 'specs/design/auth_design.md',
        )

        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        out = result.stdout
        # トップレベルキー
        self.assertRegex(out, r'(?m)^metadata:')
        self.assertRegex(out, r'(?m)^docs:')
        # docs エントリは 2 スペースインデント
        self.assertRegex(out, r'(?m)^  specs/design/auth_design\.md:')
        # フィールドは 4 スペースインデント
        self.assertRegex(out, r'(?m)^    doc_type: design')


if __name__ == '__main__':
    unittest.main()
