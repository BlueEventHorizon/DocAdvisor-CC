#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_run.py（フロントマター書き込みのラッパー）のテスト。

ラッパーの目的は「AI から fm_read / fm_write 間の配管を取り除く」ことであり、
検証すべきは **呼び出し側に決定論的な作業が残らないこと**である。

テスト対象:
- `plan` が信頼できる文書を targets から外し skipped へ回すこと（絞り込みを AI にさせない）
- `plan` が doc-advisor の標識を持つのに信頼できない文書を warnings に載せること
- `plan` が読めない文書を rejected_paths へ回し、他の判定は返すこと（partial）
- `plan` が原本を 1 バイトも変更しないこと
- `apply` が書き込み**後**の trust を返し、counts.trusted を出すこと
- `apply` が written に trusted が届かないとき status: partial になること
  （呼び出し側に件数を比較させないための契約）
- `apply` が値域違反を書き込みの前に弾き、ファイルが不変であること（Phase 0 との連動）
- `--entries-file` の不正（不在・壊れた JSON・不正な構造）が error になること
- 対象 0 件でも targets / skipped が出ること（呼び出し側にフィールドの有無で分岐させない）

テスト方針:
- in-process import で関数を直接呼ぶものと、CLI 契約（単一 JSON / exit code）を
  subprocess で確認するものを分ける
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'plugins', 'doc-advisor', 'scripts')
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import MARKER, compute_body_hash, evaluate
from fm_read import STATUS_ERROR, STATUS_OK, STATUS_PARTIAL
from fm_run import (
    REASON_ALREADY_TRUSTED,
    REASON_NO_FRONTMATTER,
    REASON_NOT_TRUSTWORTHY,
    expand_targets,
    run_apply,
    run_plan,
)

FM_RUN_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_run.py')

BODY = "# タイトル\n\n本文の内容。\n"

FULL_METADATA = {
    "title": "テスト文書",
    "purpose": "fm_run の検証に用いる文書であることを示す",
    "content_details": ["項目 A", "項目 B"],
    "applicable_tasks": ["タスク A"],
    "keywords": ["fm_run", "wrapper"],
}


def trusted_document(body=BODY):
    """信頼判定が真になるフロントマターを持つ文書。"""
    lines = ["---", f"type: {MARKER}"]
    for key, value in FULL_METADATA.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f'  - "{item}"')
        else:
            lines.append(f'{key}: "{value}"')
    lines.append(f"body_hash: {compute_body_hash(body)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def marked_but_broken_document(body=BODY):
    """doc-advisor の標識を持つが内容が不完全（§5.3 の warning 対象）。"""
    return (
        "---\n"
        f"type: {MARKER}\n"
        "title: 標識はあるが不完全\n"
        "---\n"
    ) + body


class FmRunTestBase(unittest.TestCase):
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

    def _read(self, path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def _run_cli(self, *args):
        proc = subprocess.run(
            [sys.executable, FM_RUN_SCRIPT] + list(args),
            capture_output=True, text=True, cwd=self.tmpdir,
        )
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(
            len(out.split("\n")), 1,
            f"stdout must be a single JSON line: {out!r}",
        )
        return proc, json.loads(out)


class TestPlanResolvesTargets(FmRunTestBase):
    """plan が書き込むべき対象だけを返すこと"""

    def test_trusted_documents_go_to_skipped(self):
        trusted = self._write('a.md', trusted_document())
        plain = self._write('b.md', BODY)

        status, targets, skipped, rejected, warnings = run_plan([trusted, plain])

        self.assertEqual(status, STATUS_OK)
        self.assertEqual([t['path'] for t in targets], [plain])
        self.assertEqual([s['path'] for s in skipped], [trusted])
        self.assertEqual(skipped[0]['reason'], REASON_ALREADY_TRUSTED)
        self.assertEqual(targets[0]['reason'], REASON_NO_FRONTMATTER)
        self.assertEqual(warnings, [])

    def test_untrustworthy_frontmatter_is_a_target_with_its_reason(self):
        broken = self._write('a.md', marked_but_broken_document())

        _status, targets, _skipped, _rejected, warnings = run_plan([broken])

        self.assertEqual(targets[0]['reason'], REASON_NOT_TRUSTWORTHY)
        self.assertTrue(targets[0]['has_frontmatter'])
        self.assertTrue(targets[0]['has_marker'])
        self.assertTrue(
            any('not trustworthy' in w for w in warnings),
            'doc-advisor の標識を持つのに信頼できない文書は warning になる（§5.3）',
        )

    def test_document_without_marker_yields_no_warning(self):
        """フロントマターを持たない文書は正常な対象外であり warning を出さない。"""
        plain = self._write('a.md', BODY)

        _status, targets, _skipped, _rejected, warnings = run_plan([plain])

        self.assertEqual(len(targets), 1)
        self.assertEqual(warnings, [])

    def test_unreadable_path_becomes_partial_without_dropping_others(self):
        missing = os.path.join(self.tmpdir, 'missing.md')
        plain = self._write('a.md', BODY)

        status, targets, _skipped, rejected, _warnings = run_plan([missing, plain])

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual([r['path'] for r in rejected], [missing])
        self.assertEqual([t['path'] for t in targets], [plain],
                         '読めない 1 件で他の判定を落とさない')

    def test_plan_never_modifies_the_sources(self):
        paths = {
            self._write('a.md', BODY): None,
            self._write('b.md', trusted_document()): None,
            self._write('c.md', marked_but_broken_document()): None,
        }
        for path in paths:
            paths[path] = self._read(path)

        run_plan(list(paths))

        for path, before in paths.items():
            self.assertEqual(self._read(path), before, f'plan が原本を変更した: {path}')


class TestApplyVerifiesWhatItWrote(FmRunTestBase):
    """apply が書き込み後の信頼判定まで行うこと"""

    def test_full_metadata_becomes_trusted(self):
        path = self._write('a.md', BODY)

        status, results, counts = run_apply([(path, dict(FULL_METADATA))])

        self.assertEqual(status, STATUS_OK)
        self.assertEqual(counts['written'], 1)
        self.assertEqual(counts['trusted'], 1)
        self.assertTrue(results[0]['trust'])
        self.assertTrue(evaluate(self._read(path)).trust)

    def test_partial_metadata_is_written_but_not_trusted(self):
        """部分指定で 5 フィールドが揃わない場合。

        値域違反は Phase 0 で弾かれるが、欠落は部分更新を許すため書き込みは成功する。
        書けたのに信頼されないことを **ラッパーが自分で検出して partial にする**。
        呼び出し側に fm_read を再度呼ばせて件数を比較させないための契約である。
        """
        path = self._write('a.md', BODY)

        status, results, counts = run_apply([(path, {'title': 'タイトルのみ'})])

        self.assertEqual(counts['written'], 1)
        self.assertEqual(counts['trusted'], 0)
        self.assertEqual(status, STATUS_PARTIAL,
                         'written に trusted が届かなければ partial')
        self.assertFalse(results[0]['trust'])
        self.assertTrue(
            any(v['code'] == 'FIELD_MISSING' for v in results[0]['violations']),
            '何が足りないかが violations で分かる',
        )

    def test_mixed_batch_reports_per_entry_trust(self):
        full = self._write('a.md', BODY)
        partial = self._write('b.md', BODY)

        status, results, counts = run_apply([
            (full, dict(FULL_METADATA)),
            (partial, {'title': 'タイトルのみ'}),
        ])

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual(counts['written'], 2)
        self.assertEqual(counts['trusted'], 1)
        self.assertEqual([item['trust'] for item in results], [True, False])

    def test_value_violation_is_rejected_before_writing(self):
        """Phase 0 の事前検証がラッパー経由でも効くこと。"""
        path = self._write('a.md', BODY)
        before = self._read(path)

        status, results, counts = run_apply([
            (path, dict(FULL_METADATA, purpose='x' * 201)),
        ])

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual(counts['written'], 0)
        self.assertEqual(counts['trusted'], 0)
        self.assertFalse(results[0]['ok'])
        self.assertFalse(results[0]['trust'])
        self.assertEqual(
            [v['code'] for v in results[0]['violations']], ['FIELD_TOO_LONG']
        )
        self.assertEqual(self._read(path), before, '1 バイトも書き換えられない')

    def test_failed_entry_is_not_counted_as_trusted(self):
        missing = os.path.join(self.tmpdir, 'missing.md')

        status, results, counts = run_apply([(missing, dict(FULL_METADATA))])

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual(counts['failed'], 1)
        self.assertEqual(counts['trusted'], 0)
        self.assertFalse(results[0]['trust'])


class TestExpandTargets(FmRunTestBase):
    """ディレクトリ展開を expand_dirs へ委ねること"""

    def test_paths_only_needs_no_expansion(self):
        paths, rejected_dirs, warnings = expand_targets(paths=['docs/a.md'])

        self.assertEqual(paths, ['docs/a.md'])
        self.assertEqual(rejected_dirs, [])
        self.assertEqual(warnings, [])

    def test_no_target_yields_an_empty_list(self):
        paths, _rejected, _warnings = expand_targets()

        self.assertEqual(paths, [])


class TestCliContract(FmRunTestBase):
    """CLI 契約（単一 JSON / exit code / 引数の不正）"""

    def test_plan_emits_targets_and_skipped_even_when_empty(self):
        os.makedirs(os.path.join(self.tmpdir, 'docs'))

        proc, payload = self._run_cli('plan', '--dirs', 'docs/')

        self.assertEqual(proc.returncode, 0)
        self.assertIn('targets', payload)
        self.assertIn('skipped', payload)
        self.assertEqual(payload['counts']['total'], 0)

    def test_plan_over_a_directory(self):
        self._write('docs/a.md', BODY)
        self._write('docs/b.md', trusted_document())

        _proc, payload = self._run_cli('plan', '--dirs', 'docs/')

        self.assertEqual(payload['counts']['targets'], 1)
        self.assertEqual(payload['counts']['skipped'], 1)

    def test_missing_entries_file_is_an_error(self):
        proc, payload = self._run_cli('apply', '--entries-file', 'nope.json')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], 'NOT_FOUND')

    def test_malformed_entries_file_is_an_error(self):
        self._write('entries.json', '{not json')

        proc, payload = self._run_cli('apply', '--entries-file', 'entries.json')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['error_code'], 'INVALID_PATH')

    def test_entries_with_unknown_key_is_an_error(self):
        """構造の検証を fm_write.parse_entries_json に委ねていること。"""
        self._write('entries.json', json.dumps([
            {'path': 'a.md', 'metadata': {}, 'unexpected': 1}
        ]))

        proc, payload = self._run_cli('apply', '--entries-file', 'entries.json')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['error_code'], 'INVALID_PATH')

    def test_format_command_without_placeholder_is_an_error(self):
        self._write('entries.json', json.dumps([{'path': 'a.md', 'metadata': {}}]))

        proc, payload = self._run_cli(
            'apply', '--entries-file', 'entries.json',
            '--format-command', 'echo no placeholder',
        )

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_unknown_subcommand_is_json(self):
        proc, payload = self._run_cli('frobnicate')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_apply_via_cli_reports_trusted(self):
        self._write('a.md', BODY)
        self._write('entries.json', json.dumps([
            {'path': 'a.md', 'metadata': FULL_METADATA}
        ]))

        proc, payload = self._run_cli('apply', '--entries-file', 'entries.json')

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['counts']['trusted'], 1)
        self.assertTrue(payload['results'][0]['trust'])


if __name__ == '__main__':
    unittest.main()
