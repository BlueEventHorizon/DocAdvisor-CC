#!/usr/bin/env python3
"""
extract_codex_output.py のテスト

codex exec の -o 出力ファイル(lastmsg)と stdout ログから
Markdown レビュー本文を抽出するロジックを検証する。

実行:
  python3 -m unittest tests.forge.review.test_extract_codex_output -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# テスト対象モジュールへのパスを追加
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills' / 'review' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from extract_codex_output import (
    extract,
    extract_from_stdout,
    looks_like_review_markdown,
)

SCRIPT = str(SCRIPTS_DIR / 'extract_codex_output.py')


# ===========================================================================
# looks_like_review_markdown テスト
# ===========================================================================

class TestLooksLikeReviewMarkdown(unittest.TestCase):
    """Markdown 本文判定のテスト"""

    def test_empty_string_rejected(self):
        self.assertFalse(looks_like_review_markdown(''))

    def test_whitespace_only_rejected(self):
        self.assertFalse(looks_like_review_markdown('   \n\n  '))

    def test_section_heading_accepted(self):
        self.assertTrue(looks_like_review_markdown('### 🔴致命的問題\n\nsome text'))

    def test_h2_heading_accepted(self):
        self.assertTrue(looks_like_review_markdown('## レビュー結果\n本文'))

    def test_numbered_finding_accepted(self):
        self.assertTrue(looks_like_review_markdown(
            '1. 🔴 **問題**: 説明\n   - 箇所: x.py:1'
        ))

    def test_numbered_finding_without_marker_accepted(self):
        self.assertTrue(looks_like_review_markdown(
            '1. **問題**: 説明'
        ))

    def test_severity_marker_only_accepted(self):
        # 見出しがなくても severity マーカーがあれば Markdown 扱い
        self.assertTrue(looks_like_review_markdown(
            'レビュー完了しました 🔴 重大な問題が見つかりました'
        ))

    def test_ascii_label_accepted(self):
        # ASCII ラベル `[critical]/[major]/[minor]` があれば Markdown 扱い
        self.assertTrue(looks_like_review_markdown(
            '1. [critical] **問題**: 説明'
        ))
        self.assertTrue(looks_like_review_markdown(
            '1. [major] **問題**: 説明'
        ))
        self.assertTrue(looks_like_review_markdown(
            '1. [minor] **提案**: 説明'
        ))

    def test_plain_short_message_rejected(self):
        self.assertFalse(looks_like_review_markdown('レビュー完了'))


# ===========================================================================
# extract_from_stdout テスト
# ===========================================================================

class TestExtractFromStdout(unittest.TestCase):
    """stdout ログからの抽出テスト"""

    def test_empty_stdout_returns_empty(self):
        self.assertEqual(extract_from_stdout(''), '')

    def test_stdout_without_markdown_returns_empty(self):
        stdout = """\
[2024-01-01T12:00:00] OpenAI Codex v1.0.0
workdir: /tmp/project
model: gpt-4

user instructions:
review this file
"""
        self.assertEqual(extract_from_stdout(stdout), '')

    def test_stdout_with_ascii_labels_extracts_body(self):
        """stdout に ASCII ラベル形式の Markdown 本文が混ざっていれば抽出される。

        新方式(ラベル primary)の検証: 絵文字に依存しない anchor 検出。"""
        stdout = """\
[2024-01-01T12:00:00] OpenAI Codex v1.0.0
workdir: /tmp/project
model: gpt-4

[2024-01-01T12:00:05] codex

### Critical / 致命的問題

1. [critical] **境界値エラー**: 配列範囲外アクセス
   - 箇所: utils.py:42

### Major / 品質問題

（なし）

### Minor / 改善提案

1. [minor] **ドキュメント不足**: コメントを追加

tokens used: 1234
"""
        body = extract_from_stdout(stdout)
        self.assertIn('### Critical / 致命的問題', body)
        self.assertIn('境界値エラー', body)
        self.assertIn('[critical]', body)
        self.assertIn('ドキュメント不足', body)
        self.assertNotIn('tokens used: 1234', body)

    def test_stdout_with_markdown_extracts_body(self):
        """stdout に Markdown 本文が混ざっていれば抽出される。"""
        stdout = """\
[2024-01-01T12:00:00] OpenAI Codex v1.0.0
workdir: /tmp/project
model: gpt-4

[2024-01-01T12:00:05] codex

### 🔴致命的問題

1. 🔴 **境界値エラー**: 配列範囲外アクセス
   - 箇所: utils.py:42

### 🟡品質問題

（なし）

### 🟢改善提案

1. 🟢 **ドキュメント不足**: コメントを追加

tokens used: 1234
"""
        body = extract_from_stdout(stdout)
        self.assertIn('### 🔴致命的問題', body)
        self.assertIn('境界値エラー', body)
        self.assertIn('ドキュメント不足', body)
        # tokens used メタ情報は除外される
        self.assertNotIn('tokens used: 1234', body)


# ===========================================================================
# extract 統合テスト(lastmsg 優先 / stdout フォールバック)
# ===========================================================================

class TestExtract(unittest.TestCase):
    """lastmsg / stdout 組み合わせの統合テスト"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = self.tmpdir / name
        path.write_text(content, encoding='utf-8')
        return path

    def test_lastmsg_with_markdown_adopted_directly(self):
        """lastmsg が Markdown 本文を含む場合はそれをそのまま採用する。"""
        lastmsg = self._write('lastmsg.txt', """\
### 🔴致命的問題

1. 🔴 **問題A**: 説明
   - 箇所: x.py:1

### 🟡品質問題

（なし）

### 🟢改善提案

（なし）
""")
        stdout = self._write('stdout.log', 'session metadata only')

        body = extract(str(stdout), str(lastmsg))
        self.assertIn('### 🔴致命的問題', body)
        self.assertIn('問題A', body)

    def test_lastmsg_short_falls_back_to_stdout(self):
        """lastmsg が短い完了メッセージだけの場合は stdout から抽出する。

        これが `-o` 上書きバグの典型パターン: codex が apply_patch で書いた
        本文を最終メッセージ(短い完了報告)で上書きしてしまうケース。"""
        lastmsg = self._write('lastmsg.txt', 'レビューが完了しました。\n')
        stdout = self._write('stdout.log', """\
[2024-01-01T12:00:00] session start

### 🔴致命的問題

1. 🔴 **本体の指摘**: stdout に含まれる詳細なレビュー
   - 箇所: a.py:1

### 🟡品質問題

（なし）

### 🟢改善提案

（なし）

tokens used: 500
""")

        body = extract(str(stdout), str(lastmsg))
        self.assertIn('本体の指摘', body)
        self.assertIn('### 🔴致命的問題', body)

    def test_lastmsg_with_ascii_labels_adopted_directly(self):
        """lastmsg が ASCII ラベル形式の Markdown 本文を含む場合、直接採用される。"""
        lastmsg = self._write('lastmsg.txt', """\
### Critical / 致命的問題

1. [critical] **問題A**: 説明
   - 箇所: x.py:1

### Major / 品質問題

（なし）

### Minor / 改善提案

（なし）
""")
        stdout = self._write('stdout.log', 'session metadata only')

        body = extract(str(stdout), str(lastmsg))
        self.assertIn('[critical]', body)
        self.assertIn('問題A', body)

    def test_neither_has_usable_content_returns_empty(self):
        """lastmsg も stdout も有効な Markdown を含まない場合は空を返す。"""
        lastmsg = self._write('lastmsg.txt', 'done')
        stdout = self._write('stdout.log', 'no content here\njust meta logs\n')

        body = extract(str(stdout), str(lastmsg))
        self.assertEqual(body, '')

    def test_missing_files_return_empty(self):
        """lastmsg / stdout ファイルが存在しない場合は空を返す。"""
        body = extract(str(self.tmpdir / 'nonexistent.log'),
                       str(self.tmpdir / 'nonexistent.txt'))
        self.assertEqual(body, '')


# ===========================================================================
# CLI テスト
# ===========================================================================

class TestExtractCodexOutputCli(unittest.TestCase):
    """CLI インターフェースのテスト"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_writes_output_from_lastmsg(self):
        """lastmsg が有効な場合、output に Markdown が書き出され rc=0。"""
        lastmsg = self.tmpdir / 'lastmsg.txt'
        lastmsg.write_text(
            '### 🔴致命的問題\n\n1. 🔴 **問題**: 説明\n   - 箇所: x.py:1\n',
            encoding='utf-8',
        )
        stdout_file = self.tmpdir / 'stdout.log'
        stdout_file.write_text('', encoding='utf-8')
        output = self.tmpdir / 'out.md'

        result = subprocess.run(
            [sys.executable, SCRIPT,
             '--stdout', str(stdout_file),
             '--lastmsg', str(lastmsg),
             '--output', str(output)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())
        content = output.read_text(encoding='utf-8')
        self.assertIn('### 🔴致命的問題', content)
        self.assertIn('問題', content)

    def test_cli_empty_output_returns_rc_1(self):
        """有効な Markdown を見つけられない場合 output は空 + rc=1。"""
        lastmsg = self.tmpdir / 'lastmsg.txt'
        lastmsg.write_text('done', encoding='utf-8')
        stdout_file = self.tmpdir / 'stdout.log'
        stdout_file.write_text('meta only', encoding='utf-8')
        output = self.tmpdir / 'out.md'

        result = subprocess.run(
            [sys.executable, SCRIPT,
             '--stdout', str(stdout_file),
             '--lastmsg', str(lastmsg),
             '--output', str(output)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        # output は空ファイルとして作成される(呼び出し元の test -s で検知可能)
        self.assertTrue(output.exists())
        self.assertEqual(output.read_text(encoding='utf-8'), '')


if __name__ == '__main__':
    unittest.main()
