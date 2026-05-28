# forge-review v0.2 移行ノート

## 概要

forge-review v0.2 では `/forge:review` 周辺に **破壊的変更** が複数含まれます。本ドキュメントは CHANGELOG / リリースノート断片として参照される周知文であり、REQ-004 FNC-408 (デフォルト変更周知) を満たすための一次情報源です。

`/forge:review` を実行すると、初回のみ SKILL レベルで本ドキュメントへの誘導が表示されます (フラグファイル: `.claude/.temp/.forge_review_announce_shown`)。

- 起点 Issue: #68「AI reviewer がコトをどんどん複雑にする」
- 関連要件: `docs/specs/forge-review/requirements/REQ-004_review_policy.md`
- 関連設計: `docs/specs/forge-review/design/DES-028_review_policy_design.md`

---

## 破壊的変更

### 1. 固有 perspective の廃止 [REQ-004 FNC-402]

- **旧**: `/forge:review code --perspective logic` のように perspective 軸で reviewer を並列起動できた (logic / resilience / maintainability / alignment / architecture / completeness 等)
- **新**: 固有 perspective を **完全廃止**。種別ベースの `review_criteria_<種別>.md` のみで動作する。観点軸は P1 (ルール合致) / P2 (矛盾) / P3 (不要な複雑化) の **3 優先度に固定** され、reviewer 1 体の内部で順次評価される
- **影響**:
  - `--perspective <name>` フラグを CLI から受け付けなくなる (early validation で拒否)
  - 旧 `review_<perspective>.md` のファイル名が `review_<種別>.md` に変わる (項目 7 参照)
  - 既存 plan.yaml に旧 perspective 名 (`logic` / `resilience` 等) が残っている場合は、priority ラベル (P1/P2/P3) ベースに手動で読み替える

### 2. CLI 引数体系の統一 [REQ-004 FNC-410 / DES-028 §2.2]

新 CLI 構文:

```
/forge:review <種別> [--diff | --files a.md,b.md,...] [--interactive | --auto-critical | --auto] [--codex | --claude]
```

| 軸         | フラグ                                                          | 既定値          | 役割                                          |
| ---------- | --------------------------------------------------------------- | --------------- | --------------------------------------------- |
| 種別       | `code` / `design` / `requirement` / `plan` / `uxui` / `generic` | (必須)          | 位置引数。1 個のみ                            |
| 対象軸     | `--diff` / `--files`                                            | `--diff`        | 現ブランチ未 commit 差分 / 指定ファイル群全文 |
| 介入軸     | `--interactive` / `--auto-critical` / `--auto`                  | `--interactive` | 段階的提示 / 🔴 のみ自動修正 / 全件自動修正   |
| エンジン軸 | `--codex` / `--claude`                                          | `--codex`       | reviewer 実行エンジン                         |

#### 主な変更点

- **`--diff` の意味を確定** (TBD-401 解消): 「**現ブランチの未 commit 差分のみ**」(HEAD ステージ + working tree) を対象とする。base 指定オプション (`--base main` 等) は **提供しない**。ブランチ間レビューは `--files` で対象を明示する運用に統一
- **`--files` バイパス経路を新設**: カンマ区切りで指定ファイル群を全文レビュー (例: `--files a.md,b.md,c.md`)。`.doc_structure.yaml` 経路をバイパスする
- **`--section` フラグを完全撤廃 (DROP)**: 行番号や見出し構造の変動で意味が不安定になるため、ファイル全体または `--diff` のみに統一
- **`--scope` / `--depth` フラグを撤廃**: scope は `--diff` / `--files` の二択に置き換え、depth は P1〜P3 固定のため不要
- **`--auto N` (件数指定) を撤廃**: severity 順 × 件数の混合軸は AI 誤生成の温床になるため、介入は「対話 / 🔴 のみ / 全件」の 3 モードに限定
- **介入軸を明示**: `--interactive` (=デフォルト) / `--auto-critical` / `--auto` の 3 モードに限定。相互排他で early validation により二重指定を拒否
- **デフォルト挙動を明示形と等価に**: `/forge:review code` と `/forge:review code --diff --interactive --codex` は **完全に同一動作** (FNC-407)

#### 影響

- 旧 `--perspective` / `--section` / `--scope` / `--depth` / `--auto N` を使用している CI スクリプト・呼び出しはエラー終了する
- early validation でエラーメッセージに「DROP 済みフラグ」と明記される
- per-flow orchestrator (`/forge:start-design` 等) からの呼び出しは新 CLI 体系に置き換え済み

### 3. recommendation 値域に `create_issue` 追加 [REQ-004 FNC-406]

- **旧**: `recommendation` は `fix` / `skip` の 2 値
- **新**: `fix` / `skip` / `create_issue` の **3 値** に拡張。ルール抜け落ち発見時に Issue 化を推奨する経路を新設

#### `create_issue` の判定 3 条件 [MANDATORY]

evaluator は finding が以下 **3 条件をすべて満たす場合のみ** `recommendation: create_issue` を付与する:

1. **該当規定なし**: P1 で参照する SSOT (プロジェクト固有 rules / forge 内蔵 principles / format) のいずれにも該当規定が存在しない
2. **再発性または客観性**: 同種の指摘が今回・過去のレビューで複数箇所に観察される (再発性)、または客観的事実で説明可能 (AI 主観の単発判断ではない)
3. **明文化可能粒度**: ルールとして明文化可能な具体粒度を持ち、Issue として書き起こせる (「主観的にシンプルでない」等の評価語のみは不可)

#### 影響

- `present-findings` の AskUserQuestion で「Issue 化する」選択肢が追加される
- 既存 plan.yaml の `recommendation` カラムに `create_issue` 値が出現し得る
- `merge_evals.py` で `recommendation: create_issue` 行は `should_continue` 計算から除外される

### 4. severity の SoT 移管 [REQ-004 FNC-411]

- **旧**: criteria 側 (`review_criteria_*.md`) で重大度 (🔴 / 🟡 / 🟢) を割り振っていた
- **新**: severity は **委譲先 principles 側の重大度カタログから取得**。reviewer / criteria 自身は severity を判定しない
- 各 finding には新フィールド `severity_source: <principles ファイルパス>` が付与され、どの principles 文書から severity を取得したかを追跡可能にする

#### 拡充対象 principles (addendum merge 対象)

実装フェーズで以下 4 文書に重大度カタログが merge される (DES-028 §5.1):

- `plugins/forge/docs/spec_priorities_spec.md`
- `plugins/forge/docs/spec_design_boundary_spec.md`
- `plugins/forge/docs/design_principles_spec.md`
- `plugins/forge/docs/plan_principles_spec.md`

#### 影響

- criteria 側で severity を持っていた箇所は SoT 移管に伴い削除される
- `eval_<種別>.json` 等で severity を参照しているスクリプトは `severity_source` の追加に伴いスキーマ拡張が必要
- 既存 plan.yaml の severity 形式が変わる可能性 (priority ラベルとの併記)

### 5. 出力ファイル名規約の変更 [DES-028 §4.2]

- **旧**: `review_<perspective>.md` (例: `review_logic.md` / `review_resilience.md` / `review_alignment.md`)
- **新**: `review_<種別>.md` (例: `review_code.md` / `review_design.md` / `review_requirement.md` / `review_plan.md` / `review_uxui.md` / `review_generic.md`)

#### 影響

- 既存セッションの `review_*.md` ファイル名が変わる
- `write_interpretation.py` の CLI 引数 `--perspective` は `--kind` に改名 (値域: 6 種別)
- `write_refs.py` の refs.yaml スキーマで `output_path` は `review_<種別>.md` 形式チェックが行われる
- 旧 perspective 名のファイルが残っている場合は手動で改名するか、新規セッションで再生成する

### 6. reviewer の 1 起動原則 [REQ-004 FNC-412]

- 1 回の `/forge:review` 実行につき reviewer agent は **厳密に 1 体のみ** 起動する
- **観点軸 (P1/P2/P3) も対象ファイル軸も例外なく分割しない**
- target_files が実用上限 (3〜5) を超える場合は **起動分割せず**、AskUserQuestion で `--files` の絞り込みをユーザに促す

#### 禁止事項 (Issue #68 複雑性再発防止)

- 観点ごとに reviewer agent を分割起動すること
- SSOT 文書ごとに reviewer agent を分割起動すること
- 対象ファイルごとに reviewer agent を分割起動すること
- 1 回の `/forge:review` 実行で reviewer agent を 2 体以上起動すること (例外なし)

### 7. デフォルト挙動の変更 [REQ-004 FNC-407]

```
/forge:review <種別>
  ≡ /forge:review <種別> --diff --interactive
  ≡ 対象=現ブランチ未 commit 差分 (TBD-401 解消)
    × 介入=段階的提示 (present-findings)
    × 検出=優先度 1〜3 (P1/P2/P3)
```

省略形と明示形は **常に等価**。AI agent / 利用者が「省略時の挙動」を取り違えないよう、明示形 (`--diff --interactive`) も常にサポートする。

---

## 移行手順

### ユーザー側で必要な対応

1. **既存 plan.yaml の旧 perspective 名残記述の整理**
   - 旧 `perspective: logic` / `resilience` / `alignment` / `completeness` 等が残っていれば、`priority: P1` / `P2` / `P3` への読み替えを手動で行う
   - 新規セッションは自動的に新スキーマで生成される

2. **`/forge:review` 呼び出しの新 CLI 体系への置き換え**
   - `--perspective <name>` を削除 (種別だけを位置引数として渡す)
   - `--scope <value>` を `--diff` または `--files` に置き換え
   - `--depth <value>` を削除
   - `--section "<value>"` を削除 (ファイル全体または `--diff` で代替)
   - `--auto N` (件数指定) を `--auto-critical` (🔴 のみ) または `--auto` (全件) に置き換え

3. **CI / スクリプトの確認**
   - shell スクリプト / Makefile / GitHub Actions 等で旧フラグ (`--perspective` / `--scope` / `--depth` / `--section` / `--auto N`) を使っていないか grep で確認
   - 検出された場合は新 CLI 体系に置き換え、early validation エラーを未然に防ぐ

4. **session.yaml / refs.yaml のスキーマ整合確認**
   - 旧 `perspectives[]` 必須フィールドは撤廃され、`review_packet` (criteria_path + ssot_refs[] + check_order + severity_source + output_path) に置き換わった
   - 旧スキーマで保存されたセッションが残っている場合は破棄して新規作成を推奨

5. **案内表示の抑制を確認**
   - 初回案内は `.claude/.temp/.forge_review_announce_shown` フラグファイルで抑制される
   - 再表示したい場合はこのファイルを削除

### 自動化される対応 (ユーザー対応不要)

- criteria の 3 セクション固定構造 (SSOT参照 / チェック順 / 判定ルール) への全面置換は本 feature 実装で完了
- principles 4 文書への重大度カタログ merge は `docs/specs/forge-review/principles/*_addendum.md` から自動 merge される (DES-028 §5.1)
- per-flow orchestrator (`/forge:start-design` 等) からの呼び出しは本 feature 内で新 CLI に追従済み

---

## 参照

- REQ-004 §FNC-401 (レビュー観点の優先度体系)
- REQ-004 §FNC-402 (固有 perspective の廃止と criteria の判断除去)
- REQ-004 §FNC-403 (対象指定軸)
- REQ-004 §FNC-404 (介入軸)
- REQ-004 §FNC-406 (ルール抜け落ち Issue 化)
- REQ-004 §FNC-407 (デフォルト挙動の明示)
- REQ-004 §FNC-408 (デフォルト変更の周知) ← 本ドキュメントの根拠
- REQ-004 §FNC-410 (AI 誤判定しにくい CLI 構造)
- REQ-004 §FNC-411 (principles 拡充)
- REQ-004 §FNC-412 (reviewer 1 起動原則)
- DES-028 §2.2 (CLI 構造 To-Be)
- DES-028 §2.3 (reviewer 1 起動原則 / refs.yaml 新スキーマ契約)
- DES-028 §3.5 (principles 拡充計画)
- DES-028 §4.1 (`/forge:review` SKILL.md 差分)
- DES-028 §4.2 (`/forge:reviewer` SKILL.md 差分 / 出力ファイル名規約)
- DES-028 §5.1 (addendum merge タイミング)
- 起点 Issue: #68「AI reviwer がコトをどんどん複雑にする」

---

## 変更履歴

| 日付       | 変更者  | 内容                                                                                       |
| ---------- | ------- | ------------------------------------------------------------------------------------------ |
| 2026-05-21 | k2moons | 初版作成 (FNC-408 デフォルト変更周知 / TASK-037)。CHANGELOG / リリースノート断片として配置 |
