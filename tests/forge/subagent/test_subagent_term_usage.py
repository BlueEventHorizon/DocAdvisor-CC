#!/usr/bin/env python3
"""
TEST-S004: SKILL.md 内で "subagent" が単独で使われている箇所を列挙し、
baseline 警告数を超えたら fail する回帰防止テスト。

"subagent_type" や "サブエージェント" などの複合表現は検査対象外。

設計意図:
    現状の SKILL 群には旧来の "subagent" 単独表記が残存しており、即時の
    完全除去は困難。そこで baseline 方式を採用し、警告数が現状を超えた
    時点で fail させることで「新規違反の混入」を回帰として検出する。
    違反を解消したら EXPECTED_MAX_WARNINGS を下げて baseline を引き締める。

実行:
    python3 -m unittest tests.forge.subagent.test_subagent_term_usage -v
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills'

# "subagent" が単独で使われているパターン
# subagent_type / SUBAGENT-DES-001 のような仕様 ID / sub-agent 等の複合形は除外
_STANDALONE_RE = re.compile(r'\bsubagent\b(?!_type)', re.IGNORECASE)

# baseline 警告数 (2026-05-26 時点で 0 件)。仕様 ID は検査対象外。
EXPECTED_MAX_WARNINGS = 0

# fenced コードブロック内は除外
def _strip_code_blocks(body: str) -> str:
    lines = body.split('\n')
    result = []
    in_fence = False
    for line in lines:
        if line.strip().startswith('```'):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append(line)
    return '\n'.join(result)


def _collect_warnings(skill_path: Path) -> list[str]:
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

    filtered = _strip_code_blocks(body)
    warnings = []
    for lineno, line in enumerate(filtered.split('\n'), 1):
        matches = [m.group(0) for m in _STANDALONE_RE.finditer(line)]
        if any(not token.isupper() for token in matches):
            warnings.append(
                f'{skill_path.relative_to(REPO_ROOT)} L{lineno}: '
                f'"subagent" の単独使用: {line.strip()[:80]}'
            )
    return warnings


class TestSubagentTermUsage(unittest.TestCase):
    """TEST-S004: "subagent" の単独使用を baseline 方式で検証する。"""

    def test_baseline_standalone_subagent(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob('*/SKILL.md'))
        self.assertGreater(len(skill_files), 0, 'SKILL.md が 1 件も見つからない')

        all_warnings: list[str] = []
        for sf in skill_files:
            all_warnings.extend(_collect_warnings(sf))

        if all_warnings:
            print(
                f'\n[TEST-S004] "subagent" の単独使用 {len(all_warnings)} 件 '
                f'(baseline={EXPECTED_MAX_WARNINGS}):\n'
                + '\n'.join(f'  - {w}' for w in all_warnings),
                file=sys.stderr,
            )

        self.assertLessEqual(
            len(all_warnings),
            EXPECTED_MAX_WARNINGS,
            f'警告数が baseline ({EXPECTED_MAX_WARNINGS}) を超えました '
            f'({len(all_warnings)} 件)。新規に "subagent" の単独使用が追加されて '
            f'いないか確認し、解消後は EXPECTED_MAX_WARNINGS を下げてください。',
        )


if __name__ == '__main__':
    unittest.main()
