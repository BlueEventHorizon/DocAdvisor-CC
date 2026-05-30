# new-if 実装戦略

> 本戦略は追加開発（additive development）の一時 feature **new-if** の **実装フェーズ**を対象とする。
> 設計フェーズ（① REQ-004 / DES-006）は完了済みであり、本書は計画しない。
> REQ-004 / DES-006 は `type: temporary-feature-*` の一時文書であり、`docs/specs/base/` の既存仕様（REQ-001 / DES-004 / DES-005 ほか）を supersede する正本である。実装完了後に base へ merge され削除される。
> 正本順位: 旧仕様（base/・既存ソース）と矛盾する場合は REQ-004 を最優先、次いで DES-006。

## アプローチ

**選択**: ボトムアップ（基盤層 → 上位層）+ リスク駆動の併用

**根拠**:

- **依存グラフがほぼ線形のレイヤード構造**である（DES-006 §2.2 依存方向規範: AI 層 → script 層 → 共通モジュール `toc_store.py` / `toc_utils.py` → ストアの単方向、循環なし）。下位が安定しないと上位が検証できないため、基盤層を先に積み上げるボトムアップが自然に適合する。
- **基盤は新設 `toc_store.py`**（key → store_dir 解決・meta.yaml I/O・JSON 出力ヘルパ・予約 key 判定・error_code 定数集約）であり、`prepare_toc.py` / `merge_toc.py` / `get_toc.py` / `remove_toc.py` の全 script がこれに依存する（DES-006 §4.1）。`toc_store.py` を最初に確定する必要がある。
- 同時に **path 検証の symlink 厳格化 `resolve_within_root()`（DES-006 §5.2）は新規ロジックで後方互換を意図的に破壊する**最も不確実性の高い要素であり、prepare / 単体モードの前提でもある。リスク駆動の観点から、基盤層の早期（フェーズ②前半）に潰す。
- AI 層（SKILL / agent）は script 層の JSON 契約（DES-006 §8）が固まってからでないと駆動経路を組めないため、後段に置く（スケルトン先行は不適: script 契約が未確定の段階で SKILL を組むと手戻りが大きい）。
- **`.doc_structure.yaml` 通常経路依存の最終除去を最後（フェーズ④）に置く**: 途中で削除すると `load_config()` の category 分岐に依存する既存テスト群が壊れ、フェーズ②③の検証が不安定になる。clean break だが「除去の順序」は段階分割の核（後述リスク）。
- フィーチャースライス / スケルトン先行を採らない理由: 本 feature は外部ユーザ向け新機能のデモではなく、既存パイプラインの I/F 移行であり、縦断的最小機能の早期デモより「各フェーズで build/test が緑」を維持する漸進移行の価値が高い。

> フェーズ番号は REQ-004 TBD-002 の暫定段階分割（① 設計 → ② script 層 → ③ SKILL 一本化 → ④ doc_structure 削除）に整合させ、実装対象である ②③④ を採番据え置きで用いる。①（設計）は完了済み。

## フェーズ

### フェーズ ②: script 層（deterministic 層の確立）

- **目標**: AI 層に依存せず、key + paths を入力に `prepare → merge` の協調フローで `toc.yaml` を desired-state 生成・更新でき、`get_toc` / `remove_toc` が動作する。全 script が stdout 単一 JSON 契約（status / error_code 必須）を満たす。`scripts/` 配下の全新設・改修 Python に単体テストが付随し、`python3 -m unittest discover -s tests -p 'test_*.py' -v` が緑。
- **スコープ**（DES-006 §3〜§9, §12, §13 / REQ-004 FR-N01〜N08）:
  - `toc_store.py`（新設, §4.1 / §3.1 / §3.2 / §8.2）: key → store_dir 変換（safe slug + sha256[:12]）、`meta.yaml` I/O（original_key 保持）、予約 key `all` 判定、`emit_json()`、error_code enum 定数の集約。`create_checksums.py` の `--promote-pending` / `--clean-work-dir` 機能を統合（key 単位化）。
  - `toc_utils.py`（改修, §4.2 / §5）: category 分岐削除（`load_config()` の rules/specs 分岐・`_get_default_config()` 固定キー・`init_common_config()` の root_dirs/doc_types_map 探索・`ConfigNotReadyError`・`find_config_file()`）。新規 `resolve_within_root()`（`Path.resolve(strict=True)` + `Path.is_relative_to()`、Python 3.9 下限）。流用関数（`normalize_path` / `calculate_file_hash` / `rglob_follow_symlinks` / `should_exclude` / `load_existing_toc` / `write_yaml_output` / `yaml_escape` / `validate_path_within_base` / checksums I/O）は維持。**`validate_path_within_base()` の docstring・論理パス検証ポリシーは変更しない**（traversal 専用として流用、symlink 厳格化は新関数が担う）。
  - `prepare_toc.py`（旧 `create_pending_yaml.py` 改名・転用, §5 / §6.2 / §9）: paths 検証（§5.1 フロー）→ desired-state 差分検出（added/updated/unchanged/deleted）→ pending YAML 生成、`--dry-run`、`--all` 単体モード（rglob + 固定除外 + root 外実体除外）、JSON 出力。`has_substantive_content()` を転用。
  - `merge_toc.py`（改修, §6.5 / §7.2）: 充填済み pending 統合 → `toc.yaml` 原子的書き込み（backup → validate → restore フローを key 単位で踏襲）、削除反映、`metadata.key` へ `meta.yaml` の original_key 転記、JSON 出力。
  - `get_toc.py`（旧 `filter_toc.py` 統合・新設, §11.2）: `toc.yaml` 全体取得 or `--paths` 縮小抽出、**ranking / score なし・定義順保持**、JSON or YAML 出力。
  - `remove_toc.py`（新設, FR-N06）: key 全体削除 / `--paths-json` 個別削除、予約 key `all` 削除は `--all` 入口、JSON 出力。
  - `write_pending.py`（改修, §7.1）: `--key` 対応、`--doc-type` 関連引数廃止。
  - `validate_toc.py`（改修, §7.1）: doc_type 必須撤廃（title/purpose + 3 配列のみ必須）、key ストアパス対応。
  - 単体テスト（DES-006 §13 / REQ-004 NFR-N03）: store_dir 解決（slug/hash/予約 key/空・過長・Unicode key）、path 検証 6 系統 + `./a.md`↔`a.md` 同一視 + 大小衝突 warning、desired-state diff（**部分配列 → 残り削除の固定**: 受け入れ基準）、JSON status/error_code enum 固定、単体モード（固定除外・空 repo 冪等空出力・root 外 symlink 除外）。
- **フェーズ内モジュール実装順序**（依存順）:
  1. `toc_store.py`（全 script の基盤）+ 単体テスト
  2. `toc_utils.py` 改修: `resolve_within_root()` 新規 + category 分岐削除（ただし旧 category 依存テストは削除せず後段で扱う。後述リスク）+ path 検証単体テスト
  3. `prepare_toc.py`（旧 create_pending_yaml 改名・転用）+ 差分検出・path 検証・単体モード単体テスト
  4. `merge_toc.py` 改修（prepare → merge は協調フロー FR-N07-3。backup/restore 含む）+ 単体テスト
  5. `get_toc.py`（旧 filter_toc 統合）+ 単体テスト
  6. `remove_toc.py` 新設 + 単体テスト
  7. `write_pending.py` / `validate_toc.py` 改修 + 単体テスト改修
  8. 統合テスト: `prepare → write_pending → merge` 協調フローで toc.yaml 生成 / `remove --key` でストア削除（DES-006 §13）
- **検証ポイント**:
  - `python3 -m unittest discover -s tests -p 'test_*.py' -v` が緑（NFR-N03）。
  - 全 script が stdout 単一 JSON / stderr ログを守る（FR-N08-1）。status / error_code enum がテストで固定（FR-N08-2）。
  - 部分配列 desired-state で残りが削除される回帰テストが緑（受け入れ基準）。
  - 外部依存ゼロ（標準ライブラリのみ）を維持（NFR-N01）。
  - `dprint check` が緑（変更 JSON/YAML/Markdown）。
  - 注意: このフェーズでは旧 SKILL（`create-*` / `query-*`）はまだ旧 script を参照したまま壊れている可能性がある。SKILL の整合はフェーズ③で取る。フェーズ②の build/test 健全性は「scripts/ 単体・統合テスト緑」を基準とし、SKILL 経由 E2E は対象外とする。

### フェーズ ③: SKILL / agent 一本化（AI 層の差し替え）

- **目標**: 旧 SKILL（`query-rules` / `query-specs` / `create-rules-toc` / `create-specs-toc` / `setup-doc-structure`）を全廃し、`index-docs`（fork なし）/ `query-docs`（fork / read-only）へ一本化。`toc-updater` agent がフェーズ②の新 script（`prepare_toc` / `merge_toc` / `write_pending --key`）を駆動して、key 指定・単体モード（`--all`）の生成 → 検索が SKILL 経由 E2E で動作する。
- **スコープ**（DES-006 §10 / §11 / REQ-004 §6.2 / FR-N05 / FR-N07）:
  - `index-docs` SKILL 新設（fork なし, §10）: `prepare_toc` → toc-updater 並列充填 → `merge_toc` を駆動。`--key` / `--all`。base/DES-005 orchestrator パターン（Phase 2 並列・中断耐性・continue モード）を key 単位で継承（`workflows/toc_orchestrator.md` 流用、§6.6）。
  - `query-docs` SKILL 新設（fork / read-only, §10 / base/ADR-002 継続）: `get_toc` を呼び AI が関連判断、`--key` 省略時は予約 key `all`。**自己再帰呼び出し禁止**（skill_authoring_notes）。
  - `toc-updater` agent 改修（§10 / §7.1）: pending 読み → 元文書メタデータ抽出 → `write_pending.py --key` で充填（doc_type 抽出を廃止）。
  - 旧 SKILL 5 件の削除（clean break、非推奨残存させない: implementation_guidelines「使わないコードは削除」）。
  - workflows 整合: `toc_orchestrator.md` を index-docs 駆動・key 単位へ、`toc_update_workflow.md` / `query_toc_workflow.md` を新 SKILL 名・新 script 名へ改訂（または統廃合）。
  - 起動経路の用語は `skill_launch_paths_definitions.md` の公式短縮名称で統一（継承型 SKILL / fork 型 SKILL / カスタム Agent 等）。fork 型 / 継承型の判別は人が個別判断（命名ベース禁止: skill_authoring_notes）。
  - SKILL 仕様は claude-code-guide agent で公式確認（MANDATORY: skill_authoring_notes）。スクリプトパス参照は `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_SKILL_DIR}`。
- **フェーズ内実装順序**:
  1. `toc-updater` agent 改修（index-docs が依存する充填経路を先に確定）
  2. `index-docs` SKILL 新設（生成パイプライン駆動）+ workflows（toc_orchestrator）整合
  3. `query-docs` SKILL 新設（検索パイプライン、fork / read-only）+ query workflow 整合
  4. 旧 SKILL 5 件の削除（新 SKILL 動作確認後）
- **検証ポイント**:
  - `index-docs --key K` / `index-docs --all` で toc.yaml が生成され、`query-docs --key K` / `query-docs`（省略 = all）で関連文書パスが返る（手動 E2E 確認: SKILL.md はテスト例外）。
  - 旧 SKILL ディレクトリ・参照が残存しない（grep 確認）。
  - scripts/ 単体・統合テストは引き続き緑（フェーズ②の成果物を壊していない）。
  - 注意: SKILL.md はテスト困難のため単体テスト例外（CLAUDE.md / implementation_guidelines）。健全性は「scripts テスト緑 + SKILL 経由 E2E 手動確認」で担保する。

### フェーズ ④: doc_structure 削除と仕様整合（クリーンアップ・同一 PR 整合）

- **目標**: 通常実行経路で `.doc_structure.yaml` を一切読まない状態を最終確定し、README / workflow / formats / base 仕様の supersede 箇所を改訂して REQ-004 受け入れ基準「仕様整合」（NFR-N04: コードと同一 PR）を満たす。
- **スコープ**（REQ-004 受け入れ基準 / §9 / DES-006 §7.1 / §14）:
  - `.doc_structure.yaml` 通常経路依存の最終除去確認と、それに依存していた旧テストの削除（フェーズ②で `toc_utils.py` から削除したロジックに対応する旧テストを同時除去: implementation_guidelines「使わないコードは削除、テストも同時削除」）。
  - 旧 doc_structure 依存が通常経路に残っていないことの回帰テスト追加（DES-006 §13、既存 embedding-removal 回帰テストに倣う）。
  - `formats/toc_format.md` から `doc_type` 除去（§7.1）。
  - README / README_en / SKILL / workflow から `setup-doc-structure` 前提・config_required 案内導線を削除（受け入れ基準）。Python 下限 3.9 を README に明記（REQ-004 §6.1 / NFR-N01）。
  - base 仕様の supersede 箇所改訂（NFR-N04 同一 PR）: REQ-001（PRE-01〜03 / FR-01-1 / FR-01-7 / FR-06 / NFR-02-4,5）、DES-004（文書モデル全体）、DES-005（Phase 0）の §9 通りの改訂。
  - `dprint fmt` 整形（変更 Markdown / YAML / JSON）。
- **フェーズ内実装順序**:
  1. 通常経路の doc_structure 非読込を確認 → 旧 category 依存テスト削除 + 非読込回帰テスト追加
  2. formats（toc_format.md doc_type 除去）
  3. README / workflow / SKILL の setup-doc-structure 記述削除・Python 下限明記
  4. base 仕様（REQ-001 / DES-004 / DES-005）supersede 箇所改訂
  5. `dprint fmt`
- **検証ポイント**:
  - 通常経路で `.doc_structure.yaml` を読まない回帰テストが緑（受け入れ基準）。
  - `python3 -m unittest discover -s tests -p 'test_*.py' -v` 全緑（旧テスト削除後も整合）。
  - README / SKILL / workflow / formats に `setup-doc-structure` / `doc_type` 残存なし（grep 確認）。
  - base/REQ-001・DES-004・DES-005 が §9 通り改訂済み。
  - `dprint check` 緑。

## フェーズ完了時のビルド・テスト健全性の考え方

- **各フェーズ完了時に build/test が通る単位を維持する**（REQ-004 TBD-002 暫定段階分割の原則）。フェーズ間依存は一方向（③は②の script 契約に、④は②③の成果物に依存）。
- **健全性の基準はフェーズで異なる**:
  - フェーズ②: `scripts/` 単体・統合テスト緑 + JSON 契約固定 + 外部依存ゼロ。SKILL 経由 E2E は対象外（旧 SKILL がまだ旧 script を参照し得るため、ここを健全性条件に含めない）。
  - フェーズ③: scripts テスト緑（②を壊さない）+ 新 SKILL 経由 E2E 手動確認。SKILL.md はテスト例外。
  - フェーズ④: 旧 category 依存テスト削除後も全テスト緑 + doc_structure 非読込回帰テスト緑 + 仕様/文書整合（grep・supersede 改訂）+ dprint check 緑。
- **テスト必須の貫徹**: `scripts/` 配下の新設・改修 Python は対応する単体テストを同一フェーズ内で伴う（NFR-N03 / CLAUDE.md MANDATORY）。実装タスクとテストタスクを分離する場合も同一フェーズに閉じる。
- **同一 PR 制約**: 仕様改訂（REQ-004 / DES-006 / base supersede）はコードと同一 PR（NFR-N04）。段階分割で複数 PR にする場合でも、各 PR 内でコード変更とその PR が触れる仕様・文書の整合を取る。バージョン関連ファイル（plugin.json version / README バージョン表記 / CHANGELOG / git tag v*）は通常 PR で編集禁止 → 「version bump」タスクを計画に混入させない（implementation_guidelines）。

## リスクと対策

| リスク                                                                                                                                                       | 影響度 | 対策（どのフェーズで潰すか）                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| doc_structure 削除の順序ミス（フェーズ②で `toc_utils.py` の category 分岐を削除すると、それに依存する旧テスト・旧 SKILL が即座に壊れ build/test が赤になる） | 高     | フェーズ②では `toc_utils.py` から category ロジックを削除しつつ、**それに依存する旧テストの最終削除と doc_structure 非読込の回帰固定はフェーズ④に集約**する。②では新 script のテストを緑にすることを健全性基準とし、旧 category 依存テストは④まで段階的に整理。clean break の「除去の完了」を最後に置くことで途中フェーズの検証を安定させる。                                    |
| `resolve_within_root()` symlink 厳格化（後方互換の意図的破壊・新規ロジック）の挙動誤り                                                                       | 高     | リスク駆動でフェーズ②前半（`toc_utils.py` 改修）に実装し、6 系統 path 検証 + root 外 symlink reject + 単体モード列挙後除外（§5.3）の単体テストで早期に固定。`validate_path_within_base()` の docstring・ポリシーは変更しないことを明示（traversal 専用流用と symlink 新規ロジックの分離を崩さない）。                                                                            |
| TBD-001（単体モード最大ファイル数の警告閾値）が未確定                                                                                                        | 中     | **AI が数値を捏造しない**。戦略上は「warning 機構自体はフェーズ②の `prepare_toc.py --all` で実装可能（閾値超過で warnings に追加し処理継続: NFR-N05）」と「閾値の具体値は当事者確定が必要」を分離して扱う。計画書では閾値定数の確定を実装着手前のブロッカー（当事者確認事項）として明示し、機構実装と数値確定を別タスク化。閾値未確定でも空 ToC 冪等出力・処理継続の検証は可能。 |
| 既存テストとの整合（旧 script 改名・統合に伴うテストファイルの追従漏れ）                                                                                     | 中     | 旧テスト（test_create_pending → prepare、test_filter_toc → get_toc 等）の改名・移行を各 script 改修と同一フェーズ・同一タスクで行い、使わないテストは即削除（implementation_guidelines「テストも同時削除」）。フェーズ完了時に discover 実行で孤児テスト・import エラーがないことを確認。                                                                                        |
| prepare / merge 協調フロー（FR-N07-3）の境界誤実装（script が AI 処理を内包してしまう）                                                                      | 中     | レイヤ責務（FR-N07-1: script はメタデータ抽出をしない）を単体テストで固定（「script 単体がメタデータ抽出をしないこと」: 受け入れ基準）。メタデータ充填は toc-updater agent 経路のみ（フェーズ③）に限定。                                                                                                                                                                         |
| merge 失敗時のストア破損（原子的書き込み・backup/restore の key 単位再編漏れ）                                                                               | 中     | フェーズ②の `merge_toc.py` で base/DES-005 Phase 3/4 の backup → validate → restore を key 単位ストアに踏襲（§6.5）。`os.replace` 原子的置換 + 検証失敗時 `.bak` 復元・checksums 据え置き・`.toc_work/` 保持を単体テストで確認。                                                                                                                                                 |
| SKILL 仕様の独自解釈（fork / 継承の判別、自己再帰呼び出し）                                                                                                  | 低〜中 | フェーズ③で claude-code-guide agent による公式確認（MANDATORY）。fork 型採用は規定リスト準拠、query-docs の自己再帰禁止、起動経路は公式短縮名称で統一（skill_authoring_notes / skill_launch_paths_definitions）。                                                                                                                                                                |
| 設計書の単純度によるフェーズ未分割                                                                                                                           | 低     | 本 feature は 8 モジュール改修 + SKILL/agent 一本化 + 仕様整合を含む規模であり、2 フェーズ未満には収まらない。段階分割（②③④ の 3 フェーズ）が妥当。                                                                                                                                                                                                                              |

## 計画書作成への申し送り事項

- **plan_dir 未作成**: `docs/specs/new-if/plan/` は未作成（refs/specs.yaml `plan_dir_status`）。計画書作成タスクが生成する。Spec ID は forge:next-spec-id でブランチ衝突を回避して発行する想定。
- **TBD-001 を計画書のブロッカー欄に明示**: 単体モード閾値の数値確定は当事者確認事項。AI が値を埋めない。
- **version bump タスクを混入させない**: plugin.json version / CHANGELOG / git tag は通常 PR 編集禁止（implementation_guidelines）。
- **specs 内 ID 参照は ID プレフィックス、rules/workflows/formats はプロジェクトルート起点フルパス**（document_writing_rules）。計画書記述時に適用。
