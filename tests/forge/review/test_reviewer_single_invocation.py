#!/usr/bin/env python3
"""
回帰防止テスト: reviewer 1 起動原則 (FNC-412) の静的検査。

REQ-004 FNC-412 / DES-028 §2.3 で定めた「1 回の /forge:review 実行につき
reviewer agent は厳密に 1 起動」の原則に対する**回帰**を CI で検知する。

検査方針:
  - 既存テスト基盤 (Python unittest) は SKILL.md 実行・agent 起動数の runtime
    計測を持たないため、grep/AST 相当の**静的検査**で違反を検出する。
  - 検査対象は SKILL.md と review 関連 Python scripts のみ。
  - migration_notes / plan.yaml / principles addendum は旧体系説明のため除外。

検査項目 (FNC-412):
  1. reviewer 起動の**肯定的な指示** (= 単数指定なく "並列・分割・複数体" を
     示唆する) が存在しない。
  2. ループ・バックグラウンド並列起動の表現 (旧体系) が含まれない。
  3. 旧体系の表現 (`perspectives の数だけ` 等) が含まれない。

実行:
  python3 -m unittest tests.forge.review.test_reviewer_single_invocation -v
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# 検査対象パス
TARGET_FILES: list[Path] = [
    REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "SKILL.md",
    REPO_ROOT / "plugins" / "forge" / "skills" / "reviewer" / "SKILL.md",
]
# scripts も glob で収集
TARGET_FILES += sorted(
    (REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "scripts").glob("**/*.py")
)
TARGET_FILES += sorted(
    (REPO_ROOT / "plugins" / "forge" / "scripts" / "review").glob("**/*.py")
)


# ---------------------------------------------------------------------------
# 行フィルタユーティリティ (false positive 抑制)
# ---------------------------------------------------------------------------

# 否定・禁止・宣言文脈を示すマーカー。これを含む行は「採用しない」「禁止する」等の
# 説明文と判断し、肯定的な起動指示としては数えない。
_NEGATION_MARKERS = (
    "しない",
    "せず",
    "禁止",
    "不可",
    "採用しない",
    "例外なく",
    "例外なし",
    "避け",
    "防ぐ",
    "ではなく",
    "ではない",
    "の概念は",
    "旧体系",
    "旧:",
    "Before:",
    "撤廃",
    "削除",
)


def _strip_code_fences(text: str) -> str:
    """Markdown のコードフェンス (```...```) ブロックを除去する。

    フェンス内の例示テキストはレビュー対象の指示ではないため検査から外す。
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(line)
    return "\n".join(out)


def _is_comment_or_quote(line: str) -> bool:
    """引用 (> ...) / Python コメント (# ...) 行を判定する。

    Python の '# ...' 行は仕様コメントが多く、肯定的な実行指示ではないため除外する。
    Markdown の '> ' 引用も補足情報のため除外する。
    """
    s = line.lstrip()
    return s.startswith(">") or s.startswith("#")


def _is_negated(line: str) -> bool:
    """行が否定・禁止文脈を含むか判定する。"""
    return any(marker in line for marker in _NEGATION_MARKERS)


# ---------------------------------------------------------------------------
# 違反パターン定義
# ---------------------------------------------------------------------------

# 強い禁止パターン (旧体系の機械的痕跡)
# これらは context にかかわらず存在自体が違反。
_HARD_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"for\s+perspective\s+in\s+perspectives", "旧体系: 観点ループ"),
    (r"pids\+=\(\$!\)", "旧体系: バックグラウンド並列 PID 蓄積"),
    (r'wait\s+"\$pid"', "旧体系: 並列 PID 待機"),
    (r"perspectives\s*の数だけ", "旧体系: 観点並列起動の日本語記述"),
]


# 起動指示を表すパターン (肯定文脈で出現したら違反になり得る)
# このパターン単独ではマッチさせず、_is_negated() で否定文脈を除外する。
_LAUNCH_INDICATOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"reviewer.{0,40}並列起動"),
    re.compile(r"並列起動.{0,40}reviewer"),
    re.compile(r"reviewer.{0,40}を\s*複数"),
    re.compile(r"reviewer.{0,40}\d+\s*体\s*以上.{0,40}起動"),
    re.compile(r"reviewer.{0,40}分割.{0,20}起動"),
]


def _check_hard_forbidden(path: Path) -> list[tuple[int, str, str]]:
    """強い禁止パターンの検出。

    Returns:
        (行番号, 該当文字列, 違反理由) のリスト
    """
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    # コードフェンス内のサンプルも実害は無いが、SKILL.md / scripts では
    # コード例 = 実行例の可能性が高いため、検査対象に含める。
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in _HARD_FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                violations.append((lineno, line.strip(), reason))
    return violations


# 禁止リストの見出しを示すマーカー。これが直近に出現していれば、配下の bullet 行は
# 「禁止される行為の列挙」と判定し、肯定的な指示としては数えない。
_FORBIDDEN_SECTION_MARKERS = (
    "禁止事項",
    "禁止する",
    "してはいけない",
    "採用しない",
    "撤廃",
    "DROP",
    "廃止",
    "削除",
)

# 否定セクションの効力範囲 (行数)。見出しから何行までを否定スコープとみなすか。
_FORBIDDEN_SECTION_RANGE = 12


def _in_forbidden_section(lines: list[str], idx: int) -> bool:
    """idx 行が直近の「禁止セクション見出し」配下にあるか判定する。

    直前 _FORBIDDEN_SECTION_RANGE 行以内に禁止見出しがあり、かつ間に空行 2 連続や
    新規見出し (## / ###) が割り込んでいなければ True を返す。
    """
    for back in range(1, _FORBIDDEN_SECTION_RANGE + 1):
        prev = idx - back
        if prev < 0:
            break
        line = lines[prev]
        s = line.strip()
        # 新規見出しや空行 2 連続でスコープ切れ判定
        if s.startswith("## ") or s.startswith("### "):
            return False
        if any(marker in line for marker in _FORBIDDEN_SECTION_MARKERS):
            return True
    return False


def _check_parallel_launch_indicator(path: Path) -> list[tuple[int, str, str]]:
    """並列起動を示唆する**肯定的な記述**を検出する。

    否定文脈 (「並列起動は採用しない」等) と、禁止セクション (「禁止事項:」配下の
    bullet 列挙) は除外する。
    """
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return violations
    # Markdown コードフェンス内は説明・出力例のため除外
    if path.suffix == ".md":
        text = _strip_code_fences(text)
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        if _is_comment_or_quote(line):
            continue
        if _is_negated(line):
            continue
        # 「禁止事項」配下の bullet 列挙は否定文脈として除外
        if _in_forbidden_section(lines, lineno - 1):
            continue
        for pattern in _LAUNCH_INDICATOR_PATTERNS:
            if pattern.search(line):
                violations.append(
                    (lineno, line.strip(), f"並列起動を示唆: {pattern.pattern}")
                )
                break
    return violations


def _count_positive_launch_directives(path: Path) -> list[tuple[int, str]]:
    """reviewer 起動を肯定的に指示している行を数える。

    肯定的とは: 「reviewer」と「起動」を同一行に含み、否定文脈
    (採用しない / 禁止 / 分割しない 等) でない行。

    Returns:
        (行番号, 該当行) のリスト
    """
    matches: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return matches
    if path.suffix == ".md":
        text = _strip_code_fences(text)
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _is_comment_or_quote(line):
            continue
        if _is_negated(line):
            continue
        # 「1 起動原則」「reviewer 1 起動」「reviewer 起動」等の見出し系もマッチする。
        # ここでは「reviewer を起動」「reviewer agent を ... 起動」等の動詞的指示を
        # 拾う。見出しはセクションラベルなので除外しない (起動の正規ポイントとして
        # 1 箇所カウントされる想定)。
        if "reviewer" in line and "起動" in line:
            matches.append((lineno, line.strip()))
    return matches


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReviewerSingleInvocation(unittest.TestCase):
    """FNC-412 (reviewer 1 起動原則) の静的回帰防止。

    DES-028 §2.3 / REQ-004 FNC-412:
      1 回の /forge:review 実行につき reviewer agent は厳密に 1 起動とする。
      観点軸 (P1/P2/P3) も対象ファイル軸も、いかなる軸でも reviewer を分割起動しない。
    """

    def setUp(self) -> None:
        # 存在するファイルのみを対象にする (scripts ディレクトリが空でもテストは成立)
        self.files: list[Path] = [p for p in TARGET_FILES if p.is_file()]
        self.assertGreater(
            len(self.files),
            0,
            "検査対象ファイルが 1 件も存在しない。TARGET_FILES の glob を確認すること。",
        )

    def test_no_legacy_loop_or_parallel_patterns(self) -> None:
        """旧体系のループ・バックグラウンド並列起動の機械的痕跡が無いこと。

        対象パターン:
          - `for perspective in perspectives` (旧 perspective ループ)
          - `pids+=($!)` (Bash バックグラウンド並列)
          - `wait "$pid"` (並列待機)
          - `perspectives の数だけ` (日本語旧体系記述)
        """
        all_violations: list[str] = []
        for path in self.files:
            for lineno, snippet, reason in _check_hard_forbidden(path):
                rel = path.relative_to(REPO_ROOT)
                all_violations.append(f"  {rel}:{lineno}  [{reason}]  {snippet}")
        if all_violations:
            self.fail(
                "FNC-412 違反: 旧体系のループ・並列起動パターンが残存\n"
                + "\n".join(all_violations)
                + "\n→ DES-028 §2.3 / REQ-004 FNC-412 に従い、reviewer は 1 起動に統一すること"
            )

    def test_no_positive_parallel_launch_indicator(self) -> None:
        """reviewer の並列・分割起動を**肯定的に**指示する記述が無いこと。

        否定文脈 (採用しない / 禁止 / 分割不可 / 例外なく等) は許容する
        (FNC-412 の規定そのものを書いている記述を誤検出しないため)。
        """
        all_violations: list[str] = []
        for path in self.files:
            for lineno, snippet, reason in _check_parallel_launch_indicator(path):
                rel = path.relative_to(REPO_ROOT)
                all_violations.append(f"  {rel}:{lineno}  [{reason}]  {snippet}")
        if all_violations:
            self.fail(
                "FNC-412 違反: reviewer 並列・分割起動を示唆する記述が残存\n"
                + "\n".join(all_violations)
                + "\n→ DES-028 §2.3 / REQ-004 FNC-412 に従い、観点軸も対象ファイル軸も"
                "\n  例外なく単一 reviewer 内で順次評価する形に書き換えること"
            )

    def test_reviewer_launch_directive_exists(self) -> None:
        """reviewer 起動を指示する記述が SKILL.md に**少なくとも 1 箇所**存在し、
        かつ「review SKILL.md」内の起動指示文脈が常識的な範囲 (>0) に収まること。

        FNC-412 の主眼は「1 起動」であり、「ゼロ起動」(= reviewer が動かない)
        も逆に異常状態のため、起動指示の存在も合わせて確認する (正の対称テスト)。
        並列起動の検出は test_no_positive_parallel_launch_indicator が担う。
        """
        review_skill = REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "SKILL.md"
        if not review_skill.is_file():
            self.skipTest(f"{review_skill} が存在しない")
        matches = _count_positive_launch_directives(review_skill)
        self.assertGreater(
            len(matches),
            0,
            f"{review_skill.relative_to(REPO_ROOT)} に reviewer 起動を指示する記述が"
            " 1 箇所も無い (FNC-412 は「1 起動」を求めるがゼロ起動は別の異常)",
        )


if __name__ == "__main__":
    unittest.main()
