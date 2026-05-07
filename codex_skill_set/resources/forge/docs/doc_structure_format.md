# .doc_structure.yaml フォーマット仕様

> config.yaml 互換フォーマット v4.4 | Created by: k_terada

## 概要

`.doc_structure.yaml` はプロジェクトレベルの設定ファイルで、ドキュメントの配置場所と種別を宣言する。
doc-advisor の `config.yaml` と完全互換のフォーマットを採用し、以下のツールが共通で参照する:

- **forge スキル** — ドキュメント作成先の特定、レビュー対象の解決、Feature 検出
- **Doc Advisor** — ToC 生成のスキャン対象・doc_type 判定
- **resolve_doc_structure.py** — プログラムからのパス解決（JSON 出力）

## ファイル配置

プロジェクトルート（`.git/` と同階層）に `.doc_structure.yaml` として配置する。

## スキーマ

```yaml
# .doc_structure.yaml
# doc_structure_version: 3.0

# === rules configuration ===
rules:
  root_dirs:
    - <directory_path>
  doc_types_map:
    <directory_path>: <doc_type>
  patterns:
    target_glob: "**/*.md"
    exclude:
      - <dir_name>

# === specs configuration ===
specs:
  root_dirs:
    - <directory_path>
  doc_types_map:
    <directory_path>: <doc_type>
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

### forge が使用するフィールド

| フィールド                        | 必須 | 型            | 説明                                                     |
| --------------------------------- | ---- | ------------- | -------------------------------------------------------- |
| `{category}.root_dirs`            | Yes  | array[string] | ドキュメントディレクトリ。glob パターン（`*`, `**`）対応 |
| `{category}.doc_types_map`        | Yes  | object        | パス → doc_type のマッピング。glob パターン対応          |
| `{category}.patterns.exclude`     | No   | array[string] | 除外するディレクトリ名                                   |
| `{category}.patterns.target_glob` | No   | string        | ファイル検索 glob パターン（デフォルト: `**/*.md`）      |

## root_dirs

ドキュメントが格納されるディレクトリの一覧。

- パスはプロジェクトルートからの相対パス
- 末尾 `/` 推奨
- glob パターン `*` で1レベル、`**` で任意の深さのディレクトリマッチが可能

```yaml
root_dirs:
  - docs/rules/ # リテラルパス
  - "docs/specs/*/design/" # glob パターン（1階層の全 Feature）
  - "docs/specs/**/design/" # 再帰 glob パターン（任意の深さの全 Feature）
```

## doc_types_map

パス → doc_type のマッピング。`root_dirs` の各エントリに対応する doc_type を宣言する。

```yaml
doc_types_map:
  docs/rules/: rule
  "docs/specs/*/design/": design
  "docs/specs/*/plan/": plan
  "docs/specs/*/requirement/": requirement
```

### 推奨 doc_type 名

#### specs カテゴリ

| 名前          | 説明                               |
| ------------- | ---------------------------------- |
| `requirement` | 機能・非機能要件                   |
| `design`      | 技術設計書、アーキテクチャ仕様     |
| `plan`        | 実装計画、ロードマップ、タスク分割 |
| `api`         | API 仕様、エンドポイント定義       |
| `reference`   | 参考資料、データ辞書               |

#### rules カテゴリ

| 名前       | 説明                       |
| ---------- | -------------------------- |
| `rule`     | 開発規約、コーディング標準 |
| `workflow` | ワークフロー手順           |
| `guide`    | ベストプラクティス、ガイド |

## patterns.exclude

除外するディレクトリ名のリスト。

- ディレクトリ名の完全一致でマッチ（ファイル名は対象外）
- パス内の任意の深さでマッチ
- `/` を含むパターンはパス部分文字列としてマッチ

```yaml
patterns:
  exclude:
    - archived
    - _template

# docs/specs/auth/design/a.md         → 対象
# docs/specs/archived/design/a.md     → 除外（"archived" にマッチ）
# docs/specs/_template/design/a.md    → 除外（"_template" にマッチ）
```

## バージョン管理

コメント行でバージョンを管理する:

```yaml
# doc_structure_version: 3.0
```

- フォーマット: `X.Y`（X = メジャー、Y = マイナー）
- メジャーバージョン変更 = フォーマットの破壊的変更
- マイナーバージョン変更 = 後方互換のオプショナルフィールド追加

## サンプル

### Flat Structure（単一プロジェクト）

```yaml
# doc_structure_version: 3.0

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - docs/specs/design/
    - docs/specs/plan/
    - docs/specs/requirement/
  doc_types_map:
    docs/specs/design/: design
    docs/specs/plan/: plan
    docs/specs/requirement/: requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

### Feature-Based Structure（複数 Feature）

```yaml
# doc_structure_version: 3.0

rules:
  root_dirs:
    - docs/rules/
  doc_types_map:
    docs/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

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

この形式では Feature 追加時に `.doc_structure.yaml` の変更は不要。
`docs/specs/payment/design/` ディレクトリを作成するだけで自動的に検出される。

### Nested Feature-Based Structure（サブ Feature あり）

Feature 内にサブ Feature（例: `forge/review-PR/`）がある場合、`**` で任意の深さを一括指定できる。

```yaml
# doc_structure_version: 3.0

specs:
  root_dirs:
    - "docs/specs/**/design/"
    - "docs/specs/**/plan/"
    - "docs/specs/**/requirements/"
  doc_types_map:
    "docs/specs/**/design/": design
    "docs/specs/**/plan/": plan
    "docs/specs/**/requirements/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

`docs/specs/forge/design/` と `docs/specs/forge/review-PR/design/` の両方が自動検出される。
Feature 名は `**` がキャプチャした最初のセグメント（この例では `forge`）になる。

### Feature-Based with Exclude

```yaml
specs:
  root_dirs:
    - "docs/specs/*/design/"
    - "docs/specs/*/requirement/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/requirement/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude:
      - archived
      - _template
```

## Consumer Guide

### forge スキルから（推奨）

`doc-structure` スキルの `resolve_doc_structure.py` を使用する:

```bash
SCRIPT=".codex/doc-advisor/resources/forge/skills/doc-structure/scripts/resolve_doc_structure.py"

# 全ファイル一覧
python3 "$SCRIPT" --type all

# Feature 一覧
python3 "$SCRIPT" --features

# 特定 doc_type のファイル
python3 "$SCRIPT" --doc-type design
```

### Python スクリプトから（同一プラグイン内）

```python
from resolve_doc_structure import load_doc_structure, resolve_files

config, _ = load_doc_structure(project_root)
rules_files = resolve_files(config, 'rules', project_root)
specs_files = resolve_files(config, 'specs', project_root)
```

### Doc Advisor から

`.doc_structure.yaml` を `config.yaml` として直接読み込める（フォーマット互換）。
`import_doc_structure.py` による変換は不要。
