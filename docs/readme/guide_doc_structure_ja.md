# 文書構造ガイド

`.doc_structure.yaml` はプロジェクトのドキュメント配置場所と種別を宣言する設定ファイルで、forge と doc-advisor の共通基盤として機能する。

## Feature（フィーチャー）

forge は **Feature（フィーチャー）** 単位で文書を管理することもできる。Feature とは、関連する仕様をグループ化した開発単位。Feature なしでも動作する。

| 開発パターン                           | Feature の使い方                                                |
| -------------------------------------- | --------------------------------------------------------------- |
| [追加開発](guide_sdd_ja.md#6-追加開発) | 既存のメイン仕様に後から追加する機能群を Feature として分割する |
| アジャイル開発                         | イテレーションごとに Feature 単位で開発・デリバリーする         |
| 小規模プロジェクト                     | プロジェクト全体を1つの Feature として扱ってもよい              |

Feature を使う場合、各 Feature は共通のディレクトリ構造で管理する:

```
specs/
  {feature}/
    requirements/   # 要件定義書
    design/         # 設計書
    plan/           # 計画書
```

## .doc_structure.yaml

### 役割

プロジェクトのドキュメント配置場所と種別を宣言するファイル。以下のツールが共通で参照する:

- **forge** — レビュー対象の解決、Feature ディレクトリ検出、ドキュメント作成先の特定
- **doc-advisor** — ToC 生成のスキャン対象・doc_type 判定

プロジェクトルート（`.git/` と同階層）に配置する。

### スキーマ概要

`rules` と `specs` の2カテゴリで構成される。

```yaml
# .doc_structure.yaml
# doc_structure_version: 3.0

rules:
  root_dirs: # スキャン対象ディレクトリ（glob 対応）
    - docs/rules/
  doc_types_map: # ディレクトリ → doc_type のマッピング
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: [] # 除外ディレクトリ名

specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirement/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

| フィールド             | 説明                                                                                                     |
| ---------------------- | -------------------------------------------------------------------------------------------------------- |
| `root_dirs`            | ドキュメントディレクトリ。`*`（1レベル）/ `**`（任意の深さ）の glob パターン対応                         |
| `doc_types_map`        | パス → doc_type のマッピング。推奨 doc_type: `rule`, `requirement`, `design`, `plan`, `api`, `reference` |
| `patterns.target_glob` | ファイル検索パターン（デフォルト: `**/*.md`）                                                            |
| `patterns.exclude`     | 除外するディレクトリ名（パス内の任意の深さでマッチ）                                                     |

### 設定例

#### シンプル構成（Feature なし）

```yaml
specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
    - docs/specs/requirement/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
    docs/specs/requirement/: requirement
```

#### Feature ベース構成

```yaml
specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirement/": requirement
```

Feature 追加時に `.doc_structure.yaml` の変更は不要。`docs/specs/payment/design/` ディレクトリを作成するだけで自動的に検出される。

#### ネスト Feature 構成（サブ Feature あり）

```yaml
specs:
  root_dirs:
    - "docs/specs/**/design/"
    - "docs/specs/**/plan/"
    - "docs/specs/**/requirements/"
  doc_types_map:
    "docs/specs/**/design/": design
    "docs/specs/**/plan/": plan
    "docs/specs/**/requirements/": requirement
```

`docs/specs/forge/design/` と `docs/specs/forge/review-PR/design/` の両方が自動検出される。

## /forge:setup-doc-structure

```
/forge:setup-doc-structure
```

引数なし。

### 何をするか

- プロジェクトをスキャンして `.doc_structure.yaml` を対話的に生成・更新する
- 既存 Feature ディレクトリを自動検出し glob パターンで設定する
- 推奨構成（specs / rules / reference / adr）を提示し、不足ディレクトリを `.gitkeep` 付きで作成する

### いつ実行するか

- プロジェクトで forge / doc-advisor を初めて使うとき
- ディレクトリ構造を大きく変更したとき
- Feature を手動で追加したとき

## スキーマ仕様リファレンス

詳細なフォーマット仕様は [doc_structure_format.md](../../plugins/forge/docs/doc_structure_format.md) を参照。
