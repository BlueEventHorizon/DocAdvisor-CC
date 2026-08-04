# doc-advisor 詳細ガイド

AI 検索可能なドキュメントインデックス（ToC）生成・検索ツール。文書から AI がメタデータを抽出し、タスクに関連する文書を自動発見する。

doc-advisor は文書集合を `key`（任意の文字列）単位で管理する汎用 ToC Provider であり、`key` の意味（rules / specs 等の分類）を解釈しない。与えられた `key` と project-root-relative の `paths` に対して決定的に動作する。どのファイルを索引化するかの決定は、forge などの上位層、または `--all`（予約 key `all`）の単体モードが担う。

## スキル詳細

### index-docs

```
/doc-advisor:index-docs --key <key> --paths-json '["docs/a.md", "docs/b.md"]'
/doc-advisor:index-docs --key <key> --paths-file paths.json
/doc-advisor:index-docs --all
```

| 引数                   | 説明                                                                                           |
| ---------------------- | ---------------------------------------------------------------------------------------------- |
| `--key <key>`          | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可                       |
| `--paths-json '[...]'` | 当該 key の **完全な desired state** となる project-root-relative path の JSON 配列            |
| `--paths-file <path>`  | **paths 配列そのもの**を収めた JSON ファイル（`["docs/a.md"]`。`--paths-json` の代替）         |
| `--all`                | 単体モード。`--key` 省略と同義で予約 key `all` に解決し、project root 以下の全 Markdown を対象 |

`key` と paths から、その key の ToC を desired-state で生成・更新する。前回 ToC に存在し今回 paths に含まれない path は削除される（部分配列を渡すと残りが消える）。内部は `prepare_toc.py`（差分検出）→ `doc-advisor:toc-updater` カスタム Agent による並列メタデータ充填 → `merge_toc.py`（統合）の協調フローで動作する。

### query-docs

```
/doc-advisor:query-docs [--key <key>] タスクの説明
```

| 引数           | 説明                                                              |
| -------------- | ----------------------------------------------------------------- |
| `--key <key>`  | 検索対象 ToC の key。省略時は予約 key `all`（project 全体）を検索 |
| `タスクの説明` | 関連する文書を検索するためのキーワードまたは自然文のタスク記述    |

ToC（キーワード／メタデータインデックス）でタスクに関連する文書を特定する。`query-docs` は継承型 dispatcher として検索依頼を正規化し、実検索を read-only なカスタム Agent（`doc-advisor:query-worker`）に委譲する。worker が ToC の全エントリを読み、タスク記述に関連する文書パスを判断してマッチしたパスのみを返す。内容の読み込みは呼び出し元エージェントが行う。

## 動作要件

- [Claude Code](https://claude.ai/code) CLI
- Python 3.9 以上（標準ライブラリのみ。追加パッケージは不要）
