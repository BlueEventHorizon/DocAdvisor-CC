# DES-008: OKF準拠フロントマター設計書

## 概要

doc-advisor が扱う Markdown 文書のフロントマターを Open Knowledge Format（OKF v0.1）準拠の形式へ移行する。目的は、文書の作成・編集を担う AI スキル（forge/anvil/doc-advisor 各スキル）が生成時点で ToC 相当のメタデータをフロントマターとして書き込むことで、`index-docs` 実行時に `toc-updater` Agent によるコールドリード（1ファイルずつ本文を読んで再抽出）を省略し、大量文書（数百件規模）の初回インデックス時間を短縮すること。

`toc.yaml` は query 時の唯一の参照先として維持する（query 時に個々のフロントマターを都度パースする方式は採らない）。フロントマターは「pending エントリを高速に埋めるための入力」という位置づけであり、ToC 自体の Single Source of Truth 性は変えない。

## 背景・経緯（会話ログからの要約）

- 現状、`index-docs` は `prepare_toc.py` が checksum 差分で `added`/`updated` を検出し、該当ファイルを `toc-updater` Agent（AI によるコールドリード）で1件ずつ処理する。600件規模の初回インデックスでは数時間規模のコストがかかる
- `added` 判定のファイルには前回 checksum が存在しないため、既存の checksum スキップ機構は効かない
- 文書の作成・編集がほぼ全て AI スキル経由であるという前提のもと、作成時点でその AI が既に文書内容を完全に理解している状態でフロントマターを書けば、限界コストはほぼゼロになる
- 編集時にも同じ AI スキルがフロントマターを見直す契約を持たせることで、鮮度を保つ
- ただし「見直す契約」をプロンプト規律のみに委ねず、本文ハッシュ（フロントマター内埋め込み、本文のみ対象で自己参照を回避）による機械的な不一致検出を安全網として持たせる
- `toc.yaml` を廃止して query 時に都度フロントマターを解析する方式は、コストを「index 構築時の1回」から「query 実行のたびの毎回」へ付け替えるだけであり、原子的書き込み・検証・ロールバックという既存の安全機構（`merge_toc.py`）も失うため不採用とした
- 実装上の着地点は、pending YAML を `toc-updater` Agent を呼ばずにフロントマターから直接 `status: completed` として生成し、その後は `merge_toc.py` の既存フロー（backup → 原子的書き込み → `validate_toc` → checksums 更新）を無改造で流用する

## 関連文書

- `plugins/doc-advisor/formats/toc_format.md`（現行 ToC / pending スキーマ）
- `docs/specs/base/design/DES-005_toc_generation_flow.md`（prepare/merge フロー）
- `docs/specs/base/requirements/FNC-002_zero_miss_search_accuracy_spec.md`（検索網羅性の要件）

---

## OKF実例（リファレンス実装からの引用）

比較表だけでは各フィールドに何を書くべきか判断しづらいため、OKF公式リファレンス実装（`GoogleCloudPlatform/knowledge-catalog` の `okf/bundles/ga4/`）から実例を引用する。

### 実例1: BigQueryテーブル（`tables/events_.md`）

```yaml
type: BigQuery Table
resource: https://bigquery.googleapis.com/v2/projects/bigquery-public-data/datasets/ga4_obfuscated_sample_ecommerce/tables/events_*
title: Events table (Google Analytics BigQuery Export)
description: Contains Google Analytics event export data from the `ga4_obfuscated_sample_ecommerce` dataset.
tags:
  - events
  - Google Analytics
  - BigQuery
  - ecommerce
  - schema
  - basic queries
  - advanced queries
timestamp: "2026-05-28T22:53:05+00:00"
```

本文冒頭: "The `events_` table is a sharded BigQuery table containing Google Analytics event export data from the `ga4_obfuscated_sample_ecommerce` dataset."（以下、詳細なスキーマ説明が続く）

### 実例2: BigQueryデータセット（`datasets/ga4_obfuscated_sample_ecommerce.md`）

```yaml
type: BigQuery Dataset
resource: https://bigquery.googleapis.com/v2/projects/bigquery-public-data/datasets/ga4_obfuscated_sample_ecommerce
title: BigQuery sample dataset for Google Analytics ecommerce web implementation
description: A sample of obfuscated Google Analytics BigQuery event export data for three months (November 2020 to January 2021) from the Google Merchandise Store is available as a public dataset in BigQuery.
tags:
  - ecommerce
  - web analytics
  - Google Analytics
  - BigQuery
  - public dataset
timestamp: "2026-05-28T22:49:59+00:00"
```

### 実例3: `index.md`（予約ファイル名）

```markdown
# BigQuery Table

- [Events table (Google Analytics BigQuery Export)](events_.md) - Contains Google Analytics event export data from the `ga4_obfuscated_sample_ecommerce` dataset.
```

**フロントマターは無し**。予約ファイル名（`index.md`）はfrontmatter必須ルールの対象外で、子conceptへのリンク集というナビゲーション専用ページになっている。

### 実例から読み取れる各フィールドの実態

| フィールド    | 実態                                                                                                                                                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `type`        | 固定enumではなく**自由記述の名詞句**（`BigQuery Table`, `BigQuery Dataset`）。事前定義された値リストは仕様上存在しない。旧`doc_type`のような固定分類というより`title`に近い自由度                                     |
| `tags`        | `events`, `Google Analytics`, `BigQuery`のような**ドメイン名・技術名・大分類が並ぶ**。doc-advisorの`keywords`が明示的に避けようとする「汎用カテゴリ語」に近いものも含まれる                                           |
| `description` | 1〜2文の要約。doc-advisorの`purpose`とほぼ同じ粒度・役割                                                                                                                                                              |
| `resource`    | **このconceptが指す外部実体のURI**（GA4実例では実際のBigQuery API URL）。doc-advisorの文脈では「この文書自身のパス」ではなく「この文書が説明している対象（コード上のクラス、APIエンドポイント等）」に相当しそうである |
| `index.md`    | frontmatterを持たない一覧ページ。子conceptへのリンク集に徹する                                                                                                                                                        |

---

## フィールド比較表（たたき台 — 確定前）

現行の ToC / pending スキーマ（`toc_format.md`）と OKF v0.1 のフィールドを突き合わせ、移行後のフィールドセットを検討する。◎ = 直接対応、△ = 概念は近いが意味・制約が異なる、✕ = 対応なし。

| #  | OKF v0.1 フィールド                | 現行 ToC/pending フィールド                                             | 対応度   | 移行後の扱い（要決定）                                                     |
| -- | ---------------------------------- | ----------------------------------------------------------------------- | -------- | -------------------------------------------------------------------------- |
| 1  | `type`（必須）                     | なし（`doc_type` は FNC-002 により意図的に廃止済み）                    | ✕        | 追加するか？追加する場合、検索精度への影響が無いことを再確認する必要あり   |
| 2  | `title`（推奨）                    | `title`（必須・H1から抽出）                                             | ◎        | フィールド名そのまま踏襲                                                   |
| 3  | `description`（推奨）              | `purpose`（必須・最大200文字）                                          | △        | 名称を`description`に合わせるか、`purpose`のまま残すか                     |
| 4  | `resource`（推奨）                 | なし（docsマップのキー＝パス自体が対応）                                | △        | フロントマターは文書自身に埋め込むため、自己参照的な`resource`は不要では？ |
| 5  | `tags`（推奨）                     | `keywords`（必須・最大10語・固有名詞優先・汎用語排除）                  | △        | `tags`は汎用カテゴリ許容、`keywords`は汎用語排除。統合するか併存させるか   |
| 6  | `timestamp`（推奨）                | `_meta.updated_at`（pending中間ファイルのみ、最終toc.yamlには残らない） | △        | フロントマターには残す想定（最終`toc.yaml`側の扱いは要決定）               |
| 7  | ✕（対応なし）                      | `content_details`（必須・最大10件・具体的詳細）                         | カスタム | doc-advisor固有フィールドとしてそのまま追加                                |
| 8  | ✕（対応なし）                      | `applicable_tasks`（必須・最大10件・タスク種別）                        | カスタム | doc-advisor固有フィールドとしてそのまま追加                                |
| 9  | ✕（対応なし）                      | なし（新設予定）                                                        | カスタム | 陳腐化検知用の本文ハッシュ（`content_hash`等、本文のみ対象）               |
| 10 | `index.md`（予約ファイル名・任意） | なし                                                                    | —        | 採用するか（段階的開示の仕組みとして）                                     |
| 11 | `log.md`（予約ファイル名・任意）   | なし                                                                    | —        | 採用するか（変更履歴の仕組みとして）                                       |

### 検討が必要な設計判断（未決定事項）

1. **`type`フィールドを追加するか**: OKFでは必須だが、doc-advisorは`doc_type`相当を検索精度への寄与なしとして意図的に廃止した経緯がある（FNC-002）。OKF互換性のためだけに復活させる価値があるか
2. **`description` vs `purpose`**: フィールド名をOKFに合わせるか、既存の`purpose`（200文字制限等の既存ルール付き）を維持するか
3. **`tags` vs `keywords`**: 汎用カテゴリ許容（OKF）と汎用語排除（doc-advisor）という思想の違いをどう吸収するか。フィールドを分けるか、doc-advisorのルールを優先するか
4. **英語限定ルールの扱い**: 現行ToCは全フィールド値を英語に統一しているが、原本Markdownに埋め込むフロントマターでも同じ制約を維持するか（原文が日本語の場合の見え方）
5. **本文ハッシュのフィールド名・保存形式**: 本文のみを対象とし、フロントマター全体を含めない（自己参照回避）。フィールド名・ハッシュアルゴリズム（SHA256想定）を確定する
6. **`index.md`/`log.md`の採用要否**: 本プロジェクトの文書構成にこの仕組みが必要か
7. **必須/推奨の強度**: OKFは`type`以外ほぼ寛容だが、doc-advisorは全フィールド必須・空禁止。移行後にどちらの強度を取るか（欠落時にAI再生成へフォールバックする設計と整合させる必要あり）

---

## 次のステップ

上記比較表の各行・各未決定事項について、ユーザーと合意の上でフィールドセットを確定する。確定後、本設計書に「最終フィールド定義」節を追記し、`toc_format.md`・`prepare_toc.py`・`merge_toc.py`・各Agentプロンプトへの実装反映を別途計画する。
