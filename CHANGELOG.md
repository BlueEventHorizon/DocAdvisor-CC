# Changelog

All notable changes to doc-advisor are documented in this file.

> このリポジトリは `bw-cc-plugins` マーケットプレイス（forge / anvil / doc-advisor / doc-db の 4 プラグイン集）から `doc-advisor` を分離したものです。0.3.0 より前の詳細な変更履歴は git log および旧リポジトリ `BlueEventHorizon/bw-cc-plugins` を参照してください。

## [Unreleased]

### Changed

- `bw-cc-plugins` から分離し、Claude Code 公式仕様の単一プラグインリポジトリへ再構成
  - `.claude-plugin/plugin.json` を repo ルート直下に配置
  - `plugins/doc-advisor/` 配下を repo ルート直下に展開 (`skills/`, `agents/`, `scripts/`)
  - プラグインランタイム文書を `workflows/` (orchestrator / 手順) と `formats/` (スキーマ) に分離
  - `tests/` を単一プラグイン構成にフラット化（`scripts/`, `skills/`, `integration/`）
- SKILL.md / agent / workflow 内の `${CLAUDE_PLUGIN_ROOT}/docs/` 参照を `/workflows/` または `/formats/` に更新
- `.version-config.yaml` を doc-advisor 単独構成に簡素化
- **Embedding 検索機能を廃止し、doc-advisor を ToC 検索専用に戻す** (Issue #13)
  - `query-rules` / `query-specs` SKILL から `--toc` / `--index` / `auto` の mode フラグを全廃止。デフォルトは ToC のみ
  - Embedding 実装は今後 query-docs プラグイン側で再構築予定 (`BlueEventHorizon/bw-cc-plugins#77`)

### Removed

- forge / anvil / doc-db に紐づくドキュメント・テスト・スキルを削除
- 旧 setup.sh ベースの配布物 (`test_claude_setup/`, `codex_skill_set/`, `codex_install_profiles/` 等) を削除
- `.claude-plugin/marketplace.json`（単一プラグインのため不要）
- `meta` シンボリックリンク、`.git_information.yaml` (anvil 用)
- **Embedding 関連の scripts / tests / workflow / specs を削除** (Issue #13)
  - Scripts: `scripts/embed_docs.py`, `scripts/search_docs.py`, `scripts/embedding_api.py`, `scripts/code_index/`（空）
  - Tests: `tests/scripts/test_embed_docs.py`, `test_search_docs.py`, `test_embedding_api.py`, `test_evaluate_toc_results.py`, `tests/golden_set/`（embedding 検索品質評価用）, `tests/skills/test_query_auto_redefinition.py`, `tests/skills/test_query_output_dir_e2e.py`
  - Workflow: `workflows/query_index_workflow.md`
  - Specs: `docs/specs/doc-advisor/design/DES-006_semantic_search_design.md`, `DES-007_unified_api_key_reference_design.md`, `docs/specs/doc-advisor/requirements/FNC-004_unified_api_key_reference_spec.md`, `technical_research_report.md`, `technical_qa.md`
- `.gitignore` / `dprint.jsonc` から embedding index 出力先 (`.claude/doc-advisor/index/`) を削除（不要になったため）

## [0.2.6] - 2026-05-16

- **fix**: query-specs / query-rules SKILL.md から `context: fork` 等の subagent 起動 frontmatter を削除し、`/doc-advisor:query-specs` が "initializing" で停止する不具合を解消。SKILL 本体を直接実行する方式に変更

## [0.2.5] - 2026-05-15

- **feat**: API KEY 参照を `OPENAI_API_DOCDB_KEY` 優先 + `OPENAI_API_KEY` フォールバックに統一。`embedding_api.get_api_key()` を新設
- **feat**: query-specs / query-rules SKILL.md に mode=auto の subagent 内完結フローを実装
- **docs**: SKILL.md の API KEY 関連エラー文言を `OPENAI_API_DOCDB_KEY` / `OPENAI_API_KEY` 併記に統一

## [0.2.4] - 2026-05-12

- **fix(BR-001)**: スクリプトのエラーメッセージからスラッシュコマンド形式を除去し、環境非依存な表記に変更（5 箇所）

## [0.2.3] - 2026-05-08

- **docs**: 設計 DES-026 追加、heading-chunk ハイブリッド検索プラグインの要件定義書追加 (#33)
- **chore**: create-code-index / query-code スキルと関連コードを削除
- **refactor**: index の更新

## [0.2.2] - 2026-04-28

- **fix(query-rules / query-specs)**: fork されたサブエージェントが SKILL.md 本文を実行指示と誤読し、`Skill(query-*)` を tool_use 経由で無限再帰起動するバグを修正。SKILL.md 冒頭に「これはあなた自身への実行指示書」「query-* を Skill で呼んではいけない」を明記

## 0.2.1 以前

要約のみ。詳細は git log を参照。

- **0.2.1**: ToC 検索ワークフローの output_dir 未対応バグを修正
- **0.2.0**: query-rules / query-specs を統合し、ToC / Index / ハイブリッドの 3 モードに対応
- **0.1.7**: resolve_config_path のバグ修正、`auto_create_toc.py` を品質評価により排除
- **0.1.6**: `output_dir` による ToC / Index 出力パスの動的切り替えをサポート
- **0.1.5**: セマンティック検索機能（OpenAI Embedding API）を追加
- **0.1.x 初期**: ToC キーワード検索の基本機能を整備
