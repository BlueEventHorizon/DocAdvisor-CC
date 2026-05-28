---
name: "TES-001"
type: test
title: "doc-advisor SKILL vs doc-db SKILL 検索品質比較テスト"
created: "2026-05-11"
status: draft
---

# TES-001: doc-advisor SKILL vs doc-db SKILL 検索品質比較テスト

## 目的

doc-advisor（`/doc-advisor:query-rules`, `/doc-advisor:query-specs`）と doc-db（`build_index.py` + `search_index.py`）の検索品質を同一 Golden Set で比較評価し、doc-db が doc-advisor の検索精度と同等以上であることを検証する。

## テスト対象

| 手法                        | 検索方式                                                             | エントリポイント                                                           |
| --------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| **doc-advisor**（Baseline） | auto モード（ToC キーワード + Embedding セマンティックの組み合わせ） | `/doc-advisor:query-rules {query}` <br> `/doc-advisor:query-specs {query}` |
| **doc-db**（Target）        | Hybrid（Embedding + Lexical + LLM Rerank）                           | `search_index.py --mode hybrid`                                            |

doc-advisor の auto モードは、内部で ToC キーワード検索を実行し、結果が不足すれば Embedding セマンティック検索で補完する。SKILL として実際に呼んだ際の出力（ファイルパス一覧）を評価対象とする。

## Golden Set

`meta/test_docs/bw-cc-plugins/test_manage/queries.yaml` を使用。

| タイプ     | 検証する能力       | rules  | specs  |
| ---------- | ------------------ | ------ | ------ |
| `direct`   | 基本精度           | 5      | 6      |
| `task`     | タスク起点         | 4      | 2      |
| `crosscut` | 横断的クエリ       | 3      | 3      |
| `synonym`  | 言い換え耐性       | 2      | 2      |
| `proper`   | 固有名詞           | 2      | 2      |
| `negative` | 無関係クエリの棄却 | 1      | 1      |
| **合計**   |                    | **17** | **16** |

## 評価指標

| 指標      | 計算方法                     | 閾値                     |
| --------- | ---------------------------- | ------------------------ |
| Recall    | `hit_count / expected_count` | 両手法で 100%（FN ゼロ） |
| Precision | `hit_count / result_count`   | doc-db >= doc-advisor    |
| MRR       | 期待結果の逆数順位平均       | doc-db >= doc-advisor    |

判定: Recall が FN ゼロで、Precision と MRR が doc-db >= doc-advisor なら合格。

## テスト実行手順

### 準備

Golden Set と文書配置を確認。

```bash
# クエリ一覧
python3 -c "
import yaml
with open('meta/test_docs/bw-cc-plugins/test_manage/queries.yaml') as f:
    data = yaml.safe_load(f)
    for cat in ('rules', 'specs'):
        for q in data[cat]:
            print(f\"[{cat}][{q['type']}] {q['query']} -> {len(q.get('expected_paths', []))}\")
"
```

### Phase 1: doc-advisor テスト

```bash
# 1. 設定保存
python3 .claude/skills/update-forge-toc/scripts/swap_doc_config.py --store

# 2. テスト用 doc_structure.yaml へ差し替え
cp meta/test_docs/bw-cc-plugins/test_manage/doc_structure.yaml .doc_structure.yaml

# 3. ToC 生成（output_dir 経由でテスト用ディレクトリに出力）
/doc-advisor:create-rules-toc --full
/doc-advisor:create-specs-toc --full

# 4. Golden Set の各クエリに対して SKILL を実行し結果を収集
#    queries.yaml からクエリを取り出し、以下の手順を反復:
#      /doc-advisor:query-rules {query}  → 返却パス一覧を results に記録
#      /doc-advisor:query-specs {query}  → 返却パス一覧を results に記録
#    結果ファイル: meta/test_docs/bw-cc-plugins/test_manage/results/advisor_results.json
#
#    JSON 形式:
#    {
#      "rules": [
#        {"query": "...", "result_paths": ["path/to/file1.md", ...]},
#        ...
#      ],
#      "specs": [...]
#    }

# 5. 評価
python3 meta/test_docs/evaluate_toc_results.py bw-cc-plugins advisor_results.json -v

# 6. 設定復元（必ず実行）
python3 .claude/skills/update-forge-toc/scripts/swap_doc_config.py --restore
```

### Phase 2: doc-db テスト

```bash
# 1. インデックス再構築（実環境用）
python3 plugins/doc-db/scripts/build_index.py --category rules --full
python3 plugins/doc-db/scripts/build_index.py --category specs --full

# 2. Golden Set の各クエリで検索
#    queries.yaml からクエリを取り出し、以下の手順を反復:
#      python3 plugins/doc-db/scripts/search_index.py --category rules --query "{query}" --mode hybrid --top-n 20
#      python3 plugins/doc-db/scripts/search_index.py --category specs --query "{query}" --mode hybrid --top-n 20
#    返却 JSON から result_paths を抽出し results に記録
#    結果ファイル: meta/test_docs/bw-cc-plugins/test_manage/results/docdb_results.json

# 3. 評価
python3 meta/test_docs/evaluate_toc_results.py bw-cc-plugins docdb_results.json -v
```

### Phase 3: 比較集計

両手法の結果をマージし、以下の比較表を生成:

```
| テストID | タイプ | カテゴリ | クエリ | Recall (advisor) | Recall (docdb) | Precision (advisor) | Precision (docdb) | MRR (advisor) | MRR (docdb) | 判定 |
|---------|-----|---------|--------|----------------|------|------|------|----|-----|------|
| TES-001-01 | direct | rules | ... | | | | | | | |
| TES-001-02 | task | specs | ... | | | | | | | |
```

## 判定基準

| 条件                                                                | 結果                            |
| ------------------------------------------------------------------- | ------------------------------- |
| Recall が両手法とも 100% で、Precision/MRR が doc-db >= doc-advisor | **合格**                        |
| Recall が 100% 未満                                                 | **不合格**（FN の原因分析必須） |
| Precision/MRR が doc-db < doc-advisor                               | **要分析**（差の要因を報告）    |

## 前提条件

- API キー環境変数が設定されていること（doc-advisor 内蔵の Embedding 利用のため）。`OPENAI_API_DOCDB_KEY` を優先参照し、未設定時は `OPENAI_API_KEY` にフォールバック（DES-007 統一仕様）
- Golden Set が `meta/test_docs/bw-cc-plugins/test_manage/queries.yaml` に存在すること

## 関連ドキュメント

- [`meta/test_docs/README.md`](../../meta/test_docs/README.md): テスト基盤の設計
- [`meta/test_docs/bw-cc-plugins/test_manage/queries.yaml`](../../meta/test_docs/bw-cc-plugins/test_manage/queries.yaml): Golden Set クエリ
- [`meta/test_docs/bw-cc-plugins/test_manage/doc_structure.yaml`](../../meta/test_docs/bw-cc-plugins/test_manage/doc_structure.yaml): テスト用 doc_structure.yaml
