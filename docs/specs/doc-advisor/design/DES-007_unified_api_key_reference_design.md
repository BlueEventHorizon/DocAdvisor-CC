# DES-007 統一 API KEY 参照規約 設計書

## メタデータ

| 項目     | 値                                          |
| -------- | ------------------------------------------- |
| 設計ID   | DES-007                                     |
| 関連要件 | FNC-004                                     |
| 関連設計 | DES-006（doc-advisor セマンティック検索）   |
| 作成日   | 2026-05-16                                  |
| 対象     | OpenAI Embedding API を利用する全プラグイン |

## 1. 概要

OpenAI Embedding API を呼び出すプラグイン（doc-advisor / doc-db 他）の API KEY 参照ロジックを統一する。各プラグインは **独立して同型の `get_api_key()` を実装** し、cross-plugin import を行わない。

## 2. 参照規約

### 2.1 解決順序

```
OPENAI_API_DOCDB_KEY     ← 優先
    ↓ 未設定
OPENAI_API_KEY           ← フォールバック
    ↓ 未設定
""                       ← 空文字列（既存契約と互換）
```

### 2.2 `get_api_key()` の実装契約

各プラグインの `embedding_api.py`（または相当モジュール）に以下と同型の関数を実装する:

```python
import os

OPENAI_API_KEY_ENV = "OPENAI_API_DOCDB_KEY"
_FALLBACK_ENV = "OPENAI_API_KEY"


def get_api_key() -> str:
    """OpenAI API キーを解決する。
    OPENAI_API_DOCDB_KEY 優先、未設定なら OPENAI_API_KEY にフォールバック。
    両方未設定なら空文字列を返す（既存契約と互換）。"""
    return os.environ.get(OPENAI_API_KEY_ENV) or os.environ.get(_FALLBACK_ENV, "")
```

### 2.3 エラーメッセージの統一文言

各プラグインの API 認証エラー / API KEY 未設定時のメッセージ・案内テンプレート:

```
API 認証エラー (401)。OPENAI_API_DOCDB_KEY（または OPENAI_API_KEY）が正しいか確認してください。
```

```
OPENAI_API_DOCDB_KEY（または OPENAI_API_KEY）が設定されていません。
export OPENAI_API_DOCDB_KEY='your-api-key' を実行してください。
```

## 3. cross-plugin import を採用しない理由

| 案                                          | 採否   | 理由                                                                                                                                          |
| ------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 各プラグイン内で独立実装（採用案）          | 採用   | プラグイン独立性を保つ。`forge:clean-rules` で問題化している cross-plugin `sys.path` 操作のパターンを他プラグインに持ち込まない               |
| 別プラグインの `embedding_api.py` を import | 不採用 | install 環境（`~/.claude/plugins/cache/...`）でパス解決が壊れることが既知（forge:clean-rules で実証済みの既存バグ）。同じパターンを増やさない |
| 共通パッケージとして切り出し PyPI 配布      | 不採用 | 「外部依存禁止」(`docs/rules/implementation_guidelines.md`「Python スクリプトは標準ライブラリのみ使用する」) と矛盾する                       |

実装の重複は数行であり、独立実装による保守コストよりプラグイン独立性のメリットが大きい。

## 4. テスト設計

### 4.1 テストパターン

各プラグインの `tests/{plugin}/scripts/test_embedding_api.py` で以下の 4 ケースを検証する:

| ケース                          | 環境変数の状態                                              | 期待値                      |
| ------------------------------- | ----------------------------------------------------------- | --------------------------- |
| `OPENAI_API_DOCDB_KEY` のみ設定 | `OPENAI_API_DOCDB_KEY=docdb-key`、`OPENAI_API_KEY` 未設定   | `"docdb-key"`               |
| `OPENAI_API_KEY` のみ設定       | `OPENAI_API_DOCDB_KEY` 未設定、`OPENAI_API_KEY=base-key`    | `"base-key"`                |
| 両方設定                        | `OPENAI_API_DOCDB_KEY=docdb-key`、`OPENAI_API_KEY=base-key` | `"docdb-key"`（DOCDB 優先） |
| 両方未設定                      | `OPENAI_API_DOCDB_KEY` 未設定、`OPENAI_API_KEY` 未設定      | `""`（空文字列）            |

### 4.2 環境変数モックパターン

```python
import os
import unittest
from unittest.mock import patch


class TestGetApiKey(unittest.TestCase):
    def test_docdb_key_only(self):
        with patch.dict(os.environ, {"OPENAI_API_DOCDB_KEY": "docdb-key"}, clear=True):
            self.assertEqual(get_api_key(), "docdb-key")

    def test_fallback_key_only(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "base-key"}, clear=True):
            self.assertEqual(get_api_key(), "base-key")

    def test_both_set_prefers_docdb(self):
        env = {"OPENAI_API_DOCDB_KEY": "docdb-key", "OPENAI_API_KEY": "base-key"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_api_key(), "docdb-key")

    def test_neither_set(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_api_key(), "")
```

## 5. 移行性

### 5.1 互換性

| ユーザー状態                      | 動作                                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY` のみ設定（従来） | フォールバック経路で従来通り動作。破壊的変更ではない                                    |
| `OPENAI_API_DOCDB_KEY` のみ設定   | 全プラグインが同 KEY を共有                                                             |
| 両方設定                          | `OPENAI_API_DOCDB_KEY` が優先される。`OPENAI_API_KEY` は他用途（別 API 等）のまま残せる |

### 5.2 既存ユーザーへの案内

破壊的変更ではないため、明示的なマイグレーション手順は不要。README / 各 SKILL.md のエラーメッセージで `OPENAI_API_DOCDB_KEY` の存在を案内する。

## 改定履歴

| 日付       | バージョン | 内容                                                                                               |
| ---------- | ---------- | -------------------------------------------------------------------------------------------------- |
| 2026-05-16 | 1.0        | 初版作成。誤配置されていた doc-db/DES-028 §3.4 を横断主題として doc-advisor 側へ移動し、永続原則化 |
