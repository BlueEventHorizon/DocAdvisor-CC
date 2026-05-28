---
name: swap-doc-config
description: |
  `.doc_structure.yaml` を一時的に別設定に切り替え、作業後に確実に元へ戻す。
  本番設定を汚さずに、別設定で doc-advisor パイプラインを試したいときに使う。
allowed-tools: Bash
user-invocable: true
argument-hint: "--store|--restore --target <yaml_path> --backup-dir <backup_dir>"
---

# swap-doc-config

`.doc_structure.yaml` を一時的に別のファイルへ差し替える / 元へ戻す。

## 設計原則

- **単一責務**: 差し替え/復元のみ。生成・検索・テスト本体は呼び出し側が担当する
- **生体署名なし**: forge 専用などのデフォルトは持たない。`--target` と `--backup-dir` を呼び出し側が必ず明示する
- **対称性**: `--store` で必ず `--restore` を後続で呼ぶ。例外発生時も restore を保証するのは呼び出し側の責任
- **SKILL 境界での呼び出し**: 他 SKILL・テストから内部関数を import せず、本 SKILL の CLI 経由で利用する
- **バックアップ非破壊**: 既存 `--backup-dir` がある状態での `--store` は **必ず拒否** する。`--force` 等の上書き手段は提供しない（restore し忘れの状態で再 store すると本物のバックアップが消失するため）

## 引数

| 引数           | 説明                                                               |
| -------------- | ------------------------------------------------------------------ |
| `--store`      | 現 `.doc_structure.yaml` をバックアップし、`--target` の内容で置換 |
| `--restore`    | バックアップから `.doc_structure.yaml` を復元                      |
| `--target`     | `--store` 時に差し替え元として使う YAML ファイルパス（必須）       |
| `--backup-dir` | バックアップ保存先ディレクトリ（必須）                             |

> **既存 `--backup-dir` がある場合の `--store` は拒否される**。これは前回の `--restore` 忘れの状態である可能性があり、上書きすると本物のバックアップを失う。先に `--restore` するか、`--backup-dir` の中身を手動で確認すること。

## 出力

JSON を stdout に出力する。`status` で成否を判定する。

- `--store` 成功: `{"status":"ok","action":"store","backed_up":[...],"backup_dir":"..."}`
- `--restore` 成功: `{"status":"ok","action":"restore","restored":[...]}`
- 失敗: `{"status":"error","message":"..."}`

## 呼び出し方

```bash
# 退避と差し替え
python3 ${CLAUDE_PROJECT_DIR}/.claude/skills/swap-doc-config/scripts/swap_doc_config.py \
  --store \
  --target <置換元 yaml> \
  --backup-dir <バックアップ先>

# 復元
python3 ${CLAUDE_PROJECT_DIR}/.claude/skills/swap-doc-config/scripts/swap_doc_config.py \
  --restore \
  --backup-dir <バックアップ先>
```

## 利用ガイドライン

1. `--store` 後は必ず `--restore` を呼ぶ。途中で異常終了した場合、`--backup-dir` から手動で復元できる
2. `--backup-dir` は呼び出し側 SKILL/テストごとに固有の場所を指定する（衝突を避ける）
3. 並行呼び出しはサポートしない。同時に複数の `--store` を発行しないこと
4. 再 store する前に必ず `--restore` を完了させる。既存バックアップがある状態での `--store` は拒否される（上書きで本物の元ファイルを失う事故を防ぐため）
