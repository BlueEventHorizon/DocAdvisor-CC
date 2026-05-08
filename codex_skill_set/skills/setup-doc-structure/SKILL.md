---
name: setup-doc-structure
description: |
    プロジェクトのディレクトリをスキャン・分類し .doc_structure.yaml を対話的に生成する。
    forge・doc-advisor が文書を参照するための必須初期設定。
    トリガー: "forge の初期設定", "doc structure を作成", "ドキュメント構成", "setup"
metadata:
  short-description: setup doc structure
---

## Codex Skill Resource Root

This skill is distributed by the environment-wide Doc Advisor Codex Skill set.
Resolve `$DOC_ADVISOR_CODEX_ROOT` to `${CODEX_HOME:-~/.codex}/doc-advisor`,
the directory that contains `install.yaml`.

Run bundled Python scripts with absolute paths under
`$DOC_ADVISOR_CODEX_ROOT/resources/...` and prefix them with
`PYTHONDONTWRITEBYTECODE=1` so global resources do not accumulate runtime cache
files. Project runtime output stays under the current project's
`.codex/state/doc-advisor/`.

# setup-doc-structure

## 概要

対話的に `.doc_structure.yaml` をプロジェクトルートに作成・更新する。
このファイルはドキュメントの所在を宣言し、他のツール（Doc Advisor, forge 等）がドキュメントを参照できるようにする。

## 実行規則

- プランモードが有効な場合は解除すること。プランモードの解除についてユーザーへの確認は不要。
- `.doc_structure.yaml` がすでに存在する場合は**レビューモード**に切り替えること（現在の内容を表示し、変更を提案する）。

## Procedure

### Step 1: 既存ファイルの確認

```bash
PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/forge/scripts/doc_structure/check_doc_structure.py
```

JSON 出力に応じて分岐する:

- **`exists: false`** → Step 2 へ。
- **`error` あり** → エラー内容をユーザーに報告して終了。
- **`exists: true`** →
  1. `needs_migration: true` の場合 → user confirmation を使用して「.doc_structure.yaml を v{detected_version} → v{current_version} にマイグレーションしますか？」と確認
     - Yes → `PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/forge/scripts/doc_structure/migrate_doc_structure.py <path>` で変換結果を取得し、Write で書き出す
     - No → 手順 2 へ
  2. `content` を表示し、user confirmation を使用して方針を確認する
     - **更新する** → Step 2 へ（既存の分類結果をベースにスキャン・再分類）
     - **再生成する** → 既存ファイルを削除し、Step 2 へ（ゼロから生成）
     - **このまま使う** → 完了（変更なし）

### Step 2: ディレクトリスキャン + 候補リスト作成

#### 2-1: 自動スキャン

```bash
PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/forge/scripts/doc_structure/classify_dirs.py
```

スキャン結果（JSON）を取得する。`readme_only: true` のディレクトリは分類対象外としてスキップする。

> **注意**: classify_dirs.py は浅いスキャン（親ディレクトリに .md ファイルがある場合、サブディレクトリは検出されない）のため、後続の「空ディレクトリの補完」Glob 探索は必須。

空ディレクトリの補完: ドキュメント系の親ディレクトリ（`docs/`, `rules/`, `specs/` 等）配下のサブディレクトリを Glob で探索し、スキャン結果にないものも候補に追加する。

#### 2-2: AI 分類判定 [MANDATORY]

同ディレクトリの `classification_rules.md` を Read し、そのルールに従ってスキャン結果の各ディレクトリに category と doc_type を割り当てる。

**進捗表示 [MANDATORY]**: 各ディレクトリの判定ごとに結果をユーザーに表示すること。

#### 2-3: 推奨ディレクトリの補完

スキャン結果に含まれない推奨ディレクトリを「未検出（推奨）」として候補リストに追加する。

推奨ディレクトリ（スキャンで検出されなかった場合のみ追加）:

| パス              | doc_type  | 説明                                                      |
| ----------------- | --------- | --------------------------------------------------------- |
| `docs/specs/`     | —         | 仕様書ベースディレクトリ（requirements/design/plan の親） |
| `docs/rules/`     | rule      | 開発ルール・規約                                          |
| `docs/reference/` | reference | 参考文献・技術調査メモ（今後利用予定）                    |
| `docs/adr/`       | —         | Architecture Decision Record（今後利用予定）              |

> スキャンで類似ディレクトリが検出済みの場合（例: `rules/` が既にある場合に `docs/rules/` は推奨しない）、重複する推奨は追加しない。

> **Feature ディレクトリについて**: 既存の Feature ディレクトリ（`docs/specs/{feature}/requirements/` 等）は Step 2 のスキャンで自動検出し、glob パターン（例: `docs/specs/*/requirements/`）として `.doc_structure.yaml` に設定する。ただし、まだ存在しない Feature の空ディレクトリをここで作成はしない。新規 Feature のディレクトリは `start-requirements` / `start-design` / `start-plan` が作業開始時に作成する。

### Step 3: 候補の対話的確認 [MANDATORY]

スキャン結果と推奨ディレクトリを統合した**候補リスト**をユーザーに提示する。

> **重要**: スキャン結果はあくまで候補である。ユーザーが見ていない場所にディレクトリがある可能性もある。全ての候補について確認を取り、ユーザーの指示に従う。

#### 3-1: パターン A — ディレクトリが検出された場合

テキスト出力:

```
## ドキュメントディレクトリ候補

検出済み:
  1. ✅ docs/rules/                       — rule
  2. ✅ docs/specs/login/design/          — design
  3. ✅ docs/specs/login/requirements/    — requirement
     → glob パターン: docs/specs/**/design/, docs/specs/**/requirements/

未検出（推奨）:
  4. ☐ docs/specs/**/plan/               — 計画書
  5. ☐ docs/reference/                   — 参考文献（今後利用予定）
  6. ☐ docs/adr/                         — Architecture Decision Record（今後利用予定）
```

user confirmation を使用して方針を確認する:

| 選択肢                         | 説明                                                  |
| ------------------------------ | ----------------------------------------------------- |
| この候補で確定                 | 検出済みディレクトリのみで .doc_structure.yaml を生成 |
| 不足ディレクトリを作成して追加 | 未検出（推奨）から選択し、.gitkeep 付きで作成         |
| 候補を修正                     | 分類の変更、パスの追加・除外など                      |
| （Other）                      | 別のパスを指定したい等 — 自動提供                     |

#### 3-2: パターン B — ディレクトリが検出されなかった場合

テキスト出力:

```
## ドキュメントディレクトリ候補

ドキュメントディレクトリが検出されませんでした。
推奨構成を提案します:

  ☐ docs/specs/      — 仕様書ベースディレクトリ（requirements/design/plan の親）
  ☐ docs/rules/      — 開発ルール・規約
  ☐ docs/reference/  — 参考文献（今後利用予定）
  ☐ docs/adr/        — Architecture Decision Record（今後利用予定）
```

user confirmation を使用して方針を確認する:

| 選択肢             | 説明                                                           |
| ------------------ | -------------------------------------------------------------- |
| 推奨構成を全て作成 | specs/ + rules/ + reference/ + adr/ を .gitkeep 付きで作成     |
| 選択して作成       | 作成するディレクトリを個別に選択                               |
| 作成しない         | ディレクトリ作成をスキップ（.doc_structure.yaml も生成しない） |
| （Other）          | 自分でパスを指定したい等 — 自動提供                            |

#### 3-3: 詳細選択（条件分岐）

**「不足ディレクトリを作成して追加」または「選択して作成」の場合:**

user confirmation（multiSelect）で作成するディレクトリを選択させる。
選択肢は未検出項目または推奨項目から動的に生成する（最大4件。超過時は複数回に分割）。
選択されたディレクトリを Step 4 で作成する。

**「候補を修正」の場合:**

user confirmation を使用して修正内容を確認する:

| 選択肢             | 説明                                                                 |
| ------------------ | -------------------------------------------------------------------- |
| 分類を変更         | 既存ディレクトリの category/doc_type を修正（例: 2番を plan に変更） |
| ディレクトリを除外 | 候補から除外するディレクトリを指定                                   |
| ディレクトリを追加 | 候補にないパスを追加                                                 |

修正を適用後、再度候補リストを表示して方針選択に戻る（確認ループ）。
ユーザーが追加したパスが存在しない場合 → 作成するか user confirmation を使用して確認する。

#### Feature の扱い

- 既存 Feature（`docs/specs/login/`, `docs/specs/auth/` 等）はスキャンで自動検出する
- AI が glob パターン（`docs/specs/**/design/` 等）を推定し、.doc_structure.yaml に設定する
- ユーザーが「Other」で新しい Feature パスを指定した場合 → 存在しなければ作成を提案
- Feature 名を引数として受け取らない（Feature はテンポラリーであり、スキャンで検出するもの）

### Step 4: ディレクトリ作成

Step 3 で作成を選択されたディレクトリについて:

1. `mkdir -p` でディレクトリを作成
2. 空ディレクトリに `.gitkeep` を配置
3. 作成結果を一覧表示

```
ディレクトリを作成しました:
  ✅ docs/specs/.gitkeep
  ✅ docs/rules/.gitkeep
  ✅ docs/reference/.gitkeep
```

作成したディレクトリを候補リストの「検出済み」に追加し、Step 5 へ進む。

> Step 3 でディレクトリ作成が不要だった場合（「この候補で確定」「作成しない」選択時）、この Step はスキップする。

### Step 5: .doc_structure.yaml の生成

確定した分類結果から `.doc_structure.yaml` を config.yaml 互換フォーマットで生成し、プロジェクトルートに書き出す。
doc-advisor 固有フィールドはデフォルト値で生成する（Quick reference のテンプレートを参照）。

### Step 6: 結果表示

生成したファイルの内容を表示し、次のステップを案内する:

```
.doc_structure.yaml を作成しました。

作成したディレクトリ:（Step 4 で作成した場合のみ表示）
  - docs/specs/requirements/
  - docs/specs/plan/

次のステップ:
- forge が .doc_structure.yaml を直接参照してレビュー・修正時の参考文書を収集します
- .doc_structure.yaml をバージョン管理にコミットしてください
```

---

## Schema Reference

See: `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/doc_structure_format.md`

### Quick reference

```yaml
# doc_structure_version: 3.0

# === rules configuration ===
rules:
  root_dirs:
    - <dir_path>
  doc_types_map:
    <dir_path>: <doc_type>
  patterns:
    target_glob: "**/*.md"
    exclude: []

# === specs configuration ===
specs:
  root_dirs:
    - <dir_path>
  doc_types_map:
    <dir_path>: <doc_type>
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

### 生成例（Feature-Based）

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
    - "docs/specs/**/design/"
    - "docs/specs/**/plan/"
    - "docs/specs/**/requirement/"
  doc_types_map:
    "docs/specs/**/design/": design
    "docs/specs/**/plan/": plan
    "docs/specs/**/requirement/": requirement
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

glob パターン（`*` または `**`）を使う場合、root_dirs と doc_types_map の両方に同じパターンを記述する。`*` は1階層のみ、`**` は任意の深さにマッチする。サブ Feature がある場合は `**` を推奨。

### doc_type 定義（固定。全プロジェクト・全プラグインで共通）

| category | doc_type    | 意味                                   | 含まれる文書の例                                                                      |
| -------- | ----------- | -------------------------------------- | ------------------------------------------------------------------------------------- |
| rules    | rule        | 開発プロセスのルール・規約・手順       | コーディング規約、命名規則、Git ワークフロー、レビュー手順、CI/CD ルール              |
| specs    | requirement | 「何を実現するか」のゴール定義         | ユーザーストーリー、機能要件、非機能要件、ビジネスルール、受入条件                    |
| specs    | design      | 「どう構成するか」の技術的構造         | アーキテクチャ設計、DB スキーマ設計、画面設計、シーケンス図、状態遷移図               |
| specs    | plan        | 「どの順で作るか」の作業計画           | タスク分割、実装順序、マイルストーン、スプリント計画、移行計画                        |
| specs    | api         | 外部インターフェースの契約             | REST エンドポイント定義、リクエスト/レスポンス仕様、OpenAPI/Swagger、GraphQL スキーマ |
| specs    | reference   | 判断の根拠となる補助文書               | 技術調査メモ、比較検討資料、外部仕様の要約、議事録、用語集                            |
| specs    | spec        | 上記に該当しない仕様文書（デフォルト） | 分類不明な仕様文書の一時的な受け皿                                                    |
