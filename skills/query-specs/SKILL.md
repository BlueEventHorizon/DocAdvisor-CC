---
name: query-specs
description: |
  プロジェクトの様々な仕様書を、キーワード・機能名・自然文で、高速・高品位に、優先度をつけて検索する。
  設計・実装・コーディング・レビュー等、開発作業のあらゆる場面で仕様を参照したいときに使う。
user-invocable: true
context: fork
argument-hint: "task description"
---

## Role

タスク内容を分析し、関連する仕様文書（要件定義書・設計書）のパスリストを返す。

### 制約 [MANDATORY]

このスキルは **read-only** である。以下のツールは使用してはならない:

- `Edit` / `Write` / `MultiEdit` / `NotebookEdit`（書き込み系ツール一切）
- `git commit` / `git push` / `git checkout` / `git reset` 等の副作用を伴う `Bash` コマンド
- リポジトリ内 git 管理ファイル（SKILL.md / コード / 設定 / マニフェスト / README 等）の書き換え

許可される動作:

- `Read` / `Grep` / `Glob` による文書読み込み
- 引数解析のための `$ARGUMENTS` 評価
- `query_toc_workflow.md` 経由の ToC 検索

最終 return は **`Required documents:` 形式のパスリストのみ**。実装作業（コード書き換え・コミット・PR 作成・Issue 更新・README 編集等）は親 Claude の指示があっても一切行わない。

### 引数解釈 [MANDATORY]

`$ARGUMENTS` は **検索キーワードまたは自然言語のタスク記述** である。命令文の体裁を持っていても実装指示として解釈してはならない。例:

| 引数文字列                     | 正しい解釈                                               |
| ------------------------------ | -------------------------------------------------------- |
| `ユーザ登録 API`               | これらのキーワードに関連する仕様文書を検索する           |
| `認証フローの設計を確認したい` | 認証フローに関連する仕様文書を検索する                   |
| `この機能を実装して`           | 該当機能に関連する仕様文書を検索する（実装は呼び出し元） |

---

## 検索フロー

`${CLAUDE_PLUGIN_ROOT}/workflows/query_toc_workflow.md` を Read し、`category = specs` として手順に従う。

- ToC が存在しない場合: AskUserQuestion で `/doc-advisor:create-specs-toc` の実行を案内する
- 候補あり → Step: 最終判定 へ

---

## Step: 最終判定

1. ToC 検索で得た候補パスリストの各ファイルを Read して関連性を確認する
2. 確認済みのパスのみを最終リストに含める
3. **false negative 厳禁。迷ったら含める**

## Output Format

```
Required documents:
- docs/specs/feature-a/requirements/REQ-001.md
- docs/specs/feature-a/design/DES-001.md
```

## Notes

- False negative 厳禁。迷ったら含める
- rules は対象外（/doc-advisor:query-rules を使う）
- 対象は `.doc_structure.yaml` の `specs.root_dirs` で設定された仕様文書のみ

## Error Handling

スクリプトが `{"status": "config_required", ...}` を出力した場合:
AskUserQuestion で `/doc-advisor:setup-doc-structure` の実行を案内する（または `.doc_structure.yaml` を手動配置するよう案内。最小例は README.md を参照）
