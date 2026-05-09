---
name: test-doc-db
description: |
  TST-001 テスト仕様書に基づき doc-db プラグインの機能テストを実行する。
  Layer 1（自動テスト・API キー不要）と Layer 2（手動テスト・実 API）の2層構成。
  トリガー: "doc-db テスト", "test doc-db", "doc-db の機能テスト"
disable-model-invocation: true
---

# /test-doc-db

TST-001 テスト仕様書（`specs/test/TST-001_doc_db_functional_test.md`）に基づき doc-db の機能テストを実行する。

## 引数

- `--layer1` : Layer 1 自動テスト（API キー不要）を実行
- `--layer2` : Layer 2 手動テスト（API キー必須）を実行
- `--all` : 両方を実行（Layer 1 → Layer 2 の順）
- 引数なし : Layer 1 のみ実行

## 前提条件

### Layer 1

bw-cc-plugins ソースから直接インポートするため、事前インストール不要。

### Layer 2

DocAdvisor 本体に doc-db がインストール済みであること。
未インストールの場合、ユーザーに確認してからインストールする:

```bash
bash setup.sh --source bw-cc-plugins/plugins/doc-advisor --with-doc-db .
```

## Layer 1: 自動テスト（API キー不要）

tempdir + Embedding モックで完全再現可能なテスト。

```bash
cd <project_root>
python3 -m unittest tests.doc_db.test_doc_db_installed -v
```

### 結果の判定

- 全テスト PASS → Layer 1 完了を報告
- FAIL あり → 失敗テストの詳細を報告し、修正提案

## Layer 2: 手動テスト（API キー必須）

store/restore パターンで `.doc_structure.yaml` をテスト用に差し替え、
DocAdvisor 本体にインストールされた `.claude/doc-db/scripts/` を使って
テスト専用ドキュメント（`tests/fixtures/doc_db/`）に対してスクリプトを実行する。

### 前提チェック

```bash
# 1. OPENAI_API_KEY
python3 -c "import os; k=os.environ.get('OPENAI_API_KEY',''); print('OK' if k else 'NOT SET')"
# → NOT SET の場合、ユーザーに設定を依頼し中断

# 2. doc-db インストール確認
ls .claude/doc-db/scripts/build_index.py
# → 存在しない場合、インストールを提案
```

### テスト実行手順

プロジェクトルートから全て実行する。

#### Step 1: store（.doc_structure.yaml を退避）

```bash
cp .doc_structure.yaml .doc_structure.yaml.bak
cp tests/fixtures/doc_db_test_doc_structure.yaml .doc_structure.yaml
```

> これにより doc-db のスクリプトは `tests/fixtures/doc_db/` 配下のテスト専用
> ドキュメントを参照するようになる。プロジェクト実体のドキュメントには一切触れない。

#### Step 2: grep テスト（API キー不要）

```bash
python3 .claude/doc-db/scripts/grep_docs.py --category rules --keyword "MARKER_TEST_RULE"
# → tests/fixtures/doc_db/rules/test_rule.md がヒット

python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_REQ"
# → tests/fixtures/doc_db/specs/requirements/test_req.md がヒット

python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_DES" --doc-type design
# → tests/fixtures/doc_db/specs/design/test_des.md のみヒット
```

#### Step 3: build テスト（API キー必須）

```bash
python3 .claude/doc-db/scripts/build_index.py --category rules --check
# → {"status": "stale", "reason": "index_not_found"}

python3 .claude/doc-db/scripts/build_index.py --category rules --full
# → {"status": "ok", ..., "build_state": "complete"}

python3 .claude/doc-db/scripts/build_index.py --category specs --full
# → {"status": "ok"}
# → .claude/doc-db/index/specs/ に requirement_index.json, design_index.json

python3 .claude/doc-db/scripts/build_index.py --category rules --check
# → {"status": "fresh"}
```

#### Step 4: search テスト（API キー必須、lex 除く）

```bash
python3 .claude/doc-db/scripts/search_index.py --category rules --query "variable naming" --mode lex
# → results に test_rule.md のチャンクがヒット

python3 .claude/doc-db/scripts/search_index.py --category rules --query "error handling" --mode emb
# → api_calls.embedding: 1

python3 .claude/doc-db/scripts/search_index.py --category rules --query "naming convention" --mode hybrid
# → breakdown に emb + lex

python3 .claude/doc-db/scripts/search_index.py --category specs --query "authentication" --mode rerank
# → breakdown に emb + lex + rerank, api_calls.rerank: 1

python3 .claude/doc-db/scripts/search_index.py --category specs --query "session" --mode lex --doc-type requirement
# → requirement のチャンクのみ
```

#### Step 5: restore + クリーンアップ

```bash
# .doc_structure.yaml を復元
mv .doc_structure.yaml.bak .doc_structure.yaml

# ビルド成果物を削除
rm -rf .claude/doc-db/index
```

> 復元忘れ防止: restore が完了するまでテスト完了と報告しない。

## 結果報告

テスト完了後、以下の形式で報告する:

```
## doc-db 機能テスト結果

- 実行日: YYYY-MM-DD
- bw-cc-plugins: <branch> (<commit short hash>)

### Layer 1（自動テスト）
- 結果: X/Y PASS
- 失敗: （あれば詳細）

### Layer 2（手動テスト）
- store/restore: 正常完了
- 結果: 全ステップ PASS / 一部 FAIL
- 失敗: （あれば詳細）
```
