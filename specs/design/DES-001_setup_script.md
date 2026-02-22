# DES-001: setup.sh 詳細設計

## 概要

`setup.sh` は Doc Advisor のセットアップスクリプト。テンプレートリポジトリからターゲットプロジェクトへ必要なファイルをコピーし、プロジェクト固有の設定ファイルを生成する。

## 基本情報

| 項目 | 値 |
|------|-----|
| ファイル名 | `setup.sh` |
| バージョン | v3.8 |
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

    F --> G[Agent モデル選択]
    G --> H[レガシーファイル削除]

    H --> I[ディレクトリ作成]
    I --> J[config.yaml 確認]
    J --> K[テンプレートコピー<br>変数置換付き]
    K --> M{config skip?}
    M -->|No| N[自動分類<br>classify_dirs.py --apply]
    M -->|Yes| O[分類スキップ]
    N --> L[完了メッセージ]
    O --> L
    L --> Z
```

> **Note**: v3.8 でディレクトリ選択ループは廃止。テンプレートコピー後に `classify_dirs.py --apply` を自動実行し、`config.yaml` の `root_dirs` を設定する。config を保持（skip）した場合は自動分類をスキップする。

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

## v3.8 生成構造

```
TARGET_DIR/
└── .claude/
    ├── agents/                      # Agent 定義（上書きのみ、1ファイル）
    │   └── toc-updater.md           # ワーカー: rules/specs の個別エントリ処理
    ├── skills/
    │   ├── classify-docs/           # ドキュメントディレクトリ自動分類スキル
    │   │   └── SKILL.md
    │   ├── query-rules/             # ドキュメント検索スキル (context: fork)
    │   │   └── SKILL.md
    │   ├── query-specs/             # ドキュメント検索スキル (context: fork)
    │   │   └── SKILL.md
    │   ├── create-rules-toc/        # rules ToC 生成スキル
    │   │   └── SKILL.md
    │   └── create-specs-toc/        # specs ToC 生成スキル
    │       └── SKILL.md
    └── doc-advisor/                 # 共有リソース + ランタイム出力
        ├── config.yaml              # 設定ファイル（root_dirs は空、/classify-docs で設定）
        ├── docs/                    # ドキュメント
        │   ├── toc_orchestrator.md
        │   ├── toc_format.md
        │   └── toc_update_workflow.md
        ├── scripts/                 # Python スクリプト
        │   ├── toc_utils.py
        │   ├── classify_dirs.py
        │   ├── create_checksums.py
        │   ├── create_pending_yaml.py   # --target rules|specs
        │   ├── write_pending.py         # --target rules|specs
        │   ├── merge_toc.py             # --target rules|specs
        │   ├── validate_rules_toc.py
        │   └── validate_specs_toc.py
        └── toc/                     # ランタイム出力
            ├── rules/
            │   ├── rules_toc.yaml       # 生成される ToC
            │   ├── .toc_checksums.yaml  # チェックサム
            │   └── .toc_work/           # 作業ディレクトリ
            └── specs/
                ├── specs_toc.yaml
                ├── .toc_checksums.yaml
                └── .toc_work/
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

> **Note**: `root_dirs` はテンプレート上は空配列 `[]`。setup.sh のテンプレートコピー後に `classify_dirs.py --apply` が自動実行され、プロジェクト内のドキュメントディレクトリを分類して `root_dirs` を設定する。config を保持（skip）した場合は自動分類をスキップする。

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

### 通常（config 新規作成/上書き時）

auto-classify によりドキュメントディレクトリが自動設定されるため、すぐに ToC 生成が可能:

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

### config 保持（skip）時

既存の config.yaml を保持した場合、自動分類はスキップされる:

1. Claude Code を起動
2. 必要に応じて `/classify-docs` でディレクトリを更新
3. `/create-rules-toc --full` / `/create-specs-toc --full`

## 注意事項

- templates/ ディレクトリがスクリプトと同じディレクトリに存在する必要がある
- Python スクリプトと Shell スクリプトは変数置換なしでコピーされる
- `agents/` はディレクトリ削除せず上書きのみ（ユーザーの独自 agent を保護、管理対象は `toc-updater.md` 1 ファイルのみ）
- `skills/doc-advisor/` はクリーンインストール（全削除→再作成）（v3.0 レガシー）
- advisor agent（rules-advisor.md, specs-advisor.md）は自動削除される（v3.7 移行）
- v3.8 統合による旧ファイル（per-category scripts/agents/docs）は無条件削除される
- `config.yaml` が既存の場合はユーザーに確認を求める
- 自動分類は `classify_dirs.py --apply` で実行（frontmatter doc_type → 用語ランキング → ディレクトリ名ヒューリスティック）
- `config.yaml` の `root_dirs` は空配列で生成（`/classify-docs` で設定）

## 関連ドキュメント

- `tests/test_setup_upgrade.sh`: アップグレードテスト
