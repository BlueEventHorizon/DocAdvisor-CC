---
name: review-skill-description
description: |
  SKILL.md の description / trigger を公式ベストプラクティスに基づき監査・改善提案する。
  新規スキル作成時や既存スキルの品質チェックに使用する。
  トリガー: "スキルの description をレビュー", "SKILL.md チェック", "review skill description"
user-invocable: true
argument-hint: "[対象パス or プラグイン名]"
---

# review-skill-description

SKILL.md の description フィールドと frontmatter を、Claude Code 公式ドキュメントの
ベストプラクティスに基づいて監査し、改善案を提示する。

## 引数

- `$ARGUMENTS` が指定された場合 → そのパスまたはプラグイン配下の SKILL.md を対象にする
- 省略時 → `plugins/` 配下の全 SKILL.md を対象にする

---

## 評価基準 [MANDATORY]

以下の 6 基準で各 SKILL.md を評価する。全基準を必ず適用すること。

### 1. 250 文字制限（先頭に核心）

公式: "descriptions longer than 250 characters are truncated in the skill listing"

- description 全体が 250 文字以内に収まっているか
- 先頭 50 文字で「何をするか」が完結しているか（front-load the key use case）
- 250 文字を超える場合、先頭 250 文字だけで AI が判断できるか

### 2. What + When の明記

- **What**: ユーザー（または呼び出し元）が得る本質的な価値が 1 行目で明確か
  - 書く対象: ユーザーが得る結果・効果、機能のスコープ、選べるモード
  - 書かない対象（内部構造・実装フローは記載しない）:
    - 内部実装の手順（例: 「バックアップ → 差し替え → 復元」「収集 → 執筆 → レビュー → commit」）
    - 内部ファイル名・フィールド名（例: `review_packet`, `recommendation: fix`）
    - 呼び出される他スキル名や呼び出し元の Phase 番号
    - 並列度・起動原則・内部 ID（例: 「1 体のみ起動」「FNC-412」）
- **When**: いつ使うべきか（トリガー条件・使用場面）が記載されているか
  - user-invocable スキルには `トリガー:` 行が含まれているか

### 3. LLM 推論への意味アンカー

公式: Claude は keyword matching ではなく LLM 推論で自動呼び出しを判定する。

- ユーザーが使いそうな表現・語彙が description に含まれているか
- 抽象的すぎる記述（「ツール」「ユーティリティ」だけ）になっていないか
- 対象領域の具体的なキーワードが含まれているか

### 4. 類似スキルとの差別化

- 同一プラグイン内・プラグイン間で役割が似たスキルと区別できるか
- 差分が description から明確に読み取れるか
- 例: query-rules（プロジェクト文書）vs query-forge-rules（forge 内蔵 docs）

### 5. user-invocable / disable-model-invocation の整合性

- `user-invocable: false` なのにユーザー向けトリガーが含まれていないか
- `disable-model-invocation: true` が必要なのに設定されていないか
- AI 専用スキルで呼び出し元が description に明記されているか

### 6. トリガーフレーズの品質

- 日本語・英語の両方が含まれているか
- ユーザーが自然に使う表現か
- モードや機能固有のフレーズが含まれているか（例: 「Figma から要件」）

---

## 評価手順

### Step 1: 対象の SKILL.md を収集

対象パス配下の全 SKILL.md を Glob で探索し、各ファイルの frontmatter を Read する。

### Step 2: 各スキルを 6 基準で評価

各 SKILL.md について以下の形式で評価する:

````
### {plugin}:{skill-name}

**description（現状）**:
> {現在の description 全文}

| 基準 | 判定 | 備考 |
|------|------|------|
| 250 文字制限 | OK / NG | {文字数と問題点} |
| What + When | OK / NG | {不足している要素・内部構造の露出有無} |
| 意味アンカー | OK / NG | {具体性の評価} |
| 差別化 | OK / NG | {類似スキルとの比較} |
| invocable 整合性 | OK / NG | {設定の妥当性} |
| トリガー品質 | OK / NG | {改善ポイント} |

**総合判定**: 問題なし / 改善推奨 / 要修正

**改善案**（問題がある場合のみ）:
```yaml
description: |
  {改善後の description}
````

```
### Step 3: サマリー出力

全スキルの評価をまとめて以下を出力する:
```

## サマリー

| 判定     | 件数 | スキル         |
| -------- | ---- | -------------- |
| 問題なし | N    | {スキル名一覧} |
| 改善推奨 | N    | {スキル名一覧} |
| 要修正   | N    | {スキル名一覧} |

````
---

## 補足知識

### description のコンテキスト管理

- `user-invocable: false` → description が**常に**コンテキストに入る
- `disable-model-invocation: true` → description がコンテキストに**入らない**
- デフォルト → description が常にコンテキストに入り、フルスキルは呼び出し時のみロード

### コンテキストバジェット

- 全スキル名は常に含まれる
- description は合計でコンテキストウィンドウの 1%（フォールバック 8,000 文字）
- 各エントリは 250 文字で切り詰め
- `SLASH_COMMAND_TOOL_CHAR_BUDGET` 環境変数で上限変更可能

### 模範的な description の例

```yaml
# オーケストレーター（user-invocable: true）
description: |
  コード・文書をレビューし、品質問題の発見から修正まで自動化できる。重大度 🔴🟡🟢 で分類。
  --auto で修正まで一貫実行。code/requirement/design/plan/generic の5種別に対応。
  トリガー: "レビュー", "review", "レビューして", "確認して"

# AI 専用スキル（user-invocable: false）
description: |
  forge 内蔵の知識ベースを ToC 検索し、タスクに関連するドキュメントのパスを返す。
  対象: ID体系・仕様フォーマット・設計原則・レビュー基準・ワークフロー仕様・HIG/UXガイド等。
  他スキルが forge の内部仕様や規約を参照する必要がある場面で使用する。
  ※ プロジェクト文書には /forge:query-db-rules を使う。本スキルは forge 自体の docs が対象。
````

### よくある問題パターン

| パターン                                     | 問題                                  | 対策                                 |
| -------------------------------------------- | ------------------------------------- | ------------------------------------ |
| 「〜ツール」「〜ユーティリティ」のみ         | AI が判断材料にできない               | ユーザーが得る価値を具体的に記述     |
| モード/機能が argument-hint にのみ存在       | description からマッチしない          | 主要モードを description に列挙      |
| 工程を段階列挙（「収集 → 執筆 → レビュー」） | 内部実装の露出。AI の判断に寄与しない | スコープ・モードとして価値で表現する |
| 内部スキル名・内部フィールド名の露出         | 内部実装の漏れ出し。AI の判断には不要 | ユーザーが得る結果のみ記述する       |
| user-invocable: false + ユーザー向けトリガー | 設定と内容が矛盾                      | true に変更するかトリガーを削除      |
| 関連スキルとの差分が不明                     | 誤ったスキルが呼ばれる                | 対象範囲の違いを明記                 |
