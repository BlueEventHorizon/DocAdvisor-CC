# 計画書 デフォルトフォーマット

プロジェクト固有の `plan_format.md` が見つからない場合に使用する汎用フォーマット。

作成原則: `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/plan_principles_spec.md`

## フォーマット選定理由（FNC-005）

計画書は YAML を使用する。理由:

- タスクID・優先度・依存関係・ステータス等、全てが構造化データ
- `start-implement` が機械的にパース・更新する必要がある（タスク選択・依存チェック・完了更新）
- Markdown テーブルは AI によるパースが不確実（列幅崩れ・`<br>` 改行等）

要件定義書・設計書は mermaid や自由記述を含むため Markdown を維持する。

---

## YAML スキーマ

ファイル名: `{feature}_plan.yaml`

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
      - TASK-002

# === タスク一覧 ===
tasks:
  - task_id: TASK-001
    title: タスクのタイトル
    priority: 90 # 1-99（高: 70-99, 中: 40-69, 低: 1-39）
    status: pending # pending / in_progress / completed
    design_id: DES-001 # null = 設計書なし
    depends_on: [] # 依存するタスクID の配列
    group_id: null # null = 独立タスク, "GROUP-001 (1/3)" 等
    build_check: per_task # per_task / skip / on_group_complete
    description:
      - やるべきこと 1
      - やるべきこと 2
      - やるべきこと 3
    acceptance_criteria: 受け入れ基準の記述 # null = なし
    required_reading: # 必読文書のパス配列
      - path/to/design.md
      - path/to/rule.md

# === 改定履歴 ===
revision_history:
  - date: "2026-03-15"
    content: 初版作成
```

---

## フィールド定義

### requirements_traceability

| フィールド     | 型     | 必須 | 説明                    |
| -------------- | ------ | ---- | ----------------------- |
| requirement_id | string | Yes  | 要件ID                  |
| title          | string | Yes  | 要件のタイトル          |
| design_id      | string | Yes  | 対応する設計ID          |
| status         | enum   | Yes  | `pending` / `completed` |

### design_traceability

| フィールド      | 型       | 必須 | 説明                    |
| --------------- | -------- | ---- | ----------------------- |
| design_id       | string   | Yes  | 設計ID                  |
| title           | string   | Yes  | 設計書のタイトル        |
| requirement_ids | string[] | Yes  | 対応する要件ID の配列   |
| task_ids        | string[] | Yes  | 対応するタスクID の配列 |

### tasks

| フィールド          | 型          | 必須 | 説明                                      |
| ------------------- | ----------- | ---- | ----------------------------------------- |
| task_id             | string      | Yes  | タスクID（`TASK-001` 形式）               |
| title               | string      | Yes  | タスクのタイトル                          |
| priority            | integer     | Yes  | 優先度 1-99                               |
| status              | enum        | Yes  | `pending` / `in_progress` / `completed`   |
| design_id           | string/null | Yes  | 対応する設計ID。なければ `null`           |
| depends_on          | string[]    | Yes  | 依存するタスクID の配列。なければ `[]`    |
| group_id            | string/null | Yes  | グループID。独立タスクは `null`           |
| build_check         | enum        | Yes  | `per_task` / `skip` / `on_group_complete` |
| description         | string[]    | Yes  | やるべき内容の配列（1項目 = 1行）         |
| acceptance_criteria | string/null | Yes  | 受け入れ基準。なければ `null`             |
| required_reading    | string[]    | Yes  | 必読文書パスの配列。なければ `[]`         |

### revision_history

| フィールド | 型     | 必須 | 説明               |
| ---------- | ------ | ---- | ------------------ |
| date       | string | Yes  | 日付（YYYY-MM-DD） |
| content    | string | Yes  | 改定内容           |

---

## status の遷移

```
pending → in_progress → completed
```

- `pending`: 未着手
- `in_progress`: `start-implement` が実行中
- `completed`: タスク完了（`start-implement` が更新）

---

## 優先度の目安

| 範囲  | 意味                                               |
| ----- | -------------------------------------------------- |
| 70-99 | 高: コアビジネスロジック・共通基盤・ブロッカー解消 |
| 40-69 | 中: 主要機能                                       |
| 1-39  | 低: UI・補助機能                                   |
