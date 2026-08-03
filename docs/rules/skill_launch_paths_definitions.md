---
type: doc-advisor
title: Definitions of SKILL / Agent / subagent Launch Paths and Names
purpose: Definition document that assigns official short names to the five delegation launch paths so ambiguous wording cannot be misread. It also fixes the value range of subagent_type and its invalid values.
content_details:
  - "Classification of the five launch paths: inherited SKILL, fork SKILL, general-purpose Agent, custom Agent, Bash subprocess"
  - Per-path comparison of launch tool, where the procedure lives, parent context inheritance, input, and output
  - The difference between a general-purpose Agent and a custom Agent is where the procedure lives (the caller prompt versus agents/<name>.md)
  - A fork SKILL and a custom Agent share one execution model, isolated context plus a predefined role, differing only in launch tool and definition file location
  - Only the inherited SKILL inherits the parent context; the other four paths all run in an isolated context
  - Usage rule banning the standalone word subagent, with the correct term for each referent
  - "Value range of subagent_type: built-in general-purpose Agent types and custom Agent names"
  - "Passing a Skill name, slash notation, or a file path as subagent_type is invalid, and the correct way to make an Agent play a skill's role"
  - Positioning of the machine-readable subset docs/rules/skill_launch_terms.toml
applicable_tasks:
  - Describing a launch path in SKILL.md or a design document
  - Specifying subagent_type when calling the Agent tool
  - Confirming terminology while choosing a delegation method
  - Replacing standalone uses of the word subagent in existing documents
keywords:
  - launch path
  - inherited SKILL
  - fork SKILL
  - general-purpose Agent
  - custom Agent
  - Bash subprocess
  - subagent_type
  - Skill tool
  - Agent tool
  - skill_launch_terms.toml
body_hash: sha256:d7c1d352e7ca5aebb034237f7a4edb3a60d2485260bb2f5e5eeaea75d9e60c2d
---

# SKILL / Agent / subagent 起動経路と名称 定義

## 本文書の性質

これは **定義文書** である。仕様 (specs) でもルール (rules) でもフォーマット (format) でもなく、それらすべてが依拠する **基盤・分類・用語** を提供する。

**主目的は名称の統一**。「subagent」「general-purpose subagent」等の曖昧語による誤読 (例: Issue #32 で `subagent_type: "forge:fixer"` と誤指定された事例) を防ぐため、起動経路 5 種に **公式の短縮名称** を定める。SKILL.md / 設計書 / ガイド文書はこの名称に従って記述する。

> 機械可読 subset: `docs/rules/skill_launch_terms.toml`
> subset には短縮名称に加えて、起動ツール説明で使う `Skill ツール` / `Agent ツール` も含む。

### 必読 (本文書を読む前提)

本文書の表は Claude Code 公式仕様の用語 (`context: fork` / `agent` / `subagent_type` / `allowed-tools`) を前提とする。以下を未読の場合は先に読むこと:

- [Claude Code Skills](https://code.claude.com/docs/en/skills) — `context: fork` / `agent` / `allowed-tools` の仕様
- [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents) — `subagent_type` の値域と組み込み subagent タイプ

> 本文書の射程は **「これは何か / 何と呼ぶか」**。\
> 「どれを選ぶか」(判断ガイド) は `COMMON-DES-001` を、\
> 「どう書くか」(規約) は `skill_authoring_notes.md` を参照する。

---

## 1. 起動経路 5 種と短縮名称 [MANDATORY]

Claude Code 上で「処理を他へ委譲する」経路は以下の 5 種に分類される。**それぞれ動作モデルが異なり、混同してはならない**。

| #  | **短縮名称**        | 起動ツール / 方法                                                      | 手順書はどこに?                                                                                              | 親 context | 入力                                             | 出力               |
| -- | ------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------ | ------------------ |
| 1  | **継承型 SKILL**    | `Skill` ツール (`context:` 未指定)                                     | SKILL.md (親 Claude が直接 Read)                                                                             | **継承**   | SKILL.md + `$ARGUMENTS` + 親 context             | 親 context に展開  |
| 2  | **fork 型 SKILL**   | `Skill` ツール (`context: fork`)                                       | SKILL.md (fork 先の隔離 context が Read)                                                                     | **遮断**   | SKILL.md + `$ARGUMENTS` のみ                     | return 値のみ      |
| 3a | **汎用 Agent**      | `Agent` ツール (`subagent_type: general-purpose` / `Explore` / `Plan`) | **呼び出し元 prompt 自体が手順書** (※1)                                                                      | **遮断**   | prompt + 渡された context                        | 完了通知 + 出力    |
| 3b | **カスタム Agent**  | `Agent` ツール (`subagent_type: <カスタム名>`)                         | **カスタム定義ファイル** (`agents/<name>.md` の system prompt) が手順書。呼び出し元 prompt はタスク指示 (※2) | **遮断**   | system prompt + タスク prompt + 渡された context | 完了通知 + 出力    |
| 4  | **Bash subprocess** | Bash で外部プロセス起動                                                | (該当なし)                                                                                                   | **遮断**   | コマンドライン引数                               | exit code + stdout |

### 名称の使い方 [MANDATORY]

- SKILL.md / 設計書 / ガイド文書では **短縮名称をそのまま使う**: 「**カスタム Agent** として起動する」「**fork 型 SKILL** で実行する」など
- 「subagent」「general-purpose subagent」等の単独使用は **避ける** (§2 用法統一参照)
- 番号 (`#1` / `#3a` 等) は補助的な参照のみ (例: 表内で名称と併記)。本文中で「経路 3a」のような番号単独参照はしない

### 経路間の本質的な関係

- **汎用 Agent と カスタム Agent の差**: 「**手順書がどこにあるか**」。汎用 Agent は呼び出すたびに prompt で渡す。カスタム Agent は `agents/<name>.md` の system prompt に固定化される
- **fork 型 SKILL と カスタム Agent の動作モデル同等性**: 両者は「**隔離 context + 事前定義ロール**」という点で動作モデルが同じ。差は起動ツール (Skill / Agent) と定義ファイルの場所 (`skills/<name>/SKILL.md` / `agents/<name>.md`) のみ
- **継承型 SKILL のみ親 context を継承する**。他の 4 種はすべて隔離 context

> 継承型 SKILL で `$ARGUMENTS` に親タスクの指示文を貼ると AI が暴走する経路がある。詳細・対処は `skill_authoring_notes.md` 「継承型の必須事項」および `COMMON-DES-001` §4 を参照。

---

## 2. 「subagent」という語の用法統一 [MANDATORY]

「subagent」は **曖昧語**。fork 型 SKILL / 汎用 Agent / カスタム Agent のいずれも指せるため、文書中で単独使用しない。

| 指したい対象                                  | 正しい呼称                                                |
| --------------------------------------------- | --------------------------------------------------------- |
| fork 型 SKILL の隔離 context                  | **fork 型 SKILL**                                         |
| Agent ツールで立てたビルトイン (汎用 Agent)   | **汎用 Agent** / `general-purpose` 等の具体名             |
| Agent ツールで立てたカスタム (カスタム Agent) | **カスタム Agent** / 具体名 (例: **`claude-code-guide`**) |

> 既存文書中の「subagent」「general-purpose subagent」等の単独使用は段階的に置換する。新規・修正される文書では本規約に従う。

---

## 3. `subagent_type` の値域 [MANDATORY]

Agent ツール (汎用 Agent / カスタム Agent) の `subagent_type` パラメータの値域:

- **汎用 Agent**: `general-purpose` / `Explore` / `Plan` / `statusline-setup` 等
- **カスタム Agent**: `agents/<name>.md` で定義した名前 (例: `claude-code-guide` / `doc-advisor:toc-updater`)

### 無効な値の例 (Issue #32 系)

以下は **すべて無効** — `subagent_type` の値域外:

- Skill 名 (slash command 名): `doc-advisor:query-docs` / `doc-advisor:index-docs` 等
- slash 表記: `/doc-advisor:query-docs` 等
- ファイルパス: `skills/query-docs/SKILL.md` 等

> prompt 内の slash command 表記 (`/doc-advisor:query-docs ...` 等) は、Agent ツールに渡す **タスク指示文の中の表現** であり、`subagent_type` の値ではない。\
> Agent ツールに「特定スキルのロールを演じさせる」場合の正しい指定は `subagent_type: general-purpose` (= 汎用 Agent) で、prompt 内に役割と手順を記述する。
