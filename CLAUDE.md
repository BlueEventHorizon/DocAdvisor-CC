# CLAUDE.md

このファイルは、Claude Code がこのリポジトリで作業する際のガイダンスを提供します。

## プロジェクト概要

Doc Advisor は、Claude Code 向けのドキュメント検索基盤ツール。
プロジェクトのドキュメント（`.md`）を解析し、AI が検索可能な ToC（Table of Contents）YAML インデックスを自動生成する。

**このリポジトリの役割**:

1. bw-cc-plugins のプラグインを仲介し、ターゲットプロジェクトにインストールする
2. bw-cc-plugins のプレリリース品質ゲートとして、リリース前の機能・品質テストを実施する

`setup.sh --source` で bw-cc-plugins から直接読み取り、パス変換を行ってコピーする。bw-cc-plugins は**読み取り専用**（修正禁止）。

### アーキテクチャ

```
bw-cc-plugins (develop)             プレリリース（読み取り専用）
├── plugins/doc-advisor/ ─┐
├── plugins/doc-db/      ─┤
├── plugins/forge/       ─┤
└── tests/               ─┤ L0: ユニットテスト実行
                           ↓
DocAdvisor/                プレリリーステスト + インストーラー
├── setup.sh               ← インストーラー（ソース → 変換 → ターゲットへコピー）
├── test_claude_setup/     ← setup.sh インストールテスト
├── test_codex/            ← Codex 環境テスト
├── test_claude_skills/    ← L1: 自動テスト / L2: 機能テスト
├── specs/                 ← Doc Advisor 自体の仕様書 + テスト仕様書
└── rules/                 ← Doc Advisor 自体の開発ルール
                           ↓ テスト合格 → bw-cc-plugins main にリリース
                           ↓
target-project/.claude/    インストール先（実体ファイル）
```

**変換内容**: `${CLAUDE_PLUGIN_ROOT}/` → `.claude/doc-advisor/`、`/doc-advisor:` → `/`、`/forge:setup-doc-structure` → `/setup-doc-structure`

**`.claude/` について**: 本プロジェクト自体の開発用に、Doc Advisor がインストールされている。修正対象ではない。

## 必読ドキュメント

作業開始前に以下を必ず読むこと：

| ドキュメント                 | 内容                                 |
| ---------------------------- | ------------------------------------ |
| `README.md` / `README_en.md` | プロジェクト概要、設計意図、コマンド |
| `specs/requirements/**/*.md` | 要件定義書（実装の根拠）             |
| `specs/test/TST-001_doc_db_functional_test.md` | doc-db 機能テスト仕様書 |

## 言語ルール

| 対象              | 言語   |
| ----------------- | ------ |
| CLAUDE.md         | 日本語 |
| .claude/**/*.md   | 日本語 |
| README.md         | 日本語 |
| meta/**/*.md      | 日本語 |
| rules/**/*.md     | 日本語 |
| specs/**/*.md     | 日本語 |
| README_en.md      | 英語   |
| setup.sh          | 英語   |
| その他            | 英語   |

## セッション開始時の確認 [必須]

セッション開始時（このリポジトリで最初の作業に入る前）に、必ず以下を確認しユーザーに報告すること。

### bw-cc-plugins submodule のブランチ確認

`bw-cc-plugins` submodule のブランチは **通常は `main`**（リリース済み安定版）。
`develop` の場合はプレリリーステスト対象を意味する。
気付かずに作業すると、安定版ではなく未リリース版のソースを target にインストールしてしまう恐れがある。

確認コマンド:

```bash
git -C bw-cc-plugins branch --show-current
```

報告ルール:

- `main` の場合: 先頭に 🟢 を 1 つだけ付け、一行で「🟢 bw-cc-plugins: main（通常）」と報告
- `main` 以外（`develop` 等）の場合: 先頭に 🟡 を 1 つだけ付け、太字で「**🟡 bw-cc-plugins が `<branch>` です（通常は main）。このまま作業を進めますか？**」とユーザーに確認する
- detached HEAD・ブランチ取得失敗の場合も同様に 🟡 付きで警告し、現在の commit hash を併記する

> 注: Claude Code は応答テキスト内の文字色（ANSI / HTML / CSS）をレンダリングしない仕様のため、視覚的強調は絵文字 🟡 と太字のみで行う。

ユーザーの明示的な指示なくブランチを切り替えてはならない。

## 開発ルール [必須]

- **タスク開始時に `/query-rules` を実行する**: 新しいタスクに取り掛かる前にルール文書を確認すること
- **要件定義書優先**: `specs/requirements/**/*.md` がすべてのドキュメント・実装に優先
- **不明点は人間に確認**: 推測より確認を優先
- **小さく試してから展開**: 1つを完成させてから次へ進む
- **品質最優先**: 複雑な正規表現での一括置換禁止、手抜きしない
- **外部仕様は必ず確認**: Claude Code プラグイン仕様など外部システムの仕様は、実装前に公式ドキュメントで確認すること

## bw-cc-plugins のバグ発見時 [必須]

bw-cc-plugins は**読み取り専用**であり、このリポジトリから直接修正してはいけない。
バグを発見した場合は、以下の手順で修正依頼書を作成し、ユーザーに報告すること。

### 手順

1. `specs/bug-reports/` 配下に修正依頼書を作成する
2. ファイル名: `BR-<連番3桁>_<簡潔な概要>.md`（例: `BR-001_cross_plugin_ref_transform.md`）
3. 連番は既存ファイルから自動採番する

### 修正依頼書テンプレート

```markdown
# BR-<ID>: <タイトル>

## 対象プラグイン

<プラグイン名（例: doc-db, anvil, forge, doc-advisor）>

## 対象ファイル

- `plugins/<plugin>/path/to/file`

## 現象

<バグの具体的な内容>

## 再現手順

1. <手順>

## 期待される動作

<正しい動作>

## 実際の動作

<バグの動作>

## 暫定対処（setup.sh 側）

<setup.sh で行った回避策があれば記載。なければ「なし」>

## 提案する修正

<bw-cc-plugins 側での修正案>
```

### 注意

- bw-cc-plugins を直接修正しないこと（読み取り専用）
- setup.sh で回避可能な場合は回避策を先に実装し、修正依頼書にも記録する
- ユーザーに報告し、bw-cc-plugins 管理 AI への伝達を依頼する

## bw-cc-plugins プレリリーステスト [必須]

### このリポジトリのテスト上の役割

bw-cc-plugins は `main` にリリースしないと一般のターゲットプロジェクトでテストできない。
しかしテストしていないものをリリースすべきではない。
**このジレンマを解消するのが DocAdvisor の役割である。**

DocAdvisor は bw-cc-plugins の `develop` ブランチを submodule として参照できるため、
リリース前の機能・品質テストを実施する唯一の場所となる。
この AI は、bw-cc-plugins の**プレリリース品質ゲート**として機能する責務を持つ。

```
bw-cc-plugins (develop)
  ↓ submodule
DocAdvisor ← ここでプレリリーステストを実施
  ↓ テスト合格
bw-cc-plugins (main) ← リリース
  ↓ setup.sh
target-project ← 一般ユーザーが利用
```

### テスト方式

DocAdvisor 本体を「テスト用ターゲットプロジェクト」として使用する。
`setup.sh` でプラグインをインストールし、store/restore パターンで
`.doc_structure.yaml` をテスト用フィクスチャに差し替えて、
インストール済みスクリプト・スキルをテスト専用ドキュメントに対して実行する。

```
DocAdvisor/
├── .claude/
│   ├── doc-advisor/scripts/   ← setup.sh でインストール済み
│   ├── doc-db/scripts/        ← setup.sh でインストール済み
│   └── skills/                ← setup.sh でインストール済み
├── .doc_structure.yaml        ← store/restore でテスト用に差し替え
├── test_claude_skills/
│   ├── fixtures/              ← テスト専用ドキュメント（仮想プロジェクトの文書）
│   │   ├── rules/
│   │   └── specs/
│   ├── test_doc_structure.yaml ← store 時にルートにコピーするテンプレート
│   └── init_fixtures.sh       ← テスト環境の初期化スクリプト
```

テスト環境の詳細設計: `specs/test/DES-TST-001_test_environment_design.md`

bw-cc-plugins の内部テスト（`bw-cc-plugins/tests/`）は bw-cc-plugins 自身の開発環境で実行するものであり、
DocAdvisor の責務ではない。DocAdvisor は**インストール後の成果物が正しく動作するか**を検証する。

### テスト層

| 層 | 内容 | API キー |
| --- | --- | --- |
| **L1: 自動テスト** | tempdir + API モックで再現可能なテスト（`test_claude_skills/`） | 不要 |
| **L2: 機能テスト** | store/restore + インストール済みスクリプトで実 API 実行 | 必須 |
| **L3: 品質テスト** | ゴールデンセットで recall/precision を測定・比較 | 必須 |

全層とも DocAdvisor 本体で実行する。テスト対象はインストール済みの `.claude/` 配下のスクリプト。

### プラグイン別テスト仕様

| プラグイン | テスト仕様書 | テストスキル | フィクスチャ |
| --- | --- | --- | --- |
| doc-db | `specs/test/TST-001_doc_db_functional_test.md` | `/test-doc-db` | `test_claude_skills/fixtures/` |

今後、他のプラグイン（doc-advisor, forge 等）のテスト仕様書・スキル・フィクスチャも同様に追加する。

### L3: 品質テスト

ゴールデンセットを用いた検索品質の定量評価。
bw-cc-plugins 側の要件定義書に準拠する:

- **NFR-004**: recall が doc-advisor の ToC/Embedding 方式と同等以上
- **FNC-007**: precision/recall/false negative を測定しレポート生成

現状: `evaluate.py` は未実装（テスト骨格のみ）。ゴールデンセットも未作成。
bw-cc-plugins 側で実装され次第、DocAdvisor でプレリリーステストとして実行する。

### テスト実行のタイミング

以下の場合にプレリリーステストを実施する:

1. bw-cc-plugins の `develop` ブランチが更新されたとき
2. ユーザーからリリース前テストを指示されたとき
3. 新しいプラグインや機能が追加されたとき

### API キーの方針

doc-db は現在 `OPENAI_API_KEY` を使用しているが、汎用キーは権限が強すぎるため、
将来的に制約を高めた **`OPENAI_API_BWCC_KEY`** を定義予定。
必要な権限（`/v1/embeddings`, `/v1/chat/completions`）は bw-cc-plugins 側の AI と協議して決定する。
移行後はテスト仕様書と関連スクリプトの環境変数名を更新すること。

## setup.sh / シェルスクリプト開発ルール

- **`sed -i` は macOS/Linux 非互換** — `awk` + `mv` を使用すること
  - macOS は `sed -i ''`、Linux は `sed -i` で動作が異なる
  - 代替: `awk '{gsub(/old/, "new")} 1' file > file.tmp && mv file.tmp file`
- **zsh 環境での heredoc** — `/bin/bash -c` でラップすること

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

### ソース（bw-cc-plugins、読み取り専用）

setup.sh が以下のソースから読み取り、変換してターゲットにコピーする:

| ソース | 内容 |
| ------ | ---- |
| `bw-cc-plugins/plugins/doc-advisor/agents/` | toc-updater エージェント |
| `bw-cc-plugins/plugins/doc-advisor/skills/` | query-*, create-*-toc, create-code-index, query-code |
| `bw-cc-plugins/plugins/doc-advisor/docs/` | ToC フォーマット、ワークフロー定義 |
| `bw-cc-plugins/plugins/doc-advisor/scripts/` | Python スクリプト群（Embedding, コードインデックス含む） |
| `bw-cc-plugins/plugins/forge/skills/setup-doc-structure/` | 初期設定スキル |
| `bw-cc-plugins/plugins/forge/scripts/doc_structure/` | ディレクトリ分類スクリプト |

### プロジェクト固有

| ファイル | 役割 |
| -------- | ---- |
| `setup.sh` | ソース → 変換 → ターゲットへのインストーラー |
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
