# Changelog

All notable changes to doc-advisor are documented in this file.

> このリポジトリは `bw-cc-plugins` マーケットプレイス（forge / anvil / doc-advisor / doc-db の 4 プラグイン集）から `doc-advisor` を分離したものです。0.3.0 より前の詳細な変更履歴は git log および旧リポジトリ `BlueEventHorizon/bw-cc-plugins` を参照してください。

## [0.4.5] - 2026-07-11

### Fixed

- `query-worker` が ToC のパスを稀に絶対パスとして返す問題を修正。相対パス使用を明示指示し、呼び出し元（dispatcher 等）のファイルアクセス・表示が壊れないようにした

## [0.4.4] - 2026-06-13

### Changed

- ToC ストアのパスを `.claude/doc-advisor/toc` から `.claude/.doc-advisor/toc` へ変更。Unix の dot prefix 慣習に従い、プラグインが機械生成する内部データをユーザー設定ファイルと視覚的に区別する (Issue #33)
- プラグイン実体を `plugins/doc-advisor/` へ移し、marketplace（`.claude-plugin/marketplace.json`） → plugin（`plugins/doc-advisor/.claude-plugin/plugin.json`）→ skill の 3 層 marketplace 構成に再編
- `plugins/doc-advisor/workflows/` 内のファイル名を対称な役割名に統一

### Fixed

- サブディレクトリ移動後のバージョン整合性を回復

## [0.4.3] - 2026-06-08

### Added

- `index-docs` の `--dirs-json` にグロブパターン展開を追加（`docs/specs/**/design/` など任意深さのディレクトリ／Markdown を直接マッチ）(FR-N09-8)
- `index-docs` の充填処理を連続ディスパッチ化（claim/lease + sliding-window）し、Agent の遊休を減らして並列効率を改善

### Changed

- `--exclude-json`（ユーザー除外）のマッチ方式をシステム固定除外 `should_exclude` と統一。裸名は任意階層のディレクトリ名に完全一致、`/` 含みは project root 起点（root-anchored）のセグメント境界マッチとなり、forge 等の上位層が裸名除外をそのまま転送できるようになった。設計書（DES-004）・SKILL・コメントも追従 (Issue #30)
- `index-docs` の並列充填を高速化（実効並列度の引き上げ・規約圧縮・限定バッチング）。検討経緯と速度実測（A/B・公式マルチエージェント不採用理由）を ADR-006 に記録

### Fixed

- `plugin.json` のスキル discovery を修復し、廃止済みのローカル skill を除去

## [0.4.2] - 2026-06-06

### Changed

- `query-docs` を継承型 dispatcher + read-only worker 構成へ再設計。`context: fork` 隔離が Skill ツール起動時に `$ARGUMENTS` を欠落させる既知制約（anthropics/claude-code#34164）を回避し、安全境界を read-only な `query-worker` カスタム Agent への分離へ移した (Issue #21 / ADR-002 改訂)
- `index-docs` の作業ディレクトリ状態を script 化（`--work-status`）し、AI による手動列挙を排除。SKILL を `--work-status` に整合させ、残存していた手動導出を除去・`error_pending` を文書化

### Added

- 外部 symlink の明示的同意による索引を許可 (NFR-N06)

### Fixed

- merge のチェックサム書き込みを新規充填文書のみに限定し、stale-pin を防止
- 充填エラー時の silent merge をブロック
- ディレクトリ展開時に外部 symlink を保持
- `prepare_toc` の `--dirs-json` 誤用をガードし、ツール参照を Task → Agent にリネーム

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
