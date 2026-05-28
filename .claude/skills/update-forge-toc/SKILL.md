---
name: update-forge-toc
description: |
  forge 内蔵ドキュメントの検索インデックスを更新する。
  /forge:query-forge-rules の検索結果を最新化したいときに使う。
  トリガー: "forge ToC 更新", "update forge toc", "forge インデックス更新", "forge 内蔵ドキュメントの ToC を再生成"
allowed-tools: Bash, Read, Write, Glob, Skill
user-invocable: true
argument-hint: ""
---

# update-forge-toc

`.doc_structure.yaml` を forge 内蔵 docs 用に一時差し替えして、利用可能な検索バックエンドの索引を生成する:

- `/doc-advisor:create-rules-toc` があれば ToC（`plugins/forge/toc/rules/rules_toc.yaml`）を生成
- `/doc-db:build-index` があれば Embedding インデックス（`plugins/forge/index/rules/rules_index.json`）を生成
- 両方あれば両方生成

## 前提条件

- `/swap-doc-config` SKILL が利用可能であること
- `/doc-advisor:create-rules-toc` または `/doc-db:build-index` のいずれかが利用可能であること

## forge 固有の引数

| 値                                               | 内容                                          |
| ------------------------------------------------ | --------------------------------------------- |
| `${CLAUDE_PLUGIN_ROOT}/forge_doc_structure.yaml` | swap-doc-config の `--target` に渡す YAML     |
| `${CLAUDE_PLUGIN_ROOT}/.backup`                  | swap-doc-config の `--backup-dir` に渡す path |

> **注**: `${CLAUDE_PLUGIN_ROOT}` は本 SKILL のディレクトリを指す。

## 実行フロー

> **重要**: Step 2 がエラーになっても **必ず** Step 3 (restore) を実行すること。

### Step 1: 設定の退避と差し替え

Skill ツールで `swap-doc-config` を以下の引数で実行する:

```
--store --target ${CLAUDE_PLUGIN_ROOT}/forge_doc_structure.yaml --backup-dir ${CLAUDE_PLUGIN_ROOT}/.backup
```

JSON 出力の `status` を確認:

- `ok` → Step 2 へ
- `error` → 中断（restore 不要）。`message` に `Backup already exists` が含まれる場合は前回 `--restore` し忘れの状態。`${CLAUDE_PLUGIN_ROOT}/.backup/` の中身を確認した上で `--restore` を実行して復旧してから再試行する

### Step 2: バックエンド判定と索引生成

available-skills に含まれるバックエンドを確認し、含まれているものを **すべて** 実行する。
どちらかでもエラーになっても、もう片方は続行する。

#### 2a. ToC 生成（`/doc-advisor:create-rules-toc` がある場合）

Skill ツールで `/doc-advisor:create-rules-toc` を実行する（incremental モード）。初回や checksums がない場合は自動で full にフォールバックする。

forge_doc_structure.yaml の `output_dir` 設定により、ToC は `plugins/forge/toc/rules/rules_toc.yaml` に直接出力される。

#### 2b. Embedding インデックス生成（`/doc-db:build-index` がある場合）

Skill ツールで `/doc-db:build-index --category rules` を実行する。

forge_doc_structure.yaml の `output_dir` 設定により、インデックスは `plugins/forge/index/rules/rules_index.json` に直接出力される。

#### 2c. 利用可能なバックエンドがない場合

両方とも available-skills に含まれない場合は、Step 3 で設定を復元したうえでエラー報告:

```
ERROR: 検索バックエンドが見つかりません
       doc-advisor または doc-db のいずれかをインストールしてください
```

**エラー時**: Step 2a / 2b の結果に関わらず **必ず** Step 3 以降を実行する。

### Step 3: 設定の復元

Skill ツールで `swap-doc-config` を以下の引数で実行する:

```
--restore --backup-dir ${CLAUDE_PLUGIN_ROOT}/.backup
```

JSON 出力の `status` を確認:

- `ok` → Step 4 へ
- `error` → ユーザーに手動復元を案内: `${CLAUDE_PLUGIN_ROOT}/.backup/` にバックアップがある

### Step 4: 完了報告

実行したバックエンドに応じて以下を出力する:

```
forge 内蔵 docs の検索インデックスを更新しました

- 生成元: plugins/forge/docs/, plugins/forge/skills/*/docs/
- ToC: plugins/forge/toc/rules/rules_toc.yaml ({doc-advisor を実行した場合のみ})
- インデックス: plugins/forge/index/rules/rules_index.json ({doc-db を実行した場合のみ})
- .doc_structure.yaml: 復元済み
```
