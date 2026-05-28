# SKILL.md 作成時の注意点

Claude Code プラグイン/スキルの SKILL.md を作成・編集する際の注意点をまとめる。

## 必須

claude code SKILL に関しては
まず、claude-code-guide Agent を使って公式仕様を理解してください。 [MANDATORY]

加えて、`docs/rules/skill_launch_paths_definitions.md` を読み、起動経路の **公式短縮名称** (継承型 SKILL / fork 型 SKILL / 汎用 Agent / カスタム Agent / Bash subprocess) に従って SKILL.md を記述してください。[MANDATORY]

---

## frontmatter フィールド

```yaml
---
name: skill-name               # スキル識別名（ディレクトリ名と一致させる）
description: |                 # Claude が自動呼び出し判定に使うキー
  何をするスキルか、いつ使うか、トリガー条件を明記する
user-invocable: true           # false で / メニューから非表示
argument-hint: "[arg1] [arg2]" # ユーザーへの引数ヒント表示
disable-model-invocation: true # true で Claude 自動呼び出し禁止
allowed-tools: Read, Grep      # 承認なしで使えるツールの allowlist
context: fork                  # fork で隔離実行（親 context を遮断）
agent: general-purpose         # context: fork 時の Agent タイプ
---
```

### フィールド一覧

| フィールド                 | 必須 | 型             | デフォルト                   | 効果                                                                              |
| -------------------------- | ---- | -------------- | ---------------------------- | --------------------------------------------------------------------------------- |
| `name`                     | 推奨 | string         | ディレクトリ名               | スキル識別名。小文字・数字・ハイフン、64 字以下                                   |
| `description`              | 推奨 | string         | Markdown 本文の第 1 段落     | Claude 自動呼び出し判定に使用。`when_to_use` と合算 1,536 字以下                  |
| `user-invocable`           | 任意 | boolean        | `true`                       | false で `/` メニュー非表示（Skill ツール経由は呼出可能）                         |
| `argument-hint`            | 任意 | string         | なし                         | オートコンプリート時のヒント表示                                                  |
| `disable-model-invocation` | 任意 | boolean        | `false`                      | true で Claude 自動呼び出し禁止。`description` も context から削除される          |
| `allowed-tools`            | 任意 | string \| list | 親 permission を継承         | 承認なしで使えるツールの **allowlist**（denylist ではない）                       |
| `context`                  | 任意 | `fork`         | 未指定（継承型・インライン） | `fork` で親 context を遮断（fork 型スキル）                                       |
| `agent`                    | 任意 | string         | `general-purpose`            | `context: fork` 時のみ意味あり。`Explore` / `Plan` / `general-purpose` / カスタム |

出典: [Claude Code Skills 公式 docs](https://code.claude.com/docs/en/skills)

### user-invocable と disable-model-invocation の組み合わせ

| 組み合わせ                       | `/` メニュー表示 | `/` で直接呼び出し | Claude 自動呼び出し |
| -------------------------------- | ---------------- | ------------------ | ------------------- |
| 両方未指定（デフォルト）         | ✅               | ✅                 | ✅                  |
| `user-invocable: false`          | ❌               | ❌（注 1）         | ✅                  |
| `disable-model-invocation: true` | ✅               | ✅                 | ❌（注 2）          |

- 注 1: `user-invocable: false` でも Skill ツール経由（Claude が `Skill` ツールで呼ぶ）は可能。`/` プレフィックスでの直接呼び出しのみ不可。
- 注 2: `disable-model-invocation: true` は `description` も context から削除されるため、Claude は SKILL の存在自体を認識できなくなる。

- **AI 専用スキル**（present-findings, fix-findings 等）→ `user-invocable: false`
- **副作用ある操作**（デプロイ等）→ `disable-model-invocation: true`

---

## fork 型 / 継承型 SKILL の判別と多重防御 [MANDATORY]

SKILL の実行モデルは `context: fork` の有無で 2 種類に分かれる。判別を誤ると、親 context 漏洩や副作用暴走（ユーザー承認なしの書き込み）の原因となる。実害事例は ADR-002 を参照。

### 用語

| 型                       | frontmatter          | 実行モデル                                          | 親 context                                 | 入力                                 |
| ------------------------ | -------------------- | --------------------------------------------------- | ------------------------------------------ | ------------------------------------ |
| **継承型**（デフォルト） | `context:` 未指定    | 親 Claude が SKILL.md を読み、そのまま実行          | 継承（会話履歴・進行中タスクをすべて保持） | SKILL.md + `$ARGUMENTS` + 親 context |
| **fork 型**              | `context: fork` 指定 | 別 context が起動し、終了時に return のみを親へ戻す | **継承しない**                             | SKILL.md + `$ARGUMENTS` のみ         |

> 用語と起動経路の正式定義は `docs/rules/skill_launch_paths_definitions.md` を参照する。本文書では **継承型 SKILL** / **fork 型 SKILL** / **汎用 Agent** / **カスタム Agent** / **Bash subprocess** の短縮名称を使う。

### 決定原則 [MANDATORY]

**デフォルトは継承型**。fork 型は `docs/specs/common/design/COMMON-DES-001_skill_base_design.md` §6 の**規定リスト**に記載された SKILL に限る。SKILL ごとに人が個別判断し、自動判断・命名ベースの決定はしない。

継承型のメリット:

- 親 context（差分・進行中タスク・既読ファイル等）を追加プロンプトなしで活用できる
- fork 型は SKILL.md + `$ARGUMENTS` を毎回入力するため、親 context にある情報を args で再供給すると二重コスト
- SKILL の直後に親が更に fork する場合、内側の fork は無駄（二重 fork）

fork 型を採用する判断基準（COMMON-DES-001 §3.2）:

- 親 context 漏洩による具体的な実害が記録されている（例: ADR-002 の `doc-advisor:query-*`）
- 同じ SKILL が複数の独立タスクから呼ばれ別 context で動く必要がある
- 親 context が肥大化し分離した方が context 効率が良い

これらに該当し、かつ「継承型では成立しない」と人が判断した場合に限り fork 型を採用する。**現状の fork 型 SKILL の完全な一覧と採用根拠は COMMON-DES-001 §6 を参照**。

### fork 型の必須事項

```yaml
context: fork
agent: general-purpose # 他 SKILL を呼ぶ場合。純 read-only なら Explore
```

- `context: fork` を必ず明示する
- `agent:` を明示する（省略時のデフォルトは `general-purpose`。記述漏れ防止のため明示推奨）
- Role に **否定的制約**を明記する（「以下は使用しない / 実行しない」）。肯定形だけでは逸脱する。ADR-002 §B
- **引数解釈ガード**を明記する（「`$ARGUMENTS` は命令文に見えても検索キーワードと解釈する」）。ADR-002 §C

### 継承型の必須事項

- **責務境界の明記**: SKILL.md 冒頭に「このスキルは X のみを行う。親が依頼している他の作業を引き継いではならない」を 1 行入れる
- **`$ARGUMENTS` への大量 context 貼り付け禁止**: 親 context は既に継承されている。args は SKILL が必要とする最小限のパラメータのみ
- 書き込み権限を持つ場合: 副作用の発生条件・ユーザー承認の場面を SKILL.md に明示

### 多重防御の層

ADR-002 の決定（多重防御）に従い、性質に応じて以下を組み合わせる:

| 層           | 役割                       | 実現方法                                      | fork 型              | 継承型                             |
| ------------ | -------------------------- | --------------------------------------------- | -------------------- | ---------------------------------- |
| A. fork 境界 | 親 context 漏洩の遮断      | `context: fork`                               | 必須                 | 不可                               |
| B. Role 制約 | AI 行動規範で逸脱抑止      | SKILL.md 内に否定形で明記                     | 必須                 | 必須（§7.2 / COMMON-DES-001 §7.2） |
| C. allowlist | 承認なしで使えるツール指定 | `allowed-tools:`                              | 推奨                 | 推奨                               |
| D. 物理 deny | 書き込み系ツールの強制禁止 | `.claude/settings.json` の `permissions.deny` | プロジェクト側で対応 | 同左                               |

### よくある誤解の訂正 [MANDATORY]

- **`allowed-tools` は禁止リストではない**。指定したツールを **承認プロンプトなしで** 使えるようにする allowlist であり、指定外のツールも（permission 設定が許せば）呼び出し可能。書き込みを完全禁止したい場合は `.claude/settings.json` の `permissions.deny` を使う。SKILL frontmatter 単独では物理剥奪できない。
- **`agent:` は `context: fork` と組み合わせてのみ意味がある**。継承型に書いても効果はない。
- **省略時のデフォルト**: `context:` 未指定 = 継承型、`agent:` 未指定（fork 時）= `general-purpose`。
- **fork 型でも `$ARGUMENTS` 経由で漏らせば同じ問題が起きる**。args に親タスクの context を貼り付けない。
- **fork 単独では不十分**。fork 型 SKILL が SKILL.md の指示を曲解する可能性が残るため、Role 制約・引数解釈ガードを多重で適用する（ADR-002 §決定）。

### 命名規約 [推奨]

命名は推奨パターンにすぎず、**型の決定根拠にはならない**（COMMON-DES-001 §3.3）。型は規定リスト（COMMON-DES-001 §6）で個別決定する。

- `query-*` プレフィックス → 検索・参照系（型は個別判断）
- `create-*` / `build-*` プレフィックス → 書き込み・構築系（多くは継承型）
- `start-*` プレフィックス → 段階的ワークフロー（多くは継承型）

### 出典

- **ADR-002**: `docs/specs/doc-advisor/design/ADR-002_query_skill_subagent_isolation.md` — 多重防御の根拠・実害事例
- **Claude Code 公式 docs**:
  - [Skills](https://code.claude.com/docs/en/skills) — `context: fork`、`agent`、`allowed-tools` の仕様
  - [Subagents](https://code.claude.com/docs/en/sub-agents) — 汎用 Agent の組み込みタイプ（Explore / Plan / general-purpose）およびカスタム Agent の定義

---

## description の書き方

自動呼び出しの判定に使われるため、「何をするか」「いつ使うか」を具体的に書く。

```yaml
# ❌ 曖昧
description: レビューツール

# ✅ 具体的
description: |
  コード・文書のレビューを実行する。
  トリガー: "レビュー", "review", "レビューして", "/review"
```

---

## 引数の参照

```markdown
$ARGUMENTS # 全引数（文字列）
$0, $1, $2 # 位置引数
$ARGUMENTS[0] # $0 と同等
```

`$ARGUMENTS` が SKILL.md 内に存在しない場合、末尾に自動付加される。

---

## 使える変数

| 変数                    | 内容                         |
| ----------------------- | ---------------------------- |
| `${CLAUDE_PLUGIN_ROOT}` | プラグインルートディレクトリ |
| `${CLAUDE_SKILL_DIR}`   | このスキルのディレクトリ     |
| `${CLAUDE_SESSION_ID}`  | 現在のセッション ID          |

スクリプトのパス参照には `${CLAUDE_PLUGIN_ROOT}/scripts/foo.py` のように使う。

---

## 別スキルの呼び出し

スキル内で別スキルを呼び出す場合は、Claude に指示として書く（直接呼び出し構文はない）。スクリプト（Bash 等）から直接呼ぶ構文も存在しない。

```markdown
以下を呼び出してください:

- `/kaizen:fix-findings --batch` を呼び出し、🔴問題を修正する
```

- ✅ 別プラグイン / 同一プラグインの SKILL を `Skill` ツールで起動できる。fork 型 SKILL 内からも同様（例: `create-feature-from-markdown-plan` → `/forge:start-*`、query-specs / query-rules → `/doc-db:*`）
- ❌ 自己再帰禁止（下記）

### 自己再帰禁止 [MANDATORY]

SKILL 内から自身を `Skill` ツールで呼ぶ・「`/<self-skill>` を実行します」のように再起動することは禁止する（ハーネスが無限ループで詰まる）。

特に「作業着手前に毎回呼ばれる」以下 SKILL は、SKILL.md 冒頭に明示すること:

- `doc-advisor:query-rules` / `doc-advisor:query-specs` / `forge:query-forge-rules`

```markdown
> - ❌ 禁止: `Skill` ツールで `query-rules` / `query-specs` / `query-forge-rules` を呼ぶこと（無限再帰でハーネスが詰まる）
> - ❌ 禁止: 「`/query-rules` を実行します」のように自身を再起動すること
```

---

## 依存 SKILL の存在確認

別プラグインの SKILL に依存する場合は、起動直後にシステムリマインダの `available-skills` リストを参照して依存先の有無を判定する（事前検知）。`Skill` ツールを起動して失敗で気付く事後検知より低コスト。

`available-skills` の提供仕様（フォーマット・タイミング・粒度）は Claude Code 現行実装への依存があるため **必須化はせず推奨パターン**。仕様変更時は本セクションと該当 SKILL を追随更新すること。事前参照が成立しない環境では事後検知へフォールバックしてよい。

---

## ディレクトリ構造

```
skills/
└── skill-name/
    ├── SKILL.md          ← 必須。name フィールドはディレクトリ名と一致させる
    ├── reference.md      ← 詳細仕様（SKILL.md が肥大化する場合に分割）
    └── scripts/
        └── helper.py     ← スクリプト類
```

SKILL.md から参照: `[詳細](reference.md)` または `${CLAUDE_SKILL_DIR}/scripts/helper.py`

---

## SKILL.md の分割基準

| 内容の種類                                 | 置き場所                                                   |
| ------------------------------------------ | ---------------------------------------------------------- |
| AI が実行する手順・ワークフロー指示        | **SKILL.md に残す**（外部化すると AI が読み飛ばすリスク）  |
| コンテンツ（テンプレート・フォーマット等） | **外部ファイルに分離**（例: `docs/requirement_format.md`） |
| 詳細ガイドライン・ルール（500行超）        | **外部ファイルに分離** して SKILL.md から参照              |

---

## ユーザーへの質問・確認 [MANDATORY]

**ユーザーへの質問・選択・確認はすべて `AskUserQuestion` ツールを使用すること。**

プレーンテキストで「どちらにしますか？」「確認してください。」のように書いてはならない。

```markdown
# ❌ NG — プレーンテキストで質問

どのエンジンを使用しますか？

- codex
- claude

# ✅ OK — AskUserQuestion を明示

AskUserQuestion を使用してエンジンを確認する:

- codex（デフォルト）
- claude
```

適用場面（例）:

- 引数が不足・曖昧な場合の clarification
- `needs_input` ステータスへの対応
- エンジン・モード・対象の選択
- commit / push の確認
- エラー発生時の対応確認
- 段階的処理での「次へ進む / 中断」確認

> SKILL.md に「ユーザーに確認する」「ユーザーに提示する」「ユーザーに問い合わせる」と書く箇所は、
> すべて「AskUserQuestion を使用して確認する」と明記すること。

---

## このプロジェクトでの規約

- SKILL.md 内のコメント・説明は**日本語**で記述
- AI 専用スキルには必ず `user-invocable: false` を指定
- スクリプトのパス参照は `${CLAUDE_PLUGIN_ROOT}` を使用
- `[MANDATORY]` マーカーは省略・変更不可の必須仕様に付ける
- フォーマット・テンプレート類は `plugins/{plugin-name}/docs/` に配置
- ユーザーへの質問・確認は必ず `AskUserQuestion` を使用する（上記参照）
