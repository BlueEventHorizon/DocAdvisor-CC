---
name: index-docs
description: |
  Generate or update a document ToC (Table of Contents) index from a key and a
  set of project-root-relative paths, using the desired-state pipeline
  prepare_toc → toc-updater (parallel metadata fill) → merge_toc.
  Use with --key <key> --paths-json '[...]' (driven by an upper layer such as
  forge), or with --all to index every Markdown file under the project root
  (single mode, reserved key "all").
  Trigger:
  - After an upper layer decides a key and its desired-state paths
  - "Index docs", "Rebuild the ToC for key X", "Index all Markdown"
allowed-tools: Bash, Read, Agent
user-invocable: true
argument-hint: "--key <key> --paths-json '[...]' | --key <key> --dirs-json '[...]' | --all | (no args = --all)"
---

# index-docs

key + project-root-relative paths から ToC（AI 検索用インデックス）を desired-state で生成・更新する生成系 SKILL。

> **このスキルの責務境界**: このスキルは「指定 key（または `--all` の予約 key `all`）の ToC を desired-state 同期する」ことのみを行う。親が依頼している他の作業を引き継いではならない。
>
> **起動経路**: このスキルは **継承型 SKILL**（`context: fork` を指定しない）。`prepare_toc.py`（差分検出）→ `doc-advisor:toc-updater` **カスタム Agent** を **Agent ツール**で並列起動（メタデータ充填）→ `merge_toc.py`（統合）の協調フローを駆動する。Agent ツールでカスタム Agent を並列起動するために fork しない（fork 型 SKILL は Agent を起動できないため）。起動経路の名称は `docs/rules/skill_launch_paths_definitions.md` の公式短縮名称に従う。

## Usage

```
/doc-advisor:index-docs --key <key> --paths-json '["docs/a.md", "docs/b.md"]'
/doc-advisor:index-docs --key <key> --dirs-json '["docs/rules/", "docs/specs/"]'
/doc-advisor:index-docs --key <key> --dirs-json '["docs/specs/**/design/"]'   # グロブ可
/doc-advisor:index-docs --key <key> --dirs-json '["docs/"]' --exclude-json '["docs/draft/"]'
/doc-advisor:index-docs --key <key> --paths-file paths.json
/doc-advisor:index-docs --all
```

| Argument                 | Description                                                                                                                                                                                                                                                                                                                                     |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--key <key>`            | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可（reject される）                                                                                                                                                                                                                                                       |
| `--paths-json '[...]'`   | 当該 key の **完全な desired state** となる project-root-relative path の JSON 配列                                                                                                                                                                                                                                                             |
| `--dirs-json '[...]'`    | 展開するディレクトリの JSON 配列（`--paths-json` と併用可）。SKILL が rglob で Markdown を収集する。エントリにグロブメタ文字（`*` `?` `[`）を含めるとパターン展開（例 `docs/specs/**/design/`）。マッチしたディレクトリは配下を rglob、Markdown ファイルは直接採用                                                                              |
| `--exclude-json '[...]'` | `--dirs-json` 展開時に除外するパス・ディレクトリの JSON 配列（システム固定除外は常時適用）。マッチ方式はシステム固定除外と同一: **裸名**（`/` なし、例 `plan`）は任意階層のディレクトリ名に完全一致、**`/` 含み**（例 `docs/drop.md`・`docs/draft`）は project root 起点（root-anchored）のセグメント境界マッチ＝パス完全一致／サブツリー前置き |
| `--paths-file <path>`    | paths 配列を含む JSON ファイル（`--paths-json` の代替）                                                                                                                                                                                                                                                                                         |
| `--all`                  | 単体モード。`--key` 省略と同義で予約 key `all` に解決し、project root 以下の全 Markdown を対象にする                                                                                                                                                                                                                                            |

> **desired-state の破壊性 [MANDATORY]**: `--paths-json` / `--paths-file` で渡す paths は当該 key の **完全な desired state** である。前回 ToC に存在し今回 paths に含まれない path は **削除** される（部分配列を渡すと残りが消える）。上位層の責務であり、不安な場合は先に `prepare_toc.py --dry-run` で削除予定を確認すること（後述）。

## Required Reference Documents [MANDATORY]

処理前に以下を読むこと:

- `${CLAUDE_PLUGIN_ROOT}/workflows/index_toc_orchestrator.md` — オーケストレーター手順（key 単位・並列・中断耐性・continuation）
- `${CLAUDE_PLUGIN_ROOT}/formats/toc_format.md` — ToC スキーマ定義（`doc_type` は除去済み。生成側も `doc_type` を抽出・出力しない）

## Execution Flow

`index_toc_orchestrator.md` のオーケストレーター手順に従って、以下の協調フローを駆動する。スクリプトパスはすべて `${CLAUDE_PLUGIN_ROOT}/scripts/` を使う。`$ARGUMENTS` から `--key` / `--paths-json` / `--dirs-json` / `--exclude-json` / `--paths-file` / `--all` を解釈する。引数が空（`$ARGUMENTS` なし）の場合は `--all` として扱う。

`--dirs-json` が指定されている場合は **Step 0 の前**に `expand_dirs.py` を呼んでディレクトリを展開し、結果を `--paths-json` に変換してから以降のフローへ渡す（Step 0.5 参照）。

### Step 0: 中断耐性・continuation の判定（key 単位 / §6.6）

各 key の `.toc_work/` は当該 key の `store_dir/.toc_work/` に分離される（key ごとに別ディレクトリのため、複数 key を扱っても競合しない）。**判定は手作業（`test -d` / YAML の手読み）で行わず、`toc_store.py --work-status` の出力に従う**（決定論処理は script に委ねる）:

```bash
# 再開判定では --lease-ttl 0 を付け、前回セッションの claim 残骸（in-flight）を stale 扱いで
# pending に戻す。新セッションでは前回の Agent は確実に終了しており二重投入の心配はない。
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --work-status --lease-ttl 0   # 単体モードは --all
```

stdout の JSON から `next_action` / `pending` / `completed` / `error_pending` / `has_work_dir` を読み、`next_action` に従う:

| `next_action` | 意味                                            | 動作                                                          |
| ------------- | ----------------------------------------------- | ------------------------------------------------------------- |
| `prepare`     | `.toc_work/` なし                               | 通常どおり Step 1（prepare）から開始する                      |
| `fill`        | 充填可能な pending あり                         | `prepare_toc.py` を **再実行せず** Step 2（充填）から再開する |
| `blocked`     | 充填可能 pending は無いが `error_pending` あり  | **silent merge 禁止。Step 2.5（エラー対応）** へ              |
| `merge`       | pending も error_pending も無い（全 completed） | Step 3（merge）へ直行する                                     |

> `store_dir` の特定や `.toc_work/` の有無・pending 列挙を AI が手で導出・走査しない。`--work-status` が `pending`（project-root 相対の entry_file 一覧）まで返すため、Step 2 はそのリストをそのまま使う。

### Step 0.5: ディレクトリ展開（`--dirs-json` 指定時のみ）

`--dirs-json` が指定されている場合のみ実行する。`expand_dirs.py` がディレクトリを rglob で展開し、`--paths-json` 形式に変換する。`--dirs-json` のエントリにグロブメタ文字（`*` `?` `[`）が含まれる場合はグロブパターンとして展開する（例 `docs/specs/**/design/` → 任意深さの `design/` をマッチ）。マッチしたディレクトリは配下を rglob、マッチした Markdown ファイルは直接採用する。`..`・絶対パスのグロブは `rejected_dirs` に列挙される。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/expand_dirs.py \
  --dirs-json '{dirs_json}' \
  [--exclude-json '{exclude_json}'] \
  [--paths-json '{paths_json}']   # --paths-json と併用している場合
```

stdout の単一 JSON から以下を読む:

- `paths` → 以降の `prepare_toc.py` に `--paths-json` として渡す
- `rejected_dirs` → 不在・非ディレクトリだった dirs、および不正なグロブ（`..`・絶対パス）を警告としてユーザーに表示する
- `warnings` → マッチしなかったグロブ等の注意喚起。ユーザーに表示する
- `status == error` → エラー内容を報告し AskUserQuestion でユーザーに確認する

`--paths-json` のみ指定（`--dirs-json` なし）の場合はこの Step をスキップし、既存の `--paths-json` をそのまま Step 1 へ渡す。

### Step 1: prepare（desired-state 差分検出 + pending 生成 / §6.1 / §6.2）

```bash
# key 指定（上位層駆動）
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths_json}'
# または paths-file
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-file "{paths_file}"
# 単体モード（予約 key all）
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --all
```

`prepare_toc.py` は paths 検証（traversal / 絶対パス / 不在 / 非 Markdown を reject。root 外を指す symlink は default-deny で確認待ちにする）と desired-state 差分検出を行い、added + updated 分の pending YAML を `store_dir/.toc_work/` に生成する。stdout の単一 JSON から以下を読む:

- `status`（`ok` / `partial` / `needs_confirmation` / `error`）/ `error_code`
- `toc_path`（生成された toc.yaml の project-relative パス。報告用。`.toc_work/` の所在・pending は AI が手で導出せず Step 2 で `--work-status` から取得する）
- `counts.added` / `counts.updated` / `counts.deleted` / `counts.unchanged`
- `rejected_paths`（reject された path と理由）/ `warnings`
- `external_pending`（`status == needs_confirmation` 時。root 外を指す未承認 symlink の `[{symlink, resolved, affected_count}]`）

判断:

- `status == error` → エラー内容を報告し、AskUserQuestion を使用してユーザーに対応を確認する
- `status == needs_confirmation` → **Step 1.5（越境 symlink の承認）** へ。書き込みは行われていない
- `counts.added == 0` かつ `counts.updated == 0` → 充填対象なし。`counts.deleted > 0` なら Step 3（merge）へ直行して削除を反映、両方 0 なら冪等成功（空 ToC を含む）として完了
- `counts.added > 0` または `counts.updated > 0` → Step 2 へ

> **事前確認（任意）**: 削除予定が不安な場合、`prepare_toc.py` に `--dry-run` を付けて実行すると、書き込みなしで `counts` と path 一覧のみ JSON 出力する。破壊的削除が想定外であれば、AskUserQuestion を使用して続行可否をユーザーに確認する。

### Step 1.5: 越境 symlink の承認（`status == needs_confirmation` 時のみ / NFR-N06）

明示 paths が **project root の外を指す symlink** を含む場合、不意のインデックス漏洩を防ぐため既定では索引しない（default-deny）。`external_pending` の各エントリ（越境している symlink ひとつに集約済み。配下に何ファイルあっても承認単位は symlink 1 個）について、**解決先の実体パス（`resolved`）と件数（`affected_count`）を提示**し、AskUserQuestion でユーザーに許可・不許可を確認する。

承認が決まったら、**承認した symlink の `symlink` 値だけを並べて** `--allow-external-json` を付け、`prepare_toc.py` を **同じ引数で再実行**する:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_toc.py --key "{key}" --paths-json '{paths_json}' \
  --allow-external-json '["{approved_symlink_1}", "{approved_symlink_2}"]'
```

- すべて拒否する場合は `--allow-external-json '[]'`（越境分は drop され、残りで通常処理される）
- 再実行は decided モードになり、未承認の越境 path は drop（warning に列挙）されるため `needs_confirmation` でループしない
- 再実行の結果（`status == ok` / `partial` など）に応じて以降の Step（2 / 3）へ進む

### Step 2: toc-updater カスタム Agent による連続ディスパッチ充填

充填対象は **`toc_store.py --work-status` の `pending_groups`（同一ディレクトリ近傍で最大 k 件ずつにまとめた entry_file グループ列）**を使う。AI が `ls .toc_work/*.yaml` や YAML の `_meta.status` 手読みで列挙したり、近傍グルーピングを手作業で行ったりしない（決定論は script が担う / ADR-006 案 B）。各グループを 1 つの `doc-advisor:toc-updater` カスタム Agent で充填する。

充填は **連続ディスパッチ（sliding-window）** で行う（ADR-006 / Issue #29）。並列ウィンドウを保ちつつ、完了が出るたびに空きスロットを埋め直すことで、バッチ（wave）バリアの中間テール待ちを除去する。二重投入は **claim/lease（script 側）** が防ぐ。

- **並列ウィンドウ**: 最大 10（`index_toc_orchestrator.md` の既定。実証済み安全圏 / ADR-006 案 A）。低 tier で 429 が出る場合は 5 → 3 へ下げる。10 超は未検証のため上げない。
- **投入直前に claim**: 投入するグループの entry_files を `toc_store.py --claim <entry...>` で claim（`claimed_at` をスタンプ）してから Agent を起動する。これにより次の `--work-status` がそのグループを **in-flight** として `pending` から除外し、連続投入中の二重起動を防ぐ。claim せずに起動してはならない。`--claim` は `claimed` / `rejected` を返す — **`claimed` のみを entry_files として渡し、`rejected`（`completed` / `already_claimed` / `error_pending` / `outside_work_dir` 等）は渡さない**。`claimed` が空ならそのグループは起動しない。
- 各カスタム Agent は **`run_in_background: true`** で起動し、完了通知（task-notification）を契機に補充する。`subagent_type` は `doc-advisor:toc-updater`。key とグループの entry_files（1〜k 件）を渡す。1 グループは同一ディレクトリ内に閉じ、Agent は各文書を独立に抽出する（context rot 回避）。

手順（補充は「空きスロット分まとめて」。1 完了 = 1 投入に固定しない）:

```
1. `--work-status` で `pending_groups`（未投入グループ）と `in_flight_groups`（投入済み・走行中の
   Agent 単位グループ）を取得。
    ↓
2. 空きスロット available = ウィンドウ上限 − len(in_flight_groups) を計算し、`pending_groups`
   先頭から min(available, グループ数) 個を、各グループごとに「claim → 起動」する:
     - `--claim` の返す `claimed` のみを entry_files として渡す（`rejected` は除外）。
     - `claimed` が空のグループは起動しない（次の `--work-status` が状態を正す）。
     - 起動は run_in_background。
    ↓
3. いずれかの Agent の完了通知を受けたら 1 に戻る（`--work-status` 再取得 → available 再計算 →
   空きスロット分まとめて補充）。`next_action` が:
     wait   → 未投入なし・in-flight のみ。残りの完了通知を待つ
     merge  → Step 3 へ
     blocked → Step 2.5 へ
    ↓
4. 全グループ completed（`next_action: merge`）になったら Step 3。
```

> **空きスロットは Agent 数で数える [IMPORTANT]**: ウィンドウは「並列 Agent 数」であり、1 Agent は
> 最大 k 件のグループを処理する。`in_flight`（entry のフラットリスト）の件数ではなく
> **`len(in_flight_groups)`（= 走行中 Agent 数）**で available を計算する（entry 数で引くと
> 過大に減算され負になり、補充されず wave に逆戻りする）。
>
> 複数の完了通知が会話再開前にまとまることがある（compaction・通知遅延）。1 完了 = 1 投入だと
> ウィンドウを埋め直せず並列度が落ちるため、毎回 available を再計算してまとめて補充する。

```bash
# 投入直前に claim（1 グループ分の entry_files。単体モードは --all）
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --claim <entry1> <entry2>
```

```
# claim 成功したグループを run_in_background で起動（1 グループ = 1〜k 件の近傍 entry_files）
Agent(subagent_type: doc-advisor:toc-updater, run_in_background: true,
      prompt: "key: {key}, entry_files: .claude/.doc-advisor/toc/<slug>/.toc_work/<sha256>.yaml, <同一ディレクトリの別 entry>")

# 単体モード（予約 key all）: key の代わりに all を渡す
Agent(subagent_type: doc-advisor:toc-updater, run_in_background: true,
      prompt: "all (single mode), entry_files: .claude/.doc-advisor/toc/all-<hash>/.toc_work/<sha256>.yaml")
```

> 単体モードでは toc-updater 側が `write_pending.py --all` を使う（`--key all` はユーザー任意指定として reject されるため）。`entry_files` は project-root-relative で渡す。
>
> バッチサイズは `--work-status --max-batch N`（既定 3）で調整。`--max-batch 1` で 1 ファイル 1 Agent（抽出品質の切り分け時に有用）。

状態（completed / in-flight / 未投入）は会話履歴でなく **`--work-status`（script）が単一の真実**。手で追跡せず、補充判断は毎回 `--work-status` の `next_action` に従う。compaction で履歴を失っても `--work-status` を引き直せば復元でき、claim 済み（in-flight）は再投入されない（停止した Agent の stale lease は TTL 超過で `pending` に戻り再投入対象になる）。各完了後は簡潔な進捗（例: "completed 12/29, 5 in-flight"）のみ出力する。

### Step 2.5: 充填エラーの対応（`next_action: blocked` 時のみ）

`pending` は空だが `error_pending`（充填に失敗した entry）が残る状態。**そのまま merge してはならない。** merge は completed のみ採用し成功時に `.toc_work/` を削除するため:

- errored doc は **今回の ToC から脱落**する。
- とくに **updated（既存文書の改訂）が errored の場合**、merge が現内容の checksum を書くため、**次回 prepare で「変更なし」と誤判定され、改訂が二度と索引されない（stale 固定）**。

したがって `error_pending` を握りつぶさず、`error_pending` の各 `entry_file` と `error_message` を提示し、AskUserQuestion で対応を確認する:

| 選択             | 動作                                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------------ |
| **再試行**       | `error_pending` の `entry_file` に対し toc-updater を再起動（transient 失敗の救済）→ Step 2 へ戻る     |
| **承知で merge** | 失敗分の脱落（および updated の stale 化）を承知のうえ Step 3（merge）。完了レポートで脱落 path を明示 |
| **中止**         | merge せず終了。元文書を修正して再実行を促す                                                           |

> 失敗が恒常的（元文書の問題）なら「再試行」は無限に成功しない。その場合は元文書を直してから再実行するか、「承知で merge」を選ぶ。

### Step 3: merge（統合 + 削除反映 / §6.5）

```bash
# key 指定
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --key "{key}"
# 単体モード（予約 key all）
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --all
# 削除のみ（added/updated が 0 で deleted のみの場合）
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/merge_toc.py --key "{key}" --delete-only
```

`merge_toc.py` は backup → 原子的書き込み（`os.replace`）→ validate → **OK で checksums 更新 + `.toc_work/` 削除 / NG で backup から復元・checksums 据え置き・`.toc_work/` 保持** までを **内部で完結**する。SKILL 側で追加の checksums promote / work dir 削除コマンドを呼ぶ必要はない。stdout JSON から `status` / `counts` / `deleted_paths` / `warnings` を読む。

- `status == ok` → 完了レポート（Step 4）
- `status == error` → 検証失敗時は toc.yaml が復元され `.toc_work/` が保持されている。エラー内容を報告し、AskUserQuestion を使用してユーザーに対応（元文書修正後の再実行など）を確認する

### Step 4: 完了レポート

```
✅ index-docs complete (key: {key})

[Summary]
- Mode: {key | all} / {full prepare | continuation}
- added / updated / deleted / unchanged: {counts}
- toc_path: {toc_path}
- Errors: {E} (if any)
```

エラー pending（`_meta.error_message` あり）が残る場合は一覧し、「次回再実行で再試行される。恒常的失敗は元文書を確認」とユーザーに伝える。

## Continuation の手動クリーンアップ（異常時のみ）

通常フローでは `merge_toc.py` が成功時に `.toc_work/` を削除するため、手動クリーンアップは不要。ただし以下の異常系では明示クリーンアップを使う:

- **`.toc_work/` を破棄してゼロから再 prepare したい**（壊れた pending の一掃 / full 相当の再生成）:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --clean-work-dir   # 単体モードは --all
  ```

- **pending チェックサムを active へ昇格させたい**（merge を経ない明示 promote が必要な保守作業）:

  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/toc_store.py --key "{key}" --promote-pending   # 単体モードは --all
  ```

これらは保守・異常時の手段であり、通常の生成パイプライン（Step 1〜3）では呼ばない。実行前に AskUserQuestion を使用してユーザーに確認すること（`--clean-work-dir` は充填済み作業を破棄しうるため）。

## Error Handling

- スクリプトが `status: error` の JSON を出力した場合: `error_code` と `message` を明示して報告し、AskUserQuestion を使用してユーザーに対応を確認する
- `--key all` を指定された場合（`error_code: KEY_RESERVED`）: 予約語衝突である旨を報告し、AskUserQuestion を使用して「`--all`（単体モード）に切り替えるか、別 key を指定するか」を確認する
- 空 key（`error_code: KEY_EMPTY`）: key を確認するよう報告する
- その他の予期しないエラー: 自動回復・回避を試みず、エラー詳細を明確に報告し、AskUserQuestion を使用してユーザーに対応を確認する
