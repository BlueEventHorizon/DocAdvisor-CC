---
name: update-forge-toc
description: |
  forge 内蔵ドキュメントの ToC（検索インデックス）を更新する。
  /forge:query-forge-rules の検索結果を最新化したいときに使う。
  トリガー: "forge ToC 更新", "update forge toc", "forge 内蔵ドキュメントの ToC を再生成"
allowed-tools: Bash, Read, Write, Glob
user-invocable: true
argument-hint: ""
---

# update-forge-toc

doc-advisor の `/doc-advisor:create-rules-toc --full` パイプラインを借用して、`plugins/forge/toc/rules_toc.yaml` を AI 品質で自動生成する。

## 前提条件

- `/doc-advisor:create-rules-toc` スキルが利用可能であること

## 実行フロー

> **重要**: Step 2 がエラーになっても **必ず** Step 3 (restore) を実行すること。

### Step 1: 設定の退避と差し替え

```bash
python3 .Codex/skills/update-forge-toc/scripts/swap_doc_config.py --store
```

JSON 出力の `status` を確認:

- `ok` → Step 2 へ
- `error` → 中断（restore 不要）

### Step 2: ToC 生成

`/doc-advisor:create-rules-toc --full` を実行する。

forge_doc_structure.yaml の `output_dir` 設定により、ToC は `plugins/forge/toc/rules/rules_toc.yaml` に直接出力される。コピー不要。

**エラー時**: Step 2 の結果に関わらず **必ず** Step 3 以降を実行する。

### Step 3: 設定の復元

```bash
python3 .Codex/skills/update-forge-toc/scripts/swap_doc_config.py --restore
```

JSON 出力の `status` を確認:

- `ok` → Step 4 へ
- `error` → ユーザーに手動復元を案内: `.Codex/skills/update-forge-toc/.backup/` にバックアップがある

### Step 4: 完了報告

```
forge rules_toc.yaml を更新しました

- 生成元: plugins/forge/docs/, plugins/forge/skills/*/docs/
- 出力先: plugins/forge/toc/rules/rules_toc.yaml (output_dir convention)
- .doc_structure.yaml: 復元済み
```
