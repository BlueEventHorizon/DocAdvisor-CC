---
name: setup-doc-structure
description: |
  プロジェクトをスキャンし `.doc_structure.yaml` を対話的に生成・更新する。
  doc-advisor の `/doc-advisor:query-rules` / `/doc-advisor:query-specs` /
  `/doc-advisor:create-rules-toc` / `/doc-advisor:create-specs-toc` を使う
  前提となる初期設定。
  Trigger:
  - "doc-advisor をセットアップ"
  - "doc_structure を作成"
  - "setup doc structure"
  - 初回利用時に `/doc-advisor:create-*-toc` から `config_required` エラーが
    返ったとき
allowed-tools: Bash, Read, Write, Edit, Glob, AskUserQuestion
user-invocable: true
argument-hint: "[--update]"
---

# setup-doc-structure

プロジェクト直下のドキュメントディレクトリを発見し、`.doc_structure.yaml` を生成または更新する。スクリプト依存なし、AI の判断と対話のみで完結する。

## Usage

```
/doc-advisor:setup-doc-structure [--update]
```

| Argument   | Description                                                              |
| ---------- | ------------------------------------------------------------------------ |
| (none)     | 全ディレクトリを分類して `.doc_structure.yaml` を新規作成または上書き    |
| `--update` | 既存 `.doc_structure.yaml` の `root_dirs` に未登録のディレクトリのみ追加 |

## 想定読者

このスキルは AI（あなた自身）への実行指示書である。`Skill` ツールでこの SKILL を再帰呼びしてはならない。下記手順に沿って自分で動作する。

---

## 実行フロー

### Step 0: モード判定

引数 `$0` が `--update` かどうか判定する。

- `--update` で `.doc_structure.yaml` が **存在する** → update モード（既存設定を保持し、未登録ディレクトリのみ追加）
- `--update` でも `.doc_structure.yaml` が **存在しない** → full モードにフォールバック
- 引数なし → full モード（既存があれば上書き）

`.doc_structure.yaml` の有無は次で判定:

```bash
test -f "${CLAUDE_PROJECT_DIR}/.doc_structure.yaml"
```

### Step 1: 候補ディレクトリの収集

Glob ツールで、プロジェクト内の Markdown を含むディレクトリを探索する。

```
Glob: **/*.md
```

- 結果から **ディレクトリ部分のみ** を抽出し、`.git/`, `node_modules/`, `.venv/`, `__pycache__/`, `.claude/`, `.codex/`, `.agents/`, `meta/`, `tests/` 配下は除外する
- `docs/`, `rules/`, `specs/`, `documents/`, `guidelines/`, `requirements/`, `design/`, `plan/`, `adr/`, `api/`, `architecture/` のような典型的なドキュメント関連ディレクトリ名を優先的に拾う

加えて、空ディレクトリ（まだ md が無い）の候補も探す:

```
Glob: docs/*/, rules/*/, specs/*/
```

### Step 2: 分類（rules / specs / skip）

各候補ディレクトリを以下のルールで分類する。

| 判定基準                                                                  | 分類例                                     |
| ------------------------------------------------------------------------- | ------------------------------------------ |
| パス名に `rule`, `guideline`, `standard`, `convention`                    | → **rules**                                |
| パス名に `spec`, `requirement`, `design`, `plan`, `adr`, `api`, `feature` | → **specs**                                |
| パス名に `readme`, `note`, `reference`, `external`                        | → **skip**（doc-advisor のスキャン対象外） |
| 判定困難                                                                  | → **unclassified**（後段でユーザに確認）   |

判断は **path component の前方一致** を優先する。例:

- `docs/rules/` → rules（high）
- `docs/specs/auth/design/` → specs（high）
- `guidelines/` → rules（high）
- `architecture/` → specs（medium、文脈次第）
- `notes/` → 通常 skip だが、ドキュメントが多ければユーザに確認

confidence は high / medium / low の 3 段階で内部的に保持する。

`--update` モードの場合、`.doc_structure.yaml` を Read して既存 `root_dirs` を取得し、既に含まれているディレクトリは候補から除外する。

### Step 3: ユーザに分類結果を提示

AskUserQuestion で次のように確認する。

```
Document Directory Classification

Rules (rules to follow):
  [high]   docs/rules/      (12 files)
  [medium] guidelines/      (3 files)

Specs (requirements / design / plan):
  [high]   docs/specs/auth/design/       (5 files)
  [high]   docs/specs/auth/requirements/ (4 files)

Skip:
  docs/readme/         (user-facing readme)

Unclassified:
  shared/              (need user input)
```

各 unclassified / medium / low confidence 項目について、`rules` / `specs` / `skip` のいずれかをユーザに選ばせる。

### Step 4: `.doc_structure.yaml` を生成または更新

確定した分類に基づき、以下のフォーマットで `.doc_structure.yaml` を **プロジェクトルート** に Write する。

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
    - "docs/specs/*/requirements/"
  doc_types_map:
    "docs/specs/*/design/": design
    "docs/specs/*/requirements/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

#### 規約

- **glob 対応**: 複数 feature を扱う場合は `"docs/specs/*/design/"` のように quoted glob で記述する（YAML として安全）
- **doc_type の推奨値**: `rule`, `requirement`, `design`, `plan`, `api`, `reference`, `spec`
- **`doc_types_map` のキー**は `root_dirs` のエントリと **完全一致** させる
- **update モード**: 既存ファイルを Read し、`root_dirs` / `doc_types_map` に既存エントリを保持したまま追加分のみ末尾に append する。`patterns.exclude` は明示的にユーザが要求しない限り変更しない

### Step 5: 完了メッセージ

```
.doc_structure.yaml updated

Rules directories:
  - docs/rules/
  - guidelines/

Specs directories:
  - docs/specs/*/design/
  - docs/specs/*/requirements/

Next steps:
  /doc-advisor:create-rules-toc --full
  /doc-advisor:create-specs-toc --full
```

---

## Error Handling

| 状況                                     | 対応                                                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| プロジェクトに markdown が一切ない       | 「ドキュメントが見つかりません。空の `.doc_structure.yaml` を作成しますか?」と AskUserQuestion で確認 |
| `${CLAUDE_PROJECT_DIR}` 環境変数が未設定 | 現在のカレントディレクトリを project root として扱う                                                  |
| Write に失敗（権限など）                 | エラー詳細を報告し、ユーザに手動配置を案内                                                            |

## 設計原則

- **依存ゼロ**: 外部スクリプト・Python パッケージ・他プラグインに依存しない（Glob / Write / Read / AskUserQuestion / Bash の標準ツールのみ）
- **対話必須**: 分類結果は必ず AskUserQuestion で確認する。無確認で `.doc_structure.yaml` を上書きしない
- **冪等**: 同じ入力で何度実行しても同じ結果になる
- **保守的**: 確信が持てないディレクトリは unclassified として user 判断に委ねる
