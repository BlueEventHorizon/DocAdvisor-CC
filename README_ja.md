# Doc Advisor (v3.0)

AI を活用したドキュメント管理と自動インデックス化された目次（ToC）生成。

## なぜ ToC（目次）が必要か

生成AIには構造的な限界があります：

- **Lost in the Middle**: 長いコンテキストの「真ん中」の情報は見落とされる
- **Attention Dilution**: 入力が長いほど各トークンへの注意が希薄化

**解決策**: 「全部読ませる」のではなく「必要なものだけ渡す」

Doc Advisor は、ドキュメントを事前にインデックス化し、タスクに必要なファイルだけをAIに渡します。

## 概要

Doc Advisor は、プロジェクトのドキュメントを自動的にインデックス化し、AI エージェントが必要な文書を素早く特定できるようにするツールです。

### 主な機能

- **自動 ToC 生成**: ドキュメントの内容を分析し、検索可能な構造化インデックスを自動生成
- **差分更新**: SHA-256 ハッシュで変更を検出し、変更されたファイルのみを処理
- **並列処理**: 最大5並列でドキュメント処理を高速化
- **中断耐性**: 処理中断時も完了分は保持、再開可能
- **プロジェクトベースのセットアップ**: すべてのファイルがプロジェクトにコピーされ、プラグインモード不要

## ドキュメントモデル

Doc Advisor は **rule** と **spec** の2つのカテゴリのドキュメントを管理します。

| カテゴリ | ディレクトリ | 用途 | 設定可能 |
|----------|--------------|------|----------|
| rule | `rules/` | 開発ドキュメント | Yes |
| spec | `specs/` | プロジェクト仕様 | Yes |

### rule - 開発ドキュメント

自由形式の構造。任意のサブディレクトリ内の `.md` ファイルがインデックス化されます。

| コンテンツ種別 | 例 |
|----------------|-----|
| アーキテクチャルール | `rules/core/architecture.md` |
| コーディング規約 | `rules/coding/naming_convention.md` |
| ワークフローガイド | `rules/workflow/review_process.md` |

### spec - プロジェクト仕様

パス内にサブディレクトリ名が含まれていれば、自動的に doc_type が判定されます。

| doc_type | サブディレクトリ | 目的 | 設定可能 |
|----------|------------------|------|----------|
| `requirement` | `requirements/` | 機能要件、ユースケース | Yes |
| `design` | `design/` | 技術設計、アーキテクチャ決定 | Yes |
| `plan` | `plan/` | プロジェクト計画（定義のみ、ToC対象外） | - |

例:
- `specs/requirements/login.md` → requirement
- `specs/main/design/architecture.md` → design
- `specs/auth/oauth/requirements/api.md` → requirement

## インストール

### 1. リポジトリをクローン

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor-CCPlugin.git
```

### 2. ターゲットプロジェクトをセットアップ

`setup.sh` をターゲットプロジェクトのパスで実行：

```bash
cd DocAdvisor-CCPlugin
./setup.sh /path/to/your-project
```

これにより、必要なファイルがプロジェクトにコピーされます：
```
your-project/.claude/
├── commands/          # コマンドファイル
├── agents/            # エージェント定義
├── skills/            # スキルモジュール
└── doc-advisor/
    ├── config.yaml    # プロジェクト設定
    └── docs/          # ToC フォーマット/ワークフロー文書
```

セットアップは対話形式で以下を聞いてきます：
- Rules ディレクトリ（デフォルト: `rules/`）
- Specs ディレクトリ（デフォルト: `specs/`）

### 3. Claude Code を起動

```bash
cd /path/to/your-project
claude
```

`--plugin-dir` フラグは不要です！すべてのファイルは既にプロジェクト内にあります。

### Makefile を使用（代替方法）

```bash
cd DocAdvisor-CCPlugin
make setup                            # 対話モード
make setup TARGET=/path/to/your-project  # ターゲット指定
```

## 使い方

### ToC 生成コマンド

```bash
# 開発ドキュメント（rules/）の ToC 生成
/create-rules_toc          # 差分更新（変更ファイルのみ処理）
/create-rules_toc --full   # 全ファイル再生成

# 要件定義書・設計書（specs/）の ToC 生成
/create-specs_toc          # 差分更新
/create-specs_toc --full   # 全ファイル再生成
```

### Advisor エージェント

タスクに必要なドキュメントを自動特定：

```
Task(subagent_type: rules-advisor, prompt: "ユーザー認証機能の実装に必要な文書を特定")
Task(subagent_type: specs-advisor, prompt: "画面遷移に関する要件定義書を特定")
```

## アーキテクチャ

### 設定ファイル

スクリプトは以下の設定ファイルを使用します：

- `.claude/doc-advisor/config.yaml`

### ToC 生成フロー

```
/create-*_toc
        |
        v
+-------------------------------------+
| 1. 変更検出 (SHA-256 ハッシュ)      |
|    チェックサム比較 → 変更分のみ    |
+------------------+------------------+
                   |
                   v
+-------------------------------------+
| 2. 並列処理 (最大5並列)             |
|    *-toc-updater agents             |
|    各エージェント: .md読込 → YAML出力|
+------------------+------------------+
                   |
                   v
+-------------------------------------+
| 3. マージ & 検証 → *_toc.yaml       |
+-------------------------------------+
```

### Advisor フロー

```
Task(subagent_type: *-advisor)
        |
        v
+-------------------+     +-------------------+
| *_toc.yaml 読込   |---->| 関連ドキュメント  |----> ファイルパス返却
|                   |     | 検索              |
+-------------------+     +-------------------+
```

## ディレクトリ構造

### テンプレートリポジトリ

```
DocAdvisor-CCPlugin/
├── templates/
│   ├── commands/               # コマンドテンプレート
│   │   ├── create-rules_toc.md
│   │   └── create-specs_toc.md
│   ├── agents/                 # エージェントテンプレート
│   │   ├── rules-advisor.md
│   │   ├── specs-advisor.md
│   │   ├── rules-toc-updater.md
│   │   └── specs-toc-updater.md
│   ├── skills/                 # スキルテンプレート
│   │   └── doc-advisor/        # ToC 生成スクリプト
│   └── doc-advisor/
│       └── docs/               # ToC フォーマット/ワークフロー文書
├── setup.sh                    # プロジェクトセットアップスクリプト
├── Makefile                    # ビルド自動化
└── README.md
```

### ターゲットプロジェクト構造（セットアップ後）

```
your-project/
├── .claude/
│   ├── commands/
│   │   ├── create-rules_toc.md
│   │   └── create-specs_toc.md
│   ├── agents/
│   │   ├── rules-advisor.md
│   │   ├── specs-advisor.md
│   │   ├── rules-toc-updater.md
│   │   └── specs-toc-updater.md
│   ├── skills/
│   │   └── doc-advisor/        # ToC 生成スクリプト
│   └── doc-advisor/
│       ├── config.yaml
│       └── docs/               # ToC フォーマット/ワークフロー文書
├── rules/                      # Rules ドキュメント（設定可能）
│   ├── rules_toc.yaml          # 生成された ToC インデックス
│   └── *.md                    # ドキュメントファイル
└── specs/                      # Specs ドキュメント（設定可能）
    ├── specs_toc.yaml          # 生成された ToC インデックス
    ├── requirements/           # 要件定義書
    └── design/                 # 設計書
```

## 設定

### プロジェクト設定

`.claude/doc-advisor/config.yaml` にあります：

```yaml
# === rules 設定 ===
rules:
  root_dir: rules
  toc_file: rules_toc.yaml
  checksums_file: .toc_checksums.yaml
  work_dir: .toc_work/

  patterns:
    target_glob: "**/*.md"
    exclude:
      - ".toc_work"
      - "rules_toc.yaml"
      - "reference"

  output:
    header_comment: "Development documentation search index for rules-advisor subagent"
    metadata_name: "Development Documentation Search Index"

# === specs 設定 ===
specs:
  root_dir: specs
  toc_file: specs_toc.yaml
  checksums_file: .toc_checksums.yaml
  work_dir: .toc_work/

  patterns:
    target_dirs:
      requirement: requirements
      design: design
    exclude:
      - ".toc_work"
      - ".toc_checksums.yaml"
      - "specs_toc.yaml"
      - "reference"
      - "/info/"

  output:
    header_comment: "Requirements and design document search index for specs-advisor subagent"
    metadata_name: "Requirements and Design Document Search Index"

# === 共通設定 ===
common:
  parallel:
    max_workers: 5
    fallback_to_serial: true
```

### 設定のカスタマイズ

プロジェクト設定ファイルを直接編集するか、セットアップを再実行：

```bash
# 対話形式で再セットアップ
./setup.sh /path/to/your-project

# または直接編集
nano /path/to/your-project/.claude/doc-advisor/config.yaml
```

## 処理モード

| モード | 説明 |
|--------|------|
| full | 全ファイルをスキャンして ToC を再生成 |
| incremental | 変更ファイルのみ処理（SHA-256 ハッシュで検出） |
| 継続 | 中断された処理を再開 |

## 必要要件

- Python 3（標準ライブラリのみ）
- Claude Code
- Bash シェル

## トラブルシューティング

### 設定が見つからないエラー

プロジェクトのセットアップを実行したか確認：
```bash
./setup.sh /path/to/your-project
```

### コマンドが認識されない

ファイルが存在するか確認：
```bash
ls -la /path/to/your-project/.claude/commands/
ls -la /path/to/your-project/.claude/agents/
```

### ToC 生成が失敗する

1. ターゲットディレクトリがプロジェクトに存在するか確認
2. 設定のパスが正しいか確認
3. `.toc_work/` ディレクトリで復旧を確認

## v2.0（プラグインモード）からの移行

プラグインモード（`--plugin-dir`）を使用していた場合：

1. プロジェクトで setup.sh を実行して新しいファイルをインストール
2. Claude Code 起動時に `--plugin-dir` フラグを削除
3. `.claude/doc-advisor/` 内の既存の `config.yaml` は保持されます

## ライセンス

MIT License
