# COMMON-REQ-002: エラーハンドリングポリシー要件定義書

**作成日**: 2026-03-23
**作成者**: k_terada

## 概要

例外処理における「不具合の隠蔽」を防止し、問題の早期発見とデバッグ容易性を保証するためのポリシーを定義する。
サイレントフォールバック（内部バグを握りつぶしてデフォルト値を返す処理）を禁止し、外部要因のエラーのみを許容対象とする。

## 適用範囲

本要件は、プロジェクト内の全ての Python スクリプトおよび SKILL.md に適用する。

### 背景

コミット `7c14919`（v0.0.25）および `3a2c8c1`（v0.0.26）で、`except Exception` によるバグ隠蔽パターンをプロジェクト全体から除去した。本要件はその設計判断を要件として明文化するものである。

## 用語定義

| 用語                     | 定義                                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 外部要因エラー           | コード外の環境に起因するエラー。ファイル I/O 失敗、ネットワーク障害、ユーザー入力の不正等。発生は予測可能だがコードでは防止できない |
| 内部バグ                 | コード自体の欠陥に起因するエラー。TypeError、KeyError、IndexError、ZeroDivisionError 等。テストとコード修正で防止すべきもの         |
| サイレントフォールバック | 内部バグを `try/except` で握りつぶし、デフォルト値やエラー前の状態を返すことで、問題の存在を呼び出し元から隠す処理パターン          |

## 機能要件

### FR-01: 例外キャッチの原則

| ID      | 要件                                                                                                   |
| ------- | ------------------------------------------------------------------------------------------------------ |
| FR-01-1 | 例外のキャッチは**外部要因エラー**に限定する。内部バグを握りつぶしてはならない                         |
| FR-01-2 | `except Exception` や `except:` による包括的キャッチを禁止する。キャッチする例外は具体的な型で指定する |
| FR-01-3 | 内部バグ（TypeError、KeyError、IndexError、AttributeError 等）は呼び出し元に伝播させる                 |

### FR-02: 許容される例外キャッチ

| ID      | 要件                                                                                                                                                          |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-02-1 | ファイル I/O エラー（FileNotFoundError、IOError、OSError、UnicodeDecodeError）のキャッチは許容する                                                            |
| FR-02-2 | ネットワーク通信エラー（ConnectionError、TimeoutError 等）のキャッチは許容する                                                                                |
| FR-02-3 | 型変換の試行（`int()` 等の ValueError）のキャッチは許容する。ただし try ブロックは変換処理のみに限定する                                                      |
| FR-02-4 | HTTP サーバーのリクエスト処理における `except Exception` は、フレームワークの標準パターンとして許容する。ただし `handle_error()` でエラーを適切に処理すること |

### FR-03: エラー報告

| ID      | 要件                                                                                                     |
| ------- | -------------------------------------------------------------------------------------------------------- |
| FR-03-1 | 例外をキャッチした場合、エラー情報を呼び出し元に返すか stderr に出力する。握りつぶして無視してはならない |
| FR-03-2 | JSON 出力スクリプトでは `{"status": "error", "message": "..."}` 形式でエラーを返す                       |
| FR-03-3 | 警告・エラーメッセージは `sys.stderr` に出力する（`print()` のデフォルト stdout と混在させない）         |

### FR-04: 純粋関数の例外

| ID      | 要件                                                                                                                                          |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-04-1 | 副作用を持たない純粋関数（`fn(data) -> data`）内で発生する例外はコードバグである。`try/except` でロールバックや元データ返却を行ってはならない |
| FR-04-2 | 純粋関数のエラーハンドリングはテストで保証する。実行時の防御的キャッチは不要                                                                  |

## 設計パターン

### ✅ 正しいパターン: 外部要因のみキャッチ

```python
def load_config(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError as e:
        return {'status': 'error', 'message': str(e)}
    except (IOError, OSError, UnicodeDecodeError) as e:
        return {'status': 'error', 'message': f"読み込み失敗: {e}"}

    # パース処理 — ここでの例外はバグなので try で囲まない
    config = parse_config(content)
    return {'status': 'ok', 'config': config}
```

### ❌ 禁止パターン: サイレントフォールバック

```python
# NG — 内部バグを握りつぶしてデフォルト値を返す
def load_config(path):
    try:
        content = open(path).read()
        config = parse_config(content)
        return {'status': 'ok', 'config': config}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}  # parse_config のバグも隠蔽
```

### ✅ 正しいパターン: 純粋関数は例外を伝播

```python
# マイグレーション関数は純粋関数 — 例外はバグとして伝播
def apply_migrations(content, detected_version):
    targets = [v for v in sorted(MIGRATIONS.keys())
               if detected_version < v <= CURRENT_VERSION]

    for v in targets:
        content = MIGRATIONS[v](content)  # 例外はバグ → 伝播

    return content
```

### ❌ 禁止パターン: 純粋関数のロールバック

```python
# NG — 純粋関数のバグを隠蔽して元データを返す
def apply_migrations(content, detected_version):
    original = content
    try:
        for v in targets:
            content = MIGRATIONS[v](content)
    except Exception:
        return original  # バグが隠蔽され、旧形式データが黙って使われる
    return content
```

## 判断フローチャート

```
例外が発生した
  │
  ├─ 外部要因か？（ファイル I/O、ネットワーク、ユーザー入力）
  │   ├─ Yes → 具体的な例外型でキャッチし、エラーを報告する（FR-02）
  │   └─ No → 内部バグ → 伝播させる（FR-01-3）
  │
  └─ 純粋関数内か？
      ├─ Yes → try/except を使わない。テストで保証する（FR-04）
      └─ No → 上記の外部要因判定に従う
```

## 適用済み箇所

| バージョン | 対象                      | 内容                                                            |
| ---------- | ------------------------- | --------------------------------------------------------------- |
| v0.0.25    | プロジェクト全体          | `except Exception` を具体的な例外型に限定（コミット `7c14919`） |
| v0.0.26    | プロジェクト全体          | 残存するバグ隠蔽フォールバックの除去（コミット `3a2c8c1`）      |
| v0.0.26    | COMMON-REQ-001 FR-04-1    | 純粋関数のロールバック禁止に要件文を修正                        |
| v0.0.26    | toc_utils.py              | `except Exception` → `except (IOError, OSError)` に限定         |
| v0.0.26    | resolve_doc_references.py | `except Exception` → 具体的な例外型に限定                       |
