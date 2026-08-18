# Changelog

All notable changes to doc-advisor are documented in this file.

> このリポジトリは `bw-cc-plugins` マーケットプレイス（forge / anvil / doc-advisor / doc-db の 4 プラグイン集）から `doc-advisor` を分離したものです。0.3.0 より前の詳細な変更履歴は git log および旧リポジトリ `BlueEventHorizon/bw-cc-plugins` を参照してください。

## [0.4.9] - 2026-08-18

### Fixed

- **`--key` を省略したまま `--paths` / `--dirs` / `--exclude` を渡すと、対象指定が黙って捨てられ project root 全体が索引される欠陥を修正**。単体モードへ入る書き方は `--all` の明示と `--key` の省略の2つがあり、既存の併用拒否ガードは `--all` だけを見ていたため `--key` 省略の経路が素通りしていた。判定を `_is_single_mode()`（`--all` または `--key` 省略）に統一した
- **`--paths-file` と `--dirs` / `--paths`（およびそれぞれの JSON 形）の併用が黙って捨てられていた欠陥を修正**。`--paths-file` を優先して他方を無視していたため「指定したのに索引されない文書がある」状態になっていた。`UNSUPPORTED_ARG` で拒否するようにした
- `toc-updater` Agent が不要に `advisor` ツールを呼び出していたのを抑止する制約を追加

## [0.4.8] - 2026-08-14

### Fixed

- **ToC からフロントマターへの転記が値を壊していた欠陥を修正**。`toc.yaml` の読み側は引用符を外すだけでエスケープを復元しないため、`"` を含むメタデータは原本へ余分なバックスラッシュ付きで書かれ、原本側は正しい逆変換で読まれるので**索引サイクルごとにバックスラッシュが倍加**していた（実測で 1 → 3 → 7 → 15）
  - エスケープの往復を成立させるのではなく、往復の必要をなくす方針を採った。メタデータ 5 フィールドの**使える文字を値域として機械的に強制**し、値域外の文字は「意味を保つ代替が存在するか」で扱いを分ける。`"` / 改行・CR・タブ / 先頭末尾の `'` は書き込みの入口で変換し、代替の無いバックスラッシュは拒否する。変換したことは `normalized_fields` と `warnings` で必ず報告する
  - 内容を選べない値（pending の `_meta.error_message` に入る例外文字列）は入口で正規化する。`FileNotFoundError: [Errno 2] ... 'docs/x.md'` が読み戻しで末尾のアポストロフィを失う破損も解消した
- **`--exclude` が黙って無視され、除外を指定した原本まで書き換わる欠陥を修正**。除外を「`--dirs` 展開時の除外」として実装していたため、`--dirs` を伴わない指定（明示 `--paths` のみ / `--from-toc` の ToC 全件）では適用されず、とくに `apply --from-toc --exclude` は対象 0 件から全件フォールバックへ落ちて**指定と正反対の結果**になっていた
- **`--dirs` の展開結果が 0 件のとき `--from-toc` が ToC 全件へ書き込む欠陥を修正**。全件フォールバックを「対象が指定されていないとき」に限定した
- **`apply --from-toc` が読めない対象を `status: ok` として報告する欠陥を修正**。`plan` が `partial` を返す同じ状況で `apply` が `ok` を返す非対称を解消した
- **`--exclude` に絶対パスを渡すと CLI が traceback で落ちる退行を修正**。root 配下に解決できない入力は除外判定の対象にせず、不正なパスの分類を下流へ委ねる。**異常入力でも単一 JSON を返すこと**を両入口の契約テストで固定した
- `apply` の対象指定（`--dirs` / `--paths` / `--exclude`）を `--entries-file` / `--entries-json` と併用した場合に黙って無視していたのを、`UNSUPPORTED_ARG` で拒否するようにした

### Changed

- **`--exclude` の適用点を「確定した対象集合」へ移した**。対象の出どころ（`--dirs` 展開 / 明示 `--paths` / ToC 全件）を問わず同じ 1 箇所で効く。落とした件数は `warnings` に出る
  - あわせて `expand_dirs.py` から**ユーザー除外の機構を削除**した（`--exclude-json` 引数と引き回しごと）。渡さないだけでは同じ規則の適用点が 2 つ残るため。システム固定除外の適用は従来どおり継続する
- **パスの基準を入口で 1 つに固定した**。`index_docs` と `fm_run` の `main()` で cwd を project root へ揃える。「project root と結合して開く」作法と「渡されたパスをそのまま開く」作法が 1 回の実行で交差すると、照合した対象と書き込む対象が別ファイルになりうるため
- `apply` の `counts` を `plan` と同じ形に揃えた。`needs_ai` / `skipped` / `unreadable` を常に出し、`total` を「対象として確定した件数」に統一。`warnings` / `extra` も空のときキーを落とさない

### Documentation

- DES-005 に §4.2.1（パスの基準を入口で 1 つに固定する）と §4.2.2（除外は確定した対象集合へ適用する）を新設。§4.1 のモジュール一覧・CLI オプション表へ `fm_from_toc.py` / `fm_run.py` を追加し、依存方向規範を DES-008 §6.1 の一方向依存へ整合させた
- DES-008 に値域の規範（前提ではなく検査項目であること、変換と拒否の切り分け）を追加。§8.2「既知の制約」の誤った断定を事実へ訂正した
- `toc_format.md` に `Character Domain` を追加。使える文字の値域と、`toc.yaml` の書き込み点に検証を置いていない理由を明記した
- `write-frontmatter` SKILL の出力契約に `targets[].toc_violations` を追加し、転記側 apply の `--paths` を必須表記へ改めた（省略すると承認範囲を超えて書き込まれるため）

## [0.4.7] - 2026-08-04

### Added

- 文書に ToC メタデータをフロントマターとして埋め込む仕組みを追加。信頼できるフロントマターを持つ文書は `toc-updater` Agent を起動せず**転記**だけで索引でき、大量文書のコールドリードを省略できる (REQ-006 / DES-008)
  - フロントマターを書き込むスキル `write-frontmatter` を新設。AI が本文からメタデータを作り、承認を得てから原本へマージ書き込みする（整形の後に `body_hash` を打刻）。既存キーと他ツールの `type` 標識は保持する
  - 信頼判定は `type` に `doc-advisor` を含むこと・5 フィールドが規約に適合すること・`body_hash` が現在の本文と一致することの全成立（all-or-nothing）。1 つでも欠ければ従来の AI 抽出へフォールバックする
  - `index-docs` は ToC 生成の完了後に AI 抽出で索引された文書を提示し、承認された対象のみ `write-frontmatter` へ引き渡す。索引の実行で原本が書き換わることはない
- `index-docs` / `write-frontmatter` が呼ぶ script をラッパー 1 本に集約。AI に残る責務を「Agent の起動」と「判断」だけにした (DES-005 §4.1.1 / DES-008 §6.5)
  - `index_docs.py` が段階判定・ディレクトリ展開・転記・並列度の計算・claim・統合を内部で配管し、次に何をするかを `action`（`dispatch` / `wait` / `confirm` / `done` / `error`）で返す。呼び出し側は同じコマンドを繰り返すだけでよく、初回と再開を区別しない
  - `fm_run.py` の `plan` / `apply` が対象の絞り込みと書き込み後の信頼判定までを行う。件数の比較が呼び出し側に残らない

### Changed

- **root 外を指す symlink を既定で拒否する挙動を撤去した。** `--all` 以外のすべての対象指定（`--dirs` / `--dirs-json` / `--paths` / `--paths-json` / `--paths-file`）は、越境 symlink であっても索引し、解決先の実体パスと件数を warning で提示する (REQ-001 §6.1a / NFR-N06)
  - 外部の仕様書を symlink で取り込む構成は実運用で使われており、その経路の呼び出し元（forge）は index-docs を 1 回だけ呼ぶため確認に答えられない。既定で拒否すると索引が動かないまま理由も伝わらなかった
  - 索引するか否かの決定は呼び出し元に属する。安全性は禁止ではなく透明性（何を索引したかの提示）で担保する
  - 確認を求めるのは project root 全体を走査する `--all` のみ。この経路では誰も対象を渡していない
- SKILL の引数仕様の正本を設計書（DES-005 §10.1 / DES-008 §8.1）へ移した。配布物の SKILL.md だけが正本だと、方式変更で全面書き換えしたときに上位層との契約が消えても突き合わせる相手がいない

### Fixed

- `index-docs` が `--dirs-json` / `--exclude-json` を受け付けなくなっていた問題を修正。これらを渡して index-docs を 1 回だけ呼ぶ上位層（forge の `update-db-rules` / `update-db-specs` / `query-db-rules` / `query-db-specs`）で索引が動かなくなっていた
- `fm_write` が metadata の値域（文字数・件数・空・型）を書き込み**前**に検証するようにした。従来は書ける値の集合が信頼される値の集合に収まらず、script が書いた直後の文書が信頼できない状態になりえた
- 充填エラーの再試行が claim/lease に乗るようにした。`error_pending` をそのまま投入すると claim が効かず、同じコマンドの再実行で二重投入が起きていた
- `--paths-file` に `{"paths": [...]}` を渡した場合に、配列そのものを渡すよう案内するエラーを返すようにした（受け付ける形は従来どおり配列のみ）

## [0.4.6] - 2026-07-30

### Added

- ToC の鮮度を確認する read-only スキル `check-toc` を追加。指定 key の ToC が「そのまま検索に使える（`fresh`）」か「作り直しが必要（`stale`）」かを JSON で返す。索引の生成・更新・削除は行わない (REQ-005 / DES-009)
  - 答えは `freshness` の 2 値のみ。ToC が存在しない場合も `stale` に含め（後続処理が鮮度超過と同一のため）、不在・鮮度超過・`generated_at` 不正の区別は補助情報 `reason`（`missing` / `outdated` / `generated_at_invalid` / `generated_at_future`）で返す
  - `--max-age <秒>` を必須とし、鮮度閾値の所有者を呼び出し側に固定した（本スキル側に既定値を持たない）
  - 判定は `toc.yaml` の `metadata` 読み取りだけで完結する（`docs` セクションは解析しない）
- JSON 出力契約の `error_code` に `INVALID_MAX_AGE`（`--max-age` が未指定・非整数・0 以下）と `TOC_READ_ERROR`（`toc.yaml` を読めない）を追加

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
