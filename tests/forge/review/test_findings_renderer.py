"""review.findings_renderer のテスト。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3] / "plugins" / "forge" / "scripts"),
)
sys.modules.pop("review", None)

from review.findings_renderer import generate_plan_yaml, generate_review_md, summarize


def _f(
    finding_id,
    severity,
    title,
    *,
    priority=None,
    location="",
    status="pending",
):
    """test fixture finding 辞書を生成する。

    新体系 (DES-028) に基づき、観点軸は priority (P1/P2/P3) で表現する。
    旧 `perspective` 軸 (logic/resilience 等) は撤廃済みのため fixture からも除去。
    """
    d = {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "status": status,
        "location": location,
    }
    if priority is not None:
        d["priority"] = priority
    return d


class TestFindingsRenderer(unittest.TestCase):
    def test_generate_plan_yaml(self):
        yaml_text = generate_plan_yaml([
            _f(1, "critical", "path: 問題", priority="P1"),
        ])

        self.assertIn("items:", yaml_text)
        self.assertIn('title: "path: 問題"', yaml_text)
        self.assertIn("severity: critical", yaml_text)
        self.assertIn("priority: P1", yaml_text)

    def test_generate_plan_yaml_preserves_input_order(self):
        """plan.yaml は入力順を保持する (id 連番性を維持するため、ソートは行わない)。

        review.md (generate_review_md) のみが二段ソートを適用する。
        plan.yaml への severity / priority ソート反映は upstream の id 採番段階で行う。
        """
        findings = [
            _f(1, "minor", "改善A", priority="P3"),
            _f(2, "critical", "致命A", priority="P2"),
            _f(3, "critical", "致命B", priority="P1"),
            _f(4, "major", "品質A", priority="P1"),
        ]
        yaml_text = generate_plan_yaml(findings)

        id_order = [
            line.strip() for line in yaml_text.splitlines() if line.strip().startswith("- id:")
        ]
        self.assertEqual(
            id_order,
            ["- id: 1", "- id: 2", "- id: 3", "- id: 4"],
        )

    def test_generate_review_md_and_summary(self):
        findings = [
            _f(1, "critical", "問題A", priority="P1", location="a.py:1"),
            _f(2, "minor", "改善B", priority="P3"),
        ]

        md = generate_review_md(findings)
        self.assertIn("# 統合レビュー結果", md)
        self.assertIn("**問題A**", md)
        self.assertIn("箇所: a.py:1", md)
        self.assertEqual(
            summarize(findings),
            {"total": 2, "critical": 1, "major": 0, "minor": 1},
        )

    # ---- TASK-013: priority サブセクション見出しと二段ソートのテスト ----

    def test_severity_headings_preserved(self):
        """既存の severity 見出し (### 🔴 / 🟡 / 🟢) が温存されること。"""
        md = generate_review_md([
            _f(1, "critical", "致命A", priority="P1"),
        ])
        self.assertIn("### 🔴致命的問題", md)
        self.assertIn("### 🟡品質問題", md)
        self.assertIn("### 🟢改善提案", md)

    def test_priority_subsection_headings_rendered(self):
        """priority サブセクション見出し P1/P2/P3 が描画されること。"""
        findings = [
            _f(1, "critical", "致命P1", priority="P1"),
            _f(2, "critical", "致命P2", priority="P2"),
            _f(3, "critical", "致命P3", priority="P3"),
        ]
        md = generate_review_md(findings)
        self.assertIn("#### P1 (ルール合致)", md)
        self.assertIn("#### P2 (矛盾・齟齬)", md)
        self.assertIn("#### P3 (不要な複雑化)", md)

    def test_two_stage_sort_severity_then_priority(self):
        """二段ソート結果: critical+P1 → critical+P2 → major+P1 ... の順。"""
        # 入力順をバラバラに
        findings = [
            _f(1, "major", "品質P2", priority="P2"),
            _f(2, "critical", "致命P2", priority="P2"),
            _f(3, "minor", "改善P1", priority="P1"),
            _f(4, "critical", "致命P1", priority="P1"),
            _f(5, "major", "品質P1", priority="P1"),
        ]
        md = generate_review_md(findings)

        # title が登場する順序を確認
        title_order = []
        for t in ["致命P1", "致命P2", "品質P1", "品質P2", "改善P1"]:
            idx = md.find(t)
            self.assertNotEqual(idx, -1, f"title '{t}' not found in md")
            title_order.append((idx, t))
        title_order.sort()
        self.assertEqual(
            [t for _, t in title_order],
            ["致命P1", "致命P2", "品質P1", "品質P2", "改善P1"],
        )

    def test_priority_none_placed_at_severity_section_tail(self):
        """priority=None の finding は priority 区分なしで severity セクション末尾に配置される。"""
        findings = [
            _f(1, "critical", "致命None"),  # priority 未指定
            _f(2, "critical", "致命P1", priority="P1"),
            _f(3, "critical", "致命P2", priority="P2"),
        ]
        md = generate_review_md(findings)

        idx_p1_heading = md.find("#### P1 (ルール合致)")
        idx_p2_heading = md.find("#### P2 (矛盾・齟齬)")
        idx_none = md.find("致命None")
        idx_p1 = md.find("致命P1")
        idx_p2 = md.find("致命P2")

        # P1/P2 見出しは描画される
        self.assertNotEqual(idx_p1_heading, -1)
        self.assertNotEqual(idx_p2_heading, -1)
        # priority=None は P2 以降 (= severity セクションの末尾) に出現
        self.assertLess(idx_p1, idx_none)
        self.assertLess(idx_p2, idx_none)
        # かつ priority=None 用の見出しは出ない (P1/P2/P3 ラベル文言のみ存在)
        # ("None" や "不明" 等のサブ見出しを描画しないことを確認)
        self.assertNotIn("#### None", md)
        self.assertNotIn("#### 不明", md)

    def test_priority_subsection_not_rendered_when_absent(self):
        """その priority に finding が存在しない場合、サブ見出しは描画されない。"""
        findings = [
            _f(1, "critical", "致命P1", priority="P1"),
        ]
        md = generate_review_md(findings)
        self.assertIn("#### P1 (ルール合致)", md)
        self.assertNotIn("#### P2 (矛盾・齟齬)", md)
        self.assertNotIn("#### P3 (不要な複雑化)", md)

    def test_stable_sort_within_same_severity_and_priority(self):
        """同一 severity × 同一 priority 内では入力順 (stable) を保持する。"""
        findings = [
            _f(1, "critical", "致命A", priority="P1"),
            _f(2, "critical", "致命B", priority="P1"),
            _f(3, "critical", "致命C", priority="P1"),
        ]
        md = generate_review_md(findings)
        idx_a = md.find("致命A")
        idx_b = md.find("致命B")
        idx_c = md.find("致命C")
        self.assertLess(idx_a, idx_b)
        self.assertLess(idx_b, idx_c)

    def test_severity_section_index_resets(self):
        """連番カウンタは severity セクションごとにリセットされる。"""
        findings = [
            _f(1, "critical", "致命A", priority="P1"),
            _f(2, "critical", "致命B", priority="P2"),
            _f(3, "major", "品質A", priority="P1"),
        ]
        md = generate_review_md(findings)
        # critical セクション内は 1. / 2.、major セクション内は再び 1. となる
        self.assertIn("1. **致命A**", md)
        self.assertIn("2. **致命B**", md)
        self.assertIn("1. **品質A**", md)

    def test_empty_severity_section_shows_placeholder(self):
        """finding が存在しない severity セクションは「（なし）」プレースホルダ。"""
        md = generate_review_md([
            _f(1, "critical", "致命A", priority="P1"),
        ])
        # major / minor は空なので「（なし）」が出る
        self.assertIn("（なし）", md)


if __name__ == "__main__":
    unittest.main()
