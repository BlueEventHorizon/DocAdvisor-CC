---
type: doc-advisor
title: ADR-006 index-docs Parallel Fill Performance
purpose: Records the decision to speed up the toc-updater fill phase via a wider window, a compressed format doc, and limited batching, gated on measured extraction quality.
content_details:
  - Measurements - ~18s and ~24K tokens per document, effective parallelism verified at 10, per-document time independent of the window
  - The bottleneck is launch-count overhead and tail latency, not insufficient parallelism
  - context rot is the central concern - mixing documents in one context causes cross-document keyword misattribution
  - Plan A - raise the distributed default window from 5 to 10 (verified safe; 429 on a low tier degrades to 5 then 3)
  - Plan C - compress formats/toc_format.md so per-document context shrinks (speed and quality move together)
  - Plan B - limited batching of k=2..3 same-directory neighbours, gated on a quality measurement
  - Grouping is decided deterministically by script; AI grouping by hand is forbidden
  - "Addendum (Issue #29) - continuous dispatch with claim/lease replaced foreground barrier waves; 12.6% makespan gain measured"
  - Addendum 2 - the free-slot arithmetic moved into index_docs.py because window minus in_flight_groups must not be recomputed by AI
  - Rejected - official multi-agent orchestration (not reachable from the SKILL runtime), and auto-selecting barrier vs continuous
applicable_tasks:
  - Changing the parallel window or the batch size of toc-updater fill
  - Diagnosing slow or rate-limited indexing on a large corpus
  - Deciding whether dispatch control belongs to a script or to the AI
  - Reviewing extraction quality after a batching change
  - Understanding why claim and lease exist in toc_store.py
keywords:
  - ADR-006
  - context rot
  - continuous dispatch
  - sliding-window
  - claim
  - lease
  - in_flight_groups
  - max_batch
  - tail latency
  - makespan
body_hash: sha256:b23115aa7ed595560eb1be5189dde94bc1608ca4a44988d53d936e4d6838f3f2
---

# ADR-006: index-docs 並列充填の高速化（並列度引き上げ・規約圧縮・限定バッチング）

## ステータス

採択（2026-06-07）。Issue #27 に基づく。

`index-docs`（継承型 SKILL）の Phase 2「toc-updater 並列充填」が大規模プロジェクト（400+ ファイル）で
1〜2 時間かかる問題に対する高速化方針を定義する。採択する施策は以下の 3 つである。

- **A. 並列度 5→10**（実証済み安全圏。配布デフォルトを 10 に引き上げ）
- **C. 1 件あたり固定オーバーヘッド削減**（`formats/toc_format.md` を抽出に必要な最小限へ圧縮）
- **B. 限定バッチング**（同一ディレクトリ近傍の類似文書を k=2〜3 でまとめる。品質実測ゲート通過を必須条件とする）

## コンテキスト

### 計測（Issue #27、すべて観測値）

隔離 key `perf-probe` で本リポジトリ docs/ を prepare し、toc-updater を実起動して計測した。

| 項目               | 実測                                                                                    |
| ------------------ | --------------------------------------------------------------------------------------- |
| 1 件あたり処理     | 約 18 秒・約 24K トークン・tool_uses=4（うち固定 ~4K = `toc_format.md` 等の規約再読込） |
| 実効並列度         | 10 を実証（5 で頭打ちではない）                                                         |
| 1 件あたり処理時間 | 並列度に依存せず一定（1 並列 18.6s / 5 並列 17.0s / 10 並列 16.1s）                     |
| テールレイテンシ   | 遅い 1 件が平常の 2.5 倍に化け、バッチ全体を律速                                        |

並列 5・80 バッチ・テール無視の理論下限は約 47 分。実運用 2 時間との差は、テールレイテンシ × 80 バッチ、
context overflow による再開・compaction ロス、後半バッチのメイン会話履歴肥大、レート制限 throttle
（400 件 × 24K ≒ 9.6M トークン）の累積と推定される。

→ **主因は並列度不足ではなく「起動回数（400）に比例するオーバーヘッド」と「テール律速」。**

### context rot（質の問題）

設計の中心論点は **context rot** である。

- トークン**量**が上限以下でも、コンテキストに多様・無関係な情報を詰めるほど精度が落ちる（量でなく質）。
- メタデータ抽出は「各文書を**独立に正確に**読む」ことが要件。複数文書を 1 コンテキストに混ぜると、
  ある文書のキーワードを別文書に誤帰属する**文書間混線**が起きる。
- LLM エージェントは会話履歴を保持するため、k 件を逐次処理しても前の文書がコンテキストに残り続ける。
- **小さいファイルを大量に詰めるほど多様性が上がり、rot が強く効く**（最も失敗しやすい）。

したがって高速化は「コンテキストを増やす方向（B）」ではなく「減らす方向（C）」に寄せるのが原則である。
B を採る場合も、量（トークン予算）ではなく**質（混線せず品質が保てる件数）で k の上限が決まる**。

### 配布制約

Workflow 型オーケストレーション（最大 16 同時等）は SKILL ランタイムから当てにできない
（ユーザー操作起点・未文書化）。確実に使えるのは **Agent ツール複数発行のみ**。本 ADR は
この制約下で実装する。

> **追補（Issue #29）**: 本 ADR 採択時（#27）は Agent ツールを **foreground バリア**（全完了待ち
> wave）で発行していた。Issue #29 で `run_in_background` + claim/lease による**連続ディスパッチ
> （sliding-window）を検証し配布既定に更新**した。「Agent ツール発行が唯一の確実な基盤」という
> 前提は不変で、その発行方式をバリアから連続ディスパッチへ変えた差分である（末尾「追補」節）。

## 決定

### A. 並列度を 5→10 に引き上げ（配布デフォルト 10）

`index_toc_orchestrator.md` / `skills/index-docs/SKILL.md` の並列度を 5 から 10 へ変更する。
1 件あたり処理時間は並列度に依存しないため、増やした分だけスループットが向上する。各エージェントは
1 文書のクリーンな分離を維持するため、A は品質に無関係で実証済み安全圏である。

- 配布デフォルトは **10**。
- レート制限はエンドユーザの tier 依存のため、**429 が発生する低 tier 向けに並列度を 5/3 へ下げる
  手順を文書化**する（既定は 10 のまま）。

### C. 固定オーバーヘッド削減（`toc_format.md` 圧縮）

toc-updater が毎回読む `formats/toc_format.md`（約 10.8KB）を、抽出に必要な最小限へ圧縮する。
規約再読のトークンを削りつつ、1 文書あたりのコンテキストを軽く保つため **rot 的にも有利**
（速度と品質が同方向）。

- 維持するもの：`Field Guidelines`、pending（中間ファイル）スキーマ、最終 ToC スキーマ（SSoT）。
- 削減するもの：抽出に不要な重複（網羅的な Complete Examples 等）。
- `validate_toc.py` は `toc_format.md` を**実行時に Read しない**（制約はコード内ハードコード、
  参照はコメントのみ）ことを確認済み。よって圧縮はプログラム的に安全で、影響は AI が読む量のみ。

### B. 限定バッチング（k=2〜3、同一ディレクトリ近傍）

1 エージェントが k=2〜3 件を処理し、起動回数を 1/k に、規約再読を 1/k に削減する。
**ただし context rot の主たるリスク源であり、Issue #27 の当初結論では「本命にできない」とされた。**

本 ADR では B を**配布デフォルトで有効化する**判断を採るが、これは Issue 結論との緊張関係にあるため、
以下を**必須条件（ゲート）**とする。

- **選定基準**：同一ディレクトリ近傍の**類似文書**のみをまとめる（主題が近く文書間混線が起きにくい）。
  小ファイルを無差別に大量に詰める方式は採らない。
- **グルーピングは script 側で決定論的に行う**（AI による手作業グルーピングは禁止。決定論は script、
  AI は抽出判断のみ）。
- **各文書を独立に抽出**することを toc-updater に明示し、rot 回避ガイドラインを置く。
- **品質実測ゲート（§検証）を通過しない限り既定有効化しない**。劣化が出れば既定オフへ後退する。

## トレードオフ / リスク

| リスク                                                                   | 対応                                                |
| ------------------------------------------------------------------------ | --------------------------------------------------- |
| テールレイテンシ（並列度と独立、大バッチほど悪化）                       | B のバッチングで平均化して緩和。k は小さく保つ      |
| 低 tier の 429（配布デフォルト 10 を上げすぎると発生）                   | 既定 10 のまま、低 tier 向け降格手順（5/3）を文書化 |
| 並列度上限は 10 まで実証、20/30 は未検証                                 | 本 ADR では 10 を上限とする                         |
| 配布制約（Workflow を当てにできない）                                    | Agent ツール複数発行のみで実装                      |
| **B の context rot（同一ディレクトリでも小ファイル密集なら混線しうる）** | 品質実測ゲートで検出。劣化時は既定オフへ後退        |
| サンプル数が少ない（各条件 1 回）                                        | 設計確定前に複数回計測で信頼度を上げる              |

## 検証（B の品質実測ゲート）[MANDATORY] — 実施済み・合格

B の既定有効化は、`meta/golden_set_test/`（`test_manage/RUNBOOK.md` 準拠）で
**検索品質（FN/FP）を実測**して合格した場合のみ確定する、という条件で実装した。
作業ツリー（`--plugin-dir`）をロードしたセッションで、本 PR の改定コード（並列度10・
圧縮 toc_format.md・限定バッチング k=3・独立抽出 toc-updater）を実際に起動して計測した。

**実施内容**（2026-06-07）:

- gs-rules-k3（33 文書 → 15 グループ）／ gs-specs-k3（68 文書 → 29 グループ）を
  既定バッチ k=3（同一ディレクトリ近傍）で index → query-docs 相当を全クエリ実行 → 採点。
- グループ化は 33→15・68→29 と起動回数を ~1/2 に削減（案 A/C/B の効果を実証）。

**結果**（`score.py`、golden 期待答えに対する FN/FP・negative 違反、baseline 差分）:

| セクション | クエリ | FN | FP | negative 違反 | baseline 退行 |
| ---------- | ------ | -- | -- | ------------- | ------------- |
| rules      | 22     | 0  | 0  | 0             | なし          |
| specs      | 21     | 0  | 0  | 0             | なし          |

→ **k=3 の同一ディレクトリ近傍バッチングは検索品質を劣化させない**（context rot による
文書間混線は FN/FP に表れず）。各 toc-updater が複数文書を独立抽出する設計が機能した。
よって **B を既定有効（DEFAULT_MAX_BATCH=3）で確定**する。

- 合格基準：B 有効時に FN/FP がベースラインから有意に劣化しないこと → 満たした。
- 不合格時の手順（参考）：`--max-batch 1` で既定オフへ後退（A+C は維持）し再相談。
- 留意：本計測は各条件 1 回・小規模 golden（rules+specs 約 100 文書）。より大規模・小ファイル
  密集ディレクトリでは追試の価値がある（残課題）。

## 速度実測（主目的の検証）— 実施済み

品質（信頼性）に加え、本 Issue の主目的である**速度**を A/B 実測した。同一 9 文書
（`rules/core`、同一コード）を **k1（1 件/agent×9）** と **k3（3 件/agent×3）** で充填し、
各 toc-updater の `duration_ms` / `subagent_tokens` を計測（2026-06-07）。

| 指標（1 文書あたり） | k1（バッチなし） | k3（既定バッチ） | 改善         |
| -------------------- | ---------------- | ---------------- | ------------ |
| 処理時間             | 20.5s            | 12.7s            | **38% 短縮** |
| トークン             | 18,620           | 8,777            | **53% 削減** |
| 起動回数（9 文書）   | 9                | 3                | 1/3          |

トークン 53% 減は **C（toc_format.md 圧縮）＋ B（規約再読を k 件で 1 回に償却）** の効果。
1 文書あたり処理時間 38% 減はこの償却が wall-clock にも効いていることを示す。

**400 文書の fill wall-clock 試算**（波数 = ⌈起動数/並列度⌉、波内 wall = 各アーム実測 max）:

| 構成               | 起動数 | 波数 | 波内 wall | fill 合計    |
| ------------------ | ------ | ---- | --------- | ------------ |
| 旧（k=1・並列 5）  | 400    | 80   | ~30s      | **約 40 分** |
| 新（k=3・並列 10） | 134    | 14   | ~41s      | **約 10 分** |

→ **fill wall-clock 約 4.1× 高速化**（波数 80→14）。Issue が「実運用 2 時間の主因」と挙げた
メターン往復・context overflow 再開・compaction 損は**波数に比例**するため、実運用の改善幅は
この fill 試算（4.1×）よりさらに大きいと見込まれる。並列度 5→10（A）が波数を半減、
バッチング（B）が起動数を 1/3 にする、という 2 つの独立した乗算で効く。

- 留意：各条件 1 回・小規模サンプル。テールレイテンシ（並列内 max）が波内 wall を支配するため、
  大規模では分散の追試が望ましい（残課題）。

## 不採用案

- **量ベースのビンパッキング（トークン予算 B=30〜40K で k を決める）**：撤回。k の上限は
  トークン量でなく rot（質）で決まるため。

### 公式マルチエージェント機能の検討（不採用、2026-06-07 時点の公式ドキュメントで確認）

「Anthropic 公式のマルチエージェント機能でさらに速くできないか」を検討した。結論は **index-docs
（配布プラグイン SKILL の fan-out 充填）には不適**。判断の追跡可能性のため出典付きで記録する。

前提（共通の決定的制約）：index-docs は **マーケットプレイス配布のプラグイン SKILL** として
**エンドユーザのセッション**で動く。SKILL は markdown 指示であり、ランタイムに使える
オーケストレーション基盤は「その環境で保証されるもの」に限られる。採用済みの **subagents
（Agent ツール）こそが公式の "独立 fan-out" 向け基盤**であり、index-docs は既にこれを使っている。

| 機構                           | 設計思想                                | index-docs 適合   | 不採用の主因                                                                                                                                                                                                              |
| ------------------------------ | --------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Subagents（採用中）**        | 隔離ワーカー・結果のみ親へ返す          | ◎                 | —                                                                                                                                                                                                                         |
| **Dynamic Workflows**          | deterministic な fan-out スクリプト     | △（大規模時のみ） | research preview・ユーザ opt-in（`ultracode`/`/effort`/`/deep-research`）・**SKILL から起動不可**・`CLAUDE_CODE_DISABLE_WORKFLOWS` 等で無効化可                                                                           |
| **Agent Teams**                | 協調・反証する重量級チーム              | ✗（用途違い）     | **experimental・既定オフ（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` 要設定）**・ユーザ承認必須・teammate は完全セッションで「significantly more tokens」・推奨 3〜5（低 throughput）・公式が独立 fan-out は subagents へ誘導 |
| **Agent SDK / Managed Agents** | 自前/管理基盤の独立オーケストレーション | △                 | **プラグイン/SKILL モデルの放棄**＝独立サービス化（ユーザ API キー・別課金・別配布）                                                                                                                                      |

**Dynamic Workflows**（[docs](https://code.claude.com/docs/en/workflows.md)）：ループを会話外の
スクリプトに出してメターン往復・主コンテキスト肥大を消せる点は、ADR が挙げた実運用コスト要因に
合致し着眼は正しい。しかし research preview かつユーザの明示操作でのみ起動し、**プラグインの
SKILL からエンドユーザのランタイムで起動できない**。設定で無効化もできる。よって配布プラグインが
依存できない。加えて `parallel()` はバリアでテール律速を解消せず、低 tier では 16 同時が 429 を悪化
させうる。公式の subagent 比ベンチも未公開。

**Agent Teams**（[docs](https://code.claude.com/docs/en/agent-teams)）：teammate 同士が
「share findings, challenge each other, and coordinate」する協調・反証作業（research / parallel
review / competing hypotheses）向け。index-docs の充填は**各文書を独立抽出し通信不要・むしろ
隔離が要件**で、用途が正反対。公式は明示的に "Use subagents when you need quick, focused workers
that report back" / "Focused tasks where only the result matters" と誘導する。さらに experimental・
既定オフ・ユーザ承認必須・teammate が完全セッションで高トークン・推奨 3〜5 と、可用性・コスト・
throughput のいずれでも subagents に劣る。唯一の接点は plugin scope の subagent 定義を teammate
として流用できる点だが、これはユーザ手動操作であり index 高速化パスではない。

→ 公式マルチエージェントは「協調が価値を生む作業」のための機能であり、index-docs のような
**独立・大量・通信不要の fan-out** には subagents が正解。配布制約（preview/experimental/opt-in/
SKILL 非起動）も相まって、本 ADR は **subagents（Agent ツール）＋ A+C+B** を採用する。
ただし開発・テスト側（本リポジトリ。dev が opt-in 可能）でゴールデンセット計測や大規模 index を
回す用途では Workflow が有用なため、別途ハーネス化を検討する余地はある（残課題）。

## 追補: 連続ディスパッチ / claim-lease（Issue #29, 2026-06-07）

### 背景

採択時（#27）の Phase 2 は **バリア型 wave ループ**だった（最大 N 個を 1 メッセージで起動 → 全完了
待ち → `--work-status` 再走査 → 次 wave）。各 wave は **最も遅い 1 件**が次 wave 全体を律速する。
とくに案 B の限定バッチングは**グループサイズが不均一**（1/2/3 件混在）なため、同一 wave 内で
1 件グループが 3 件グループの完了を遊んで待つ無駄が出る。

バリアを選んでいた理由は、`run_in_background` で連続投入すると in-flight の entry がまだ
`completed` を書く前に `--work-status` を引いて **pending に見え二重起動する race** があったため。
これは安全側の妥協だった。

### 決定

**race を script 側の claim/lease で正しく解いたうえで、Phase 2 を連続ディスパッチ
（sliding-window）に変更し、配布既定とする。**

- **claim/lease（`toc_store.py`）**: 投入直前に entry を `--claim`（`claimed_at` をスタンプ）。
  `--work-status` は有効リース内を **in-flight** として `pending` から除外する。停止した Agent の
  stale lease は TTL（既定 900s）超過で `pending` に戻り再投入対象になる。→ 二重起動 race を根絶。
- **sliding-window（orchestrator）**: `run_in_background` で並列ウィンドウ（既定 10）を保ち、
  1 グループ完了通知ごとに次の未投入グループを claim → 起動して補充する。
- **再開（continuation）**: 新セッションの Phase 0 は `--work-status --lease-ttl 0` で前回 claim
  残骸を stale 扱いにし pending へ戻す（前回 Agent は終了済みのため二重投入の懸念なし）。

### 検証（dev セッション・隔離 key・本物 ToC 不可触）

- **機能スパイク**（4 件）: 完了通知での main-loop 再起動・claim による in-flight 除外（二重投入
  なし）・`next_action: merge` までの全フロー完遂を実証。
- **中規模 wall-clock 実測**（docs 全体 21 md → 9 グループ・サイズ不均一 `[2,3,3,3,2,3,2,1,2]`・
  並列度 P=3）: 連続型で実起動し各グループの実 `duration_ms` を収集、**同一 duration**から
  バリア型 makespan（wave 内 max の和）と連続型 makespan（list scheduling）を決定論 script で算出。

  | 方式                     | makespan   | 備考                                   |
  | ------------------------ | ---------- | -------------------------------------- |
  | バリア型                 | **129.6s** | wave 内 max `[45.1, 53.1, 31.4]s` の和 |
  | 連続型（sliding-window） | **113.3s** | 理想下限 107.6s に肉薄                 |
  | 改善                     | **12.6%**  | #29 予測「10〜30%」の範囲内            |

  バリア型は wave2 の最遅 53.1s が 31.8s/41.1s を遊ばせて律速。連続型はその中間テール待ちを
  除去する。**効くのはグループ数 > 並列度（複数 wave）のとき**で、大規模（400 件・wave 多数）ほど
  効果が増す。スパイク 4 + 中規模 9 = 計 13 グループの `run_in_background` 起動は全て成功した。
- 集計は決定論 script（手計算しない）。各条件 1 回・小規模サンプルのため、大規模での分散の追試は
  残課題。

### 配布既定: 連続固定（自動選択・バリア固定は不採用）

**規模で自動選択（groups > 並列度 で連続、以下はバリア）は不採用**とし、**連続固定**を採る。理由:

- 小規模（グループ数 ≤ 並列度 = 1 wave）では **連続型 makespan = バリア型 makespan = max(全グループ)**
  で速度差ゼロ。かつ補充サイクルが無いため markdown 制御の反復リスクも実質発生しない。
- よって自動選択が小規模で得るのは「foreground を使う（`run_in_background` 依存の回避）」のみで、
  そのために**バリア／連続の 2 制御パスを恒久維持する複雑性は割に合わない**。
- 連続固定の唯一の弱点（`run_in_background` 不可環境）は、異常時に foreground 一括起動へ
  フォールバックする運用注記で吸収でき、主フローは連続 1 本に保てる。

### 正しさとリスクの切り分け

- **正しさ（品質・全件処理）は両規模で claim/lease + `--work-status` 継続判定が担保**する。
  二重起動は claim の in-flight 除外、投入漏れ（window 縮小）は `--work-status` 再走査で `fill`
  回収、停止 Agent は stale lease の TTL 回収、compaction での履歴喪失は状態がファイル
  （`claimed_at`）にあるため `--work-status` 再実行で復元。連続制御が緩んでも**誤った ToC は出ない**。
- **崩れうるのは速度利得のみ**: markdown 指示での sliding-window 制御は会話内 Claude の遵守に
  依存し、大規模・長時間・compaction でウィンドウが縮むと利得が目減りしてバリア型に近づく
  （遅くなるだけ）。これは「正しさ」ではなく「速度」のリスク。
- **残課題**: ①大規模（400 件級）での連続 vs バリア実測、②`run_in_background` の配布エンドユーザ
  全環境（headless/CI/cron/旧版）での信頼性確認とフォールバック運用の明文化。

### 追補 2: 連続ディスパッチの決定論部分を script へ移した（2026-08-04）

上記「正しさとリスクの切り分け」は、sliding-window の制御が markdown 指示による AI の遵守に依存し、
**崩れうるのは速度利得のみ**と整理していた。この整理は claim/lease による正しさの担保について正しい
が、**速度利得が崩れる確率を過小に見ていた**。

空きスロットの計算は `window − len(in_flight_groups)`（走行中 **Agent** 数）でなければならない。
`len(in_flight)`（entry 数）で引くと過大に減算されて負になり、補充されないまま wave 実行へ逆戻り
する。この区別は SKILL.md の注意書き（`[IMPORTANT]` 付き）で AI に伝えていたが、**注意書きで
伝える設計そのものが誤りだった**。決定論的な算術を AI に毎ラウンド正しく再計算させる根拠はない。

そこで空きスロット計算・グループ選択・claim・`claimed`/`rejected` の振り分けを
`index_docs.py`（DES-005 §4.1.1 のラッパー）へ移し、ラッパーが **claim 済みの「今起動すべき
Agent 群」を返す**形にした。AI は返された配列で Agent を起動するだけになり、算術を行わない。

- **AI に残る責務**: Agent の起動と、判断（越境 symlink の承認・充填エラーへの対応）のみ
- **ウィンドウ幅（10）とバッチサイズ（3）は CLI に出さない**。呼び出し側が run ごとに判断する値
  ではないため、ラッパー内の定数とする。低 tier で 429 が出る場合の切り分けはコア CLI
  （`toc_store.py --work-status --max-batch N`）で行う
- **回帰をテストで固定**: `in_flight_groups` が `window` 以上のとき `available` が負にならず
  `action: wait` になることを統合テストで固定した（entry 数で引く実装に戻れば失敗する）

本追補は §「決定」の内容（claim/lease + sliding-window を配布既定とする）を変更しない。変えたのは
**その制御を誰が計算するか**である。
