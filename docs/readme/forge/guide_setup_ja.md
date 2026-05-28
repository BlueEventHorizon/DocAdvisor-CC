# セットアップ・ユーティリティガイド

プロジェクトの初期設定、バージョン管理、ルール整理などの運用系スキル。

## setup-doc-structure

プロジェクトのドキュメント配置場所と種別を宣言する `.doc_structure.yaml` を生成する。forge と doc-advisor の共通基盤。

> 詳細は [文書構造ガイド](../guide_doc_structure_ja.md) を参照。

```
/forge:setup-doc-structure
```

引数なし。対話的にプロジェクトをスキャンし、推奨構成を提示する。

---

## setup-version-config

プロジェクトをスキャンしてバージョン管理対象を検出し、`.version-config.yaml` を生成する。`update-version` の前提条件。

```
/forge:setup-version-config
```

引数なし。

### いつ使うか

- プロジェクトで初めてバージョン管理を設定するとき
- プロジェクト構造を変更したとき（プラグイン追加、README フォーマット変更など）

### 実行フロー

1. 既存 `.version-config.yaml` の確認（更新 / 再生成 / キャンセル）
2. `scan_version_targets.py` でバージョンファイル・README・CHANGELOG を自動検出
3. 検出結果を表示し、対話的に設定を調整
4. `.version-config.yaml` を書き出し

### 設定の構造

```yaml
targets:
  - name: forge # ターゲット名
    version_file: plugins/forge/.claude-plugin/plugin.json # バージョンファイル
    version_path: version # JSON パス
    sync_files: # 同期対象
      - path: README.md
        pattern: "| **forge** | {version} |"
        filter: "| **forge**"

changelog:
  file: CHANGELOG.md
  format: keep-a-changelog
  git_log_auto: false

git:
  tag_format: "{target}-v{version}"
  commit_message: "chore: bump {target} to {version}"
  auto_tag: false
  auto_commit: false
```

---

## update-version

`.version-config.yaml` に基づいてバージョンを一括更新する。CHANGELOG への git log 自動反映にも対応。

```
/forge:update-version [target] <patch | minor | major | X.Y.Z>
```

| 引数                        | 説明                                   |
| --------------------------- | -------------------------------------- |
| `target`                    | ターゲット名（省略時は先頭ターゲット） |
| `patch` / `minor` / `major` | バンプ種別                             |
| `X.Y.Z`                     | バージョン番号を直接指定               |

### 使用例

```bash
/forge:update-version patch                # 先頭ターゲットをパッチバンプ
/forge:update-version forge 0.1.0          # forge を 0.1.0 に更新
/forge:update-version anvil minor          # anvil をマイナーバンプ
```

### 実行フロー

1. `.version-config.yaml` の読み込み
2. 現在のバージョン取得
3. main ブランチと比較（既にバンプ済みなら確認）
4. 新バージョンを計算
5. コミット履歴を収集（CHANGELOG 用）
6. ファイル更新
   - `version_file`（plugin.json 等）を更新
   - `sync_files`（README 等）のバージョンを同期
7. CHANGELOG にエントリを挿入
8. テスト実行（`tests/` がある場合）
9. git 操作（commit / push / tag を確認）

### エラー時の対応

| 状況                          | 対応                                            |
| ----------------------------- | ----------------------------------------------- |
| `.version-config.yaml` がない | `/forge:setup-version-config` の実行を案内      |
| 指定ターゲットが存在しない    | 利用可能なターゲット一覧を表示                  |
| テスト失敗                    | バージョン更新は完了済み。テスト修正後に commit |

---

## clean-rules

プロジェクトの `rules/` ディレクトリを分析し、forge 内蔵ドキュメントとの重複削除・ファイル再構築を行う。

```
/forge:clean-rules
```

引数なし。デフォルトは分析レポートのみ出力（変更なし）。

### いつ使うか

- forge 導入後に既存ルールとの重複を整理したいとき
- ルール文書が肥大化・散在して管理が困難になったとき

### 実行フロー

1. **分析**: `rules/` のファイル・セクションを分類
   - Content Type: Constraint / Convention / Format / Process / Decision / Reference
   - Authority: Tool-provided（forge 内蔵）/ Project-defined / External standard
2. **重複検出**: forge 内蔵 docs との類似度をスコアリング
3. **レポート出力**: 削除候補・再構築候補を一覧表示
4. ユーザー確認後に実行:
   - **削除**: forge でカバーされるセクションを除去
   - **再構築**: Content Type が混在する大ファイルを分割・統合
5. `.doc_structure.yaml` と ToC を更新
6. commit 確認

### 安全性

- デフォルトは分析のみ（変更なし）
- 実行前に `git stash` で退避。問題時は `git stash pop` で復元可能
- Project-defined のルールは絶対に削除しない

---

## help

forge スキル一覧を表示し、選択したスキルの引数をガイド付きで構成して実行する。

```
/forge:help
```

引数なし。

### ウィザードの流れ

1. **スキル選択**: 番号で選択
2. **引数構成**: 選択スキルに応じた対話形式の質問
3. **コマンド確認**: 構築されたコマンドを表示して実行確認

```
1. review              : コード・文書のレビュー
2. start-uxui-design   : デザイントークン・UI コンポーネント生成
3. start-requirements  : 要件定義書の作成
4. start-design        : 設計書の作成
5. start-plan          : 計画書の作成
6. start-implement     : タスク実行・実装
7. setup               : 初期設定
```
