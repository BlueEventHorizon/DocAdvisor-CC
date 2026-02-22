# CLAUDE.md

このファイルは、Claude Code がこのリポジトリで作業する際のガイダンスを提供します。

## プロジェクト概要

Doc Advisor は、Claude Code 向けのドキュメント検索基盤ツール。
プロジェクトのドキュメント（`.md`）を解析し、AI が検索可能な ToC（Table of Contents）YAML インデックスを自動生成する。

**このリポジトリの役割**: テンプレートとセットアップスクリプトを提供するインストーラー。
`templates/` 配下にコピー元テンプレート（プレースホルダー `{{...}}` 付き）があり、`setup.sh` でターゲットプロジェクトの `.claude/` 配下にコピー・変数置換される。

### アーキテクチャ

```
DocAdvisor-CC/
├── templates/          ← コピー元テンプレート（修正対象はここ）
│   ├── doc-advisor/    ← config, docs, scripts
│   ├── agents/         ← ワーカーエージェント定義
│   └── skills/         ← スキル定義
├── setup.sh            ← インストーラー（テンプレート → ターゲットへコピー・置換）
├── tests/              ← テスト用プロジェクト群（検証はここで行う）
├── specs/              ← Doc Advisor 自体の仕様書
└── rules/              ← Doc Advisor 自体の開発ルール
```

**`.claude/` について**: 本プロジェクト自体の開発用に、現行バージョンの Doc Advisor がインストールされている。修正対象ではない。テンプレートの修正は必ず `templates/` に対して行う。

## 必読ドキュメント

作業開始前に以下を必ず読むこと：

| ドキュメント | 内容 |
|--------------|------|
| `README.md` / `README_ja.md` | プロジェクト概要、設計意図、コマンド |
| `specs/requirements/**/*.md` | 要件定義書（実装の根拠） |

## 言語ルール

| 対象 | 言語 |
|------|------|
| CLAUDE.md | 日本語 |
| .claude/**/*.md | 日本語 |
| README_ja.md | 日本語 |
| meta/**/*.md | 日本語 |
| rules/**/*.md | 日本語 |
| specs/**/*.md | 日本語 |
| README.md | 英語 |
| templates/**/*.md | 英語 |
| その他 | 英語 |

## 開発ルール [必須]

- **要件定義書優先**: `specs/requirements/**/*.md` がすべてのドキュメント・実装に優先
- **不明点は人間に確認**: 推測より確認を優先
- **小さく試してから展開**: 1つを完成させてから次へ進む
- **品質最優先**: 複雑な正規表現での一括置換禁止、手抜きしない
- **外部仕様は必ず確認**: Claude Code プラグイン仕様など外部システムの仕様は、実装前に公式ドキュメントで確認すること

## Claude Code 仕様に関する作業 [必須]

Claude Code の仕様（commands, agents, skills, hooks, settings 等）に関わる作業を行う場合は、**必ず `claude-code-guide` エージェントを使用して最新の仕様を取得し、深く理解してから作業すること**。

```
Task(subagent_type: claude-code-guide, prompt: "調査したい内容")
```

理由:
- Claude Code の仕様は頻繁に更新される
- 古い知識に基づく実装は動作しない可能性がある
- 公式ドキュメントの最新情報を確認することで、正確な実装が可能になる

## ファイルヘッダー [必須]

新規作成ファイルの `Created by` は git 定義の作者名を使用:
```bash
git config user.name
```

## 主要ファイル

### テンプレート（setup.sh で対象プロジェクトにコピーされる）

| ファイル | 役割 |
|----------|------|
| `templates/doc-advisor/config.yaml` | プロジェクト設定テンプレート |
| `templates/doc-advisor/docs/*_toc_format.md` | ToC スキーマ定義（Single Source of Truth） |
| `templates/doc-advisor/docs/*_toc_update_workflow.md` | ToC 更新の詳細ワークフロー |
| `templates/doc-advisor/docs/*_orchestrator.md` | オーケストレーター手順 |
| `templates/doc-advisor/scripts/` | Python スクリプト群 |
| `templates/skills/query-{rules,specs}/SKILL.md` | ドキュメント検索スキル |
| `templates/skills/create-{rules,specs}-toc/SKILL.md` | ToC 生成スキル |
| `templates/agents/` | ワーカーエージェント（toc-updater） |

### プロジェクト固有

| ファイル | 役割 |
|----------|------|
| `setup.sh` | ターゲットプロジェクトへのセットアップスクリプト |
| `specs/requirements/` | Doc Advisor 自体の要件定義書 |
| `specs/design/` | Doc Advisor 自体の設計書 |
| `rules/` | 開発ルール文書 |

## 禁止事項

### システムディレクトリへの書き込み禁止

以下のディレクトリにファイルやディレクトリを作成してはいけない:

- `/tmp`
- `/var`
- `/etc`
- `/usr`
- `/` 直下全般

理由:
- セキュリティリスクがある
- 他のユーザーやプロセスと競合する可能性がある
- シンボリックリンク攻撃の対象になりやすい
- 予測可能な名前だと悪用される可能性がある

代替案:
- プロジェクトの隣のディレクトリに作成する
- ユーザーのワーキングディレクトリ配下で作業する
- どうしても一時ディレクトリが必要な場合は `mktemp -d` を使用する

### サンドボックス制限

Bash の `mkdir` コマンドはサンドボックス制限でエラーになる場合がある。

```
mkdir: /path/to/dir: Operation not permitted
```

**回避策**: Write ツールは親ディレクトリを自動作成するため、ディレクトリ作成が必要な場合は Write ツールで `.gitkeep` 等を作成する。

```
# NG: Bash mkdir
mkdir -p path/to/new/dir

# OK: Write ツールでファイル作成（ディレクトリも自動作成）
Write path/to/new/dir/.gitkeep
```

### シンボリックリンク配下の探索

ファイル検索は Glob ツールを優先するが、**Glob はシンボリックリンクを辿れない**。
`meta/`, `rules/`, `specs/`, `.claude/` がシンボリックリンクの場合、Glob の結果は空になる。

**対策**: シンボリックリンク配下の探索には `find -L` または `rg -L` を使うこと。

```bash
find -L specs -name "*.md" -type f
rg -L --files specs --glob "*.md"
```

<!-- doc-advisor-section-start -->
## Doc Advisor ルール [MANDATORY]

### ToC ファイルの直接修正禁止

`.claude/doc-advisor/toc/` 配下のファイルを直接編集・修正してはいけない。
ToC の生成・更新には、必ず Doc Advisor の Skill/Agent を使用すること：

- `/create-rules-toc` — rules の ToC を生成・更新
- `/create-specs-toc` — specs の ToC を生成・更新
<!-- doc-advisor-section-end -->
