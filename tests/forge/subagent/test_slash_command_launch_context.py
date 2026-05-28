#!/usr/bin/env python3
"""
TEST-S005: Agent prompt として展開されるテキストブロック内に /forge:<skill> / /anvil:<skill>
表記がある場合、近傍 5 行以内 (前後) に起動経路の明示があること。
baseline 警告数を超えたら fail する回帰防止テスト。

- テキストブロック境界 = ``` コードブロック (fenced)
- 起動経路の明示: "汎用 Agent" / "継承型 SKILL" / "fork 型 SKILL" / "Bash subprocess"
  / "Skill ツール" / "Agent ツール"
- [KNOWN-FP] マーカー付きは除外
- review 配下の reviewer/SKILL.md は対象外 (fork 型に構造的解消済み)

設計意図:
    現状の SKILL 群には起動経路の明示が伴わない /forge:* / /anvil:* 表記が
    多く残っており、これらは多くが「ユーザーが入力するコマンド構文の例示」
    で正当な使い方。即時の完全除去は実用的ではないため baseline 方式を採用。
    警告数が現状を超えた時点で fail させることで、AI が誤読する経路 (Issue
    #32) が新規に混入していないかを回帰として検出する。違反を解消したら
    EXPECTED_MAX_WARNINGS を下げて baseline を引き締める。

実行:
    python3 -m unittest tests.forge.subagent.test_slash_command_launch_context -v
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills'

LAUNCH_CONTEXT_PATTERNS = [
    re.compile(r'汎用 Agent'),
    re.compile(r'継承型 SKILL'),
    re.compile(r'fork 型 SKILL'),
    re.compile(r'Bash subprocess'),
    re.compile(r'Skill ツール'),
    re.compile(r'Agent ツール'),
]

_SKILL_CALL_RE = re.compile(r'/(forge|anvil):[a-z]')

# review 配下は構造的解消済みのため対象外
_EXCLUDED_SKILLS = {'reviewer'}

# baseline 警告数 (2026-05-26 時点で 45 件)。違反を解消したらこの値を下げる。
# 新規違反が混入して警告数がこれを超えると fail する (回帰防止)。
EXPECTED_MAX_WARNINGS = 45


def _check_file(skill_path: Path) -> list[str]:
    skill_name = skill_path.parent.name
    if skill_name in _EXCLUDED_SKILLS:
        return []

    content = skill_path.read_text(encoding='utf-8')
    # frontmatter を除く
    if content.startswith('---'):
        end = content.find('---', 3)
        if end != -1:
            body = content[end + 3:]
        else:
            body = content
    else:
        body = content

    lines = body.split('\n')
    warnings = []
    in_fence = False
    fence_lines: list[tuple[int, str]] = []  # (lineno, line)

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('```'):
            if in_fence:
                # フェンス終了: ブロック内でチェック
                for i, (fln, fl) in enumerate(fence_lines):
                    if _SKILL_CALL_RE.search(fl) and '[KNOWN-FP]' not in fl:
                        # 近傍 5 行 (fence_lines の前後) に起動経路があるか
                        context_start = max(0, i - 5)
                        context_end = min(len(fence_lines), i + 6)
                        context_text = '\n'.join(tl for _, tl in fence_lines[context_start:context_end])
                        has_context = any(p.search(context_text) for p in LAUNCH_CONTEXT_PATTERNS)
                        if not has_context:
                            warnings.append(
                                f'{skill_path.relative_to(REPO_ROOT)} L{fln}: '
                                f'コードブロック内 /{fl.strip()[:60]} の近傍に起動経路記述なし'
                            )
                in_fence = False
                fence_lines = []
            else:
                in_fence = True
        elif in_fence:
            fence_lines.append((lineno, line))

    return warnings


class TestSlashCommandLaunchContext(unittest.TestCase):
    """TEST-S005: prompt ブロック内の /forge: 呼び出しに起動経路明示があることを baseline 方式で検証する。"""

    def test_baseline_launch_context_warnings(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob('*/SKILL.md'))
        self.assertGreater(len(skill_files), 0, 'SKILL.md が 1 件も見つからない')

        all_warnings: list[str] = []
        for sf in skill_files:
            all_warnings.extend(_check_file(sf))

        if all_warnings:
            print(
                f'\n[TEST-S005] prompt ブロック内 /forge: 呼び出しの起動経路未明示 '
                f'{len(all_warnings)} 件 (baseline={EXPECTED_MAX_WARNINGS}):\n'
                + '\n'.join(f'  - {w}' for w in all_warnings),
                file=sys.stderr,
            )

        self.assertLessEqual(
            len(all_warnings),
            EXPECTED_MAX_WARNINGS,
            f'警告数が baseline ({EXPECTED_MAX_WARNINGS}) を超えました '
            f'({len(all_warnings)} 件)。新規に prompt ブロック内の起動経路未明示が '
            f'追加されていないか確認し、解消後は EXPECTED_MAX_WARNINGS を下げてください。',
        )


if __name__ == '__main__':
    unittest.main()
