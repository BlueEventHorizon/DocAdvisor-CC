---
name: query
description: |
  doc-db index を検索する。Hybrid / Rerank に加え、ID・固有名詞がある場合は grep で全文行検索し結果を統合する。
  トリガー: "/query", "doc-db で検索"
user-invocable: true
argument-hint: "--category rules|specs --query <text> [--mode emb|lex|hybrid|rerank] [--top-n N] [--doc-type ...]"
allowed-tools: Bash, AskUserQuestion
---

# /query

## 1. インデックス検索（必須の第一ステップ）

`$ARGUMENTS` を解釈し、`--category` / `--query` / `--mode` / `--top-n` / `--doc-type` を組み立てて実行する。stdout の JSON 全体を保持する（後続のパス集合 `S_hybrid` の元になる）。

```bash
python3 ".claude/doc-db/scripts/search_index.py" \
  --category "<rules|specs>" \
  --query "<ユーザーのクエリ>" \
  [--mode <emb|lex|hybrid|rerank>] \
  [--top-n <N>] \
  [--doc-type "<requirement,design 等>"]
```

- `$ARGUMENTS` からユーザーの意図を解釈し、各引数を明示的に組み立てる（`$@` は使わない）。
- `--doc-type` 省略時、スクリプトは `.doc_structure.yaml` の全 doc_type を検索する。ユーザーが特定の種別のみ検索したい意図がある場合は AI が判断して `--doc-type` を明示する。
- rules の場合、`--doc-type` は付けない（無視される）。

## 2. grep 併用（条件付き・DES-026 §3.4）

次の **いずれかを満たす** と判定したら、`grep_docs.py` による全文行検索を**追加で**実行する。

- クエリ（またはユーザー `$ARGUMENTS`）に **ID パターン** `[A-Z]+-\d+`（例: `FNC-006`, `DES-026`, `TASK-016`）が含まれる
- クエリに **固有名詞・識別子**（仕様書名、ファイル名、拡張子付き設定名など）が含まれ、Embedding だけでは取りこぼしやすいと判断できる

**ID・キーワードの抽出:**

- 正規表現 `[A-Z]+-\d+` でクエリ全体から ID を列挙する（重複は除く）。
- 固有名詞は文脈から判断する（機械的パーサーに任せない）。

**安全性制約 [MANDATORY]:**

- grep に渡すキーワードは **ID パターン（`[A-Z]+-\d+`）または英数字・ハイフン・アンダースコア・ドットのみで構成される文字列** に限定する。
- シェルメタ文字（`$`, `` ` ``, `(`, `)`, `|`, `;`, `&`, `>`, `<`, `\`）を含む文字列は grep キーワードとして**使用しない**（Bash injection 防止）。
- 上記に該当する固有名詞は grep 補完対象から除外し、Hybrid 検索のみに依存する。

**grep の実行（抽出した各キーワードごと）:**

`search_index.py` に渡した `--category` と一致させる。`--doc-type` は specs のときのみ、`search_index` に渡した値と同じカンマ区切りを渡す（ユーザーが省略していたら `grep_docs` 側も省略でよい — 両スクリプトとも `.doc_structure.yaml` の全 doc_type を検索する）。

```bash
python3 ".claude/doc-db/scripts/grep_docs.py" \
  --category "<rules|specs>" \
  --keyword "<抽出した 1 語句または ID>" \
  [--doc-type "<requirement,design 等>"]
```

- stdout の JSON の `results` は `{ "path", "line", "content" }` の配列である。Index の状態に依存しない（GRP-02）。

## 3. 結果の統合（AI が行う・ロジックではなく手順）

1. **Hybrid 側のパス集合** `S_hybrid`: `search_index.py` の応答 JSON 内 `results[*].path` を重複なく集める。
2. **grep 結果の処理**: 各 `grep_docs.py` 実行で得た `results` について、各行ヒットの `path` を見る。
3. **補完候補**: grep でヒットした行のうち、`path` が `S_hybrid` に**含まれない**ものを「補完候補」としてマークする。Hybrid に既に含まれるパス上の行は、必要なら本文引用の補足として使ってよいが「漏れ補完」リストには乗せない。
4. **ユーザーへの提示順**: まず Hybrid（意味順位・スコア付き）を提示し、続けて「全文 grep で見つかった行（インデックス候補に無かったパス）」を `(path, line, content)` で列挙する。false negative を避けるため、迷った補完候補は含める。

## 4. エラー時

- `search_index.py` が stderr にバリデーション JSON（exit 2）を出した場合: 設計書の案内に従い `--full` や設定確認をユーザーに伝える。AskUserQuestion を使用して次のアクションを確認する。
- `grep_docs.py` が `{"status":"error",...}` を出した場合: 原因を要約し、`.doc_structure.yaml` や引数を確認する。AskUserQuestion を使用して続行するか確認する。

## 5. 注意

- 処理ロジック・正規表現の実装はスクリプトに置く。本 SKILL は **実行順序と判断基準** のみを記す（`skill_authoring_notes.md` の「AI への実行指示」の扱い）。
- ユーザーへの選択・確認が必要なときは **AskUserQuestion** ツールを使う（プレーンテキストでの質問だけにしない）。
