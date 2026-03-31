# Doc Advisor

[![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Doc Advisorは、生成AIのコンテキストをクリーンに保つため、ドキュメントをインデックス化し、生成AIに必要なドキュメントのみを精選して渡します。

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

| カテゴリ | ディレクトリ | 用途             | 設定可能 |
| -------- | ------------ | ---------------- | -------- |
| rule     | `rules/`     | 開発ドキュメント | Yes      |
| spec     | `specs/`     | プロジェクト仕様 | Yes      |

### rule - 開発ドキュメント

自由形式の構造。任意のサブディレクトリ内の `.md` ファイルがインデックス化されます。

| コンテンツ種別       | 例                                  |
| -------------------- | ----------------------------------- |
| アーキテクチャルール | `rules/core/architecture.md`        |
| コーディング規約     | `rules/coding/naming_convention.md` |
| ワークフローガイド   | `rules/workflow/review_process.md`  |

### spec - プロジェクト仕様

パス内にサブディレクトリ名が含まれていれば、自動的に doc_type が判定されます。

| doc_type      | サブディレクトリ | 目的                                    | 設定可能 |
| ------------- | ---------------- | --------------------------------------- | -------- |
| `requirement` | `requirements/`  | 機能要件、ユースケース                  | Yes      |
| `design`      | `design/`        | 技術設計、アーキテクチャ決定            | Yes      |
| `plan`        | `plan/`          | プロジェクト計画（定義のみ、ToC対象外） | -        |

例:

- `specs/requirements/login.md` → requirement
- `specs/main/design/architecture.md` → design
- `specs/auth/oauth/requirements/api.md` → requirement

### ToC 生成の仕組み

#### 探索範囲

`specs/` 配下を再帰的に探索し、パスに `requirement` または `design` ディレクトリが含まれるファイルを対象とします。深さ制限はありません。

| パス例                               | 対象 | 理由                  |
| ------------------------------------ | ---- | --------------------- |
| `specs/feature1/requirements/app.md` | ✅   | `requirements` を含む |
| `specs/main/sub/design/api.md`       | ✅   | `design` を含む       |
| `specs/feature1/plan/task.md`        | ❌   | 対象外                |

#### plan が対象外の理由

`plan` ディレクトリは ToC の対象外です。理由：

1. **作業中に全文読む**: plan は実行時に全文参照するため、検索インデックスによる部分参照は不要
2. **定義済みの実行計画**: requirement/design は「何を作るか」の参照用、plan は「どう作るか」の定義済み実行計画

#### 処理時間

| 処理     | 実行者             | 速度     |
| -------- | ------------------ | -------- |
| 再帰探索 | Python (`os.walk`) | 高速     |
| 差分検出 | Python (SHA-256)   | 高速     |
| 内容解析 | Claude (LLM)       | **遅い** |
| 統合     | Python             | 高速     |

ボトルネックは LLM による解析です。インクリメンタルモード（デフォルト）では変更ファイルのみ処理することで最適化しています。

#### シンボリックリンク対応 (v3.2+)

すべてのスクリプトがディレクトリ走査時にシンボリックリンクを follow します。これにより、シンボリックリンク経由で外部ドキュメントを含めることができます：

```bash
# 例: シンボリックリンクで外部ドキュメントを含める
ln -s /path/to/external/docs rules/external
```

- シンボリックリンクのループは検出・防止されます（inode 追跡）
- 複数のシンボリックリンクで同じファイルを参照している場合、重複処理を回避します

## インストール

### 1. リポジトリをクローン

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

### 2. ターゲットプロジェクトをセットアップ

`setup.sh` をターゲットプロジェクトのパスで実行：

```bash
cd DocAdvisor-CC
./setup.sh /path/to/your-project
```

これにより、必要なファイルがプロジェクトにコピーされます：

```
your-project/
├── .doc_structure.yaml              # ドキュメント構造設定
└── .claude/
    ├── agents/            # ワーカーエージェント（toc-updater）
    ├── skills/
    │   ├── setup-doc-structure/
    │   │   └── SKILL.md   # ドキュメントディレクトリ自動分類スキル
    │   ├── query-rules/
    │   │   └── SKILL.md   # rules ドキュメント検索スキル
    │   ├── query-specs/
    │   │   └── SKILL.md   # specs ドキュメント検索スキル
    │   ├── create-rules-toc/
    │   │   └── SKILL.md   # rules ToC 生成スキル
    │   └── create-specs-toc/
    │       └── SKILL.md   # specs ToC 生成スキル
    └── doc-advisor/       # すべてのリソースとランタイム出力
        ├── docs/
        ├── scripts/
        └── toc/           # ToC ファイル
```

ターゲットプロジェクトに `.doc_structure.yaml` があれば、ドキュメントディレクトリは自動設定されます。
なければ、セットアップ後に Claude Code で `/setup-doc-structure` を実行してください。

セットアップ後にエージェントモデルを変更する場合：

```bash
bash .claude/doc-advisor/scripts/change_agent_model.sh <haiku|sonnet|opus|inherit>
```

### 3. Claude Code を起動

```bash
cd /path/to/your-project
claude
```

`--plugin-dir` フラグは不要です！すべてのファイルは既にプロジェクト内にあります。

### Makefile を使用（代替方法）

```bash
cd DocAdvisor-CC
make setup                            # 対話モード
make setup TARGET=/path/to/your-project  # ターゲット指定
```

## 使い方

### ToC 生成コマンド

```bash
# 開発ドキュメント（rules/）の ToC 生成
/create-rules-toc          # 差分更新（変更ファイルのみ処理）
/create-rules-toc --full   # 全ファイル再生成

# 要件定義書・設計書（specs/）の ToC 生成
/create-specs-toc          # 差分更新
/create-specs-toc --full   # 全ファイル再生成
```

### ドキュメント検索スキル

タスクに必要なドキュメントを自動特定：

```bash
/query-rules ユーザー認証機能の実装に必要な文書を特定
/query-specs 画面遷移に関する要件定義書を特定
```

### CLAUDE.md への推奨記載

プロジェクトの `CLAUDE.md` に以下を追記すると、Claude が自動的にドキュメントを参照するようになります：

```markdown
## 作業タスク実施の基本フロー [MANDATORY]

作業タスクを受け取ったら、以下のフローに従うこと：

1. ルール文書を特定
   /query-rules [タスク内容]

2. 要件定義書・設計書を特定
   /query-specs [タスク内容]

3. 必要となる文書セット**全て**を読む

4. 作業タスクを実行
```

## アーキテクチャ

### 設定ファイル

スクリプトは以下の設定ファイルを使用します：

- `.doc_structure.yaml`（プロジェクトルート）

### ToC 生成フロー

```
/create-*-toc
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

### ドキュメント検索フロー

```
/query-rules or /query-specs
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
DocAdvisor/
├── templates/
│   ├── agents/                 # ワーカーエージェントテンプレート
│   │   └── toc-updater.md
│   ├── skills/
│   │   ├── setup-doc-structure/
│   │   │   └── SKILL.md        # ドキュメントディレクトリ自動分類スキル
│   │   ├── query-rules/
│   │   │   └── SKILL.md        # rules ドキュメント検索スキル
│   │   ├── query-specs/
│   │   │   └── SKILL.md        # specs ドキュメント検索スキル
│   │   ├── create-rules-toc/
│   │   │   └── SKILL.md        # rules ToC 生成スキル
│   │   └── create-specs-toc/
│   │       └── SKILL.md        # specs ToC 生成スキル
│   └── doc-advisor/            # ToC 生成リソース
│       ├── docs/               # オーケストレータ、フォーマット、ワークフロー文書
│       └── scripts/            # Python スクリプト
├── setup.sh                    # プロジェクトセットアップスクリプト
├── Makefile                    # ビルド自動化
└── README.md
```

### ターゲットプロジェクト構造（セットアップ後）

```
your-project/
├── .doc_structure.yaml         # ドキュメント構造設定
├── .claude/
│   ├── agents/
│   │   └── toc-updater.md
│   ├── skills/
│   │   ├── setup-doc-structure/
│   │   │   └── SKILL.md        # ドキュメントディレクトリ自動分類スキル
│   │   ├── query-rules/
│   │   │   └── SKILL.md        # rules ドキュメント検索スキル
│   │   ├── query-specs/
│   │   │   └── SKILL.md        # specs ドキュメント検索スキル
│   │   ├── create-rules-toc/
│   │   │   └── SKILL.md        # rules ToC 生成スキル
│   │   └── create-specs-toc/
│   │       └── SKILL.md        # specs ToC 生成スキル
│   └── doc-advisor/            # すべてのリソースとランタイム出力
│       ├── docs/               # オーケストレータ、フォーマット、ワークフロー文書
│       ├── scripts/            # Python スクリプト
│       └── toc/                # ランタイム出力
│           ├── rules/          # rules の生成成果物
│           │   ├── rules_toc.yaml
│           │   ├── .toc_checksums.yaml
│           │   └── .toc_work/
│           └── specs/          # specs の生成成果物
│               ├── specs_toc.yaml
│               ├── .toc_checksums.yaml
│               └── .toc_work/
├── rules/                      # Rules ドキュメント（設定可能）
│   └── *.md                    # ドキュメントファイル
└── specs/                      # Specs ドキュメント（設定可能）
    ├── requirements/           # 要件定義書
    └── design/                 # 設計書
```

## 設定

### プロジェクト設定

プロジェクトルートの `.doc_structure.yaml` で管理します：

```yaml
# doc_structure_version: 3.0

rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - specs/
  doc_types_map:
    specs/requirements/: requirement
    specs/design/: design
    specs/plan/: plan
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

Doc Advisor 内部設定（ToC パス・チェックサムパス・作業ディレクトリ・並列数）はコードデフォルトで管理されており、このファイルには含まれません。

> **注**: システムファイル（`.toc_work/`, `*_toc.yaml`, `.toc_checksums.yaml`）は自動的に除外されます。
> **注**: 除外パターンはディレクトリパスに対して判定されます（ファイル名は対象外）。

### 設定のカスタマイズ

Claude Code で `/setup-doc-structure` を実行して自動検出・更新するか、直接編集：

```bash
nano /path/to/your-project/.doc_structure.yaml
```

## 処理モード

| モード      | 説明                                           |
| ----------- | ---------------------------------------------- |
| full        | 全ファイルをスキャンして ToC を再生成          |
| incremental | 変更ファイルのみ処理（SHA-256 ハッシュで検出） |
| 継続        | 中断された処理を再開                           |

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

### スキルが認識されない

ファイルが存在するか確認：

```bash
ls -la /path/to/your-project/.claude/skills/create-rules-toc/SKILL.md
ls -la /path/to/your-project/.claude/skills/create-specs-toc/SKILL.md
ls -la /path/to/your-project/.claude/doc-advisor/
ls -la /path/to/your-project/.claude/agents/
```

### ToC 生成が失敗する

1. ターゲットディレクトリがプロジェクトに存在するか確認
2. 設定のパスが正しいか確認
3. `.claude/doc-advisor/toc/{rules,specs}/.toc_work/` で復旧を確認

## v2.0（プラグインモード）からの移行

プラグインモード（`--plugin-dir`）を使用していた場合、setup.sh を実行してアップグレード：

```bash
./setup.sh /path/to/your-project
```

### アップグレード時の動作

**自動削除**（doc-advisor のレガシーファイル）:

- `.claude/commands/create-rules_toc.md`
- `.claude/commands/create-specs_toc.md`
- `.claude/skills/doc-advisor/`（削除、分割されたスキルに置き換え）
- `.claude/doc-advisor/docs/`（テンプレートから再作成）

**インストール**（v3.8+ 構造）:

- `.claude/agents/toc-updater.md`（統合ワーカーエージェント）
- `.claude/skills/setup-doc-structure/SKILL.md`（ドキュメントディレクトリ自動分類）
- `.claude/skills/query-rules/SKILL.md`（rules ドキュメント検索）
- `.claude/skills/query-specs/SKILL.md`（specs ドキュメント検索）
- `.claude/skills/create-rules-toc/SKILL.md`（rules ToC 生成）
- `.claude/skills/create-specs-toc/SKILL.md`（specs ToC 生成）
- `.claude/doc-advisor/docs/`
- `.claude/doc-advisor/scripts/`
- `.claude/doc-advisor/toc/rules/`（ToC 出力）
- `.claude/doc-advisor/toc/specs/`（ToC 出力）

**保持**（ユーザーのカスタムファイル）:

- `.claude/commands/your-custom-command.md`（他のコマンド）
- `.claude/agents/your-custom-agent.md`（doc-advisor 以外のエージェント）

### アップグレード後

1. Claude Code 起動時に `--plugin-dir` フラグを削除 - 全ファイルがプロジェクト内にあります。
2. ToC ファイルを再生成（パスが変更されたため）：
   ```bash
   /create-rules-toc --full
   /create-specs-toc --full
   ```

## ライセンス

MIT License
