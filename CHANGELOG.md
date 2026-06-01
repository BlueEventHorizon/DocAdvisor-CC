# Changelog

All notable changes to doc-advisor are documented in this file.

> このリポジトリは `bw-cc-plugins` マーケットプレイス（forge / anvil / doc-advisor / doc-db の 4 プラグイン集）から `doc-advisor` を分離したものです。0.3.0 より前の詳細な変更履歴は git log および旧リポジトリ `BlueEventHorizon/bw-cc-plugins` を参照してください。

## [0.4.1] - 2026-06-02

### Added

- `index-docs` に単体モード `--all`（予約 key `all`）を追加し、project root 以下の全 Markdown を一括索引可能に
- `index-docs` に `--dirs-json`（ディレクトリ指定）を追加し、ディレクトリ配下の Markdown を展開して索引可能に
- ローカル開発用 skill（配布対象外）`index-rules` / `index-specs` / `query-rules` / `query-specs` を追加（key + path I/F のドッグフーディング・forge 上位層のデモ）

### Changed

- ToC ストアのディレクトリ構造を簡素化（`keys/` 階層と `meta.yaml` を廃止し store_dir パスを短縮）

### Fixed

- `query-docs` のエラーを修正
- `.version-config.yaml` の `tag_format` を既存タグ運用（`v` 接頭辞なし）に整合

## [0.4.0] - 2026-06-01

### Added

- key + path インターフェースによる ToC Provider 基盤 `toc_store.py` を新設。`key`（任意文字列）と project-root-relative の `paths` で ToC を決定的に生成・参照する方式へ移行 (Issue #15)
- embedding 撤去・doc_structure 残存防止の回帰テスト、および GitHub Actions ワークフローを追加

### Changed

- ToC の生成・検索インターフェースを key + path 方式へ全面移行し、script 層・SKILL・agent を新方式に一本化 (Issue #15)
- 配布スキルを `index-docs` / `query-docs` の 2 種へ統合（旧 `create-rules-toc` / `create-specs-toc` / `query-rules` / `query-specs` / `setup-doc-structure` を置換）
- `.doc_structure.yaml` を前提としない汎用 ToC Provider へ一般化。`key` の分類（rules / specs 等）を解釈せず、与えられた key と paths に対して決定的に動作する

### Removed

- OpenAI Embedding API によるセマンティック検索を撤去し、ToC-only 構成へ復帰 (Issue #13)
- `index_file` 設定・embedding 関連キーワード・dead code の `grep_docs.py` を削除
- doc_structure 概念をランタイム配布物（SKILL / workflow / formats / agent / README）から撤去 (Issue #15 フェーズ④)

## [0.3.0] - 2026-05-28

### Changed

- `bw-cc-plugins` から分離し、Claude Code 公式仕様の単一プラグインリポジトリへ再構成
  - `.claude-plugin/plugin.json` を repo ルート直下に配置
  - `plugins/doc-advisor/` 配下を repo ルート直下に展開 (`skills/`, `agents/`, `scripts/`)
  - プラグインランタイム文書を `workflows/` (orchestrator / 手順) と `formats/` (スキーマ) に分離
  - `tests/` を単一プラグイン構成にフラット化（`scripts/`, `skills/`, `integration/`, `golden_set/`）
- SKILL.md / agent / workflow 内の `${CLAUDE_PLUGIN_ROOT}/docs/` 参照を `/workflows/` または `/formats/` に更新
- `.version-config.yaml` を doc-advisor 単独構成に簡素化

### Removed

- forge / anvil / doc-db に紐づくドキュメント・テスト・スキルを削除
- 旧 setup.sh ベースの配布物 (`test_claude_setup/`, `codex_skill_set/`, `codex_install_profiles/` 等) を削除
- `.claude-plugin/marketplace.json`（単一プラグインのため不要）
- `meta` シンボリックリンク、`.git_information.yaml` (anvil 用)

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
