#!/usr/bin/env python3
"""
検索系 query-docs の dispatcher + read-only worker 隔離 / 制約テスト

ADR-002 改訂版 (docs/specs/base/design/ADR-002_query_skill_subagent_isolation.md §F)
で採択された新構成（継承型 dispatcher + read-only カスタム Agent）が、対象ファイルに
反映されていることを検証する:

1. query-docs が継承型 SKILL として定義され、`context: fork` を持たない
2. query-docs が dispatcher 責務に限定され（query-worker を Agent で起動する記述を持ち）、
   自前で ToC 全エントリの関連判断を行う記述を持たない
3. query-worker カスタム Agent が read-only 制約・引数解釈ガード・`Required documents:`
   出力契約を持つ
4. query-docs / query-worker が `allowed-tools` を物理 deny と誤認させる記述を持たない

実行:
  python3 -m unittest tests.skills.test_query_skill_isolation -v
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# 配布物（skills / agents / workflows / formats）は plugins/doc-advisor/ 配下に置く。
PLUGIN_ROOT = REPO_ROOT / 'plugins' / 'doc-advisor'

# 継承型 dispatcher SKILL（ADR-002 改訂版: context: fork を持たない）
QUERY_DOCS_SKILL = PLUGIN_ROOT / 'skills' / 'query-docs' / 'SKILL.md'
# read-only 検索 worker（カスタム Agent）
QUERY_WORKER_AGENT = PLUGIN_ROOT / 'agents' / 'query-worker.md'


def _split_frontmatter_body(path: Path):
    """frontmatter 文字列と本文に分割する。"""
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        raise AssertionError(f"{path} に YAML frontmatter がない")
    end = text.find('\n---', 3)
    if end == -1:
        raise AssertionError(f"{path} の frontmatter が閉じていない")
    fm = text[3:end]
    body = text[end + 4:]
    return fm, body


class TestQueryDocsIsInheritedDispatcher(unittest.TestCase):
    """query-docs が継承型 dispatcher として定義されていることを検証 (ADR-002 §A / §F-1,2)"""

    def test_no_context_fork(self):
        """継承型なので frontmatter に `context: fork` を持たない (§F-1)"""
        fm, _ = _split_frontmatter_body(QUERY_DOCS_SKILL)
        self.assertNotRegex(
            fm,
            r'(?m)^context:\s*fork\s*$',
            "query-docs は継承型 dispatcher のため `context: fork` を持ってはならない "
            "(ADR-002 改訂版 §A 違反)"
        )

    def test_launches_query_worker_via_agent(self):
        """dispatcher は query-worker カスタム Agent を起動する記述を持つ (§F-2)"""
        fm, body = _split_frontmatter_body(QUERY_DOCS_SKILL)
        # Agent ツールを allowed-tools に持つ
        self.assertRegex(
            fm,
            r'(?m)^allowed-tools:.*\bAgent\b',
            "query-docs dispatcher の allowed-tools に `Agent` がない "
            "(worker 起動に必要 / ADR-002 §B)"
        )
        # worker の subagent_type を明記している
        self.assertIn(
            'doc-advisor:query-worker', body,
            "query-docs dispatcher が `doc-advisor:query-worker` を起動する記述を持たない "
            "(ADR-002 §B 違反)"
        )

    def test_dispatcher_does_not_self_judge_toc(self):
        """dispatcher 自身は ToC 全エントリ判断・get_toc 実行を行わない旨を明記 (§F-2)"""
        _, body = _split_frontmatter_body(QUERY_DOCS_SKILL)
        self.assertIn(
            'dispatcher', body,
            "query-docs に dispatcher 責務の記述がない"
        )
        # 自前で get_toc を実行しない旨が書かれている
        self.assertIn(
            'get_toc.py', body,
            "query-docs に get_toc を自分で実行しない旨の記述がない"
        )
        self.assertRegex(
            body,
            r'(自分で|dispatcher は).*(get_toc|ToC 全エントリ).*(しない|行わない)',
            "query-docs に「dispatcher は ToC 関連判断/get_toc を自分で行わない」記述がない "
            "(ADR-002 §F-2 違反)"
        )


class TestQueryWorkerReadonlyConstraint(unittest.TestCase):
    """query-worker が read-only 制約を持つことを検証 (ADR-002 §B / §F-3)"""

    REQUIRED_PHRASES = [
        'read-only',
        'Edit',
        'Write',
        'MultiEdit',
        'NotebookEdit',
        'git commit',
        'git 管理ファイル',
        '[MANDATORY]',
    ]

    def test_worker_role_has_constraints(self):
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        for phrase in self.REQUIRED_PHRASES:
            self.assertIn(
                phrase, body,
                f"agents/query-worker.md に制約文言 '{phrase}' がない (ADR-002 §B/§F-3 違反)"
            )

    def test_worker_argument_guard(self):
        """引数解釈ガードが含まれている (ADR-002 §C / §F-3)"""
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        self.assertRegex(
            body,
            r'(?m)^#{2,3}\s*引数解釈',
            "agents/query-worker.md に `引数解釈` セクションがない (ADR-002 §C 違反)"
        )
        self.assertIn(
            '実装指示として解釈してはならない', body,
            "agents/query-worker.md の引数解釈に命令文の解釈ガードがない (ADR-002 §C 違反)"
        )

    def test_worker_return_contract(self):
        """最終 return が `Required documents:` 形式を含む (§F-3)"""
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        self.assertIn(
            'Required documents:', body,
            "agents/query-worker.md に `Required documents:` 出力契約の記載がない"
        )

    def test_worker_is_readonly_tooling(self):
        """worker の tools が read-only 系（書き込み系を含まない）であることを検証"""
        fm, _ = _split_frontmatter_body(QUERY_WORKER_AGENT)
        import re
        m = re.search(r'(?m)^tools:\s*(.+)$', fm)
        self.assertIsNotNone(m, "agents/query-worker.md の frontmatter に tools がない")
        tools = {t.strip() for t in m.group(1).split(',')}
        forbidden = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
        self.assertEqual(
            tools & forbidden, set(),
            f"agents/query-worker.md の tools に書き込み系 {tools & forbidden} が含まれている"
        )


class TestQueryWorkerOutputUnion(unittest.TestCase):
    """worker の出力契約が `Required documents:` / `Query error:` の明示的 union で、
    通常時に余分な散文を返さない契約になっていることを検証 (review #21 指摘 2/3)
    """

    def test_query_error_block_defined(self):
        """ToC 未生成・予約 key 衝突を返す `Query error:` ブロックが定義されている"""
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        self.assertIn(
            'Query error:', body,
            "agents/query-worker.md に `Query error:` 出力形式の定義がない "
            "(エラー時の出力契約欠落 / review #21 指摘 2)"
        )
        for code in ('TOC_NOT_FOUND', 'KEY_RESERVED'):
            self.assertIn(
                code, body,
                f"agents/query-worker.md の `Query error:` 契約に `{code}` がない"
            )

    def test_two_forms_are_exclusive(self):
        """成功形式とエラー形式が排他（どちらか 1 つだけ返す）と明記されている"""
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        self.assertRegex(
            body,
            r'2\s*形式のいずれか',
            "agents/query-worker.md に「2 形式のいずれか 1 つだけ返す」旨の排他契約がない"
        )

    def test_no_extra_prose_in_normal_case(self):
        """通常時に散文・思考ログ・案内文を返さない制約が明記されている"""
        _, body = _split_frontmatter_body(QUERY_WORKER_AGENT)
        self.assertIn(
            'Do NOT return', body,
            "agents/query-worker.md に出力抑制（Do NOT return）の記載がない"
        )
        # worker は利用者向け案内文を書かない（案内は dispatcher 責務）
        self.assertRegex(
            body,
            r'(案内文|思考ログ).*(dispatcher|書かない|含めない|返さない|禁止)'
            r'|(dispatcher|書かない|含めない|返さない|禁止).*(案内文|思考ログ)',
            "agents/query-worker.md に「案内文・思考ログを返さない」制約がない"
        )

    def test_dispatcher_handles_union(self):
        """dispatcher が両形式を判別して処理する記述を持つ"""
        _, body = _split_frontmatter_body(QUERY_DOCS_SKILL)
        for form in ('Required documents:', 'Query error:'):
            self.assertIn(
                form, body,
                f"query-docs dispatcher が worker 出力形式 `{form}` の処理を記述していない "
                "(union 判別の欠落 / review #21 指摘 2)"
            )


class TestNoAllowedToolsPhysicalDenyMisrepresentation(unittest.TestCase):
    """allowed-tools を物理 deny と誤認させる記述がないことを検証 (ADR-002 §E / §F-4)"""

    def test_dispatcher_clarifies_allowed_tools(self):
        """query-docs は allowed-tools が物理 deny でない旨を明記している (§F-4)"""
        _, body = _split_frontmatter_body(QUERY_DOCS_SKILL)
        self.assertIn(
            '物理 deny', body,
            "query-docs に allowed-tools が物理 deny ではない旨の明記がない (ADR-002 §E/§F-4 違反)"
        )


if __name__ == '__main__':
    unittest.main()
