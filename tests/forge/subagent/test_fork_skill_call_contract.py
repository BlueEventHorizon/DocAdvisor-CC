#!/usr/bin/env python3
"""Regression tests for fork SKILL caller-side input contracts."""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding='utf-8')


def _section(text: str, start: str, end: str) -> str:
    try:
        start_idx = text.index(start)
    except ValueError as exc:
        raise AssertionError(f'セクション開始マーカーが見つかりません: {start}') from exc
    try:
        end_idx = text.index(end, start_idx)
    except ValueError as exc:
        raise AssertionError(f'セクション終了マーカーが見つかりません: {end}') from exc
    return text[start_idx:end_idx]


class TestForkSkillCallContract(unittest.TestCase):
    """Issue #95: fork 型 fixer の呼び出し契約を旧 Agent 契約へ戻さない。"""

    def test_review_callers_do_not_use_legacy_fixer_agent_contract(self) -> None:
        paths = [
            'plugins/forge/skills/review/SKILL.md',
            'plugins/forge/skills/present-findings/SKILL.md',
            'plugins/forge/skills/evaluator/SKILL.md',
            'plugins/forge/skills/fixer/SKILL.md',
            'plugins/forge/docs/session_format.md',
            'docs/specs/forge/design/DES-015_review_workflow_design.md',
            'docs/specs/forge/design/DES-028_review_policy_design.md',
            'docs/specs/forge/requirements/REQ-004_review_policy.md',
        ]
        forbidden = [
            'fixer (汎用 Agent)',
            'Agent ツール / general-purpose',
            '汎用 Agent に修正を委譲',
            '指摘事項の詳細テキスト冒頭',
        ]

        violations = []
        for path in paths:
            content = _read(path)
            for phrase in forbidden:
                if phrase in content:
                    violations.append(f'{path}: {phrase}')

        self.assertEqual(
            violations,
            [],
            'fork 型 fixer 呼び出し元に旧 Agent 契約または詳細貼り付け契約が残っています:\n'
            + '\n'.join(f'  - {v}' for v in violations),
        )

    def test_present_findings_documents_structured_fixer_args(self) -> None:
        content = _read('plugins/forge/skills/present-findings/SKILL.md')
        required_examples = [
            'args: "{session_dir} {review_type} --single {id}"',
            'args: "{session_dir} {review_type} --batch"',
            'args: "{session_dir} {review_type} --diff-only {files_modified}"',
            'args: "{session_dir} {review_type} {engine} --diff-only {files_modified}"',
        ]

        missing = [example for example in required_examples if example not in content]
        self.assertEqual(
            missing,
            [],
            'present-findings の fixer / reviewer 呼び出しに構造化 args 例が不足しています:\n'
            + '\n'.join(f'  - {m}' for m in missing),
        )

    def test_review_documents_fork_data_handoff_contract(self) -> None:
        content = _read('plugins/forge/skills/review/SKILL.md')
        required = [
            'fork 型 SKILL への入力契約',
            'target_files、指摘詳細、参考文書本文、親タスク本文は貼り付けない',
            '`refs.yaml` / `plan.yaml` / `review_<種別>.md` / `patch_result.json`',
            'fixer には指摘本文や対象ファイル本文を直接渡さない',
            '`status: fixed` への遷移は、単独修正レビュー後に review が `mark_fixed.py`',
        ]

        missing = [phrase for phrase in required if phrase not in content]
        self.assertEqual(
            missing,
            [],
            'review/SKILL.md に fork 型 SKILL へのデータ受け渡し契約が不足しています:\n'
            + '\n'.join(f'  - {m}' for m in missing),
        )

    def test_fixer_single_argument_example_includes_id(self) -> None:
        content = _read('plugins/forge/skills/fixer/SKILL.md')

        self.assertIn('.claude/.temp/review-abc123 code --single 3', content)
        self.assertNotRegex(
            content,
            re.compile(r'\.claude/\.temp/review-abc123 code --single\s*\|'),
            '--single の引数例に対象 id が含まれていません',
        )

    def test_des028_fixer_path_uses_skill_tool_contract(self) -> None:
        content = _read('docs/specs/forge/design/DES-028_review_policy_design.md')
        section = _section(content, '##### fixer 経路の手順', '##### 除外規定')

        self.assertIn('Skill ツール (fork)', section)
        self.assertIn('patch_result.json', section)
        self.assertNotIn('Agent ツール / general-purpose', section)
        self.assertNotIn('汎用 Agent に修正を委譲', section)
        self.assertNotIn('fixer が mark_fixed.py', section)

    def test_des015_review_to_fixer_interface_uses_session_dir_contract(self) -> None:
        content = _read('docs/specs/forge/design/DES-015_review_workflow_design.md')
        section = _section(content, '### review → fixer', '## 7. 設計原則')

        self.assertIn('Skill ツール (fork)', section)
        self.assertIn('構造化 args', section)
        self.assertIn('--diff-only', section)
        self.assertIn('patch_result.json', section)
        self.assertIn('| 制約 | 指摘詳細・対象ファイル・参考文書 | **直接渡さない**', section)
        self.assertIn('**直接渡さない**', section)
        self.assertIn('単独修正レビュー完了後に `mark_fixed.py`', section)
        self.assertNotIn('| 入力 | 指摘事項（修正リスト）', section)
        self.assertNotIn('| 入力 | target_files', section)
        self.assertNotIn('| 入力 | reference_docs', section)
        self.assertNotIn('| 入力 | related_code', section)

    def test_present_findings_args_style_is_consistent(self) -> None:
        content = _read('plugins/forge/skills/present-findings/SKILL.md')

        self.assertNotIn('args: `{session_dir}', content)

    def test_batch_ids_format_is_documented(self) -> None:
        paths = [
            'plugins/forge/skills/fixer/SKILL.md',
            'plugins/forge/skills/present-findings/SKILL.md',
        ]

        missing = [
            path
            for path in paths
            if '--ids 1 2 3' not in _read(path)
        ]
        self.assertEqual(
            missing,
            [],
            '--batch の id リスト書式が明示されていません:\n'
            + '\n'.join(f'  - {m}' for m in missing),
        )

    def test_inline_mode_does_not_claim_fixer_without_session_dir(self) -> None:
        content = _read('plugins/forge/skills/present-findings/SKILL.md')
        section = _section(content, '### --inline モード時の扱い', '### batch_update')

        self.assertIn('session_dir が存在しない', section)
        self.assertIn('修正実行、単独修正レビュー', section)
        self.assertIn('行わない', section)

    def test_session_format_fixed_owner_is_review_callers(self) -> None:
        content = _read('plugins/forge/docs/session_format.md')

        self.assertIn('| `fixed`        | 修正完了         | `review` / `present-findings`', content)
        self.assertNotIn('| `fixed`        | 修正完了         | `fixer`', content)
        self.assertIn('plan.yaml の `fixed` 遷移は行わない', content)


if __name__ == '__main__':
    unittest.main()
