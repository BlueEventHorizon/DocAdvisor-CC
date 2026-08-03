#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fm_to_pending.py のユニットテスト（DES-008 §5.1 / §5.3 / §6.1 / §6.2）。

テスト対象:
- 転記した pending が write_pending.write_entry_yaml の出力と**バイト一致**すること
- 信頼できるフロントマターを持つ文書の pending が status: completed になること
- 転記由来の pending が _meta.extracted_by: frontmatter を持ち、toc.yaml には
  extracted_by が出ないこと（DES-008 §8.2）
- スキーマ違反を含む文書の pending が未完了のまま**バイト単位で無変更**で残ること
- フロントマターを持たない文書の pending も無変更で残ること（warning なし）
- 既に completed の pending を再処理しないこと
- _meta.source_file が欠落した pending を壊さないこと
- 読み取り失敗を含む場合に status: partial になり、他の pending の処理は続くこと
- 列挙規則が merge_toc.load_completed_pendings と揃っていること（隠しファイル除外・昇順）
- 転記由来のエントリが merge_toc 経由で validate_toc を通ること（戦略書 R2 の回帰防止）

テスト方針:
- 判定・転記は in-process import（updated_at を固定してバイト比較する）
- CLI 契約（引数エラー・exit code・stdout 単一 JSON）は subprocess で確認する
- merge との統合は subprocess（prepare の pending テンプレート → 転記 → merge）
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
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SCRIPTS_DIR = os.path.join(REPO_ROOT, 'plugins', 'doc-advisor', 'scripts')
FRONTMATTER_DIR = os.path.join(SCRIPTS_DIR, 'frontmatter')
for _path in (FRONTMATTER_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fm_core import MARKER, compute_body_hash
from fm_read import STATUS_ERROR, STATUS_OK, STATUS_PARTIAL, ErrorCode
from fm_to_pending import (
    ACTION_ALREADY_COMPLETED,
    ACTION_FAILED,
    ACTION_LEFT_PENDING,
    ACTION_TRANSCRIBED,
    build_pending_text,
    list_pendings,
    main,
    process_pending,
    process_work_dir,
    read_pending_meta,
)

# 出力書式の正本（バイト一致の期待値生成に使う）
from write_pending import write_entry_yaml
# prepare が作る pending テンプレートと work file 名（実際の入力に合わせる）
from prepare_toc import PENDING_TEMPLATE, get_yaml_filename
from toc_store import WORK_DIRNAME, resolve_store_dir

FM_TO_PENDING_SCRIPT = os.path.join(FRONTMATTER_DIR, 'fm_to_pending.py')
MERGE_SCRIPT = os.path.join(SCRIPTS_DIR, 'merge_toc.py')

BODY = "# Title\n\nSome body text.\n"

FIXED_TIMESTAMP = "2026-08-02T00:00:00Z"

# 転記に用いるメタデータ（yaml_escape が引用符を付ける値を意図的に混ぜる）
TRUSTED_METADATA = {
    'title': 'Foo: Bar 設計',
    'purpose': 'Foo の役割を定義する文書',
    'content_details': ['項目 A', '項目 B'],
    'applicable_tasks': ['タスク A'],
    'keywords': ['Foo', 'true', '123'],
}


def _render_frontmatter(metadata, body, *, type_value=MARKER, body_hash=None):
    """任意のメタデータからフロントマター付き文書を組み立てる。

    Args:
        metadata: フロントマターに書くキー → 値（文字列 / 文字列の list）
        body: 本文
        type_value: type に書く値
        body_hash: body_hash に書く値（省略時は body から算出した正しい値）

    Returns:
        str: 文書全体
    """
    lines = ["---", f"type: {type_value}"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f'  - "{item}"')
        else:
            lines.append(f'{key}: "{value}"')
    lines.append(
        f"body_hash: {body_hash if body_hash else compute_body_hash(body)}"
    )
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def trusted_document(metadata=None, body=BODY):
    """信頼判定が真になる文書を返す。"""
    return _render_frontmatter(metadata or TRUSTED_METADATA, body)


def violating_document(body=BODY):
    """マーカーは持つがスキーマに適合しない文書を返す（§5.3 の warning 対象）。

    content_details を配列ではなく文字列にする（DES-008 §5.1 が転記前に弾く例）。
    """
    metadata = dict(TRUSTED_METADATA)
    metadata['content_details'] = 'これは配列ではない'
    return _render_frontmatter(metadata, body)


class FmToPendingTestBase(unittest.TestCase):
    """一時 project root に文書と pending を配置する共通セットアップ。"""

    KEY = 'rules'

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.project_root = Path(self.tmpdir)
        (self.project_root / '.git').mkdir(exist_ok=True)
        self.store_dir = resolve_store_dir(self.KEY, project_root=self.project_root)
        self.work_dir = self.store_dir / WORK_DIRNAME
        self.work_dir.mkdir(parents=True, exist_ok=True)
        # _meta.source_file は project-root-relative であり、fm_to_pending は
        # cwd 起点で解決する（project root の解決を行わない / DES-008 §6.1）。
        # in-process 実行のため cwd を project root に合わせる。
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)

    def tearDown(self):
        os.chdir(self._original_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_doc(self, rel_path, text):
        """文書を配置し、project-root-relative パスを返す。"""
        full = self.project_root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding='utf-8')
        return rel_path

    def _write_pending(self, source_file):
        """prepare_toc と同一のテンプレート・命名で pending を作る。"""
        path = self.work_dir / get_yaml_filename(source_file)
        path.write_text(
            PENDING_TEMPLATE.format(source_file=source_file), encoding='utf-8'
        )
        return path

    def _abs(self, rel_path):
        return str(self.project_root / rel_path)


# ===========================================================================
# 書式のバイト一致（write_pending.write_entry_yaml が正本）
# ===========================================================================

class TestByteIdenticalOutput(FmToPendingTestBase):
    """転記の出力が write_pending.write_entry_yaml とバイト一致すること"""

    def _expected_bytes(self, source_file, metadata):
        """write_pending.write_entry_yaml に同じ値を渡した出力を得る。"""
        expected_path = self.project_root / 'expected.yaml'
        # extracted_by は転記経路の値を明示的に渡す。値を除外して比較すると
        # 書式（キーの位置・インデント・エスケープ）の一致検証が緩むため、
        # write_entry_yaml 側が meta 経由で値を受ける形にしてある（DES-008 §8.2）。
        meta = {
            'source_file': source_file,
            'status': 'completed',
            'updated_at': FIXED_TIMESTAMP,
            'extracted_by': 'frontmatter',
        }
        self.assertTrue(write_entry_yaml(str(expected_path), meta, metadata))
        return expected_path.read_bytes()

    def test_build_pending_text_matches_write_entry_yaml(self):
        """build_pending_text の出力が正本とバイト一致する（引用符付き値を含む）"""
        source_file = 'docs/a.md'
        text = build_pending_text(source_file, TRUSTED_METADATA, FIXED_TIMESTAMP)
        self.assertEqual(
            text.encode('utf-8'), self._expected_bytes(source_file, TRUSTED_METADATA)
        )

    def test_transcribed_file_matches_write_entry_yaml(self):
        """転記後の pending ファイルが正本とバイト一致する"""
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)
        self.assertTrue(result['ok'])
        # source_file は pending から読んだ値をそのまま書く
        self.assertEqual(
            pending.read_bytes(), self._expected_bytes(rel, TRUSTED_METADATA)
        )

    def test_empty_arrays_emit_key_line_only(self):
        """要素 0 件の配列でもキー行だけが出る（正本と同じ挙動）"""
        metadata = {
            'title': 'T', 'purpose': 'P',
            'content_details': [], 'applicable_tasks': [], 'keywords': [],
        }
        text = build_pending_text('docs/a.md', metadata, FIXED_TIMESTAMP)
        self.assertIn('content_details:\napplicable_tasks:\nkeywords:\n', text)
        self.assertEqual(
            text.encode('utf-8'), self._expected_bytes('docs/a.md', metadata)
        )

    def test_single_trailing_newline(self):
        """末尾改行はちょうど 1 つ"""
        text = build_pending_text('docs/a.md', TRUSTED_METADATA, FIXED_TIMESTAMP)
        self.assertTrue(text.endswith('\n'))
        self.assertFalse(text.endswith('\n\n'))

    def test_no_claimed_at_or_error_message(self):
        """claimed_at / error_message は書かない（_meta を作り直す）"""
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)
        # prepare の出力に claim と error を後付けした状態から転記する
        pending.write_text(
            pending.read_text(encoding='utf-8').replace(
                '  status: pending\n',
                '  status: pending\n  claimed_at: 2026-08-02T00:00:00Z\n'
                '  error_message: "previous failure"\n',
            ),
            encoding='utf-8',
        )

        process_pending(pending, updated_at=FIXED_TIMESTAMP)
        text = pending.read_text(encoding='utf-8')
        self.assertNotIn('claimed_at', text)
        self.assertNotIn('error_message', text)


# ===========================================================================
# 転記とスキップ（DES-008 §5.1 / §5.2 / §5.3）
# ===========================================================================

class TestTranscription(FmToPendingTestBase):
    """信頼できるものだけを completed にすること"""

    def test_trusted_becomes_completed(self):
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_TRANSCRIBED)
        self.assertTrue(result['trust'])
        self.assertFalse(result['warn'])
        meta = read_pending_meta(pending.read_text(encoding='utf-8'))
        self.assertEqual(meta['status'], 'completed')
        self.assertEqual(meta['source_file'], rel)
        self.assertEqual(meta['updated_at'], FIXED_TIMESTAMP)

    def test_extracted_by_records_frontmatter_provenance(self):
        """転記経路の pending は _meta.extracted_by: frontmatter を持つ（DES-008 §8.2）"""
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)

        process_pending(pending, updated_at=FIXED_TIMESTAMP)

        text = pending.read_text(encoding='utf-8')
        self.assertIn('  extracted_by: frontmatter\n', text)
        self.assertEqual(
            read_pending_meta(text)['extracted_by'], 'frontmatter'
        )

    def test_transcribed_content_comes_from_frontmatter(self):
        """本文フィールドはフロントマター由来の値で書き直される"""
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)
        process_pending(pending, updated_at=FIXED_TIMESTAMP)

        text = pending.read_text(encoding='utf-8')
        self.assertIn('purpose: Foo の役割を定義する文書', text)
        self.assertIn('  - 項目 A', text)
        self.assertNotIn('title: null', text)


class TestUntrustedLeftUnchanged(FmToPendingTestBase):
    """信頼できないものは pending をバイト単位で無変更で残すこと"""

    def test_schema_violation_left_unchanged(self):
        rel = self._write_doc('docs/a.md', violating_document())
        pending = self._write_pending(rel)
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_LEFT_PENDING)
        self.assertFalse(result['trust'])
        self.assertTrue(result['warn'], "マーカー有りの違反は warning 対象（§5.3）")
        self.assertEqual(pending.read_bytes(), before)
        self.assertEqual(
            read_pending_meta(pending.read_text(encoding='utf-8'))['status'], 'pending'
        )

    def test_body_hash_mismatch_left_unchanged(self):
        """フロントマターが本文から取り残された文書も転記しない"""
        rel = self._write_doc(
            'docs/a.md',
            _render_frontmatter(
                TRUSTED_METADATA, BODY, body_hash='sha256:' + '0' * 64
            ),
        )
        pending = self._write_pending(rel)
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_LEFT_PENDING)
        self.assertTrue(result['warn'])
        self.assertEqual(pending.read_bytes(), before)

    def test_no_frontmatter_left_unchanged_without_warning(self):
        """フロントマター無しは正常な対象外であり warning を出さない"""
        rel = self._write_doc('docs/a.md', BODY)
        pending = self._write_pending(rel)
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_LEFT_PENDING)
        self.assertFalse(result['warn'])
        self.assertEqual(pending.read_bytes(), before)

    def test_other_tool_marker_left_unchanged_without_warning(self):
        """type に doc-advisor を含まない文書も正常な対象外"""
        rel = self._write_doc(
            'docs/a.md',
            _render_frontmatter(
                TRUSTED_METADATA, BODY, type_value='temporary-feature-design'
            ),
        )
        pending = self._write_pending(rel)
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_LEFT_PENDING)
        self.assertFalse(result['warn'])
        self.assertEqual(pending.read_bytes(), before)


class TestSkipAndFailure(FmToPendingTestBase):
    """再処理の禁止と失敗の扱い"""

    def test_already_completed_not_reprocessed(self):
        """既に completed の pending は再処理しない（--force なしの write_pending と同様）"""
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)
        # AI 抽出で既に completed になった pending を正本（write_entry_yaml）で作る。
        # build_pending_text は転記由来（extracted_by: frontmatter）を書くため、
        # AI 抽出済みの代用にはならない。
        write_entry_yaml(
            str(pending),
            {
                'source_file': rel,
                'status': 'completed',
                'updated_at': "2026-01-01T00:00:00Z",
                'extracted_by': 'ai',
            },
            {
                'title': 'AI 抽出のタイトル', 'purpose': 'AI 抽出の purpose',
                'content_details': ['AI 1'], 'applicable_tasks': ['AI T'],
                'keywords': ['AI'],
            },
        )
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertEqual(result['action'], ACTION_ALREADY_COMPLETED)
        self.assertTrue(result['ok'])
        self.assertEqual(pending.read_bytes(), before)

    def test_missing_source_file_key_is_not_broken(self):
        """_meta.source_file が欠落した pending を壊さない"""
        pending = self.work_dir / 'broken.yaml'
        pending.write_text(
            "_meta:\n  status: pending\n  updated_at: null\n\n"
            "title: null\npurpose: null\ncontent_details: []\n"
            "applicable_tasks: []\nkeywords: []\n",
            encoding='utf-8',
        )
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertFalse(result['ok'])
        self.assertEqual(result['action'], ACTION_FAILED)
        self.assertIn('source_file', result['detail'])
        self.assertEqual(pending.read_bytes(), before)

    def test_source_file_not_found_is_failure(self):
        pending = self._write_pending('docs/missing.md')
        before = pending.read_bytes()

        result = process_pending(pending, updated_at=FIXED_TIMESTAMP)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], ErrorCode.NOT_FOUND)
        self.assertEqual(pending.read_bytes(), before)


class TestProcessWorkDir(FmToPendingTestBase):
    """work-dir 一括処理（列挙規則・status・counts / 判断事項 D1）"""

    def test_mixed_documents(self):
        """信頼できるもののみ転記され、他は無変更で残る"""
        trusted = self._write_doc('docs/trusted.md', trusted_document())
        violating = self._write_doc('docs/violating.md', violating_document())
        plain = self._write_doc('docs/plain.md', BODY)
        pendings = {
            name: self._write_pending(name) for name in (trusted, violating, plain)
        }
        before = {name: path.read_bytes() for name, path in pendings.items()}

        status, results, counts, warnings = process_work_dir(
            self.work_dir, updated_at=FIXED_TIMESTAMP
        )

        self.assertEqual(status, STATUS_OK)
        self.assertEqual(counts['total'], 3)
        self.assertEqual(counts['transcribed'], 1)
        self.assertEqual(counts['left_pending'], 2)
        self.assertEqual(counts['failed'], 0)
        self.assertEqual(counts['warned'], 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn(violating, warnings[0])

        self.assertNotEqual(pendings[trusted].read_bytes(), before[trusted])
        self.assertEqual(pendings[violating].read_bytes(), before[violating])
        self.assertEqual(pendings[plain].read_bytes(), before[plain])

    def test_partial_on_read_failure_and_continues(self):
        """読み取り失敗があっても他の pending の処理は続き status は partial"""
        trusted = self._write_doc('docs/trusted.md', trusted_document())
        trusted_pending = self._write_pending(trusted)
        self._write_pending('docs/missing.md')

        status, results, counts, _warnings = process_work_dir(
            self.work_dir, updated_at=FIXED_TIMESTAMP
        )

        self.assertEqual(status, STATUS_PARTIAL)
        self.assertEqual(counts['failed'], 1)
        self.assertEqual(counts['transcribed'], 1)
        self.assertEqual(
            read_pending_meta(trusted_pending.read_text(encoding='utf-8'))['status'],
            'completed',
        )

    def test_listing_excludes_hidden_and_is_sorted(self):
        """列挙規則が merge_toc.load_completed_pendings と揃っている"""
        (self.work_dir / '.deleted.json').write_text('[]', encoding='utf-8')
        (self.work_dir / '.toc_checksums_pending.yaml').write_text(
            'checksums:\n', encoding='utf-8'
        )
        (self.work_dir / 'b.yaml').write_text('_meta:\n', encoding='utf-8')
        (self.work_dir / 'a.yaml').write_text('_meta:\n', encoding='utf-8')
        (self.work_dir / 'c.txt').write_text('x', encoding='utf-8')

        names = [path.name for path in list_pendings(self.work_dir)]
        self.assertEqual(names, ['a.yaml', 'b.yaml'])

    def test_missing_work_dir_is_zero_entries(self):
        """work-dir 不在は 0 件として扱う（merge_toc と同じ）"""
        status, results, counts, warnings = process_work_dir(
            self.project_root / 'nonexistent'
        )
        self.assertEqual(status, STATUS_OK)
        self.assertEqual(results, [])
        self.assertEqual(counts['total'], 0)
        self.assertEqual(warnings, [])

    def test_empty_work_dir_is_not_error(self):
        status, _results, counts, _warnings = process_work_dir(self.work_dir)
        self.assertEqual(status, STATUS_OK)
        self.assertEqual(counts['total'], 0)


# ===========================================================================
# _meta リーダ（往復一致 / DES-008 §6.1: parse_simple_yaml を import しない）
# ===========================================================================

class TestReadPendingMeta(unittest.TestCase):
    """最小リーダが write_pending の出力と往復一致すること"""

    def test_round_trip_with_escaped_source_file(self):
        source_file = 'docs/foo: bar.md'
        text = build_pending_text(source_file, TRUSTED_METADATA, FIXED_TIMESTAMP)
        self.assertIn('source_file: "docs/foo: bar.md"', text)
        meta = read_pending_meta(text)
        self.assertEqual(meta['source_file'], source_file)
        self.assertEqual(meta['status'], 'completed')

    def test_reads_prepare_template(self):
        meta = read_pending_meta(PENDING_TEMPLATE.format(source_file='docs/a.md'))
        self.assertEqual(meta['source_file'], 'docs/a.md')
        self.assertEqual(meta['status'], 'pending')

    def test_ignores_body_fields(self):
        """_meta 外の最上位キーは読まない（本文フィールドは転記に不要）"""
        meta = read_pending_meta(
            "_meta:\n  source_file: docs/a.md\n  status: pending\n\n"
            "title: T\ncontent_details:\n  - x\n"
        )
        self.assertEqual(set(meta), {'source_file', 'status'})


# ===========================================================================
# CLI 契約（DES-005 §8.1）
# ===========================================================================

class TestCli(FmToPendingTestBase):
    """stdout 単一 JSON / exit code / 引数エラー"""

    def _run(self, *args):
        env = os.environ.copy()
        env['PYTHONPATH'] = FRONTMATTER_DIR
        return subprocess.run(
            [sys.executable, FM_TO_PENDING_SCRIPT] + list(args),
            capture_output=True, text=True, cwd=str(self.project_root), env=env,
        )

    def _payload(self, proc):
        out = proc.stdout.strip()
        self.assertTrue(out, f"stdout empty; stderr: {proc.stderr}")
        self.assertEqual(len(out.split('\n')), 1, f"stdout must be single JSON: {out}")
        return json.loads(out)

    def test_cli_transcribes(self):
        rel = self._write_doc('docs/a.md', trusted_document())
        pending = self._write_pending(rel)

        proc = self._run('--work-dir', str(self.work_dir))

        self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
        payload = self._payload(proc)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertIsNone(payload['error_code'])
        self.assertEqual(payload['counts']['transcribed'], 1)
        self.assertEqual(payload['results'][0]['action'], ACTION_TRANSCRIBED)
        self.assertEqual(
            read_pending_meta(pending.read_text(encoding='utf-8'))['status'],
            'completed',
        )

    def test_cli_missing_work_dir_argument(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 1)
        payload = self._payload(proc)
        self.assertEqual(payload['status'], STATUS_ERROR)
        self.assertEqual(payload['error_code'], ErrorCode.UNSUPPORTED_ARG)

    def test_cli_rejects_out_option(self):
        """--out は実装しない（--work-dir のみ）"""
        proc = self._run('--out', 'x.yaml')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self._payload(proc)['status'], STATUS_ERROR)

    def test_cli_nonexistent_work_dir_is_ok(self):
        proc = self._run('--work-dir', str(self.project_root / 'nope'))
        self.assertEqual(proc.returncode, 0)
        payload = self._payload(proc)
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['counts']['total'], 0)

    def test_main_in_process_partial(self):
        rel = self._write_doc('docs/a.md', trusted_document())
        self._write_pending(rel)
        self._write_pending('docs/missing.md')

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(['--work-dir', str(self.work_dir)])

        self.assertEqual(code, 0)
        payload = json.loads(stream.getvalue().strip())
        self.assertEqual(payload['status'], STATUS_PARTIAL)


# ===========================================================================
# merge との統合（戦略書 R2: validate_toc のロールバック回帰防止）
# ===========================================================================

class TestMergeIntegration(FmToPendingTestBase):
    """fm_to_pending → merge_toc → validate_toc が通ること"""

    def _run_script(self, script, *args, scripts_dir=SCRIPTS_DIR):
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(self.project_root)
        env['PYTHONPATH'] = scripts_dir
        return subprocess.run(
            [sys.executable, script] + list(args),
            capture_output=True, text=True, cwd=str(self.project_root), env=env,
        )

    def test_transcribed_entry_passes_validate_toc(self):
        rel = self._write_doc('docs/a.md', trusted_document())
        self._write_pending(rel)

        transcribe = self._run_script(
            FM_TO_PENDING_SCRIPT, '--work-dir', str(self.work_dir),
            scripts_dir=FRONTMATTER_DIR,
        )
        self.assertEqual(transcribe.returncode, 0, f"stderr: {transcribe.stderr}")

        merge = self._run_script(MERGE_SCRIPT, '--key', self.KEY)
        # merge_toc は成功時に validate_toc を通しており、失敗すれば
        # toc.yaml をロールバックして非ゼロで終了する
        self.assertEqual(merge.returncode, 0, f"stderr: {merge.stderr}")
        payload = json.loads(merge.stdout.strip())
        self.assertEqual(payload['status'], STATUS_OK)
        self.assertEqual(payload['counts']['added'], 1)

        toc = (self.store_dir / 'toc.yaml').read_text(encoding='utf-8')
        self.assertIn('docs/a.md:', toc)
        self.assertIn('Foo: Bar 設計', toc)
        self.assertNotIn(
            'extracted_by', toc,
            "extracted_by は pending の来歴であり toc.yaml には書き出さない（DES-008 §8.2）",
        )
        self.assertFalse(self.work_dir.exists(), ".toc_work は merge 成功で除去される")

    def test_untrusted_pending_blocks_merge_until_filled(self):
        """転記されなかった pending は completed でないため merge に載らない"""
        rel = self._write_doc('docs/a.md', violating_document())
        self._write_pending(rel)

        transcribe = self._run_script(
            FM_TO_PENDING_SCRIPT, '--work-dir', str(self.work_dir),
            scripts_dir=FRONTMATTER_DIR,
        )
        self.assertEqual(transcribe.returncode, 0)
        payload = json.loads(transcribe.stdout.strip())
        self.assertEqual(payload['counts']['transcribed'], 0)
        self.assertEqual(len(payload['warnings']), 1)

        merge = self._run_script(MERGE_SCRIPT, '--key', self.KEY)
        merge_payload = json.loads(merge.stdout.strip())
        self.assertEqual(merge_payload['counts']['added'], 0)


if __name__ == '__main__':
    unittest.main()
