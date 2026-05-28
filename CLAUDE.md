# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Code プラグインのマーケットプレイスリポジトリ。4 プラグインを格納・配布する。

- **forge** (v0.1.1) — ドキュメントライフサイクルツール。要件定義・設計・計画書の作成、コード・文書レビュー、自動修正に対応
- **doc-advisor** (v0.3.0) — AI 検索可能なドキュメントインデックス。ToC キーワード検索と Embedding セマンティック検索の2層構造
- **doc-db** (v0.0.2) — 見出し chunk の Hybrid 検索（Embedding + Lexical + LLM Rerank）。doc-advisor とは併用・補完
- **anvil** — GitHub 連携（commit / PR / Issue 作成・実装）（`/anvil:commit`, `/anvil:create-pr`, `/anvil:create-issue`, `/anvil:impl-issue`）

全体像・スキル一覧・ワークフロー図は [README.md](README.md) を参照。

## 重要規約

- **全ての作業開始時に `/query-rules` を実行**: 新しい作業（タスク）に取り掛かる前に `/query-rules` でプロジェクトルールを確認する [MANDATORY]
- **ルールは `docs/rules/` で管理**: CLAUDE.md にルールを極力書かない（コンテキスト肥大化防止）
  - ルールを読むための必要な入り口となる記述は許容される(query-xxx SKILLを使う、など）
- **設計文書の保存**: plan モードで作成した重要な設計文書は `docs/specs/forge/**/requirements/`, `docs/specs/forge/**/design/` に保存する
- **forge 内蔵知識ベースの更新**: `/update-forge-toc` で `/forge:query-forge-rules` の検索インデックス（`plugins/forge/toc/rules/rules_toc.yaml`）を再生成する

## Repository Layout

| Path                                              | 役割                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------- |
| `.claude-plugin/marketplace.json`                 | マーケットプレイスマニフェスト                                            |
| `plugins/{plugin}/.claude-plugin/plugin.json`     | 各プラグインマニフェスト                                                  |
| `plugins/{plugin}/skills/{skill}/SKILL.md`        | スキル定義（frontmatter + 本文）                                          |
| `plugins/{plugin}/scripts/`                       | スキルから呼ばれる Python / Bash                                          |
| `plugins/{plugin}/docs/`                          | プラグイン内部仕様（forge は `/forge:query-forge-rules` 対象）            |
| `plugins/forge/toc/rules/rules_toc.yaml`          | forge 内蔵知識ベースの ToC                                                |
| `docs/rules/`                                     | プロジェクトルール（`/query-rules` 対象）                                 |
| `docs/specs/{plugin}/{requirements,design,plan}/` | プラグインごとの仕様文書（`/query-specs` 対象）                           |
| `docs/readme/`                                    | ユーザー向けガイド（日英併記、`guide_*_ja.md`）                           |
| `docs/references/`                                | 外部参考資料                                                              |
| `tests/{common,forge,doc_advisor}/`               | プラグイン別テスト                                                        |
| `meta/`                                           | 研究・評価・ゴールデンセット（git 管理外、下記ルール参照）                |
| `.claude/settings.json`                           | 権限・hooks 設定（プロジェクトレベル）                                    |
| `.claude/skills/`                                 | ローカル限定 skill（配布対象外、`update-forge-toc` 等）                   |
| `.agents/skills/`                                 | agent 向け skill                                                          |
| `.doc_structure.yaml`                             | rules/specs のパス解決設定                                                |
| `.version-config.yaml`                            | バージョン一括更新の対象設定                                              |
| `dprint.jsonc`                                    | フォーマッタ設定（JSON/TOML/Markdown/YAML）                               |
| `AGENTS.md`                                       | `CLAUDE.md` へのシンボリックリンク（Codex 向け、内容は CLAUDE.md と同一） |

### meta/ ディレクトリのルール [MANDATORY]

`meta/` は研究・評価・ゴールデンセット用の作業領域であり、**いつでも削除される可能性がある**。

- `plugins/` / `tests/` / `docs/` 配下のコード・文書は `meta/` 内のファイルに依存してはならない
- `meta/` 内のスクリプトが `plugins/` のモジュールを呼び出すのは許容される（逆方向は禁止）
- SKILL として配布しない（ユーザー環境に `meta/` は存在しない）

## Information Sources

タスクに応じて以下の入口を使う:

| 対象                                                       | 入口                                                                                                                             |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| プロジェクト全体の鳥瞰                                     | `README.md`（ワークフロー図 + 全スキル一覧 + トリガー句）                                                                        |
| 仕様駆動開発の思想・What/How 境界                          | `docs/readme/guide_sdd_ja.md`                                                                                                    |
| 各スキルの挙動・引数・使用例                               | `docs/readme/forge/guide_{create_docs,implement,review,setup,uxui_design}_ja.md` / `docs/readme/guide_{anvil,doc-advisor}_ja.md` |
| プロジェクトルール（実装・文書・CLI・SKILL 作成）          | `/query-rules` → `docs/rules/`                                                                                                   |
| プロジェクト仕様（要件/設計/計画）                         | `/query-specs` → `docs/specs/`                                                                                                   |
| forge 内部仕様（ID体系・フォーマット・原則・レビュー基準） | `/forge:query-forge-rules` → `plugins/forge/docs/`                                                                               |
| Claude Code / SDK / API 仕様                               | `claude-code-guide` agent                                                                                                        |
| 最新の変更意図                                             | `git log main..HEAD` / `CHANGELOG.md`                                                                                            |

## Development

ビルドシステム・パッケージマネージャーは使用していない。Python スクリプトは標準ライブラリのみで動作する（外部依存なし）。

### フォーマット

JSON / TOML / Markdown / YAML は [dprint](https://dprint.dev/) でフォーマット。設定は `dprint.jsonc`。

```bash
dprint fmt          # フォーマット適用
dprint check        # チェックのみ
```

### プラグインのローカルテスト

```bash
# セッション限定でプラグインをロード
claude --plugin-dir ./plugins/forge

# マーケットプレイス経由
/plugin marketplace add BlueEventHorizon/bw-cc-plugins
/plugin install forge@bw-cc-plugins
```

### スクリプト動作確認

```bash
# レビュー対象の自動検出
python3 plugins/forge/skills/review/scripts/resolve_review_context.py [対象パス]

# ディレクトリスキャン（メタデータ JSON 出力）
python3 plugins/forge/scripts/doc_structure/classify_dirs.py [プロジェクトルート]
```

## Debugging [MANDATORY]

コード読解による推論で 2〜3 回修正しても解決しない場合は、**ログ挿入で実際の状態を観測する**。推測に基づく修正を繰り返さず、`print()` / 変数ダンプで実際に何が起こっているかを確認してから次の修正を行う。観測後にログを除去すること。

## Testing [MANDATORY]

`plugins/` 配下の Python スクリプトにはテストが必須。SKILL.md はテスト困難なため例外。
`.claude/` 配下のローカルスキル・スクリプトはテスト対象外。

### テストの配置

`tests/` にプラグイン名・スキル名で分類:

```
tests/
├── common/                 # プラグイン横断（マニフェスト整合性等）
├── forge/
│   ├── review/
│   └── scripts/
└── {plugin}/               # 新プラグイン追加時も同構造
```

### テスト実行

```bash
# 一括実行
python3 -m unittest discover -s tests -p 'test_*.py' -v

# 特定モジュールのみ
python3 -m unittest tests.forge.review.test_xxx -v
```

### 品質評価テスト

ユニットテストはバグがないことを保証する。**検索品質**（精度・再現率）は `meta/test_docs/` で測定する（git 管理外、ローカルのみ）。

- doc-db / Embedding / ToC の方式を同一ゴールデンセットで比較評価
- 評価スクリプト: `meta/test_docs/` 配下（`run_docdb_test.py` / `run_search_test.py` / `evaluate_toc_results.py` 等）
- 詳細・実行手順は `meta/test_docs/README.md`
