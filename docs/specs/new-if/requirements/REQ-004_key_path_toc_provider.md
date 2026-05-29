---
type: temporary-feature-requirement
notes:
  - この文書が正。旧仕様（ソースコード・設計書・計画書）と矛盾する場合はこの文書を優先して判断・実装すること。
  - 旧仕様ファイルは本 feature 実装完了まで書き換えない。新規ファイル / 新規ディレクトリとして切り出すこと。
  - 本 feature 実装完了後、この文書は旧仕様書（base/）へ merge され削除される予定。
---

# REQ-004: key + path 汎用 ToC Provider 要件定義書

## 概要

doc-advisor を、`.doc_structure.yaml` と `rule` / `spec` カテゴリに依存した文書探索器から、**上位層が決定した `key + project-root-relative paths` を入力として ToC を生成・更新・検索・削除する汎用 ToC Provider** へ移行する。

doc-advisor は文書集合の決定責務（どのファイルが rules か、Feature 構造とは何か）を持たず、与えられた `key` と `paths` に対して決定的に動作する。文書集合の決定は forge などの上位層、または `--all`（予約 key `all`）の単体モードが担う。

> **位置づけ**: 本要件は `docs/specs/base/`（現行 doc-advisor 基盤仕様）に対する **Feature 差分**である。base の確定要件を一部 supersede する（§9 参照）。出典は GitHub Issue #15 およびそのレビュー契約。本書は Issue 本文を正規化し、**symlink policy / 旧 SKILL migration policy / script 名を確定**した上で、本質的にプロダクト方針判断を要する事項のみを未決事項として残す。

## 背景とスコープ

| 項目         | 内容                                                                                                                 |
| ------------ | -------------------------------------------------------------------------------------------------------------------- |
| 出典         | GitHub Issue #15「doc-advisor を key + path 配列 I/F に移行し doc_structure 依存を廃止する」                         |
| 関連 Issue   | bw-cc-plugins#77（embedding は query-docs 側へ分離。本書では前提として扱い、対象外）                                 |
| supersede 元 | base/REQ-001（PRE-01〜03, FR-01-1, FR-01-7, FR-06, NFR-02-4/5）, base/DES-004（文書モデル）, base/DES-005（Phase 0） |
| 適用ルール   | docs/rules/implementation_guidelines.md（設計書同一 PR 更新 / 不使用コード削除 / 標準ライブラリ）                    |

## 前提条件

| ID      | 要件                                                                                                        |
| ------- | ----------------------------------------------------------------------------------------------------------- |
| PRE-N01 | 上位層（forge 等）が、当該 key の **完全な desired state** としての paths 配列を決定して doc-advisor へ渡す |
| PRE-N02 | doc-advisor 単体利用時は `--all`（予約 key `all`）で実行プロジェクト root 以下の Markdown を対象にできる    |
| PRE-N03 | embedding 検索は doc-advisor の責務外（query-docs 側）。本書の検索は ToC 検索のみを指す                     |

> base/REQ-001 PRE-01〜03（`.doc_structure.yaml` 必須・setup-doc-structure 前提）は本書により **無効化**される（§9）。

## 確定機能要件

### FR-N01: key 単位 ToC 管理

| ID       | 要件                                                                                                                                                                         |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-N01-1 | doc-advisor は ToC を opaque な `key` 単位で管理する                                                                                                                         |
| FR-N01-2 | doc-advisor は `key` の意味（rules / specs 等の分類意味）を解釈しない。ただし予約 key `all` のみ単体モード用に特別扱いする                                                   |
| FR-N01-3 | `key` から保存パスへの変換は衝突しない決定的変換とする（safe slug + hash suffix。詳細は DES-006）                                                                            |
| FR-N01-4 | original key は ToC の metadata に保持し、復元・照合可能とする                                                                                                               |
| FR-N01-5 | 空 key は reject する。長すぎる key は slug 切り詰め + hash suffix で吸収する。Unicode key は NFC 正規化後に slug 化する。予約語 `all` はユーザー任意 key として使用できない |

### FR-N02: desired-state sync（ToC 生成・更新）

| ID       | 要件                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------ |
| FR-N02-1 | sync は渡された paths を当該 key の **完全な desired state** として扱う                          |
| FR-N02-2 | 前回 ToC に存在し今回 paths に含まれない path は **削除**する                                    |
| FR-N02-3 | paths に含まれる新規ファイルは追加、変更ファイルは更新、無変更は冪等に成功する                   |
| FR-N02-4 | `added` / `updated` / `deleted` / `unchanged` の件数と、`deleted` の path 一覧を JSON で出力する |
| FR-N02-5 | `prepare_toc.py --dry-run` で実際の書き込みをせず、追加・更新・削除の予定を JSON で提示できる    |
| FR-N02-6 | sync は SHA-256 ハッシュによる変更検出を踏襲する（base/REQ-001 FR-03 を key 単位で継続）         |

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
| FR-N05-3 | 検索の見落としゼロ方針（false negative 最小化）を踏襲する（base/FNC-002 を継続）                                                                                           |
| FR-N05-4 | ドキュメント検索 SKILL `query-docs` は `context: fork` の read-only 隔離実行を踏襲する（base/ADR-002 を継続）                                                              |

### FR-N06: 削除

| ID       | 要件                                                                         |
| -------- | ---------------------------------------------------------------------------- |
| FR-N06-1 | `remove --key <key>` で当該 key の ToC 全体（ディレクトリ）を削除する        |
| FR-N06-2 | `remove --key <key> --paths-json [...]` で指定 path のエントリを個別削除する |

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
| FR-N08-3 | JSON は `status` / `error_code` / `message` / `key` / `toc_path` / `normalized_paths` / `rejected_paths` / `counts` / `warnings` を含む（schema は DES-006） |

## 確定設計方針

ユーザー要請により、本 Feature の着手前提となる以下 3 点を確定する。技術的詳細（アルゴリズム・schema）は DES-006 に委ねるが、**方針はここで固定**する。

### 6.1 path validation policy【確定】

| 規則        | 確定内容                                                                                                                                                                                                                                                                               |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 入力形式    | project-root-relative のみ受理。絶対パスは reject                                                                                                                                                                                                                                      |
| traversal   | `..` による root 外参照は reject（論理パス検証。既存 `validate_path_within_base()` を流用、CWE-22）                                                                                                                                                                                    |
| **symlink** | **新 I/F では厳格化する。** `Path.resolve(strict=True)` + `Path.is_relative_to()` による実体解決を**新規実装**する（既存 `validate_path_within_base()` の論理パス検証とは別ロジック）。実体を解決し、解決後パスが project root 配下にある場合のみ受理。root 外を指す symlink は reject |
| 正規化      | NFC 正規化（既存 `normalize_path()`）。`./a.md` と `a.md` を同一視。重複は除去                                                                                                                                                                                                         |
| 大小衝突    | case-insensitive 衝突を検出し warning として JSON に含める                                                                                                                                                                                                                             |
| 不正対象    | 不在ファイル / ディレクトリ / 非 Markdown は `rejected_paths` に理由付きで列挙する                                                                                                                                                                                                     |

> **symlink を厳格化する根拠**: base の `validate_path_within_base()` は「project-configured symlink が base 外を指すのは_意図的に許可_」というポリシー（論理パスのみ検証し symlink 先は不問）だった。これは category スキャンにおいて root_dir 自体を外部共有ディレクトリへ symlink するユースケースを支えるものだった。新 I/F は上位層が**個別 path を明示的に渡す** desired-state モデルであり、symlink を経由せず実体パスを直接渡せるため、root 外 symlink を許可する技術的理由がない。漏洩防止（root 外ファイルの不意なインデックス化）を優先し、**base ポリシーから意図的に変更**する。
>
> **実装上の注記**: 既存 `validate_path_within_base()` は `os.path.normpath` による論理パス検証のみで symlink 先を辿らない設計のため、これを流用しても symlink 厳格化（root 外実体の reject）は実現しない。したがって symlink 検証は `validate_path_within_base()` とは**別の新規ロジック**として実装する（traversal の論理パス検証のみ `validate_path_within_base()` を流用）。`Path.resolve(strict=True)` は対象の実在を要求するため、不在 path の reject（§FR-N03-4）と検証を兼ねられる。root 配下判定には `Path.is_relative_to()` を用い、**サポート下限を Python 3.9 に確定**する（README に明記）。詳細実装は DES-006 に委ねる。
>
> **失われるユースケースと緩和**: モノレポで共有ドキュメントを symlink して取り込む運用は、上位層が symlink 先の実体パス（project root 内に解決されるパス）を渡すか、共有ドキュメントを project root 内に物理配置することで代替する。root 外の実体を指す symlink は本 I/F では非対応とする（後方互換の意図的破壊。受容前提・§6.1 確定）。

### 6.2 旧 SKILL migration policy【確定】

doc_structure 廃止に伴い、category 固有 SKILL を**全廃し、汎用 SKILL へ一本化する（clean break）**。`implementation_guidelines.md`「使わないコードは削除 [MANDATORY]」に従い、不使用ロジックは非推奨残存させず削除する。

| 旧 SKILL / 機能                         | 確定方針                                                                                                                                                                                     |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `setup-doc-structure`                   | **廃止**。`.doc_structure.yaml` 生成・config_required 案内導線を削除する                                                                                                                     |
| `create-rules-toc` / `create-specs-toc` | **廃止**。汎用生成 SKILL `index-docs` へ一本化する                                                                                                                                           |
| `query-rules` / `query-specs`           | **廃止**。汎用検索 SKILL `query-docs`（`doc-advisor:query-docs`）へ一本化する。category 別の検索体験は提供しない                                                                             |
| 汎用検索 SKILL（新設）                  | **`query-docs`**。`get_toc` を呼び、`--key` 省略時は予約 key `all` を検索する。`context: fork` / read-only（base/ADR-002 継続）                                                              |
| 汎用生成 SKILL（新設）                  | **`index-docs`**。agent 並列起動のため fork しない。`prepare_toc` → agent 充填 → `merge_toc` を駆動                                                                                          |
| 旧 category 内部ロジック                | **削除**。`load_config()` の category 分岐、`_get_default_config()` の rules/specs 固定キー、`init_common_config()` の root_dirs/doc_types_map 探索、`extract_id_from_filename()` を除去する |

> **確定の含意と影響**: category の意味づけは doc-advisor の責務外となり、`rules` / `specs` を分けて検索する体験は doc-advisor から消える。これを必要とする利用者は、上位層（forge）が任意の key で `prepare_toc` / `merge_toc` を駆動するか、`query-docs`（key 省略 = `all`）で project 全体を横断検索する運用へ移行する。後方互換の意図的破壊であり、受容を前提とする（§6.2 確定）。base/REQ-001 FR-05（タスク関連パスリストの返却）契約自体は `query-docs` が継承する。
>
> **命名に関する注記**: 検索 SKILL 名 `query-docs` は、embedding 検索を担う別プラグイン `query-docs`（bw-cc-plugins#77）と語が重複する。plugin namespace により `doc-advisor:query-docs` と `query-docs:*` は技術的に区別される。意味的な混同リスクは認識した上で、**`query-docs` のまま採用する（衝突許容）**。

### 6.3 script 名【確定】

Issue 提案の `update_toc.py` / `search_toc.py`、および単一 `sync_toc.py` は「単体で完結する」と誤読させ、FR-N07-3 の協調フローと矛盾するため採用しない。sync は **prepare（決定的・差分検出）と merge（決定的・統合）の間に agent のメタデータ充填が挟まる**ため、その境界を CLI 表層に明示する。

| script           | 責務                                                                                                           | 主なオプション                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `prepare_toc.py` | desired-state 差分検出 + pending YAML 生成（追加・変更対象の抽出、削除予定の算出）。**メタデータ抽出はしない** | `--key` / `--paths-json` / `--paths-file` / `--all` / `--dry-run`       |
| `merge_toc.py`   | agent 充填済み pending を統合し、削除を反映して ToC を書き出す                                                 | `--key` / `--delete-only`                                               |
| `get_toc.py`     | ToC 取得・抽出（全体取得 or `--paths` 縮小抽出）。lexical ranking はしない                                     | `--key` / `--all` / `--paths`（`--all` / `--key all` は FR-N04-4）      |
| `remove_toc.py`  | key 全体削除 / 指定 path の個別削除。予約 key `all` の削除は `--all` 入口で行う                                | `--key` / `--all` / `--paths-json`（`--all` / `--key all` は FR-N04-4） |

> sync は `prepare_toc.py`（script）→ メタデータ充填（agent 並列）→ `merge_toc.py`（script）の協調フローであり、単一コマンドではない（FR-N07-3）。`--dry-run` は `prepare_toc.py` が担い、削除・追加・更新予定を書き込みなしで JSON 出力する。既存 `filter_toc.py` の paths 抽出機能は `get_toc.py --paths` に統合する。`create_pending_yaml.py` → `prepare_toc.py` への改名・key 対応、`validate_toc.py` / `create_checksums.py` / `write_pending.py` の key 対応は DES-006 で設計する。

### 6.4 単体モード（`all`）固定除外【確定】

`.git/**` / `.claude/**` の runtime state / `.codex/**` / `node_modules/**` / `vendor/**` / `dist/**` / `build/**` / `__pycache__/**` / `.venv/**` / `target/**` / `coverage/**` / `.pytest_cache/**` / `.mypy_cache/**` / 生成済み ToC・work files。

## 非機能要件

| ID      | 要件                                                                                                                                                                                                              |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NFR-N01 | Python は標準ライブラリのみ使用（base/REQ-001 NFR-01 / NFR-003 を継続）。サポート下限は Python 3.9（`Path.is_relative_to` 使用のため）                                                                            |
| NFR-N02 | 既存資産（`validate_path_within_base` / `normalize_path` / `calculate_file_hash` / `rglob_follow_symlinks` / `should_exclude` / `load_existing_toc` / `write_yaml_output` / `yaml_escape`）を可能な限り再利用する |

| NFR-N03 | `scripts/` 配下 Python はテスト必須（implementation_guidelines）。本 Feature の追加・改修コードは同一 PR でテストを伴う |
| NFR-N04 | 仕様改訂（REQ-004 / DES-006 / base 仕様の supersede 記載）はコードと同一 PR で行う |
| NFR-N05 | （性能）最大ファイル数超過時は warning を JSON に含めるが処理は継続する。超過判定の閾値（最大ファイル数）は `TBD-001` とし当事者確定まで未定とする。空 repo / 対象 0 件時は error ではなく空 ToC を冪等出力する |
| NFR-N06 | （セキュリティ）path traversal / root 外 symlink によるインデックス漏洩を防止する。検証方針は §6.1 path validation policy に従う（traversal は論理パス検証、symlink は実体解決 reject） |
| NFR-N07 | （運用性）base/DES-005 のバックアップ・復元フローは key 単位で継続する（Phase 1〜4 の key 単位再編に伴い、ToC 書き出し時のバックアップ・復元も key 単位で行う） |

> **`rglob_follow_symlinks`（`os.walk` followlinks=True）の follow 列挙と §6.1 symlink 厳格化の適用範囲**: 単体モード（`--all`）の収集は `rglob_follow_symlinks` で symlink を follow して列挙するが、列挙後に §6.1 の実体解決（`Path.resolve(strict=True)` + `Path.is_relative_to()`）を適用し、root 外の実体を指すものは除外する。一方、上位層が明示的に渡す paths の検証は §6.1 の実体解決で root 外 symlink を直接 reject する。

## 非目的 / スコープ外

- embedding（セマンティック）検索の維持・改善（query-docs 側 / Issue #13・#77）
- BM25 / hybrid / rerank の実装
- lexical 検索 script（ranking / score）の新規実装
- `.doc_structure.yaml` の新仕様化（廃止対象であり再定義しない）
- forge 側の文書探索ロジックの実装
- 既存 `.claude/doc-advisor/toc/{rules,specs}/` から `keys/` 配下への自動 migration（§6.2 clean break 確定により持たない）
- doc_type 自動分類の維持（category 廃止に伴い doc-advisor の責務外。ToC スキーマからも除去）
- category 別検索体験（rules / specs を分けた検索）の維持

## 受け入れ基準

### doc_structure 廃止

- [ ] 通常実行経路で `.doc_structure.yaml` を読まない
- [ ] `toc_utils.py` から doc_structure 前提の探索・分類ロジックを削除する（非推奨残存させない）
- [ ] README / SKILL / workflow から `setup-doc-structure` 前提の案内を削除する
- [ ] ToC スキーマから `doc_type` フィールドを除去し、`formats/toc_format.md` を改訂する（検索は title/purpose/keywords 依存のため機能影響がないことを確認）

### 汎用 key + paths I/F

- [ ] `prepare_toc.py --key <key> --paths-json` / `--paths-file` + `merge_toc.py` で ToC を desired-state 更新できる
- [ ] paths は project-root-relative として解決される
- [ ] 絶対パス・traversal・root 外 symlink・不在・非 Markdown は §6.1 に従い JSON で reject / 列挙される
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

### 取得・検索

- [ ] `get_toc.py --key <key>` で全体取得、`--paths` で縮小抽出ができる
- [ ] `get_toc` の出力が ToC の定義順を保持し、score / rank フィールドを含まない（lexical ranking をしないことの観測可能基準）
- [ ] `query-docs` SKILL が `get_toc` を呼び、`--key` 省略時に予約 key `all` を検索する

### JSON 契約

- [ ] 全 script が stdout 単一 JSON / stderr ログを守る
- [ ] `status` / `error_code` enum がテストで固定される

### レイヤ責務

- [ ] script 単体がメタデータ抽出をしないこと（metadata 充填は agent 経路のみ）

### 仕様整合

- [ ] base/REQ-001・DES-004・DES-005 の supersede 箇所が §9 通り改訂される（同一 PR）

## 未確定事項

§6 で確定済みの方針（旧 UD-1〜UD-3 = symlink 厳格化の後方互換破壊受容 / category 検索体験喪失の受容 / clean break、および UD-6〜UD-8 = 生成 SKILL 名 `index-docs` / `query-docs` 命名衝突許容 / Python 下限 3.9）は §6.1・§6.2 本文および確定設計方針へ反映済みのため、本表からは除く。真に未確定なのは PR の分割方針のみ。

| ID      | 内容                                                                                                                                         | 期限           |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| TBD-001 | 単体モード（`--all`）の最大ファイル数の警告閾値（NFR-N05）。AI による数値捏造を避け、当事者が確定する                                        | 実装着手前     |
| TBD-002 | 段階分割か単一 PR か（① 設計 → ② script 層 → ③ SKILL 一本化 → ④ doc_structure 削除）。暫定は段階分割（規模・レビュー負荷・回帰リスクの観点） | DES-006 着手前 |

## 用語定義

| 用語           | 定義                                                                                           |
| -------------- | ---------------------------------------------------------------------------------------------- |
| key            | ToC の管理単位を表す opaque な文字列。doc-advisor は意味を解釈しない。上位層が決定する         |
| desired state  | 当該 key が保持すべき paths の完全集合。sync は前回状態との差分で追加・更新・削除を反映する    |
| ToC Provider   | 文書集合の決定責務を持たず、与えられた key + paths に対し ToC を生成・検索・削除する役割       |
| 予約 key `all` | `--key` 省略 / `--all` 指定時に解決される単体モード用の予約 key。ユーザー任意 key には使えない |
| 上位層         | doc-advisor を呼び出し paths を決定する側（forge 等）                                          |
| `query-docs`   | 新設の汎用検索 SKILL（`doc-advisor:query-docs`、fork / read-only）                             |
| `index-docs`   | 新設の汎用生成 SKILL（`doc-advisor:index-docs`、prepare→agent→merge を駆動。fork しない）      |

## 関連文書（base との差分マッピング）

| base 文書 | 本書による扱い                                                                                                                                                                                                                                               |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| REQ-001   | PRE-01〜03（doc_structure 前提）/ FR-01-1（2 カテゴリ）/ FR-01-7（doc_type 付与）/ FR-06（setup）/ NFR-02-4,5 を **supersede**。FR-03（変更検出）/ FR-05（検索）/ NFR-01（標準ライブラリ）は **継続**。旧 `query-rules`/`query-specs` は `query-docs` に統合 |
| DES-004   | 文書モデル全体（category / doc_types_map / doc_structure スキーマ / doc_type）を **supersede**。除外パターン判定ロジックは流用                                                                                                                               |
| DES-005   | Phase 0（config_required フロー）を **supersede**。Phase 1〜4（ハッシュ変更検出・並列・マージ・検証）は key 単位に再編して **継続**                                                                                                                          |
| DES-003   | ファイルパス = 識別子の原則を **継続・強化**（key + path の二層識別へ拡張）                                                                                                                                                                                  |
| FNC-002   | 見落としゼロ検索方針を **継続**                                                                                                                                                                                                                              |
| ADR-002   | query SKILL の fork / read-only 隔離を **継続**（`query-docs` が継承）                                                                                                                                                                                       |
| NFR-003   | 標準ライブラリ優先を **継続**                                                                                                                                                                                                                                |

| 新規予定 | 内容                                                                                                                                |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| DES-006  | key + path ToC Provider 設計書（key→保存パス変換 / JSON schema / script 内部構成 / prepare・merge 2 フェーズ / key 単位 checksums） |
