#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ゴールデンセット精度検証テスト（FNC-002 対応）

search_docs.py を subprocess で呼び出し、queries.yaml に定義された
正解文書（expected_paths）が検索結果に全件含まれるかを検証する。
見落とし 1 件でもテスト失敗とする。

前提条件:
- API キー環境変数が設定されていること（`OPENAI_API_DOCDB_KEY` 優先、未設定時 `OPENAI_API_KEY` にフォールバック。DES-007 統一仕様）。双方未設定時は skipTest
- Embedding インデックスが構築済みであること（未構築時は skipTest）
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

# テスト対象スクリプトのパス
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "plugins" / "doc-advisor" / "scripts"
SEARCH_DOCS_SCRIPT = SCRIPTS_DIR / "search_docs.py"

# search_docs.py の get_index_path() を使用するため
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# ゴールデンセット YAML のパス
GOLDEN_SET_DIR = Path(__file__).resolve().parent
QUERIES_YAML = GOLDEN_SET_DIR / "queries.yaml"


def load_queries_yaml(yaml_path):
    """queries.yaml を標準ライブラリのみでパースする。

    簡易 YAML パーサー: ゴールデンセットの構造のみ対応。
    PyYAML を使用しない（外部依存禁止）。

    Returns:
        dict: {"specs": [...], "rules": [...]} 形式

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        ValueError: パース結果が空（カテゴリなし、またはエントリなし）の場合
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    result = {}
    current_category = None
    current_entry = None
    current_key = None  # 現在処理中のキー（リスト項目の親キー）

    for line in lines:
        stripped = line.rstrip()

        # コメントまたは空行をスキップ
        if not stripped or stripped.lstrip().startswith("#"):
            continue

        # インデント計算
        indent = len(line) - len(line.lstrip())

        # カテゴリ行（indent=0, "specs:" or "rules:"）
        if indent == 0 and stripped.endswith(":"):
            current_category = stripped[:-1].strip()
            result[current_category] = []
            current_entry = None
            current_key = None
            continue

        # エントリの開始（"- query:" パターン）
        if current_category is not None and stripped.lstrip().startswith("- query:"):
            value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            current_entry = {
                "query": value,
                "expected_paths": [],
                "note": "",
                "known_failure": "",
            }
            result[current_category].append(current_entry)
            current_key = None
            continue

        # エントリ内のキー
        if current_entry is not None:
            content = stripped.lstrip()

            # リスト項目（"- " で始まる値）
            if content.startswith("- ") and current_key == "expected_paths":
                val = content[2:].strip().strip('"').strip("'")
                current_entry["expected_paths"].append(val)
                continue

            # キー: 値のペア
            if ":" in content:
                key, _, value = content.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key == "expected_paths":
                    current_key = "expected_paths"
                    # 値がインラインの場合
                    if value and value != "":
                        current_entry["expected_paths"].append(value)
                    continue
                elif key == "note":
                    current_entry["note"] = value
                    current_key = None
                    continue
                elif key == "query":
                    current_entry["query"] = value
                    current_key = None
                    continue
                elif key == "known_failure":
                    current_entry["known_failure"] = value
                    current_key = None
                    continue

    if not result:
        raise ValueError(f"load_queries_yaml: '{yaml_path}' をパースしましたがカテゴリが1件も見つかりませんでした。ファイル形式を確認してください。")
    for category, entries in result.items():
        if not entries:
            raise ValueError(f"load_queries_yaml: カテゴリ '{category}' にエントリがありません。'{yaml_path}' の内容を確認してください。")
    return result


def _check_index_exists(category):
    """指定カテゴリのインデックスが存在するか確認する。

    search_docs.py の get_index_path() を使い、config 設定に従ったパスを参照する。

    Args:
        category: "specs" または "rules"

    Returns:
        bool: インデックスが存在すれば True
    """
    project_root = _get_project_root()
    if project_root is None:
        return False
    from search_docs import get_index_path
    index_path = get_index_path(category, project_root)
    return index_path.exists()


def _get_project_root():
    """プロジェクトルートを返す。

    CLAUDE_PROJECT_DIR 環境変数が設定されていればそちらを優先。
    設定されていなければ .git を上方探索する。

    Returns:
        Path or None
    """
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root)

    # .git ディレクトリを上方探索
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _run_search(category, query, project_root):
    """search_docs.py を subprocess で実行し、結果を返す。

    Args:
        category: "specs" または "rules"
        query: 検索クエリ文字列
        project_root: プロジェクトルートのパス

    Returns:
        dict: search_docs.py の JSON 出力をパースした dict
    """
    cmd = [
        sys.executable,
        str(SEARCH_DOCS_SCRIPT),
        "--category", category,
        "--query", query,
        "--skip-stale-check",
    ]
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(project_root)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env=env,
        timeout=60,
    )

    if result.returncode != 0:
        # エラー出力も含めてパース試行
        output = result.stdout.strip()
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass
        return {
            "status": "error",
            "error": f"search_docs.py exited with code {result.returncode}: {result.stderr}",
        }

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error": f"JSON パースエラー: {e}\nstdout: {result.stdout}",
        }


class TestGoldenSet(unittest.TestCase):
    """ゴールデンセット精度検証テスト。

    queries.yaml から全エントリを動的にロードし、
    各クエリの検索結果に expected_paths が全件含まれるかを検証する。
    """

    @classmethod
    def setUpClass(cls):
        """テスト全体の前提条件チェック"""
        # ゴールデンセットの読み込み（API 不要なバリデーションテストでも使用）
        cls.queries = load_queries_yaml(QUERIES_YAML)

        # API キーチェック（OPENAI_API_DOCDB_KEY 優先、未設定時 OPENAI_API_KEY フォールバック。DES-007 / FNC-004 KEY-01）
        cls.api_key = (
            os.environ.get("OPENAI_API_DOCDB_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        cls.skip_reason = None

        if not cls.api_key:
            cls.skip_reason = "OPENAI_API_DOCDB_KEY / OPENAI_API_KEY のいずれも設定されていないためスキップ"
            return

        # プロジェクトルートの解決
        cls.project_root = _get_project_root()
        if cls.project_root is None:
            cls.skip_reason = "プロジェクトルートが見つからないためスキップ"

    def _skip_if_no_api(self):
        """API キーが必要なテストの前提条件チェック"""
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def _run_category_tests(self, category):
        """指定カテゴリのゴールデンセットを全件検証する。

        Args:
            category: "specs" または "rules"
        """
        # インデックス存在チェック
        if not _check_index_exists(category):
            self.skipTest(
                f"{category} の Embedding インデックスが未構築のためスキップ。"
                f"embed_docs.py --category {category} を実行してください。"
            )

        entries = self.queries.get(category, [])
        self.assertGreater(
            len(entries), 0,
            f"queries.yaml の {category} セクションにエントリがありません",
        )

        all_failures = []
        known_failures = []     # xfail: known_failure 指定エントリの見落とし（許容）
        unexpected_passes = []  # xpass: known_failure なのに全件ヒット（marker 除去を促す）

        for entry in entries:
            query = entry["query"]
            expected_paths = entry["expected_paths"]
            note = entry.get("note", "")
            known_failure = entry.get("known_failure", "")

            result = _run_search(category, query, self.project_root)

            if result.get("status") != "ok":
                # 検索エラーは recall ミスとは別の実害であり、known_failure でも常に失敗扱い
                all_failures.append(
                    f"  クエリ: {query}\n"
                    f"  エラー: {result.get('error', 'unknown error')}"
                )
                continue

            # 検索結果のパスを取得
            result_paths = [r["path"] for r in result.get("results", [])]

            # expected_paths が全件含まれるか検証
            missing = [p for p in expected_paths if p not in result_paths]
            if missing:
                if known_failure:
                    # 既知未達: fail させず xfail として記録（追跡先を明示）
                    known_failures.append(
                        f"  クエリ: {query} (既知未達, 追跡: {known_failure})\n"
                        f"  見落とし: {missing}"
                    )
                    continue
                all_failures.append(
                    f"  クエリ: {query} ({note})\n"
                    f"  見落とし: {missing}\n"
                    f"  検索結果: {result_paths[:10]}{'...' if len(result_paths) > 10 else ''}"
                )
            elif known_failure:
                # known_failure 指定なのに全件ヒット → 解消された可能性。marker 除去を促す
                unexpected_passes.append(
                    f"  クエリ: {query} (known_failure: {known_failure} だが全件ヒット → "
                    f"queries.yaml の known_failure を除去してください)"
                )

        # xfail / xpass は情報として出力し、テストは緑のままにする
        if known_failures:
            print(
                f"\n[golden-set] {category}: 既知未達 {len(known_failures)} 件を xfail として許容:\n"
                + "\n".join(known_failures),
                file=sys.stderr,
            )
        if unexpected_passes:
            print(
                f"\n[golden-set] {category}: known_failure の解消を検出 (xpass) {len(unexpected_passes)} 件:\n"
                + "\n".join(unexpected_passes),
                file=sys.stderr,
            )

        if all_failures:
            self.fail(
                f"{category} カテゴリで {len(all_failures)} 件の見落としが発生:\n"
                + "\n".join(all_failures)
            )

    def test_specs_golden_set(self):
        """specs カテゴリのゴールデンセット精度検証"""
        self._skip_if_no_api()
        self._run_category_tests("specs")

    def test_rules_golden_set(self):
        """rules カテゴリのゴールデンセット精度検証"""
        self._skip_if_no_api()
        self._run_category_tests("rules")

    def test_queries_yaml_minimum_count(self):
        """queries.yaml に最低 10 件のクエリがあることを確認"""
        total = 0
        for category in ("specs", "rules"):
            entries = self.queries.get(category, [])
            total += len(entries)
            self.assertGreaterEqual(
                len(entries), 5,
                f"{category} カテゴリのクエリが 5 件未満です（現在 {len(entries)} 件）",
            )
        self.assertGreaterEqual(
            total, 10,
            f"クエリ合計が 10 件未満です（現在 {total} 件）",
        )

    def test_queries_yaml_has_expected_paths(self):
        """各エントリに expected_paths が 1 件以上あることを確認"""
        for category in ("specs", "rules"):
            for entry in self.queries.get(category, []):
                self.assertGreater(
                    len(entry.get("expected_paths", [])),
                    0,
                    f"クエリ '{entry['query']}' に expected_paths がありません",
                )


class TestLoadQueriesYaml(unittest.TestCase):
    """queries.yaml パーサーの単体テスト"""

    def test_load_queries_yaml(self):
        """queries.yaml を正しくパースできること"""
        queries = load_queries_yaml(QUERIES_YAML)

        # specs と rules の両カテゴリが存在
        self.assertIn("specs", queries)
        self.assertIn("rules", queries)

        # 各カテゴリに 5 件以上
        self.assertGreaterEqual(len(queries["specs"]), 5)
        self.assertGreaterEqual(len(queries["rules"]), 5)

        # 各エントリの構造チェック
        for category in ("specs", "rules"):
            for entry in queries[category]:
                self.assertIn("query", entry)
                self.assertIn("expected_paths", entry)
                self.assertIsInstance(entry["query"], str)
                self.assertIsInstance(entry["expected_paths"], list)
                self.assertGreater(len(entry["expected_paths"]), 0)

    def test_known_failure_parsed(self):
        """known_failure フィールドをパースできること（#96 追跡用 xfail marker）"""
        import tempfile

        yaml_content = """\
specs:
  - query: "既知未達クエリ"
    expected_paths:
      - "docs/specs/some/missing.md"
    note: "xfail テスト"
    known_failure: "#96"
  - query: "通常クエリ"
    expected_paths:
      - "docs/specs/some/found.md"
    note: "通常"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            queries = load_queries_yaml(tmp_path)
        finally:
            import os as _os
            _os.unlink(tmp_path)

        specs = queries["specs"]
        self.assertEqual(specs[0]["known_failure"], "#96")
        # known_failure を持たないエントリは空文字（デフォルト）
        self.assertEqual(specs[1]["known_failure"], "")

    def test_inline_expected_paths(self):
        """expected_paths のインライン形式（1行で値を書く形式）を正しくパースできること"""
        import tempfile

        yaml_content = """\
specs:
  - query: "テストクエリ"
    expected_paths: "docs/specs/some/file.md"
    note: "インライン形式テスト"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            queries = load_queries_yaml(tmp_path)
        finally:
            import os as _os
            _os.unlink(tmp_path)

        self.assertIn("specs", queries)
        self.assertEqual(len(queries["specs"]), 1)

        entry = queries["specs"][0]
        self.assertEqual(entry["query"], "テストクエリ")
        self.assertIsInstance(entry["expected_paths"], list)
        self.assertEqual(entry["expected_paths"], ["docs/specs/some/file.md"])
        self.assertEqual(entry["note"], "インライン形式テスト")


if __name__ == "__main__":
    unittest.main()
