# ToC 候補生成ワークフロー

ToC（キーワード/メタデータ）ベースで関連文書の候補パスを生成する。
**候補パスの生成まで**が責務。ファイル内容の Read・最終判定は呼び出し元が行う。

## パラメータ

| 変数             | 説明                                                                                                |
| ---------------- | --------------------------------------------------------------------------------------------------- |
| `{category}`     | `rules` または `specs`                                                                              |
| `{task}`         | 検索対象タスクの説明                                                                                |
| `{filter_paths}` | （任意）フィルタ対象のパスをカンマ区切り。指定された場合は全量 Read を回避し縮小 ToC を Read する。 |

## Procedure

1. ToC ファイルのパスを決定する:
   - `.doc_structure.yaml` を Read し、`{category}.output_dir` フィールドを確認する
   - `output_dir` が設定されている場合: `{output_dir}/toc/{category}/{category}_toc.yaml`
   - `output_dir` が未設定の場合（デフォルト）: `.claude/doc-advisor/toc/{category}/{category}_toc.yaml`
2. `{filter_paths}` が指定されている場合は **Filter Procedure** へ。指定なしの場合は次へ
3. 決定したパスの ToC ファイルを Read する
   - **ファイルが存在しない場合**: 候補なし（空リスト）として返す。エラーにしない
   - **ファイルが存在する場合**: **全文を Read ツールで読み込む**
4. 全エントリを深く理解し、タスク内容から関連候補を特定する
   - keywords, purpose, title, applicable_tasks を照合
5. 関連の可能性があるパスを候補リストとして保持する

## Filter Procedure（{filter_paths} 指定時）

`{filter_paths}` で渡されたパス群に対応する ToC エントリだけを抽出した縮小 YAML を Read する。
ToC が大きく（100 件超）AI が全文を読みきれない場合に呼び出し元が利用する。

1. 抽出スクリプトを実行する:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/filter_toc.py \
     --category {category} \
     --paths "{filter_paths}"
   ```
   - `{"status": "error", ...}` を返した場合: 候補なし（空リスト）として返す。エラーにしない
2. 標準出力に得られた縮小 YAML を Read 対象として扱い、`docs:` 配下のエントリを深く理解する
   - keywords, purpose, title, applicable_tasks を照合
3. 関連の可能性があるパスを候補リストとして保持する
4. `metadata.missing_paths` がある場合は記録する（呼び出し元の最終判定で本文 Read の対象に加える）

## Critical Rule

**ToC は読み込んだ範囲を深く理解してから判断する。**

- PROHIBITED: Grep/検索ツールで ToC を検索すること
- PROHIBITED: ToC を部分的にしか読まないこと（全文 Read 時）
- REQUIRED: Read ツールで対象 YAML を読み込むこと（全文 Read または filter_toc.py の縮小 YAML）
- REQUIRED: 全エントリを理解してから関連文書を特定すること
- False negative 厳禁。迷ったら含める
