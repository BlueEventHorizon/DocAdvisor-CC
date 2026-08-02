#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_write.py のユニットテスト（DES-008 §4.2 / §4.5 / §6.2 / §6.3、DES-005 §8.1）。

テスト対象:
- 処理順序（書き込み → 整形 → 打刻）が守られ、打刻が整形の不動点に置かれること。
  偽の整形器で本文を書き換えても、直後の fm_read が trust == true を返す
- 同一文書へ 2 回連続適用して内容が変化しないこと（冪等）
- --format-command 未指定でも正常終了し trust == true になること
- 未知キー（name / description / applicable_when）が保持されること
- type が和集合で更新されること
- 整形コマンドが非ゼロ終了したとき当該 entry が失敗として報告され打刻されないこと
- 未閉鎖フロントマター・不正キーが当該 entry の失敗になり、他の entry は処理されること
- 整形コマンドがシェルを介さず実行され、対象ファイル以外を書き換えないこと
- 原子的書き込みがパーミッションを維持し、一時ファイルを残さないこと
- status / error_code の値域が定義された集合に含まれること
- argparse エラー・--entries-json の形式不正が JSON になること（subprocess 経路）

テスト方針:
- 書き込みと JSON 組み立ては in-process import（emit_json に stream を渡して検証する）
- CLI 契約（引数エラー・exit code・stdout 単一 JSON）は subprocess で確認する
- 偽の整形器は一時ディレクトリに置いた Python スクリプトとして作る（外部依存を持たない）
"""

import contextlib
import io
import json
import os
import shlex
import shutil
import stat
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

import fm_write as fm_write_module
from fm_core import MARKER, compute_body_hash, evaluate, split_document
from fm_read import ERROR_CODES, STATUSES, STATUS_ERROR, STATUS_OK, STATUS_PARTIAL, ErrorCode
from fm_write import (
    build_format_argv,
    main,
    parse_entries_json,
    process_entries,
    validate_format_command,
    validate_metadata_argument,
    write_entry,
)

FM_WRITE_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_write.py')

BODY = "# タイトル\n\n本文の内容。\n"

WRITE_METADATA = {
    "title": "テスト文書",
    "purpose": "fm_write の検証に用いる文書であることを示す",
    "content_details": ["項目 A", "項目 B"],
    "applicable_tasks": ["タスク A"],
    "keywords": ["fm_write", "body_hash"],
}

# 偽の整形器: 本文末尾へマーカー行を 1 度だけ足す。
# 「末尾に空行を足す」だけでは normalize_body が空行を落とすためハッシュが変わらず、
# 打刻順序の証明にならない。正規化を越えて本文が変わり、かつ 2 回目は変化しない
# （冪等な整形器の模倣）ものを使う。
FORMATTER_MARKER = "<!-- formatted -->"

FAKE_FORMATTER = '''\
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    text = f.read()
marker = "{marker}"
if marker not in text:
    text = text.rstrip("\\n") + "\\n\\n" + marker + "\\n"
with open(path, "w", encoding="utf-8") as f:
    f.write(text)
'''.format(marker=FORMATTER_MARKER)

FAILING_FORMATTER = '''\
import sys

sys.stderr.write("formatter failed\\n")
sys.exit(3)
'''


def plain_document(body=BODY):
    """フロントマターを持たない文書。"""
    return body


def skill_like_document(body=BODY):
    """doc-advisor 以外のキーを持つ文書（DES-008 §4.5 の共存対象）。"""
    return (
        "---\n"
        "name: foo-skill\n"
        "description: Foo をするスキル\n"
        "applicable_when:\n"
        "  - Foo をしたいとき\n"
        "---\n"
    ) + body


def temporary_feature_document(body=BODY):
    """forge の一時文書標識のみを持つ文書（type の和集合更新の対象）。"""
    return (
        "---\n"
        "type: temporary-feature-requirement\n"
        "---\n"
    ) + body


class FmWriteTestBase(unittest.TestCase):
    """一時ディレクトリに文書と偽の整形器を配置する共通セットアップ。"""

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

    def _formatter_command(self, source=FAKE_FORMATTER, name='fake_formatter.py',
                           suffix=''):
        """偽の整形器を配置し --format-command 文字列を返す。"""
        script = self._write(name, source)
        command = f"{shlex.quote(sys.executable)} {shlex.quote(script)} {{file}}"
        return command + suffix

    def _entries(self, *paths, metadata=None):
        return [
            (path, dict(WRITE_METADATA if metadata is None else metadata))
            for path in paths
        ]


class TestStampAfterFormatting(FmWriteTestBase):
    """打刻が整形の不動点に置かれること（DES-008 §4.2 / §6.3）"""

    def test_trust_is_true_after_formatting_changed_the_body(self):
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command()

        result = write_entry(path, dict(WRITE_METADATA), command)

        self.assertTrue(result['ok'], result['detail'])
        self.assertTrue(result['formatted'])
        text = self._read(path)
        # 整形器が本文を実際に変えたこと（順序が逆なら打刻は無効化される）
        self.assertIn(FORMATTER_MARKER, split_document(text).body)
        # 打刻が整形後の本文に対して行われていること
        self.assertEqual(result['body_hash'],
                         compute_body_hash(split_document(text).body))
        self.assertTrue(evaluate(text).trust)

    def test_stamping_before_formatting_would_be_invalid(self):
        """順序の逆転が実際に trust を壊すことを示す（対照実験）"""
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command()

        # 整形前の本文で打刻した状態を作る
        before = write_entry(path, dict(WRITE_METADATA))
        self.assertTrue(before['ok'], before['detail'])
        self.assertTrue(evaluate(self._read(path)).trust)

        # その後に整形が走るとハッシュが無効化される（戦略書 R4 の帰結）
        subprocess.run(build_format_argv(command, path), check=True)
        self.assertFalse(evaluate(self._read(path)).trust)

    def test_frontmatter_keys_are_written_before_formatting(self):
        """整形器が読む時点で既にフロントマターが書かれていること（手順 3 → 4）"""
        observer = '''\
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    text = f.read()
with open(path + ".seen", "w", encoding="utf-8") as f:
    f.write(text)
'''
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command(source=observer, name='observer.py')

        result = write_entry(path, dict(WRITE_METADATA), command)
        self.assertTrue(result['ok'], result['detail'])

        seen = self._read(path + '.seen')
        self.assertIn('title: テスト文書', seen)
        # 打刻は整形の後であり、整形器が見た時点では body_hash が無い
        self.assertNotIn('body_hash:', seen)


class TestWithoutFormatCommand(FmWriteTestBase):
    """--format-command 未指定でも正常終了し trust == true になること（§6.3）"""

    def test_no_format_command(self):
        path = self._write('docs/a.md', plain_document())

        result = write_entry(path, dict(WRITE_METADATA))

        self.assertTrue(result['ok'], result['detail'])
        self.assertFalse(result['formatted'])
        self.assertTrue(result['changed'])
        self.assertTrue(evaluate(self._read(path)).trust)

    def test_stale_body_hash_is_refreshed(self):
        path = self._write('docs/a.md', plain_document())
        write_entry(path, dict(WRITE_METADATA))

        # 本文だけを書き換えて陳腐化させる
        text = self._read(path)
        self._write('docs/a.md', text + "\n追記された段落。\n")
        self.assertFalse(evaluate(self._read(path)).trust)

        result = write_entry(path, dict(WRITE_METADATA))
        self.assertTrue(result['ok'], result['detail'])
        self.assertTrue(evaluate(self._read(path)).trust)


class TestIdempotency(FmWriteTestBase):
    """同一文書へ 2 回連続適用して内容が変化しないこと（戦略書 フェーズ 2）"""

    def test_idempotent_without_format_command(self):
        path = self._write('docs/a.md', plain_document())

        write_entry(path, dict(WRITE_METADATA))
        first = self._read(path)
        second_result = write_entry(path, dict(WRITE_METADATA))

        self.assertTrue(second_result['ok'], second_result['detail'])
        self.assertFalse(second_result['changed'])
        self.assertEqual(self._read(path), first)

    def test_idempotent_with_format_command(self):
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command()

        write_entry(path, dict(WRITE_METADATA), command)
        first = self._read(path)
        second_result = write_entry(path, dict(WRITE_METADATA), command)

        self.assertTrue(second_result['ok'], second_result['detail'])
        self.assertFalse(second_result['changed'])
        self.assertEqual(self._read(path), first)
        self.assertTrue(evaluate(first).trust)

    def test_idempotent_on_document_with_existing_frontmatter(self):
        path = self._write('docs/a.md', skill_like_document())

        write_entry(path, dict(WRITE_METADATA))
        first = self._read(path)
        write_entry(path, dict(WRITE_METADATA))

        self.assertEqual(self._read(path), first)


class TestExistingFrontmatterIsPreserved(FmWriteTestBase):
    """未知キーの保持と type の和集合更新（DES-008 §4.5 / §6.4）"""

    def test_unknown_keys_are_preserved(self):
        path = self._write('docs/a.md', skill_like_document())

        result = write_entry(path, dict(WRITE_METADATA))
        self.assertTrue(result['ok'], result['detail'])

        text = self._read(path)
        self.assertIn('name: foo-skill\n', text)
        self.assertIn('description: Foo をするスキル\n', text)
        self.assertIn('applicable_when:\n  - Foo をしたいとき\n', text)
        self.assertTrue(evaluate(text).trust)

    def test_type_is_merged_as_union(self):
        path = self._write('docs/a.md', temporary_feature_document())

        result = write_entry(path, dict(WRITE_METADATA))
        self.assertTrue(result['ok'], result['detail'])

        metadata = evaluate(self._read(path)).metadata
        self.assertEqual(metadata['type'], ['temporary-feature-requirement', MARKER])


class TestFormatCommandFailure(FmWriteTestBase):
    """整形コマンドの失敗は当該 entry の失敗であり打刻せず元へ戻す（戦略書 R4）"""

    def test_non_zero_exit_fails_the_entry_and_restores_the_document(self):
        original = plain_document()
        path = self._write('docs/a.md', original)
        command = self._formatter_command(source=FAILING_FORMATTER,
                                          name='failing_formatter.py')

        result = write_entry(path, dict(WRITE_METADATA), command)

        self.assertFalse(result['ok'])
        self.assertIsNone(result['error_code'])
        self.assertIn('exit 3', result['detail'])
        self.assertIsNone(result['body_hash'])
        self.assertFalse(result['changed'])

        # 手順 3 の書き込みは取り消され、書き込み前と完全に同一である
        text = self._read(path)
        self.assertEqual(text, original)
        self.assertNotIn('title: テスト文書', text)
        self.assertFalse(evaluate(text).trust)

    def test_trusted_document_is_restored_instead_of_staying_trusted(self):
        """既に body_hash を持つ文書で整形が失敗しても中途半端な更新を残さない。

        マージ規則は与えられたキーだけを差し替えるため、手順 2 では既存の
        body_hash が残る。整形器が本文を変えなければその値は依然として本文と
        一致するので、ロールバックしなければ「失敗を報告したのに fm_read が
        trust 真と判定する」状態になり、失敗した entry が転記対象になってしまう。
        """
        path = self._write('docs/a.md', plain_document())
        # まず正常に書き込んで body_hash を持つ信頼済み文書を作る
        self.assertTrue(write_entry(path, dict(WRITE_METADATA))['ok'])
        trusted = self._read(path)
        self.assertTrue(evaluate(trusted).trust)

        command = self._formatter_command(source=FAILING_FORMATTER,
                                          name='failing_formatter.py')
        result = write_entry(path, {'title': '更新後のタイトル'}, command)

        self.assertFalse(result['ok'])
        self.assertFalse(result['changed'])

        # 直前の状態へ戻っており、失敗した更新が残っていない
        text = self._read(path)
        self.assertEqual(text, trusted)
        self.assertNotIn('更新後のタイトル', text)

    def test_rollback_failure_keeps_changed_true(self):
        """復元にも失敗した場合は変更が残るため changed を真として報告する。

        detail だけに書いて changed を偽のままにすると、呼び出し側が
        「失敗したが原本は無傷」と誤って判断する。
        """
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command(source=FAILING_FORMATTER,
                                          name='failing_formatter.py')

        real_write = fm_write_module.write_text_atomic
        calls = []

        def flaky_write(target, text):
            calls.append(target)
            # 1 回目（手順 3）は成功させ、2 回目（復元）を失敗させる
            if len(calls) >= 2:
                raise OSError('復元用の書き込みを失敗させる')
            return real_write(target, text)

        fm_write_module.write_text_atomic = flaky_write
        try:
            result = write_entry(path, dict(WRITE_METADATA), command)
        finally:
            fm_write_module.write_text_atomic = real_write

        self.assertFalse(result['ok'])
        self.assertTrue(result['changed'])
        self.assertIn('復元に失敗', result['detail'])
        # 手順 3 の書き込みが実際に残っている（changed の報告と一致する）
        self.assertIn('title: テスト文書', self._read(path))

    def test_other_entries_are_still_processed(self):
        failing = self._write('docs/a.md', plain_document())
        ok_path = self._write('docs/b.md', plain_document())
        # a.md だけを失敗させたいので、対象ファイル名で分岐する整形器を使う
        selective = '''\
import os
import sys

path = sys.argv[1]
if os.path.basename(path) == "a.md":
    sys.exit(3)
'''
        command = self._formatter_command(source=selective, name='selective.py')

        status, results, counts = process_entries(
            self._entries(failing, ok_path), command
        )

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertFalse(results[0]['ok'])
        self.assertTrue(results[1]['ok'], results[1]['detail'])
        # 失敗した a.md はロールバックされるため changed に数えない
        self.assertEqual(counts, {'total': 2, 'written': 1, 'failed': 1,
                                  'changed': 1, 'formatted': 1})
        self.assertTrue(evaluate(self._read(ok_path)).trust)
        self.assertFalse(evaluate(self._read(failing)).has_frontmatter)

    def test_missing_executable_fails_the_entry(self):
        path = self._write('docs/a.md', plain_document())
        command = os.path.join(self.tmpdir, 'no_such_formatter') + ' {file}'

        result = write_entry(path, dict(WRITE_METADATA), command)

        self.assertFalse(result['ok'])
        self.assertIn('整形コマンドを実行できません', result['detail'])


class TestEntryFailures(FmWriteTestBase):
    """未閉鎖フロントマター・不正キー・不在の扱い（他 entry は処理を続ける）"""

    def test_unclosed_frontmatter_fails_the_entry(self):
        text = "---\ntype: doc-advisor\ntitle: 途中で終わる\n"
        path = self._write('docs/a.md', text)

        result = write_entry(path, dict(WRITE_METADATA))

        self.assertFalse(result['ok'])
        self.assertIsNone(result['error_code'])
        self.assertFalse(result['changed'])
        self.assertEqual(self._read(path), text, '原本は変更されない')

    def test_unowned_metadata_key_fails_the_entry(self):
        text = plain_document()
        path = self._write('docs/a.md', text)

        result = write_entry(path, {'title': 'x', 'name': 'foo'})

        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], ErrorCode.UNSUPPORTED_ARG)
        self.assertEqual(self._read(path), text)

    def test_body_hash_cannot_be_passed_as_metadata(self):
        text = plain_document()
        path = self._write('docs/a.md', text)

        result = write_entry(path, {'body_hash': 'sha256:' + '0' * 64})

        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], ErrorCode.UNSUPPORTED_ARG)
        self.assertEqual(self._read(path), text)

    def test_invalid_metadata_value_fails_the_entry(self):
        path = self._write('docs/a.md', plain_document())

        for metadata in ({'title': 3}, {'keywords': [1, 2]}, {'keywords': {'a': 'b'}}):
            with self.subTest(metadata=metadata):
                with self.assertRaises(ValueError):
                    validate_metadata_argument(metadata)
                result = write_entry(path, metadata)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_missing_file_is_reported_as_not_found(self):
        missing = os.path.join(self.tmpdir, 'missing.md')

        result = write_entry(missing, dict(WRITE_METADATA))

        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], ErrorCode.NOT_FOUND)

    def test_failures_do_not_stop_other_entries(self):
        bad = self._write('docs/bad.md', "---\ntype: doc-advisor\n")
        good = self._write('docs/good.md', plain_document())
        missing = os.path.join(self.tmpdir, 'missing.md')

        status, results, counts = process_entries(
            self._entries(bad, good, missing)
        )

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual([item['ok'] for item in results], [False, True, False])
        self.assertEqual(counts['written'], 1)
        self.assertEqual(counts['failed'], 2)
        self.assertTrue(evaluate(self._read(good)).trust)


class TestFormatCommandSafety(FmWriteTestBase):
    """整形コマンドはシェルを介さず、対象ファイルのみを置換する（戦略書 R5）"""

    def test_placeholder_is_required(self):
        with self.assertRaises(ValueError):
            validate_format_command('dprint fmt')

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_format_command('   ')

    def test_only_file_placeholder_is_expanded(self):
        argv = build_format_argv('fmt {file} {dir} {{file}}', '/tmp/a.md')
        self.assertEqual(argv, ['fmt', '/tmp/a.md', '{dir}', '{/tmp/a.md}'])

    def test_shell_metacharacters_are_not_interpreted(self):
        path = self._write('docs/a.md', plain_document())
        redirect = os.path.join(self.tmpdir, 'shell_was_used.txt')
        command = self._formatter_command(suffix=f' >{shlex.quote(redirect)}')

        result = write_entry(path, dict(WRITE_METADATA), command)

        self.assertTrue(result['ok'], result['detail'])
        self.assertFalse(os.path.exists(redirect),
                         'リダイレクトが解釈された（shell=True になっている）')

    def test_other_files_are_not_modified(self):
        target = self._write('docs/a.md', plain_document())
        other = self._write('docs/b.md', plain_document())
        other_text = self._read(other)
        command = self._formatter_command()

        result = write_entry(target, dict(WRITE_METADATA), command)

        self.assertTrue(result['ok'], result['detail'])
        self.assertEqual(self._read(other), other_text)


class TestAtomicWrite(FmWriteTestBase):
    """原子的書き込みの性質（パーミッション維持・一時ファイルを残さない）"""

    def test_permissions_are_preserved(self):
        for mode in (0o644, 0o600):
            with self.subTest(mode=oct(mode)):
                path = self._write(f'docs/{mode}.md', plain_document())
                os.chmod(path, mode)

                write_entry(path, dict(WRITE_METADATA))

                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), mode)

    def test_no_temporary_files_are_left(self):
        path = self._write('docs/a.md', plain_document())
        command = self._formatter_command()

        write_entry(path, dict(WRITE_METADATA), command)

        self.assertEqual(sorted(os.listdir(os.path.dirname(path))), ['a.md'])


class TestJsonContract(FmWriteTestBase):
    """status / error_code の値域と JSON 出力（DES-005 §8.1 / §8.2）"""

    def _run_main(self, entries, format_command=None):
        argv = ['--entries-json', json.dumps(entries)]
        if format_command is not None:
            argv += ['--format-command', format_command]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(argv)
        return code, json.loads(stream.getvalue().strip())

    def test_status_and_error_code_value_domains(self):
        good = self._write('docs/a.md', plain_document())
        bad = self._write('docs/bad.md', "---\ntype: doc-advisor\n")
        missing = os.path.join(self.tmpdir, 'missing.md')

        cases = [
            [{'path': good, 'metadata': WRITE_METADATA}],
            [{'path': bad, 'metadata': WRITE_METADATA},
             {'path': missing, 'metadata': WRITE_METADATA}],
            [],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                code, payload = self._run_main(entries)
                self.assertEqual(code, 0)
                self.assertIn(payload['status'], STATUSES)
                self.assertIsNone(payload['error_code'])
                for item in payload['results']:
                    self.assertTrue(
                        item['error_code'] is None
                        or item['error_code'] in ERROR_CODES
                    )

    def test_empty_entries_is_not_an_error(self):
        code, payload = self._run_main([])

        self.assertEqual(code, 0)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['results'], [])
        self.assertEqual(payload['counts']['total'], 0)

    def test_results_follow_input_order(self):
        first = self._write('docs/a.md', plain_document())
        second = self._write('docs/b.md', plain_document())

        code, payload = self._run_main([
            {'path': second, 'metadata': WRITE_METADATA},
            {'path': first, 'metadata': WRITE_METADATA},
        ])

        self.assertEqual([item['path'] for item in payload['results']],
                         [second, first])

    def test_metadata_is_optional(self):
        path = self._write('docs/a.md', plain_document())

        code, payload = self._run_main([{'path': path}])

        self.assertEqual(payload['status'], STATUS_OK)
        # type の和集合更新のみが行われ、5 フィールドは無いため trust は偽
        self.assertIn(f'type: {MARKER}', self._read(path))
        self.assertFalse(evaluate(self._read(path)).trust)

    def test_partial_returns_zero(self):
        missing = os.path.join(self.tmpdir, 'missing.md')

        code, payload = self._run_main([{'path': missing}])

        self.assertEqual(code, 0)
        self.assertEqual(payload['status'], STATUS_PARTIAL)

    def test_invalid_format_command_is_a_top_level_error(self):
        path = self._write('docs/a.md', plain_document())
        text = self._read(path)

        code, payload = self._run_main(
            [{'path': path, 'metadata': WRITE_METADATA}], 'dprint fmt'
        )

        self.assertEqual(code, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)
        self.assertEqual(self._read(path), text, '1 件も書き込まないこと')


class TestParseEntriesJson(unittest.TestCase):
    """--entries-json の構造検証（引数自体の不正は全体を落とす）"""

    def test_valid(self):
        raw = '[{"path": "docs/a.md", "metadata": {"title": "x"}}]'
        self.assertEqual(parse_entries_json(raw),
                         [('docs/a.md', {'title': 'x'})])

    def test_metadata_defaults_to_empty_dict(self):
        self.assertEqual(parse_entries_json('[{"path": "docs/a.md"}]'),
                         [('docs/a.md', {})])

    def test_accepts_empty_array(self):
        self.assertEqual(parse_entries_json('[]'), [])

    def test_rejects_malformed_structures(self):
        cases = (
            'not-json',
            '{}',
            '["docs/a.md"]',
            '[{"metadata": {}}]',
            '[{"path": "  "}]',
            '[{"path": 1}]',
            '[{"path": "docs/a.md", "metadata": []}]',
            '[{"path": "docs/a.md", "format": "x"}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_entries_json(raw)


class TestCliContract(FmWriteTestBase):
    """subprocess 経路の CLI 契約（stdout 単一 JSON / exit code）"""

    def _run_script(self, args):
        env = os.environ.copy()
        env['PYTHONPATH'] = FRONTMATTER_DIR
        return subprocess.run(
            [sys.executable, FM_WRITE_SCRIPT] + args,
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
        result = self._run_script(['--entries-json', '[]', '--scan'])
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
        result = self._run_script(['--help'])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_malformed_entries_json_is_reported_as_json(self):
        result = self._run_script(['--entries-json', '{'])
        payload = self._last_json_line(result.stdout)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.INVALID_PATH)

    def test_relative_paths_and_stdout_is_single_json(self):
        self._write('docs/a.md', plain_document())
        entries = json.dumps([{'path': 'docs/a.md', 'metadata': WRITE_METADATA}])

        result = self._run_script(['--entries-json', entries])
        lines = [ln for ln in result.stdout.strip().split('\n') if ln.strip()]
        payload = json.loads(lines[-1])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['results'][0]['path'], 'docs/a.md')
        self.assertTrue(
            evaluate(self._read(os.path.join(self.tmpdir, 'docs/a.md'))).trust
        )


if __name__ == '__main__':
    unittest.main()
