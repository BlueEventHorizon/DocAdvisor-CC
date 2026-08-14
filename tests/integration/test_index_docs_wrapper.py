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

    def _pending_sources(self, payload):
        """dispatch された pending が指す source_file をソートして返す。

        「何件か」ではなく「何が残り、何が落ちたか」を固定するために使う。
        """
        sources = []
        for agent in payload.get('agents') or []:
            for entry_file in agent['entry_files']:
                text = (self.project_root / entry_file).read_text(encoding='utf-8')
                for line in text.split('\n'):
                    # source_file は _meta ブロック配下にあるためインデントされる
                    if line.strip().startswith('source_file:'):
                        sources.append(line.split(':', 1)[1].strip().strip('"\''))
                        break
        return sorted(sources)

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
            any('withdrawn' in w for w in payload['warnings']),
            f"撤回したことが warnings で透明化されていない: {payload['warnings']}",
        )
        dispatched = [
            entry for agent in payload['agents'] for entry in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 1, '転記できる文書も AI 抽出へ回る')

    def _broken_scripts_copy(self, name, mutate):
        """scripts のコピーを作り、frontmatter/ を壊してからパスを返す。

        リポジトリの scripts/frontmatter/ には触らない。
        """
        scripts_copy = Path(self.tmpdir) / name
        shutil.copytree(
            SCRIPTS_DIR, scripts_copy,
            ignore=shutil.ignore_patterns('__pycache__'),
        )
        mutate(scripts_copy / 'frontmatter')
        return scripts_copy

    def _assert_breakage_is_reported_as_json_error(self, scripts_copy):
        """破損が単一 JSON の action: error として返ることを確認する。

        traceback で終了すると「stdout に単一 JSON」という CLI 契約
        （DES-005 §8.1）を破り、呼び出し側が action で分岐できない。
        silent success とは別種の欠陥として、これも許容しない。
        """
        proc = self._run_raw(
            scripts_copy / 'index_docs.py', '--key', 'rules', '--dirs', 'docs/',
            scripts_dir=scripts_copy,
        )

        self.assertEqual(
            proc.returncode, 1,
            f"破損が error になっていない: stdout={proc.stdout} stderr={proc.stderr}",
        )
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout が空（traceback で終了した）: {proc.stderr[-400:]}")
        self.assertEqual(
            len(out.split("\n")), 1,
            f"stdout は単一 JSON でなければならない: {out!r}",
        )
        self.assertNotIn(
            'Traceback', proc.stderr,
            'traceback で終了しており CLI 契約を満たしていない',
        )
        payload = json.loads(out)
        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error_code'], 'READ_ERROR')
        self.assertIn('破損', payload['message'])

    def test_missing_transcription_module_is_an_error_not_a_silent_skip(self):
        """**撤回と破損を区別すること。**

        ディレクトリごと消えているのは撤回であり許容する。ディレクトリはあるのに
        読み込めないのは破損である。

        破損を転記 0 件として続行しても toc.yaml の内容は正しい（未信頼の文書は
        AI 抽出へ回り、それは正常なフォールバック経路である）。失われるのは
        **転記による高速化だけ**である。したがって固定したいのは「誤った ToC が
        出ないこと」ではなく「**配布物が壊れたまま性能劣化が黙って続かないこと**」
        である。warnings は自動実行で見落とされるため成功経路に載せない。
        """
        self._write_md('docs/trusted.md', trusted_document())

        # ディレクトリは残し、転記モジュールだけを取り除く（部分配置の再現）
        scripts_copy = self._broken_scripts_copy(
            'scripts_missing_module',
            lambda fm_dir: (fm_dir / 'fm_to_pending.py').unlink(),
        )

        self._assert_breakage_is_reported_as_json_error(scripts_copy)

    def test_syntax_error_in_the_transcription_module_is_a_json_error(self):
        """構文破損も JSON の error として返ること。

        構文エラーは `SyntaxError` であり `ImportError` ではない。`ImportError`
        だけを捕まえていると例外が `main()` の外へ伝播し、traceback で終了して
        stdout に JSON が出ない。silent success は避けられても CLI 契約を破る。
        """
        self._write_md('docs/trusted.md', trusted_document())

        def break_syntax(fm_dir):
            (fm_dir / 'fm_to_pending.py').write_text(
                'def broken(:\n    pass\n', encoding='utf-8'
            )

        scripts_copy = self._broken_scripts_copy(
            'scripts_syntax_error', break_syntax
        )

        self._assert_breakage_is_reported_as_json_error(scripts_copy)

    def test_broken_dependency_of_the_transcription_module_is_a_json_error(self):
        """転記モジュールの依存（fm_core）が壊れている場合も JSON の error。"""
        self._write_md('docs/trusted.md', trusted_document())

        def break_dependency(fm_dir):
            (fm_dir / 'fm_core.py').write_text(
                'raise RuntimeError("simulated broken dependency")\n',
                encoding='utf-8',
            )

        scripts_copy = self._broken_scripts_copy(
            'scripts_broken_dependency', break_dependency
        )

        self._assert_breakage_is_reported_as_json_error(scripts_copy)


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

    def test_retry_goes_through_claim_so_a_second_run_does_not_double_dispatch(self):
        """retry が claim/lease に乗ること（二重投入の防止）。

        error_pending をそのまま dispatch すると claim_entries が error_message を
        持つ entry を reject するため claim が効かず、同じコマンドを再実行すると
        同一 entry が再投入される。複数 Agent が同じ pending を同時に更新すれば
        結果が競合・上書きされる。そこで retry は error 状態を解除してから通常の
        claim 経路へ合流させる。
        """
        key = 'rules'
        entry = self._make_error_pending(key)

        first = self._index('--key', key, '--dirs', 'docs/',
                            '--on-fill-error', 'retry')
        self.assertEqual(first['action'], 'dispatch')
        self.assertEqual(first['in_flight_agents'], 0)

        # 充填せずに再実行する。claim が効いていれば in-flight として扱われ wait。
        second = self._index('--key', key, '--dirs', 'docs/',
                             '--on-fill-error', 'retry')

        self.assertEqual(
            second['action'], 'wait',
            '2 回目が dispatch なら claim が効いておらず二重投入する',
        )
        self.assertEqual(second['in_flight_agents'], 1)

    def test_retry_clears_the_error_so_the_entry_is_a_normal_pending(self):
        """retry 後の entry が error_pending でなく通常の pending になること。"""
        key = 'rules'
        entry = self._make_error_pending(key)

        self._index('--key', key, '--dirs', 'docs/', '--on-fill-error', 'retry')

        entry_text = (self.project_root / entry).read_text(encoding='utf-8')
        self.assertNotIn('error_message', entry_text,
                         'error_message が残っていると再び error_pending に落ちる')
        self.assertIn('claimed_at', entry_text, 'claim のスタンプが付いている')


class TestUpperLayerContract(WrapperTestBase):
    """上位層（forge 等）が渡す JSON 形の引数を受けること

    forge の update-db-specs / update-db-rules は `.doc_structure.yaml` から解決した
    配列を `--dirs-json` / `--exclude-json` で渡し、index-docs を **1 回だけ** 呼ぶ
    （再実行や引数の組み替えをしない）。したがってこの形を受けられなくなると
    **上位層からの索引が動かなくなり、上位層には理由が分からない**。

    人間・AI が手で打つ `--dirs` / `--exclude` と、機械的に渡す JSON 形の両方を
    受けるのは、呼び出し元が 2 種類あるためである（オプションを増やしてよい
    という例外ではない）。
    """

    def test_dirs_json_is_accepted_as_forge_passes_it(self):
        for i in range(1, 4):
            self._write_md(f'docs/d{i}.md')

        payload = self._index('--key', 'rules', '--dirs-json', json.dumps(['docs/']))

        self.assertEqual(payload['action'], 'dispatch')
        dispatched = [
            e for agent in payload['agents'] for e in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 3)

    def test_exclude_json_is_accepted_and_applied(self):
        self._write_md('docs/keep.md')
        self._write_md('docs/drop.md')

        payload = self._index(
            '--key', 'rules',
            '--dirs-json', json.dumps(['docs/']),
            '--exclude-json', json.dumps(['docs/drop.md']),
        )

        self.assertEqual(payload['action'], 'dispatch')
        dispatched = [
            e for agent in payload['agents'] for e in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 1, 'exclude-json が効いていない')

    def test_exclude_applies_to_explicit_paths_too(self):
        """`--dirs` を伴わない指定でも除外が効くこと。

        除外は「選び方」ではなく「選んだ結果から何を落とすか」である。以前は
        ディレクトリ展開の内側でしか適用しておらず、明示 paths のみの指定では
        黙って無視されていた。
        """
        self._write_md('docs/keep.md')
        self._write_md('docs/drop.md')

        payload = self._index(
            '--key', 'rules',
            '--paths-json', json.dumps(['docs/keep.md', 'docs/drop.md']),
            '--exclude-json', json.dumps(['docs/drop.md']),
        )

        self.assertEqual(payload['action'], 'dispatch')
        dispatched = [
            e for agent in payload['agents'] for e in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 1, '明示 paths でも exclude が効く')

    def test_exclude_count_is_reported_for_explicit_paths(self):
        """明示 paths 経路でも落とした件数を warnings に載せること（DES-005 §4.2.2）。

        `--dirs` 経路だけが warning を出す形では、除外が効いたのか対象が最初から
        無かったのかを利用者が区別できない。
        """
        self._write_md('docs/keep.md')
        self._write_md('docs/drop.md')

        payload = self._index(
            '--key', 'rules',
            '--paths-json', json.dumps(['docs/keep.md', 'docs/drop.md']),
            '--exclude-json', json.dumps(['docs/drop.md']),
        )

        self.assertTrue(
            any('--exclude' in w for w in payload.get('warnings') or []),
            '除外件数が warnings に出ていない',
        )

    def test_repeated_and_json_forms_are_merged(self):
        self._write_md('a/one.md')
        self._write_md('b/two.md')

        payload = self._index(
            '--key', 'rules', '--dirs', 'a/', '--dirs-json', json.dumps(['b/']),
        )

        self.assertEqual(payload['action'], 'dispatch')
        dispatched = [
            e for agent in payload['agents'] for e in agent['entry_files']
        ]
        self.assertEqual(len(dispatched), 2, '併用時に連結されていない')

    def test_paths_file_is_accepted(self):
        self._write_md('docs/a.md')
        paths_file = self.project_root / 'paths.json'
        paths_file.write_text(json.dumps(['docs/a.md']), encoding='utf-8')

        payload = self._index('--key', 'rules', '--paths-file', 'paths.json')

        self.assertEqual(payload['action'], 'dispatch')

    def test_malformed_dirs_json_is_rejected(self):
        payload = self._index('--key', 'rules', '--dirs-json', '{not json')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'INVALID_PATH')

    def test_dirs_json_must_be_an_array_of_non_empty_strings(self):
        for bad in ('{"a": 1}', json.dumps(['ok', '']), json.dumps([1, 2])):
            with self.subTest(bad=bad):
                payload = self._index('--key', 'rules', '--dirs-json', bad)
                self.assertEqual(payload['action'], 'error')
                self.assertEqual(payload['error_code'], 'INVALID_PATH')


class TestExternalSymlinkPassThrough(WrapperTestBase):
    """越境 symlink をラッパー経由で扱うこと（NFR-N06）

    実運用で外部の仕様書を symlink で置いて索引している構成がある。上位層は
    index-docs を **1 回だけ** 呼び確認に答える経路を持たないため、明示指定された
    対象は確認を挟まず索引する。**索引するか否かの決定は呼び出し元に残す**のが
    doc-advisor の立場であり、渡す側はそれが symlink であることを知っている。

    走査（`--all`）だけは誰も対象を渡していないため確認する。
    """

    def _fresh_project_root(self):
        """独立した project root へ差し替える（1 テスト内で複数の形を試すため）。

        setUp を呼び直すと前回の一時ディレクトリが tearDown の対象から外れて
        残るため、addCleanup で個別に片付ける。
        """
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.project_root = Path(self.tmpdir)
        (self.project_root / '.git').mkdir()

    def _link_external_dir(self, link_rel, names):
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(outside), ignore_errors=True)
        for name in names:
            (outside / name).write_text('# Ext\n\nThis is body content.\n',
                                        encoding='utf-8')
        link = self.project_root / link_rel
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlink not supported on this platform')
        return outside

    def test_dirs_containing_external_symlink_reaches_done(self):
        """--dirs 配下の越境 symlink が confirm を挟まず done まで到達すること。"""
        self._link_external_dir('docs/shared', ['a.md', 'b.md'])

        payload, _calls, _agents = self._drive_to_done(
            'specs', '--key', 'specs', '--dirs', 'docs/',
        )

        self.assertEqual(payload['counts']['added'], 2)

    def test_the_warning_names_the_target_on_the_first_call(self):
        """注意喚起は prepare が走る最初の応答に出ること（解決先と件数を含む）。

        ラッパーは状態を持たないため、prepare の warning は初回の応答にだけ載る
        （2 回目以降は prepare を再実行しない）。呼び出し側は action を問わず
        warnings を提示する契約であり、ここで消えると注意喚起の唯一の経路が失われる。
        """
        outside = self._link_external_dir('docs/shared', ['a.md', 'b.md'])

        first = self._index('--key', 'specs', '--dirs', 'docs/')

        self.assertEqual(first['action'], 'dispatch')
        hit = [w for w in first['warnings'] if 'external symlink indexed' in w]
        self.assertEqual(len(hit), 1, f"warnings: {first['warnings']}")
        self.assertIn('docs/shared', hit[0])
        self.assertIn(str(outside), hit[0])
        self.assertIn('2 file(s)', hit[0])

    def test_every_target_form_indexes_it(self):
        """判定基準は「単体モードか否か」であり、対象指定の形によらないこと。

        `--dirs` だけを確認しても足りない。上位層は `--dirs-json` を渡し、
        長大な配列では `--paths-file` を渡す。どの形でも同じ経路を通る。
        """
        forms = [
            ('--dirs', ['--dirs', 'docs/']),
            ('--dirs-json', ['--dirs-json', json.dumps(['docs/'])]),
            ('--paths', ['--paths', 'docs/external/a.md']),
            ('--paths-json', ['--paths-json', json.dumps(['docs/external/a.md'])]),
            ('--paths-file', ['--paths-file', 'targets.json']),
        ]
        for label, args in forms:
            with self.subTest(form=label):
                self._fresh_project_root()
                self._link_external_dir('docs/external', ['a.md'])
                (self.project_root / 'targets.json').write_text(
                    json.dumps(['docs/external/a.md']), encoding='utf-8')

                payload, _calls, _agents = self._drive_to_done(
                    'specs', '--key', 'specs', *args,
                )

                self.assertEqual(payload['counts']['added'], 1)

    def test_single_mode_asks_before_leaving_the_root(self):
        """--all の走査で見つかった越境 symlink は confirm になること。"""
        self._link_external_dir('docs/shared', ['a.md'])

        payload = self._index('--all')

        self.assertEqual(payload['action'], 'confirm')
        self.assertEqual(payload['reason'], 'external_symlink')
        self.assertEqual(
            [e['symlink'] for e in payload['external_pending']], ['docs/shared'],
        )

    def test_single_mode_indexes_after_approval(self):
        """--all + --allow-external で承認された symlink が索引されること。"""
        self._link_external_dir('docs/shared', ['a.md'])

        payload, _calls, _agents = self._drive_to_done(
            'all', '--all', '--allow-external', 'docs/shared',
        )

        self.assertEqual(payload['counts']['added'], 1)


class TestSingleModeHasTwoEntrances(WrapperTestBase):
    """単体モードの制約は `--all` と `--key` 省略の**両方**にかかること。

    REQ-001 FR-N04-1 / FR-N04-5 は `--all` の明示と `--key` の省略を同義と定める。
    ガードを `args.all` だけで書くと後者が素通りし、渡した対象指定が prepare の
    単体モード分岐で捨てられる。**その帰結は「1 件だけ索引するつもりが project root
    全体が索引され、desired-state のため ToC の内容も全件へ置き換わる」**である。

    実際にこの欠陥が発生したため、2 つの入口が同じ扱いを受けることを固定する。
    """

    def test_omitted_key_with_paths_is_rejected(self):
        """`--key` 省略 + `--paths` を黙って全件索引に変えない。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/other.md')

        payload = self._index('--paths', 'docs/keep.md')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--paths', payload['message'])
        self.assertIn('--key', payload['message'], '対処方法として --key を案内する')

    def test_omitted_key_with_dirs_is_rejected(self):
        self._write_md('docs/keep.md')

        payload = self._index('--dirs', 'docs/')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--dirs', payload['message'])

    def test_omitted_key_with_exclude_is_rejected(self):
        """`--exclude` 側のガードも同じ条件で働く。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index('--exclude', 'docs/draft')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--exclude', payload['message'])

    def test_omitted_key_with_dirs_and_exclude_is_rejected(self):
        """`--all --exclude` の拒否メッセージが案内する形へ書き換えても素通りしない。

        以前はこの形が「excluded by --exclude: N path(s)」と警告を出しながら
        除外対象を索引しており、報告と実態が食い違っていた。
        """
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index('--dirs', 'docs/', '--exclude', 'docs/draft')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_omitted_key_without_targets_still_scans_everything(self):
        """引数なしの単体モードは従来どおり全件索引する（過剰な拒否を防ぐ）。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index()

        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(payload['key'], 'all')
        self.assertEqual(
            self._pending_sources(payload),
            ['docs/draft/drop.md', 'docs/keep.md'],
        )

    def test_explicit_key_with_targets_still_works(self):
        """`--key` を渡す通常経路は影響を受けない（過剰な拒否を防ぐ）。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index(
            '--key', 'rules', '--dirs', 'docs/', '--exclude', 'docs/draft'
        )

        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(self._pending_sources(payload), ['docs/keep.md'])


class TestExcludeIsNeverSilentlyIgnored(WrapperTestBase):
    """除外を適用できない経路で `--exclude` を黙って捨てないこと（DES-005 §4.2.2）。

    除外は「確定した対象集合」へ適用する規則だが、単体モード（prepare が自分で走査する）と
    `--paths-file`（配列をファイルのまま渡す）では対象集合がラッパーの手元に無い。
    黙って捨てると「除外したつもりの文書が索引される」ため拒否する。
    """

    def test_all_with_exclude_is_rejected(self):
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index('--all', '--exclude', 'docs/draft')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--all', payload['message'])

    def test_paths_file_with_exclude_is_rejected(self):
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')
        paths_file = self.project_root / 'paths.json'
        paths_file.write_text(
            json.dumps(['docs/keep.md', 'docs/draft/drop.md']), encoding='utf-8'
        )

        payload = self._index(
            '--key', 'rules', '--paths-file', str(paths_file),
            '--exclude', 'docs/draft',
        )

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--paths-file', payload['message'])

    def test_dirs_with_exclude_still_applies(self):
        """適用できる経路では従来どおり除外し、件数を報告する（過剰な拒否を防ぐ）。

        **残ったパスを固定する。** action と警告文だけを見ると、除外が過剰に
        マッチして残すべき文書まで落とす退行を検出できない（`filter_excluded` が
        残す側と落とす側を取り違えても、dispatch も警告も成立してしまう）。
        """
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/drop.md')

        payload = self._index(
            '--key', 'rules', '--dirs', 'docs/', '--exclude', 'docs/draft'
        )

        self.assertEqual(payload['action'], 'dispatch')
        self.assertTrue(
            any('--exclude' in w for w in payload.get('warnings') or [])
        )
        self.assertEqual(self._pending_sources(payload), ['docs/keep.md'])


class TestPathsFileIsExclusive(WrapperTestBase):
    """`--paths-file` と他の対象指定の併用を拒否すること（DES-005 §4.2.3）。

    `--dirs` / `--paths` とそれぞれの JSON 形は連結されるが、`--paths-file` は
    配列をファイルのまま prepare へ渡す経路であり連結する先が無い。実装は
    `--paths-file` を優先して他を捨てるため、黙って受理すると「指定したのに
    索引されない文書がある」状態になる（§4.2.2 の黙殺と同型）。
    """

    def _paths_file(self, *rel_paths):
        paths_file = self.project_root / 'paths.json'
        paths_file.write_text(json.dumps(list(rel_paths)), encoding='utf-8')
        return str(paths_file)

    def test_paths_file_with_dirs_is_rejected(self):
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/d.md')

        payload = self._index(
            '--key', 'rules',
            '--paths-file', self._paths_file('docs/keep.md'),
            '--dirs', 'docs/draft',
        )

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--paths-file', payload['message'])
        self.assertIn('--dirs', payload['message'])

    def test_paths_file_with_paths_is_rejected(self):
        self._write_md('docs/keep.md')
        self._write_md('docs/other.md')

        payload = self._index(
            '--key', 'rules',
            '--paths-file', self._paths_file('docs/keep.md'),
            '--paths', 'docs/other.md',
        )

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--paths', payload['message'])

    def test_paths_file_with_dirs_json_is_rejected(self):
        """JSON 形（上位層が渡す経路）でも同じく拒否する。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/d.md')

        payload = self._index(
            '--key', 'rules',
            '--paths-file', self._paths_file('docs/keep.md'),
            '--dirs-json', json.dumps(['docs/draft']),
        )

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
        self.assertIn('--dirs-json', payload['message'])

    def test_paths_file_alone_still_works(self):
        """単独指定は従来どおり通ること（過剰な拒否を防ぐ）。"""
        self._write_md('docs/keep.md')
        self._write_md('docs/draft/d.md')

        payload = self._index(
            '--key', 'rules', '--paths-file', self._paths_file('docs/keep.md')
        )

        self.assertEqual(payload['action'], 'dispatch')
        self.assertEqual(self._pending_sources(payload), ['docs/keep.md'])


class TestAbnormalPathsStillEmitJson(WrapperTestBase):
    """**異常入力でも単一 JSON を返すこと**（DES-005 §8.1）。

    `filter_excluded` の新設で「絶対パス + `--exclude`」がラッパーを traceback で
    落とす退行が起きた（`--exclude` なしなら `prepare_toc` が `ABSOLUTE_PATH` を返して
    いた）。除外の判定点で不正なパスを先取りせず、分類を下流へ委ねることを固定する。
    """

    def test_absolute_path_with_exclude_returns_json(self):
        self._write_md('docs/a.md')

        payload = self._index(
            '--key', 'rules',
            '--paths', '/etc/hosts.md',
            '--exclude', 'docs/draft',
        )

        self.assertIn('status', payload)
        self.assertIn('error_code', payload)

    def test_absolute_path_classification_matches_without_exclude(self):
        """`--exclude` の有無で分類が変わらないこと。"""
        self._write_md('docs/a.md')

        without = self._index('--key', 'rules', '--paths', '/etc/hosts.md')
        with_exclude = self._index(
            '--key', 'rules', '--paths', '/etc/hosts.md', '--exclude', 'docs/draft'
        )

        self.assertEqual(with_exclude['error_code'], without['error_code'])
        self.assertEqual(with_exclude['action'], without['action'])


class TestArgumentContract(WrapperTestBase):
    """引数の矛盾・不正が error として返ること"""

    def test_all_cannot_be_combined_with_explicit_targets(self):
        self._write_md('docs/a.md')

        payload = self._index('--all', '--dirs', 'docs/')

        self.assertEqual(payload['action'], 'error')
        self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')

    def test_all_cannot_be_combined_with_json_form_targets(self):
        """JSON 形の対象指定も `--all` との併用を拒否し、フラグ名を報告すること。"""
        self._write_md('docs/a.md')

        for flag, value in (('--dirs-json', json.dumps(['docs/'])),
                            ('--paths-json', json.dumps(['docs/a.md']))):
            with self.subTest(flag=flag):
                payload = self._index('--all', flag, value)
                self.assertEqual(payload['action'], 'error')
                self.assertEqual(payload['error_code'], 'UNSUPPORTED_ARG')
                self.assertIn(
                    flag, payload['message'],
                    'どの引数が併用されたかを報告していない',
                )

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
