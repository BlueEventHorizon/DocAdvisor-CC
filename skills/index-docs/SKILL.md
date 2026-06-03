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
/doc-advisor:index-docs --key <key> --dirs-json '["docs/"]' --exclude-json '["docs/draft/"]'
/doc-advisor:index-docs --key <key> --paths-file paths.json
/doc-advisor:index-docs --all
```

| Argument                 | Description                                                                                          |
| ------------------------ | ---------------------------------------------------------------------------------------------------- |
| `--key <key>`            | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可（reject される）            |
| `--paths-json '[...]'`   | 当該 key の **完全な desired state** となる project-root-relative path の JSON 配列                  |
| `--dirs-json '[...]'`    | 展開するディレクトリの JSON 配列（`--paths-json` と併用可）。SKILL が rglob で Markdown を収集する   |
| `--exclude-json '[...]'` | `--dirs-json` 展開時に除外するパス・ディレクトリの JSON 配列（システム固定除外は常時適用）           |
| `--paths-file <path>`    | paths 配列を含む JSON ファイル（`--paths-json` の代替）                                              |
| `--all`                  | 単体モード。`--key` 省略と同義で予約 key `all` に解決し、project root 以下の全 Markdown を対象にする |

> **desired-state の破壊性 [MANDATORY]**: `--paths-json` / `--paths-file` で渡す paths は当該 key の **完全な desired state** である。前回 ToC に存在し今回 paths に含まれない path は **削除** される（部分配列を渡すと残りが消える）。上位層の責務であり、不安な場合は先に `prepare_toc.py --dry-run` で削除予定を確認すること（後述）。

## Required Reference Documents [MANDATORY]

処理前に以下を読むこと:

- `${CLAUDE_PLUGIN_ROOT}/workflows/toc_orchestrator.md` — オーケストレーター手順（key 単位・並列・中断耐性・continuation）
- `${CLAUDE_PLUGIN_ROOT}/workflows/toc_update_workflow.md` — 詳細ワークフロー（prepare → 充填 → merge、checksums/work dir 責務）
- `${CLAUDE_PLUGIN_ROOT}/formats/toc_format.md` — ToC スキーマ定義（`doc_type` は除去済み。生成側も `doc_type` を抽出・出力しない）

## Execution Flow

`toc_orchestrator.md` のオーケストレーター手順に従って、以下の協調フローを駆動する。スクリプトパスはすべて `${CLAUDE_PLUGIN_ROOT}/scripts/` を使う。`$ARGUMENTS` から `--key` / `--paths-json` / `--dirs-json` / `--exclude-json` / `--paths-file` / `--all` を解釈する。引数が空（`$ARGUMENTS` なし）の場合は `--all` として扱う。

`--dirs-json` が指定されている場合は **Step 0 の前**に `expand_dirs.py` を呼んでディレクトリを展開し、結果を `--paths-json` に変換してから以降のフローへ渡す（Step 0.5 参照）。

### Step 0: 中断耐性・continuation の判定（key 単位 / §6.6）

各 key の `.toc_work/` は当該 key の `store_dir/.toc_work/` に分離される（key ごとに別ディレクトリのため、複数 key を扱っても競合しない）。処理開始時に当該 key の `.toc_work/` 残存を判定する。

| 状況                                                             | 判定                                                                                   |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `store_dir/.toc_work/` が存在し pending（`status: pending`）あり | `prepare_toc.py` を **再実行せず**、残 pending の充填（Step 2）から再開し merge へ進む |
| `store_dir/.toc_work/` が存在し全 `completed`                    | 充填済み。merge（Step 3）へ直行する                                                    |
| `store_dir/.toc_work/` なし                                      | 通常どおり Step 1（prepare）から開始する                                               |

`store_dir` は `prepare_toc.py` / `merge_toc.py` の JSON 出力 `toc_path`（`.claude/doc-advisor/toc/<slug>/toc.yaml`）の親ディレクトリとして特定できる。`.toc_work/` の存在は Bash の `test -d` で確認する。

### Step 0.5: ディレクトリ展開（`--dirs-json` 指定時のみ）

`--dirs-json` が指定されている場合のみ実行する。`expand_dirs.py` がディレクトリを rglob で展開し、`--paths-json` 形式に変換する。

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/expand_dirs.py \
  --dirs-json '{dirs_json}' \
  [--exclude-json '{exclude_json}'] \
  [--paths-json '{paths_json}']   # --paths-json と併用している場合
```

stdout の単一 JSON から以下を読む:

- `paths` → 以降の `prepare_toc.py` に `--paths-json` として渡す
- `rejected_dirs` → 不在・非ディレクトリだった dirs を警告としてユーザーに表示する
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

`prepare_toc.py` は paths 検証（traversal / 絶対パス / root 外 symlink / 不在 / 非 Markdown を reject）と desired-state 差分検出を行い、added + updated 分の pending YAML を `store_dir/.toc_work/` に生成する。stdout の単一 JSON から以下を読む:

- `status`（`ok` / `partial` / `error`）/ `error_code`
- `toc_path`（→ `store_dir` と `.toc_work/` の特定に使う）
- `counts.added` / `counts.updated` / `counts.deleted` / `counts.unchanged`
- `rejected_paths`（reject された path と理由）/ `warnings`

判断:

- `status == error` → エラー内容を報告し、AskUserQuestion を使用してユーザーに対応を確認する
- `counts.added == 0` かつ `counts.updated == 0` → 充填対象なし。`counts.deleted > 0` なら Step 3（merge）へ直行して削除を反映、両方 0 なら冪等成功（空 ToC を含む）として完了
- `counts.added > 0` または `counts.updated > 0` → Step 2 へ

> **事前確認（任意）**: 削除予定が不安な場合、`prepare_toc.py` に `--dry-run` を付けて実行すると、書き込みなしで `counts` と path 一覧のみ JSON 出力する。破壊的削除が想定外であれば、AskUserQuestion を使用して続行可否をユーザーに確認する。

### Step 2: toc-updater カスタム Agent による並列充填

`store_dir/.toc_work/*.yaml`（隠しファイル `.` 始まりは除く）のうち `_meta.status: pending` のものを、`doc-advisor:toc-updater` カスタム Agent で **並列充填**する。

- **並列数**: 最大 5（`toc_orchestrator.md` の既定）。CRITICAL: 1 つの assistant メッセージ内で複数の Agent 呼び出しをまとめて発行する（1 件ずつ別メッセージにすると並列にならない）。
- **`run_in_background: true` は使わない**（Phase 2 ループが壊れる）。
- 各カスタム Agent には key と entry_file を渡す。`subagent_type` には `doc-advisor:toc-updater` を指定する。

```
# key 指定時（1 メッセージで最大 5 件並列）
Agent(subagent_type: doc-advisor:toc-updater, prompt: "key: {key}, entry_file: .claude/doc-advisor/toc/<slug>/.toc_work/<sha256>.yaml")
...（最大 5 件）

# 単体モード（予約 key all）: key の代わりに all を渡す
Agent(subagent_type: doc-advisor:toc-updater, prompt: "all (single mode), entry_file: .claude/doc-advisor/toc/all-<hash>/.toc_work/<sha256>.yaml")
```

> 単体モードでは toc-updater 側が `write_pending.py --all` を使う（`--key all` はユーザー任意指定として reject されるため）。`entry_file` は project-root-relative で渡す。

各バッチ完了後、簡潔な進捗（例: "Batch 2/4 complete, 10 remaining"）のみ出力し、pending が残る限り並列起動を繰り返す。すべて `completed`（またはエラー記録済み pending）になったら Step 3 へ。ファイル一覧に `xargs` を使わない（長い日本語ファイル名で失敗する）。`ls .toc_work/*.yaml` か `while read` ループを使う。

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
