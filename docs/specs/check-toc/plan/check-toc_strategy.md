# check-toc 実装戦略

## アプローチ

**選択**: ボトムアップ（純関数優先）

**根拠**:

DES-009 のモジュール依存は浅く一方向（`SKILL.md → check_toc.py → toc_store / toc_utils → ファイル`）で、
新規技術も外部サービス連携も無い。したがってスケルトン先行で早期に全層を通す利得は小さい。

一方、本 feature の主たる不確実性は「判定規則そのものが正しいか」に集中している（境界値・skew・
`generated_at` の解析可否）。これは純関数として切り出せば I/O なしで検証できる（DES-009 §3.3 の `judge`）。
そのため基盤（`error_code` の追加）→ 純関数（判定・解析・metadata 読み取り）→ CLI 統合 → SKILL 公開の順に
積み上げ、各段でテストを伴わせる。

既存コードへの変更は `toc_store.py` の `ErrorCode` / `ERROR_CODES` への 2 件追加のみで、既存値は変更しない
（追加開発の原則: 既存コードは最小限のタッチで拡張する）。

## フェーズ

### フェーズ 1: 判定コアと error_code 基盤

- **目標**: 鮮度判定と `generated_at` 解析、metadata 読み取りが単体テストで検証済みの状態になる。
  ファイル I/O と CLI を伴わずに、REQ-005 FR-C02 の 5 判定すべてが再現できる
- **スコープ**: `toc_store.py` への `INVALID_MAX_AGE` / `TOC_READ_ERROR` 追加（DES-009 §5.2）、
  `check_toc.py` の `judge` / `parse_generated_at` / `read_toc_metadata`（DES-009 §3.3 / §4.2 / §4.3）、
  および `tests/scripts/test_check_toc.py` の該当テスト
- **検証ポイント**: `python3 -m unittest discover -s tests -p 'test_*.py'` が全件通る。
  **既存 `tests/scripts/test_toc_store.py` の `set(ERROR_CODES)` 完全一致検証を同時に更新すること**（下記リスク参照）。
  境界値（差 = `max_age`）が `fresh`、skew 内の未来時刻が `fresh` かつ `age_seconds=0`、
  skew 超過の未来時刻が `stale` / `generated_at_future` になることを確認する

### フェーズ 2: CLI 統合

- **目標**: `python3 plugins/doc-advisor/scripts/check_toc.py --key specs --max-age 86400` が
  実 ToC に対して JSON を返し、exit code が `status` に対応する
- **スコープ**: `check_toc.py` の `parse_args` / `main`、`toc_store.emit_json` による出力組み立て
  （DES-009 §4.1 / §5.1 / §5.3）、および引数検証・出力形式・副作用なしのテスト
- **検証ポイント**: 固定した `generated_at` を持つ fixture と注入した判定時刻の組で `fresh` / `stale` / `missing` の
  3 経路が単体テストで再現できること、存在しない key で `stale` / `missing` が返ること、
  実行後に ToC・`.toc_work/`・checksums が変化しないこと（`git status` で確認）。
  実 ToC に対する確認は補助とし、`--max-age` に十分大きい値を渡して `fresh` が返ることだけを見る
  （`generated_at` は時間経過で必ず閾値を超えるため、実 ToC が `fresh` であること自体を検証条件にしない）

### フェーズ 3: SKILL 公開

- **目標**: `/doc-advisor:check-toc --key specs --max-age 86400` が script の JSON のみを返す
- **スコープ**: `plugins/doc-advisor/skills/check-toc/SKILL.md`（DES-009 §2.2 / §3.2）。
  継承型 SKILL・`allowed-tools: Bash` のみ・`$ARGUMENTS` を解釈せず透過
- **検証ポイント**: SKILL を実際に起動し、**出力に説明文・要約が混ざらないこと**を目視確認する
  （REQ-005 FR-C03-4）。SKILL.md は自動テストの対象外（`docs/rules/implementation_guidelines.md`）のため、
  この確認はフェーズ 3 の唯一の検証手段である

## リスクと対策

| リスク                                                                                                                      | 影響度 | 対策（どのフェーズで潰すか）                                                                              |
| --------------------------------------------------------------------------------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------- |
| `tests/scripts/test_toc_store.py` が `set(ERROR_CODES)` を期待集合と完全一致で検証しており、`error_code` 追加で必ず失敗する | 高     | フェーズ 1 で `error_code` 追加と同一変更内で期待集合を更新する。後追いにするとテストが赤のまま次段へ進む |
| SKILL の起動経路が「JSON のみを返す」を満たせない（AI が要約を付ける）                                                      | 中     | フェーズ 3 で実起動して目視確認する。継承型を選ぶ設計判断（DES-009 §2.2）が前提であり、fork へ変えない    |
| `read_toc_metadata` の打ち切り実装が `toc.yaml` の構成変更に弱い                                                            | 低     | `formats/toc_format.md` の `metadata` 先行という規約に依拠し、フェーズ 1 のテストで打ち切り挙動を固定する |
| `toc_store.py` への追加が他 script へ波及する                                                                               | 低     | 追加のみで既存値を変更しない。フェーズ 1 の全体テスト実行で波及を検出する                                 |

## 本 feature で行わないこと

- `DES-005 §8.2` の `error_code` 値域の更新（追加 feature の frontmatter が宣言するとおり、
  旧設計書は書き換えず merge 時に反映する）
- `CHANGELOG.md` / version 関連ファイルの編集（リリースコミットで一括）
- `README.md` への `check-toc` の記載（配布物の説明はリリース時にまとめる。実装完了後の merge 作業で扱う）
