#!/usr/bin/env python3
"""
Changed-line gate for forge SKILL / document wording.

This test intentionally checks only added lines in the current branch diff.
Existing legacy wording is handled by baseline tests, while newly edited lines
must follow the current launch-path terminology and review CLI contract.
"""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from dataclasses import dataclass
from pathlib import Path

from tests.forge.subagent.skill_launch_terms import load_terms

REPO_ROOT = Path(__file__).resolve().parents[3]

CHECKED_PATH_PREFIXES = (
    'plugins/forge/skills/',
    'docs/readme/forge/',
    'docs/specs/forge/',
)
CHECKED_SUFFIXES = {'.md', '.yaml', '.yml', '.json', '.py', '.sh', '.txt', ''}

_HUNK_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
_STANDALONE_SUBAGENT_RE = re.compile(r'\bsubagent\b(?!_type)', re.IGNORECASE)
_OLD_REVIEW_TARGET_RE = re.compile(
    r'/forge:review\s+'
    r'(code|design|plan|requirement|uxui|generic)\s+'
    r'(?!-)'
    r'(\{[^}]+\}|[^\s`|#]+)'
)
_SLASH_COMMAND_RE = re.compile(r'/(forge|anvil):[a-z][a-z0-9-]*')


def _compile_literal_patterns(values: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(re.escape(value)) for value in values]


_LAUNCH_CONTEXT_PATTERNS = _compile_literal_patterns(
    load_terms()['launch_context']['terms']
)
# 使用例マーカーは公式用語ではなくテスト誤検知抑制のための heuristic。
# SUBAGENT-DES-002 §2.1 / §4.2 / §7.2 により TOML 用語集には追加せず、
# テストコード側に保持する。
_USER_EXAMPLE_PATTERNS = [
    re.compile(r'使い方'),
    re.compile(r'使用例'),
    re.compile(r'Usage'),
    re.compile(r'Example'),
    re.compile(r'コマンド例'),
    re.compile(r'コマンド確認'),
    re.compile(r'コマンドを実行'),
    re.compile(r'ユーザー入力'),
    re.compile(r'対応するスキル'),
]

_INVOCATION_HINT_RE = re.compile(
    r'(起動|呼び出|実行|委譲|call|launch|run)',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChangedLine:
    path: str
    lineno: int
    text: str


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def _resolve_diff_base() -> str | None:
    env_base = os.environ.get('FORGE_DIFF_BASE')
    if env_base:
        return env_base

    for candidate in ('main', 'origin/main'):
        try:
            _run_git(['rev-parse', '--verify', candidate])
            return candidate
        except RuntimeError:
            continue
    return None


def _is_checked_path(path: str) -> bool:
    if not path.startswith(CHECKED_PATH_PREFIXES):
        return False
    return Path(path).suffix.lower() in CHECKED_SUFFIXES


def _changed_lines() -> list[ChangedLine]:
    base = _resolve_diff_base()
    if base is None:
        raise unittest.SkipTest('main / origin/main が見つからないため差分検査をスキップします')

    diff = _run_git([
        'diff',
        '--unified=0',
        '--no-ext-diff',
        '--no-color',
        f'{base}...HEAD',
        '--',
        *CHECKED_PATH_PREFIXES,
    ])

    changed: list[ChangedLine] = []
    current_path: str | None = None
    new_lineno: int | None = None

    for raw in diff.splitlines():
        if raw.startswith('+++ b/'):
            current_path = raw.removeprefix('+++ b/')
            continue
        if raw.startswith('+++ /dev/null'):
            current_path = None
            continue

        hunk = _HUNK_RE.match(raw)
        if hunk:
            new_lineno = int(hunk.group(1))
            continue

        if current_path is None or new_lineno is None:
            continue

        if raw.startswith('+') and not raw.startswith('+++'):
            if _is_checked_path(current_path):
                changed.append(ChangedLine(current_path, new_lineno, raw[1:]))
            new_lineno += 1
        elif raw.startswith('-') and not raw.startswith('---'):
            continue
        elif raw.startswith(' '):
            new_lineno += 1

    return changed


def _current_file_lines(path: str) -> list[str]:
    return (REPO_ROOT / path).read_text(encoding='utf-8', errors='replace').splitlines()


def _line_context(path: str, lineno: int, radius: int = 5) -> str:
    lines = _current_file_lines(path)
    start = max(0, lineno - radius - 1)
    end = min(len(lines), lineno + radius)
    return '\n'.join(lines[start:end])


def _has_launch_context_or_user_example(path: str, lineno: int) -> bool:
    context = _line_context(path, lineno)
    if any(pattern.search(context) for pattern in _LAUNCH_CONTEXT_PATTERNS):
        return True

    broader_context = _line_context(path, lineno, radius=25)
    return any(pattern.search(broader_context) for pattern in _USER_EXAMPLE_PATTERNS)


def _uses_standalone_subagent_term(text: str) -> bool:
    for match in _STANDALONE_SUBAGENT_RE.finditer(text):
        token = match.group(0)
        if token.isupper():
            continue
        return True
    return False


def _requires_launch_context(line: ChangedLine) -> bool:
    if not line.path.startswith('plugins/forge/skills/'):
        return False
    if not _SLASH_COMMAND_RE.search(line.text):
        return False
    if '[KNOWN-FP]' in line.text:
        return False

    stripped = line.text.strip()
    if '呼び出し元' in stripped or 'から呼び出される' in stripped or '次回' in stripped:
        return False
    if stripped.startswith(('/forge:', '/anvil:')):
        return True
    return _INVOCATION_HINT_RE.search(stripped) is not None


class TestChangedLinesPolicy(unittest.TestCase):
    """Newly changed lines must follow current forge launch and review contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.changed = _changed_lines()

    def test_changed_lines_do_not_add_standalone_subagent(self) -> None:
        violations = [
            f'{line.path} L{line.lineno}: {line.text.strip()}'
            for line in self.changed
            if _uses_standalone_subagent_term(line.text)
        ]

        self.assertEqual(
            violations,
            [],
            '変更行に "subagent" の単独使用が含まれています。'
            '「fork 型 SKILL」「汎用 Agent」「カスタム Agent」等に置換してください:\n'
            + '\n'.join(f'  - {v}' for v in violations),
        )

    def test_changed_lines_do_not_use_legacy_review_positional_target(self) -> None:
        violations = [
            f'{line.path} L{line.lineno}: {line.text.strip()}'
            for line in self.changed
            if _OLD_REVIEW_TARGET_RE.search(line.text)
        ]

        self.assertEqual(
            violations,
            [],
            '変更行に旧 `/forge:review <種別> <対象>` 構文が含まれています。'
            'ファイル・ディレクトリ指定は `--files` を使ってください:\n'
            + '\n'.join(f'  - {v}' for v in violations),
        )

    def test_changed_skill_slash_command_lines_explain_launch_context(self) -> None:
        violations = []
        for line in self.changed:
            if not _requires_launch_context(line):
                continue
            if _has_launch_context_or_user_example(line.path, line.lineno):
                continue
            violations.append(f'{line.path} L{line.lineno}: {line.text.strip()}')

        self.assertEqual(
            violations,
            [],
            '変更行の slash command 表記に起動経路またはユーザー入力例である説明がありません。'
            'Skill 内から起動する場合は Skill ツール / Agent ツール等を明示してください:\n'
            + '\n'.join(f'  - {v}' for v in violations),
        )


if __name__ == '__main__':
    unittest.main()
