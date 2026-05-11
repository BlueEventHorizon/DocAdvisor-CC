# BR-002: anvil SKILL.md 内の /doc-advisor: 参照が非ポータブル

**ステータス: 変更不要と判断（2026-05-09）**

## 対象プラグイン

anvil

## 対象ファイル

- `plugins/anvil/skills/impl-issue/SKILL.md`（149, 155, 161, 194, 219行目）

## 現象

anvil の `impl-issue` SKILL.md が `/doc-advisor:query-specs`、`/doc-advisor:query-rules` というクロスプラグイン参照を複数箇所で使用している。プラグインモードでは正しく解決されるが、setup.sh によるスタンドアロンインストールでは `/query-specs`、`/query-rules` に変換する必要がある。

## 判断（bw-cc-plugins 側）

SKILL.md 内のクロスプラグイン参照（64箇所）は、プラグインモード（一次配布形態）で名前空間付きが必須のため変更不要と判断。スタンドアロンモードは setup.sh 側の sed 変換で対処。

## 暫定対処（setup.sh 側）

`install_optional_plugin` の `_transform_plugin` 関数に `/doc-advisor:` → `/` の sed ルールを追加して対処済み。この変換は今後も必要（上流で変更しない方針のため）。
