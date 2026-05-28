#!/usr/bin/env python3
"""
回帰防止テスト: 旧 perspective 名のファイル名残置を検出する。

REQ-004 FNC-410 (旧体系の出力ファイル名規約変更) / DES-028 §3 設計に基づき、
`review_<perspective>.md` / `eval_<perspective>.json` 形式の旧体系ファイル名
リテラルが SKILL / scripts / templates / forge-review feature の設計・要件文書から
完全に消えていることを CI で保証する。

検出対象 (完全一致のファイル名トークン 26 種):
  - review_<perspective>.md  × 13 (logic / resilience / maintainability /
    architecture / completeness / alignment / feasibility / consistency /
    verifiability / hig_compliance / usability / visual_system / distinctiveness)
  - eval_<perspective>.json  × 13 (上記 13 種の review_ を eval_、.md を .json に置換)

検出対象外 (温存):
  - "perspective" という単語自体 (文脈用語)
  - "review_<perspective>" のようなテンプレ記法 (山括弧含む)

実行:
  python3 -m unittest tests.forge.review.test_no_legacy_perspective_filename -v
"""

import glob
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 旧 perspective 名 13 種 (REQ-004 FNC-402 廃止対象 perspective に対応)
LEGACY_PERSPECTIVES = (
    "logic",
    "resilience",
    "maintainability",
    "architecture",
    "completeness",
    "alignment",
    "feasibility",
    "consistency",
    "verifiability",
    "hig_compliance",
    "usability",
    "visual_system",
    "distinctiveness",
)

# 検出対象のリテラル文字列 26 種 (review_*.md 13 種 + eval_*.json 13 種)
LEGACY_FILENAME_TOKENS = tuple(
    [f"review_{p}.md" for p in LEGACY_PERSPECTIVES]
    + [f"eval_{p}.json" for p in LEGACY_PERSPECTIVES]
)

# 検査対象パスのパターン (glob, REPO_ROOT 相対)
SCAN_PATTERNS = (
    "plugins/forge/skills/review/**/*.md",
    "plugins/forge/skills/reviewer/**/*.md",
    "plugins/forge/skills/evaluator/**/*.md",
    "plugins/forge/skills/fixer/**/*.md",
    "plugins/forge/skills/present-findings/**/*.md",
    "plugins/forge/skills/**/scripts/**/*.py",
    "plugins/forge/skills/**/templates/**/*",
    "plugins/forge/scripts/**/*.py",
    "docs/specs/forge-review/design/**/*.md",
    "docs/specs/forge-review/requirements/**/*.md",
)

# 除外対象パス (REPO_ROOT 相対)
#   - 本テストファイル自身
#   - tests/ 配下 (fixture として旧名を持つ可能性がある)
#   - principles/ (addendum は merge 元、旧名残置を許容)
#   - forge-review の計画書 (本文説明として旧名が出現する可能性)
#   - 移行ノート (旧名 → 新名対比のため旧名を必ず含む)
EXCLUDE_RELATIVE_PATHS = (
    "tests/forge/review/test_no_legacy_perspective_filename.py",
    "docs/readme/forge/migration_notes/forge_review_v0.2.md",
    "docs/specs/forge-review/plan/forge-review_plan.yaml",
)

EXCLUDE_PATH_PREFIXES = (
    "tests/",
    "docs/specs/forge-review/principles/",
)


def _to_relative(path_str: str) -> str:
    """REPO_ROOT 相対パスへ正規化 (POSIX 区切り)"""
    p = Path(path_str).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _is_excluded(rel_path: str) -> bool:
    if rel_path in EXCLUDE_RELATIVE_PATHS:
        return True
    for prefix in EXCLUDE_PATH_PREFIXES:
        if rel_path.startswith(prefix):
            return True
    return False


def _collect_target_files() -> tuple[list[str], list[str]]:
    """検査対象ファイル一覧 (rel paths) と除外されたファイル一覧 (rel paths) を返す"""
    seen: set[str] = set()
    targets: list[str] = []
    excluded: list[str] = []

    for pattern in SCAN_PATTERNS:
        abs_pattern = str(REPO_ROOT / pattern)
        for match in glob.glob(abs_pattern, recursive=True):
            if not os.path.isfile(match):
                continue
            rel = _to_relative(match)
            if rel in seen:
                continue
            seen.add(rel)
            if _is_excluded(rel):
                excluded.append(rel)
            else:
                targets.append(rel)

    targets.sort()
    excluded.sort()
    return targets, excluded


class TestNoLegacyPerspectiveFilename(unittest.TestCase):
    """回帰防止: 旧 perspective ファイル名 (review_*.md / eval_*.json 26 種) が
    SKILL / scripts / templates / DES 系文書から完全に消えていることを検証する
    (REQ-004 FNC-410 / DES-028 §3)。"""

    def test_no_legacy_perspective_filename(self):
        target_files, excluded_files = _collect_target_files()

        # 前提: 検査対象ファイルが 1 件以上収集できていること
        self.assertGreater(
            len(target_files),
            0,
            "検査対象ファイルが 0 件: SCAN_PATTERNS / REPO_ROOT 解決が壊れている可能性",
        )

        violations: list[tuple[str, str]] = []  # (rel_path, token)
        unreadable: list[tuple[str, str]] = []  # (rel_path, error)

        for rel_path in target_files:
            abs_path = REPO_ROOT / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # バイナリ (templates 配下に存在し得る) は検出対象外
                continue
            except OSError as e:
                unreadable.append((rel_path, str(e)))
                continue

            for token in LEGACY_FILENAME_TOKENS:
                if token in content:
                    violations.append((rel_path, token))

        if unreadable:
            lines = [f"  - {p}: {err}" for p, err in unreadable]
            self.fail(
                "検査対象ファイルの読み込みに失敗:\n" + "\n".join(lines)
            )

        if violations:
            # 違反を集約して報告 (1 件ずつ assert しない)
            grouped: dict[str, list[str]] = {}
            for rel_path, token in violations:
                grouped.setdefault(rel_path, []).append(token)

            lines = [
                "旧 perspective ファイル名 (review_*.md / eval_*.json) が残存しています "
                "(REQ-004 FNC-410 / DES-028 §3 違反):",
                f"  検査ファイル数: {len(target_files)} / 除外: {len(excluded_files)}",
                f"  違反ファイル数: {len(grouped)} / 違反トークン延べ: {len(violations)}",
                "",
                "違反一覧:",
            ]
            for rel_path in sorted(grouped):
                tokens = ", ".join(sorted(set(grouped[rel_path])))
                lines.append(f"  - {rel_path}: {tokens}")
            self.fail("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
