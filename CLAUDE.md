# CLAUDE.md

> **Scope**: このファイルは **doc-advisor 自体を開発するためのリポジトリガイド** であり、エンドユーザの実行時コンテキストには **ロードされない**。リポジトリルートに置かれ、配布物（`plugins/doc-advisor/`）には含まれない。
>
> エンドユーザ向けの動作仕様は [`plugins/doc-advisor/skills/*/SKILL.md`](plugins/doc-advisor/skills/) / [`plugins/doc-advisor/workflows/`](plugins/doc-advisor/workflows/) / [`plugins/doc-advisor/formats/`](plugins/doc-advisor/formats/) / [`README.md`](README.md) に置く。本ファイルにランタイム前提の指示を書かないこと。

This file provides guidance to Claude Code (claude.ai/code) when working on **this repository's source code**.

## Project Overview

`doc-advisor` プラグイン本体のリポジトリ。Claude Code 公式仕様の 3 層構成（marketplace → plugin → skill）。リポジトリルートが marketplace（`.claude-plugin/marketplace.json`）、プラグイン実体は `plugins/doc-advisor/`（`.claude-plugin/plugin.json`）。

ToC（キーワード／メタデータ）でルール・仕様文書をインデックス化し、AI が必要なコンテキストを自動発見できるようにする。

詳細は [README.md](README.md) を参照。

## 重要規約 [MANDATORY]

- プロジェクトルール文書の参照には `query-db-rules` SKILL を使う
- プロジェクトルール文書の更新後には `update-db-rules` SKILL を使う
- プロジェクト仕様の参照には `query-db-specs` SKILL を使う
- プロジェクト仕様の更新後には `update-db-specs` SKILL を使う
- **ルールは `docs/rules/` で管理**: CLAUDE.md にルールを詰め込まない（コンテキスト肥大化防止）
- **設計文書は `docs/specs/**/{requirements,design}/` に保存**: plan モードで作成した重要設計は ID プレフィックス（REQ-, DES-, ADR-）で命名
- **プラグインランタイム文書の境界**: `plugins/doc-advisor/{workflows,formats}/` 配下は SKILL.md がランタイム Read する配布物。リポジトリルートの `docs/` 配下はプロジェクト自身のメタ文書（配布物に含めない）
- **文書間参照にパスを焼き込まない**: 「どのタスクで何を読むべきか」をタスク記述から動的に発見すること（＝パス参照の保守コスト爆発を無くすこと）こそ doc-advisor の存在意義。文書には「何に依存するか（概念・ID）」だけ残し、`docs/...md` のようなディレクトリパス直書きの "ここを見ろ" 参照は書かない（パスは改訂で腐り、ToC の動的発見を無意味化する）。参照先の発見は `query-docs` に委ねる
- **feature/fix PR では CHANGELOG.md・version 関連ファイルを編集しない**。リリースコミットでまとめて更新（`/forge:update-version` を使う）
- **`.toc_work/` 等の消えるべき一時物は `.gitignore` に入れない**。残存が `git status` に untracked として出ることで異常を検知できる
- **`docs/specs/base/design/` の ADR と DES は通し番号を共有**。`forge:next-spec-id` の出力を鵜呑みにせず ADR/DES 横断の最大番号+1 を使う
- **決定論的な定型処理（列挙・転記・集計・ファイル生成）は script 化する**。AI は判断のみ担い、手転記・手列挙をしない
- **agent/SKILL のプロンプト指示は混入点でなく出力構築点に 1 箇所だけ置く**。近接した複数箇所への同一指示は重複であり追記しない
- **`/forge:merge-specs` の統合先は「既存文書と同一主題か」で決める**。既存文書の改訂版にあたる一時文書は既存文書へ **fold**（内容を反映して統合）する。一時文書をそのまま昇格させて併存させるのは誤り。新規機能を定義する一時文書は base へ**分離文書として置き**、既存文書側は齟齬（構成の種数・一覧・値域・用語）だけを直す。いずれの場合も一時文書（`type: temporary-feature-*` と計画書）は残さず削除する（`additive_development_spec.md` §4 / merge-specs の純粋新規の扱い）

## Repository Layout

3 層構成。配布物は `plugins/doc-advisor/` 配下にまとめ、その階層が end user に `${CLAUDE_PLUGIN_ROOT}` として配布される。リポジトリルートには marketplace カタログとプロジェクト文書（配布対象外）のみを置く。

| Path                                             | 役割                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `.claude-plugin/marketplace.json`                | marketplace カタログ（`source: ./plugins/doc-advisor`）。`/plugin install` の入口   |
| `plugins/doc-advisor/.claude-plugin/plugin.json` | プラグインマニフェスト（`${CLAUDE_PLUGIN_ROOT}` = `plugins/doc-advisor/`）          |
| `plugins/doc-advisor/skills/{skill}/SKILL.md`    | 配布 SKILL（3 件: index-docs / query-docs / check-toc。ToC の生成・検索・鮮度確認） |
| `plugins/doc-advisor/agents/toc-updater.md`      | 配布 agent（ToC 更新の並列処理用）                                                  |
| `plugins/doc-advisor/scripts/`                   | SKILL から呼ばれる Python スクリプト                                                |
| `plugins/doc-advisor/workflows/`                 | SKILL がランタイム Read する手順文書                                                |
| `plugins/doc-advisor/formats/`                   | SKILL がランタイム Read するスキーマ文書                                            |
| `docs/rules/`                                    | プロジェクトルール（`query-docs` で参照）                                           |
| `docs/specs/base/`                               | doc-advisor 基盤仕様の要件・設計文書                                                |
| `docs/specs/common/`                             | 旧 bw-cc-plugins 由来の共通仕様（移行記録として保持）                               |
| `docs/readme/`                                   | ユーザ向けガイド（日英併記）                                                        |
| `tests/`                                         | 単体テスト・統合テスト                                                              |
| `.claude/`                                       | このリポジトリのローカル設定（プラグイン配布物ではない）                            |
| `.claude/skills/`                                | ローカル限定 skill（配布対象外: review-skill-description 等）                       |
| `.agents/skills/`                                | agent 向け補助 skill                                                                |
| `.doc_structure.yaml`                            | 上位層（forge 等）が rules/specs を解決するための設定（doc-advisor 自体は未使用）   |
| `.version-config.yaml`                           | バージョン一括更新設定                                                              |
| `dprint.jsonc`                                   | フォーマッタ設定                                                                    |
| `AGENTS.md`                                      | `CLAUDE.md` への symlink（Codex 等向け、内容は同一）                                |

## Information Sources

| 対象                           | 入口                                           |
| ------------------------------ | ---------------------------------------------- |
| ユーザ向け説明                 | `README.md` / `README_en.md`                   |
| プロジェクトルール             | `/forge:query-db-rules` → `docs/rules/`        |
| プロジェクト仕様（要件・設計） | `/forge:query-db-specs` → `docs/specs/`        |
| プラグイン内部仕様             | `plugins/doc-advisor/{workflows,formats}/*.md` |
| Claude Code / SDK / API 仕様   | `claude-code-guide` agent                      |
| 最新の変更意図                 | `git log main..HEAD` / `CHANGELOG.md`          |

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
# セッション限定でロード（plugin ルートを指定）
claude --plugin-dir ~/path/to/DocAdvisor/plugins/doc-advisor

# GitHub 経由
/plugin marketplace add BlueEventHorizon/DocAdvisor
/plugin install doc-advisor@DocAdvisor
```

## Testing [MANDATORY]

`plugins/doc-advisor/scripts/` 配下の Python スクリプトにはテストが必須。SKILL.md はテスト困難なため例外。
`.claude/` 配下のローカル skill はテスト対象外。

### テスト実行

```bash
# 一括実行
python3 -m unittest discover -s tests -p 'test_*.py' -v

# 特定モジュールのみ
python3 -m unittest tests.scripts.test_toc_utils -v
```

### 品質評価テスト

検索品質（ゴールデンセット）の場所・実行方法は [`DEVELOPMENT.md`](DEVELOPMENT.md) に集約。

## Debugging [MANDATORY]

コード読解による推論で 2〜3 回修正しても解決しない場合は、**ログ挿入で実際の状態を観測する**。推測に基づく修正を繰り返さず、`print()` / 変数ダンプで実際に何が起こっているかを確認してから次の修正を行う。観測後にログを除去すること。
