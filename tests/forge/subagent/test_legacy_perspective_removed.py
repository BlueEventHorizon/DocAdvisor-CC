#!/usr/bin/env python3
"""
TEST-S003: 旧 perspective ベースの review ファイル名参照が除去されていること。

検査対象:
- `review_{perspective}.md` テンプレート文字列 (curly-brace 形式)
- `review_<perspective>.md` テンプレート文字列 (angle-bracket 形式)
- 旧 perspective 実名: review_logic.md / review_resilience.md / review_alignment.md 等

除外:
- OBSOLETE マーカー付き行
- migration_notes/ ディレクトリ配下 (移行ドキュメントは旧名を記録する)

実行:
    python3 -m unittest tests.forge.subagent.test_legacy_perspective_removed -v
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

SEARCH_DIRS = [
    REPO_ROOT / 'plugins' / 'forge',
    REPO_ROOT / 'docs' / 'readme' / 'forge',
]

# テンプレート変数として "perspective" が使われているパターン
_TEMPLATE_PAT = re.compile(r'review_(\{perspective\}|<perspective>)\.md')

# 旧 perspective 実名 (新体系の種別名・関連ファイル名は除外)
_KNOWN_LEGACY_PERSPECTIVES = {
    'logic', 'resilience', 'alignment', 'security',
    'maintainability', 'correctness', 'readability',
}
_LEGACY_NAME_PAT = re.compile(
    r'(?<![a-zA-Z0-9_])review_(' + '|'.join(_KNOWN_LEGACY_PERSPECTIVES) + r')\.md'
)


def _should_skip_path(path: Path) -> bool:
    """移行ドキュメント等はスキップする。"""
    return 'migration_notes' in path.parts


def _check_file(path: Path) -> list[str]:
    if _should_skip_path(path):
        return []
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []

    violations = []
    for lineno, line in enumerate(text.split('\n'), 1):
        if 'OBSOLETE' in line:
            continue
        if _TEMPLATE_PAT.search(line):
            # 旧体系の説明 (「完全削除」「旧体系」等で明示) は除外
            if '旧体系' not in line and '完全削除' not in line:
                violations.append(
                    f'{path.relative_to(REPO_ROOT)} L{lineno}: '
                    f'旧テンプレート変数 "{{perspective}}" が残存: {line.strip()[:80]}'
                )
        m = _LEGACY_NAME_PAT.search(line)
        if m:
            violations.append(
                f'{path.relative_to(REPO_ROOT)} L{lineno}: '
                f'旧 perspective 名 "{m.group(0)}" が残存: {line.strip()[:80]}'
            )
    return violations


class TestLegacyPerspectiveRemoved(unittest.TestCase):
    """TEST-S003: 旧 perspective ベースの review ファイル名参照が除去されていること。"""

    def test_no_legacy_perspective_references(self) -> None:
        violations: list[str] = []
        for search_dir in SEARCH_DIRS:
            if not search_dir.exists():
                continue
            for path in sorted(search_dir.rglob('*')):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix not in {'.md', '.yaml', '.yml', '.json', '.py', '.sh', '.txt', ''}:
                    continue
                violations.extend(_check_file(path))

        self.assertEqual(
            violations,
            [],
            '旧 perspective ベースの review ファイル名参照が残存しています:\n'
            + '\n'.join(f'  - {v}' for v in violations),
        )


if __name__ == '__main__':
    unittest.main()
