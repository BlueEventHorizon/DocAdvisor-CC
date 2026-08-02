#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_read.py のユニットテスト（DES-008 §5.3 / §6.2、DES-005 §8.1 / §9.2）。

テスト対象:
- 信頼判定の分岐が JSON に反映されること（trust 真 / フロントマター無し（warning なし）/
  マーカー有りでスキーマ違反（warning あり））
- 複数パスを渡したとき results が入力順に並ぶこと
- 読み取れないパスを混ぜたとき status: partial となり他の判定は返ること
- 対象 0 件が error にならないこと（DES-005 §9.2）
- argparse エラー・--paths-json の形式不正が JSON として出力されること（subprocess 経路）
- status / error_code の値域が自前の定数集合に含まれること

テスト方針:
- 判定と JSON 組み立ては in-process import（emit_json に stream を渡して検証する）
- CLI 契約（引数エラー・exit code・stdout 単一 JSON）は subprocess で確認する
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# テスト対象モジュールの import
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'plugins', 'doc-advisor', 'scripts')
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import MARKER, Violation, compute_body_hash
from fm_read import (
    ERROR_CODES,
    STATUSES,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PARTIAL,
    ErrorCode,
    build_report,
    emit_json,
    evaluate_path,
    main,
    parse_paths_json,
)

FM_READ_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_read.py')

BODY = "# Title\n\nSome body text.\n"


def trusted_document(body=BODY):
    """信頼判定が真になる文書を組み立てる。"""
    return (
        "---\n"
        f"type: {MARKER}\n"
        "title: Foo Doc\n"
        "purpose: Foo の説明\n"
        "content_details:\n"
        "  - 項目 A\n"
        "applicable_tasks:\n"
        "  - タスク A\n"
        "keywords:\n"
        "  - Foo\n"
        f"body_hash: {compute_body_hash(body)}\n"
        "---\n"
    ) + body


def violating_document(body=BODY):
    """マーカーは持つがスキーマに適合しない文書を組み立てる（§5.3 の warning 対象）。"""
    return (
        "---\n"
        f"type: {MARKER}\n"
        "title: Bar Doc\n"
        "purpose: Bar の説明\n"
        "content_details: これは配列ではない\n"
        "applicable_tasks:\n"
        "  - タスク B\n"
        "keywords:\n"
        "  - Bar\n"
        f"body_hash: {compute_body_hash(body)}\n"
        "---\n"
    ) + body


class FmReadTestBase(unittest.TestCase):
    """一時ディレクトリに文書を配置する共通セットアップ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, text):
        path = os.path.join(self.tmpdir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def _run_main(self, paths):
        """main を in-process で実行し (exit_code, payload) を返す。"""
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(['--paths-json', json.dumps(paths)])
        return code, json.loads(stream.getvalue().strip())


class TestTrustBranches(FmReadTestBase):
    """信頼判定の分岐が JSON に反映されること（DES-008 §5.1 / §5.3）"""

    def test_trusted_document(self):
        path = self._write('trusted.md', trusted_document())
        status, results, rejected, counts, warnings = build_report([path])

        self.assertEqual(status, STATUS_OK)
        self.assertEqual(rejected, [])
        self.assertEqual(warnings, [])
        self.assertTrue(results[0]['trust'])
        self.assertTrue(results[0]['has_marker'])
        self.assertFalse(results[0]['warn'])
        self.assertEqual(results[0]['violations'], [])
        self.assertEqual(counts['trusted'], 1)
        self.assertEqual(counts['untrusted'], 0)

    def test_no_frontmatter_is_not_warned(self):
        """フロントマター無しは正常な対象外であり warning を出さない（§5.3）"""
        path = self._write('plain.md', BODY)
        status, results, rejected, counts, warnings = build_report([path])

        self.assertEqual(status, STATUS_OK)
        self.assertFalse(results[0]['trust'])
        self.assertFalse(results[0]['has_frontmatter'])
        self.assertFalse(results[0]['has_marker'])
        self.assertFalse(results[0]['warn'])
        self.assertEqual(warnings, [])
        self.assertEqual(counts['untrusted'], 1)
        self.assertEqual(counts['warned'], 0)

    def test_marker_with_schema_violation_is_warned(self):
        """マーカー有り + スキーマ違反は warning を出す（§5.3）"""
        path = self._write('violating.md', violating_document())
        status, results, rejected, counts, warnings = build_report([path])

        self.assertEqual(status, STATUS_OK)
        self.assertFalse(results[0]['trust'])
        self.assertTrue(results[0]['has_marker'])
        self.assertTrue(results[0]['warn'])
        self.assertEqual(len(warnings), 1)
        self.assertIn(path, warnings[0])
        self.assertIn(Violation.FIELD_TYPE_MISMATCH, warnings[0])
        self.assertEqual(counts['warned'], 1)

    def test_body_hash_mismatch_is_warned(self):
        """本文だけが変わった文書はマーカー有りのため warning 対象（§5.3）"""
        path = self._write('stale.md', trusted_document() + "\nAdded paragraph.\n")
        status, results, rejected, counts, warnings = build_report([path])

        self.assertFalse(results[0]['trust'])
        self.assertTrue(results[0]['warn'])
        codes = [v['code'] for v in results[0]['violations']]
        self.assertIn(Violation.BODY_HASH_MISMATCH, codes)
        self.assertEqual(len(warnings), 1)

    def test_non_doc_advisor_frontmatter_is_not_warned(self):
        """別ツールのフロントマターのみを持つ文書は正常な対象外（§4.1）"""
        path = self._write('skill.md', "---\nname: foo\ndescription: bar\n---\n" + BODY)
        status, results, rejected, counts, warnings = build_report([path])

        self.assertFalse(results[0]['trust'])
        self.assertTrue(results[0]['has_frontmatter'])
        self.assertFalse(results[0]['has_marker'])
        self.assertFalse(results[0]['warn'])
        self.assertEqual(warnings, [])


class TestMultiplePaths(FmReadTestBase):
    """複数ファイル判定（入力順・partial 写像）"""

    def test_results_follow_input_order(self):
        first = self._write('a.md', trusted_document())
        second = self._write('b.md', BODY)
        third = self._write('c.md', violating_document())

        for order in ([first, second, third], [third, first, second]):
            _, results, _, _, _ = build_report(order)
            self.assertEqual([item['path'] for item in results], order)

    def test_duplicate_paths_are_reported_once_per_entry(self):
        path = self._write('a.md', trusted_document())
        _, results, _, counts, _ = build_report([path, path])

        self.assertEqual([item['path'] for item in results], [path, path])
        self.assertEqual(counts['total'], 2)

    def test_unreadable_paths_map_to_partial(self):
        """1 件の読み取り失敗で全体を落とさず partial にする"""
        ok_path = self._write('a.md', trusted_document())
        missing = os.path.join(self.tmpdir, 'missing.md')
        directory = os.path.join(self.tmpdir, 'subdir')
        os.makedirs(directory)

        status, results, rejected, counts, warnings = build_report(
            [missing, ok_path, directory]
        )

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual([item['path'] for item in results], [missing, ok_path, directory])
        # 他のファイルの判定は返る
        self.assertTrue(results[1]['trust'])
        # 不在は NOT_FOUND、ディレクトリ等の読み取り失敗は READ_ERROR
        self.assertEqual(results[0]['error_code'], ErrorCode.NOT_FOUND)
        self.assertEqual(results[2]['error_code'], ErrorCode.READ_ERROR)
        self.assertEqual(
            rejected,
            [
                {'path': missing, 'reason': ErrorCode.NOT_FOUND},
                {'path': directory, 'reason': ErrorCode.READ_ERROR},
            ],
        )
        self.assertEqual(counts['unreadable'], 2)
        self.assertEqual(counts['trusted'], 1)
        # 読み取り失敗は文書の規約違反ではないため warning にしない
        self.assertEqual(warnings, [])

    def test_undecodable_file_maps_to_read_error(self):
        path = os.path.join(self.tmpdir, 'binary.md')
        with open(path, 'wb') as f:
            f.write(b"---\ntype: doc-advisor\n---\n\xff\xfe invalid utf-8\n")

        status, results, rejected, counts, _ = build_report([path])

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual(results[0]['error_code'], ErrorCode.READ_ERROR)
        self.assertFalse(results[0]['trust'])
        self.assertEqual(counts['unreadable'], 1)

    def test_empty_target_list_is_not_error(self):
        """対象 0 件は error にしない（DES-005 §9.2）"""
        status, results, rejected, counts, warnings = build_report([])

        self.assertEqual(status, STATUS_OK)
        self.assertEqual(results, [])
        self.assertEqual(rejected, [])
        self.assertEqual(warnings, [])
        self.assertEqual(counts['total'], 0)


class TestEvaluatePath(FmReadTestBase):
    """evaluate_path の戻り値の形（path / trust / error_code は常に含む）"""

    def test_always_contains_path_trust_and_error_code(self):
        ok_path = self._write('a.md', trusted_document())
        for item in (evaluate_path(ok_path), evaluate_path(ok_path + '.missing')):
            self.assertIn('path', item)
            self.assertIn('trust', item)
            self.assertIn('error_code', item)

    def test_relative_path_is_resolved_against_cwd(self):
        """相対パスは cwd 起点で解決する（project root 解決は行わない）"""
        self._write('docs/a.md', trusted_document())
        original_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        try:
            item = evaluate_path('docs/a.md')
        finally:
            os.chdir(original_cwd)

        self.assertIsNone(item['error_code'])
        self.assertTrue(item['trust'])


class TestJsonContract(FmReadTestBase):
    """JSON 出力契約（DES-005 §8.1 / §8.2）"""

    def test_status_and_error_code_are_always_present(self):
        stream = io.StringIO()
        emit_json(STATUS_OK, stream=stream)
        payload = json.loads(stream.getvalue().strip())

        self.assertEqual(payload['status'], STATUS_OK)
        self.assertIsNone(payload['error_code'])
        self.assertNotIn('results', payload)

    def test_emit_json_is_single_line(self):
        stream = io.StringIO()
        emit_json(
            STATUS_OK, counts={'total': 0}, results=[], warnings=[], stream=stream
        )
        self.assertEqual(len(stream.getvalue().strip().split('\n')), 1)

    def test_status_domain_is_fixed(self):
        self.assertEqual(STATUSES, frozenset({'ok', 'partial', 'error'}))

    def test_error_code_domain_is_fixed(self):
        self.assertEqual(
            ERROR_CODES,
            frozenset({'INVALID_PATH', 'UNSUPPORTED_ARG', 'NOT_FOUND', 'READ_ERROR'}),
        )
        self.assertEqual(ErrorCode.INVALID_PATH, 'INVALID_PATH')
        self.assertEqual(ErrorCode.UNSUPPORTED_ARG, 'UNSUPPORTED_ARG')
        self.assertEqual(ErrorCode.NOT_FOUND, 'NOT_FOUND')
        self.assertEqual(ErrorCode.READ_ERROR, 'READ_ERROR')

    def test_error_code_domain_is_within_the_shared_contract(self):
        """本 script の error_code が DES-005 §8.1 の共通列挙に含まれることを固定する。

        fm_read は toc_store を import しないため（DES-008 §6.1）値を独立定義するが、
        共通列挙の外の値を作ると、契約を検証する呼び出し側が正常な応答を不正値として
        扱う。ローカル集合の固定だけではこの逸脱を検出できないため、テストコード側で
        共通定数を読み込んで包含関係を固定する。
        """
        import toc_store

        self.assertTrue(
            ERROR_CODES <= toc_store.ERROR_CODES,
            'fm_read の error_code が DES-005 §8.1 の共通列挙から外れている: '
            f'{sorted(ERROR_CODES - toc_store.ERROR_CODES)}',
        )
        self.assertTrue(STATUSES <= toc_store.STATUSES)

    def test_emitted_values_are_within_the_defined_domains(self):
        path = self._write('a.md', trusted_document())
        missing = os.path.join(self.tmpdir, 'missing.md')

        for paths in ([], [path], [path, missing]):
            code, payload = self._run_main(paths)
            self.assertEqual(code, 0)
            self.assertIn(payload['status'], STATUSES)
            self.assertTrue(
                payload['error_code'] is None or payload['error_code'] in ERROR_CODES
            )
            for item in payload['results']:
                self.assertTrue(
                    item['error_code'] is None or item['error_code'] in ERROR_CODES
                )
            for item in payload['rejected_paths']:
                self.assertIn(item['reason'], ERROR_CODES)

    def test_main_returns_zero_for_partial(self):
        """partial は処理が続行され結果が得られている状態なので exit code 0"""
        path = self._write('a.md', trusted_document())
        missing = os.path.join(self.tmpdir, 'missing.md')

        code, payload = self._run_main([path, missing])
        self.assertEqual(code, 0)
        self.assertEqual(payload['status'], STATUS_PARTIAL)

    def test_paths_json_must_be_a_list_of_non_empty_strings(self):
        for raw in ('{}', '"docs/a.md"', '[1]', '["  "]', 'not-json'):
            with self.assertRaises(ValueError):
                parse_paths_json(raw)

    def test_paths_json_accepts_empty_array(self):
        self.assertEqual(parse_paths_json('[]'), [])


class TestCliContract(FmReadTestBase):
    """subprocess 経路の CLI 契約（stdout 単一 JSON / exit code）"""

    def _run_script(self, args):
        env = os.environ.copy()
        env['PYTHONPATH'] = FRONTMATTER_DIR
        return subprocess.run(
            [sys.executable, FM_READ_SCRIPT] + args,
            capture_output=True,
            text=True,
            cwd=self.tmpdir,
            env=env,
        )

    def _last_json_line(self, stdout):
        lines = [ln for ln in stdout.strip().split('\n') if ln.strip()]
        self.assertTrue(lines, 'stdout に JSON がありません')
        return json.loads(lines[-1])

    def test_unknown_argument_is_reported_as_json(self):
        result = self._run_script(['--paths-json', '[]', '--scan'])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_missing_required_argument_is_reported_as_json(self):
        result = self._run_script([])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_help_is_reported_as_json(self):
        """add_help=False のため --help も引数エラーとして JSON になる"""
        result = self._run_script(['--help'])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_malformed_paths_json_is_reported_as_json(self):
        result = self._run_script(['--paths-json', '{'])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.INVALID_PATH)

    def test_relative_paths_and_stdout_is_single_json(self):
        self._write('docs/a.md', trusted_document())
        self._write('docs/b.md', BODY)

        result = self._run_script(['--paths-json', '["docs/a.md", "docs/b.md"]'])
        lines = [ln for ln in result.stdout.strip().split('\n') if ln.strip()]
        payload = json.loads(lines[-1])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual([item['path'] for item in payload['results']],
                         ['docs/a.md', 'docs/b.md'])
        self.assertTrue(payload['results'][0]['trust'])
        self.assertFalse(payload['results'][1]['trust'])
        self.assertEqual(payload['warnings'], [])

    def test_does_not_modify_targets(self):
        """読み取り専用であること（原本を書き換えない / REQ-006 制約）"""
        text = trusted_document()
        path = self._write('docs/a.md', text)

        self._run_script(['--paths-json', '["docs/a.md"]'])

        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), text)


if __name__ == '__main__':
    unittest.main()
