#!/usr/bin/env python3
"""
TEST-S002: SKILL.md 本文に /forge:<skill> / /anvil:<skill> の Skill 呼出記述があれば
allowed-tools に Skill が含まれること。

実行:
    python3 -m unittest tests.forge.subagent.test_skill_allowedtools_consistency -v
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / 'plugins' / 'forge' / 'skills'

# 呼び出しとみなすパターン
# 1. 矢印起動: → /forge: または → `/forge:
_ARROW_INVOCATION = re.compile(r'→\s*`?/(forge|anvil):[a-z]')
# 2. 動詞起動: /forge:xxx を呼び出す / 起動する / 実行する (受動形除外)
_VERB_RE = re.compile(r'/(forge|anvil):[a-z][^\s`]*')
_ACTION_VERBS = re.compile(r'を(呼び出す|起動する|実行する|実行してください)')
_PASSIVE_VERBS = re.compile(r'(起動される|実行される|呼び出される)')


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end]
    result: dict = {}
    for line in fm_text.split('\n'):
        if ':' in line and not line.strip().startswith('-'):
            key, _, val = line.partition(':')
            result[key.strip()] = val.strip()
    return result, content[end + 3:]


def _strip_exclusions(body: str) -> str:
    """除外スコープを取り除いた本文を返す。
    除外対象:
    1. fenced コードブロック
    2. ### 制約 / ### 禁止事項 見出し配下
    3. blockquote 行
    """
    lines = body.split('\n')
    result = []
    in_fence = False
    in_excluded_section = False
    excluded_level = 0

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2)
            if level >= 3 and ('制約' in title or '禁止事項' in title):
                in_excluded_section = True
                excluded_level = level
                continue
            elif in_excluded_section and level <= excluded_level:
                in_excluded_section = False

        if in_excluded_section:
            continue
        if stripped.startswith('>'):
            continue

        result.append(line)

    return '\n'.join(result)


def _is_skill_invocation(line: str) -> bool:
    """行が Skill 呼び出しを表しているか判定する。受動形は除外。"""
    if _PASSIVE_VERBS.search(line):
        return False
    if _ARROW_INVOCATION.search(line):
        return True
    if _VERB_RE.search(line) and _ACTION_VERBS.search(line):
        return True
    return False


def _check_skill(skill_path: Path) -> list[str]:
    content = skill_path.read_text(encoding='utf-8')
    fm, body = _parse_frontmatter(content)

    allowed_tools_raw = fm.get('allowed-tools', '')
    if not allowed_tools_raw:
        return []

    allowed_tools = {t.strip() for t in allowed_tools_raw.split(',')}
    has_skill = 'Skill' in allowed_tools

    filtered = _strip_exclusions(body)
    violations = []
    for lineno, line in enumerate(filtered.split('\n'), 1):
        if _VERB_RE.search(line) and _is_skill_invocation(line):
            if not has_skill:
                violations.append(
                    f'{skill_path.relative_to(REPO_ROOT)} L{lineno}: '
                    f'Skill 呼出記述があるが allowed-tools に Skill がない: {line.strip()[:80]}'
                )
            break  # SKILL ファイルごとに最初の違反のみ報告

    return violations


class TestSkillAllowedToolsConsistency(unittest.TestCase):
    """TEST-S002: Skill 呼出記述と allowed-tools の整合性検証。"""

    def test_all_forge_skills(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob('*/SKILL.md'))
        self.assertGreater(len(skill_files), 0, 'SKILL.md が 1 件も見つからない')

        all_violations: list[str] = []
        for sf in skill_files:
            all_violations.extend(_check_skill(sf))

        self.assertEqual(
            all_violations,
            [],
            'Skill 呼出記述と allowed-tools の不整合:\n'
            + '\n'.join(f'  - {v}' for v in all_violations),
        )


if __name__ == '__main__':
    unittest.main()
