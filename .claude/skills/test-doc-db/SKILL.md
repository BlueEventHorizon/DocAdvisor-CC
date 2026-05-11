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
テスト環境設計は `specs/test/DES-TST-001_test_environment_design.md` を参照。

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
`init_fixtures.sh setup` で自動インストール + store を行う。

## Layer 1: 自動テスト（API キー不要）

tempdir + Embedding モックで完全再現可能なテスト。

```bash
cd <project_root>
python3 -m unittest test_claude_skills.doc_db.test_doc_db_installed -v
```

### 結果の判定

- 全テスト PASS → Layer 1 完了を報告
- FAIL あり → 失敗テストの詳細を報告し、修正提案

## Layer 2: 手動テスト（API キー必須）

`init_fixtures.sh` でテスト環境を準備し、
DocAdvisor 本体にインストールされた `.claude/doc-db/scripts/` を使って
テスト専用ドキュメント（`test_claude_skills/fixtures/`）に対してスクリプトを実行する。

### 前提チェック

```bash
# OPENAI_API_KEY
python3 -c "import os; k=os.environ.get('OPENAI_API_KEY',''); print('OK' if k else 'NOT SET')"
# → NOT SET の場合、ユーザーに設定を依頼し中断

# テスト環境の状態確認
bash test_claude_skills/init_fixtures.sh status
```

### テスト実行手順

プロジェクトルートから全て実行する。

#### Step 1: テスト環境セットアップ

```bash
bash test_claude_skills/init_fixtures.sh setup
```

> プラグイン未インストールならインストールし、.doc_structure.yaml を
> テスト用テンプレートに差し替える。スクリプトは `test_claude_skills/fixtures/` 配下の
> テスト専用ドキュメントを参照するようになる。

#### Step 2: grep テスト（API キー不要）

```bash
python3 .claude/doc-db/scripts/grep_docs.py --category rules --keyword "MARKER_TEST_RULE"
# → test_claude_skills/fixtures/rules/test_rule.md がヒット

python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_REQ"
# → test_claude_skills/fixtures/specs/requirements/test_req.md がヒット

python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_DES" --doc-type design
# → test_claude_skills/fixtures/specs/design/test_des.md のみヒット
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

#### Step 5: リセット

```bash
bash test_claude_skills/init_fixtures.sh reset
```

> .doc_structure.yaml を復元し、ビルド成果物を削除する。
> reset が完了するまでテスト完了と報告しない。

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
- init_fixtures: setup/reset 正常完了
- 結果: 全ステップ PASS / 一部 FAIL
- 失敗: （あれば詳細）
```
