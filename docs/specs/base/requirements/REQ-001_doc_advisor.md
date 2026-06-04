# REQ-001: doc-advisor 要件定義書

## 概要

doc-advisor は、プロジェクトのドキュメント（ルール・仕様文書等）を ToC（Table of Contents = キーワード／メタデータの検索インデックス）として索引化し、AI エージェントがタスクに関連する文書を素早く特定できるようにする Claude Code プラグインである。

doc-advisor は、**上位層が決定した `key + project-root-relative paths` を入力として ToC を生成・更新・検索・削除する汎用 ToC Provider** である。文書集合の決定責務（どのファイルが索引対象か、Feature 構造とは何か）は持たず、与えられた `key` と `paths` に対して決定的に動作する。文書集合の決定は forge などの上位層、または `--all`（予約 key `all`）の単体モードが担う。

検索方式は **ToC 検索のみ**。Embedding（セマンティック）検索は doc-advisor の責務外であり、query-docs プラグイン側で扱う（`BlueEventHorizon/bw-cc-plugins#77`）。

> **適用範囲の境界**: doc-advisor は `.doc_structure.yaml` / category / `doc_type` を通常経路では使用しない。文書集合の分類・決定は上位層（forge 等）の責務であり、doc-advisor は `key + project-root-relative paths` のみで決定的に動作する（§6.2）。

## 背景とスコープ

| 項目       | 内容                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------- |
| 出典       | GitHub Issue #15「doc-advisor を key + path 配列 I/F に移行し doc_structure 依存を廃止する」      |
| 関連 Issue | bw-cc-plugins#77（embedding は query-docs 側へ分離。本書では前提として扱い、対象外）              |
| 適用ルール | docs/rules/implementation_guidelines.md（設計書同一 PR 更新 / 不使用コード削除 / 標準ライブラリ） |

## 前提条件

| ID      | 要件                                                                                                        |
| ------- | ----------------------------------------------------------------------------------------------------------- |
| PRE-N01 | 上位層（forge 等）が、当該 key の **完全な desired state** としての paths 配列を決定して doc-advisor へ渡す |
| PRE-N02 | doc-advisor 単体利用時は `--all`（予約 key `all`）で実行プロジェクト root 以下の Markdown を対象にできる    |
| PRE-N03 | embedding 検索は doc-advisor の責務外（query-docs 側）。本書の検索は ToC 検索のみを指す                     |

## 機能要件

### FR-N01: key 単位 ToC 管理

| ID       | 要件                                                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-N01-1 | doc-advisor は ToC を opaque な `key` 単位で管理する                                                                                                          |
| FR-N01-2 | doc-advisor は `key` の意味（rules / specs 等の分類意味）を解釈しない。ただし予約 key `all` のみ単体モード用に特別扱いする                                    |
| FR-N01-3 | `key` から保存パスへの変換は決定的変換とする（safe slug。詳細は DES-005）                                                                                     |
| FR-N01-4 | original key は ToC の metadata に保持し、復元・照合可能とする                                                                                                |
| FR-N01-5 | 空 key は reject する。長すぎる key は slug 切り詰めで吸収する。Unicode key は NFC 正規化後に slug 化する。予約語 `all` はユーザー任意 key として使用できない |

### FR-N02: desired-state sync（ToC 生成・更新）

| ID       | 要件                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------ |
| FR-N02-1 | sync は渡された paths を当該 key の **完全な desired state** として扱う                          |
| FR-N02-2 | 前回 ToC に存在し今回 paths に含まれない path は **削除**する                                    |
| FR-N02-3 | paths に含まれる新規ファイルは追加、変更ファイルは更新、無変更は冪等に成功する                   |
| FR-N02-4 | `added` / `updated` / `deleted` / `unchanged` の件数と、`deleted` の path 一覧を JSON で出力する |
| FR-N02-5 | `prepare_toc.py --dry-run` で実際の書き込みをせず、追加・更新・削除の予定を JSON で提示できる    |
| FR-N02-6 | sync は SHA-256 ハッシュによる変更検出を踏襲する                                                 |

### FR-N03: paths 入力

| ID       | 要件                                                                               |
| -------- | ---------------------------------------------------------------------------------- |
| FR-N03-1 | `--paths-json '["docs/a.md", ...]'` で paths を直接指定できる                      |
| FR-N03-2 | `--paths-file <path>` で JSON ファイルから paths を読み込める                      |
| FR-N03-3 | paths は project-root-relative として解決される（検証規則は §6.1 path policy）     |
| FR-N03-4 | 不正 path（絶対パス・traversal・root 外・非 Markdown・不在）は §6.1 に従い処理する |

### FR-N04: 単体モード（予約 key `all`）

| ID       | 要件                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------- |
| FR-N04-1 | `--all`（または `--key` 省略）で、実行プロジェクト root 以下の Markdown を対象に ToC 化できる     |
| FR-N04-2 | key 省略時は予約 default key `all` に解決し、検索・削除時も同じ key を使う                        |
| FR-N04-3 | 固定除外を適用する（§6.4）。`all` は予約語とし、ユーザー任意 key としては使用できない（FR-N01-5） |
| FR-N04-4 | `--all` / `--key all` の解決規則は本要件で一元定義する（各 script はこれを参照する）              |

> **`--all` / `--key all` 解決規則【一元定義】**（各 script 表はこの規則を参照する）:
>
> | 入力        | 扱い                                                                                                                     |
> | ----------- | ------------------------------------------------------------------------------------------------------------------------ |
> | `--all`     | **許可**。単体モードを起動し、対象を予約 key `all` の ToC に解決する（`--key` 省略も同義）                               |
> | `--key all` | **reject**。`all` は予約語のためユーザー任意 key 指定としては予約語衝突として扱う（FR-N01-5 / 受け入れ基準）             |
> | 指す対象    | `--all`（許可）と予約語 `all`（任意指定 reject）は**同一の ToC（予約 key `all`）**を指す。差は「どの入口から到達するか」 |
>
> 削除入口も同規則に従う。`remove_toc.py` で予約 key `all` の ToC を削除する場合、`--all` 相当の指定（= 予約 key `all` を対象にする入口）で行い、`--key all`（ユーザー任意指定）は reject する。

### FR-N05: ToC 取得・検索

| ID       | 要件                                                                                                                                                                       |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-N05-1 | `get_toc` は対象 key の ToC を取得する（全体取得、または `--paths` 指定で縮小抽出）                                                                                        |
| FR-N05-2 | script は **lexical ranking / score 付けを行わない**（ToC 抽出のみ）。出力は ToC の定義順を保持し、score / rank フィールドを持たない。最終的な関連判断は SKILL / AI が担う |
| FR-N05-3 | 検索の見落としゼロ方針（false negative 最小化）を踏襲する（FNC-002 を継続）                                                                                                |
| FR-N05-4 | ドキュメント検索 SKILL `query-docs` は `context: fork` の read-only 隔離実行を踏襲する（ADR-002 を継続）                                                                   |

### FR-N06: 削除

| ID       | 要件                                                                         |
| -------- | ---------------------------------------------------------------------------- |
| FR-N06-1 | `remove --key <key>` で当該 key の ToC 全体（ディレクトリ）を削除する        |
| FR-N06-2 | `remove --key <key> --paths-json [...]` で指定 path のエントリを個別削除する |

### FR-N09: ディレクトリ入力（SKILL 層展開）

| ID       | 要件                                                                                                                                        |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-N09-1 | `index-docs` SKILL は `--dirs-json '["docs/rules/", ...]'` でディレクトリ配列を受け取れる                                                   |
| FR-N09-2 | `--exclude-json '["docs/rules/draft/", "docs/rules/wip.md"]'` でディレクトリ・ファイルの除外を指定できる                                    |
| FR-N09-3 | ディレクトリ展開・除外フィルタは **SKILL 層で完結**する。script 層（`prepare_toc.py` 等）のインターフェースは変更しない                     |
| FR-N09-4 | 展開結果（ファイルパス配列）は既存の `--paths-json` として `prepare_toc.py` へ渡す。desired-state の完全性責務は呼び出し側が担う（PRE-N01） |
| FR-N09-5 | 展開には Python ヘルパー（`rglob_follow_symlinks` / `should_exclude` 再利用）を使ってよい                                                   |
| FR-N09-6 | システム固定除外（`SYSTEM_EXCLUDE_PATTERNS`）は `--exclude-json` の指定有無にかかわらず常時適用する                                         |
| FR-N09-7 | `--dirs-json` と `--paths-json` は併用できる。展開後のファイルリストをマージして重複を除去してから `prepare_toc.py` へ渡す                  |

### FR-N07: レイヤ責務境界（deterministic / AI）

| ID       | 要件                                                                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| FR-N07-1 | **script 層（決定的）**: path 検証・desired-state 差分検出・pending 生成・merge・JSON 出力。メタデータ抽出はしない                         |
| FR-N07-2 | **AI 層（SKILL / agent）**: ToC エントリの title / purpose / content_details / keywords 抽出、検索時の関連判断                             |
| FR-N07-3 | sync は **単一コマンドで完結しない**。実体は `prepare_toc.py（script）→ メタデータ充填（agent 並列）→ merge_toc.py（script）` の協調である |

### FR-N08: JSON 出力契約

| ID       | 要件                                                                                                                                                         |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| FR-N08-1 | 全 script は stdout に **単一 JSON** を出力する。ログ・進捗は stderr に出力する                                                                              |
| FR-N08-2 | `status` と `error_code` は enum とし、テストで固定する                                                                                                      |
| FR-N08-3 | JSON は `status` / `error_code` / `message` / `key` / `toc_path` / `normalized_paths` / `rejected_paths` / `counts` / `warnings` を含む（schema は DES-005） |

## 確定方針

以下の方針を確定する。技術的詳細（アルゴリズム・schema・CLI オプション・内部構成）は DES-005 に委ねる。

### 6.1 path validation policy【確定】

| 規則        | 確定内容                                                                                                                                                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 入力形式    | project-root-relative のみ受理。絶対パスは reject                                                                                                                                                                                          |
| traversal   | `..` による root 外参照は reject（論理パス検証。既存 `validate_path_within_base()` を流用、CWE-22）                                                                                                                                        |
| **symlink** | **default-deny + 明示承認。** 実体を解決し、解決後パスが project root 配下なら受理。root 外を指す symlink は既定では索引せず、上位層の明示承認（`--allow-external-json`）があった prefix のみ受理する（実体解決・承認の実装は DES-005 §5） |
| 正規化      | NFC 正規化（既存 `normalize_path()`）。`./a.md` と `a.md` を同一視。重複は除去                                                                                                                                                             |
| 大小衝突    | case-insensitive 衝突を検出し warning として JSON に含める                                                                                                                                                                                 |
| 不正対象    | 不在ファイル / ディレクトリ / 非 Markdown は `rejected_paths` に理由付きで列挙する                                                                                                                                                         |

> **symlink を default-deny + 明示承認にする根拠**: root 外ファイルの不意なインデックス化（漏洩）を防ぐことが第一目的。一方で「project root の外に実体を置き symlink で取り込む」運用（例: 別リポジトリの共有 doc セット、テスト用 doc セット）は正当に存在し、その実体が root 外にある以上 symlink 以外に索引する経路がない（絶対パスは ABSOLUTE_PATH、root 外への相対は PATH_TRAVERSAL で reject されるため）。したがって **一律 reject ではなく、越境を検出したら上位層に提示して許可・不許可を確認し、承認された symlink のみ受理する**。承認の単位は「root 境界を越える symlink の prefix」ひとつであり、その配下のファイル数に依存しない（500 ファイルでも承認は symlink 1 個）。サポート下限を Python 3.9 に確定する（`Path.is_relative_to`、README に明記）。実体解決・確認フロー（discovery / decided）の実装詳細は DES-005 §5 に委ねる。

### 6.2 SKILL 構成【確定】

doc-advisor は category 固有の SKILL を持たず、汎用 SKILL 2 種へ一本化する。`key` の分類的意味（rules / specs 等）は解釈せず、与えられた `key` と `paths` に対して決定的に動作する。`implementation_guidelines.md`「使わないコードは削除 [MANDATORY]」に従い、category 依存ロジックは残さない。

| SKILL / 機能          | 確定方針                                                                                                                                            |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 汎用検索 `query-docs` | `get_toc` を呼び、`--key` 省略時は予約 key `all` を検索する。`context: fork` / read-only（ADR-002）。FR-N05（タスク関連パスリストの返却）契約を担う |
| 汎用生成 `index-docs` | agent 並列起動のため fork しない。`prepare_toc` → agent 充填 → `merge_toc` を駆動する                                                               |
| category 内部ロジック | 持たない。`load_config()` の category 分岐、`_get_default_config()` の rules/specs 固定キー、`extract_id_from_filename()` 等は存在しない            |

> **category 非対応の含意**: category の意味づけは doc-advisor の責務外であり、`rules` / `specs` を分けて検索する体験は提供しない。これを必要とする利用者は、上位層（forge）が任意の key で生成・検索を駆動するか、`query-docs`（key 省略 = `all`）で project 全体を横断検索する。検索 SKILL 名 `query-docs` は別プラグイン `query-docs`（bw-cc-plugins#77）と語が重複するが、plugin namespace（`doc-advisor:query-docs`）で区別する。

### 6.3 script 協調の方針【確定】

sync は **prepare（決定的・差分検出）と merge（決定的・統合）の間に agent のメタデータ充填が挟まる**ため、その境界を CLI 表層に明示する（FR-N07-3）。単一 `sync_toc.py` は「単体で完結する」と誤読させるため採用しない。doc-advisor が提供する主要 script は以下:

| script           | 責務                                                                                                       |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| `prepare_toc.py` | desired-state 差分検出 + pending YAML 生成（追加・変更対象の抽出、削除予定の算出）。メタデータ抽出はしない |
| `merge_toc.py`   | agent 充填済み pending を統合し、削除を反映して ToC を書き出す                                             |
| `get_toc.py`     | ToC 取得・抽出（全体取得 or `--paths` 縮小抽出）。lexical ranking はしない                                 |
| `remove_toc.py`  | key 全体削除 / 指定 path の個別削除                                                                        |

> 共通基盤として `toc_store.py` / `toc_utils.py` / `write_pending.py` / `validate_toc.py` を用いる。**各 script の CLI オプションと内部構成は DES-005 §4 が定義する**。

### 6.4 単体モード（`all`）固定除外【確定】

単体モード（`--all`）では固定除外を適用する（FR-N04-3）。除外リストの定義（SoT）は DES-005 §9.1 を参照する。

### 6.5 SKILL 層ディレクトリ展開方針【確定】

`--dirs-json` によるディレクトリ入力は **`index-docs` SKILL 層で完結**する。script 層のインターフェースは変更しない（FR-N09-3）。

| 項目                | 方針                                                                                                                         |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 展開責務            | SKILL が `rglob` でディレクトリ内の `**/*.md` を収集し、`--paths-json` に変換して `prepare_toc.py` へ渡す                    |
| 除外順序            | ① システム固定除外（`SYSTEM_EXCLUDE_PATTERNS`）→ ② `--exclude-json` 指定の除外（常にこの順で適用）                           |
| `--paths-json` 併用 | `--dirs-json` 展開結果と `--paths-json` 指定ファイルをマージし、重複除去してから渡す（FR-N09-7）                             |
| Python ヘルパー     | 展開・除外に `rglob_follow_symlinks` / `should_exclude` を再利用するヘルパー script を追加してよい（FR-N09-5、テスト必須）   |
| desired-state 責務  | ディレクトリ展開後のファイルリストが当該 key の desired state となる。上位層（forge 等）はディレクトリ集合が完全かを管理する |

## 非機能要件

| ID      | 要件                                                                                                                                                                                                                                                            |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-N01 | Python は標準ライブラリのみ使用（NFR-003 を継続）。サポート下限は Python 3.9（`Path.is_relative_to` 使用のため）                                                                                                                                                |
| NFR-N02 | 既存資産（`validate_path_within_base` / `normalize_path` / `calculate_file_hash` / `rglob_follow_symlinks` / `should_exclude` / `load_existing_toc` / `write_yaml_output` / `yaml_escape`）を可能な限り再利用する                                               |
| NFR-N03 | `scripts/` 配下 Python はテスト必須（implementation_guidelines）。追加・改修コードは同一 PR でテストを伴う                                                                                                                                                      |
| NFR-N04 | 仕様文書（要件・設計）の更新はコードと同一 PR で行う（implementation_guidelines）                                                                                                                                                                               |
| NFR-N05 | （性能）最大ファイル数超過時は warning を JSON に含めるが処理は継続する。超過判定の閾値（最大ファイル数）は 100 件とする（2026-05-30 当事者確定）。空 repo / 対象 0 件時は error ではなく空 ToC を冪等出力する                                                  |
| NFR-N06 | （セキュリティ）path traversal / root 外 symlink によるインデックス漏洩を防止する。検証方針は §6.1 path validation policy に従う（traversal は論理パス検証で reject、root 外 symlink は default-deny で確認待ちにし、上位層が明示承認した prefix のみ受理する） |
| NFR-N07 | （運用性）ToC 書き出し時のバックアップ・復元フローは key 単位で行う（DES-005 §6.5）                                                                                                                                                                             |

## 非目的 / スコープ外

- embedding（セマンティック）検索の維持・改善（query-docs 側 / Issue #13・#77）
- BM25 / hybrid / rerank の実装
- lexical 検索 script（ranking / score）の新規実装
- `.doc_structure.yaml` の新仕様化（廃止対象であり再定義しない）
- forge 側の文書探索ロジックの実装
- 既存 `.claude/doc-advisor/toc/{rules,specs}/` から新パス配下への自動 migration（§6.2 clean break により持たない）
- doc_type 自動分類の維持（category 廃止に伴い doc-advisor の責務外。ToC スキーマからも除去）
- category 別検索体験（rules / specs を分けた検索）の維持

## 受け入れ基準

### doc_structure 廃止

- [ ] 通常実行経路で `.doc_structure.yaml` を読まない
- [ ] `toc_utils.py` から doc_structure 前提の探索・分類ロジックを削除する（非推奨残存させない）
- [ ] README / SKILL / workflow から doc_structure 前提のセットアップ案内を削除する
- [ ] ToC スキーマから `doc_type` フィールドを除去し、`formats/toc_format.md` を改訂する

### 汎用 key + paths I/F

- [ ] `prepare_toc.py --key <key> --paths-json` / `--paths-file` + `merge_toc.py` で ToC を desired-state 更新できる
- [ ] paths は project-root-relative として解決される
- [ ] 絶対パス・traversal・不在・非 Markdown は §6.1 に従い JSON で reject / 列挙される
- [ ] root 外を指す symlink は default-deny で `needs_confirmation`（`external_pending` に越境 symlink を集約）として提示され、`--allow-external-json` で承認された prefix のみ受理される（NFR-N06）
- [ ] key は opaque に扱われ、original key が metadata に保持される
- [ ] 空 key / 過長 key / Unicode key / 予約語 `all` が §FR-N01-5 に従い処理される

### desired-state sync

- [ ] 前回 ToC にあり今回 paths にない path が削除される
- [ ] 新規追加・変更更新・無変更冪等が成立する
- [ ] **部分配列を渡すと前回 ToC の残りが削除される**ことを回帰テストで固定する
- [ ] `added` / `updated` / `deleted` / `unchanged` 件数と deleted paths が JSON 出力される
- [ ] `prepare_toc.py --dry-run` が書き込みなしで予定を提示する

### 単体モード（`all`）

- [ ] `--all` / `--key` 省略で project root 以下 Markdown を予約 key `all` に ToC 化する
- [ ] §6.4 固定除外が適用される
- [ ] 空 repo で空 ToC を冪等出力する（error にしない）
- [ ] ユーザーが `--key all` を任意指定した場合に予約語衝突として扱う

### ディレクトリ入力（SKILL 層展開）

- [ ] `index-docs` SKILL が `--dirs-json` を受け取り、ディレクトリ内の Markdown を展開して `prepare_toc.py --paths-json` へ渡す
- [ ] `--exclude-json` で指定したディレクトリ・ファイルが展開結果から除外される
- [ ] システム固定除外（`SYSTEM_EXCLUDE_PATTERNS`）が `--exclude-json` の有無にかかわらず適用される
- [ ] `--dirs-json` と `--paths-json` の併用で重複除去されたファイルリストが渡される
- [ ] `prepare_toc.py` のインターフェースが変更されない（SKILL 層で閉じている）

### 取得・検索 / JSON 契約 / レイヤ責務

- [ ] `get_toc.py --key <key>` で全体取得、`--paths` で縮小抽出ができ、score / rank フィールドを含まない
- [ ] `query-docs` SKILL が `get_toc` を呼び、`--key` 省略時に予約 key `all` を検索する
- [ ] 全 script が stdout 単一 JSON / stderr ログを守り、`status` / `error_code` enum がテストで固定される
- [ ] script 単体がメタデータ抽出をしない（metadata 充填は agent 経路のみ）

## 確定事項

| ID      | 内容                                                                                                                                    | 状態     |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| TBD-001 | 単体モード（`--all`）の最大ファイル数の警告閾値（NFR-N05）。**100 件で確定**（2026-05-30 当事者確定）                                   | 確定済み |
| TBD-002 | 段階分割か単一 PR か（① 設計 → ② script 層 → ③ SKILL 一本化 → ④ doc_structure 削除）。**段階分割で確定**（フェーズ ②③④ として実装済み） | 確定済み |

## 用語定義

| 用語           | 定義                                                                                           |
| -------------- | ---------------------------------------------------------------------------------------------- |
| key            | ToC の管理単位を表す opaque な文字列。doc-advisor は意味を解釈しない。上位層が決定する         |
| desired state  | 当該 key が保持すべき paths の完全集合。sync は前回状態との差分で追加・更新・削除を反映する    |
| ToC Provider   | 文書集合の決定責務を持たず、与えられた key + paths に対し ToC を生成・検索・削除する役割       |
| 予約 key `all` | `--key` 省略 / `--all` 指定時に解決される単体モード用の予約 key。ユーザー任意 key には使えない |
| 上位層         | doc-advisor を呼び出し paths を決定する側（forge 等）                                          |
| ToC            | Table of Contents — ドキュメントのメタデータ検索インデックスファイル（YAML）                   |
| `query-docs`   | 汎用検索 SKILL（`doc-advisor:query-docs`、fork / read-only）                                   |
| `index-docs`   | 汎用生成 SKILL（`doc-advisor:index-docs`、prepare→agent→merge を駆動。fork しない）            |

## 関連文書

- ADR-002: query-docs の fork 型 SKILL 隔離と read-only 制約
- FNC-002: 見落としゼロの検索精度
- DES-003: 文書識別子の設計（key + path 二層識別）
- DES-004: ドキュメントモデル設計書（スキャン対象・除外ルール）
- DES-005: key + path ToC Provider 設計書（key→保存パス変換 / JSON schema / script 内部構成 / prepare・merge 2 フェーズ / key 単位 checksums）
