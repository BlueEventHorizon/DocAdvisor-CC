---
name: index-docs
description: |
  Generate or update a document ToC (Table of Contents) index from a key and a
  set of project-root-relative paths. Drives one wrapper script that decides
  each next step and returns the agents to launch.
  Use with --key <key> --dirs <dir>... (or --paths / --paths-json), or with
  --all to index every Markdown file under the project root.
  Trigger:
  - After an upper layer decides a key and its desired-state paths
  - "Index docs", "Rebuild the ToC for key X", "Index all Markdown"
allowed-tools: Bash, Read, Agent, AskUserQuestion, Skill
user-invocable: true
argument-hint: "--key <key> --dirs <dir>... | --key <key> --paths-json '[...]' | --all | (no args = --all)"
---

# index-docs

key + project-root-relative paths から ToC（AI 検索用インデックス）を desired-state で生成・更新する生成系 SKILL。

> **このスキルの責務境界**: このスキルは「指定 key（または `--all` の予約 key `all`）の ToC を desired-state 同期する」ことのみを行う。親が依頼している他の作業を引き継いではならない。**原本の Markdown は書き換えない**（`action: done` で AI 抽出結果の書き戻し候補を提示し、承認された場合に限り `write-frontmatter` SKILL へ引き渡す。書き込みはその SKILL の責務）。
>
> **起動経路**: このスキルは **継承型 SKILL**（`context: fork` を指定しない）。`index_docs.py` が返した `agents[]` を `Agent` ツールで並列起動するために fork しない（fork 型 SKILL は Agent を起動できない）。起動経路の名称は `docs/rules/skill_launch_paths_definitions.md` の公式短縮名称に従う。

## このスキルがすること

**`index_docs.py` を呼び、返ってきた `action` に従うだけである。** パイプラインの配管（ディレクトリ展開・差分検出・フロントマターからの転記・並列度の計算・claim・統合）はすべて script が行う。

AI が担うのは次の 2 つだけである。

1. **Agent の起動** — script は起動できないため
2. **判断** — 越境 symlink の承認・充填エラーへの対応・書き戻しの可否

## Usage

```
/doc-advisor:index-docs --key <key> --dirs docs/rules/
/doc-advisor:index-docs --key <key> --dirs docs/specs/ docs/rules/
/doc-advisor:index-docs --key <key> --dirs 'docs/specs/**/design/'   # グロブ可
/doc-advisor:index-docs --key <key> --dirs docs/ --exclude docs/draft/
/doc-advisor:index-docs --key <key> --paths docs/a.md docs/b.md
/doc-advisor:index-docs --key <key> --paths-json '["docs/a.md"]'     # 上位層からの機械的な受け渡し
/doc-advisor:index-docs --all
```

| Argument               | Description                                                                                             |
| ---------------------- | ------------------------------------------------------------------------------------------------------- |
| `--key <key>`          | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可                                |
| `--dirs <dir>...`      | 索引するディレクトリ（複数指定可）。グロブメタ文字（`*` `?` `[`）を含めるとパターン展開                 |
| `--paths <path>...`    | 索引する Markdown ファイル（複数指定可。`--dirs` と併用可）                                             |
| `--paths-json '[...]'` | paths の JSON 配列（上位層が機械的に渡す場合）                                                          |
| `--paths-file <path>`  | paths 配列を含む JSON ファイル                                                                          |
| `--exclude <path>...`  | `--dirs` 展開時に除外するパス・ディレクトリ（システム固定除外は常時適用）                               |
| `--all`                | 単体モード。予約 key `all` に解決し project root 以下の全 Markdown を対象にする。対象指定と併用できない |

> **desired-state の破壊性 [MANDATORY]**: 渡す対象は当該 key の **完全な desired state** である。前回 ToC に存在し今回含まれない path は **削除** される（部分指定すると残りが消える）。上位層の責務である。

## Required Reference Documents [MANDATORY]

処理前に以下を読むこと:

- `${CLAUDE_PLUGIN_ROOT}/workflows/index_toc_orchestrator.md` — `action` ごとの手順と待機ループの終了条件
- `${CLAUDE_PLUGIN_ROOT}/formats/toc_format.md` — ToC スキーマ定義

## Execution Flow

### 唯一のコマンド

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --key "{key}" --dirs {dirs}
# 単体モード
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --all
```

`$ARGUMENTS` から `--key` / `--dirs` / `--paths` / `--paths-json` / `--paths-file` / `--exclude` / `--all` を解釈して渡す。引数が空なら `--all` として扱う。

**初回と再開を区別しない [MANDATORY]**。状態は `.toc_work/` が持ち、script が今どの段階かを判定する。**Agent の完了通知を受けたら、同じコマンドをそのまま再実行する**。前回セッションの続きであっても、compaction を越えていても、同じコマンドで再開できる。

> **コア script を直接呼ばない [MANDATORY]**: `prepare_toc.py` / `merge_toc.py` / `toc_store.py` / `expand_dirs.py` / `frontmatter/fm_to_pending.py` を本 SKILL から呼んではならない。これらは `index_docs.py` が内部で配管しており、直接呼ぶと二重の入口になって状態が食い違う（例: prepare を再実行して充填済み pending を壊す、claim せずに Agent を起動して二重投入する）。これらの CLI はテストと障害切り分けのために残されている。

### `action` ごとの動作

stdout の単一 JSON から `action` を読み、下表に従う。**それ以外の判断をしない**（件数の計算・グループの選択・claim・次段の決定はすべて script が済ませている）。

| `action`   | 動作                                                                               |
| ---------- | ---------------------------------------------------------------------------------- |
| `dispatch` | `agents[]` の各要素で Agent を起動し、完了通知を待って**同じコマンドを再実行**する |
| `wait`     | 走行中の Agent の完了通知を待って**同じコマンドを再実行**する                      |
| `confirm`  | `reason` に応じて `AskUserQuestion` で判断を仰ぎ、決定を引数に足して再実行する     |
| `done`     | 完了レポートを出す。`ai_extracted_paths` が空でなければ書き戻しを確認する          |
| `error`    | `error_code` と `message` を報告し、`AskUserQuestion` でユーザーに対応を確認する   |

#### `action: dispatch`

`agents[]` の各要素を **`run_in_background: true`** で起動する。`prompt` は**そのまま渡せる文字列**であり、key や entry_file を組み立て直してはならない。

```
Agent(subagent_type: "{agents[i].subagent_type}", run_in_background: true,
      prompt: "{agents[i].prompt}")
```

- 複数要素があれば**同一メッセージ内で並列起動する**（1 要素 = 1 Agent）
- claim は script が済ませているため、起動前に何もしない
- `warnings` が空でなければユーザーに提示する
- 起動後、完了通知を受けたら同じコマンドを再実行する。**進捗は簡潔に**（例: `completed 12/29, 5 in-flight`）

#### `action: wait`

未投入の対象は無く、走行中の Agent のみが残っている。完了通知を待って同じコマンドを再実行する。

> **待機ループの終了条件 [MANDATORY]**: 完了通知は起動した Agent の数だけ届く。**通知を待たずに再実行を繰り返してはならない**（同じ `wait` が返るだけで進まない）。何らかの理由で通知が届かない場合、claim のリースが TTL（既定 900 秒）を超えると script が当該 entry を `dispatch` へ戻すため、再実行すれば回復する。それでも `wait` が続く場合は異常であり、ユーザーへ報告して判断を仰ぐ。

#### `action: confirm` / `reason: external_symlink`

明示 paths が **project root の外を指す symlink** を含む。不意のインデックス漏洩を防ぐため既定では索引しない（default-deny / NFR-N06）。書き込みは行われていない。

`external_pending` の各エントリについて、**解決先の実体パス（`resolved`）と件数（`affected_count`）を提示**し、`AskUserQuestion` で許可・不許可を確認する。承認した symlink を並べて再実行する。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --key "{key}" --dirs {dirs} \
  --allow-external "{approved_symlink_1}" "{approved_symlink_2}"
```

すべて拒否する場合は `--allow-external` を値なしで指定する（越境分は drop され、残りで処理される）。

#### `action: confirm` / `reason: fill_error`

充填に失敗した pending が残っている。**そのまま統合してはならない。** merge は completed のみ採用し成功時に `.toc_work/` を削除するため:

- 失敗した文書は **今回の ToC から脱落**する
- とくに **既存文書の改訂（updated）が失敗した場合**、merge が現内容の checksum を書くため、**次回以降も「変更なし」と誤判定され改訂が二度と索引されない（stale 固定）**

`error_pending` の各 `entry_file` と `error_message` を提示し、`AskUserQuestion` で確認する。

| 選択             | 再実行時に足す引数       |
| ---------------- | ------------------------ |
| **再試行**       | `--on-fill-error retry`  |
| **承知で統合**   | `--on-fill-error merge`  |
| **中止**         | `--on-fill-error abort`  |
| **元文書を修正** | 修正後に引数なしで再実行 |

> 失敗が恒常的（元文書の問題）なら再試行は何度やっても成功しない。script はその旨を `warnings` に載せる。

#### `action: done`

完了レポートを出す。**値は JSON からそのまま転記する**（件数を数え直さない）。

```
✅ index-docs complete (key: {key})

[Summary]
- added / updated / deleted / unchanged: {counts}
- フロントマター転記 / AI 抽出: {transcribed} / {ai_extracted}
- toc_path: {toc_path}
- 削除された path: {deleted_paths} (if any)
- reject された path / dir: {rejected_paths} / {rejected_dirs} (if any)
- Warnings: {warnings} (if any)
```

`warnings` は握りつぶさず一覧する。内容には次が含まれうる。

- フロントマターに `doc-advisor` の標識があるのに信頼できない文書（規約違反または本文からの取り残され。当該文書は AI 抽出で索引されている）
- 越境 symlink を索引しなかったこと
- 充填エラーを承知で統合したことによる脱落
- 転記フェーズを実行できなかったこと

### 書き戻しの確認（`ai_extracted_paths` が空でない場合のみ / DES-008 §8.2）

`action: done` で `ai_extracted_paths` が空でない場合のみ実行する。これらの文書は信頼できるフロントマターを持たなかったため AI 抽出で索引された。抽出結果を原本のフロントマターへ書き戻すと、以降その文書は転記だけで索引でき、結果は git を通じて全クローンへ伝播する（コーパスの自己修復）。

**ToC の生成完了「後」に行う [MANDATORY]**。索引という読み取り操作の副作用で原本に git diff が生じるのは驚きがあるためである（REQ-006 の制約）。ここまでの時点で原本は 1 バイトも変わっていない。

1. `ai_extracted_paths` の一覧（件数とパス）を提示し、**書き戻すと原本の Markdown に diff が生じる**ことを明示して `AskUserQuestion` で確認する

   | 選択                 | 動作                                                                 |
   | -------------------- | -------------------------------------------------------------------- |
   | **書き戻す**         | 全件を対象として手順 2 へ                                            |
   | **対象を絞って書く** | 除外する対象を `AskUserQuestion` で確認し、残った対象のみで手順 2 へ |
   | **書き戻さない**     | 何もせず終了する（既定。原本は変更されない）                         |

2. 承認された対象のみを渡して `Skill` ツールで `doc-advisor:write-frontmatter` を起動する

   ```
   Skill(skill: doc-advisor:write-frontmatter,
         args: "--paths-json '[\"{approved_path_1}\", \"{approved_path_2}\"]'")
   ```

   - 引数は **`--paths-json` のみ**。`write-frontmatter` は自身の `AskUserQuestion` で改めてメタデータと書き込みの承認を取る
   - **承認されなかった対象を渡してはならない**
   - **ToC の JSON や `.toc_work/` を `write-frontmatter` に読ませてはならない**。候補パスは本 SKILL が引数として渡す

> **集約結果をファイルに残さない [MANDATORY]**: `ai_extracted_paths` は実行中の確認を簡便にするための一時情報である（DES-008 §8.2）。候補一覧を別ファイル・作業ファイル・ToC へ書き出してはならない。「信頼できるフロントマターを持たない文書の集合」は `fm_read.py` でいつでも再計算できる。

## 異常時の手動クリーンアップ

通常フローでは merge 成功時に `.toc_work/` が削除される。以下の異常系でのみコア script を直接使う（**通常経路では使わない**）。

- **`.toc_work/` を破棄してゼロから再生成したい**（壊れた pending の一掃 / 恒常的な充填エラーからの復帰）:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --clean-work-dir   # 単体モードは --all
  ```

- **削除予定を事前に確認したい**（desired-state の破壊性が不安な場合）:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths_json}' --dry-run
  ```

  `--dry-run` は書き込みをせず件数と path 一覧のみを出す。ディレクトリ指定は展開してから渡す必要がある（`expand_dirs.py`）。

実行前に `AskUserQuestion` でユーザーに確認すること（`--clean-work-dir` は充填済みの作業を破棄しうる）。

## 禁止事項 [MANDATORY]

**NEVER** 以下を行ってはならない:

- ❌ **コア script を通常経路で直接呼ぶこと**（前述）。二重の入口になって状態が食い違う
- ❌ **`agents[].prompt` を組み立て直すこと**。script が渡せる形で返している
- ❌ **並列度・グループ・claim を自分で判断すること**。`available` の計算も `pending_groups` の切り出しも script が済ませている
- ❌ **`.toc_work/` の中身を `ls` / YAML の手読みで調べること**。状態は script の出力が単一の真実である
- ❌ **原本の Markdown を書き換えること**。書き込みは `write-frontmatter` の責務
- ❌ **`error_pending` を握りつぶして統合すること**。脱落と stale 固定を招く
- ❌ commit / push を行うこと

## Error Handling

- `action: error` → `error_code` と `message` を明示して報告し、`AskUserQuestion` でユーザーに対応を確認する
- `KEY_RESERVED`（`--key all` を指定した）→ 予約語衝突である旨を報告し、`--all`（単体モード）に切り替えるか別 key を使うかを確認する
- `KEY_EMPTY` → key を確認するよう報告する
- `UNSUPPORTED_ARG`（`--all` と対象指定の併用等）→ どちらを意図したかを `AskUserQuestion` で確認する
- その他の予期しないエラー: 自動回復・回避を試みず、エラー詳細を明確に報告し、`AskUserQuestion` でユーザーに対応を確認する
