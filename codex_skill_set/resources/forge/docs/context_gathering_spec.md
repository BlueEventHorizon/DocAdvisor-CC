# コンテキスト収集仕様書

このファイルは、forge オーケストレータスキルが **コンテキスト収集 agent** に渡す
自己完結型の作業指示書である。

agent はこのファイルを読み、指定されたタスクを実行し、
結果を `{session_dir}/refs/` に書き込む。

---

## 入力パラメータ

オーケストレータから agent に以下のパラメータが渡される:

| パラメータ           | 必須 | 説明                                                               |
| -------------------- | ---- | ------------------------------------------------------------------ |
| `session_dir`        | ○    | セッションディレクトリのパス                                       |
| `spec`               | ○    | この仕様書のパス                                                   |
| `tasks`              | ○    | 実行するタスク名のリスト（YAML list 形式）                         |
| `feature`            | -    | 対象 Feature 名（検索キーワードとして活用）                        |
| `skill_type`         | -    | 作業種別（実装ルール調査の検索キーワード）                         |
| `target_description` | -    | feature がない場合の検索コンテキスト（タスク説明、対象ファイル等） |

```yaml
session_dir: .claude/.temp/start-design-a3f7b2
spec: plugins/forge/docs/context_gathering_spec.md
tasks:
  - 仕様書調査
  - 実装ルール調査
feature: "login" # 省略可能
skill_type: "設計書作成" # 省略可能
target_description: "..." # feature がない場合に使用
```

## 前提

- `session_dir` のパスが agent に渡されていること
- `{session_dir}/refs/` ディレクトリが存在すること（なければ作成）
- 実行するタスクのリストが指定されていること
- `feature`、`skill_type`、`target_description` は検索精度を上げるためのヒントとして活用する
- `feature` が省略された場合、`target_description` や「Issue/Task確認」タスクで得た情報を検索キーワードとして使用する

---

## Issue/Task確認

**目的**: タスクの起点となる Issue や計画書のタスクから、背景・受入条件・関連情報を把握する。

**手順**:

1. ブランチ名から Issue 番号を推定:
   ```bash
   git branch --show-current
   ```
   - `feature/123-xxx` → Issue #123
   - `fix/GH-456` → Issue #456
   - パターンにマッチしない場合 → スキップ

2. Issue が特定できた場合、内容を取得:
   ```bash
   gh issue view {number}
   ```

3. 計画書のタスクが指定されている場合:
   - 計画書ファイルを Read し、該当タスクの詳細を把握する

4. 取得した情報から以下を整理:
   - タスクの目的・背景
   - 受入条件（あれば）
   - 関連する機能名・コンポーネント名

**出力**: なし（後続タスクの検索精度を上げるためのインプット）

---

## 仕様書調査

**目的**: タスクに関連する仕様書（要件定義・設計書・計画書）を特定する。

**検索キーワード**: `feature` があればそれを使用。なければ `target_description` または「Issue/Task確認」で得た情報（機能名・コンポーネント名等）を使用する。

**手順（優先順）**:

### 方法 A: `query-specs` Skill を使用

`query-specs` が利用可能な場合:

```
query-specs {タスクの説明やキーワード}
```

返された文書パスを結果に含める。

### 方法 B: `.doc_structure.yaml` フォールバック

`query-specs` が利用できない場合、`doc-structure` スキルのスクリプトを使用:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/doc-structure/scripts/resolve_doc_structure.py" --type specs
```

JSON 出力の `specs` キーからファイルパス一覧を取得し、関連性を判断する。

### 方法 C: 直接探索

上記いずれも利用できない場合:

```
Glob: docs/specs/**/*.md
Glob: specs/**/*.md
```

ファイルのタイトル行を読み、タスクとの関連性を判断する。

**出力**: `{session_dir}/refs/specs.yaml`

```yaml
source: query-specs # or doc_structure_fallback or direct_search
query: "タスクの説明"
documents:
  - path: specs/requirements/app_overview.md
    reason: "アプリ全体の要件定義"
  - path: specs/design/login_screen_design.md
    reason: "ログイン画面の設計仕様"
```

---

## 実装ルール調査

**目的**: タスクに適用されるプロジェクト固有の開発ルール・規約を特定する。

**手順（優先順）**:

### 方法 A: `query-rules` Skill を使用

`query-rules` が利用可能な場合:

```
query-rules {タスクの説明やキーワード}
```

### 方法 B: `.doc_structure.yaml` フォールバック

`doc-structure` スキルのスクリプトを使用:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 "$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/doc-structure/scripts/resolve_doc_structure.py" --type rules
```

JSON 出力の `rules` キーからファイルパス一覧を取得する。

### 方法 C: 直接探索

```
Glob: docs/rules/**/*.md
Glob: rules/**/*.md
```

**出力**: `{session_dir}/refs/rules.yaml`

```yaml
source: query-rules
query: "タスクの説明"
documents:
  - path: rules/coding_standards.md
    reason: "コーディング規約"
  - path: rules/naming_conventions.md
    reason: "命名規則"
```

---

## 類似PR調査

**目的**: 過去の類似変更から実装パターンやレビュー観点を学ぶ。

**前提条件**: `gh` CLI が利用可能であること。利用できない場合はスキップする。

**手順**:

1. `gh` CLI の利用可否を確認:
   ```bash
   which gh && gh auth status
   ```
   失敗した場合 → このタスク全体をスキップ

2. タスクに関連するキーワードで PR を検索:
   ```bash
   gh pr list --state merged --search "{キーワード}" --limit 5
   ```

3. 見つかった PR の詳細を確認:
   ```bash
   gh pr view {number}
   ```

4. 関連性が高い PR の変更ファイルを確認:
   ```bash
   gh pr diff {number} --name-only
   ```

**出力**: `{session_dir}/refs/prs.yaml`

```yaml
source: gh-pr-search
query: "キーワード"
documents:
  - path: "PR #123: ログイン機能の追加"
    reason: "同じ認証モジュールを変更した直近のPR"
  - path: "PR #98: 画面遷移のリファクタ"
    reason: "ナビゲーション構造の変更パターンの参考"
```

---

## 既存コード調査

**目的**: タスクに関連する既存のソースコード・テスト・類似実装を特定する。

**検索キーワード**: `feature` があればそれを使用。なければ `target_description` または「Issue/Task確認」で得た情報を使用する。

**手順**:

1. 「Issue/Task確認」で得た情報（機能名・コンポーネント名）を元に探索:
   ```
   Grep: {キーワード}（ソースコード内を検索）
   Glob: **/*{コンポーネント名}*（ファイル名で検索）
   ```

2. 以下のカテゴリで分類:
   - **対象ファイルと同一ディレクトリ**のファイル
   - **対象ファイルを import/参照**しているファイル
   - **類似の命名・構造**を持つファイル（同種機能の別実装例）
   - **テストファイル**

3. 各ファイルの関連行範囲を特定（可能な場合）

**出力**: `{session_dir}/refs/code.yaml`

```yaml
source: code-exploration
query: "LoginViewModel"
documents:
  - path: src/features/login/LoginViewModel.swift
    reason: "変更対象のViewModel"
  - path: src/features/login/LoginViewModelTests.swift
    reason: "対象のテストファイル"
    lines: "15-80"
  - path: src/features/profile/ProfileViewModel.swift
    reason: "同種ViewModelの実装パターン参考"
```

---

## エラー時の振る舞い

- 各タスクで検索結果が 0 件の場合: 空の documents で yaml を書き込む
- `query-specs` や `query-rules` が利用不可の場合: フォールバック手段に切り替える
- `gh` CLI が利用不可の場合: 「類似PR調査」をスキップ（refs/prs.yaml を作成しない）
- 予期しないエラーの場合: エラー内容をオーケストレータに報告し、該当タスクをスキップ
