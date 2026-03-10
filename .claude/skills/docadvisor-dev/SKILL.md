---
name: docadvisor-dev
description: |
  Doc Advisor プロジェクトの構築・開発作業を支援するスキル。
  テンプレート開発、バージョン管理、シンボリックリンク対応、setup.sh の変更などに必要な知識を提供。

  トリガー:
  - 「Doc Advisor を開発」「テンプレートを修正」「setup.sh を変更」
  - 「バージョンを上げる」（→ /update-version も参照）
  - 「新しいプレースホルダーを追加」「Python スクリプトを修正」
  - 「シンボリックリンクの問題」
---

# Doc Advisor 開発スキル

Doc Advisor プロジェクトの構築・開発作業を支援する。

## 必読ドキュメント

作業前に以下を読むこと:

| ドキュメント                                   | 内容                                                                 |
| ---------------------------------------------- | -------------------------------------------------------------------- |
| `TECHNICAL_GUIDE.md` / `TECHNICAL_GUIDE_ja.md` | ドキュメントモデル、アーキテクチャ、設定詳細、トラブルシューティング |
| `rules/docadvisor_development.md`              | 開発ルール全般                                                       |
| `rules/symlink_handling.md`                    | シンボリックリンク対応                                               |
| `rules/version_management.md`                  | バージョン管理                                                       |
| `rules/template_development.md`                | テンプレート開発                                                     |

## プロジェクト構造

```
DocAdvisor-CC/
├── .claude -> privates/.claude   # シンボリックリンク（プライベート）
├── rules/ -> privates/rules/     # 開発ルール
├── specs/ -> privates/specs/     # 仕様書
├── meta/ -> privates/meta/       # 開発履歴・知見
├── templates/                    # テンプレート（パブリック）
│   ├── agents/                   # エージェント定義
│   ├── skills/                   # スキル定義
│   └── doc-advisor/              # ランタイムリソース
├── tests/                        # テスト
├── setup.sh                      # セットアップスクリプト
└── README.md, etc.
```

## 主要な作業パターン

### 1. テンプレートの修正

1. `templates/` 配下のファイルを編集
2. プレースホルダー `{{...}}` を使用（ハードコード禁止）
3. バージョン識別子 `doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}` を確認
4. テスト実行: `cd tests && ./run_all_tests.sh`

### 2. 新しいプレースホルダーの追加

1. `setup.sh` の `copy_and_substitute()` に sed 置換を追加:
   ```bash
   -e "s|{{NEW_PLACEHOLDER}}|${NEW_VALUE}|g" \
   ```
2. `rules/template_development.md` のプレースホルダー表を更新
3. テンプレートでプレースホルダーを使用
4. テスト実行

### 3. Python スクリプトの修正

1. `templates/doc-advisor/scripts/` 配下を編集
2. `toc_utils.py` の共通関数を使用
3. シンボリックリンク対応: `rglob_follow_symlinks()` を使用
4. テスト実行

### 4. バージョン更新

```bash
/update-version 3.4
```

または手動で:

1. `setup.sh` の `DOC_ADVISOR_VERSION` を変更
2. ルートファイル（README, TECHNICAL_GUIDE 等）を更新
3. CHANGELOG.md を更新
4. テスト実行

### 5. 新機能の追加

1. `specs/` に要件定義を作成
2. `meta/history/CONVERSATION_HISTORY.md` に検討内容を記録
3. テンプレートを実装
4. テストを追加
5. ドキュメントを更新

## 重要な教訓（サマリー）

| 教訓                            | 説明                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| doc_type と ToC 生成対象の区別  | plan ディレクトリは存在するが ToC 対象外。doc_type 値は `requirement \| design` のみ  |
| ファイルパスで識別              | ID ではなくファイルパスを識別子として使用。`extract_id_from_filename()` は deprecated |
| 除外パターンの動作              | `should_exclude()` はディレクトリパスのみでマッチ（ファイル名は除外しない）           |
| config.yaml は自動参照されない  | Markdown テンプレートは sed 置換で値を埋め込む                                        |
| Python パスはラッパー環境を考慮 | `{{PYTHON_PATH}}` プレースホルダーを使用。`python3` をハードコードしない              |
| シンボリックリンク対応          | `Path.rglob()` は follow しない、`rglob_follow_symlinks()` を使用                     |
| クロスプラットフォーム          | `sed -i` を避け `awk` を使用                                                          |

詳細は `rules/docadvisor_development.md` を参照。

## テスト

```bash
cd tests && ./run_all_tests.sh
```

テストスイート:

- `test_basic.sh`: 基本セットアップ
- `test_checksums.sh`: チェックサム生成
- `test_write_pending.sh`: pending YAML 書き込み
- `test_merge.sh`: ToC マージ
- `test_custom_dirs.sh`: カスタムディレクトリ名
- `test_edge_cases.sh`: エッジケース
- `test_symlink.sh`: シンボリックリンク対応
- `test_setup_upgrade.sh`: アップグレードテスト

## 関連スキル

| スキル              | 用途                                         |
| ------------------- | -------------------------------------------- |
| `/update-version`   | バージョン番号の一括更新                     |
| `/create-rules-toc` | rules ToC の生成（ターゲットプロジェクト用） |
| `/create-specs-toc` | specs ToC の生成（ターゲットプロジェクト用） |
