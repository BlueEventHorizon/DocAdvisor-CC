#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index_docs.py（索引パイプラインのラッパー）の統合テスト。

ラッパーの目的は「AI から script 間の配管を取り除く」ことであり、検証すべきは
**1 回の呼び出しで進むところまで進み、次に何をすべきかを action で返すこと**である。

テスト対象:
- 同じコマンドを繰り返すだけで prepare → 転記 → 充填 → merge が進むこと
- action の値域（dispatch / wait / confirm / done / error）と分岐条件
- agents[].prompt が Agent へそのまま渡せる文字列になっていること
- claim により同じコマンドの再実行が二重投入しないこと
- 空きスロットを **走行中 Agent 数**で数えること（entry 数で引くと負になり、
  補充されず wave 実行へ逆戻りする。ADR-006 が警告した回帰の固定）
- 全件転記できたとき Agent を 1 つも返さず done へ直行すること
- **転記フェーズを呼ばなくても全体が通ること**（フロントマター撤回の予行。
  DES-008 §6.1 の「1 ディレクトリの削除で戻せる」が実際に成立しているか）
- 削除のみ / 対象 0 件 / 全件 unchanged の各冪等経路
- done が完了レポートに必要な値（transcribed / ai_extracted）を自分で数えること

テスト方針:
- ラッパーは subprocess で呼び、stdout の単一 JSON 契約（DES-005 §8.1）も検証する
- 充填は write_pending.py で代替する（AI 層である toc-updater は起動できない）
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'plugins', 'doc-advisor', 'scripts'
))
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import MARKER, compute_body_hash
from toc_store import ERROR_CODES, STATUSES, WORK_DIRNAME, resolve_store_dir
from toc_utils import load_existing_toc

INDEX_DOCS_SCRIPT = os.path.join(SCRIPTS_DIR, 'index_docs.py')
WRITE_PENDING_SCRIPT = os.path.join(SCRIPTS_DIR, 'write_pending.py')

# index_docs が返す action の値域（script 側の定数と一致することを確認する）
ACTIONS = frozenset({'dispatch', 'wait', 'confirm', 'done', 'error'})

# write_pending は content_details / keywords に最低 5 件を要求する（充填品質の下限）
SAMPLE_ARGS = [
    '--title', 'Filled Document',
    '--purpose', 'Filled by the test in place of the toc-updater agent.',
    '--content-details', ' ||| '.join(f'detail-{i}' for i in range(1, 6)),
    '--applicable-tasks', ' ||| '.join(f'task-{i}' for i in range(1, 3)),
    '--keywords', ' ||| '.join(f'keyword-{i}' for i in range(1, 6)),
]

TRUSTED_BODY = "# Trusted\n\nBody of a document that carries its own metadata.\n"
TRUSTED_METADATA = {
    'title': 'Trusted Document',
    'purpose': 'Carries doc-advisor metadata in its own frontmatter.',
    'content_details': ['detail A', 'detail B'],
    'applicable_tasks': ['task A'],
    'keywords': ['Trusted', 'frontmatter'],
}


def trusted_document(body=TRUSTED_BODY):
    """転記の対象になる（信頼できる）フロントマターを持つ文書。"""
    lines = ["---", f"type: {MARKER}"]
    for key, value in TRUSTED_METADATA.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f'  - "{item}"')
        else:
            lines.append(f'{key}: "{value}"')
    lines.append(f"body_hash: {compute_body_hash(body)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


class WrapperTestBase(unittest.TestCase):
    """一時 project root とラッパー実行ヘルパ。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        os.makedirs(self.project_root / '.git', exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_md(self, rel_path, content='# Title\n\nThis is body content.\n'):
        full = self.project_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
        return full

    def _store_dir(self, key):
        return resolve_store_dir(key, project_root=self.project_root)

    def _run_raw(self, script, *args, scripts_dir=None):
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = str(scripts_dir or SCRIPTS_DIR)
        return subprocess.run(
            [sys.executable, str(script)] + list(args),
            capture_output=True, text=True,
            cwd=str(self.project_root), env=env,
        )

    def _index(self, *args):
        """ラッパーを呼び、stdout の単一 JSON 契約を検証して payload を返す。"""
        proc = self._run_raw(INDEX_DOCS_SCRIPT, *args)
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(
            len(out.split("\n")), 1,
            f"stdout must be a single JSON line: {out!r}",
        )
        payload = json.loads(out)
        self.assertIn(payload["status"], STATUSES)
        self.assertTrue(
            payload["error_code"] is None or payload["error_code"] in ERROR_CODES,
            f"error_code not in enum: {payload['error_code']}",
        )
        self.assertIn(payload["action"], ACTIONS)
        return payload

    def _fill(self, key, entry_file):
        """write_pending.py で pending を充填する（toc-updater の代替）。"""
        key_args = ['--all'] if key == 'all' else ['--key', key]
        proc = self._run_raw(
            WRITE_PENDING_SCRIPT, *key_args,
            '--entry-file', str(entry_file), *SAMPLE_ARGS,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"write_pending failed: {proc.stdout} {proc.stderr}",
        )

    def _fill_all_dispatched(self, key, payload):
        """dispatch された全 entry を充填する。"""
        for agent in payload['agents']:
            for entry_file in agent['entry_files']:
                self._fill(key, self.project_root / entry_file)

    def _drive_to_done(self, key, *args, max_rounds=20):
        """done になるまで同じコマンドを繰り返す（AI の待機ループの代替）。

        Returns:
            tuple: (最後の payload, 呼び出し回数, 起動した Agent 総数)
        """
        calls = 0
        agents_started = 0
        payload = None
        for _ in range(max_rounds):
            payload = self._index(*args)
            calls += 1
            if payload['action'] == 'done':
                return payload, calls, agents_started
            if payload['action'] == 'dispatch':
                agents_started += len(payload['agents'])
                self._fill_all_dispatched(key, payload)
                continue
            self.fail(f"unexpected action: {payload}")
        self.fail(f"did not reach done in {max_rounds} rounds: {payload}")


class TestSameCommandDrivesThePipeline(WrapperTestBase):
    """同じコマンドの繰り返しで prepare → 充填 → merge が完了すること"""

    def test_repeating_one_command_reaches_done(self):
        key = 'rules'
        for i in range(1, 5):
            self._write_md(f'docs/d{i}.md')

        payload, calls, agents = self._drive_to_done(key, '--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['counts']['added'], 4)
        self.assertEqual(payload['ai_extracted'], 4)
        self.assertEqual(payload['transcribed'], 0)
        # 4 件 / max_batch 3 → 2 グループ。1 回目 dispatch、2 回目 done。
        self.assertEqual(agents, 2)
        self.assertEqual(calls, 2)

        toc = load_existing_toc(self._store_dir(key) / 'toc.yaml')
        self.assertEqual(len(toc), 4)

    def test_dispatch_prompt_is_ready_to_pass_to_an_agent(self):
        """prompt が転記なしでそのまま Agent へ渡せる形であること。"""
        self._write_md('docs/a.md')

        payload = self._index('--key', 'rules', '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'dispatch')
        agent = payload['agents'][0]
        self.assertEqual(agent['subagent_type'], 'doc-advisor:toc-updater')
        self.assertIn('key: rules', agent['prompt'])
        self.assertIn('entry_files:', agent['prompt'])
        # entry_files はそのまま prompt に含まれる（呼び出し側が組み立てない）
        for entry_file in agent['entry_files']:
            self.assertIn(entry_file, agent['prompt'])

    def test_single_mode_prompt_marks_the_reserved_key(self):
        """単体モードでは toc-updater が --all を使う必要があるため明示する。"""
        self._write_md('docs/a.md')

        payload = self._index('--all')

        self.assertEqual(payload['action'], 'dispatch')
        self.assertIn('all (single mode)', payload['agents'][0]['prompt'])


class TestNoDoubleDispatch(WrapperTestBase):
    """claim により同じコマンドの再実行が二重投入しないこと"""

    def test_second_call_without_filling_returns_wait(self):
        self._write_md('docs/a.md')

        first = self._index('--key', 'rules', '--dirs', 'docs/')
        second = self._index('--key', 'rules', '--dirs', 'docs/')

        self.assertEqual(first['action'], 'dispatch')
        self.assertEqual(second['action'], 'wait')
        self.assertEqual(second['agents'] if 'agents' in second else [], [])
        self.assertEqual(second['in_flight_agents'], 1)


class TestWindowIsCountedInAgents(WrapperTestBase):
    """空きスロットを走行中 Agent 数で数えること（ADR-006 の回帰固定）

    `in_flight` は entry のフラットリストである。entry 数で引くと過大に減算されて
    負になり、補充されないまま wave 実行へ逆戻りする。
    """

    def test_available_never_goes_negative(self):
        # 1 グループ 3 件 × 2 グループ = 6 件を投入し、window を 1 に絞る。
        # entry 数（6）で引けば 1 - 6 = -5 になるが、Agent 数（2）で引くので 0 で止まる。
        for i in range(1, 7):
            self._write_md(f'docs/d{i}.md')

        first = self._index('--key', 'rules', '--dirs', 'docs/')
        self.assertEqual(first['action'], 'dispatch')
        self.assertEqual(len(first['agents']), 2, '6 件 / max_batch 3 = 2 グループ')

        second = self._index('--key', 'rules', '--dirs', 'docs/', '--window', '1')

        self.assertEqual(second['action'], 'wait')
        self.assertEqual(second['available'], 0, 'available が負にならない')
        self.assertEqual(second['in_flight_agents'], 2, 'entry 数 6 ではなく Agent 数 2')

    def test_window_limits_the_number_of_agents_started(self):
        for i in range(1, 10):
            self._write_md(f'docs/d{i}.md')

        payload = self._index('--key', 'rules', '--dirs', 'docs/',
                              '--window', '2', '--max-batch', '1')

        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(len(payload['agents']), 2, 'window を超えて起動しない')
        self.assertEqual(payload['available'], 2)


class TestTranscriptionSkipsAgents(WrapperTestBase):
    """信頼できるフロントマターを持つ文書が Agent を起動せず done へ直行すること"""

    def test_all_transcribed_reaches_done_without_any_agent(self):
        key = 'rules'
        for i in range(1, 4):
            body = f"# Doc {i}\n\nBody of document {i}.\n"
            self._write_md(f'docs/d{i}.md', trusted_document(body))

        payload = self._index('--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'done', '1 回の呼び出しで完了する')
        self.assertEqual(payload['transcribed'], 3)
        self.assertEqual(payload['ai_extracted'], 0)
        self.assertEqual(payload['ai_extracted_paths'], [])
        toc = load_existing_toc(self._store_dir(key) / 'toc.yaml')
        self.assertEqual(len(toc), 3)

    def test_mixed_corpus_only_dispatches_the_untrusted_ones(self):
        key = 'rules'
        self._write_md('docs/trusted.md', trusted_document())
        self._write_md('docs/plain.md')

        payload = self._index('--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(payload['transcribed'], 1)
        dispatched = [
            entry for agent in payload['agents'] for entry in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 1, '転記済みは投入されない')

    def test_ai_extracted_paths_lists_only_agent_filled_documents(self):
        key = 'rules'
        self._write_md('docs/trusted.md', trusted_document())
        self._write_md('docs/plain.md')

        payload, _calls, _agents = self._drive_to_done(
            key, '--key', key, '--dirs', 'docs/'
        )

        self.assertEqual(payload['transcribed'], 1)
        self.assertEqual(payload['ai_extracted'], 1)
        self.assertEqual(payload['ai_extracted_paths'], ['docs/plain.md'])


class TestFrontmatterWithdrawalRehearsal(WrapperTestBase):
    """転記フェーズが無くても全体が通ること（DES-008 §6.1 の撤回可能性）

    フロントマター方式を撤回する場合、`scripts/frontmatter/` をディレクトリごと
    削除し、ラッパーの転記ブロック（_transcribe とその呼び出し）を削るだけで済む
    という設計になっている。それが実際に成立しているかを、frontmatter/ を
    import できない状態にして確認する。

    転記が行われなければ、信頼できるフロントマターを持つ文書も AI 抽出へ回る
    （転記 0 件と等価）。索引そのものは完了する。
    """

    def _run_without_frontmatter_dir(self, *args):
        """frontmatter/ を持たない scripts ツリーのコピーでラッパーを実行する。

        **リポジトリの scripts/frontmatter/ には一切触らない。** 実物を消して
        finally で戻す形にすると、プロセスが途中で落ちたときにリポジトリが
        壊れた状態で残る。撤回の予行はコピーの上で行えば十分である。
        """
        scripts_copy = Path(self.tmpdir) / 'scripts_without_frontmatter'
        shutil.copytree(
            SCRIPTS_DIR, scripts_copy,
            ignore=shutil.ignore_patterns('__pycache__'),
        )
        shutil.rmtree(scripts_copy / 'frontmatter')
        return self._run_raw(
            scripts_copy / 'index_docs.py', *args, scripts_dir=scripts_copy,
        )

    def test_indexing_completes_when_transcription_is_unavailable(self):
        key = 'rules'
        # 転記できるはずの文書を置く。転記が使えなければ AI 抽出へ回るだけで、
        # 索引が止まってはならない。
        self._write_md('docs/trusted.md', trusted_document())

        proc = self._run_without_frontmatter_dir('--key', key, '--dirs', 'docs/')

        self.assertEqual(
            proc.returncode, 0,
            f"転記が使えない状態で索引が失敗した: {proc.stdout} {proc.stderr}",
        )
        payload = json.loads(proc.stdout.strip())
        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(payload['transcribed'], 0, '転記は 0 件になる')
        self.assertTrue(
            any('transcription skipped' in w or 'transcription failed' in w
                for w in payload['warnings']),
            f"転記を飛ばしたことが warnings で透明化されていない: {payload['warnings']}",
        )
        dispatched = [
            entry for agent in payload['agents'] for entry in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 1, '転記できる文書も AI 抽出へ回る')


class TestIdempotentPaths(WrapperTestBase):
    """変更なし / 削除のみ / 対象 0 件の冪等経路"""

    def test_all_unchanged_returns_done_without_merging(self):
        key = 'rules'
        self._write_md('docs/a.md')
        self._drive_to_done(key, '--key', key, '--dirs', 'docs/')

        payload = self._index('--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'done')
        self.assertEqual(payload['counts']['unchanged'], 1)
        self.assertEqual(payload['counts']['added'], 0)
        self.assertEqual(payload['counts']['updated'], 0)
        self.assertEqual(payload['transcribed'], 0)

    def test_deleted_only_is_reflected_without_dispatching(self):
        key = 'rules'
        self._write_md('docs/a.md')
        self._write_md('docs/b.md')
        self._drive_to_done(key, '--key', key, '--dirs', 'docs/')

        # b.md を desired から外す（--paths で a.md のみを渡す）
        payload = self._index('--key', key, '--paths', 'docs/a.md')

        self.assertEqual(payload['action'], 'done')
        self.assertEqual(payload['counts']['deleted'], 1)
        self.assertEqual(payload['deleted_paths'], ['docs/b.md'])
        toc = load_existing_toc(self._store_dir(key) / 'toc.yaml')
        self.assertEqual(list(toc.keys()), ['docs/a.md'])

    def test_empty_target_set_emits_an_empty_toc(self):
        key = 'rules'
        (self.project_root / 'docs').mkdir()

        payload = self._index('--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'done')
        self.assertEqual(payload['counts']['added'], 0)
        toc_path = self._store_dir(key) / 'toc.yaml'
        self.assertTrue(toc_path.exists(), '空 ToC が冪等出力される')


class TestFillErrorIsNotSilentlyMerged(WrapperTestBase):
    """充填エラーが残る場合に silent merge しないこと（DES-005 §6.6）"""

    def _make_error_pending(self, key):
        self._write_md('docs/a.md')
        payload = self._index('--key', key, '--dirs', 'docs/')
        entry = payload['agents'][0]['entry_files'][0]
        proc = self._run_raw(
            WRITE_PENDING_SCRIPT, '--key', key,
            '--entry-file', str(self.project_root / entry),
            '--error', '--error-message', 'extraction failed in the test',
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return entry

    def test_blocked_returns_confirm_with_the_failed_entries(self):
        key = 'rules'
        entry = self._make_error_pending(key)

        payload = self._index('--key', key, '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'confirm')
        self.assertEqual(payload['reason'], 'fill_error')
        self.assertEqual(
            [item['entry_file'] for item in payload['error_pending']], [entry]
        )
        self.assertIn('hint', payload)

    def test_on_fill_error_merge_drops_the_entry_and_says_so(self):
        key = 'rules'
        self._make_error_pending(key)

        payload = self._index('--key', key, '--dirs', 'docs/',
                              '--on-fill-error', 'merge')

        self.assertEqual(payload['action'], 'done')
        self.assertTrue(
            any('dropped from this ToC' in w for w in payload['warnings']),
            f"脱落が透明化されていない: {payload['warnings']}",
        )

    def test_on_fill_error_abort_stops_without_merging(self):
        key = 'rules'
        self._make_error_pending(key)

        payload = self._index('--key', key, '--dirs', 'docs/',
                              '--on-fill-error', 'abort')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['status'], 'error')

    def test_on_fill_error_retry_redispatches_the_failed_entry(self):
        key = 'rules'
        entry = self._make_error_pending(key)

        payload = self._index('--key', key, '--dirs', 'docs/',
                              '--on-fill-error', 'retry')

        self.assertEqual(payload['action'], 'dispatch')
        self.assertTrue(payload['retry'])
        dispatched = [
            e for agent in payload['agents'] for e in agent['entry_files']
        ]
        self.assertEqual(dispatched, [entry])
        self.assertTrue(
            any('keep failing on every retry' in w for w in payload['warnings']),
            '恒常的失敗の警告が出ていない',
        )


class TestArgumentContract(WrapperTestBase):
    """引数の矛盾・不正が error として返ること"""

    def test_all_cannot_be_combined_with_explicit_targets(self):
        self._write_md('docs/a.md')

        payload = self._index('--all', '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_reserved_key_is_rejected(self):
        payload = self._index('--key', 'all', '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'KEY_RESERVED')

    def test_malformed_paths_json_is_rejected(self):
        payload = self._index('--key', 'rules', '--paths-json', '{not json')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'INVALID_PATH')


class TestSourcesAreNeverModified(WrapperTestBase):
    """索引実行が原本を書き換えないこと（REQ-006 の制約）"""

    def test_indexing_leaves_every_source_byte_identical(self):
        key = 'rules'
        contents = {}
        for i in range(1, 4):
            path = self._write_md(f'docs/d{i}.md')
            contents[path] = path.read_bytes()
        trusted = self._write_md('docs/trusted.md', trusted_document())
        contents[trusted] = trusted.read_bytes()

        self._drive_to_done(key, '--key', key, '--dirs', 'docs/')

        for path, before in contents.items():
            self.assertEqual(
                path.read_bytes(), before,
                f"索引実行が原本を書き換えた: {path}",
            )


class TestWorkDirIsRemovedOnSuccess(WrapperTestBase):
    """成功時に .toc_work/ が残らないこと（残存は異常シグナル）"""

    def test_work_dir_is_gone_after_done(self):
        key = 'rules'
        self._write_md('docs/a.md')

        self._drive_to_done(key, '--key', key, '--dirs', 'docs/')

        work_dir = self._store_dir(key) / WORK_DIRNAME
        self.assertFalse(
            work_dir.exists(),
            '.toc_work/ の残存は merge 未完の異常シグナルであり成功時は消える',
        )


if __name__ == '__main__':
    unittest.main()
