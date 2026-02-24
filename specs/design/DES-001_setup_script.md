# DES-001: setup.sh 詳細設計

## 概要

`setup.sh` は Doc Advisor のセットアップスクリプト。テンプレートリポジトリからターゲットプロジェクトへ必要なファイルをコピーし、プロジェクト固有の設定ファイルを生成する。

## 基本情報

| 項目 | 値 |
|------|-----|
| ファイル名 | `setup.sh` |
| バージョン | v4.0 |
| 実行要件 | Bash |
| 依存コマンド | `sed`, `find`, `mkdir`, `cp`, `chmod`, `rm` |

## 使用方法

```bash
# 指定したディレクトリにセットアップ
./setup.sh TARGET_DIR

# 対話モード（ディレクトリを対話的に入力）
./setup.sh

# ヘルプ表示
./setup.sh -h
./setup.sh --help
```

## 引数

| 引数 | 必須 | 説明 |
|------|------|------|
| `TARGET_DIR` | 任意 | セットアップ先プロジェクトのパス。省略時は対話的に入力を求める |
| `-h`, `--help` | 任意 | ヘルプメッセージを表示して終了 |

## デフォルト値

| 変数 | デフォルト値 | 説明 |
|------|--------------|------|
| `DEFAULT_AGENT_MODEL` | `opus` | Agent 定義に使用するモデル |
| `PYTHON_PATH` | `python3` | Python 実行パス（shell wrapper 検出時は実パスに切替） |

## 処理フロー

```mermaid
flowchart TD
    A[開始] --> B{引数解析}
    B -->|--help| C[ヘルプ表示] --> Z[終了]
    B -->|TARGET_DIR あり| D[TARGET_DIR 設定]
    B -->|TARGET_DIR なし| E[対話的に入力]

    D --> F[パス正規化]
    E --> F

    F --> F2{.doc_structure.yaml<br>チェック}
    F2 -->|あり| G[Agent モデル選択]
    F2 -->|なし| F3{ユーザー選択}
    F3 -->|Continue| G
    F3 -->|Exit| Z

    G --> H[レガシーファイル削除]

    H --> I[ディレクトリ作成]
    I --> J[config.yaml 確認]
    J --> K[テンプレートコピー<br>変数置換付き]
    K --> L[SessionStart hook<br>settings.json にマージ]
    L --> M[完了メッセージ]
    M --> Z
```

> **Note**: v4.0 で `.doc_structure.yaml` チェックはセットアップの最初に行われる。未検出時はユーザーに Continue/Exit を選択させ、doc-structure プラグインを先にインストールする機会を与える。ディレクトリ分類はターゲットプロジェクト側の `/classify-docs` スキルで AI 駆動で実行する。

---

## 主要関数

### `copy_and_substitute()`

単一ファイルをコピーしながら変数置換を行う。

```bash
copy_and_substitute "$src" "$dst"
```

**置換対象変数:**

| プレースホルダー | 置換値 | 置換方法 |
|------------------|--------|----------|
| `{{AGENT_MODEL}}` | Agent 定義のモデル指定 | `sed` |
| `{{PYTHON_PATH}}` | Python 実行パス | `sed` |
| `{{DOC_ADVISOR_VERSION}}` | Doc Advisor バージョン | `sed` |

**実装:**

```bash
copy_and_substitute() {
    local src="$1"
    local dst="$2"
    if [[ -f "$src" ]]; then
        sed -e "s|{{AGENT_MODEL}}|${AGENT_MODEL}|g" \
            -e "s|{{PYTHON_PATH}}|${PYTHON_PATH}|g" \
            -e "s|{{DOC_ADVISOR_VERSION}}|${DOC_ADVISOR_VERSION}|g" \
            "$src" > "$dst"
    fi
}
```

### `copy_dir_with_substitution()`

ディレクトリを再帰的にコピーし、テキストファイルには変数置換を適用する。

```bash
copy_dir_with_substitution "$src_dir" "$dst_dir"
```

**処理対象ファイル:**

| 拡張子 | 処理 |
|--------|------|
| `.md` | 変数置換してコピー |
| `.yaml` | 変数置換してコピー |
| `.py` | 変数置換してコピー |
| `.sh` | そのままコピー → 実行権限付与 |

---

## v4.0 生成構造

```
TARGET_DIR/
├── .claude/
│   ├── settings.json                # SessionStart hook 登録済み
│   ├── agents/                      # Agent 定義（上書きのみ、1ファイル）
│   │   └── toc-updater.md           # ワーカー: rules/specs の個別エントリ処理
│   ├── skills/
│   │   ├── classify-docs/           # ドキュメントディレクトリ自動分類スキル
│   │   │   └── SKILL.md
│   │   ├── query-rules/             # ドキュメント検索スキル (context: fork)
│   │   │   └── SKILL.md
│   │   ├── query-specs/             # ドキュメント検索スキル (context: fork)
│   │   │   └── SKILL.md
│   │   ├── create-rules-toc/        # rules ToC 生成スキル
│   │   │   └── SKILL.md
│   │   └── create-specs-toc/        # specs ToC 生成スキル
│   │       └── SKILL.md
│   └── doc-advisor/                 # 共有リソース + ランタイム出力
│       ├── config.yaml              # 設定ファイル（root_dirs は空、/classify-docs で設定）
│       ├── docs/                    # ドキュメント
│       │   ├── toc_orchestrator.md
│       │   ├── toc_format.md
│       │   ├── toc_update_workflow.md
│       │   └── classification_rules.md  # /classify-docs 用分類ルール
│       ├── scripts/                 # Python/Shell スクリプト
│       │   ├── toc_utils.py
│       │   ├── classify_dirs.py         # ディレクトリスキャナー
│       │   ├── check_config.sh          # SessionStart hook スクリプト
│       │   ├── create_checksums.py
│       │   ├── create_pending_yaml.py   # --target rules|specs
│       │   ├── write_pending.py         # --target rules|specs
│       │   ├── merge_toc.py             # --target rules|specs
│       │   ├── validate_rules_toc.py
│       │   └── validate_specs_toc.py
│       └── toc/                     # ランタイム出力
│           ├── rules/
│           │   ├── rules_toc.yaml       # 生成される ToC
│           │   ├── .toc_checksums.yaml  # チェックサム
│           │   └── .toc_work/           # 作業ディレクトリ
│           └── specs/
│               ├── specs_toc.yaml
│               ├── .toc_checksums.yaml
│               └── .toc_work/
```

---

## アップグレード処理（v2.0 → v3.0）

### レガシーファイル削除

v2.0 からのアップグレード時、doc-advisor のレガシーファイルを**ファイル名指定で自動削除**する。

#### 削除対象

| レガシーパス | 処理 | 理由 |
|-------------|------|------|
| `commands/create-rules_toc.md` | 自動削除 | Skills に統合 |
| `commands/create-specs_toc.md` | 自動削除 | Skills に統合 |
| `doc-advisor/config.yaml` | 自動削除 | 新しい場所に移動 |
| `doc-advisor/docs/` | 自動削除 | 新しい場所に移動 |

#### 保持されるもの

| パス | 理由 |
|------|------|
| `commands/` 内のユーザー独自コマンド | ユーザー資産の保護 |
| `agents/` 内のユーザー独自エージェント | ユーザー資産の保護 |
| `doc-advisor/toc/rules/`, `doc-advisor/toc/specs/` | ランタイム出力 |

### コピー方式

| ディレクトリ | 方式 | 理由 |
|-------------|------|------|
| `agents/` | **上書きのみ** | ユーザーの独自 agent を保護（管理対象は `toc-updater.md` 1 ファイルのみ） |
| `skills/classify-docs/` | **上書き** | 単一ファイルなので上書きで十分 |
| `skills/query-rules/` | **上書き** | 単一ファイルなので上書きで十分 |
| `skills/query-specs/` | **上書き** | 単一ファイルなので上書きで十分 |
| `skills/create-rules-toc/` | **上書き** | 単一ファイルなので上書きで十分 |
| `skills/create-specs-toc/` | **上書き** | 単一ファイルなので上書きで十分 |
| `skills/doc-advisor/` | **自動削除** | v3.0 レガシー（分割されたため不要） |

### config.yaml の保護

既存の `config.yaml` がある場合、ユーザーに選択肢を提示:

```
Options:
  [o] Overwrite (backup to config.yaml.bak)
  [s] Skip (keep existing config)
  [m] Merge manually (show diff after setup)
```

Overwrite 選択時のバックアップ先: `doc-advisor/config.yaml.bak`

## アップグレード処理（v3.6 → v3.7: advisor agent → skill 移行）

### 削除対象

| レガシーパス | 処理 | 理由 |
|-------------|------|------|
| `agents/rules-advisor.md` | バージョン識別子チェック後に自動削除 | query-rules skill に置き換え |
| `agents/specs-advisor.md` | バージョン識別子チェック後に自動削除 | query-specs skill に置き換え |

### 削除判断

現行バージョン (`DOC_ADVISOR_VERSION`) の `doc-advisor-version-xK9XmQ` 識別子を持つファイルは保護される。識別子がない、または旧バージョンの場合のみ削除する。

---

## アップグレード処理（v3.8: スクリプト・Agent・ドキュメント統合）

### 概要

v3.8 でカテゴリ別に分かれていたスクリプト・Agent・ドキュメントを統合。`--target rules|specs` パラメータで切り替える方式に変更。

### 削除対象（バージョンチェックなし、無条件削除）

統合による置き換えのため、同一バージョンであっても旧ファイルを削除する。

| レガシーパス | 統合先 |
|-------------|--------|
| `agents/rules-toc-updater.md` | `agents/toc-updater.md` |
| `agents/specs-toc-updater.md` | `agents/toc-updater.md` |
| `scripts/create_pending_yaml_rules.py` | `scripts/create_pending_yaml.py` |
| `scripts/create_pending_yaml_specs.py` | `scripts/create_pending_yaml.py` |
| `scripts/write_rules_pending.py` | `scripts/write_pending.py` |
| `scripts/write_specs_pending.py` | `scripts/write_pending.py` |
| `scripts/merge_rules_toc.py` | `scripts/merge_toc.py` |
| `scripts/merge_specs_toc.py` | `scripts/merge_toc.py` |
| `docs/rules_orchestrator.md` | `docs/toc_orchestrator.md` |
| `docs/specs_orchestrator.md` | `docs/toc_orchestrator.md` |
| `docs/rules_toc_format.md` | `docs/toc_format.md` |
| `docs/specs_toc_format.md` | `docs/toc_format.md` |
| `docs/rules_toc_update_workflow.md` | `docs/toc_update_workflow.md` |
| `docs/specs_toc_update_workflow.md` | `docs/toc_update_workflow.md` |

> **Note**: バージョンチェックを行わない理由 — これらは「更新」ではなく「置き換え」であるため。旧ファイル名のまま残すと重複動作の原因となる。

### ディレクトリ選択の廃止

v3.8 でディレクトリ選択機能を廃止。`config.yaml` の `root_dirs` は空配列 `[]` で生成され、`/classify-docs` スキルで自動分類・設定する。

### v4.0: classify-docs 復活と SessionStart hook（v3.8 → v4.0）

| 変更 | 内容 |
|------|------|
| `setup_dirs.sh` 廃止 | `/classify-docs` スキルで完全に代替 |
| `--skip-doc-structure` フラグ廃止 | setup.sh はディレクトリ分類を行わないため不要 |
| `classify-docs` スキル復活 | テンプレートとして `templates/skills/classify-docs/SKILL.md` を配置。AI 駆動でディレクトリを分類 |
| SessionStart hook 導入 | `check_config.sh` が未設定状態を検出し Claude に警告を注入 |
| `settings.json` hook マージ | setup.sh が Python で既存 hooks を壊さずに SessionStart hook を追加 |

---

### 削除判断の原則

```
【重要】識別子ベースの削除ロジック

ファイルに doc-advisor 識別子があるか？
  → ある（現行バージョン）: 管理中 → 削除しない
  → ある（旧バージョン）:   更新対象 → 削除OK
  → ない:                   古い残骸 → 削除OK

※例外: v3.8 統合による置き換え → バージョン問わず無条件削除
```

> **Note**: v3.6 で `doc-advisor-version-xK9XmQ` 識別子が導入済み。v3.7 の advisor agent 削除はこの識別子ベースで動作している。レガシー（v2.0）ファイルは識別子がないためファイル名指定で削除する。v3.8 の統合削除はバージョンチェックなしで動作する。

---

## config.yaml の構造

生成される設定ファイルの構造:

```yaml
# === rules 設定 ===
rules:
  root_dirs: []    # Auto-classified by /classify-docs
  toc_file: .claude/doc-advisor/toc/rules/rules_toc.yaml
  checksums_file: .claude/doc-advisor/toc/rules/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/rules/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude:
      # - reference
      # - archive
  output:
    header_comment: "Development documentation search index for rules-advisor subagent"
    metadata_name: "Development Documentation Search Index"

# === specs 設定 ===
specs:
  root_dirs: []    # Auto-classified by /classify-docs
  toc_file: .claude/doc-advisor/toc/specs/specs_toc.yaml
  checksums_file: .claude/doc-advisor/toc/specs/.toc_checksums.yaml
  work_dir: .claude/doc-advisor/toc/specs/.toc_work/
  patterns:
    target_glob: "**/*.md"
    exclude:
      # - plan  # Uncomment to exclude plan directory
      # - reference
      # - /info/
  output:
    header_comment: "Project specification document search index for specs-advisor subagent"
    metadata_name: "Project Specification Document Search Index"

# === 共通設定 ===
common:
  parallel:
    max_workers: 5               # 並列処理数
    fallback_to_serial: true     # 並列失敗時は直列実行
```

> **Note**: `root_dirs` はテンプレート上はコメントアウト（`# root_dirs: []`）。setup.sh はテンプレートコピーに徹し、ディレクトリ分類は行わない。ターゲットプロジェクトで `/classify-docs` スキルを実行し、AI 駆動で `root_dirs` を設定する。`.doc_structure.yaml` がある場合はランタイムで `root_dirs` を導出するため手動設定は不要。

## SessionStart hook インストール（v4.0）

### 概要

setup.sh はテンプレートコピー後に `.claude/settings.json` へ SessionStart hook を登録する。

### hook スクリプト

`check_config.sh` は以下の順序でチェックする:

0. `cd "$CLAUDE_PROJECT_DIR"` でプロジェクトルートに移動（hook の cwd は不定のため）
1. `.doc_structure.yaml` が存在 → 即 exit 0（出力なし）
2. `config.yaml` に `root_dirs:` が設定済み → 即 exit 0（出力なし）
3. `config.yaml` が存在しない → 即 exit 0（Doc Advisor 未インストール）
4. いずれにも該当しない → 警告メッセージを出力

### マージロジック

既存の `settings.json` を壊さずに hook を追加する:

```python
# 1. 既存 settings.json を読み込み（存在しなければ空 dict）
# 2. hooks.SessionStart 配列に check_config.sh エントリを追加
# 3. 同一コマンドの重複チェック（既に存在すればスキップ）
# 4. JSON として書き戻し
```

### settings.json 出力例

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/doc-advisor/scripts/check_config.sh"
          }
        ]
      }
    ]
  }
}
```

---

## エラーハンドリング

| エラー条件 | 挙動 |
|------------|------|
| 不明なオプション | エラーメッセージ + exit 1 |
| 引数が多すぎる | エラーメッセージ + exit 1 |
| TARGET_DIR が存在しない | エラーメッセージ + exit 1 |
| テンプレートディレクトリが存在しない | Warning 表示 + 続行 |

**スクリプト設定:**
- `set -e`: エラー発生時に即座に終了

## セットアップ後の次のステップ

### .doc_structure.yaml がある場合

ランタイムで `root_dirs` が導出されるため、すぐに ToC 生成が可能:

1. Claude Code を起動:
   ```bash
   cd TARGET_DIR
   claude
   ```
2. 初回 ToC 生成を実行:
   ```
   /create-rules-toc --full
   /create-specs-toc --full
   ```

### .doc_structure.yaml がない場合

SessionStart hook が未設定を警告するので、`/classify-docs` でディレクトリを分類する:

1. Claude Code を起動（SessionStart hook が警告を表示）
2. `/classify-docs` を実行し、AI がディレクトリを分類
3. `/create-rules-toc --full` / `/create-specs-toc --full`

## 注意事項

- templates/ ディレクトリがスクリプトと同じディレクトリに存在する必要がある
- Python スクリプトと Shell スクリプトは変数置換なしでコピーされる（`.py`, `.sh` はそのままコピー）
- `agents/` はディレクトリ削除せず上書きのみ（ユーザーの独自 agent を保護、管理対象は `toc-updater.md` 1 ファイルのみ）
- `skills/doc-advisor/` はクリーンインストール（全削除→再作成）（v3.0 レガシー）
- advisor agent（rules-advisor.md, specs-advisor.md）は自動削除される（v3.7 移行）
- v3.8 統合による旧ファイル（per-category scripts/agents/docs）は無条件削除される
- `config.yaml` が既存の場合はユーザーに確認を求める
- setup.sh はテンプレートコピーと hook 登録に徹し、ディレクトリ分類は行わない
- `config.yaml` の `root_dirs` はコメントアウト状態で生成（`/classify-docs` で設定）
- SessionStart hook は `settings.json` に Python でマージ（既存 hooks を壊さない）
- hook コマンドパスは `"$CLAUDE_PROJECT_DIR"` 環境変数を使用（hook の cwd はプロジェクトルートとは限らないため）
- 旧形式（相対パス）の hook は自動で `$CLAUDE_PROJECT_DIR` 形式にアップグレードされる

## 関連ドキュメント

- `tests/test_setup_upgrade.sh`: アップグレードテスト
