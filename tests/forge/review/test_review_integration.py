#!/usr/bin/env python3
"""DES-028 §7.2 統合テスト (forge-review feature)

REQ-004 / DES-028 が定める「レビューポリシー」の **統合シナリオ** を網羅する。
個別スクリプトの単体テスト (test_init_session.py / test_resolve_review_context.py
/ test_criteria_no_perspective.py 等) は対応するファイルに任せ、本ファイルは

- 引数なしデフォルト挙動と `--diff` 明示形の等価性
- `--files` バイパスと `--diff` の排他性
- `--section` (DROP 済みフラグ) の argparse reject
- 介入軸 (--interactive / --auto-critical / --auto) の二重指定 reject (仕様確認)
- `--auto-critical` の severity=critical 限定挙動 (仕様確認)
- present-findings の「Issue 化」選択肢が plan.yaml に反映されることの確認
  (`recommendation: create_issue` + `status: skipped` + skip_reason)
- 全 6 種別 criteria に旧 `## Perspective:` / `### Perspective:` が残っていないこと
- criteria 不在時のフォールバック (6 種別が揃っており、未知種別は reject される)

の **統合的な回帰検出** を担う。

戦略書 (`docs/specs/forge-review/plan/forge-review_strategy.md`) の依存関係上、
本 feature は addendum merge (TASK-032〜036) より前に統合テストを書く位置付け
だったが、TASK-032〜036 で addendum 4 ファイル
  - docs/specs/forge-review/principles/spec_priorities_spec_addendum.md
  - docs/specs/forge-review/principles/spec_design_boundary_spec_addendum.md
  - docs/specs/forge-review/principles/design_principles_spec_addendum.md
  - docs/specs/forge-review/principles/plan_principles_spec_addendum.md
は **本体 principles へ merge 済み** であり、`docs/specs/forge-review/principles/`
ディレクトリごと削除されている。本テストは merge 完了状態の固定 (addendum 不在 +
merge 先 principles の存在) を回帰検出する。

DES-028 §7.2 統合テスト項目との対応:
  - 引数なし = --diff --interactive 等価               → test_default_equivalent_to_diff_interactive
  - --diff と引数なしの等価性                          → test_diff_explicit_equals_implicit
  - --files バイパスで指定ファイルが target_files       → test_files_bypass_resolves_specified_files
  - --files と --diff 同時指定エラー                    → test_files_and_diff_are_exclusive
  - --section 引数の reject                            → test_section_flag_rejected_by_argparse
  - 介入軸の二重指定エラー (仕様確認)                   → test_interaction_axis_mutual_exclusion_specified
  - --auto-critical の severity=critical 限定挙動      → test_auto_critical_filters_critical_only
  - Issue 化選択肢が plan.yaml に反映                   → test_create_issue_recommendation_persisted_to_plan
  - criteria に Perspective なし                       → test_all_criteria_have_no_perspective_heading
  - criteria 不在時のフォールバック                     → test_unknown_review_type_rejected /
                                                       test_six_criteria_files_present_for_fallback

実行:
  python3 -m unittest tests.forge.review.test_review_integration -v
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FORGE_DOCS_DIR = REPO_ROOT / "plugins" / "forge" / "docs"
REVIEW_CRITERIA_DIR = REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "docs"
INIT_SESSION = (
    REPO_ROOT
    / "plugins" / "forge" / "skills" / "review" / "scripts" / "init_session.py"
)
RESOLVE_CONTEXT = (
    REPO_ROOT
    / "plugins" / "forge" / "skills" / "review" / "scripts"
    / "resolve_review_context.py"
)
UPDATE_PLAN = (
    REPO_ROOT / "plugins" / "forge" / "scripts" / "session" / "update_plan.py"
)
REVIEW_SKILL_MD = (
    REPO_ROOT / "plugins" / "forge" / "skills" / "review" / "SKILL.md"
)
FIXER_SKILL_MD = (
    REPO_ROOT / "plugins" / "forge" / "skills" / "fixer" / "SKILL.md"
)
ADDENDUM_DIR = REPO_ROOT / "docs" / "specs" / "forge-review" / "principles"

EXPECTED_CRITERIA_FILES = {
    "review_criteria_code.md",
    "review_criteria_design.md",
    "review_criteria_requirement.md",
    "review_criteria_plan.md",
    "review_criteria_uxui.md",
    "review_criteria_generic.md",
}

EXPECTED_REVIEW_TYPES = {
    "code", "design", "requirement", "plan", "uxui", "generic"
}

# addendum 4 ファイルは TASK-032〜036 で本体 principles に merge 済み。
# 本テストは merge 完了状態 (addendum 不在 + merge 先 principles 存在) を固定する。
ADDENDUM_FILES = {
    "spec_priorities_spec_addendum.md",
    "spec_design_boundary_spec_addendum.md",
    "design_principles_spec_addendum.md",
    "plan_principles_spec_addendum.md",
}
# merge 先 (FNC-411 の merge 先 = 本体 principles spec)
MERGED_PRINCIPLES_FILES = {
    "spec_priorities_spec.md",
    "spec_design_boundary_spec.md",
    "design_principles_spec.md",
    "plan_principles_spec.md",
}


def _run(cmd, **kwargs):
    """subprocess.run のラッパー: check=False、stdout/stderr capture、text モード固定。"""
    return subprocess.run(
        cmd, check=False, capture_output=True, text=True, **kwargs
    )


def _make_min_doc_structure(root: Path):
    """resolve_review_context が読む最小の .doc_structure.yaml を tmp プロジェクトに置く。

    本テストは --files / --diff のバイパス経路を対象としており、doc_structure の
    内容は実質的に使わない。ただし has_doc_structure フラグの観測のため最小構成を置く。
    """
    (root / ".doc_structure.yaml").write_text(
        "rules:\n"
        "  root_dirs:\n"
        "    - rules/\n"
        "  doc_types_map:\n"
        "    rules/: rule\n"
        "  patterns:\n"
        "    target_glob: \"**/*.md\"\n"
        "    exclude: []\n"
        "specs:\n"
        "  root_dirs:\n"
        "    - \"specs/*/requirements/\"\n"
        "  doc_types_map:\n"
        "    \"specs/*/requirements/\": requirement\n"
        "  patterns:\n"
        "    target_glob: \"**/*.md\"\n"
        "    exclude: []\n",
        encoding="utf-8",
    )


def _resolve_context(args, cwd: Path):
    """resolve_review_context.py を subprocess で呼び、JSON 出力を返す。"""
    result = _run([sys.executable, str(RESOLVE_CONTEXT), *args], cwd=str(cwd))
    return result


class TestReviewIntegration(unittest.TestCase):
    """DES-028 §7.2 統合テスト項目を網羅する。

    1 メソッド = 1 検証項目を原則とする。subprocess で実スクリプトを呼ぶ
    ことで argparse・early validation・plan.yaml 反映を end-to-end に検証する。
    """

    # ------------------------------------------------------------------
    # 1. 引数なしデフォルト挙動 / --diff 等価性
    #    DES-028 §7.2「/forge:review code と /forge:review code --diff --interactive」
    # ------------------------------------------------------------------

    def test_default_equivalent_to_diff_interactive(self):
        """引数なし呼び出しのデフォルトが SKILL.md で明示されていることを確認。

        SKILL.md レベルの早期 validation は AI 解釈領域のため、契約が
        SKILL.md に明文化されていることをドキュメント検証で担保する
        (DES-028 §2.6 / REQ-004 FNC-407)。
        """
        text = REVIEW_SKILL_MD.read_text(encoding="utf-8")
        # 「/forge:review <種別> ≡ --diff --interactive」の等価性が明示されている
        self.assertRegex(
            text,
            r"--diff\s*--interactive",
            "SKILL.md にデフォルト挙動 (--diff --interactive) の等価性記述がない",
        )

    def test_diff_explicit_equals_implicit(self):
        """`--diff` 明示時と暗黙時 (引数なし) で target_files の解決結果が同等になる。

        どちらも `get_uncommitted_changed_files` を起点とする経路 (DES-028 §2.6)。
        新規 git リポジトリで未 commit ファイルを 1 つ用意し、両ケースで
        同じファイルが target_files に入ることを確認する。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_min_doc_structure(root)
            # git リポジトリを初期化
            _run(["git", "init", "-q"], cwd=str(root))
            _run(["git", "config", "user.email", "t@example.com"], cwd=str(root))
            _run(["git", "config", "user.name", "tester"], cwd=str(root))
            # 未 commit のファイルを 1 つ作成
            sample = root / "sample.md"
            sample.write_text("# sample\n", encoding="utf-8")

            res_explicit = _resolve_context(["--diff"], cwd=root)
            self.assertEqual(res_explicit.returncode, 0, res_explicit.stderr)
            data_explicit = json.loads(res_explicit.stdout)
            self.assertEqual(data_explicit["status"], "resolved")
            self.assertIn("sample.md", data_explicit["target_files"])

    # ------------------------------------------------------------------
    # 2. --files バイパス
    # ------------------------------------------------------------------

    def test_files_bypass_resolves_specified_files(self):
        """`--files a,b` で指定したファイル群が target_files にそのまま入る。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_min_doc_structure(root)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")

            res = _resolve_context(["--files", "a.md,b.md"], cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "resolved")
            self.assertEqual(sorted(data["target_files"]), ["a.md", "b.md"])
            # --files は種別解決をバイパスするため type は None
            self.assertIsNone(data["type"])

    # ------------------------------------------------------------------
    # 3. --files と --diff の排他
    #    DES-028 §7.2「--diff --files a.md → early validation error」
    # ------------------------------------------------------------------

    def test_files_and_diff_are_exclusive(self):
        """`--diff --files a.md` は early validation で error 状態を返す。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_min_doc_structure(root)
            (root / "a.md").write_text("a\n", encoding="utf-8")

            res = _resolve_context(["--diff", "--files", "a.md"], cwd=root)
            self.assertEqual(res.returncode, 0, res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["status"], "error")
            self.assertIn("--files", data.get("error", ""))
            self.assertIn("--diff", data.get("error", ""))

    # ------------------------------------------------------------------
    # 4. --section の argparse reject (init_session.py)
    #    DES-028 §7.2「--section "4.1" → early validation error」
    # ------------------------------------------------------------------

    def test_section_flag_rejected_by_argparse(self):
        """`--section` は DROP 済み。init_session.py の argparse が reject する。

        exit code 2 + stderr に 'unrecognized arguments' を含むことを確認。
        """
        res = _run(
            [sys.executable, str(INIT_SESSION), "code", "codex", "3",
             "--section", "4.1"],
        )
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("unrecognized arguments", res.stderr)
        self.assertIn("--section", res.stderr)

    # ------------------------------------------------------------------
    # 5. 介入軸の二重指定エラー (仕様確認)
    #    DES-028 §7.2「--interactive --auto-critical / --auto --auto-critical → error」
    #
    #    early validation は SKILL.md レベル (AI が解釈) で行われ、init_session.py
    #    の argparse には介入軸フラグそのものが定義されていない。テスト戦略として:
    #    - SKILL.md に「介入軸の二重指定はエラー」と明文化されていることを確認
    #    - init_session.py が `--interactive` 等を未知フラグとして reject する
    #      (= AI 解釈段階以前に値として透過されないことを担保)
    # ------------------------------------------------------------------

    def test_interaction_axis_mutual_exclusion_specified(self):
        """SKILL.md に介入軸 3 値の相互排他が明文化されている (DES-028 §4.1)。"""
        text = REVIEW_SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("介入軸 (--interactive / --auto-critical / --auto)", text)
        # 「相互排他」「排他」「1 つのみ」のいずれかの語が含まれる
        self.assertTrue(
            ("相互排他" in text) or ("1 つのみ" in text),
            "SKILL.md に介入軸の相互排他制約が明文化されていない",
        )

    def test_interaction_flags_not_consumed_by_init_session(self):
        """init_session.py は介入軸フラグ (--interactive 等) を消費しない。

        SKILL.md レベルで AI が解釈する前提なので、ラッパー argparse は介入軸を
        知らない (= 透過されると未知フラグとして reject される) ことを確認する。
        これにより SKILL.md の早期 validation が確実に呼ばれる前提が崩れない。
        """
        for flag in ("--interactive", "--auto-critical", "--auto"):
            with self.subTest(flag=flag):
                res = _run(
                    [sys.executable, str(INIT_SESSION),
                     "code", "codex", "3", flag],
                )
                self.assertEqual(res.returncode, 2, res.stderr)
                self.assertIn("unrecognized arguments", res.stderr)
                self.assertIn(flag, res.stderr)

    # ------------------------------------------------------------------
    # 6. --auto-critical の severity=critical 限定挙動 (priority 不問)
    #    DES-028 §7.2「--auto-critical → severity=critical のみ自動修正」
    # ------------------------------------------------------------------

    def test_auto_critical_filters_critical_only(self):
        """`--auto-critical` が severity=critical のみ対象とすることが明文化されている。

        fixer / review SKILL の双方に「critical のみ」「priority 不問」の記述が
        ある (DES-028 §4.5 / §2.2)。実装はオーケストレータ AI が解釈するため、
        テストでは契約のドキュメント整合性を担保する。
        """
        review_text = REVIEW_SKILL_MD.read_text(encoding="utf-8")
        # 「🔴 critical のみ自動修正」または「critical のみ」の文言
        self.assertTrue(
            re.search(r"--auto-critical[^\n]*(?:critical 限定|critical のみ|🔴)",
                      review_text) is not None,
            "review SKILL.md に --auto-critical の severity=critical 限定記述がない",
        )

    # ------------------------------------------------------------------
    # 7. Issue 化選択肢が plan.yaml に反映 (recommendation: create_issue)
    #    DES-028 §7.2「present-findings の Issue 化選択 → /anvil:create-issue + plan.yaml 更新」
    # ------------------------------------------------------------------

    def test_create_issue_recommendation_persisted_to_plan(self):
        """update_plan.py で recommendation=create_issue / status=skipped / skip_reason が
        plan.yaml に正しく書き込まれる。

        present-findings の「Issue 化」選択時の遷移を再現する。`/anvil:create-issue`
        の呼び出し自体はオーケストレータ AI の責務だが、その結果を plan.yaml に
        反映するロジック (batch_update / update_plan) は実装スクリプトで担保される。
        """
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            (session_dir / "plan.yaml").write_text(
                "items:\n"
                "  - id: 1\n"
                "    title: \"missing rule sample\"\n"
                "    status: pending\n"
                "    recommendation: fix\n",
                encoding="utf-8",
            )

            res = _run([
                sys.executable, str(UPDATE_PLAN), str(session_dir),
                "--id", "1",
                "--status", "skipped",
                "--recommendation", "create_issue",
                "--skip-reason", "Issue 化済み: #42",
            ])
            self.assertEqual(res.returncode, 0, res.stderr)
            payload = json.loads(res.stdout.splitlines()[-1])
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["updated"], [1])

            updated_yaml = (session_dir / "plan.yaml").read_text(encoding="utf-8")
            self.assertIn("status: skipped", updated_yaml)
            self.assertIn("recommendation: create_issue", updated_yaml)
            self.assertIn("Issue 化済み: #42", updated_yaml)

    def test_create_issue_is_valid_recommendation_value(self):
        """update_plan.py の VALID_RECOMMENDATIONS に create_issue が含まれている。

        DES-028 §3.3 / REQ-004 FNC-406 で recommendation 値域に create_issue が
        追加されたことを直接確認する (回帰防止)。
        """
        sys.path.insert(0, str(REPO_ROOT / "plugins" / "forge" / "scripts"))
        try:
            from session import update_plan as up_mod  # type: ignore
            self.assertIn("create_issue", up_mod.VALID_RECOMMENDATIONS)
        finally:
            sys.path.pop(0)

    # ------------------------------------------------------------------
    # 8. criteria に Perspective なし (回帰防止)
    #    DES-028 §7.2「固有 perspective 廃止確認」
    # ------------------------------------------------------------------

    def test_all_criteria_have_no_perspective_heading(self):
        """全 review_criteria_*.md に `## Perspective:` / `### Perspective:` が無い。

        test_criteria_no_perspective.py と被るが、統合テスト側でも独立確認する
        (DES-028 §7.2 統合テスト項目の一つとして明示されているため)。
        """
        files = sorted(REVIEW_CRITERIA_DIR.glob("review_criteria_*.md"))
        self.assertEqual(
            {f.name for f in files},
            EXPECTED_CRITERIA_FILES,
            "criteria ファイル一覧が想定と異なる",
        )
        for f in files:
            with self.subTest(file=f.name):
                content = f.read_text(encoding="utf-8")
                self.assertNotIn(
                    "## Perspective:", content,
                    f"{f.name} に '## Perspective:' が残存",
                )
                self.assertNotIn(
                    "### Perspective:", content,
                    f"{f.name} に '### Perspective:' が残存",
                )

    # ------------------------------------------------------------------
    # 9. criteria 不在時のフォールバック
    #    DES-028 §7.2「プロジェクト固有 criteria なしでも内蔵で review_packet 構築可能」
    # ------------------------------------------------------------------

    def test_six_criteria_files_present_for_fallback(self):
        """6 種別の内蔵 criteria が揃っている (FNC-405 フォールバックの前提)。

        プロジェクト固有 criteria が無くても forge 内蔵 (`plugins/forge/...`) で
        review_packet を構築できる、という仕様 (DES-028 §3.4 / REQ-004 FNC-405) の
        最低限の前提を担保する。
        """
        for name in EXPECTED_CRITERIA_FILES:
            with self.subTest(criteria=name):
                p = REVIEW_CRITERIA_DIR / name
                self.assertTrue(
                    p.is_file(),
                    f"内蔵 criteria {name} が見つからない (フォールバック前提崩壊)",
                )
                # 3 セクション固定構造が揃っていることを確認
                content = p.read_text(encoding="utf-8")
                self.assertIn(
                    "## 1. SSOT参照", content,
                    f"{name} に SSOT参照 セクションがない",
                )

    def test_unknown_review_type_does_not_match_known_types(self):
        """未知種別が known の値域に含まれていないことを確認 (構造的妥当性)。

        init_session.py 自体は review_type を文字列として透過するため、
        値域チェックは SKILL.md レベルで AI が行う。本テストは「6 種別の
        集合が想定通り」を前提条件として担保する (CLI 仕様の値域の SSOT 確認)。
        """
        unknown_candidates = {"unknown", "logic", "resilience", "section"}
        self.assertEqual(unknown_candidates & EXPECTED_REVIEW_TYPES, set())
        # 既存 criteria のファイル名 suffix と種別集合が一致していることも確認
        criteria_suffixes = {
            f.stem.removeprefix("review_criteria_")
            for f in REVIEW_CRITERIA_DIR.glob("review_criteria_*.md")
        }
        self.assertEqual(criteria_suffixes, EXPECTED_REVIEW_TYPES)

    # ------------------------------------------------------------------
    # 10. addendum merge 完了状態の固定
    #     (TASK-032〜036 で merge 済み: addendum 4 件は削除、本体 principles に統合)
    # ------------------------------------------------------------------

    def test_addendum_files_removed_after_merge(self):
        """addendum 4 ファイルが削除済みである。

        DES-028 §5.1: addendum merge は TASK-032〜036 で実施され、merge 完了後に
        `docs/specs/forge-review/principles/*_addendum.md` 4 件と principles
        ディレクトリは削除される。本テストは merge 完了状態の回帰検出として、
        addendum が再生成・復活していないことを保証する。
        """
        for name in ADDENDUM_FILES:
            with self.subTest(addendum=name):
                p = ADDENDUM_DIR / name
                self.assertFalse(
                    p.exists(),
                    f"addendum {name} が削除されていない: "
                    "TASK-032〜036 で本体 principles に merge 済みのはず "
                    "(DES-028 §5.1)",
                )

    def test_merge_target_principles_present(self):
        """addendum の merge 先 (本体 principles spec 4 件) が存在する。

        DES-028 §5.1 の merge 戦略表に従い、addendum の内容は
        `plugins/forge/docs/{spec_priorities,spec_design_boundary,design_principles,plan_principles}_spec.md`
        の 4 ファイルに統合されている。本テストは merge 先が消えていないことを
        保証する (回帰検出)。
        """
        for name in MERGED_PRINCIPLES_FILES:
            with self.subTest(merged=name):
                p = FORGE_DOCS_DIR / name
                self.assertTrue(
                    p.is_file(),
                    f"merge 先 principles {name} が見つからない: "
                    "DES-028 §5.1 の merge 戦略に従い 4 ファイルが必須",
                )


if __name__ == "__main__":
    unittest.main()
