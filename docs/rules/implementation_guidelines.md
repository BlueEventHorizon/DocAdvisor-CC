# 実装ガイドライン

プラグインのスクリプト（Python / Bash）および SKILL.md 実装時のルールを定義する。

---

## スクリプト言語の選定 [MANDATORY]

処理内容に応じて Python または Bash を選定する。

| 条件                                           | 言語   | 理由                                          |
| ---------------------------------------------- | ------ | --------------------------------------------- |
| データ変換・パース・YAML/JSON 操作             | Python | 構造化データ処理に強い                        |
| 外部コマンド呼び出し・ファイル操作・パイプ処理 | Bash   | シンプルで高速。Python 起動オーバーヘッドなし |
| 両方の特性が必要                               | Python | Bash の複雑化を避ける                         |

**Python スクリプトは標準ライブラリのみ使用する**（外部依存禁止）。
**Bash スクリプトは外部コマンド（codex, git, curl 等）の呼び出しに使用してよい。**

---

## テスト必須 [MANDATORY]

`plugins/` 配下の Python スクリプトにはテストが必須。Bash スクリプトは手動テストまたは統合テストで確認する。

### 対象と例外

| 対象                    | テスト必須         | 理由                                           |
| ----------------------- | ------------------ | ---------------------------------------------- |
| `plugins/` 配下の `.py` | 必須               | プラグインとして配布されるコード               |
| `plugins/` 配下の `.sh` | 推奨（統合テスト） | 外部コマンド依存のため単体テスト困難な場合あり |
| SKILL.md                | 例外               | AI の振る舞いを記述するもので自動テスト困難    |
| `.claude/` 配下         | 対象外             | ローカルスキル・プロジェクト固有スクリプト     |

### テストの配置

`tests/` にプラグイン名・スキル名で分類して配置する:

```
tests/
├── common/                 # プラグイン横断（マニフェスト整合性等）
├── forge/
│   ├── review/             # plugins/forge/skills/review/scripts/ のテスト
│   └── scripts/            # plugins/forge/scripts/ のテスト
└── {plugin}/               # 新プラグイン追加時も同構造
```

命名規則: `test_{module}.py`（例: `test_session_manager.py`）

### テスト実行

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

---

## SKILL.md にインラインスクリプトを書かない [MANDATORY]

処理ロジックを SKILL.md 内にインラインで記述してはならない。

### 理由

AI が SKILL.md 内のスクリプトを解釈して実行する際、コードを勝手に改変・省略して失敗するリスクがある。独立したスクリプトファイルであれば、AI はそのまま実行するだけで済む。

### 正しいパターン

処理ロジックは独立したスクリプトファイル（Python または Bash）として実装し、SKILL.md からはそのスクリプトを呼び出す。

```markdown
# ❌ NG — SKILL.md 内にロジックを記述

以下の Python コードを実行してデータを集計する:

    import json
    data = json.load(open('plan.yaml'))
    # ... 50行のロジック ...

# ✅ OK — 外部スクリプトを呼び出す

以下のスクリプトを実行して指摘事項を抽出する:

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_review_findings.py" {review_md} {plan_yaml}
```

### スクリプトの配置

| 配置先                             | 用途                       |
| ---------------------------------- | -------------------------- |
| `plugins/{plugin}/skills/{skill}/` | スキル固有のスクリプト     |
| `plugins/{plugin}/scripts/`        | プラグイン共通のスクリプト |

SKILL.md からの参照には `${CLAUDE_SKILL_DIR}` または `${CLAUDE_PLUGIN_ROOT}` を使用する。

---

## 設計書の保守 [MANDATORY]

forge 内蔵ルール（`/forge:query-forge-rules` → `design_principles_spec.md`「設計書の保守」）に従う。

本リポジトリ固有の補足:

- ADR の配置先: `docs/specs/{plugin}/design/ADR-{NNN}_{topic}.md`

---

## 使わないコードは削除する [MANDATORY]

非推奨マーカーやコメントアウトで残さない。残存コードは勘違いの原因になる。

- 削除の経緯はコミットメッセージへの記載で十分（CHANGELOG には `/forge:update-version` 実行時に git log から自動反映される）
- 「将来使うかもしれない」は削除の理由にならない。git 履歴から復元できる
- テストファイルも本体と同時に削除する

---

## AI が解釈すべき入力にスクリプトパーサーを使わない [MANDATORY]

ユーザー入力（コマンド引数等）は自然言語が混在するため、リジッドなトークンパーサーではなく AI が直接解釈する。

- スクリプトは構造化データ（YAML/JSON）の処理に限定する
- 引数が不足・曖昧な場合は AskUserQuestion で補完する
- コマンド構文は SKILL.md に記載し、AI がそれを参照して意図を汲み取る

---

## バージョン関連ファイルの編集禁止 [MANDATORY]

feature PR / fix PR / refactor PR 等の通常の作業 PR で、バージョン関連ファイルを編集してはならない。
バージョン更新の単一責任は `/forge:update-version` にあり、AI および開発者が個別 PR で先回りバンプしてはならない。

### 編集禁止対象

| 対象                                        | 内容                                              |
| ------------------------------------------- | ------------------------------------------------- |
| `plugins/*/.claude-plugin/plugin.json`      | 各プラグインの `version` フィールド               |
| `.claude-plugin/marketplace.json`           | 各プラグインエントリの `version` フィールド       |
| `README.md` / `README_ja.md` のバージョン表 | プラグインバージョン記載行（数値変更を伴う diff） |
| `CHANGELOG.md` 等の変更履歴ファイル         | 全エントリ（追加・修正・削除いずれも禁止）        |
| git tag（`v*` / `<plugin>-v*`）             | 作成・移動・削除いずれも禁止                      |

### 例外

以下に限り編集してよい:

- 新規プラグイン追加時の初期値記述（`0.0.1` 等の新規エントリ作成。既存値の変更ではないため）
- `/forge:update-version` を明示起動した場合（唯一の正規ルート）
- 本ルール文書自体の改訂

### 唯一の正規ルート

バージョン更新は `/forge:update-version` のみが担う:

- Step 3.5: `current > main` 検出時に二重バンプ確認 → **1 リリース = 1 バンプ**
- Step 5: git log から CHANGELOG エントリを自動生成 → PR ごとの CHANGELOG 編集は二重作業 + 競合源

詳細は `docs/specs/forge/design/DES-023_version_management_workflow_design.md` を参照。

### 理由

| 理由                           | 説明                                                                    |
| ------------------------------ | ----------------------------------------------------------------------- |
| リリース単位の一意性           | 誰がいつ何をまとめてリリースするかを `/forge:update-version` に集約する |
| CHANGELOG 自動生成との衝突回避 | git log 由来の自動生成と手動編集が二重化すると整合性が崩れる            |
| 並行 PR の merge conflict 回避 | 複数 PR が同時に同じ version 行を編集すると衝突が頻発する               |

**NEVER** feat / fix / chore コミットの流れで AI が自発的にバージョンをバンプしてはならない。
**MUST** バージョン更新が必要と判断したら、ユーザーに `/forge:update-version` の明示起動を提案する。
