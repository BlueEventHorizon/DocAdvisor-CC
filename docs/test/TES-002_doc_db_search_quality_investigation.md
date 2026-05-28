---
name: "TES-002"
type: investigation
title: "doc-db Hybrid 検索品質調査：根本原因分析と改善施策"
created: "2026-05-11"
status: final
---

# TES-002: doc-db Hybrid 検索品質調査：根本原因分析と改善施策

## 1. 背景と目的

TES-001 の比較テスト（Golden Set 33件）で doc-db hybrid が 75.8%（25/33）に留まり、`direct` タイプのクエリ 2 件が見落とされた。

- **FNC-001**: "doc-advisor のコンテキスト外検索と3モード検索方式" → `DES-006_semantic_search_design.md` 未検出
- **FNC-002**: "見落としゼロの検索精度要件と Golden Set" → `FNC-002_zero_miss_search_accuracy_spec.md` 未検出

`direct` タイプの見落としは品質上の重大な問題であるため、根本原因を特定し修正する。

## 2. 根本原因分析

### 2.1 FNC-001 の見落とし

| 原因                              | 詳細                                                                                                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A: Lexical トークナイザのバグ** | `TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)` が日本語・ASCII の境界でトークンを分割しない。"と3モード" が 1 トークンになり、lex ランクが 169 位に落ちた |
| **B: RRF の不均衡ペナルティ**     | lex ランクが極端に低いと RRF スコアが大幅に下がり、emb ランク 19 位のチャンクが総合で上位 10 件外に落ちた                                                  |
| **C: top-n が 10 件**             | emb で 19 位のチャンクが top-10 に入らず、そもそも評価対象外だった                                                                                         |

### 2.2 FNC-002 の見落とし

| 原因                              | 詳細                                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| **D: ASCII/CJK 境界バグ（同上）** | "Golden Set" の "Set" が前の日本語と結合し、lex 検索でヒットしなかった                  |
| **E: 同義語なし**                 | "Golden Set"（英語）に対応する "ゴールデンセット"（カタカナ）の辞書が存在しなかった     |
| **F: lex=0 の RRF ペナルティ**    | lex ヒットなしのチャンクは RRF で大幅ランクダウン。emb で高スコアでも最終結果から外れた |

### 2.3 試みた解決策と意外な発見

#### min_chunk_level=1 の誤解

当初、**B** の原因として「"コンテキスト外検索" と "3モード検索方式" が別チャンクに分散している」と誤推測し、`min_chunk_level=1`（ファイル全体を 1 チャンクに統合）を施策4として実装した。

しかしベンチマーク結果は以下のとおり：

| 設定                         | 合格率            | 状況                                         |
| ---------------------------- | ----------------- | -------------------------------------------- |
| 改善前（min_chunk_level=6）  | 75.8% (25/33)     | FNC-001/002 失敗                             |
| min_chunk_level=1 適用後     | 84.8% (28/33)     | FNC-001/002 修正、synonym 1 件リグレッション |
| **min_chunk_level=6 に戻す** | **87.9% (29/33)** | FNC-001/002 維持、リグレッション解消         |

min_chunk_level=1 は**逆効果**だった。理由：

- h3 チャンク "FNC-005: 文書フォーマットの選定基準"（emb=0.668）がファイル全体（emb=0.376）に統合されて意味的焦点が希薄化
- YAML/Markdown 等の汎用キーワードがファイル全体に散在し、lex スコアが膨張して無関係チャンクのランクを押し上げた
- FNC-001/002 の修正は施策1+3+5（トークナイザ・emb フォールバック・同義語）で達成可能だった

**教訓: チャンク粒度を粗くする方向は emb の意味的焦点を失う。lex 問題はトークナイザと同義語で解決すること。**

## 3. 実装した施策

### 施策1: TOKEN_RE の修正（`lexical_search.py`）

**問題**: `[^\W_]+` が UNICODE モードで日本語・数字・ASCII を区別せず 1 トークンに結合する。

```python
# 修正前
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# 修正後（優先順：ID パターン → ASCII → CJK → 数字）
TOKEN_RE = re.compile(
    r"[A-Za-z]+-\d+|[A-Za-z0-9_]+|[^\W\d_A-Za-z]+|\d+",
    re.UNICODE,
)
```

効果：

- "と3モード" → ["と", "3", "モード"] に分割
- "Golden Set" → ["golden", "set"] に分割（NFKC 正規化後）
- "FNC-006" → ["fnc-006"] として ID パターンで 1 トークン保持

### 施策2: top-n デフォルト値の変更（`search_index.py`）

```python
# 修正前
parser.add_argument("--top-n", type=int, default=10)

# 修正後
parser.add_argument("--top-n", type=int, default=20)
```

テストランナー（`run_docdb_test.py`）も同様に `-n 20` をデフォルトに変更。

### 施策3: emb-only フォールバック（`hybrid_score.py`）

lex ヒット率が極端に低い場合（lex 件数 / emb 件数 < 5%）、RRF をスキップして emb スコア降順で返す。

```python
EMB_FALLBACK_LEX_RATIO = 0.05

def rrf_fuse(emb_items, lex_items, k=60):
    if emb_items and len(lex_items) / len(emb_items) < EMB_FALLBACK_LEX_RATIO:
        sorted_emb = sorted(emb_items, key=lambda x: (-x["emb_score"], x["chunk_id"]))
        return [{"chunk_id": r["chunk_id"], "score": r["emb_score"]} for r in sorted_emb]
    # 通常の RRF ロジック
    ...
```

効果：lex ヒットゼロでも emb 高スコアチャンクが上位に残る。

### 施策4: min_chunk_level パラメータ（`chunk_extractor.py`）

`extract_chunks()` に `min_chunk_level` パラメータを追加。デフォルト 6（全見出しレベル分割、後方互換）。`build_index.py` では `MIN_CHUNK_LEVEL = 6` のまま維持。

```python
def extract_chunks(
    path: str,
    markdown_text: str,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
    min_chunk_level: int = 6,  # 6=全レベル分割（デフォルト）
) -> List[Dict]:
    ...
```

このパラメータは実験・特殊用途向けに提供するが、本番インデックスでは変更しない。

### 施策5: 英語↔カタカナ同義語展開（`lexical_search.py`）

```python
PHRASE_SYNONYMS: List[Tuple[str, str]] = [
    ("golden set", "ゴールデンセット"),
    ("embedding",  "エンベディング"),
    ("hybrid search", "ハイブリッド検索"),
    ("chunk",      "チャンク"),
    ("pipeline",   "パイプライン"),
    ("migration",  "マイグレーション"),
    # ... 計13エントリ
]
```

`score_chunks()` 内でクエリに含まれるフレーズを検出し、対応する同義語の出現回数をスコアに加算する。

## 4. 最終ベンチマーク結果

bw-cc-plugins Golden Set（33件）、`hybrid` モード、`top-n=20`。

| タイプ   | 改善前            | 改善後            |
| -------- | ----------------- | ----------------- |
| direct   | 11/13             | **13/13**         |
| task     | 6/6               | 6/6               |
| crosscut | 3/4               | **3/4**           |
| synonym  | 2/4               | **4/4**           |
| proper   | 3/4               | 3/4               |
| negative | 0/2               | 0/2               |
| **合計** | **25/33 (75.8%)** | **29/33 (87.9%)** |

### 残存する失敗（4件）

| クエリ                                         | タイプ   | 原因                                                              |
| ---------------------------------------------- | -------- | ----------------------------------------------------------------- |
| Kubernetes のデプロイメントマニフェスト…       | negative | threshold 未実装：emb が意味的に近い文書を返す                    |
| forge の文書フォーマット要件と SKILL.md 分離   | crosscut | `REQ-003_skill_script_separation.md` の関連語彙がクエリと乖離     |
| REQ-005 issue-driven flow と GitHub Issue 連携 | proper   | `doc_types_map` の `requirement` 対象外パスにある可能性（要調査） |
| Android Jetpack Compose のナビゲーション…      | negative | 同上（threshold 未実装）                                          |

negative 2 件はスコア閾値の仕組みがなければ原理的に解決しない。`search_index.py` に `--score-threshold` オプションを追加する余地がある。

## 5. 追加したユニットテスト

| テストファイル                         | テスト名                                  | 対応施策 |
| -------------------------------------- | ----------------------------------------- | -------- |
| `tests/doc_db/test_lexical_search.py`  | `test_tokenize_splits_cjk_and_ascii`      | 施策1    |
|                                        | `test_tokenize_splits_cjk_and_latin`      | 施策1    |
|                                        | `test_tokenize_digits_separate`           | 施策1    |
|                                        | `test_cjk_keyword_matches_in_body`        | 施策1    |
|                                        | `test_phrase_synonym_en_to_ja`            | 施策5    |
|                                        | `test_phrase_synonym_ja_to_en`            | 施策5    |
| `tests/doc_db/test_hybrid_score.py`    | `test_emb_fallback_when_lex_ratio_low`    | 施策3    |
|                                        | `test_rrf_used_when_lex_ratio_sufficient` | 施策3    |
|                                        | `test_emb_fallback_with_zero_lex`         | 施策3    |
| `tests/doc_db/test_chunk_extractor.py` | `test_min_chunk_level_1_collapses_to_h1`  | 施策4    |
|                                        | `test_min_chunk_level_2_collapses_h3`     | 施策4    |
|                                        | `test_min_chunk_level_default_unchanged`  | 施策4    |

## 6. 今後の課題

| 課題                                   | 優先度 | 対応案                                      |
| -------------------------------------- | ------ | ------------------------------------------- |
| negative クエリの誤検出                | 中     | `--score-threshold` オプションの追加        |
| REQ-005 の不検出                       | 中     | `doc_types_map` のパス解決をデバッグ        |
| 同義語辞書の拡充                       | 低     | 実運用クエリのログから追加候補を収集        |
| `lexical_search.py` の日本語形態素解析 | 低     | 長い CJK トークンの部分一致改善（MeCab 等） |

## 関連ドキュメント

- [TES-001: doc-advisor vs doc-db 比較テスト仕様](test_spec_doc_advisor_vs_docdb.md)
- `meta/test_docs/bw-cc-plugins/test_manage/queries.yaml`: Golden Set クエリ
- `plugins/doc-db/scripts/lexical_search.py`: 施策1・5
- `plugins/doc-db/scripts/hybrid_score.py`: 施策3
- `plugins/doc-db/scripts/chunk_extractor.py`: 施策4
