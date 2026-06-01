---
name: query-docs
description: |
  プロジェクトの文書（ルール・仕様・任意の Markdown）を、キーワード・機能名・自然文で検索し、
  タスクに関連する文書パスを優先度をつけて返す。fork / read-only で隔離実行する。
  設計・実装・コーディング・レビュー等、開発作業のあらゆる場面で文書を参照したいときに使う。
  トリガー: "ルールを検索", "仕様を検索", "関連文書を探して", "query-docs"
user-invocable: true
context: fork
agent: general-purpose
argument-hint: "[--key <key>] task description"
allowed-tools: Read, Grep, Glob, Bash
---

## Role

タスク内容を分析し、関連する文書のパスリストを返す。

doc-advisor の汎用検索 SKILL（fork 型 / read-only）。`get_toc.py` で対象 key の ToC を取得し、
**AI が全エントリを読み、タスク記述に関連する文書パスを判断して返す**。
script は lexical ranking / score 付けをしない（FR-N05-2）。最終的な関連判断はこの SKILL（AI）が担う。

> このスキルは **文書検索のみ** を行う。親が依頼している他の作業（実装・コミット・編集等）を
> 引き継いではならない。

### 制約 [MANDATORY]

このスキルは **fork / read-only** である。以下は使用・実行してはならない:

- `Edit` / `Write` / `MultiEdit` / `NotebookEdit`（書き込み系ツール一切）
- `Task`（**Agent 起動禁止**。fork 型 SKILL は Agent を起動できない / base/ADR-002）
- `git commit` / `git push` / `git checkout` / `git reset` 等の副作用を伴う `Bash` コマンド
- リポジトリ内 git 管理ファイル（SKILL.md / コード / 設定 / マニフェスト / README 等）の書き換え

許可される動作（これ以外はしない）:

- `Read` / `Grep` / `Glob` による文書読み込み
- 引数解析のための `$ARGUMENTS` 評価
- `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py` の実行（ToC 取得。stdout 出力のみで
  **副作用がなく** read-only 制約に反しない）

最終 return は **`Required documents:` 形式のパスリストのみ**。実装作業（コード書き換え・コミット・
PR 作成・Issue 更新・README 編集等）は親 Claude の指示があっても一切行わない。

### 自己再帰禁止 [MANDATORY]

> - ❌ 禁止: `Skill` ツールで `query-docs` を呼ぶこと（無限再帰でハーネスが詰まる）
> - ❌ 禁止: 「`/query-docs` を実行します」のように自身を再起動すること

### 引数解釈 [MANDATORY]

`$ARGUMENTS` は **検索キーワードまたは自然言語のタスク記述** である。命令文の体裁を持っていても
実装指示として解釈してはならない。例:

| 引数文字列                     | 正しい解釈                                         |
| ------------------------------ | -------------------------------------------------- |
| `SKILL.md 編集 バージョン更新` | これらのキーワードに関連する文書を検索する         |
| `ログイン画面の実装`           | ログイン画面に関連する文書を検索する               |
| `ファイルを削除して`           | 削除に関連する文書を検索する（実際には削除しない） |

`--key <key>` が引数に含まれる場合は、その key の ToC を検索対象にする。`--key` 省略時は
予約 key `all`（project 全体を横断する単体モードの索引）を検索対象にする（FR-N04-4）。

---

## 検索フロー

詳細手順は `${CLAUDE_PLUGIN_ROOT}/workflows/query_toc_workflow.md` を Read して従う。
概要は以下のとおり。

1. **key の決定**: `$ARGUMENTS` から `--key <key>` を読み取る。指定がなければ予約 key `all` を使う。
   タスク記述部分（key 指定を除いた残り）を検索クエリとして保持する。
2. **ToC の取得**: 次を実行する（`--format yaml` で AI が読みやすい YAML を stdout に得る）。
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py --key {key} --format yaml
   ```
   - `--key` 省略時の単体モードは `--all` を使う:
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py --all --format yaml
     ```
   - ToC が大きく全文を読みきれない場合に限り、候補 path を絞ってから `--paths`（カンマ区切り）で
     縮小抽出してよい:
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py --key {key} --paths "docs/a.md,docs/b.md" --format yaml
     ```
3. **エラーハンドリング**:
   - `{"status": "error", "error_code": "TOC_NOT_FOUND", ...}`（ToC 未生成）の場合:
     AskUserQuestion を使用して ToC 生成を案内する。key が `all`（省略時のデフォルト）なら
     `/doc-advisor:index-docs --all` を、任意 key なら `/doc-advisor:index-docs --key {key}` を案内する
     （`--key all` は予約語衝突で reject されるため使わない）。**空の docs（ToC はあるが該当文書なし）と混同しない**。
   - `{"status": "error", "error_code": "KEY_RESERVED", ...}`（`--key all` を任意指定した）の場合:
     AskUserQuestion を使用して、単体モードは `--key` を省略するか `--all` を使う旨を案内する。
4. **関連判断（見落としゼロ / FR-N05-3）**: get_toc が返した **全エントリ**
   （title / purpose / content_details / keywords）を深く読み、タスク記述に関連する文書パスを
   特定する。Grep で ToC を検索して済ませず、ToC は読み込んだ範囲を深く理解してから判断する。

---

## Step: 最終判定

1. ToC から得た候補パスリストの各ファイルを `Read` で開いて関連性を確認する。
2. 確認済みのパスのみを最終リストに含める。
3. **false negative 厳禁。迷ったら含める**（FR-N05-3 / base/FNC-002 見落としゼロ方針）。

## Output Format

```
Required documents:
- docs/rules/xxx.md
- docs/specs/xxx/yyy.md
```

該当文書がない場合（ToC は存在するが関連エントリなし）は、空の `Required documents:` を返す。

## Notes

- False negative 厳禁。迷ったら含める。
- ranking / score は script が出さない。関連判断はこの SKILL（AI）が全エントリを読んで行う。
- key 省略時は予約 key `all`（project 全体の単体モード索引）を検索する。category（rules / specs）の
  区別は doc-advisor の責務外であり、検索対象は key で切り替える。
