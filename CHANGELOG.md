# Changelog

All notable changes to this project will be documented in this file.

## [marketplace 0.1.25] - 2026-05-21

### marketplace

- **chore**: forge 0.1.1 のリリースに伴い marketplace バージョンをバンプ

## [forge 0.1.1] - 2026-05-21

### forge

- **feat(review)**: `/forge:review` パイプラインを 1 reviewer 起動原則 + criteria 固定 3 セクション構造 (SSOT参照 / チェック順 / 判定ルール) に再設計 (Issue #68 / REQ-004 / DES-028)。観点軸並列起動 (`## Perspective:` × N) と対象ファイル軸並列起動を撤廃し、P1/P2/P3 を同一 reviewer 内でチェック順に順次評価する方式に変更
- **feat(review)**: criteria 5 種別 (`code` / `design` / `requirement` / `plan` / `uxui` / `generic`) を 3 セクション固定構造に全面置換。criteria は判断を持たず routing table + review playbook に純化
- **feat(review)**: `recommendation: create_issue` を正式に値域追加 (FNC-406 3 条件: 該当規定なし / 再発性または客観性 / 明文化可能粒度)。present-findings に Issue 化選択肢 + `/anvil:create-issue` 経路を実装
- **feat(review)**: priority (P1/P2/P3) × severity (🔴/🟡/🟢) の直交ラベル付与に変更。evaluator は 5 観点 × priority の直交評価、present-findings は priority 二段ソート対応
- **refactor(scripts)**: `write_refs.py` を旧 `perspectives[]` スキーマ撤廃 + `review_packet { criteria_path / ssot_refs[] / check_order }` 検証に置換。`write_interpretation.py` を `--kind` 引数 + `review_<種別>.md` 命名に変更。`merge_evals.py` を priority ベース統合に書き換え
- **feat(principles)**: forge 内蔵 principles 4 ファイル (`spec_priorities_spec.md` / `spec_design_boundary_spec.md` / `design_principles_spec.md` / `plan_principles_spec.md`) に重大度カタログ + グレーゾーン許容範囲 + 観点別利用ガイドを merge (FNC-411)
- **test**: 回帰検出テスト 5 ファイルを追加 (`test_criteria_no_perspective.py` / `test_no_legacy_perspective_filename.py` / `test_review_integration.py` / `test_reviewer_single_invocation.py` / `test_resolve_review_context.py`)

## [marketplace 0.1.24] - 2026-05-19

### marketplace

- **chore**: forge 0.1.0、anvil 0.0.8、doc-db 0.0.2 のリリースに伴い marketplace バージョンをバンプ

## [forge 0.1.0] - 2026-05-19

### forge

- **feat**: forge-query 抽象 SKILL（`query-db-rules` / `query-db-specs` / `update-db-rules` / `update-db-specs`）を新設し、doc-advisor / doc-db バックエンドを自動選択する設計を導入（DES-001 / ADR-001）。`select_backend.py` が API キー有無と利用可能バックエンドから採用先を決定し、4 SKILL は `user-invocable: false` の内部 SKILL として動作する
- **refactor**: forge skills 内の `/doc-advisor:*` 直呼びを `/forge:*-db-*` 抽象 SKILL に切り替え（review / start-design / start-plan / clean-rules / merge-feature-specs / create-feature-from-plan / start-requirements / start-uxui-design）
- **fix(skills)**: query 系 SKILL に read-only 制約を実装し、subagent が書き込み系ツールを使用しないように Role 否定的制約 + allowed-tools 絞り込みを追加（Issue #55 / ADR-002）
- **refactor**: start-plan SKILL に実装戦略策定フェーズを追加（DES-027）。設計書からタスクを機械的に分解する前に、SubAgent が実装アプローチを判断し `strategy_draft.md` を生成する
- **refactor**: FNC-008/DES-028 を doc-advisor へ再配置し、merge-feature-specs に配置整合性検査を追加
- **docs**: SKILL 基本設計書を新設し fork 型を規定リストで厳密管理。forge 文書スタイル指針と ID 参照記法、文書スタイル指針 (document_style_guide) を追加し DWR を整理

## [anvil 0.0.8] - 2026-05-19

### anvil

- **docs(impl-issue)**: `/doc-advisor:query-specs` / `/doc-advisor:query-rules` への args 渡し方を、Issue タイトル・本文から抽出した短い検索キーワードまたは短い自然文のタスク記述に限定する制約を明文化（COMMON-DES-001 §3.4 [MANDATORY]）。Issue 本文の全文貼り付けを禁止

## [doc-db 0.0.2] - 2026-05-19

### doc-db

- **update**: query SKILL の Output Format を `Required documents:` 先頭ハイブリッド形式に統一（forge-query 抽象 SKILL との互換性確保）

## [marketplace 0.1.22] - 2026-05-16

### marketplace

- **chore**: doc-advisor 0.2.6 のリリースに伴い marketplace バージョンをバンプ

## [doc-advisor 0.2.6] - 2026-05-16

### doc-advisor

- **fix**: query-specs / query-rules SKILL.md から `context: fork` 等の subagent 起動 frontmatter を削除し、`/doc-advisor:query-specs` が "initializing" で停止する不具合を解消。SKILL 本体を直接実行する方式に変更し、doc-db への Hybrid 検索委譲フロー（`/doc-db:build-index --check` / `/doc-db:query`）は維持

## [marketplace 0.1.21] - 2026-05-15

### marketplace

- **chore**: doc-advisor 0.2.5 のリリースに伴い marketplace バージョンをバンプ

## [doc-advisor 0.2.5] - 2026-05-15

### doc-advisor

- **feat**: API KEY 参照を `OPENAI_API_DOCDB_KEY` 優先 + `OPENAI_API_KEY` フォールバックの方式で doc-db と統一。`embedding_api.get_api_key()` を新設し、`embed_docs.py` / `search_docs.py` の直接参照を置き換え
- **feat**: query-specs / query-rules SKILL.md に mode=auto subagent 内完結フロー（doc-db Hybrid 検索委譲・available-skills 事前参照）を実装
- **docs**: SKILL.md の API KEY 関連エラー文言を `OPENAI_API_DOCDB_KEY` / `OPENAI_API_KEY` 併記に統一

## [forge 0.0.45] - 2026-05-12

### forge

- **feat**: start-plan に実装戦略策定フェーズを追加（DES-027）。設計書からタスクを機械的に分解する前に、SubAgent が実装アプローチを戦略的に判断し `strategy_draft.md` を生成するフェーズを導入
- **fix(BR-001)**: スクリプトのエラーメッセージからスラッシュコマンド形式を除去し、プラグインモード・スタンドアロンモード両方で正しいスキル名を案内するよう変更

## [doc-advisor 0.2.4] - 2026-05-12

### doc-advisor

- **fix(BR-001)**: スクリプトのエラーメッセージからスラッシュコマンド形式を除去し、環境非依存な表記に変更（5 箇所）

## [marketplace 0.1.20] - 2026-05-12

### marketplace

- **chore**: forge 0.0.45、doc-advisor 0.2.4、doc-db 0.0.1 のリリースに伴い marketplace バージョンをバンプ

## [doc-db 0.0.1] - 2026-05-12

### doc-db

- **feat**: 初回リリース。見出し chunk 単位の Hybrid 検索（Embedding + Lexical BM25）と LLM Rerank
- **feat**: emb top-K 保証（EMB_GUARANTEE_K=5）を実装し、hybrid recall ≥ emb recall の不変条件を保証。RRF による語彙マッチなしチャンクの押し出しを防ぐ
- **feat**: `embed_text` フィールドを導入。heading_path の文脈 + 直近祖先 prose を結合してチャンク埋め込みの精度を向上（空セクションのフォールバック対応）
- **refactor**: Lexical スコアリングを TF から BM25 に刷新し、PHRASE_SYNONYMS（手動同義語辞書）を削除。字句一致のみに特化し、意味的類似は Embedding に委ねる
- **feat**: `get_index_path()` が `.doc_structure.yaml` の `output_dir` を尊重するように対応

## [BR-001 / BR-002 対応] - 2026-05-09

### forge / doc-db / doc-advisor

- **fix(BR-001)**: 全プラグインの Python スクリプトのエラーメッセージに含まれるスラッシュコマンド形式（`/forge:setup-doc-structure`, `/doc-advisor:create-*-toc` 等）を環境非依存な表記に変更。プラグインモードとスタンドアロンモードの両方で正しいスキル名を案内できるようにした。対象: doc-db 2 箇所、doc-advisor 5 箇所、forge 3 箇所の計 10 箇所
- **test**: `TestNoSlashCommandRefsInScripts` を `tests/common/test_plugin_integrity.py` に追加。forge / doc-advisor / doc-db の Python スクリプト内にスラッシュコマンド形式が残っていないことを自動検証する回帰防止テスト
- **docs(BR-002)**: SKILL.md 内のクロスプラグイン参照（64 箇所）は、プラグインモード（一次配布形態）で名前空間付きが必須のため変更不要と判断。スタンドアロンモードは setup.sh 側の sed 変換で対処済み

## [forge 0.0.44] - 2026-05-08

### forge

- **feat**: start-implement で全タスク完了後に plan の扱いをユーザーへ確認するフローを追加
- **feat**: review SKILL の TBD-xxx fix path を需求レビューで対応
- **refactor**: monitor 機能の削除、meta & progress の削除、冗長性の解消
- **fix**: review SKILL の修正、meta 関連テストの修正

## [doc-advisor 0.2.3] - 2026-05-08

### doc-advisor

- **docs**: デザイン DES-026 追加、heading-chunk ハイブリッド検索プラグインの要件定義書追加 (#33)
- **chore**: create-code-index / query-code スキルと関連コードの削除
- **refactor**: index の更新

## [marketplace 0.1.19] - 2026-05-06

### marketplace

- **feat**: forge を 0.0.43、anvil を 0.0.7 に更新。start-implement の plan 後始末強化と impl-issue Phase 5 の AskUserQuestion 追加を反映

## [0.0.43] - 2026-05-06

### forge

- **feat(start-implement)**: 全タスク完了時に plan の扱いをユーザーへ確認するフローを追加。`{main_specs_root}` 配下の構成から追加開発か基本仕様修正かを文脈判定し、`/forge:merge-feature-specs` 実行 / plan 削除 / plan 残し のいずれかを `AskUserQuestion` で誘導（#31）
- **refactor(session)**: セッション管理を新方式に刷新。session_manager の責務分離、monitor のクリーンアップ、`atomic_write_text` を `yaml_utils` に統合し共通化
- **fix(help)**: help SKILL の動作不具合を修正

## [anvil 0.0.7] - 2026-05-06

### anvil

- **refactor(impl-issue)**: 類似 PR 調査（Phase 5）の実行前に `AskUserQuestion` でユーザー確認を入れるよう改善

## [marketplace 0.1.18] - 2026-04-29

### marketplace

- **feat**: forge を 0.0.42、anvil を 0.0.6 に更新。`merge-feature-specs` の汎用化（プロジェクト構造非依存）と `create-issue` SKILL の品質向上を反映

## [0.0.42] - 2026-04-29

### forge

- **fix(merge-feature-specs)**: 任意プロジェクト構造で動作するよう汎用化。plugin 階層前提を廃し、`.doc_structure.yaml` と `feature_dir.parent` ベースで main 仕様棚を解決。`scan_feature.py` に `--main-specs-root` / `--id-digits` / `--id-separator` オプションを追加し、`requirement` 単数形と plugin 階層なし構造に対応
- **fix(merge-feature-specs)**: 前提条件を明確化（PR #26 review 反映）。Phase 0 で `.doc_structure.yaml` と doc-advisor の必須検査を追加し、フォールバック推測を排除。必須（`.doc_structure.yaml` / doc-advisor）と任意（dprint / anvil）の区別を整理

## [anvil 0.0.6] - 2026-04-29

### anvil

- **feat(create-issue)**: SKILL の品質を `create-pr` と同等に向上。Issue 構成・記述ガイドライン・テンプレートを大幅拡充（236 行追加）

## [marketplace 0.1.17] - 2026-04-28

### marketplace

- **fix**: forge を 0.0.41、doc-advisor を 0.2.2 に更新。`context: fork` SKILL が無限再帰でハーネスを詰まらせる重大バグを修正

## [0.0.41] - 2026-04-28

### forge

- **fix(query-forge-rules)**: fork されたサブエージェントが SKILL.md 本文を「query-forge-rules を Skill で呼べ」と誤読し、`Skill(query-forge-rules)` を tool_use → 無限再帰でサブエージェントが大量並列起動しハーネスが応答停止する重大バグを修正。SKILL.md 冒頭に「これはあなた自身への実行指示書」「query-* を Skill で呼んではいけない」を明記

## [doc-advisor 0.2.2] - 2026-04-28

### doc-advisor

- **fix(query-rules / query-specs / query-code)**: fork されたサブエージェントが SKILL.md 本文を「query-rules / query-specs / query-code を Skill で呼べ」と誤読し、`Skill(query-*)` を tool_use → 無限再帰でサブエージェントが 500+ 並列起動しハーネスが 30 分以上応答停止する重大バグを修正。SKILL.md 冒頭に「これはあなた自身への実行指示書」「query-* を Skill で呼んではいけない」を明記

## [marketplace 0.1.16] - 2026-04-26

### marketplace

- **feat**: forge を 0.0.40、anvil を 0.0.5 に更新。plan → 要件/設計の橋渡し（forge）と GitHub Issue 駆動開発フロー（anvil）を追加

## [0.0.40] - 2026-04-26

### forge

- **feat(create-feature-from-plan)**: Claude Code plan mode の markdown を入口に、`forge:start-requirements` → `forge:start-design` を順次起動して要件定義書 → 設計書を一気通貫で作成する薄いオーケストレーション skill を追加。`~/.claude/plans/*.md` から直近候補を提示する `list_recent_plans.py` を同梱

## [anvil 0.0.5] - 2026-04-26

### anvil

- **feat(create-issue)**: 問題・背景・原因を整理して GitHub Issue を作成する skill を追加（解決策は `impl-issue` が担当）。`gh issue create` を内部で呼び出す
- **feat(impl-issue)**: GitHub Issue から実装計画策定 → ブランチ作成 → 実装 → PR 作成までを一貫実行する skill を追加。仕様書/ルール調査（doc-advisor 連携）、類似 PR 学習、Issue への解決内容追記、UI Issue の Figma デザイン仕様書作成・実装レビューまで 14 Phase でカバー

## [marketplace 0.1.15] - 2026-04-24

### marketplace

- **feat**: forge を 0.0.39 に更新。io_verb Feature（SKILL.md を script 詳細から解放する透過ラッパー30本）の完成と find_session no-arg 契約違反の是正を反映

## [0.0.39] - 2026-04-24

### forge

- **refactor(io_verb)**: SKILL.md を低レベル script の引数詳細から解放する透過ラッパー導入を完了（TASK-001〜010）。`find_session` / `init_session` / `update_plan` / `skip_all_unprocessed` / `resolve_doc` / `resolve_rules` / `resolve_specs` / `update_version_files` 系の wrapper を各 SKILL 配下に配置し、`extract_review_findings.py` を reviewer から review skill へ移動
- **fix(io_verb)**: `find_session.py` 6本の no-arg 契約違反を是正。`+ sys.argv[1:]` を削除し、対応する 6 テストを `test_extra_argv_not_passed_through` に反転。DES-024 §3.1 の「wrapper は skill 名を自前で知り、SKILL.md から no-arg 呼び出し」契約を実装に反映
- **fix(review)**: `skip_all_unprocessed.py` の subprocess 呼び出し2箇所に `encoding="utf-8", errors="replace"` を明示し、非 UTF-8 ロケール下での UnicodeDecodeError リスクを排除
- **docs(io_verb)**: io_verb 設計書（DES-024）と実装計画書を追加。要件・設計・計画・実装を一連で完結

## [marketplace 0.1.14] - 2026-04-20

### marketplace

- **feat**: forge を 0.0.38 に更新。monitor スキルへの再構築とレビュー重複統合ロジックの刷新を反映

## [0.0.38] - 2026-04-20

### forge

- **refactor(show-browser → monitor)**: show-browser スキルを廃止し、`plugins/forge/scripts/monitor/` に集約。`launcher.py` / `server.py` / `notify.py` を分離し、review / implement / uxui / document / generic の各テンプレートを再構築。session_manager と統合して自動起動に対応
- **refactor(reviewer)**: 機械的な重複除去を廃止し、present-findings 側で Claude が意味的に統合する方式に変更。`extract_review_findings.py` から `deduplicate_findings` / `perspectives` 複数フィールド / `bodies_by_perspective` を削除し、同一箇所の指摘は個別項目として残す。present-findings に Step 1.5「意味的重複の自動統合」を追加
- **feat(monitor)**: `review.html` テンプレートに `skip_reason` 表示を追加。重複統合の理由を browser 上で確認可能に
- **fix(session)**: `update_plan.py` / `write_interpretation.py` / `write_refs.py` の通知処理を整備

## [marketplace 0.1.13] - 2026-04-19

### marketplace

- **feat**: forge を 0.0.37 に更新。reviewer パイプラインの信頼性を大幅強化

## [0.0.37] - 2026-04-19

### forge

- **fix(review)**: codex exec の `-o` 最終メッセージが reviewer 本体のレビュー内容を上書きする不具合を根絶。`-o` を `.codex_lastmsg.txt` に、stdout を `.stdout` に分離し、`extract_codex_output.py` で Markdown 本文を抽出する新設計に変更
- **fix(review)**: `--full-auto` を削除し `--sandbox read-only` のみに。reviewer が `apply_patch` で誤書き込みする経路を塞ぐ二重防御
- **fix(reviewer)**: `extract_review_findings.py` がセクション見出し欠落時に指摘事項を silent drop する不具合を修正。finding 行マーカー必須化 + 空セクション保持（`（なし）`）+ parser fallback の 3 層防御を導入（実セッションで 21 件中 12 件しか拾えなかった事故の対策）
- **refactor(reviewer)**: severity 指定を絵文字 🔴/🟡/🟢 から ASCII ラベル `[critical]/[major]/[minor]` primary に移行。LLM による絵文字の省略・Unicode 正規化の揺れ・色覚アクセシビリティの不安定性を回避（絵文字は後方互換として装飾扱い）
- **refactor(review)**: review skill の構造的リファクタリング

## [marketplace 0.1.12] - 2026-04-19

### marketplace

- **feat**: forge を 0.0.36 に更新。SDD 解説書と追加開発ワークフロー仕様を追加、参照漏れを修正、show-browser / review の挙動を改善

## [0.0.36] - 2026-04-19

### forge

- **feat(show-browser)**: severity を複数選択対応にし、解決済み/Skipped をトグル化
- **feat(show-browser)**: `session_end` SSE payload に close-tab hint を追加
- **fix(show-browser)**: サーバーを独立セッションで起動し、起動指示を簡素化
- **fix(review)**: codex exec 実行時に stdin を close してハング発生を防止
- **docs**: SDD 解説書 `docs/readme/guide_sdd_ja.md` を新規追加（哲学・5 段階の役割・追加開発ワークフローを解説）
- **docs**: AI 向け追加開発ワークフロー仕様 `plugins/forge/docs/additive_development_spec.md` を新規追加（判定基準・矛盾時の優先度・merge 手順を定義）
- **docs**: `requirement_format.md` に追加 feature 用 frontmatter（`type: temporary-feature-requirement`）ルールを追加
- **fix**: start-requirements の `--add` モードで `additive_development_spec.md` / `requirement_format.md` を [MANDATORY] 参照するよう修正（参照漏れ対応）
- **chore**: forge 内蔵 `rules_toc.yaml` を更新

## [marketplace 0.1.11] - 2026-04-18

### marketplace

- **docs**: 日本語 README をデフォルトに変更（旧 README.md → README_en.md、旧 README_ja.md → README.md）。言語切替リンクと `.version-config.yaml` を追従
- **chore**: 未使用の画像ファイル（install_kaizen.png, review.png）を削除

## [0.0.35] - 2026-04-18

### forge

- **refactor**: start-uxui-design スキルを刷新。`design_token_template.md` / `component_catalog_template.md` を追加し、`uxui_analysis_workflow.md` を大幅拡張
- **feat**: review スキルに UXUI 観点の `review_criteria_uxui.md` を追加
- **docs**: setup-version-config / update-version SKILL.md の README 例示を `README_en.md` に合わせて更新

## [marketplace 0.1.10] - 2026-04-16

### marketplace

- **feat**: forge を 0.0.34 に更新。README ドキュメント体系の再構築

## [0.0.34] - 2026-04-16

### forge

- **docs**: README ドキュメント体系を再構築。全スキルの詳細ガイドファイルを作成し、ルート README からの2層ナビゲーションに整理
- **docs**: スキルテーブルに Trigger 列を追加。ユーザートリガーは代表フレーズ1個、AI 専用は呼び出し元を「※」付きで表示。全4プラグインで統一
- **docs**: ガイドファイルの命名を `README_*` から `guide_*` に統一。ルート README のみ README を維持
- **docs**: AI 専用スキル（reviewer, evaluator, fixer 等）に関連ガイドへのリンクを追加
- **docs**: Document Structure Guide を独立ファイルとして新設。Feature 概念・スキーマ概要・設定パターンを記載
- **fix**: show-browser サーバーの monitor_dir クリーンアップ競合を修正

## [marketplace 0.1.9] - 2026-04-15

### marketplace

- **feat**: forge を 0.0.33 に更新。レビューパイプラインのデータ破壊バグ修正 + show-browser のセキュリティ強化

## [0.0.33] - 2026-04-15

### forge

- **fix**: evaluator 結果マージの ID 衝突バグを修正。`review` SKILL.md Phase 4 Step 1.5 / 自動修正モード Step 1 を `merge_evals.py` 経由に変更し、perspective ローカル ID → plan.yaml グローバル ID の変換を保証。`update_items_batch` に重複 ID 検出ガードを追加して誤用を即エラー化（2026-04-15 インシデント対応）
- **fix**: `review` Phase 5 に終了確認ステップを追加。未処理指摘（pending / needs_review）が残った状態でセッションディレクトリが無条件削除される問題を修正。全件が `fixed` または `skipped` で決着するまで終了しない構造に改修
- **fix**: `show-browser` のパス / コンテンツ経由の攻撃への耐性を強化

## [marketplace 0.1.8] - 2026-04-15

### marketplace

- **feat**: forge を 0.0.32 に更新。show-browser 機能の全オーケストレータ統合を完了

## [0.0.32] - 2026-04-15

### forge

- **feat**: `show-browser` スキルを全オーケストレータに統合。review / start-design / start-plan / start-requirements / start-implement の各 SKILL.md にセッション作成直後の show_browser.py 呼び出しを追加し、ブラウザでセッション進捗をリアルタイム表示可能に
- **feat**: `session_status.html` 汎用テンプレートを追加。session.yaml メタデータ（スキル名・ステータス・開始時刻・Feature名）、refs/ 配下の収集結果、出力先ファイルの存在状態を SSE 経由でリアルタイム表示
- **fix**: start-implement SKILL.md の不具合修正

## [marketplace 0.1.7] - 2026-04-12

### marketplace

- **feat**: forge を 0.0.31 に更新。仕様書 ID の全ブランチスキャン採番機能を追加

## [0.0.31] - 2026-04-12

### forge

- **feat**: `next-spec-id` スキルを追加。全ブランチ（ローカル+リモート）をスキャンして仕様書 ID の次の連番を安全に取得する。`.doc_structure.yaml` から specs パスを動的に解決し、ブランチ間の ID 重複を防止
- **refactor**: start-requirements / start-design / start-plan の各ワークフローに ID 採番スクリプト呼び出しを統合。手動番号決定を禁止し、スクリプトによる一貫した採番を必須化
- **refactor**: SKILL.md の description / trigger を改善（複数スキル）
- **feat**: レビュー基準に requirement / design / plan 用の追加 perspective を追加

## [marketplace 0.1.6] - 2026-04-11

### marketplace

- **feat**: forge を 0.0.30 に更新。`.doc_structure.yaml` の `**` 再帰 glob パターン対応

## [0.0.30] - 2026-04-11

### forge

- **feat**: `.doc_structure.yaml` で `**`（再帰 glob）パターンをサポート。`docs/specs/**/design/` のように1行で任意の深さの Feature ディレクトリを指定可能に
- **refactor**: `_extract_feature_from_match()` を `**` 対応に改修。prefix/suffix 分割アルゴリズムで可変長マッチから Feature 名を抽出
- **docs**: doc_structure_format.md, SKILL.md 等の関連文書を `**` パターン対応に更新

## [marketplace 0.1.5] - 2026-04-11

### marketplace

- **fix**: doc-advisor を 0.2.1 に更新。ToC 検索ワークフローの output_dir 未対応バグを修正

## [0.2.1] - 2026-04-11

### doc-advisor

- **fix**: `query_toc_workflow.md` が `.doc_structure.yaml` の `output_dir` を参照せず固定パス（`.claude/doc-advisor/toc/`）を使用していたバグを修正。`output_dir` 設定時に正しい ToC パスを導出するように変更

## [marketplace 0.1.4] - 2026-04-11

### marketplace

- **feat**: doc-advisor を 0.2.0 に更新。query-rules/query-specs を統合し、ToC/Index/ハイブリッドの3モード対応に

## [0.2.0] - 2026-04-11

### doc-advisor

- **feat**: query-rules/query-specs を統合し、`--toc`（キーワード）/ `--index`（セマンティック）/ ハイブリッド（デフォルト）の3モード検索に対応。両方の検索結果を union して AI が最終判定する
- **refactor**: create-rules-index/create-specs-index を query に統合。query 時に Index を自動ビルド（差分更新）するため、手動インデックス構築が不要に
- **refactor**: query-rules-index/query-specs-index スキルを廃止し、query-rules/query-specs に統合。検索手順を workflow 文書（`query_toc_workflow.md`, `query_index_workflow.md`）に分離

## [marketplace 0.1.3] - 2026-04-09

### marketplace

- **feat**: doc-advisor を 0.1.7 に更新。resolve_config_path バグ修正、auto_create_toc.py 削除（品質評価により排除）

## [0.1.7] - 2026-04-09

### doc-advisor

- **fix**: `resolve_config_path()` のパス解決バグを修正。`output_dir` 由来のマルチコンポーネントパスが `project_root` ではなく `FIRST_DIR` 基準で解決され、二重パスが生成される問題を解消
- **feat**: `write_yaml_output()` / `write_checksums_yaml()` で出力先ディレクトリを自動作成（`output_dir` で新規ディレクトリへの初回書き出しに対応）
- **refactor**: `auto_create_toc.py` を削除。品質評価の結果（ゴールデンセット検索精度 41% vs embedding 95%）、メタデータ抽出品質が実用水準に達しないため排除。`_auto_generated` マーカー処理も併せて削除

## [marketplace 0.1.2] - 2026-04-08

### marketplace

- **feat**: doc-advisor を 0.1.6 に更新。output_dir による ToC/Index 出力パスの動的切り替えをサポート

## [0.1.6] - 2026-04-08

### doc-advisor

- **feat**: output_dir フィールドによる ToC/Index 出力パスの動的切り替えをサポート
- **feat**: create_checksums.py に --promote-pending / --clean-work-dir フラグを追加し、Phase 3 のハードコードパスを排除
- **feat**: get_index_path() を config 参照に変更（embed_docs.py / search_docs.py）
- **fix**: golden_set テストの stale チェックスキップと config ベースのインデックスパス統一

## [marketplace 0.1.1] - 2026-04-07

### marketplace

- **feat**: doc-advisor を 0.1.5 に更新。セマンティック検索機能（OpenAI Embedding API）の追加に対応

## [0.1.5] - 2026-04-07

### doc-advisor

- **feat**: セマンティック検索機能を実装。OpenAI Embedding API (`text-embedding-3-small`) でドキュメントをベクトル化し、コサイン類似度検索を可能に
  - `embed_docs.py`: 差分更新・全体再構築・staleness check の3モード対応インデックス構築（チェックサムによる差分管理）
  - `search_docs.py`: クエリのベクトル化とコサイン類似度計算による検索（純粋 Python 実装、件数上限なし）
  - `embedding_api.py`: OpenAI API 通信の共有モジュール（バッチ100件、リトライ、レート制限対応）
  - `create-rules-index` / `create-specs-index` スキル: インデックス構築オーケストレーター
  - `query-rules-index` / `query-specs-index` スキル: セマンティック検索 + grep 補完の2段階検索
- **fix**: インデックス書き込みをアトミック化（一時ファイル経由の `os.replace`）し、書き込み中断による JSON 破損を防止
- **fix**: API レスポンスの embedding 数検証を追加（件数不一致時に RuntimeError）
- **fix**: API リトライに `Retry-After` ヘッダー対応と 5xx/URLError バックオフ（2秒）を追加。`API_RETRY_COUNT` を `API_MAX_RETRIES` にリネーム

## [0.1.4] - 2026-04-07

### doc-advisor

- **refactor**: `create-code-index` / `query-code` スキルを無効化。`plugin.json` の skills リストから除外し、ユーザー・AI ともに呼び出し不可に（ファイルは保持）

## [marketplace 0.1.0] - 2026-04-07

### marketplace

- **feat**: マーケットプレイスバージョン管理を導入。`metadata.version` を `marketplace.json` に追加（公式スキーマ準拠）
- **feat**: `.version-config.yaml` に marketplace ターゲットを追加。`/forge:update-version` でリポジトリ全体のバージョンも一括管理可能に

## [0.0.29] - 2026-04-05

### forge

- **feat**: `/forge:start-uxui-design` スキルを新規追加。要件定義書の ASCII アートからデザイントークン（THEME-xxx）と UI コンポーネント視覚仕様（CMP-xxx）を創造する。Apple HIG / Don Norman / Dieter Rams / Nielsen / Gestalt の知識ベースに基づく UX 評価付き（iOS / macOS 対応）
- **feat**: デザイン哲学の統合フレームワーク（3 層モデル: 認知の制約 / 構造の道具 / 美の方向性）を `design_philosophy.md` に構築
- **feat**: `/forge:review uxui` レビュー種別を追加。HIG 準拠性・ユーザビリティ・ビジュアルシステムの 3 観点でデザイン文書をレビュー
- **feat**: `update-forge-toc` ローカルスキルを作成。doc-advisor パイプラインを借用して forge 内蔵 `rules_toc.yaml` を自動生成
- **refactor**: ワークフロー・レビュー基準の知識ベース参照を `/forge:query-forge-rules` 経由に統一（ハードコードパス廃止、フォールバック付き）

## [0.0.28] - 2026-04-04

### forge

- **feat**: `merge_evals.py` を新規追加。evaluator 結果（eval_*.json）の plan.yaml 一括マージをスクリプト化し、インライン処理を廃止
  - perspective → グローバル ID の動的マッピング（ハードコード排除）
  - `not_auto_fixable` リストを出力に含め、対話モードへの切り替え判断を支援
- **feat**: テスト 15 件追加（merge_evals: ユニット 11件 + E2E 4件）

## [0.1.3] - 2026-04-03

### doc-advisor

- **feat**: コードインデックス機能を実装（REQ-004 / DES-007）
  - `graph.py`: ImportGraph クラス（BFS N-hop 依存探索、逆引きインデックス）
  - `core.py`: ファイルスキャン・差分検出・インデックス構築・アトミック書き込み
  - `build_code_index.py`: CLI ラッパー（--diff / --mcp-data / --check）
  - `search_code.py`: CLI 検索（--query キーワード検索 / --affected-by 影響範囲検索）
  - `create-code-index` スキル: オーケストレーター + Swift subagent（Swift-Selena MCP 統合）
  - `query-code` スキル: 2段階検索（キーワード絞り込み + AI 評価）
- **feat**: テスト 91 件追加（graph 22件 + core 28件 + build CLI 21件 + search CLI 20件）

## [0.0.27] - 2026-03-29

### forge

- **fix**: `find_project_root()` の親方向探索を削除。`~/.claude/` 誤検出によるホームディレクトリスキャンを防止
- **docs**: review SKILL.md の reviewer/evaluator/fixer subagent 起動方法を明確化（`subagent_type` 指定なし = general-purpose を明示）
- **docs**: present-findings サマリーテーブルの5列目ヘッダを `AF`（auto_fixable）に修正

## [0.1.2] - 2026-03-29

### doc-advisor

- **refactor**: `check_doc_structure.sh` を廃止し、Python エラーハンドリングに統合
  - `ConfigNotReadyError` を `init_common_config()` に追加。設定未完了時に `{"status": "config_required"}` JSON を出力し、SKILL.md の Error Handling で AskUserQuestion による設定案内に対応
  - 4 SKILL.md の Pre-check セクションを削除し Error Handling を更新

### doc-advisor / forge 共通

- **fix**: `find_project_root()` / `get_project_root()` の親方向探索を削除。`~/.claude/` 誤検出によるホームディレクトリスキャンを防止

### forge

- **docs**: present-findings サマリーテーブルの5列目ヘッダを `AF` に修正
- **docs**: review SKILL.md の reviewer/evaluator/fixer 起動方法を明確化（general-purpose を明示）

## [0.1.1] - 2026-03-28

### doc-advisor

- **fix**: `determine_doc_type()` が `doc_types_map` の glob パターンキーとマッチしないバグを修正。`expand_doc_types_map()` を追加し `init_common_config()` で事前展開する根本対応
- **fix**: `load_checksums()` が空行でパースを中止する問題を修正
- **fix**: `load_config()` / `load_checksums()` の例外捕捉に OSError を追加
- **fix**: `has_substantive_content()` に UnicodeDecodeError 捕捉を追加
- **refactor**: DEPRECATED 関数 `extract_id_from_filename()` を削除
- **refactor**: checksums YAML 書き込みを `write_checksums_yaml()` に共通化
- **refactor**: 未使用 `import re` 削除、`import hashlib` をトップレベルに移動
- **refactor**: `validate_toc.py` の形骸化した重複パス検査を削除
- **docs**: SKILL.md の Error Handling に AskUserQuestion を明示
- **test**: `has_substantive_content()`, `determine_doc_type()`, `expand_doc_types_map()`, `expand_root_dir_globs()` のテスト追加

## [0.1.0] - 2026-03-28

### doc-advisor

- **feat**: .claude/ 配下のローカルスキルから独立プラグインに移行（TASK-001〜013）
  - スキル・agent・docs・scripts を `plugins/doc-advisor/` に移行
  - toc_utils.py をプラグイン環境に適応（`CLAUDE_PROJECT_DIR` / CWD 探索）
  - 全テストを Python unittest に移行（統合テスト含む）
  - forge プラグインからの namespace 参照を更新
- **refactor**: 重複関数の統一とコード一貫性の改善

## [0.0.26] - 2026-03-22

### forge

- **refactor**: バグ隠蔽フォールバックを除去し YAML ユーティリティを統合
  - session_manager.py の `except Exception` バグ隠蔽ハンドラを削除
  - session_manager.py の YAML ユーティリティを yaml_utils.py に統合（約60行削除）
  - skill_monitor.py の YamlReader 自前パーサーを yaml_utils.parse_yaml に統合（約300行削除）
  - エラー握りつぶし箇所（4箇所）に stderr 警告を追加
  - 到達不能コード（IndexError キャッチ、デッドコード、不要ラッパー）を削除

## [0.0.25] - 2026-03-22

### forge

- **refactor**: バグ起因でしか発生しない例外に対する無用なフォールバックを全スクリプトから除去
  - `except Exception` を具体的な例外型（IOError, OSError, UnicodeDecodeError）に限定（migrate_doc_structure / resolve_doc_references / resolve_review_context / read_session）
  - skill_monitor.py の二重ファイル読み込みを排除し、content ベースの parse_yaml に変更
  - scan_version_targets.py から不要な ValueError catch を除去
- **refactor**: review SKILL.md の Codex 存在チェック二重化を解消（Phase 3 の exit code ハンドリングに一本化）
- **refactor**: fixer SKILL.md から到達不能なフォールバック手順を削除し session_dir を必須化
- **fix**: セッション削除保護機能を追加（in_progress セッションの誤削除防止）
- **fix**: バージョン管理スクリプトのコードレビュー指摘事項を修正
- **docs**: subagent diff review ステップを review Phase 5 に追加
- **docs**: parallel agent output contract 設計書を追加

## [0.0.24] - 2026-03-22

### forge

- **feat**: perspectives ベースのレビューアーキテクチャを実装（reviewer/evaluator を perspective ごとに並列起動）
  - review_criteria を5種別（requirement/design/plan/code/generic）に分割し `## Perspective:` セクションで観点を定義
  - reviewer を 1 perspective 単位処理に変更（並列起動はオーケストレーターが制御）
  - evaluator を perspective 並列起動対応。出力契約パターン導入（eval_*.json → orchestrator が一括マージ）
  - extract_review_findings.py を multi-file merge 対応（glob 収集・通し番号 ID・perspective タグ・重複除去）
  - write_refs.py を perspectives 必須フィールド対応（name/criteria_path/section/output_path バリデーション付き）
- **feat**: バージョン管理ワークフロー設計書を作成（setup-version-config / update-version の設計を文書化）
  - scan_version_ref_files 追加（ルート全テキストファイルからバージョン参照を自動検出）
  - filter ルールを設計書に明記（README/CLAUDE.md 等の複数 target ファイルで誤置換を防止）
  - .version-config.yaml に CLAUDE.md を sync_files として追加
- **feat**: clean-rules スキルを追加
- **refactor**: evaluation.yaml を廃止し plan.yaml に統合（recommendation/auto_fixable/reason フィールド追加）
  - write_evaluation.py とテストを削除
  - present-findings から evaluation.yaml 依存を除去
  - session_format.md から evaluation.yaml セクションを削除
- **refactor**: evaluator SKILL.md を強化（対象ファイル検証必須化、判定バイアス是正）
- **fix**: 設計書のパイプライン順序を実装と統一（reviewers → extract → evaluators）
- **fix**: 廃止済み evaluation.yaml / review_criteria_spec.md への参照を全設計書・スクリプト・テストから削除
- **fix**: UnicodeDecodeError ハンドリングを extract_review_findings.py / scan_version_targets.py / list_forge_docs.py に追加
- **fix**: update_plan.py に recommendation/auto_fixable/reason フィールド処理と --recommendation バリデーションを追加
- **fix**: review/SKILL.md にブランチ確認ステップを追加（ブランチ関連の対象指定時）

## [0.0.23] - 2026-03-16

### forge

- **refactor**: セッション YAML 操作を scripts/session/ パッケージに委譲（write_refs, write_evaluation, update_plan, read_session, yaml_utils）
- **refactor**: 単一 SKILL 専用スクリプトをスキルディレクトリへ移動（extract_review_findings → reviewer, calculate/update_version → bump, scan_version_targets → setup-version-config）
- **refactor**: doc_structure 関連スクリプトを scripts/doc_structure/ に整理（classify_dirs, resolve_doc_references, migrate_doc_structure）
- **fix**: extract_review_findings.py が見出し形式（`### 1. **問題名**`）の指摘をパースできない問題を修正
- **feat**: reviewer テンプレート（templates/review.md）を追加し、SKILL.md のプロンプトをテンプレート参照に変更
- **refactor**: start-requirements ワークフローをモード別ファイルに分離（interactive, reverse-engineering, from-figma）

## [0.0.22] - 2026-03-16

### forge

- **refactor**: 全オーケストレーター（start-requirements/design/plan/implement）の完了処理を統一（review --auto → ToC → commit）
- **refactor**: finalize スキルを廃止。完了処理は各オーケストレーターが直接実行
- **refactor**: review Phase 1 の引数解析を Python スクリプトから AI 解釈に移行
- **remove**: `parse_review_args.py` とテスト削除（AI 解析に移行のため）
- **fix**: README の `--refactor` オプション名を `--auto` に統一（SKILL.md と整合）
- **refactor**: CLAUDE.md のルールを `docs/rules/implementation_guidelines.md` に移動（DocAdvisor 管理）
- **docs**: `orchestrator_pattern.md` に FNC-006（共通完了処理フロー）、FNC-007（AI 引数解釈）追加

## [0.0.21] - 2026-03-16

### forge

-

## [0.0.20] - 2026-03-15

### forge

- **refactor**: .doc_structure.yaml v3.0 対応（Doc Advisor v5.0 内部フィールド除去）
- **feat**: `migrate_doc_structure.py` 新規作成（COMMON-REQ-001 準拠の段階的マイグレーション）
  - v1→v2→v3 のチェーン実行、--check / --dry-run モード、テスト45件
- **feat**: `version_migration_spec.md` 新規作成（バージョンマイグレーション実装仕様）
- **fix**: review ワークフロー実装を設計書に整合
  - 残存セッション検出フロー追加、session_manager.py cleanup 使用、--diff-only パラメータ明示
  - 一括修正後の再レビューループ追加、auto 次サイクルで reviewer 再呼び出し
- **refactor**: 計画書フォーマットを Markdown → YAML に移行（FNC-005）
- **docs**: 設計書・要件定義書の齟齬修正（COMMON-REQ-001 と version_management_design の整合）

## [0.0.19] - 2026-03-15

### forge

- **refactor**: ドキュメント構造の大規模リファクタリング
  - `defaults/` を `docs/` に統合（8ファイル移動、ディレクトリ削除）
  - 設計書ファイル名を `_design` 接尾辞で統一（4ファイルリネーム）
  - ランタイム docs を `_format` / `_spec` 接尾辞で統一（5ファイルリネーム）
  - `doc_structure_format.md` を設計書 → ランタイム docs に移動
  - パイプライン → ワークフロー用語統一
- **refactor**: スキルリネーム `create-design/plan/requirements` → `start-design/plan/requirements`
- **refactor**: `start-implement` の `--parallel` を廃止、`--task` を複数ID対応（カンマ区切り）に変更
- **feat**: `review_workflow_design.md` 新規作成（3設計書を統合）
- **fix**: review ワークフロー実装を設計書に整合
  - fixer 後の単独修正レビュー（`--diff-only`）ループ追加
  - 対話モードで evaluator が plan.yaml を更新するよう修正
  - show-report を review Phase 4 から除去

## [0.0.18] - 2026-03-13

### forge

-

## [0.0.17] - 2026-03-13

### forge

-

## [anvil 0.0.4] - 2026-03-13

### anvil

-

## [0.0.16] - 2026-03-13

### forge

- **fix**: evaluator の plan.yaml 更新責務を全モード共通に統一（session_format.md, review_session_design.md）
- **fix**: present-findings の `in_progress` 更新を fixer 呼び出し前に移動し、`fixed` 上書きリスクを解消
- **fix**: forge_review_pipeline.md の evaluator インタフェーステーブルに3モード（--auto / --auto-critical / --interactive）を記載
- **fix**: review_session_design.md の進捗バー定義に `needs_review` を追加
- **fix**: `doc_structure_format.md` への参照パスを `docs/specs/forge/design/` に修正（README, README_ja, setup/SKILL.md, テスト）

## [0.0.15] - 2026-03-12

### forge

- **feat**: evaluator に `auto_fixable` フラグを追加（✅ 自明マーク判定を evaluator に一元化）
- **refactor**: evaluation.yaml の `decision` フィールドを `recommendation` にリネーム
- **refactor**: evaluator の plan.yaml 更新を全モード共通化（`--interactive` でも初期更新）
- **feat**: create-design / create-plan スキルのフルワークフロー実装
- **feat**: オーケストレータパターン要件定義書・セッションプロトコル設計書・コンテキスト収集ガイドを追加
- **docs**: create-* スキルから競合する優先度指示を削除
- **feat**: doc-advisor の SKILL / query ドキュメント改善

### anvil

- **refactor**: commit スキルの hook/issue-ref 検出をスクリプト化
- **fix**: Phase 7 で「push しない」をデフォルト選択肢に設定

## [0.0.14] - 2026-03-11

### forge

- **fix**: review パイプラインの Phase 番号を整数化（1.5 → 2 等）

## [0.0.13] - 2026-03-10

### forge

- **feat**: 全 SKILL.md でユーザー確認に AskUserQuestion ツールを必須化
- **fix**: AskUserQuestion の呼び出し修正

## [0.0.12] - 2026-03-09

### forge

- **feat**: `update-version` スキルを追加（plugin.json / marketplace.json / README.md の一括更新）

## [0.0.11] - 2026-03-08

### forge

- **feat**: セッションディレクトリ設計の実装と `session_format.md` 追加
- **refactor**: review パイプラインをオーケストレータパターンに再設計し設計書を追加
- **feat**: review パイプラインに Phase 別 progress reporting を追加

## [0.0.10] - 2026-03-07

### forge

- **feat**: review --refactor サイクルに evaluation phase（吟味フェーズ）を追加
- **refactor**: Phase 番号を 1.5 → 2, 2 → 3, 3 → 4 に整理
- **fix**: commit & push のユーザー確認フロー修正
- **fix**: コードレビュー指摘の修正（3サイクル）

## [0.0.9] - 2026-03-06

### forge

- **feat**: `create-design`, `create-plan`, `help` スキルを追加

### xcode

- **fix**: xcode スクリプトの修正

## [0.0.8] - 2026-03-05

### xcode

- **feat**: xcode プラグインを追加（`build`, `test` スキル）

## [0.0.7] - 2026-03-04

### anvil

- **feat**: anvil プラグインを追加（`create-pr`, `commit` スキル）

### forge

- **fix**: forge スキルの修正

## [0.0.6] - 2026-03-03

### forge

- **feat**: doc-advisor 更新
- **refactor**: スキル名のリネーム

## [0.0.5] - Initial Release

### forge

- **feat**: 初回リリース — review, setup, create-requirements, present-findings, fix-findings スキル
- **feat**: doc-advisor 統合（/query-rules, /query-specs）
- **feat**: .doc_structure.yaml によるプロジェクト文書構造管理
