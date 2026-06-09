# 開発ガイド

`doc-advisor` プラグイン本体を**このリポジトリで開発・デバッグ**するための手引き。

- ユーザー向けのインストール・使い方は [`README.md`](README.md)
- AI（Claude Code）向けのリポジトリ規則は [`CLAUDE.md`](CLAUDE.md)
- プロジェクトルール（コーディング・文書記述など）は `docs/rules/`

## 前提

- 外部依存なし。Python 3.9 以上の標準ライブラリのみで動作する
- フォーマッタは [dprint](https://dprint.dev/)（設定は `dprint.jsonc`）
- このリポジトリは **marketplace → plugin → skill の 3 層構成**。リポジトリルートに `.claude-plugin/marketplace.json`（マーケットプレイス、`source: "./plugins/doc-advisor"`）、プラグイン実体は `plugins/doc-advisor/`（`.claude-plugin/plugin.json`）に置く

## ローカル開発・デバッグ

ローカルのリポジトリを Claude Code に読み込ませる方法は 3 通りあり、目的で使い分ける。

| 方式                        | 用途                                        | 恒久登録への影響 |
| --------------------------- | ------------------------------------------- | ---------------- |
| A. `--plugin-dir`           | skill / script の中身を編集しながらデバッグ | 汚さない         |
| B. ローカル marketplace add | `marketplace add → install` フローの検証    | 汚す（要後始末） |
| C. GitHub 経由              | 配布物の最終確認（本番フロー）              | 汚す（要後始末） |

### 方式A: `--plugin-dir`（中身のデバッグに推奨）

セッション起動時にプラグインディレクトリを直接読み込む。

```bash
claude --plugin-dir ~/path/to/DocAdvisor/plugins/doc-advisor
```

- キャッシュを介さずディレクトリ実体を直読みする
- 恒久登録（`~/.claude/plugins/known_marketplaces.json` / `installed_plugins.json`）を汚さない
- 現在チェックアウト中のブランチの内容で動く（push 不要）
- 編集を反映するにはセッションを再起動する

中身（`plugins/doc-advisor/` 配下の `skills/*/SKILL.md`、`scripts/`、`agents/`）を編集しながら試す用途には、これが最も手間が少ない。

### 方式B: ローカルパスをマーケットプレイス登録

`marketplace add` はローカルディレクトリパスも受け付ける。`marketplace add → install` のフロー全体を、GitHub に push する前に検証できる。

```bash
claude plugin marketplace add ~/path/to/DocAdvisor
claude plugin install doc-advisor@DocAdvisor
```

挙動が 2 層に分かれる点に注意する。

- **マーケットプレイス層**: ローカルリポジトリ実体を直接参照する（`installLocation` がリポジトリそのもの）。現在チェックアウト中のブランチの `marketplace.json` を読む
- **プラグイン本体**: install 時に `~/.claude/plugins/cache/` へコピーされ、その時点の commit がスナップショットされる。**編集はホットリロードされない**

したがって編集やブランチ切替を反映するには `claude plugin marketplace update DocAdvisor` と再 install が必要。中身を高速に試したいなら方式A を使う。

GitHub 経由（方式C）はデフォルトブランチ固定なのに対し、この方式は**任意のブランチ**の内容で install テストできる。

### 方式C: GitHub 経由（本番フロー）

ユーザーが実際に使う配布フロー。最終確認に用いる。

```text
/plugin marketplace add BlueEventHorizon/DocAdvisor
/plugin install doc-advisor@DocAdvisor
```

- ソースは GitHub の**デフォルトブランチ（main）固定**
- `marketplace.json` が main に存在することが前提（無いと `marketplace add` が失敗する）

### リロードと有効化

```bash
# 有効化済みプラグインの再読込（Claude Code 内）
/reload-plugins

# 無効化したプラグインを再有効化
claude plugin enable doc-advisor@DocAdvisor
```

### デバッグ時の注意: uninstall の巻き込み

`claude plugin uninstall <plugin>@<marketplace>` は、`@<marketplace>` 指定が効かず**同名プラグインを巻き込んで削除する**場合がある（Claude Code 2.1.159 で観測）。複数マーケットプレイスに同名プラグインが存在するときは、実行前に `~/.claude/plugins/installed_plugins.json` で対象を確認する。恒久登録を汚さない方式A（`--plugin-dir`）を使えば、この副作用自体を避けられる。

## マニフェスト検証

```bash
claude plugin validate .                       # marketplace カタログ（リポジトリルート）
claude plugin validate ./plugins/doc-advisor   # プラグインマニフェスト
```

3 層構成（`marketplace.json` の `source: "./plugins/doc-advisor"`）のため、marketplace カタログはルート、プラグイン本体は `plugins/doc-advisor/` をそれぞれ検証する。

## テスト

`plugins/doc-advisor/scripts/` 配下の Python スクリプトにはテストが必須。SKILL.md はテスト困難なため例外、`.claude/` 配下のローカル skill は対象外。

```bash
# 一括実行
python3 -m unittest discover -s tests -p 'test_*.py' -v

# 特定モジュールのみ
python3 -m unittest tests.scripts.test_toc_utils -v
```

### 検索品質テスト（ゴールデンセット）

検索品質（FN/FP）の評価用ゴールデンセットは、リポジトリ外のローカルワークスペース `meta/DocAdvisor/golden_set_test/`（リポジトリの `meta` symlink 経由・gitignore 対象）に置く。**手順の正本は同ワークスペースの `test_manage/RUNBOOK.md`** に集約し、ここでは方式の要点と入口だけを示す（手順の二重管理を避ける）。

方式は **「別 key 隔離 + 結果 diff」**。本物の ToC を一切上書きしない:

- **project_root = ワークスペース自身**にして測る。`golden_set_test/` を project_root にすれば `rules/` `specs/` は素のサブディレクトリになり symlink 越境は起きず、ToC store もワークスペース内に隔離される。呼び出し単位で `CLAUDE_PROJECT_DIR=<ワークスペース絶対パス>` をインライン指定し、**セッションの env は汚さない**。
- 別条件（guidance 等）を測るときだけ、reference（key=`rules`/`specs`）を残したまま**テスト専用 key**（`gs-rules`/`gs-specs`）で index を生成し、後始末は `remove_toc.py --key …`。
- **LLM とスクリプトの境界**: index 構築（toc-updater agent）と query-docs 実行は LLM 工程。採点（FN/FP・カテゴリ別集計）と baseline 対比は決定論で、`test_manage/score.py`（`report` / `diff`）が担う。

入口:

- クエリ定義: `test_manage/queries.yaml`（パス基準は同ファイル冒頭コメント）
- 採点・対比: `test_manage/score.py`（使い方は RUNBOOK.md）
- 測定結果: `test_manage/results/`

> `python3` が失敗する環境では `/opt/homebrew/bin/python3` を使う。

## フォーマット

JSON / TOML / Markdown / YAML は dprint で整形する。

```bash
dprint fmt      # 整形を適用
dprint check    # 差分チェックのみ
```

## リリース・配布

- **バージョンの単一情報源**: `.claude-plugin/plugin.json` の `version`。`marketplace.json` の plugin entry では `version` を省略し、二重管理を避ける
- **バージョン更新**: `.version-config.yaml` と `update-version` スキルで一括更新する
- **ブランチ運用**: develop で作業し main へマージする。`marketplace.json` は**デフォルトブランチ（main）に存在**しないと GitHub 経由インストールが動かない
- **リリースタグ**: `claude plugin tag` は `plugin.json` と marketplace entry の整合を検証したうえでタグを作成する

## MCP 補助（任意）

開発補助の MCP サーバー接続を Makefile に用意している。

```bash
make connect_gemini      # gemini-cli MCP を接続
make connect_serena      # serena MCP を接続（要 SERENA_PATH）
make help                # 全ターゲットを表示
```

## 関連ドキュメント

- `README.md` / `README_en.md` — ユーザー向けガイド
- `CLAUDE.md` — AI 向けリポジトリ規則
- `docs/rules/document_writing_rules.md` — 文書記述ルール
- `docs/rules/implementation_guidelines.md` — 実装ガイドライン
- `docs/specs/base/` — 基盤仕様（要件・設計）
