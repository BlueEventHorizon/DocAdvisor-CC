---
name: index-rules
description: |
  プロジェクトのルール文書（docs/rules/）の検索インデックスを作成・更新する。
  ルール文書を追加・改訂したあとに実行する: /index-rules。
disable-model-invocation: true
user-invocable: true
allowed-tools: Skill
---

# index-rules

`docs/rules/` のルール文書から検索インデックスを作成・更新する（このリポジトリ専用 / 配布対象外）。
検索は `/query-rules` で行う。

## When To Use

- ルール文書を追加・改訂し、検索インデックスを更新したいとき（`/index-rules`）
- 仕様文書（`docs/specs/`）のインデックスは使わない → `/index-specs`

## Workflow

1. Skill ツールで `doc-advisor:index-docs` を次の引数で起動する。

   ```text
   --key rules --dirs-json '["docs/rules/"]'
   ```

2. 完了レポート（added / updated / deleted / toc_path）をそのまま伝える。

## Side Effects

- 検索インデックスを生成・更新する（`docs/rules/` 配下が対象）。

## Validation

- `/index-rules` → `docs/rules/` から検索インデックスが作られ、`/query-rules <タスク>` で検索できる。
