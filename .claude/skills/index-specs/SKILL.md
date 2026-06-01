---
name: index-specs
description: |
  プロジェクトの仕様文書（docs/specs/、要件・設計）の検索インデックスを作成・更新する。
  仕様文書を追加・改訂したあとに実行する: /index-specs。
disable-model-invocation: true
user-invocable: true
allowed-tools: Skill
---

# index-specs

`docs/specs/` の仕様文書（要件・設計）から検索インデックスを作成・更新する（このリポジトリ専用 / 配布対象外）。
検索は `/query-specs` で行う。

## When To Use

- 仕様文書を追加・改訂し、検索インデックスを更新したいとき（`/index-specs`）
- ルール文書（`docs/rules/`）のインデックスは使わない → `/index-rules`

## Workflow

1. Skill ツールで `doc-advisor:index-docs` を次の引数で起動する。

   ```text
   --key specs --dirs-json '["docs/specs/"]'
   ```

2. 完了レポート（added / updated / deleted / toc_path）をそのまま伝える。

## Side Effects

- 検索インデックスを生成・更新する（`docs/specs/` 配下が対象）。

## Validation

- `/index-specs` → `docs/specs/` から検索インデックスが作られ、`/query-specs <タスク>` で検索できる。
