# ToC 検索ワークフロー（key + path I/F）

ToC（キーワード/メタデータ）ベースで、タスクに関連する文書の候補パスを取得する。
**候補パスの取得まで**が本ワークフローの責務。ファイル本文の Read・最終判定は呼び出し元（`query-docs` SKILL）が行う。

> 本ワークフローは DES-005 §11.2（検索ユースケースのシーケンス）/ REQ-001 FR-N05 を実装する。
> ToC は opaque な `key` 単位で管理され、category（rules / specs）の区別は持たない。
> `get_toc.py` は lexical ranking / score 付けをしない（FR-N05-2）。関連判断は呼び出し元の AI が担う。

## パラメータ

| 変数             | 説明                                                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `{key}`          | 検索対象の ToC を示す key。`query-docs` の `--key` 引数。省略時は予約 key `all`（単体モード索引）に解決する（FR-N04-4）。 |
| `{task}`         | 検索対象タスクの説明（関連判断のためのクエリ）。                                                                          |
| `{filter_paths}` | （任意）縮小抽出対象のパスをカンマ区切り。ToC が大きく全文を読みきれない場合に呼び出し元が利用する。                      |

## Procedure

1. `{filter_paths}` が指定されている場合は **Filter Procedure** へ。指定なしの場合は次へ。
2. `get_toc.py` で対象 key の ToC を取得する。AI が読みやすい YAML を stdout に得るため `--format yaml` を使う:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py --key {key} --format yaml
   ```
   - `{key}` が省略（= 単体モード）の場合は `--all` を使う:
     ```bash
     python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py --all --format yaml
     ```
3. 出力を判定する:
   - `{"status": "error", "error_code": "TOC_NOT_FOUND", ...}`（ToC 未生成）の場合: `missing_toc` 状態を返す。
     これは「ToC は存在するが該当文書がない（空の docs）」とは **明確に区別** する。呼び出し元はこれを受けて
     ToC 生成（`/doc-advisor:index-docs --key {key}` または `--all`）を案内する。
   - `{"status": "error", "error_code": "KEY_RESERVED", ...}`（`--key all` の任意指定）の場合: `reserved_key` 状態を返す。
     呼び出し元は単体モードでは `--key` を省略するか `--all` を使う旨を案内する。
   - 正常時（`--format yaml`）: stdout に得られた ToC YAML を読み込み対象とする。
4. 全エントリ（`docs:` 配下の title / purpose / content_details / keywords）を深く理解し、タスク内容から関連候補を特定する。
5. 関連の可能性があるパスを候補リストとして保持する。

## Filter Procedure（{filter_paths} 指定時）

`{filter_paths}` で渡されたパス群に対応する ToC エントリだけを抽出した縮小 YAML を得る。
ToC が大きく（100 件超）AI が全文を読みきれない場合に呼び出し元が利用する。

1. 抽出する:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/get_toc.py \
     --key {key} \
     --paths "{filter_paths}" \
     --format yaml
   ```
   - `{key}` 省略時は `--all` を使う。
   - `{"status": "error", ...}` を返した場合: 候補なし（空リスト）として返す。エラーにしない。
2. 標準出力に得られた縮小 YAML を読み込み対象として扱い、`docs:` 配下のエントリを深く理解する。
3. 関連の可能性があるパスを候補リストとして保持する。

## Critical Rule

**ToC は読み込んだ範囲を深く理解してから判断する。**

- PROHIBITED: Grep/検索ツールで ToC を検索すること
- PROHIBITED: ToC を部分的にしか読まないこと（全文取得時）
- REQUIRED: `get_toc.py --format yaml` で取得した YAML を読み込むこと（全体取得または `--paths` の縮小抽出）
- REQUIRED: 全エントリを理解してから関連文書を特定すること
- False negative 厳禁。迷ったら含める（FR-N05-3 / base/FNC-002 見落としゼロ方針）
