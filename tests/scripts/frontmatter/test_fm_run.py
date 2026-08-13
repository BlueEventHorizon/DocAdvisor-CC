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

from merge_toc import write_toc_atomic
from toc_store import CHECKSUMS_FILENAME, TOC_FILENAME, resolve_store_dir
from toc_utils import calculate_file_hash, write_checksums_yaml

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
        # CLI は入口で cwd を project root へ揃える（DES-005 §4.2.1）。
        # CLAUDE_PROJECT_DIR が環境に残っていると tmpdir ではなくそちらへ移動する
        # ため、明示的に外して cwd=tmpdir を project root として扱わせる。
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        proc = subprocess.run(
            [sys.executable, FM_RUN_SCRIPT] + list(args),
            capture_output=True, text=True, cwd=self.tmpdir, env=env,
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


class TestCliAlwaysEmitsJson(FmRunTestBase):
    """**異常入力でも単一 JSON を返すこと**（DES-005 §8.1）。

    正常系だけを固定していると、境界処理を足したときに traceback で落ちる形が通る。
    実際に `filter_excluded` の新設で「絶対パス + --exclude」が traceback になる退行が
    起きた（`--exclude` なしなら rejected_paths で正常に返っていた）。**その形をここで
    落とす。**
    """

    ABNORMAL_ARGS = (
        ('plan', '--paths', '/etc/hosts.md', '--exclude', 'docs/draft'),
        ('plan', '--paths', '/etc/hosts.md'),
        ('plan', '--paths', '../outside.md', '--exclude', 'docs/draft'),
        ('plan', '--dirs', 'nosuchdir/', '--exclude', 'docs/draft'),
        ('plan', '--paths', 'docs/missing.md', '--exclude', 'docs/draft'),
    )

    def test_abnormal_paths_still_return_single_json(self):
        for args in self.ABNORMAL_ARGS:
            with self.subTest(args=args):
                proc, payload = self._run_cli(*args)
                self.assertIn('status', payload, 'status は error でも必須')
                self.assertIn('error_code', payload)
                self.assertNotIn(
                    'Traceback', proc.stderr,
                    'traceback で落ちる形は JSON 契約違反',
                )


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


class TestFromToc(FmRunTestBase):
    """ToC からの書き戻し（DES-008 §8.2）

    検証の主眼は「AI がメタデータを作らずに書き戻しが完結すること」である。
    `--entries-file` を一切渡さずに、ToC の値がそのまま原本へ入り、`body_hash` が
    打刻されて信頼判定が真になることを確認する。
    """

    KEY = 'rules'

    TOC_ENTRY = {
        'title': 'Indexed Document',
        'purpose': 'Serve as the transcription source for the write-back path',
        'content_details': ['detail A', 'detail B'],
        'applicable_tasks': ['task A'],
        'keywords': ['fm_run', 'writeback'],
    }

    def _run_cli(self, *args):
        """cwd = project root、CLAUDE_PROJECT_DIR は外して実行する。

        `--from-toc` は project root から store_dir を解決するため、実行環境に
        CLAUDE_PROJECT_DIR が残っていると別のプロジェクトの ToC を読みうる。
        """
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        proc = subprocess.run(
            [sys.executable, FM_RUN_SCRIPT] + list(args),
            capture_output=True, text=True, cwd=self.tmpdir, env=env,
        )
        out = proc.stdout.strip()
        self.assertTrue(out, f'stdout empty; stderr: {proc.stderr}')
        return proc, json.loads(out)

    def _prepare_toc(self, entries, checksum_paths=None):
        """toc.yaml と checksums を本番の writer で用意する。"""
        store_dir = resolve_store_dir(self.KEY, self.tmpdir)
        store_dir.mkdir(parents=True, exist_ok=True)
        write_toc_atomic(
            entries, store_dir / TOC_FILENAME,
            key=self.KEY, toc_rel=f'{store_dir.name}/{TOC_FILENAME}',
        )
        paths = entries if checksum_paths is None else checksum_paths
        checksums = {
            rel: calculate_file_hash(os.path.join(self.tmpdir, rel)) for rel in paths
        }
        write_checksums_yaml(checksums, store_dir / CHECKSUMS_FILENAME)

    def test_apply_counts_share_one_basis(self):
        """`total` が「対象として確定した件数」であり、内訳と基準が揃うこと。

        転記経路で `total` を entry 数（転記できた分）だけにすると、同じ counts に載る
        needs_ai / skipped / unreadable と基準が食い違い、SKILL の報告が「対象」から
        needs_ai の分を落とす。
        """
        self._write('docs/a.md', BODY)                    # 転記対象
        self._write('docs/b.md', trusted_document())      # 既に信頼 → skipped
        self._write('docs/c.md', BODY)                    # ToC に無い → needs_ai
        self._prepare_toc(
            {'docs/a.md': dict(self.TOC_ENTRY), 'docs/b.md': dict(self.TOC_ENTRY)},
            checksum_paths=['docs/a.md', 'docs/b.md'],
        )

        _proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY,
            '--paths', 'docs/a.md', 'docs/b.md', 'docs/c.md',
        )

        counts = payload['counts']
        self.assertEqual(counts['total'], 3, '対象として確定した件数')
        self.assertEqual(
            counts['written'] + counts['failed']
            + counts['needs_ai'] + counts['skipped'] + counts['unreadable'],
            counts['total'],
            '内訳の合計が total に一致する（基準が 1 つ）',
        )

    def test_plan_carries_the_toc_metadata(self):
        self._write('docs/a.md', BODY)
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)})

        _proc, payload = self._run_cli(
            'plan', '--from-toc', self.KEY, '--paths', 'docs/a.md')

        self.assertEqual(payload['counts']['from_toc'], 1)
        self.assertEqual(payload['counts']['needs_ai'], 0)
        target = payload['targets'][0]
        self.assertEqual(target['source'], 'toc')
        self.assertEqual(
            target['metadata'], self.TOC_ENTRY,
            'plan は ToC の値をそのまま提示する（AI に作らせない）',
        )
        self.assertIn('toc_path', payload)

    def test_plan_without_paths_covers_every_indexed_document(self):
        self._write('docs/a.md', BODY)
        self._write('docs/b.md', BODY)
        self._prepare_toc({
            'docs/a.md': dict(self.TOC_ENTRY),
            'docs/b.md': dict(self.TOC_ENTRY),
        })

        _proc, payload = self._run_cli('plan', '--from-toc', self.KEY)

        self.assertEqual(
            sorted(t['path'] for t in payload['targets']),
            ['docs/a.md', 'docs/b.md'],
            '対象の列挙は script が行う（ToC を AI に手読みさせない）',
        )

    def test_apply_writes_the_toc_values_without_any_authored_entries(self):
        path = self._write('docs/a.md', BODY)
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)})

        proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY, '--paths', 'docs/a.md')

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['counts']['trusted'], 1)

        result = evaluate(self._read(path))
        self.assertTrue(result.trust, '書き込み後の文書は信頼判定を通る')
        for field, value in self.TOC_ENTRY.items():
            self.assertEqual(
                result.metadata[field], value,
                f'{field} が ToC の値と一致しない（転記なのに内容が変わっている）',
            )
        self.assertEqual(
            result.metadata['body_hash'], compute_body_hash(BODY),
            'body_hash は転記後に script が打刻する',
        )
        self.assertIn(MARKER, result.metadata['type'])

    def test_apply_leaves_untranscribable_documents_to_the_ai(self):
        self._write('docs/a.md', BODY)
        self._write('docs/orphan.md', BODY)
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)},
                          checksum_paths=['docs/a.md'])

        _proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY,
            '--paths', 'docs/a.md', 'docs/orphan.md',
        )

        self.assertEqual(payload['counts']['written'], 1)
        self.assertEqual(payload['counts']['needs_ai'], 1)
        self.assertEqual(
            [item['path'] for item in payload['needs_ai']], ['docs/orphan.md'])
        self.assertEqual(payload['needs_ai'][0]['toc_reason'], 'not_in_toc')
        self.assertEqual(
            self._read(os.path.join(self.tmpdir, 'docs/orphan.md')), BODY,
            '転記できない文書は 1 バイトも変更しない',
        )

    def test_apply_does_not_transcribe_a_stale_entry(self):
        path = self._write('docs/a.md', BODY)
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)})
        edited = BODY + '\n索引後に本文を書き換えた。\n'
        self._write('docs/a.md', edited)

        _proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY, '--paths', 'docs/a.md')

        self.assertEqual(payload['counts']['written'], 0)
        self.assertEqual(payload['needs_ai'][0]['toc_reason'], 'body_changed')
        self.assertEqual(
            self._read(path), edited,
            '陳腐化した ToC の値で原本を書き換えてはならない',
        )

    def test_already_trusted_document_is_skipped(self):
        path = self._write('docs/a.md', trusted_document())
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)})
        before = self._read(path)

        _proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY, '--paths', 'docs/a.md')

        self.assertEqual(payload['counts']['written'], 0)
        self.assertEqual(payload['counts']['skipped'], 1)
        self.assertEqual(self._read(path), before)

    def test_missing_toc_is_an_error(self):
        self._write('docs/a.md', BODY)

        proc, payload = self._run_cli(
            'plan', '--from-toc', 'nosuchkey', '--paths', 'docs/a.md')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], 'TOC_NOT_FOUND')

    def test_empty_key_is_an_error(self):
        proc, payload = self._run_cli('plan', '--from-toc', '   ')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['error_code'], 'KEY_EMPTY')

    def test_from_toc_and_entries_are_mutually_exclusive(self):
        self._write('entries.json', json.dumps([]))

        proc, payload = self._run_cli(
            'apply', '--from-toc', self.KEY, '--entries-file', 'entries.json')

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_warnings_flag_index_anomalies_only(self):
        """正常な状態（未索引 / 本文の更新）は warning にしない。

        件数に比例して warning が並ぶと、エントリ不足のような本当の異常が埋もれる。
        分類は targets[].toc_reason で全件見えるため情報は失われない。
        """
        self._write('docs/a.md', BODY)
        self._write('docs/orphan.md', BODY)
        broken = dict(self.TOC_ENTRY)
        del broken['keywords']
        self._write('docs/broken.md', BODY)
        self._prepare_toc(
            {'docs/a.md': dict(self.TOC_ENTRY), 'docs/broken.md': broken},
            checksum_paths=['docs/a.md', 'docs/broken.md'],
        )

        _proc, payload = self._run_cli(
            'plan', '--from-toc', self.KEY,
            '--paths', 'docs/a.md', 'docs/orphan.md', 'docs/broken.md',
        )

        self.assertEqual(payload['counts']['needs_ai'], 2)
        self.assertEqual(
            [w for w in payload['warnings'] if 'orphan' in w], [],
            '未索引の文書は正常な状態であり warning にしない',
        )
        self.assertTrue(
            any('broken.md' in w and 'incomplete_entry' in w
                for w in payload['warnings']),
            'エントリが揃っていない ToC は索引側の異常として warning にする',
        )

    def test_plan_from_toc_never_modifies_the_sources(self):
        path = self._write('docs/a.md', BODY)
        self._prepare_toc({'docs/a.md': dict(self.TOC_ENTRY)})

        self._run_cli('plan', '--from-toc', self.KEY, '--paths', 'docs/a.md')

        self.assertEqual(self._read(path), BODY)


class TestApplyCountsShapeIsStable(FmRunTestBase):
    """apply の counts が `--from-toc` の有無で形を変えないこと。

    `_target_counts` の docstring が「フィールドの有無で呼び出し側に分岐させると、
    そこが新たな判断点になる」と述べており、plan はその通り常に同じ形を出す。apply
    だけが `--from-toc` のときにフィールドを足す形になっていた。
    """

    ALWAYS = ('total', 'written', 'failed', 'changed', 'formatted', 'trusted',
              'needs_ai', 'skipped', 'unreadable')

    def test_entries_json_path_has_every_field(self):
        self._write('a.md', BODY)
        entries = json.dumps([{"path": "a.md", "metadata": FULL_METADATA}])

        _proc, payload = self._run_cli('apply', '--entries-json', entries)

        for field in self.ALWAYS:
            with self.subTest(field=field):
                self.assertIn(field, payload['counts'])
        self.assertEqual(payload['counts']['needs_ai'], 0)
        self.assertEqual(payload['counts']['skipped'], 0)
        self.assertEqual(payload['counts']['unreadable'], 0)


class TestExcludeAppliesToTheResolvedSet(FmRunTestBase):
    """`--exclude` が対象の出どころによらず効くこと。

    以前はディレクトリ展開の内側でしか適用しておらず、`--dirs` を伴わない指定
    （明示 paths のみ / ToC 全件）では黙って無視されていた。とくに
    `--from-toc --exclude`（`--dirs` なし）は対象 0 件から全件フォールバックへ落ち、
    「除外して」と指定した原本まで書き換えた（指定と正反対の結果）。
    """

    def test_exclude_filters_explicit_paths(self):
        self._write('docs/a.md', BODY)
        self._write('docs/b.md', BODY)

        _proc, payload = self._run_cli(
            'plan', '--paths', 'docs/a.md', 'docs/b.md', '--exclude', 'docs/b.md'
        )

        self.assertEqual([t['path'] for t in payload['targets']], ['docs/a.md'])

    def test_exclude_filters_expanded_dirs(self):
        self._write('docs/a.md', BODY)
        self._write('docs/skip/b.md', BODY)

        _proc, payload = self._run_cli(
            'plan', '--dirs', 'docs/', '--exclude', 'docs/skip'
        )

        self.assertEqual([t['path'] for t in payload['targets']], ['docs/a.md'])

    def test_excluded_count_is_reported(self):
        self._write('docs/a.md', BODY)
        self._write('docs/b.md', BODY)

        _proc, payload = self._run_cli(
            'plan', '--paths', 'docs/a.md', 'docs/b.md', '--exclude', 'docs/b.md'
        )

        self.assertTrue(
            any('--exclude' in w for w in payload['warnings']),
            '黙って落とさず件数を報告する',
        )


class TestApplyOutputShapeIsStable(FmRunTestBase):
    """apply の出力が「フィールドの有無で呼び出し側に分岐させない」こと。

    `plan` は空配列でも常に出す。apply だけが値が無いときキーごと消える形だと、
    読み手に有無の分岐が残る（SKILL の観測表は warnings を無条件に挙げている）。
    """

    ALWAYS = ('warnings', 'needs_ai', 'skipped', 'rejected_dirs', 'rejected_paths')

    def test_entries_json_path_emits_every_key(self):
        self._write('a.md', BODY)
        entries = json.dumps([{"path": "a.md", "metadata": FULL_METADATA}])

        _proc, payload = self._run_cli('apply', '--entries-json', entries)

        for key in self.ALWAYS:
            with self.subTest(key=key):
                self.assertIn(key, payload, '値が無くてもキーは出す')
        self.assertEqual(payload['warnings'], [])


class TestApplyRejectsTargetArgsWithEntries(FmRunTestBase):
    """`--entries-*` と対象指定の併用を黙って無視しないこと。

    無視すると「対象を絞ったつもりの指定が効かないまま原本へ書き込む」ことになる。
    """

    def test_paths_with_entries_json_is_an_error(self):
        self._write('a.md', BODY)
        entries = json.dumps([{"path": "a.md", "metadata": FULL_METADATA}])

        _proc, payload = self._run_cli(
            'apply', '--entries-json', entries, '--paths', 'b.md'
        )

        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--paths', payload['message'])

    def test_dirs_and_exclude_are_reported_together(self):
        self._write('a.md', BODY)
        entries = json.dumps([{"path": "a.md", "metadata": FULL_METADATA}])

        _proc, payload = self._run_cli(
            'apply', '--entries-json', entries, '--dirs', 'docs/', '--exclude', 'x/'
        )

        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--dirs', payload['message'])
        self.assertIn('--exclude', payload['message'])

    def test_target_args_are_still_accepted_with_from_toc(self):
        """`--from-toc` との併用は従来どおり有効（過剰な拒否を防ぐ）。"""
        self._write('a.md', BODY)

        _proc, payload = self._run_cli(
            'apply', '--from-toc', 'nosuchkey', '--paths', 'a.md'
        )

        self.assertNotEqual(payload.get('error_code'), 'UNSUPPORTED_ARG')


if __name__ == '__main__':
    unittest.main()
