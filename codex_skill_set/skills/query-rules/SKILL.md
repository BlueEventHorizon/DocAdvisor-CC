---
name: query-rules
description: |
    Search document indexes to identify rule documents needed for a task.
    Supports ToC (keyword), Index (semantic), and hybrid (auto) modes.
    Trigger:
    - "What rules apply to this task?"
    - Before starting implementation work
metadata:
  short-description: query rules
---

## Codex Skill Resource Root

This skill is distributed by the environment-wide Doc Advisor Codex Skill set.
Resolve `$DOC_ADVISOR_CODEX_ROOT` to `${CODEX_HOME:-~/.codex}/doc-advisor`,
the directory that contains `install.yaml`.

Run bundled Python scripts with absolute paths under
`$DOC_ADVISOR_CODEX_ROOT/resources/...` and prefix them with
`PYTHONDONTWRITEBYTECODE=1` so global resources do not accumulate runtime cache
files. Project runtime output stays under the current project's
`.codex/state/doc-advisor/`.

> **【最重要・無限再帰防止】**
> このファイルは fork されたサブエージェントである **あなた自身への実行指示書** である。
> 親エージェントから渡された `$ARGUMENTS`（タスク説明）に対して、以下の手順を**あなた自身で実行**せよ。
>
> - ❌ 禁止: `Skill` ツールで `query-rules` / `query-specs` / `query-code` / `query-forge-rules` を呼ぶこと（無限再帰でハーネスが詰まる）
> - ❌ 禁止: 「`/query-rules` を実行します」のように、自分が呼び出されたスキルを再起動すること
> - ✅ 必須: 下記 Procedure に従って Read / Bash / user confirmation 等の基本ツールで処理を完了させ、結果を返す

## Role

タスク内容を分析し、関連するルール文書のパスリストを返す。

## 引数パース

`$ARGUMENTS` を解析する:

- `--toc` で始まる → `mode = toc`、残りを `{task}` とする
- `--index` で始まる → `mode = index`、残りを `{task}` とする
- フラグなし → `mode = auto`、全体を `{task}` とする

---

## mode = toc

`$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/query_toc_workflow.md` を Read し、`category = rules` として手順に従う。

- ToC が存在しない場合: user confirmation で `create-rules-toc` の実行を案内する。**Index にフォールバックしない**
- 候補あり → Step: 最終判定 へ

## mode = index

`$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/query_index_workflow.md` を Read し、`category = rules` として手順に従う。

- Index 構築に失敗した場合（OPENAI_API_KEY 未設定等）: user confirmation でエラー内容を通知する。**ToC にフォールバックしない**
- 候補あり → Step: 最終判定 へ

## mode = auto（デフォルト）

### Step 1: Index 候補生成

`$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/query_index_workflow.md` を Read し、`category = rules` として手順に従う。
このとき `search_docs.py` の `--threshold 0.2`（広め）で実行する。
候補パスを内部保持する。失敗時は Index 候補 = 空。

### Step 2: ToC 候補生成

`$DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/docs/query_toc_workflow.md` を Read し、`category = rules` として手順に従う。

ToC ファイルの `metadata.file_count` を確認し、サイズに応じて動作を切り替える:

| ToC のエントリ数 | 動作                                                                                               |
| ---------------- | -------------------------------------------------------------------------------------------------- |
| 100 件以下       | ToC を全量 Read してキーワードマッチング（最高精度を維持）                                         |
| 100 件超         | Filter Procedure を使用。Step 1 の Index 候補を `{filter_paths}` として渡し、縮小 ToC を Read する |

100 件超で Step 1 の Index 候補が空（API キー未設定等）の場合は ToC 全量 Read にフォールバックする。
候補パスを内部保持する。ToC 不在時は ToC 候補 = 空。

### Step 3: 統合

| Index | ToC  | 動作                                                                                          |
| ----- | ---- | --------------------------------------------------------------------------------------------- |
| あり  | あり | union(Index候補, ToC候補) で重複排除 → Step: 最終判定                                         |
| あり  | なし | Index 候補をそのまま使用 → Step: 最終判定                                                     |
| なし  | あり | ToC 候補をそのまま使用 → Step: 最終判定                                                       |
| なし  | なし | user confirmation で通知（`create-rules-toc` 実行 or `OPENAI_API_KEY` 設定を案内） |

---

## Step: 最終判定

1. 統合された候補パスリストの各ファイルを Read して関連性を確認する
2. 確認済みのパスのみを最終リストに含める
3. **false negative 厳禁。迷ったら含める**

## Output Format

```
Required documents:
- rules/core/xxx.md
- rules/layer/domain/xxx.md
- rules/workflow/xxx/xxx.md
- rules/format/xxx.md
```

## Notes

- False negative 厳禁。迷ったら含める
- requirements, design documents, plans は対象外（query-specs を使う）
- 対象は `.doc_structure.yaml` の `rules.root_dirs` で設定されたルール文書のみ

## Error Handling

スクリプトが `{"status": "config_required", ...}` を出力した場合:
user confirmation で `setup-doc-structure` の実行を案内する
