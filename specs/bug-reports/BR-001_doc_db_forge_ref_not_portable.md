# BR-001: doc-db スクリプト内の /forge:setup-doc-structure 参照が非ポータブル

**ステータス: 修正済み（2026-05-09）**

## 対象プラグイン

doc-db, doc-advisor, forge

## 対象ファイル

- `plugins/doc-db/scripts/_utils.py`（157行目）
- `plugins/doc-db/scripts/doc_structure.py`（558行目）
- 他 doc-advisor 5箇所、forge 3箇所（計10箇所）

## 現象

Python スクリプトが `/forge:setup-doc-structure` 等のスラッシュコマンド形式をハードコードしていた。プラグインモード専用の記法であり、スタンドアロンインストールでは解決できない。

## 修正内容（bw-cc-plugins 側）

全プラグインの Python スクリプト内のスラッシュコマンド形式（計10箇所）を環境非依存な表記（`setup-doc-structure` 等、先頭 `/` なし・プラグインプレフィックスなし）に変更。回帰防止テスト `TestNoSlashCommandRefsInScripts` を `tests/common/test_plugin_integrity.py` に追加。

## 暫定対処（setup.sh 側）

`install_optional_plugin` の `_transform_plugin` 関数に `/forge:setup-doc-structure` → `/setup-doc-structure` の sed ルールを追加済み。上流修正後はマッチしないため無害な安全ネットとして残留。
