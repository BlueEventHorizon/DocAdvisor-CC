# doc-db 検索精度の内部解説

doc-db は、doc-advisor の文書単位 Embedding を出発点として、**chunk 粒度の細分化・BM25・Hybrid 融合・Embedding recall 保証・LLM Rerank・grep 補完**を多層に積み重ねた検索プラグインである。本書はその設計判断と精度向上の経緯を、コードと評価データから掘り起こして解説する。

使い方（コマンド・引数・トリガー）は [guide_doc-db_ja.md](guide_doc-db_ja.md) を参照。本書は「なぜ高精度か」を扱う。

---

## 1. なぜ doc-db は精度が高いのか — 5 層の合成

doc-db の検索パイプラインは、独立に動く 5 つのレイヤーが**互いの弱点を埋め合う**構造になっている。

```
[クエリ]
   │
   ├─[L1] Embedding 検索 (text-embedding-3-large, 3072 dim, cosine)
   │        ├─ chunk = 見出し境界 + embed_text に親見出し+prose 連結
   │        └─ short chunk 補完 (MIN_EMBED_PROSE)
   │
   ├─[L2] Lexical 検索 (BM25: Robertson IDF + 文書長正規化)
   │        ├─ NFKC + lower、CJK は文字単位
   │        ├─ ID 完全一致 +10.0、クエリ完全一致 +2.0
   │
   ├─[L3] Hybrid 融合 (RRF k=60)
   │        ├─ lex ヒット率 < 5% → emb only にフォールバック
   │        └─ EMB_GUARANTEE_K=5 で emb 上位 K 件を fused 上位 K 件に必ず昇格
   │
   ├─[L4] LLM Rerank (gpt-4o-mini, JSON mode, temperature=0)
   │        ├─ 候補数を token budget で動的決定 (5〜30)
   │        └─ API 失敗時は hybrid score にフォールバック
   │
   └─[L5] SKILL 層の grep 補完 (オプション)
            ├─ ID パターン [A-Z]+-\d+ をクエリから抽出
            └─ ファイル全文 grep で false negative を回収
```

各レイヤーが何を解決しているか、コードと根拠データを順に見る。

---

## 2. L1: 見出し chunk と embed_text 強化

### 2.1 chunk = 見出し境界

`plugins/doc-db/scripts/chunk_extractor.py` は Markdown を `^(#{1,6})\s+...` で分割し、`heading_path` を chunk のメタデータに保持する。

- `MAX_CHUNK_CHARS = 8192`（chunk_extractor.py:12）
- `MIN_CHUNK_LEVEL = 6`（build_index.py:28）— H6 まで全て chunk 境界

**なぜファイル単位ではなく chunk か**: doc-advisor は `EMBEDDING_MAX_CHARS = 7500` でファイル全体を 1 ベクトルに圧縮する（embed_docs.py:374-385）。これは大ファイル末尾セクションが切り捨てられ、しかも 1 ベクトルに「目的が異なる複数セクション」が混ざって意味希釈する。doc-db は**論理的な意味境界**で切ることで、希薄化を抑える。

### 2.2 chunk_id は決定的なハッシュ

`chunk_extractor.py:74-80`:

```python
def _build_chunk_id(path: str, heading_path: List[str], seen: Dict[str, int]) -> str:
    base = hashlib.sha256(f"{path}|{' > '.join(heading_path)}".encode("utf-8")).hexdigest()[:8]
```

ファイルパス + heading_path から SHA-256 先頭 8 文字で生成。同じ見出し構造なら ID が安定するため、差分更新で**変更のない chunk は embedding を保持**し、変更分だけ再 API を叩ける。

### 2.3 embed_text 強化 — 短すぎる chunk の救済

`chunk_extractor.py` の `_enrich_embed_texts()`（コミット `725101c`、2026-05-12 追加）:

- 各 chunk に `embed_text` フィールドを付与し、Embedding に渡すテキストを `heading_path + "\n\n" + prose` に統一
- `MIN_EMBED_PROSE = 50`（chunk_extractor.py:13）。prose が 50 文字未満なら、**同一ファイル内の直前 chunk を遡って prose を補完**する

**なぜ重要か**: 「### 概要」「### 5. 開発時の基本原則」のように見出しだけの chunk は、本文がほぼ無く embedding ベクトルが意味を持たない（モデルが見出しの単語しか拾えない）。親 chunk の本文を連結することで、文脈付きベクトルになる。

実測効果は **7.3 改善の決定打** の「embed top-K 保証 + embed_text 強化」セクションで具体クエリと共に示す。

---

## 3. L2: Lexical 検索（BM25）

### 3.1 トークナイザ — CJK 文字単位

`plugins/doc-db/scripts/lexical_search.py:22`:

```python
TOKEN_RE = re.compile(r"[A-Za-z]+-\d+|[A-Za-z0-9_]+|[^\W\d_A-Za-z]+|\d+", re.UNICODE)
```

- `[A-Za-z]+-\d+` → `FNC-001`, `DES-026` 等の **ID パターンは 1 トークン**
- `[^\W\d_A-Za-z]+` → CJK 文字は連結（後段で substring カウントするため、結果として文字単位粒度のマッチに帰着）

正規化は NFKC + `.lower()` のみ（lexical_search.py:28-29）。形態素解析は導入していない（外部依存ゼロの方針 = NFR-005）。

### 3.2 BM25 — TF からの全面刷新

初版（コミット `46bc3ba`, 2026-05-08）は単純 TF カウントだった。コミット `1c28861`（2026-05-11）で全面書き換え:

```python
BM25_K1 = 1.5
BM25_B = 0.75

# Robertson IDF
idf[token] = math.log((N - df + 0.5) / (df + 0.5) + 1)

# BM25 スコア
tf_norm = (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avgdl))
score += idf[token] * tf_norm
```

**TF→BM25 で何が変わったか**: 単純 TF 方式では `ai` `エージェント` のような出現頻度の高い一般語が「単語が多く含まれる」というだけで上位を独占し、`develop_with_agent_rule.md` のような正解文書が押し出されていた。**IDF が一般語の重みを下げ、希少語を優遇する**ことで、クエリ「AI エージェントを使った開発の進め方」では正解文書がパスするようになる（後述 **7.3** の score breakdown 参照）。

`tests/doc_db/test_lexical_search.py` に `test_bm25_rare_token_outranks_common_token` が新規追加されており、この性質を unit test で固定している。

### 3.3 ID / フレーズの強制ブースト

BM25 に加え、構造化 ID とフレーズの完全一致にボーナススコアを足す（lexical_search.py:76-82）:

```python
for id_token in id_tokens:
    if id_token in body:
        score += 10.0           # FNC-001 等の ID が chunk 内にあれば +10
if query_norm.strip() and query_norm in body:
    score += 2.0                # クエリ全体の連続マッチで +2
```

これにより、`「FNC-006 の要件」`のような構造化クエリは BM25 計算と無関係に確実に上位に来る。

### 3.4 同義語辞書を**意図的に廃止**した設計判断

コミット `632a168`（2026-05-11）では `PHRASE_SYNONYMS` という 13 ペアの英↔カタカナ辞書（"golden set"↔"ゴールデンセット" など）を導入したが、わずか 3 時間後のコミット `1c28861` で**全削除**された。

設計書 `docs/specs/doc-db/design/DES-026_doc_db_design.md` v1.3 の §6.4:

> 同義語展開は非採用（クロスランゲージ同義語は Embedding 側が担う）

これは重要な設計判断で、**Lexical = 正規化済み完全一致、Embedding = 意味的同義**と役割を明確に分離した。Lexical 側で同義語をやると BM25 の確率モデルに歪みが出るうえ、Embedding と二重カウントになる。代わりに、cross-lingual の取りこぼしは **L3 の emb top-K 保証** で構造的に補償する（次節）。

---

## 4. L3: Hybrid 融合 — RRF + lex フォールバック + emb top-K 保証

`plugins/doc-db/scripts/hybrid_score.py`(99 行) は doc-db の精度面の心臓部。

### 4.1 RRF（Reciprocal Rank Fusion）

ベース融合は加重和でなく RRF（hybrid_score.py:29-68）:

```python
score = 0.0
if chunk_id in emb_rank:
    score += 1.0 / (60 + emb_rank[chunk_id])
if chunk_id in lex_rank:
    score += 1.0 / (60 + lex_rank[chunk_id])
```

**なぜ RRF か**: cosine 類似度（0〜1）と BM25 スコア（数十〜数百）はスケールが噛み合わない。線形加重では係数 α の調整が文書集合依存になる。RRF は「順位」だけを見るのでスケールに頑健で、両者が**同意した chunk**を自然に押し上げる。

### 4.2 lex フォールバック — 日本語クエリの構造的弱点を捌く

CJK は形態素解析なしだと BM25 が単語境界で当たらず、lex score=0 になる chunk が多発する。それを RRF にそのまま渡すと「emb で上位だが lex 不在」の chunk が `1.0/(60+rank)` の片方しか得点せず、「lex で偶然 1 件だけヒットした関係薄い chunk」と紛れる。

hybrid_score.py:12, 30-37:

```python
EMB_FALLBACK_LEX_RATIO = 0.05
...
if emb_items and len(lex_items) / len(emb_items) < EMB_FALLBACK_LEX_RATIO:
    sorted_emb = sorted(emb_items, key=lambda x: (-x["emb_score"], x["chunk_id"]))
    return [{"chunk_id": r["chunk_id"], "score": r["emb_score"]} for r in sorted_emb]
```

lex ヒット率が 5% 未満なら **RRF を捨てて emb のみで並べる**。これにより「全く lex に当たらない自然文クエリ」での品質を担保する。

### 4.3 emb top-K 保証 — 「hybrid recall ≥ emb recall」の不変条件

これが doc-db で最も特徴的なメカニズム。コミット `9d02bd4`（2026-05-12）。

```python
EMB_GUARANTEE_K = 5
...
top_emb_ids = [item["chunk_id"] for item in sorted(emb_items, key=lambda x: (-x["emb_score"], x["chunk_id"]))[:5]]
top_emb_id_set = set(top_emb_ids)
intruders = [x for x in fused[:5] if x["chunk_id"] not in top_emb_id_set]
if intruders:
    promotion_threshold = max(x["score"] for x in intruders)
    for rank_idx, cid in enumerate(top_emb_ids):
        if cid in (top_emb_id_set - {x["chunk_id"] for x in fused[:5]}):
            score_map[cid]["score"] = promotion_threshold + (5 - rank_idx) * 1e-9
    fused.sort(key=lambda x: (-x["score"], x["chunk_id"]))
```

ロジック:

1. Embedding 単独の上位 5 件を取る
2. RRF 後の上位 5 件と比較し、emb 上位 5 件のうち RRF top-5 に**入れなかった chunk** を昇格対象にする
3. RRF top-5 に居る「emb top-5 でない侵入者」の最高スコアを `promotion_threshold` とする
4. 昇格対象の chunk に `promotion_threshold + (5-rank_idx) * 1e-9` のスコアを設定し、emb 上位の相対順序を 1e-9 オフセットで保ったまま top-5 に押し込む

**何を保証しているか**: `hybrid` の top-K 集合は emb の top-K 集合を**必ず包含する**。式で書けば

```
hybrid_recall(K) ≥ emb_recall(K)   ∀ K ≤ EMB_GUARANTEE_K
```

これは「Hybrid を使うことで Embedding 単独より recall が落ちる」というアンチパターンを構造的に禁止する不変条件である。同義語辞書を捨てた代償（cross-lingual の lex=0 ヒット）を、ここで構造的に補償している。`tests/doc_db/test_hybrid_score.py` に `test_emb_guarantee_k_in_top_k`, `test_emb_guarantee_preserves_emb_rank_order` で固定。

---

## 5. L4: LLM Rerank

`plugins/doc-db/scripts/llm_rerank.py`（gpt-4o-mini, JSON mode）。

### 5.1 候補数を token budget で動的決定

```python
CONTEXT_WINDOW = 128000
INPUT_BUDGET_RATIO = 0.7
MIN_CANDIDATES = 5
MAX_CANDIDATES = 30
PROMPT_OVERHEAD_TOKENS = 800
OUTPUT_BUDGET_TOKENS = 1500
PREVIEW_TOKENS = 200
```

各候補は `heading_path + body` の冒頭 200 token preview を持ち、平均 token から `floor((128K * 0.7 - 800 - 1500) / 平均)` を計算して最大候補数を決める。一律 30 ではなく**実 token を測って詰め込む**ので、長い chunk が混ざっても context overflow しない。

トークン推定は ASCII 単語数 + 非 ASCII 文字数 / 2 のヒューリスティック（embedding_api.py 経由）で日本語にも対応。

### 5.2 graceful fallback

```python
except (...):
    fallback = sorted(selected, key=lambda x: (-x.get("score", 0.0), x["chunk_id"]))
    return fallback, {"fallback_used": True, ...}
```

API 失敗（rate limit, timeout, JSON 不正）時は **rerank を諦めて hybrid score 順で返す**。SKILL 側は `fallback_used` を観測してログに残す。**rerank の不調が検索全体の失敗にならない**設計。

---

## 6. L5: grep 補完（SKILL 層）

`plugins/doc-db/skills/query/SKILL.md` のワークフローで、`grep_docs.py`（184 行）を hybrid の後に走らせる。

- クエリから `[A-Z]+-\d+` 形式の ID を抽出
- シェルメタ文字を含む固有名詞は除外（**Bash injection 防止**、コミット `1eb8327` で要件化）
- Hybrid 結果に無いパスから抽出された行を「補完候補」として提示

意義: Embedding 単独だと `FNC-006` のような短い ID 文字列はベクトル空間で識別性が低い。Lexical の +10 ボーナスでカバーしているが、index が `incomplete`（embedding API が一部失敗）状態でも grep は動くので、二重の安全網になる。

---

## 7. 精度向上の歴史（時系列）

git log と評価結果から、各コミットがどの問題を解いたかを並べる。

| コミット  | 日時 (JST)  | 施策                                                       | 解いた問題                                  |
| --------- | ----------- | ---------------------------------------------------------- | ------------------------------------------- |
| `881b468` | 05-07       | text-embedding-3-large 採用 (3072 dim)                     | doc-advisor の small (1536 dim) より表現力  |
| `46bc3ba` | 05-08       | core pipeline 実装。見出し chunk + 単純 TF + RRF           | 文書全体 embedding の希釈・スケール衝突     |
| `28173ab` | 05-08       | stale 検知、欠損自動 rebuild、二相整合性                   | 古い index で誤検索する false negative      |
| `38d2886` | 05-08       | LLM Rerank 追加                                            | 自然文クエリの並べ順                        |
| `43a2d41` | 05-08       | バッチ実効化、エラー分類、token 推定改善                   | 部分失敗の可観測性、候補数の安定            |
| `1eb8327` | 05-09       | grep 補完 (TASK-016)                                       | ID 完全一致の false negative 補填           |
| `dae6c1d` | 05-09       | doc-type 動的解決                                          | plan 等が検索対象から漏れる                 |
| `fa167df` | 05-10       | `.doc_structure.yaml` の output_dir 尊重                   | ゴールデンセット評価環境の整備              |
| `632a168` | 05-11 19:33 | lex_ratio fallback + PHRASE_SYNONYMS + min_chunk_level     | 日本語クエリで lex=0 大量、同義語の対症療法 |
| `1c28861` | 05-11 22:39 | TF → **BM25**、PHRASE_SYNONYMS 全削除                      | IDF 不在で一般語過大評価、辞書メンテ負荷    |
| `725101c` | 05-12 00:34 | embed_text 強化 (heading_path + prose, MIN_EMBED_PROSE=50) | 短い chunk の embedding が意味を持たない    |
| `9d02bd4` | 05-12 00:43 | **emb top-K 保証** (EMB_GUARANTEE_K=5)                     | hybrid で emb 上位が押し出される            |
| `0fd0bba` | 05-12 12:30 | OPENAI_API_DOCDB_KEY 分離                                  | 運用上のキー分離（精度には無関係）          |

### 7.1 contact-b_docs（43 query）の評価推移

`meta/test_docs/contact-b_docs/test_manage/results/` の result_*.json から抽出した実測値:

| 計測日時 (JST) | mode                  | pass / total      | 直前の主要変更                                    |
| -------------- | --------------------- | ----------------- | ------------------------------------------------- |
| 03-31 11:11    | doc-advisor (ToC)     | 41/43 = 95.3%     | ベースライン                                      |
| 05-10 12:44    | doc-db hybrid         | **37/43 = 86.0%** | doc-db 初期、TF + 同義語なし                      |
| 05-11 19:35    | doc-db hybrid         | **40/43 = 93.0%** | lex_ratio fallback + 同義語辞書 + min_chunk_level |
| 05-11 21:01    | doc-advisor embedding | 41/43 = 95.3%     | リファレンス再計測                                |
| 05-11 21:23    | doc-db hybrid         | **41/43 = 95.3%** | BM25 化 + 同義語辞書廃止                          |
| 05-12 12:37    | doc-db hybrid         | **41/43 = 95.3%** | embed_text 強化 + emb top-K 保証                  |

最終時点で **doc-advisor の embedding と同等の 95.3%** に到達。残る 2 件は negative テスト（汎用文書を完全棄却できない既知の構造的制約）。

### 7.2 bw-cc-plugins（33 query、より難しいセット）

| 計測日時 (JST) | mode          | pass / total      | direct | task | crosscut | synonym | proper | negative |
| -------------- | ------------- | ----------------- | ------ | ---- | -------- | ------- | ------ | -------- |
| 05-11 11:26    | embedding     | 23/33 = 69.7%     | 11/11  | 5/6  | 3/6      | 2/4     | 2/4    | 0/2      |
| 05-11 11:27    | hybrid (初回) | 23/33 = 69.7%     | 9/11   | 6/6  | 3/6      | 3/4     | 2/4    | 0/2      |
| 05-11 15:45    | hybrid        | 28/33 = 84.8%     | 13/13  | 6/6  | 4/4      | 2/4     | 3/4    | 0/2      |
| 05-11 16:41    | hybrid (最終) | **29/33 = 87.9%** | 13/13  | 6/6  | 3/4      | 4/4     | 3/4    | 0/2      |

直感に反する興味深い動き:

- 初回 hybrid (`23/33`) は embedding 単独と同点だが、type breakdown が違う。**embedding は direct 11/11 だが synonym 2/4**、**hybrid は direct 9/11 だが synonym 3/4**。RRF だけでは direct で押し負ける chunk があった
- その後 direct は 11→13 に完全救済、synonym は 2→4 に完全救済
- negative は両方 0/2。これは「Kubernetes 関連クエリ」「Android Jetpack Compose」のような汎用 IT 用語に対して、技術的に隣接する文書（Skill 作成ガイド等）が embedding 空間で類似性を持ってしまう構造的制約

なお bw-cc-plugins セットは BM25 化（`1c28861`）と emb top-K 保証（`9d02bd4`）の**前**で計測が止まっており、これらを反映した再計測は未実施。後述 8 章の参考データはこの注意のもとで読まれたい。

### 7.3 改善の決定打 — 具体クエリで見る score breakdown

最も劇的な改善例: **「AI エージェントを使った開発の進め方」**（rules/synonym タイプ、正解 = `rules/core/develop_with_agent_rule.md`）

`result_docdb_hybrid_*.json` から、各時点での chunk 上位 5 件と score breakdown を抜粋:

**(a) 同義語辞書時代 (05-11 19:35, lex_fix)** — `fail`、`develop_with_agent_rule.md` 不在

| rank | chunk                                               | score  | emb   | lex     |
| ---- | --------------------------------------------------- | ------ | ----- | ------- |
| 1    | architecture_rule.md / レイヤーの責務               | 0.0256 | 0.477 | **2.0** |
| 2    | bad_practices.md / AIが陥りやすい誤りパターン       | 0.0255 | 0.431 | **3.0** |
| 3    | task_orchestration_workflow.md / ワークフロー全体像 | 0.0229 | 0.384 | **5.0** |
| 4    | project_rule.md / AI対話・開発ルール                | 0.0225 | 0.603 | 1.0     |
| 5    | project_rule.md / 4. 開発の役割分担                 | 0.0220 | 0.506 | 1.0     |

emb は project_rule.md が最高 (0.603) なのに、lex が高い "AI" "エージェント" を含む別文書に RRF で押し負けている。`develop_with_agent_rule.md` は top に出てこない。

**(b) BM25 化後 (05-11 21:23)** — `pass`、`develop_with_agent_rule.md` 入賞

| rank | chunk                                               | score  | emb   | lex |
| ---- | --------------------------------------------------- | ------ | ----- | --- |
| 1    | document_writing_rules.md / 実行手順                | 0.0279 | 0.481 | 4.0 |
| 2    | bad_practices.md / AIが陥りやすい誤りパターン       | 0.0252 | 0.431 | 3.0 |
| 3    | architecture_rule.md / レイヤーの責務               | 0.0251 | 0.477 | 2.0 |
| 4    | task_orchestration_workflow.md / ワークフロー全体像 | 0.0243 | 0.385 | 7.0 |
| 5    | project_rule.md / AI対話・開発ルール                | 0.0220 | 0.603 | 1.0 |

`develop_with_agent_rule.md` 自体は top-5 から外れるが、top-N（実際は 10）には **score=0.0218** で入る（`expected_scores` 値）。BM25 の IDF により「AI」「エージェント」のような頻出語の重みが下がり、相対的に正解文書が浮上した。

**(c) embed_text 強化 + emb top-K 保証 (05-12 12:37)** — `pass`、`develop_with_agent_rule.md` が **rank 2 に昇格**

| rank | chunk                                                            | score      | emb       | lex     |
| ---- | ---------------------------------------------------------------- | ---------- | --------- | ------- |
| 1    | project_rule.md / AI対話・開発ルール                             | 0.0313     | 0.602     | 2.88    |
| 2    | **develop_with_agent_rule.md / 開発における Agent / MCP の活用** | **0.0290** | **0.531** | **0.0** |
| 3    | task_execution_workflow.md / タスク実行ワークフロー              | 0.0290     | 0.517     | 0.0     |
| 4    | document_writing_rules.md / 実行手順                             | 0.0290     | 0.512     | 1.91    |
| 5    | project_rule.md / 5. 開発時の基本原則                            | 0.0290     | 0.509     | 0.0     |

ここに doc-db の核心が見える:

- `develop_with_agent_rule.md` は **lex=0.0** で BM25 では全く拾えない
- embed_text 強化で `heading_path + prose` を embedding した結果、emb=0.531 に上がった（lex_fix 時点では top-5 にすら入っていなかったので emb 値そのものが改善している）
- **emb top-K 保証**で `1.0/(60+rank)` の RRF だけでは届かなかったこの chunk が、score 0.0290 で rank 2 に押し込まれている。同じ 0.0290 が rank 3, 4, 5 にもあるのは **emb top-5 の昇格スコア + 1e-9 オフセット**の痕跡（rank が下がるごとに 1e-9 ずつ小さくなる）

つまり 1 クエリの中に、**BM25 で一般語の重みを下げる効果**、**embed_text 強化で短い chunk の意味復元**、**emb top-K 保証で lex=0 chunk を構造的に救済**、という 3 つの施策がそろって乗っている。

---

## 8. doc-advisor との横並び比較

| 観点                   | doc-advisor                                                       | doc-db                                                            |
| ---------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------- |
| 索引粒度               | ファイル単位 (1 ファイル 1 ベクトル)                              | 見出し chunk 単位 (H1〜H6)                                        |
| Embedding モデル       | text-embedding-3-small (1536 dim)                                 | text-embedding-3-large (3072 dim)                                 |
| Embedding 投入テキスト | 本文を 7,500 字で truncate                                        | `heading_path + prose`（短ければ親 chunk から補完）               |
| Lexical                | なし（grep_docs は補助、検索本体ではない）                        | BM25 + ID/フレーズ boost、CJK 文字粒度                            |
| Hybrid                 | union（threshold ベースの Index 候補と ToC 候補を集合演算で結合） | RRF (k=60) + lex フォールバック + emb top-K 保証                  |
| recall 保証            | 閾値（0.3 / 0.2）でのカットオフ                                   | **`hybrid_recall(K) ≥ emb_recall(K)` の不変条件をコード上で保証** |
| 再ランキング           | なし                                                              | LLM Rerank (gpt-4o-mini, token budget で動的候補数)               |
| ID/固有名詞            | grep_docs.py（任意、SKILL 側で判断）                              | grep_docs.py + Lexical の ID +10 boost（二重）                    |
| index 鮮度             | checksum + `--check`                                              | checksum + 検索時 stale 検知 + 自動 rebuild + 二相 commit         |
| 部分失敗               | 個別エラーで止まる                                                | `build_state="incomplete"` を index に記録、検索時に提示          |

doc-advisor は ToC キーワード一致＋ファイル単位 embedding なので、**ファイル全体が広く関連していれば強い**。doc-db は **ファイル内の特定セクションだけが関連するケース** や **lex で当たらない自然文クエリ** に強い。前者は計算コストが軽く（rerank の API 課金なし）、後者は精度寄り。**併用想定**で、両者は同じ `.doc_structure.yaml` を共有する。

---

## 9. 残課題

### 9.1 negative テストの構造的不通過

「Kubernetes」「Android Jetpack Compose」のような、文書セットと無関係だが技術領域として隣接するクエリで、`rules/` 配下の SKILL 作成ガイド等が cosine 0.3〜0.5 ヒットする。閾値で完全棄却するには `rules/` 全体の cosine 分布を割って絶対的に低くする必要があるが、それは正解クエリの recall も下げる。

→ 設計書 `NFR-004` の QUL-02 で「false negative 0 を最優先、false positive は許容」と明文化。受容する。

### 9.2 grep 補完が評価値に反映されない

`run_docdb_test.py` は `search_index.search()` を直接 import する。SKILL 層の grep_docs ワークフローは通らない。bw-cc-plugins セットの失敗のうち、`REQ-005 issue-driven flow` のような ID 完全一致クエリは実環境では grep で取れているはずだが、評価スコアには反映されない。

### 9.3 bw-cc-plugins セットの再計測

BM25 + embed_text 強化 + emb top-K 保証を投入した後（05-12 以降）、bw-cc-plugins セットでの再計測は未実施。contact-b と同様に有意な改善があるかは確認待ち。

### 9.4 形態素解析の不在

`MUST: 標準ライブラリのみ`（NFR-005）の制約で MeCab 等を使えない。CJK は文字単位 substring に倒している。語彙的に近い別語（「アクセス」と「アクセシビリティ」など）は BM25 では別語扱いだが、Embedding は問題なく拾うため、Hybrid 全体では破綻していない。

---

## 10. 参考

### コード（絶対パス）

- `plugins/doc-db/scripts/chunk_extractor.py` — 見出し chunk + embed_text 強化
- `plugins/doc-db/scripts/lexical_search.py` — BM25 + ID/フレーズ boost
- `plugins/doc-db/scripts/hybrid_score.py` — RRF + lex フォールバック + emb top-K 保証
- `plugins/doc-db/scripts/llm_rerank.py` — gpt-4o-mini rerank + 動的候補数 + fallback
- `plugins/doc-db/scripts/grep_docs.py` — SKILL から呼ばれる行単位検索
- `plugins/doc-db/scripts/build_index.py` — 二相 commit + 差分更新
- `plugins/doc-db/scripts/search_index.py` — 鮮度検知 + 自動 rebuild
- `plugins/doc-db/scripts/embedding_api.py` — text-embedding-3-large、バッチ、retry

### 設計書

- `docs/specs/doc-db/design/DES-026_doc_db_design.md` — 本体設計書 (v1.3)
- `docs/specs/doc-db/design/ADR-001_build_search_io_separation.md`
- `docs/specs/doc-db/GLO-001_search_terminology.md` — 検索パイプライン用語集
- `docs/specs/doc-db/requirements/FNC-006_doc_db_search_spec.md`
- `docs/specs/doc-db/requirements/NFR-004_doc_db_search_quality_spec.md`

### 評価環境（git 管理外）

- `meta/test_docs/README.md` — ゴールデンセット運用方針
- `meta/test_docs/run_docdb_test.py` — doc-db テストランナ
- `meta/test_docs/run_search_test.py` — doc-advisor 比較対象
- `meta/test_docs/contact-b_docs/test_manage/` — 43 query, 連絡先管理アプリの文書セット
- `meta/test_docs/bw-cc-plugins/test_manage/` — 33 query, 本リポジトリ自身を文書セット化したもの

### テスト（リグレッション固定）

- `tests/doc_db/test_lexical_search.py::test_bm25_rare_token_outranks_common_token`
- `tests/doc_db/test_hybrid_score.py::test_emb_guarantee_k_in_top_k`
- `tests/doc_db/test_hybrid_score.py::test_emb_guarantee_preserves_emb_rank_order`
- `tests/doc_db/test_chunk_extractor.py` — `min_chunk_level`, `embed_text` 強化
