# SKILL.md 作成時の注意点

Claude Code プラグイン/スキルの SKILL.md を作成・編集する際の注意点をまとめる。

---

## frontmatter フィールド

```yaml
---
name: skill-name              # スキルの識別名（ディレクトリ名と一致させる）
description: |                # Claude が自動呼び出し判定に使うキー
  何をするスキルか、いつ使うか、トリガー条件を明記する
user-invocable: true          # false でメニューから非表示（AI専用）
argument-hint: "[arg1] [arg2]" # ユーザーへの引数ヒント表示
disable-model-invocation: true # true で Claude 自動呼び出し禁止（手動のみ）
allowed-tools: Read, Grep     # 使用可能ツールを絞る場合に指定
context: fork                 # fork で subagent 隔離実行
agent: Explore                # context: fork 時の subagent タイプ
---
```

### user-invocable と disable-model-invocation の使い分け

| 設定 | メニュー表示 | ユーザー呼び出し | Claude 自動呼び出し |
|-----|------------|--------------|-----------------|
| デフォルト | ✅ | ✅ | ✅ |
| `user-invocable: false` | ❌ | ❌ | ✅ |
| `disable-model-invocation: true` | ✅ | ✅ | ❌ |

- **AI 専用スキル**（present-findings, fix-findings 等）→ `user-invocable: false`
- **副作用ある操作**（デプロイ等）→ `disable-model-invocation: true`

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
$ARGUMENTS       # 全引数（文字列）
$0, $1, $2       # 位置引数
$ARGUMENTS[0]    # $0 と同等
```

`$ARGUMENTS` が SKILL.md 内に存在しない場合、末尾に自動付加される。

---

## 使える変数

| 変数 | 内容 |
|-----|------|
| `${CLAUDE_PLUGIN_ROOT}` | プラグインルートディレクトリ |
| `${CLAUDE_SKILL_DIR}` | このスキルのディレクトリ |
| `${CLAUDE_SESSION_ID}` | 現在のセッション ID |

スクリプトのパス参照には `${CLAUDE_PLUGIN_ROOT}/scripts/foo.py` のように使う。

---

## 別スキルの呼び出し

スキル内で別スキルを呼び出す場合は、Claude に指示として書く（直接呼び出し構文はない）。

```markdown
以下を呼び出してください:
- `/kaizen:fix-findings --batch` を呼び出し、🔴問題を修正する
```

スクリプト（Bash コマンド）から直接スキルを呼び出すことはできない。

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

| 内容の種類 | 置き場所 |
|-----------|---------|
| AI が実行する手順・ワークフロー指示 | **SKILL.md に残す**（外部化すると AI が読み飛ばすリスク） |
| コンテンツ（テンプレート・フォーマット等） | **外部ファイルに分離**（例: `defaults/requirement_format.md`） |
| 詳細ガイドライン・ルール（500行超） | **外部ファイルに分離** して SKILL.md から参照 |

---

## このプロジェクトでの規約

- SKILL.md 内のコメント・説明は**日本語**で記述
- AI 専用スキルには必ず `user-invocable: false` を指定
- スクリプトのパス参照は `${CLAUDE_PLUGIN_ROOT}` を使用
- `[MANDATORY]` マーカーは省略・変更不可の必須仕様に付ける
- フォーマット・テンプレート類は `plugins/kaizen/defaults/` に配置
