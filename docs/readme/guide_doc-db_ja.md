# doc-db 詳細ガイド

見出し（Heading）境界で区切った **chunk 単位**の文書 Index を構築し、**Embedding + Lexical（語彙一致）の Hybrid 検索**と **LLM Rerank** でルール・仕様を検索するプラグイン。クエリに仕様 ID や固有名詞が含まれる場合は、**ファイル全文に対する grep** を追加し、Hybrid 結果と統合して取りこぼしを抑える。

## 概要（doc-advisor との違い）

| 観点     | doc-advisor                        | doc-db                                                   |
| -------- | ---------------------------------- | -------------------------------------------------------- |
| 索引の粒 | 文書単位の ToC / Embedding の 2 層 | **見出し chunk 単位**の Embedding Index + Lexical スコア |
| 検索     | ToC・Index・ハイブリッド（自動）   | `emb` / `lex` / `hybrid` / `rerank` を明示選択可能       |
| 後処理   | —                                  | **LLM Rerank**（失敗時は Hybrid スコアへフォールバック） |
| 軽量さ   | ToC + grep 中心で軽量              | Index 構築・API 呼び出しが増える（高精度寄り）           |

**doc-db は doc-advisor の上位互換ではない。** doc-advisor は ToC／既存の Index パイプラインで実装前のルール・仕様収集に軽量。**doc-db** は chunk ベースの Hybrid + Rerank で意味検索と ID・用語の両立を狙う。**両方インストールして用途に応じて使い分け・併用できる。** いずれも同一の `.doc_structure.yaml` を参照する。

## 前提条件

- プロジェクトルートに `.doc_structure.yaml`（`/forge:setup-doc-structure` で生成）— [文書構造ガイド](guide_doc_structure_ja.md) を参照
- `OPENAI_API_DOCDB_KEY` — Embedding（Index 構築・クエリ）および Rerank モードで LLM API を使用する
- Python 3（スキルから `python3` で `plugins/doc-db/scripts/` を実行）

## スキル一覧

| スキル        | 役割                               |
| ------------- | ---------------------------------- |
| `build-index` | chunk Index の生成・差分更新       |
| `query`       | Index 検索（+ 条件付き grep 統合） |

## スキル詳細

### build-index

```
/doc-db:build-index --category rules|specs [--full] [--check] [--doc-type ...]
```

| 引数         | 説明                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------ |
| `--category` | `rules` または `specs`（必須）                                                                   |
| `--full`     | 全体再スキャン（初回や Index 再生成時）                                                          |
| `--check`    | 鮮度・整合性の確認                                                                               |
| `--doc-type` | `specs` 時のみ。`requirement` / `design` / `plan` 等（カンマ区切り可）。未指定時は実装既定に従う |

ルール文書や仕様の追加・変更後、検索前に Index を更新する。

**例（rules の初回フルビルド）:**

```
/doc-db:build-index --category rules --full
```

### query

```
/doc-db:query --category rules|specs --query "..." [--mode emb|lex|hybrid|rerank] [--top-n N] [--doc-type ...]
```

| 引数         | 説明                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------- |
| `--category` | `rules` または `specs`（必須）                                                               |
| `--query`    | 検索クエリ（必須）                                                                           |
| `--mode`     | `emb` / `lex` / `hybrid` / `rerank`（省略時はスクリプト既定）                                |
| `--top-n`    | 返却件数の上限                                                                               |
| `--doc-type` | `specs` で対象 doc 種別を絞る場合。省略時は `requirement` と `design` が既定など、実装に従う |

**例（rules を Hybrid で検索）:**

```
/doc-db:query --category rules --query "ユニットテストの必須条件" --mode hybrid
```

SKILL では、クエリに `[A-Z]+-\d+` 形式の ID や固有名詞がある場合に **`grep_docs.py` による全文行検索**を追加し、Hybrid 結果に無かったパスを補完候補として提示する（詳細は `plugins/doc-db/skills/query/SKILL.md`）。

## 動作フロー概要

1. **Index 構築** — `build-index` が `.doc_structure.yaml` から対象ファイルを解決し、見出し chunk を抽出して Embedding を書き込む（`.claude/doc-db/index/` 配下）。
2. **Hybrid 検索** — `query` が `search_index.py` で Index 鮮度確認のうえ Embedding・Lexical を組み合わせ、`rerank` 指定時は LLM で並べ替え。
3. **grep 補完** — ID や安全な識別子がクエリにあれば grep を追加実行し、Hybrid だけでは拾えなかった行を結果に足す。

## doc-advisor からの移行・併用

- **併用（推奨）** — ToC の更新・`/doc-advisor:query-*` で素早く候補を得つつ、chunk 粒度の意味検索が必要なときだけ `/doc-db:query` を使う。
- **doc-db のみ追加** — 既存の `.doc_structure.yaml` をそのまま使える。doc-advisor のファイルや Index（`.claude/doc-advisor/` 等）は **変更しない**。
- **運用の目安** — CI や普段のルール確認は doc-advisor でもよい。設計書・要件の deep dive や長文にまたがる用語探索は doc-db を検討する。

## 動作要件

- 上記「前提条件」に加え、ネットワーク越しに OpenAI API に到達できること（NFR-005: 追加の pip / 常駐 DB は不要）。
