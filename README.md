# doc-advisor

**Version: 0.4.6**

Claude Code 用の AI 検索可能なドキュメントインデックスプラグイン。プロジェクトの Markdown 文書を ToC（キーワード・メタデータ）で `key` 単位にインデックス化・検索し、AI が必要なコンテキストを自動発見できるようにする。

[English README](README_en.md)

## なぜ doc-advisor が必要か

プロジェクトが大きくなるとルール・規約・設計文書が蓄積される。AI がそれらを見つけられなければ活用できない。`doc-advisor` はこれらの文書をインデックス化し、AI が実装・レビュー時に関連文書を自動取得できるようにする。

- **実装前**: コードを書く前にプロジェクト固有の実装ルールと関連仕様を集める
- **レビュー時**: 適用すべきルールをレビュー観点として追加し、汎用的なベストプラクティスではなくプロジェクトの実際の基準で検査する

### 「この実装に何を読むべきか」を誰も保守できない問題（doc-advisor の存在意義）

定型のルール文書なら「これに従え」と固定で参照しても、ルール自体がそう変わらないので問題は小さい。だが**実装タスク**では事情が違う。「この機能を実装するには文書 A・B・C を読む必要がある」という**読むべき文書の集合は、タスクごとに変わる**。

ここで本質的な問題が出る — **その集合を誰が考え、実装者に教えるのか**。あらゆるタスクについて「これを読め」というリストを人が事前に書き、文書が増減・移動・改訂するたびに更新し続けるのは現実的でない。**保守コストが爆発する**。

doc-advisor は、この「タスク → 読むべき文書」の対応を**事前に書かず、タスク記述から動的に発見する**ために存在する。だから文書側は「何に依存するか（概念・ID）」だけ持てばよく、「このタスクでどれを読むか」は `query-docs` が都度組み立てる。結果として、文書にディレクトリパスを焼き込んだ "ここを見ろ" という参照は**そもそも不要になる**（パス参照はファイルの移動・リネームで腐り、保守コストの一因になる）。

## スキル一覧

doc-advisor は文書集合を `key`（任意の文字列）単位で管理する汎用 ToC Provider。`key` の意味（rules / specs 等の分類）を解釈せず、与えられた `key` と project-root-relative の `paths` に対して決定的に動作する。

| スキル         | 説明                                                              | トリガー句           |
| -------------- | ----------------------------------------------------------------- | -------------------- |
| **index-docs** | key + paths から ToC（キーワード/メタデータ）を生成・更新         | `"index docs"`       |
| **query-docs** | key 単位の ToC をキーワード/自然文で検索し関連文書パスを返す      | `"関連文書を探して"` |
| **check-toc**  | key 単位の ToC が新しいか（`fresh` / `stale`）を返す（read-only） | `"ToC は最新か"`     |

## ワークフロー

```mermaid
flowchart LR
    UP[上位層 / 単体モード<br/>key + paths 決定]
    DOC[(対象 Markdown)]
    IX[index-docs<br/>ToC 生成・更新]
    QR[query-docs<br/>検索]
    CK[check-toc<br/>鮮度確認]
    AI[AI Agent<br/>実装/レビュー]

    UP --> IX
    DOC --> IX --> TOC[(ToC YAML / key 単位)]
    QR --> TOC
    CK --> TOC
    AI --> QR
    QR -. 関連文書パス .-> AI
    UP --> CK
    CK -. fresh / stale .-> UP
```

## インストール

```text
/plugin marketplace add BlueEventHorizon/DocAdvisor
/plugin install doc-advisor@DocAdvisor
```

無効化したプラグインを再有効化するには、ターミナルから:

```bash
claude plugin enable doc-advisor@DocAdvisor
```

### ローカルで試す（セッション限定）

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor.git
claude --plugin-dir ./DocAdvisor/plugins/doc-advisor
```

## 使い方

事前の設定ファイル（`.doc_structure.yaml`）は不要。`key` と project-root-relative の `paths` を渡すだけで動作する。

### 1. ToC 構築（index-docs）

`key` と paths を指定して、その key の **完全な desired state** として ToC を構築・更新する。

```text
# 上位層（forge 等）が key と paths を決定して渡す
/doc-advisor:index-docs --key my-rules --paths-json '["docs/rules/a.md", "docs/rules/b.md"]'

# paths を JSON ファイルから読み込む
/doc-advisor:index-docs --key my-rules --paths-file paths.json

# 単体モード: project root 以下の全 Markdown を予約 key "all" に索引化
/doc-advisor:index-docs --all
```

> **desired-state の破壊性**: `--paths-json` / `--paths-file` で渡す paths は当該 key の完全な desired state。前回 ToC に存在し今回 paths に含まれない path は削除される（部分配列を渡すと残りが消える）。

### 2. 検索（query-docs）

```text
# key を指定して検索
/doc-advisor:query-docs --key my-rules "認証フローのレビュー観点"

# key 省略時は予約 key "all"（project 全体の単体モード索引）を検索
/doc-advisor:query-docs "ユーザ登録 API"
```

### 3. 鮮度確認（check-toc）

検索の前に「その ToC はまだ使えるか」を確認する read-only なスキル。判定結果を JSON で返すだけで、索引の生成・更新はしない。

```text
# 24 時間以内に生成された ToC かを確認
/doc-advisor:check-toc --key my-rules --max-age 86400

# 予約 key "all" を対象にする
/doc-advisor:check-toc --all --max-age 86400
```

答えは `freshness` の 2 値。ToC が存在しない場合も `stale` に含まれる（作り直しが必要という後続処理が鮮度超過と同じため）。原因は `reason`（`missing` / `outdated` / `generated_at_invalid` / `generated_at_future`）として併記される。

```json
{
  "status": "ok",
  "key": "my-rules",
  "freshness": "stale",
  "reason": "outdated",
  "age_seconds": 172800,
  "max_age_seconds": 86400
}
```

`--max-age` は必須。閾値をいくつにするか・古いときに何をするかは呼び出し側が決める。

## 動作要件

- [Claude Code](https://claude.ai/code) CLI
- Python 3.9 以上（標準ライブラリのみ。追加パッケージは不要）

## 開発者向け情報

このリポジトリ自体での開発・デバッグ・テスト・フォーマット・リリース手順は [`DEVELOPMENT.md`](DEVELOPMENT.md) を参照。`--plugin-dir` を使ったローカルデバッグなどを記載している。

このリポジトリは `BlueEventHorizon/bw-cc-plugins` マーケットプレイス（forge / anvil / doc-advisor / doc-db の 4 プラグイン集）から `doc-advisor` を分離したものです。

## ライセンス

[MIT](LICENSE)
