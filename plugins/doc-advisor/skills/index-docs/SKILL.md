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

> **このスキルの責務境界**: このスキルは「指定 key（または `--all` の予約 key `all`）の ToC を desired-state 同期する」ことのみを行う。親が依頼している他の作業を引き継いではならない。**原本の Markdown は書き換えない**（`action: done` で AI 抽出結果の書き戻し候補を `write-frontmatter` SKILL へ引き渡す。承認の要否の判定と書き込みはその SKILL の責務）。
>
> **起動経路**: このスキルは **継承型 SKILL**（`context: fork` を指定しない）。`index_docs.py` が返した `agents[]` を `Agent` ツールで並列起動するために fork しない（fork 型 SKILL は Agent を起動できない）。起動経路の名称は `docs/rules/skill_launch_paths_definitions.md` の公式短縮名称に従う。

## このスキルがすること

**`index_docs.py` を呼び、返ってきた `action` に従うだけである。** パイプラインの配管（ディレクトリ展開・差分検出・フロントマターからの転記・並列度の計算・claim・統合）はすべて script が行う。

AI が担うのは次の 2 つだけである。

1. **Agent の起動** — script は起動できないため
2. **判断** — 越境 symlink の承認・充填エラーへの対応（書き戻しの承認判定は `write-frontmatter` の責務）

## Usage

```
/doc-advisor:index-docs --key <key> --dirs docs/rules/
/doc-advisor:index-docs --key <key> --dirs docs/specs/ docs/rules/
/doc-advisor:index-docs --key <key> --dirs 'docs/specs/**/design/'   # グロブ可
/doc-advisor:index-docs --key <key> --dirs docs/ --exclude docs/draft/
/doc-advisor:index-docs --key <key> --paths docs/a.md docs/b.md
/doc-advisor:index-docs --all

# 上位層（forge 等）が機械的に渡す形
/doc-advisor:index-docs --key <key> --dirs-json '["docs/rules/"]' --exclude-json '["docs/rules/draft/"]'
/doc-advisor:index-docs --key <key> --paths-json '["docs/a.md"]'
```

| Argument                 | Description                                                                                                                                                                                                                                                |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--key <key>`            | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可                                                                                                                                                                                   |
| `--dirs <dir>...`        | 索引するディレクトリ（複数指定可）。グロブメタ文字（`*` `?` `[`）を含めるとパターン展開                                                                                                                                                                    |
| `--dirs-json '[...]'`    | dirs の JSON 配列（**上位層が機械的に渡す形**。`--dirs` と併用可）                                                                                                                                                                                         |
| `--paths <path>...`      | 索引する Markdown ファイル（複数指定可。`--dirs` と併用可）                                                                                                                                                                                                |
| `--paths-json '[...]'`   | paths の JSON 配列（**上位層が機械的に渡す形**）                                                                                                                                                                                                           |
| `--paths-file <path>`    | **paths 配列そのもの**を収めた JSON ファイル（`["docs/a.md"]`。`{"paths": [...]}` ではない）。**他の対象指定（`--dirs` / `--dirs-json` / `--paths` / `--paths-json`）とは併用できない**（連結する先が無いため。黙って捨てず `UNSUPPORTED_ARG` で拒否する） |
| `--exclude <path>...`    | 確定した対象集合から除外するパス・ディレクトリ（`--dirs` / `--paths` のどちらでも効く。システム固定除外は常時適用）。**`--all` / `--paths-file` とは併用できない**（対象集合がラッパーの手元に無いため。黙って無視せず `UNSUPPORTED_ARG` で拒否する）      |
| `--exclude-json '[...]'` | exclude の JSON 配列（**上位層が機械的に渡す形**。`--exclude` と併用可）                                                                                                                                                                                   |
| `--all`                  | 単体モード。予約 key `all` に解決し project root 以下の全 Markdown を対象にする。対象指定と併用できない                                                                                                                                                    |

> **JSON 形をそのまま渡す [MANDATORY]**: 上位層（forge の `update-db-rules` / `update-db-specs` 等）は `.doc_structure.yaml` から解決した配列を `--dirs-json` / `--exclude-json` で渡し、**本 SKILL を 1 回だけ呼ぶ**（再実行や引数の組み替えをしない）。受け取った JSON 形は**そのまま script へ渡す**こと。`--dirs` へ書き換えたり要素を並べ替えたりしない。script が両形を受け付けて連結する。

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

`$ARGUMENTS` から `--key` / `--dirs` / `--dirs-json` / `--paths` / `--paths-json` / `--paths-file` / `--exclude` / `--exclude-json` / `--all` を解釈して渡す。引数が空なら `--all` として扱う。**JSON 形（`--dirs-json` 等）は形を変えずそのまま渡す**（前掲の [MANDATORY]）。

> **`--key` の省略は「引数が空」とは別である [MANDATORY]**（REQ-001 FR-N04-1 / FR-N04-5）。`--key` を省くと、対象指定の有無にかかわらず**単体モード**（project root 以下の全走査）になる。したがって `--key` を省いたまま `--dirs` / `--paths` / `--exclude` を渡すことはできず、script が `UNSUPPORTED_ARG` で拒否する。**対象を指定して索引するなら `--key` を必ず渡すこと。** 上位層から key を受け取っていない場合に、対象指定だけを渡して呼んではならない（拒否されるか、拒否が無い実装では project root 全体が索引され、desired-state のため ToC の内容が全件へ置き換わる）。

**初回と再開を区別しない [MANDATORY]**。状態は `.toc_work/` が持ち、script が今どの段階かを判定する。**Agent の完了通知を受けたら、同じコマンドをそのまま再実行する**。前回セッションの続きであっても、compaction を越えていても、同じコマンドで再開できる。

> **コア script を直接呼ばない [MANDATORY]**: `prepare_toc.py` / `merge_toc.py` / `toc_store.py` / `expand_dirs.py` / `frontmatter/fm_to_pending.py` を本 SKILL から呼んではならない。これらは `index_docs.py` が内部で配管しており、直接呼ぶと二重の入口になって状態が食い違う（例: prepare を再実行して充填済み pending を壊す、claim せずに Agent を起動して二重投入する）。これらの CLI はテストと障害切り分けのために残されている。

### `action` ごとの動作

stdout の単一 JSON から `action` を読み、下表に従う。**それ以外の判断をしない**（件数の計算・グループの選択・claim・次段の決定はすべて script が済ませている）。

| `action`   | 動作                                                                               |
| ---------- | ---------------------------------------------------------------------------------- |
| `dispatch` | `agents[]` の各要素で Agent を起動し、完了通知を待って**同じコマンドを再実行**する |
| `wait`     | 走行中の Agent の完了通知を待って**同じコマンドを再実行**する                      |
| `confirm`  | `reason` に応じて `AskUserQuestion` で判断を仰ぎ、決定を引数に足して再実行する     |
| `done`     | 完了レポートを出す。`ai_extracted_paths` が空でなければ書き戻しへ引き渡す          |
| `error`    | `error_code` と `message` を報告し、`AskUserQuestion` でユーザーに対応を確認する   |

#### `action: dispatch`

`agents[]` の各要素を **`run_in_background: true`** で起動する。`prompt` は**そのまま渡せる文字列**であり、key や entry_file を組み立て直してはならない。

```
Agent(subagent_type: "{agents[i].subagent_type}", run_in_background: true,
      prompt: "{agents[i].prompt}")
```

- 複数要素があれば**同一メッセージ内で並列起動する**（1 要素 = 1 Agent）
- claim は script が済ませているため、起動前に何もしない
- `warnings` が空でなければユーザーに提示する。**初回の応答にしか出ない warning がある**（差分検出は初回しか走らないため。越境 symlink を索引したこと・reject された path 等）。ここで提示しないと二度と現れない
- 起動後、完了通知を受けたら同じコマンドを再実行する。**進捗は簡潔に**（例: `completed 12/29, 5 in-flight`）

#### `action: wait`

未投入の対象は無く、走行中の Agent のみが残っている。完了通知を待って同じコマンドを再実行する。

> **待機ループの終了条件 [MANDATORY]**: 完了通知は起動した Agent の数だけ届く。**通知を待たずに再実行を繰り返してはならない**（同じ `wait` が返るだけで進まない）。何らかの理由で通知が届かない場合、claim のリースが TTL（既定 900 秒）を超えると script が当該 entry を `dispatch` へ戻すため、再実行すれば回復する。それでも `wait` が続く場合は異常であり、ユーザーへ報告して判断を仰ぐ。

#### `action: confirm` / `reason: external_symlink`（`--all` のときだけ起きる）

`--all` の走査が **project root の外を指す symlink** を見つけた。誰も索引対象として渡していないため、project root の外へ勝手に広げずユーザーに確認する（NFR-N06）。書き込みは行われていない。

> **渡された対象は確認しない [MANDATORY]**: `--all` 以外のすべての対象指定（`--dirs` / `--dirs-json` / `--paths` / `--paths-json` / `--paths-file`）は、越境 symlink であっても**そのまま索引する**。それが symlink であることは渡す側が知っており、doc-advisor が別の理由で塞ぐと、上位層は自分の指定が通らない理由を知り得ない。注意喚起は `warnings` で行う。**この経路で `confirm` は返らない。**

`external_pending` の各エントリについて、**解決先の実体パス（`resolved`）と件数（`affected_count`）を提示**し、`AskUserQuestion` で許可・不許可を確認する。承認した symlink を並べて再実行する。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/index_docs.py --all \
  --allow-external "{approved_symlink_1}" "{approved_symlink_2}"
```

すべて拒否する場合は `--allow-external` を値なしで指定する（越境分は落とされ、残りで処理される）。`--allow-external` は**この確認の答えを戻すためだけの引数**であり、呼び出し元が自分から渡すものではない（Usage の引数表に無いのはそのため）。

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
- 越境 symlink を索引しなかったこと（`--all` でユーザーが承認しなかった分）
- 充填エラーを承知で統合したことによる脱落
- 転記フェーズを実行できなかったこと

### 書き戻しへの引き渡し（`ai_extracted_paths` が空でない場合のみ / DES-008 §8.2）

`action: done` で `ai_extracted_paths` が空でない場合のみ実行する。これらの文書は信頼できるフロントマターを持たなかったため AI 抽出で索引された。抽出結果を原本のフロントマターへ書き戻すと、以降その文書は転記だけで索引でき、結果は git を通じて全クローンへ伝播する（コーパスの自己修復）。

**書き戻しの内容は今生成した ToC そのものであり、AI が作り直すものではない [MANDATORY]**。`toc.yaml` のエントリはフロントマターと同じ 5 フィールドを持つため、`write-frontmatter` に `--from-toc {key}` を渡せば script が転記する。**候補文書を自分で `Read` してメタデータを起草してはならない。**

**ToC の生成完了「後」に行う [MANDATORY]**。索引という読み取り操作の副作用で原本に git diff が生じるのは驚きがあるためである（REQ-006 の制約）。ここまでの時点で原本は 1 バイトも変わっていない。

1. `ai_extracted_paths` の一覧（件数とパス）を提示し、書き戻しのため `write-frontmatter` へ引き渡すことを宣言する。**本スキルでは書き戻しの可否を `AskUserQuestion` で確認しない**。承認の要否は `write-frontmatter` が文書ごとに判定する（doc-advisor のフロントマターを既に持つ文書は承認不要で自動書き戻し、フロントマターが無い文書・他ツールのフロントマターしか持たない文書は承認必須。二重に確認しない）

2. `ai_extracted_paths` の全件を渡して `Skill` ツールで `doc-advisor:write-frontmatter` を起動する

   ```
   Skill(skill: doc-advisor:write-frontmatter,
         args: "--paths {path_1} {path_2} --from-toc {key}")
   ```

   - 引数は **`--paths` と `--from-toc` のみ**。`--from-toc` に渡すのは今回索引した key（単体モードでは `all`）であり、これにより `write-frontmatter` は ToC の値を転記する
   - 承認が必要な対象（フロントマターの新規追加）への `AskUserQuestion` は `write-frontmatter` 側で行われる
   - **ToC の JSON や `.toc_work/` の中身を渡してはならない**。渡すのは key と候補パスだけであり、ToC の読み取りは script が行う

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
