# CLAUDE.md

> **Scope**: このファイルは **doc-advisor 自体を開発するためのリポジトリガイド** であり、エンドユーザの実行時コンテキストには **ロードされない**。プラグイン利用者は本ファイルを参照しない（インストール先には配布されるが Claude Code が plugin context として読み込まない）。
>
> エンドユーザ向けの動作仕様は [`skills/*/SKILL.md`](skills/) / [`workflows/`](workflows/) / [`formats/`](formats/) / [`README.md`](README.md) に置く。本ファイルにランタイム前提の指示を書かないこと。

This file provides guidance to Claude Code (claude.ai/code) when working on **this repository's source code**.

## Project Overview

`doc-advisor` プラグイン本体のリポジトリ。Claude Code 公式仕様の単一プラグイン構成（リポジトリルートに `.claude-plugin/plugin.json`）。

ToC（キーワード）と Embedding（セマンティック）の2層検索でルール・仕様文書をインデックス化し、AI が必要なコンテキストを自動発見できるようにする。

詳細は [README.md](README.md) を参照。

## 重要規約 [MANDATORY]

- **作業開始時に `/query-rules` を実行**: プロジェクトルールを最初に確認する。`docs/rules/` を検索
- **ルールは `docs/rules/` で管理**: CLAUDE.md にルールを詰め込まない（コンテキスト肥大化防止）
- **設計文書は `docs/specs/doc-advisor/{requirements,design}/` に保存**: plan モードで作成した重要設計は ID プレフィックス（REQ-, DES-, ADR-）で命名
- **プラグインランタイム文書の境界**: `workflows/` `formats/` 配下は SKILL.md がランタイム Read する配布物。`docs/` 配下はプロジェクト自身のメタ文書

## Repository Layout

単一プラグイン構成。リポジトリルート全体が `${CLAUDE_PLUGIN_ROOT}` として end user に配布される。

| Path                         | 役割                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------- |
| `.claude-plugin/plugin.json` | プラグインマニフェスト                                                              |
| `skills/{skill}/SKILL.md`    | 配布 SKILL（4 件: create-rules-toc / create-specs-toc / query-rules / query-specs） |
| `agents/toc-updater.md`      | 配布 agent（ToC 更新の並列処理用）                                                  |
| `scripts/`                   | SKILL から呼ばれる Python スクリプト                                                |
| `workflows/`                 | SKILL がランタイム Read する手順文書                                                |
| `formats/`                   | SKILL がランタイム Read するスキーマ文書                                            |
| `docs/rules/`                | プロジェクトルール（`/query-rules` 対象）                                           |
| `docs/specs/doc-advisor/`    | doc-advisor の要件・設計文書                                                        |
| `docs/specs/common/`         | 旧 bw-cc-plugins 由来の共通仕様（移行記録として保持）                               |
| `docs/readme/`               | ユーザ向けガイド（日英併記）                                                        |
| `tests/`                     | 単体テスト・統合テスト・golden set                                                  |
| `.claude/`                   | このリポジトリのローカル設定（プラグイン配布物ではない）                            |
| `.claude/skills/`            | ローカル限定 skill（配布対象外: swap-doc-config 等）                                |
| `.agents/skills/`            | agent 向け補助 skill                                                                |
| `.doc_structure.yaml`        | このリポジトリ自身の rules/specs 検索設定                                           |
| `.version-config.yaml`       | バージョン一括更新設定                                                              |
| `dprint.jsonc`               | フォーマッタ設定                                                                    |
| `AGENTS.md`                  | `CLAUDE.md` への symlink（Codex 等向け、内容は同一）                                |

## Information Sources

| 対象                           | 入口                                       |
| ------------------------------ | ------------------------------------------ |
| ユーザ向け説明                 | `README.md` / `README_en.md`               |
| プロジェクトルール             | `/doc-advisor:query-rules` → `docs/rules/` |
| プロジェクト仕様（要件・設計） | `/doc-advisor:query-specs` → `docs/specs/` |
| プラグイン内部仕様             | `workflows/*.md`, `formats/*.md`           |
| Claude Code / SDK / API 仕様   | `claude-code-guide` agent                  |
| 最新の変更意図                 | `git log main..HEAD` / `CHANGELOG.md`      |

## Development

外部依存なし。Python は標準ライブラリのみで動作。

### フォーマット

JSON / TOML / Markdown / YAML は [dprint](https://dprint.dev/) でフォーマット。設定は `dprint.jsonc`。

```bash
dprint fmt      # フォーマット適用
dprint check    # チェックのみ
```

### プラグインのローカルテスト

```bash
# セッション限定でロード
claude --plugin-dir /Users/moons/data/dev/moons/ai_tools/DocAdvisor

# GitHub 経由
/plugin marketplace add BlueEventHorizon/DocAdvisor
/plugin install doc-advisor@DocAdvisor
```

## Testing [MANDATORY]

`scripts/` 配下の Python スクリプトにはテストが必須。SKILL.md はテスト困難なため例外。
`.claude/` 配下のローカル skill はテスト対象外。

### テスト実行

```bash
# 一括実行
python3 -m unittest discover -s tests -p 'test_*.py' -v

# 特定モジュールのみ
python3 -m unittest tests.scripts.test_toc_utils -v
```

### 品質評価テスト

検索品質（precision/recall）は `tests/goldenset_test/` および `tests/golden_set/queries.yaml` で測定する。詳細は `tests/golden_set/test_golden_set.py` を参照。

## Debugging [MANDATORY]

コード読解による推論で 2〜3 回修正しても解決しない場合は、**ログ挿入で実際の状態を観測する**。推測に基づく修正を繰り返さず、`print()` / 変数ダンプで実際に何が起こっているかを確認してから次の修正を行う。観測後にログを除去すること。
