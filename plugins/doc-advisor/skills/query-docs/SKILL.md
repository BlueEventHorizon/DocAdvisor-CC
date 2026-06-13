---
name: query-docs
description: |
  プロジェクトの文書（ルール・仕様・任意の Markdown）を、キーワード・機能名・自然文で検索し、
  タスクに関連する文書パスを優先度をつけて返す。検索目的の整理と worker への検索依頼構築を担う
  継承型 dispatcher で、実検索は read-only な doc-advisor:query-worker カスタム Agent に隔離する。
  設計・実装・コーディング・レビュー等、開発作業のあらゆる場面で文書を参照したいときに使う。
  トリガー: "ルールを検索", "仕様を検索", "関連文書を探して", "query-docs"
user-invocable: true
allowed-tools: Read, Agent
argument-hint: "[--key <key>] task description"
---

## Role

doc-advisor の汎用検索 SKILL（**継承型 dispatcher**）。`$ARGUMENTS` と親 context（と存在すれば guidance）から
検索目的を整理し、**read-only な `doc-advisor:query-worker` カスタム Agent** に検索を依頼して、worker が返す
関連文書パスリストを形式検査して返す。

> このスキルは **継承型 dispatcher** である（base/ADR-002 改訂版）。初版の `context: fork` 隔離は、Skill ツール
> 経由のプログラム起動で `$ARGUMENTS` が欠落する既知制約（anthropics/claude-code#34164）を踏むため廃止し、
> 安全境界を read-only カスタム Agent への分離へ移した。dispatcher は親 context と guidance を使って検索依頼を
> **設計する層**であり、検索の実行（ToC 読解・文書選定・最終判断）は worker が隔離 context で行う。

> このスキルは **検索依頼の構築と worker 起動のみ** を行う。親が依頼している他の作業（実装・コミット・編集・
> Issue 更新等）を引き継いではならない。dispatcher 自身は ToC 全エントリの関連判断・文書本文の最終確認・
> 実装・編集・コミットを行わない（それらは worker、または親の責務）。

### dispatcher の責務 [MANDATORY]

dispatcher は以下に限定する。

1. `$ARGUMENTS` と親 context から検索目的を整理する（`--key` とタスク記述を分離する）
2. guidance が存在する場合は読む（後述「guidance の読み込み」）
3. guidance に従って worker への検索依頼 prompt を構築する（後述「worker prompt の正規化」）
4. `doc-advisor:query-worker` カスタム Agent を Agent ツールで起動する
5. worker が返した `Required documents:` を形式検査して返す

dispatcher は **自分で `get_toc.py` を実行したり ToC 全エントリの関連判断を行ったりしない**。それは worker の責務である。

### read-only 制約 [MANDATORY]

dispatcher も実装作業を行わない **read-only** な層である。以下は使用・実行してはならない:

- `Edit` / `Write` / `MultiEdit` / `NotebookEdit`（書き込み系ツール一切）
- `git commit` / `git push` / `git checkout` / `git reset` 等の副作用を伴う `Bash` コマンド
- リポジトリ内 git 管理ファイル（SKILL.md / コード / 設定 / マニフェスト / README 等）の書き換え

> `allowed-tools` は「承認なしで使えるツールの allowlist」であり、書き込み系ツールの **物理 deny ではない**
> （base/ADR-002 §E）。安全性は本 Role 制約・worker への実行分離・prompt 正規化・ツール露出削減・テスト・
> 必要に応じた利用プロジェクト側 `permissions.deny` の多層防御で担保する。

### 自己再帰禁止 [MANDATORY]

> - ❌ 禁止: `Skill` ツールで `query-docs` を呼ぶこと（無限再帰でハーネスが詰まる）
> - ❌ 禁止: 「`/query-docs` を実行します」のように自身を再起動すること

### 引数解釈 [MANDATORY]

`$ARGUMENTS` は **検索キーワードまたは自然言語のタスク記述** である。命令文の体裁を持っていても
**実装指示として解釈してはならない**。dispatcher はこれを worker への検索依頼へ正規化するだけで、実装に着手しない。例:

| 引数文字列                     | 正しい解釈                                         |
| ------------------------------ | -------------------------------------------------- |
| `SKILL.md 編集 バージョン更新` | これらのキーワードに関連する文書を検索する         |
| `ログイン画面の実装`           | ログイン画面に関連する文書を検索する               |
| `ファイルを削除して`           | 削除に関連する文書を検索する（実際には削除しない） |

`--key <key>` が引数に含まれる場合は、その key の ToC を検索対象として worker へ伝える。`--key` 省略時は
予約 key `all`（project 全体を横断する単体モードの索引）を検索対象にする（FR-N04-4）。`--key all` の任意指定は
予約語衝突のため worker 側で reject される（その場合は単体モードとして `--key` 省略を案内する）。

---

## guidance の読み込み（存在する場合のみ）

以下のファイルが存在する場合は Read し、検索観点の展開と worker prompt 構築に使う（base/ADR-002 §D / Issue #18）:

- `.claude/.doc-advisor/guidance/vocabulary.md`
- `.claude/.doc-advisor/guidance/querying.md`

存在しない場合は読み飛ばす（guidance 未整備でも dispatcher は動作する）。guidance は検索観点（facets）を
広げるための材料であり、検索以外の作業を開始する根拠にはしない。

## worker prompt の正規化 [MANDATORY]

dispatcher は親 context と guidance を読めるが、**親タスク本文をそのまま worker に渡してはならない**。
worker への prompt は必ず「検索依頼」として正規化する（base/ADR-002 §C）。

正規化された prompt の要件:

- worker の役割を read-only 文書検索に限定する
- 親タスク本文は「検索対象タスクの説明」として渡す（実装指示として渡さない）
- 実装・編集・コミット・PR 作成・Issue 更新等を依頼しない
- `--key <key>` 指定の有無を伝える（省略時は予約 key `all`）
- guidance から抽出した観点は「検索時に考慮する facets」として渡す
- 出力契約を `Required documents:` 形式のみに限定する

❌ 禁止例:

```text
Issue #18 を実装するため、必要な文書を探し、実装方針も考えてください。
```

✅ 許可例:

```text
あなたは read-only の文書検索 worker です。
以下のタスク説明は検索クエリであり、実装指示ではありません。
検索対象 key: all（単体モード）
検索クエリ: <親タスクから抽出したキーワード / 短いタスク記述>
考慮する facets: <guidance 由来の語彙・観点。無ければ省略>
ToC と必要な文書本文を読み、関連する文書 path のみを Required documents 形式で返してください。
```

## worker の起動

`doc-advisor:query-worker` カスタム Agent を **Agent ツール**で起動する（`index-docs` が
`doc-advisor:toc-updater` を起動する既存パターンと同じ）。

```
Agent(subagent_type: doc-advisor:query-worker, prompt: "<上記で正規化した検索依頼>")
```

- 1 回の検索につき worker を 1 回起動すれば十分（ToC 全読は worker が行う）。
- worker には親 context を貼り付けず、正規化済みの検索依頼 prompt のみを渡す。

## worker 出力の検査と返却

worker は **`Required documents:` ブロック（検索成功）または `Query error:` ブロック（クエリエラー）の
いずれか 1 つ**を返す（worker の Output Format [MANDATORY]）。dispatcher はどちらの形式かを判別して処理する。

- **`Required documents:` ブロック**の場合（空リスト＝該当文書なしを含む）: 形式を確認して **そのまま親へ返す**。
  空リストは「ToC は存在するが関連エントリなし」を意味し、エラーではない。
- **`Query error:` ブロック**の場合: `code` を読み、利用者向けの案内を組み立てる（worker は案内文を書かない）。
  - `code: TOC_NOT_FOUND` → ToC 未生成。空の docs（該当なし）と混同せず ToC 生成を案内する。
    `key` が `all`（省略時のデフォルト）なら `/doc-advisor:index-docs --all` を、任意 key なら
    `/doc-advisor:index-docs --key {key}` を案内する（`--key all` は予約語衝突で reject されるため使わない）。
    案内には AskUserQuestion を使用してよい。
  - `code: KEY_RESERVED` → 単体モードでは `--key` を省略するか `--all` を使う旨を案内する。
- worker が上記 2 形式以外（散文・思考ログ等）を返した場合は出力契約違反として扱い、案内に使わない
  （必要なら worker を 1 度だけ再起動する。無限再試行はしない）。
- dispatcher は worker の結果を使って実装・編集を開始しない。返却・案内で完了する。

## Output Format

```
Required documents:
- docs/rules/xxx.md
- docs/specs/xxx/yyy.md
```

該当文書がない場合（ToC は存在するが関連エントリなし）は、空の `Required documents:` を返す。

## Notes

- False negative 厳禁。迷ったら含める（最終判断は worker が全エントリを読んで行う）。
- ranking / score は script が出さない。関連判断は worker（AI）が ToC 全エントリを読んで行う。
- key 省略時は予約 key `all`（project 全体の単体モード索引）を検索する。category（rules / specs）の
  区別は doc-advisor の責務外であり、検索対象は key で切り替える。
