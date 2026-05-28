# 文書作成ガイド

要件定義 → 設計 → 計画の 3 段階で開発文書を作成する。各スキルは前段階の成果物を入力とし、AI レビュー → ToC 更新 → commit の共通完了処理で締める。

```
start-requirements → start-design → start-plan → start-implement
 (何を作るか)         (どう作るか)     (いつ作るか)   (作る)
```

## 共通の仕組み

### コンテキスト収集

3 つのスキルは共通のコンテキスト収集パターンを採用する。文書作成前に、並列 Agent が以下を収集する:

| Agent       | 収集対象                     | 出力              |
| ----------- | ---------------------------- | ----------------- |
| specs agent | 仕様書（要件定義書・設計書） | `refs/specs.yaml` |
| rules agent | プロジェクトルール文書       | `refs/rules.yaml` |
| code agent  | 既存実装・参照コード         | `refs/code.yaml`  |

### 完了処理

文書作成後は以下を順次実行する:

1. `/forge:review {type} --auto` — AI レビュー + 自動修正
2. `/forge:update-db-specs` — ToC 更新（利用可能な場合）
3. `/anvil:commit` — commit/push 確認

---

## start-requirements

要件定義書を作成する。3 つのモードに対応し、入力源が異なる。

```
/forge:start-requirements [feature] [--mode interactive|reverse-engineering|from-figma] [--new|--add]
```

| 引数      | 説明                             |
| --------- | -------------------------------- |
| `feature` | Feature 名（省略時は対話で確定） |
| `--mode`  | モード指定（省略時は選択肢提示） |
| `--new`   | 新規アプリ                       |
| `--add`   | 既存アプリへの機能追加           |

### モード選択ガイド

| モード                | 入力源                 | いつ使うか                       | 前提条件              |
| --------------------- | ---------------------- | -------------------------------- | --------------------- |
| `interactive`         | ユーザーとの対話       | ゼロから要件を定義したいとき     | `.doc_structure.yaml` |
| `reverse-engineering` | 既存ソースコード       | 既存コードを文書化したいとき     | ソースコード          |
| `from-figma`          | Figma デザインファイル | デザインから要件を抽出したいとき | Figma MCP 対応環境    |

### 使用例

```bash
# ゼロから対話で要件定義
/forge:start-requirements user-auth --mode interactive --new

# 既存コードから要件を逆算
/forge:start-requirements dashboard --mode reverse-engineering --add

# Figma デザインから要件抽出
/forge:start-requirements product-catalog --mode from-figma --new
```

### 実行フロー

1. モード・Feature 名・新規/追加の確定
2. セッション作成（ブラウザでリアルタイム進捗表示）
3. コンテキスト収集（並列）
4. モード別ワークフロー実行（対話 / ソース解析 / Figma 解析）
5. 完了処理（レビュー → ToC → commit）

### 出力

`specs/{feature}/requirements/` に要件定義書（Markdown）を生成。ID 体系:

| プレフィックス | 種別                 |
| -------------- | -------------------- |
| APP-xxx        | アプリ概要・全体方針 |
| SCR-xxx        | 画面仕様             |
| FNC-xxx        | 機能仕様             |
| NFR-xxx        | 非機能要件           |

### 参考ドキュメント

- `plugins/forge/docs/requirement_format.md` — 要件定義書テンプレート
- `plugins/forge/docs/spec_format.md` — ID 分類カタログ
- `plugins/forge/docs/spec_design_boundary_spec.md` — 要件/設計の境界ガイド

---

## start-design

要件定義書から設計書を作成する。既存実装資産の再利用を重視し、不要な新規作成を防ぐ。

```
/forge:start-design [feature]
```

| 引数      | 説明                             |
| --------- | -------------------------------- |
| `feature` | Feature 名（省略時は対話で確定） |

### いつ使うか

- 要件定義書が完成した後
- アーキテクチャ・モジュール構成を文書化したいとき

### 実行フロー

1. Feature 名の確定
2. **コンテキスト収集**（3 Agent 並列）
   - 要件定義書の取得（`/query-specs`）
   - プロジェクト設計ルールの収集（`/query-rules`）
   - 既存実装資産の探索（コードベーススキャン）
3. 要件定義書の詳細分析
4. 設計書の作成（ID 採番・フォーマット適用）
5. 完了処理（レビュー → ToC → commit）

### 設計原則

- **既存資産優先**: 再利用可能なコンポーネントがある場合、新規作成せず活用する
- **What/How の境界**: 要件（何を作るか）と設計（どう作るか）を明確に分離する
- **トレーサビリティ**: 全要件が設計のどこに反映されているかを追跡可能にする

### 出力

`specs/{feature}/design/` に設計書（Markdown）を生成。ID 体系: `DES-xxx`

### 参考ドキュメント

- `plugins/forge/docs/design_format.md` — 設計書テンプレート
- `plugins/forge/docs/design_principles_spec.md` — 設計原則ガイド
- `plugins/forge/docs/spec_design_boundary_spec.md` — What/How の境界

---

## start-plan

設計書からタスクを抽出し、YAML 形式の計画書を作成する。

```
/forge:start-plan [feature]
```

| 引数      | 説明                             |
| --------- | -------------------------------- |
| `feature` | Feature 名（省略時は対話で確定） |

### いつ使うか

- 設計書が完成した後
- 実装作業の分担・スケジュールを決めるとき

### 実行フロー

1. Feature 名の確定
2. **コンテキスト収集**（2 Agent 並列）
   - 要件定義書 + 設計書の取得
   - 計画書ルールの収集
3. 既存計画書の確認（更新モードの場合）
4. 計画書の作成・更新（タスク抽出 → 粒度チェック → ID 採番）
5. 完了処理（レビュー → ToC → commit）

### タスク粒度の基準

| 基準       | 要件                                       |
| ---------- | ------------------------------------------ |
| 実行単位   | 1 Agent が単独で実行・完結できる粒度       |
| 内容量     | やるべき内容 5〜10 項目程度                |
| 完結性     | タスク完了時にビルド・テスト成功が条件     |
| ファイル数 | 1 ファイル or 密接に関連する 2〜3 ファイル |

### 計画書の構造（最小完全 YAML）

計画書は YAML 形式の `{feature}_plan.yaml`。**Markdown ではない**。
top-level は `requirements_traceability` / `design_traceability` / `tasks` / `revision_history` の 4 キーのみ（`plan_format.md` の正本スキーマに従う）。

```yaml
# {feature} 実装計画書

# === トレーサビリティ ===
requirements_traceability:
  - requirement_id: REQ-001
    title: 要件のタイトル
    design_id: DES-001
    status: pending # pending / completed

design_traceability:
  - design_id: DES-001
    title: 設計書のタイトル
    requirement_ids:
      - REQ-001
    task_ids:
      - TASK-001

# === タスク一覧 ===
tasks:
  - task_id: TASK-001
    title: タスク名
    priority: 90 # 高:70-99, 中:40-69, 低:1-39
    status: pending # pending / in_progress / completed
    design_id: DES-001 # 設計書なしは null（"-" ではない）
    depends_on: [] # 依存タスク ID 配列。なければ []
    group_id: null # 独立タスクは null、"GROUP-001 (1/3)" 等
    build_check: per_task # per_task / skip / on_group_complete
    description:
      - やるべきこと 1
      - やるべきこと 2
    acceptance_criteria: 受け入れ基準の記述 # なければ null
    required_reading: # 必読文書パスの配列。なければ []
      - specs/{feature}/design/DES-001_xxx.md

# === 改定履歴 ===
revision_history:
  - date: "2026-03-15"
    content: 初版作成
```

### 重要な原則

- `description` は設計書の該当セクションを特定できるレベルにとどめる（実装詳細は書かない）
- `design_id` が無いタスクは `null`（`-` や `"-"` は使わない）
- `depends_on` / `required_reading` が無い場合は空配列 `[]`（`null` や `-` ではない）
- `build_check` の値は `per_task` / `skip` / `on_group_complete` のみ
- 依存関係に循環がないか確認
- トレーサビリティマトリクスで全要件・全設計が反映されていることを検証

### 出力

`specs/{feature}/plan/{feature}_plan.yaml` に計画書（YAML）を生成。**Markdown 形式の計画書は出力しない**。
Claude Code plan mode が生成する Markdown plan とは別物（Markdown plan を入力に要件・設計を作る場合は `/forge:create-feature-from-markdown-plan` を使う）。

### 参考ドキュメント

- `plugins/forge/docs/plan_format.md` — 計画書 YAML スキーマ
- `plugins/forge/docs/plan_principles_spec.md` — タスク粒度・グループ化の考え方
