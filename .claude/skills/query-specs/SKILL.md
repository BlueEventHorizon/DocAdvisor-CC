---
name: query-specs
description: |
  プロジェクトの仕様文書（docs/specs/、要件・設計）を検索し、タスクに関連する仕様のパスを返す。
  仕様を参照したいとき: /query-specs <タスク>。
disable-model-invocation: true
user-invocable: true
argument-hint: "<検索タスク>"
allowed-tools: Skill
---

# query-specs

`docs/specs/` の仕様文書（要件・設計）から、タスクに関連するものを探す（このリポジトリ専用 / 配布対象外）。
検索インデックスの作成・更新は `/index-specs` で行う。

## When To Use

- プロジェクトの仕様（要件・設計）を参照したいとき（`/query-specs <タスク>`）
- ルール文書（`docs/rules/`）を探すときは使わない → `/query-rules`

## Workflow

1. Skill ツールで `doc-advisor:query-docs` を `--key specs <$ARGUMENTS>` で起動する。
2. 返ってきた `Required documents:` のパスリストをそのまま返す。
   - 検索対象が未生成（`TOC_NOT_FOUND`）なら、先に `/index-specs` を実行するよう案内する。

## Side Effects

- read-only。

## Validation

- `/query-specs REQ-001 の要件` → 関連する仕様文書のパスが返る。
