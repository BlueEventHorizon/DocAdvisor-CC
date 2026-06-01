---
name: query-rules
description: |
  プロジェクトのルール文書（docs/rules/）を検索し、タスクに関連するルールのパスを返す。
  ルールを参照したいとき: /query-rules <タスク>。
disable-model-invocation: true
user-invocable: true
argument-hint: "<検索タスク>"
allowed-tools: Skill
---

# query-rules

`docs/rules/` のルール文書から、タスクに関連するものを探す（このリポジトリ専用 / 配布対象外）。
検索インデックスの作成・更新は `/index-rules` で行う。

## When To Use

- プロジェクトのルールを参照したいとき（`/query-rules <タスク>`）
- 仕様文書（`docs/specs/`）を探すときは使わない → `/query-specs`

## Workflow

1. Skill ツールで `doc-advisor:query-docs` を `--key rules <$ARGUMENTS>` で起動する。
2. 返ってきた `Required documents:` のパスリストをそのまま返す。
   - 検索対象が未生成（`TOC_NOT_FOUND`）なら、先に `/index-rules` を実行するよう案内する。

## Side Effects

- read-only。

## Validation

- `/query-rules バージョン更新の手順` → 関連するルール文書のパスが返る。
