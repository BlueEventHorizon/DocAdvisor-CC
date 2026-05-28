# 文書構造ガイド

`.doc_structure.yaml` はプロジェクトのドキュメント配置場所と種別を宣言する設定ファイルで、`doc-advisor` の各スキル（`query-rules` / `query-specs` / `create-rules-toc` / `create-specs-toc`）が参照する。

## Feature（フィーチャー）

`docs/specs/{feature}/...` のように **Feature 単位** で仕様を分割管理する場合、各 Feature は共通のディレクトリ構造を持たせる:

```
docs/
  specs/
    {feature}/
      requirements/   # 要件定義書
      design/         # 設計書
      plan/           # 計画書
```

Feature 単位の分割は必須ではない。プロジェクト全体を 1 つの Feature として扱ってもよい。

## .doc_structure.yaml

### 役割

プロジェクトのドキュメント配置場所と種別を宣言する。`doc-advisor` のスキルはこのファイルを読み、対象ファイルの探索と doc_type 判定に使う。

プロジェクトルート（`.git/` と同階層）に配置する。

### スキーマ概要

`rules` と `specs` の 2 カテゴリで構成される。

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
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirements/": requirement
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

> **YAML 注意**: `doc_types_map` のキーが `*` や `**` を含む場合は `"..."` で **必ず quote** する。`root_dirs` 側の glob entry も quote が安全。

### 設定例

#### シンプル構成（Feature なし）

```yaml
specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
    - docs/specs/requirements/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
    docs/specs/requirements/: requirement
```

#### Feature ベース構成

```yaml
specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/plan/"
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/plan/": plan
    "docs/specs/*/requirements/": requirement
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

`docs/specs/auth/design/` と `docs/specs/auth/social-login/design/` の両方が自動検出される。

## /doc-advisor:setup-doc-structure

```
/doc-advisor:setup-doc-structure [--update]
```

### 何をするか

- プロジェクトをスキャンして `.doc_structure.yaml` を **対話的に** 生成または更新する
- 既存ディレクトリを発見し、rules / specs に分類する
- ユーザの確認を経て `.doc_structure.yaml` を Write する

`--update` を指定した場合、既存 `.doc_structure.yaml` の `root_dirs` に未登録のディレクトリのみ追加する。

### いつ実行するか

- プロジェクトで `doc-advisor` を初めて使うとき
- ディレクトリ構造を大きく変更したとき
- 新しい Feature を手動で追加したとき

### 手動で書く場合

スキルを使わず手動で配置することもできる。上記スキーマと例を参考に、プロジェクトルートに `.doc_structure.yaml` を作成する。
