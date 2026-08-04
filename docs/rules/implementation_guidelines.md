---
type: doc-advisor
title: Implementation Guidelines
purpose: "Defines the rules for implementing plugin scripts and SKILL.md: language selection, mandatory tests, the inline-script ban, design doc sync, distributed interface changes, and version file edits."
content_details:
  - Criteria for choosing Python or Bash by workload (Python for data transformation and YAML/JSON handling, Bash for invoking external commands)
  - Python scripts use the standard library only; external dependencies are forbidden
  - Tests are mandatory for .py files under scripts/; SKILL.md is exempt because AI behavior is hard to test automatically; .claude/ is out of scope
  - Test placement under tests/scripts, tests/skills, tests/integration and the test_{module}.py naming convention
  - Why inline scripts are banned in SKILL.md (the AI rewrites or omits the code and fails), the correct pattern of calling a standalone script, and where scripts live (skills/{skill}/ versus scripts/) referenced via CLAUDE_PLUGIN_ROOT or CLAUDE_SKILL_DIR
  - Design documents are updated in the same PR as the code, and ADRs live under docs/specs/base/design/
  - Distributed interfaces are contracts with upper layers - grep callers in the other repository before removing an argument, read git diff after a full Write overwrite, and name each dropped argument in the plan
  - Unused code is deleted outright, including its tests, rather than left as deprecation markers or commented-out blocks
  - Never apply a rigid token parser to input the AI is meant to interpret; fill gaps with AskUserQuestion instead
  - Ordinary feature/fix/refactor PRs must not edit plugin.json version, README version lines, CHANGELOG entries, or git tags
applicable_tasks:
  - Choosing the implementation language for a new script
  - Adding tests and deciding where to place them
  - Writing a script invocation from SKILL.md
  - Changing or removing a SKILL argument or a distributed script CLI
  - Updating design documents and ADRs alongside code
  - Judging whether a version or CHANGELOG edit is allowed in the current PR
  - Removing code that is no longer used
keywords:
  - standard library only
  - inline script ban
  - tests/scripts
  - test_{module}.py
  - CLAUDE_PLUGIN_ROOT
  - design doc maintenance
  - backward compatibility
  - CHANGELOG
  - plugin.json
  - ADR
body_hash: sha256:88250c28b0aca2764a12470de89cc98b03d991d9d45970a853e6ff50f3029e32
---

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

`scripts/` 配下の Python スクリプトにはテストが必須。Bash スクリプトは手動テストまたは統合テストで確認する。

### 対象と例外

| 対象                    | テスト必須         | 理由                                           |
| ----------------------- | ------------------ | ---------------------------------------------- |
| `scripts/` 配下の `.py` | 必須               | プラグインとして配布されるコード               |
| `scripts/` 配下の `.sh` | 推奨（統合テスト） | 外部コマンド依存のため単体テスト困難な場合あり |
| SKILL.md                | 例外               | AI の振る舞いを記述するもので自動テスト困難    |
| `.claude/` 配下         | 対象外             | ローカルスキル・プロジェクト固有スクリプト     |

### テストの配置

配布物（`plugins/doc-advisor/`）に対するテストはリポジトリルートの `tests/` 直下に責務単位で分類して配置する（テストは配布物に含めない）:

```
tests/
├── scripts/                # plugins/doc-advisor/scripts/ のスクリプトのテスト
├── skills/                 # plugins/doc-advisor/skills/ のスキルのテスト
└── integration/            # プラグイン全体の統合テスト
```

命名規則: `test_{module}.py`（例: `test_toc_utils.py`）

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

| 配置先            | 用途                       |
| ----------------- | -------------------------- |
| `skills/{skill}/` | スキル固有のスクリプト     |
| `scripts/`        | プラグイン共通のスクリプト |

SKILL.md からの参照には `${CLAUDE_SKILL_DIR}` または `${CLAUDE_PLUGIN_ROOT}` を使用する。

---

## 設計書の保守 [MANDATORY]

設計書は実装変更時に追従更新する。実装と設計が乖離したまま放置しない。

- ADR の配置先: `docs/specs/base/design/ADR-{NNN}_{topic}.md`
- 設計書の更新は **コードと同一 PR** で行うのが原則
- 大きな構造変更は専用の `DES-{NNN}` 設計書を立て、`README.md` / `CLAUDE.md` の説明とも整合させる

---

## 配布インターフェースを壊す前に呼び出し元を確認する [MANDATORY]

配布物（SKILL の引数・配布 script の CLI）は**上位層との契約**である。変更・削除の前に呼び出し元を横断 grep して確認する。

```bash
# 呼び出し元は別リポジトリ（bw-cc-plugins の forge / anvil）にあるため、
# このリポジトリ内の grep では見つからない
grep -rn "doc-advisor:index-docs" <bw-cc-plugins のチェックアウト>/plugins/
```

- 引数の**追加**は既存の呼び出し元を壊さない。**削除・改名、および受け付ける形を減らすこと**が壊す
- 上位層は各 SKILL を **1 回だけ**呼び、引数を組み替えず、失敗しても再試行しない。壊れると**上位層には理由が分からないまま機能が止まる**
- 引数仕様の正本は設計書に置く（配布物だけを正本にすると、書き換えで契約が消えても突き合わせる相手がいない）。契約の所在は DES-005 / DES-008 の該当節

### 全面上書きしたら差分を読む

配布物を `Write` で全面上書きすると**何が消えたかが画面に出ない**。上書き後に `git diff` を読み、引数表・オプション名の行が消えていないかを確認する。`Edit` なら差分が目に入るが、`Write` は見えない。

### 後方互換を壊す変更は計画に個別項目として書く

「オプションを整理する」「引数を最小にする」等の包括表現の下に後方互換の破壊を含めてはならない。**どの引数を削るかを名指しで書き、承認を得る。** 計画に書かれていない破壊は承認されていない。

---

## 使わないコードは削除する [MANDATORY]

非推奨マーカーやコメントアウトで残さない。残存コードは勘違いの原因になる。

- 削除の経緯はコミットメッセージへの記載で十分（CHANGELOG はリリースコミットでまとめて更新する）
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
バージョン更新は **リリースコミット** で一括して行い、AI および開発者が個別 PR で先回りバンプしてはならない。

### 編集禁止対象

| 対象                                          | 内容                                                     |
| --------------------------------------------- | -------------------------------------------------------- |
| `.claude-plugin/plugin.json`                  | `version` フィールド                                     |
| `README.md` / `README_en.md` のバージョン表記 | バージョン記載行（数値変更を伴う diff）                  |
| `CHANGELOG.md` 等の変更履歴ファイル           | 全エントリ（追加・修正・削除いずれも、リリース時を除く） |
| git tag（`v*`）                               | 作成・移動・削除いずれも禁止                             |

### 例外

以下に限り編集してよい:

- リリース作業として明示的に起動された場合（commit message に release / chore: bump 等を明記）
- 本ルール文書自体の改訂

### 理由

| 理由                           | 説明                                                                   |
| ------------------------------ | ---------------------------------------------------------------------- |
| リリース単位の一意性           | 誰がいつ何をまとめてリリースするかをリリースコミットに集約する         |
| CHANGELOG 整合性               | feature/fix PR ごとの CHANGELOG 編集はリリース時の整理と二重作業になる |
| 並行 PR の merge conflict 回避 | 複数 PR が同時に同じ version 行を編集すると衝突が頻発する              |

**NEVER** feat / fix / chore コミットの流れで AI が自発的にバージョンをバンプしてはならない。
**MUST** バージョン更新が必要と判断したら、ユーザーに明示的なリリース作業の起動を提案する。
