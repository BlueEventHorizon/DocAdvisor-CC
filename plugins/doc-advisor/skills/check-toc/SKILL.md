---
name: check-toc
description: |
  指定 key の ToC（AI 検索用インデックス）が、そのまま検索に使えるか（fresh）/
  作り直しが必要か（stale）を返す read-only な SKILL。閾値は呼び出し側が秒で渡す。
  上位層（forge 等）が検索前に索引を作り直すべきか判断するための材料を提供する。
  索引の生成・更新・削除は行わない（それは index-docs の責務）。
  トリガー:
  - 検索の前に ToC の鮮度を確認したいとき
  - "ToC は新しいか", "索引を作り直すべきか", "check-toc"
user-invocable: true
allowed-tools: Bash
argument-hint: "--key <key> --max-age <秒> | --all --max-age <秒>"
---

# check-toc

指定 key の ToC の鮮度を判定し、結果を JSON で返す。

> **このスキルの責務境界**: このスキルは「指定 key（または `--all` の予約 key `all`）の ToC が fresh か stale かを返す」ことのみを行う。索引の生成・更新（`index-docs`）や検索（`query-docs`）へ進んではならない。親が依頼している他の作業を引き継いではならない。
>
> **起動経路**: このスキルは **継承型 SKILL**（`context: fork` を指定しない）。script の stdout をそのまま親 context へ渡すために fork しない（fork 型 SKILL は隔離 context の AI が return 値を構築するため、出力に要約・説明が混入しうる）。起動経路の名称は `docs/rules/skill_launch_paths_definitions.md` の公式短縮名称に従う。

## Usage

```
/doc-advisor:check-toc --key <key> --max-age <秒>
/doc-advisor:check-toc --all --max-age <秒>
```

| Argument         | Description                                                                               |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `--key <key>`    | 対象 ToC の opaque key（上位層が決定）。`all` は予約語のため任意指定不可（reject される） |
| `--all`          | 単体モード。`--key` 省略と同義で予約 key `all` に解決する                                 |
| `--max-age <秒>` | **必須**。鮮度閾値を正の整数（秒）で指定する。既定値は持たない                            |

`--max-age` に既定値を持たないのは、閾値の所有者を呼び出し側に固定するためである。渡し忘れた場合は判定せず
`status=error` / `error_code=INVALID_MAX_AGE` を返す。

## Execution Flow

`$ARGUMENTS` を**解釈・補完せずそのまま**渡して次を 1 回だけ実行し、**stdout の JSON をそのまま返す**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_toc.py" $ARGUMENTS
```

`$ARGUMENTS` に上記以外の引数（親タスクの指示文を含む）が混ざっている場合、script が未知引数として reject する。
その場合は判定結果を推測せず、script の出力をそのまま返す。

## 出力

単一 JSON を返す。呼び出し側が読む答えは `freshness` である。

| field             | 内容                                                                                                        |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| `status`          | `ok`（判定完了） / `error`（判定不能）                                                                      |
| `error_code`      | `status=error` のときの理由コード。`status=ok` では `null`                                                  |
| `key`             | 解決後の key                                                                                                |
| `toc_path`        | `toc.yaml` の project-root 相対パス（不在時も期待パスを返す）                                               |
| `freshness`       | `fresh`（そのまま検索に使える） / `stale`（作り直しが必要）。`status=error` では `null`                     |
| `reason`          | `stale` の原因（`missing` / `outdated` / `generated_at_invalid` / `generated_at_future`）。診断用の補助情報 |
| `generated_at`    | ToC の `metadata.generated_at`。不在・解析不能では `null`                                                   |
| `age_seconds`     | 判定時刻と `generated_at` の差（秒）。算出できない場合は `null`                                             |
| `max_age_seconds` | 入力された閾値のエコー                                                                                      |

**ToC が存在しない場合も `status=ok` / `freshness=stale` / `reason=missing` を返す**（不在は鮮度確認の正常な結論であり、エラーではない）。

## 呼び出し側への注意

- **経路の選択は `freshness` で行い、exit code では行わない**。`stale` は正常な判定結果であり exit code は `0` である。exit code は `status` に対応する（`ok` → `0` / `error` → `1`）
- **`reason` に依存しない**。`freshness` だけで後続処理は決まる。`reason` は人間の切り分けと診断のための補助情報であり、値域が追加されうる
- 境界値の扱い・時刻のずれの許容幅・`generated_at` の解釈・ToC の探索方法は本 SKILL の内部判断である

## 禁止事項 [MANDATORY]

- ❌ **script の JSON 以外を最終出力に含めること**（説明文・要約・前置きを付けない）。呼び出し側は最終出力から JSON を読む
- ❌ JSON の field を加工・省略・翻訳すること
- ❌ `stale` / `missing` を受けて `index-docs` を起動すること（索引更新は呼び出し側の判断）
- ❌ `$ARGUMENTS` を解釈して不足引数を補完すること（閾値の既定値を本 SKILL が決めない）
- ❌ 書き込み系ツール・副作用を伴う `Bash` コマンドの使用、および ToC・`.toc_work/`・checksums の書き換え

> `allowed-tools` は「承認なしで使えるツールの allowlist」であり、書き込み系ツールの **物理 deny ではない**（`base/ADR-002 §E`）。read-only 性は本禁止事項・`check_toc.py` が読み取りのみで実装されていること・その単体テスト（副作用なしの検証）の多層で担保する。
