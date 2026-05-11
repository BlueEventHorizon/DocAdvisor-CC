---
type: temporary-feature-requirement
notes:
  - この文書が正。旧仕様（ソースコード・設計書・計画書）と矛盾する場合はこの文書を優先して判断・実装すること。
  - 旧仕様ファイルは本 feature 実装完了まで書き換えない。新規ファイル / 新規ディレクトリとして切り出すこと。
  - 本 feature 実装完了後、この文書は旧仕様書へ merge され削除される予定。
---

# REQ-004: setup.sh の forge プラグイン変更耐性強化 要件定義書

**作成日**: 2026-04-28
**作成者**: k_terada
**関連 plan**: `~/.claude/plans/enumerated-nibbling-balloon.md`

## 概要

`setup.sh` が `bw-cc-plugins/plugins/forge/` から取り込む資産（SKILL・script・docs）を、forge 側の変更に追従しやすい形で宣言・検証する仕組みを導入する。

直近、forge への新規 SKILL 追加（`doc-structure/`）や Python の親ディレクトリ参照パターン変更が DocAdvisor 側のコピー漏れ・sed 変換ずれを引き起こしてきた。本 feature は次の 3 点を達成する:

1. forge から取り込む資産の **可視化**（setup.sh を読むだけで一覧が分かる）
2. install 結果の **決定論的検証**（テストで毎回検知）
3. テストでは捕まらない **意味的妥当性の AI 検証**（SKILL で補完）

将来段階として、forge 側でのマニフェスト宣言と Python の env 変数化により、DocAdvisor 側の追従コストを更に下げる。

## 適用範囲

本要件は以下に適用する:

- DocAdvisor の `setup.sh`
- DocAdvisor の `tests/` 配下
- DocAdvisor リポジトリ直下の `.claude/skills/` 配下（DocAdvisor 開発者向け検証 SKILL）

将来段階で次の改修を要望するが、実装は別 PR で段階的に進める:

- `bw-cc-plugins/plugins/forge/` へのマニフェストファイル追加
- forge 側 Python script の env 変数化

**本 PR の完了条件**: 本要件における必須完了条件は FR-01〜FR-03 のみ。FR-04 / FR-05 は将来段階の別 PR を前提とし、本書ではその受け入れ要件のみを定義する。FR-04 / FR-05 が未完了の暫定運用期間は、setup.sh の親ディレクトリ参照経路の変換ロジック（`copy_and_substitute()` 内の置換ルール群）が残存し、forge 側 Python の親階層変更には引き続き当該ロジックの追従更新が必要となる既知制約を許容する。

### 対象外

- target project 側（`.claude/` 配下にインストールされる成果物の機能変更）
- bw-cc-plugins の他プラグイン（anvil / xcode / doc-advisor 本体）への影響
- ToC の生成内容そのものの品質検証（target project の責務）

## 前提条件

| ID     | 要件                                                                                                              |
| ------ | ----------------------------------------------------------------------------------------------------------------- |
| PRE-01 | `bw-cc-plugins` submodule が初期化済みであり、`bw-cc-plugins/plugins/forge/` および `bw-cc-plugins/plugins/doc-advisor/` のソースが利用可能であること |
| PRE-02 | `python3` 実行環境が利用可能であること（`rules/python_detection.md` の Python 検出規約に従う）                    |
| PRE-03 | target project の `.claude/` ディレクトリへ書き込み可能であること（install 先・検証実行先として）                  |
| PRE-04 | DocAdvisor リポジトリ直下で `setup.sh` が一度以上正常に動作した状態であること（検証 SKILL 利用時の初期条件）       |

## 用語定義

| 用語             | 定義                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| plugin imports   | setup.sh が forge / doc-advisor 双方の plugin から取り込む SKILL・agent・script・docs の総称                         |
| forge plugin imports | 上記のうち forge plugin に限定した文脈で用いる呼称                                                              |
| 決定論的検証     | ファイル存在・構文 parse・文字列一致など、判定が一意に定まる自動検証                                                |
| 意味的検証       | 設定整合性・規約適合・未知パターン検知など、AI による判断を要する補完検証                                           |
| 宣言リスト       | setup.sh トップレベルに置く、forge / doc-advisor から取り込む資産の一覧                                              |
| マニフェスト     | forge plugin 自身が保持する、DocAdvisor が取り込むべき資産の宣言ファイル（将来段階）                                 |
| DISABLED_SKILLS  | setup.sh 内で管理される、上流で実装中等の理由により install 対象から除外する SKILL 名の一覧（FR-02-5 参照）          |

### バージョン識別子の役割

DocAdvisor では複数のバージョン識別子が並存する。各識別子の役割と真とする値の出典を以下に整理する。

| 軸                              | 粒度             | 用途                       | 真とする値の出典                                                       |
| ------------------------------- | ---------------- | -------------------------- | ---------------------------------------------------------------------- |
| `doc-advisor-version-xK9XmQ`    | ファイル単位     | レガシー保護・上書き判定    | setup.sh の `DOC_ADVISOR_VERSION`                                       |
| `.source_version`               | ディレクトリ単位 | install ソース追跡          | `bw-cc-plugins/plugins/doc-advisor/.claude-plugin/plugin.json#version` および bw-cc-plugins HEAD commit hash |
| forge マニフェスト（将来段階）  | プラグイン単位   | 取り込み資産の宣言          | forge 側 manifest（FR-04、TBD-001 で確定）                              |

これらは互いに置換せず、共存する。FR-04 のマニフェスト導入後も `.source_version` および xK9XmQ 識別子は併用する。

## 機能要件

### FR-01: forge plugin imports の可視化

| ID      | 要件                                                                                                                          |
| ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| FR-01-1 | `setup.sh` トップレベルに「forge / doc-advisor から取り込む資産」の宣言リストを SKILL / agent / script / docs ごとに保持する。形式（bash array / heredoc / 別ファイル）は実装依存とし、FR-04 マニフェスト schema 確定時に整合形式へ移行することを想定する |
| FR-01-2 | コピー処理（Phase B 相当）は宣言リストを反復するのみで、資産名の個別ハードコード行を持たない                                  |
| FR-01-3 | 新規 SKILL / script / doc を取り込む場合、宣言リストへの追加だけで完結し、コピー処理ロジックの修正を要しない                  |
| FR-01-4 | 宣言リスト上の資産が forge / doc-advisor 側に存在しない場合、stdout に `Warning: Source directory not found: <path>` 形式の警告を出力してスキップし、install 全体は exit 0 で継続する |

### FR-02: install 後の決定論的検証

| ID      | 要件                                                                                                                                                                  |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-02-0 | 検証実行前に PRE-01〜PRE-03 を確認し、不足時は PASS / FAIL とは独立した「環境エラー（exit 2）」で終了する。submodule 未初期化・python3 不在・target project の `.claude/` 不可アクセスを検知対象とする |
| FR-02-1 | install 後、forge 由来の Python script が top-level で import 可能であることを検証する。検証対象モジュール一覧、cwd、判定コマンド・許容 exit code の確定は **TBD-004** に委ねる |
| FR-02-2 | install 後の検証は SKILL と agent で個別に行う。<br>**SKILL**: `skills/<name>/` ディレクトリの存在・`SKILL.md` の存在・frontmatter 構文・`name` フィールドがディレクトリ名と一致することを検証する。<br>**agent**: `agents/<name>.md` の存在・frontmatter 構文・`name` フィールドがファイル basename（拡張子除く）と一致することを検証する |
| FR-02-3 | install 後、以下の文字列が install 結果（`.claude/` 配下）に残存しないことを検証する。将来 sed / 変換ルールが追加された場合は本表へ追記する:<br>`${CLAUDE_PLUGIN_ROOT}/`<br>`/doc-advisor:`<br>`/forge:setup-doc-structure` |
| FR-02-4 | install 後、`.source_version` 内の `source_commit` が現在の bw-cc-plugins HEAD commit hash と一致することを検証する。setup.sh は `git -C bw-cc-plugins rev-parse HEAD` で取得した値を `source_commit` キーに記録する。dirty working tree の場合は `source_commit` 値の suffix として `-dirty` を付与し、検証は suffix を含めて等値比較する。`--source` で submodule 外のソースを指定した等の理由で commit hash が取得できない場合は `source_commit: unknown` を記録し、本検証は skip 扱いとして警告のみ出力する |
| FR-02-5 | install 後、停止中 SKILL（`DISABLED_SKILLS` に列挙された SKILL 名、現状: `create-code-index`, `query-code`）が install されていないことを検証する。`DISABLED_SKILLS` の正本は `setup.sh` 内変数とし、宣言リスト（FR-01）はその subset として保持する。停止中 SKILL のソースは `bw-cc-plugins/plugins/doc-advisor/skills/{create-code-index,query-code}/` であり、上流で実装中のため install 対象外として扱う。復活条件は別 PR の取り込み判断時に決定する |
| FR-02-6 | install 後、`.doc_structure.yaml`（ToC 設定ファイル）および ToC 生成 SKILL（`/create-rules-toc` / `/create-specs-toc`）が存在することを検証する（ToC 内容そのものの品質検証は対象外）。参照: REQ-001 PRE-01〜PRE-03 / FR-08。なお REQ-002 で残存する旧称 `/setup-config` は別 PR で順次 `/setup-doc-structure` に移行する前提とする |
| FR-02-7 | 検証結果は項目単位で PASS / FAIL を出力する。いずれかの FAIL があれば全体 FAIL と判定する |
| FR-02-8 | FAIL があっても後続項目の実行は中断せず、全項目を実行した上で集計結果を返す（既存 `tests/test_optional_plugins.sh` の継続実行方針を踏襲）。ただし最終集計の合否判定は FR-02-7 に従い、いずれかの FAIL があれば全体 FAIL とする。実行ログは `tests/.last_validation.log` に保存する。個別項目の単独再実行可否・引数仕様は **TBD-005** に委ねる |

### FR-03: 意味的妥当性の AI 検証

| ID      | 要件                                                                                                                                                                |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-03-1 | DocAdvisor 開発者は `/setup-validator <target-project-path>` で AI 補完検証を起動できる。引数省略時は既定値として `tests/test_project` を対象とする                  |
| FR-03-2 | 検証 SKILL は最初に決定論的検証 (FR-02) を実行し、FAIL がある場合は、AI 検証コストの抑制と原因切り分けを優先するため AI 検証をスキップしてテスト結果のみ報告して停止する。AI 検証が示し得た追加コンテキストの欠落は本要件で許容するトレードオフとする |
| FR-03-3 | 検証 SKILL は次の意味的整合を AI で検証する: frontmatter の意味的整合 / Python script の関数内 lazy 解決の整合 / sed ルールの論理整合 / forge 側の未捕捉ファイル検知 / `.source_version` と install 内容の対応。各項目の入力資料・期待出力・false positive 許容方針・代表ケース別の三値判定境界は **TBD-006** に委ねる |
| FR-03-4 | 決定論的検証 (FR-02) PASS 時に限り、検証 SKILL の出力は `OK` / `注意` / `要確認` の三値で diagnostic を返す。合否の最終判定は行わず、判断は人間に委ねる            |
| FR-03-5 | 検証 SKILL は DocAdvisor リポジトリ直下のみに配置する。target project への install 経路には載せない                                                                  |
| FR-03-6 | AI 検証が起動できない（SKILL が呼べない / API 不通等）場合は、決定論的検証結果のみ報告して exit 0 で終了する                                                          |

### FR-04: forge plugin マニフェスト連携（将来段階）

| ID      | 要件                                                                                                                                              |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-04-1 | `bw-cc-plugins/plugins/forge/` に DocAdvisor 取り込み資産を宣言するマニフェストファイル（命名・形式は **TBD-001** で確定）が存在する場合、setup.sh はそれを優先して読み取り、取り込む資産を決定する |
| FR-04-2 | マニフェストが存在しない場合、setup.sh は FR-01 の宣言リスト（フォールバック）を使用して動作を継続する                                            |
| FR-04-3 | マニフェスト不在時のフォールバック動作を必ず維持する。古い forge ブランチへ切り替えても setup が壊れない                                          |
| FR-04-4 | マニフェスト導入は forge 側の別 PR を前提とする。本要件はその受け入れ要件を定義する                                                                |

### FR-05: forge Python の env 変数化（将来段階）

| ID      | 要件                                                                                                                                                                            |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-05-1 | forge 側 Python script は `.claude/skills/` の位置を環境変数経由で解決できる仕組みを持つ                                                                                         |
| FR-05-2 | 環境変数が設定されていない場合は親ディレクトリ探索のフォールバックで解決し、forge native 実行環境でも DocAdvisor install 後環境でも同じコードで動作する                          |
| FR-05-3 | env 変数化完了後、DocAdvisor 側で行っていた親ディレクトリ参照経路の変換責務は forge 側に集約され、setup.sh から該当変換ロジックを除去できる。除去可能となる時点は forge プラグインの最低サポートバージョン（**TBD-007** で確定）に達した時とし、それまでは互換層として維持する。FR-04-3 の「古い forge ブランチへ切り替えても setup が壊れない」条件を優先する |
| FR-05-4 | env 変数化は forge 側の別 PR を前提とする。本要件はその受け入れ要件を定義する                                                                                                    |

## 非機能要件

| ID     | 要件                                                                                                                                                          |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-01 | `bw-cc-plugins` は読み取り専用扱いを維持する。本 feature の DocAdvisor 側変更は bw-cc-plugins を改変しない                                                    |
| NFR-02 | 既存の install 動作（target project への配置・変換）は本 feature 適用前後で互換性を保つ                                                                       |
| NFR-03 | 検証 SKILL は false positive / false negative を許容する診断者である。合否判定の最終責任は人間に残る                                                          |
| NFR-04 | 決定論的検証は forge への新規ファイル追加に対し、テスト対象リストの更新のみで追従できる構造とする                                                              |
| NFR-05 | 検証 SKILL の本文は Claude Code の最新仕様に従って記述する（仕様取得は `claude-code-guide` 経由で行う）                                                        |
| NFR-06 | `tests/test_setup_validation.sh`（決定論的検証）および `/setup-validator`（AI 補完検証含む）の実行時間目安・同一入力に対する出力再現性の数値目標は **TBD-008** で確定する |

## 既存テストとの関係

本要件で新設する `tests/test_setup_validation.sh` および `/setup-validator` は、REQ-002 既存テスト（T-001〜T-012）を**置換せず補完する**位置付けとする。

| 既存テスト                          | 関係                                                                                                                              |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_setup_upgrade.sh`       | REQ-002 のアップグレード経路の振る舞いを担保する。FR-02-3 / FR-02-5 と検証対象が一部重複するが、本要件はテスト失敗の検知契機が異なる（既存テストは upgrade 経路、本要件は forge 変更追従）ため併存させる |
| `tests/test_optional_plugins.sh`    | `.source_version` の生成・検証および sed 残骸検知の実装ひな型として利用する。FR-02-4 / FR-02-3 の `.source_version` / 残骸検知部分を `tests/test_setup_validation.sh` に移管・統合し、`test_optional_plugins.sh` は optional plugin 専用テストとして整理する |

REQ-002 の T-009〜T-012 は引き続き実行する。`test_setup_validation.sh` は同領域を構造的検証の観点で再カバーし、二重化による検知精度向上を狙う。

## 受け入れ基準

DocAdvisor 開発者は次の 2 つの検証をそれぞれ 1 コマンドで実施できる:

- **決定論的検証**: `bash tests/test_setup_validation.sh` を 1 コマンドで実行し、FR-02 の全項目について PASS / FAIL を得られる
- **AI 補完検証**: `/setup-validator <target-project-path>` を 1 コマンドで実行し、決定論的検証 + AI 補完検証の結果を得られる

両者は独立した 1 コマンドであり、決定論的検証のみ実行する場合に AI 検証起動は不要とする。

次のシナリオで本 feature が機能する:

| シナリオ                                                                       | 期待結果                                                  |
| ------------------------------------------------------------------------------ | --------------------------------------------------------- |
| forge に新規 SKILL を追加し setup.sh 宣言リストに反映                          | install で取り込まれ、決定論的検証が PASS                  |
| forge に新規 SKILL を追加するが宣言リストに未反映                              | `/setup-validator` の AI 検証が `要確認` を出す            |
| sed ルール不足で install 後ファイルに `${CLAUDE_PLUGIN_ROOT}` が残存            | 決定論的検証が FAIL                                        |
| forge の Python parent カウントが変わり import が壊れる                         | 決定論的検証 (FR-02-1) が FAIL                             |
| `bw-cc-plugins` の HEAD commit hash と `.source_version` の `source_commit` が不一致 | 決定論的検証 (FR-02-4) が FAIL                       |
| 停止中 SKILL（`DISABLED_SKILLS`）が install されてしまう                        | 決定論的検証 (FR-02-5) が FAIL                             |
| `bw-cc-plugins` submodule が未初期化の状態で検証を実行                          | FR-02-0 が環境エラー（exit 2）で終了                       |
| `python3` が利用不可の環境で検証を実行                                          | FR-02-0 が環境エラー（exit 2）で終了                       |

## 未確定事項

| ID      | 内容                                                                                                                                | 期限                |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| TBD-001 | forge マニフェスト（FR-04）のスキーマ詳細・配置パス・読み込み形式は forge 側 PR で確定する                                          | FR-04 着手前        |
| TBD-002 | forge Python env 変数（FR-05）の命名（`CLAUDE_PLUGIN_ROOT` / `CLAUDE_SKILLS_ROOT` 等）の正式仕様は Claude Code 公式仕様で確認する     | FR-05 着手前        |
| TBD-003 | 検証 SKILL の AI 検証で扱う forge 側コミット差分の解析範囲（直近 N commit / 任意期間）の確定                                         | FR-03 設計時        |
| TBD-004 | FR-02-1 の Python import 検証における対象モジュール一覧・cwd（target project root か `.claude/doc-advisor/scripts/` か）・判定コマンド（`python3 -c 'import …'` / `python3 -m py_compile` / `python3 script.py --help` の選択）・許容 exit code を確定する | FR-02 設計時        |
| TBD-005 | FR-02-8 の個別項目単独再実行の引数仕様（項目 ID 指定方式 / フィルタ式 等）を確定する                                                 | FR-02 設計時        |
| TBD-006 | FR-03-3 の 5 つの意味的検証項目それぞれについて、入力資料・期待出力・false positive 許容方針および `OK` / `注意` / `要確認` 三値の判定境界（代表ケース別）を確定する | FR-03 設計時        |
| TBD-007 | FR-05-3 で setup.sh の親ディレクトリ参照経路変換ロジックを除去可能とする forge プラグインの最低サポートバージョン境界を確定する     | FR-05 着手時        |
| TBD-008 | NFR-06 の運用 NFR 数値目標（`tests/test_setup_validation.sh` の実行時間上限・`/setup-validator` の AI 検証含む実行時間目安・同一入力に対する出力再現性の判定方法）を確定する | FR-02 / FR-03 検証実装後 |

## 変更履歴

| 日付       | 変更者   | 内容                                                                                                                                                |
| ---------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-28 | k_terada | 初版作成（plan: enumerated-nibbling-balloon.md より）                                                                                                |
| 2026-04-28 | k_terada | レビュー指摘に基づき修正: 前提条件章追加、FR-02-0/FR-02-8/FR-03-6 追加、FR-02-2/FR-02-3/FR-02-4/FR-02-5/FR-02-6 を具体化、FR-03-1 に対象指定追記、FR-03-2/FR-03-4 にスキップ条件・適用条件追記、FR-04-1 のマニフェストファイル名抽象化、FR-05-3 から sed 言及除去、用語「plugin imports」改名、バージョン識別子の役割表追加、既存テストとの関係節追加、受け入れ基準を 2 コマンドに分離、NFR-06 / TBD-004〜TBD-008 追加 |
