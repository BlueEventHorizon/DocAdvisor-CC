# TST-001: doc-db 機能テスト仕様書

> Created by k2moons
> 作成日: 2026-05-09
> 最終更新: 2026-05-09
> ステータス: 第5版

## 概要

doc-db プラグインの機能テスト仕様書。
`setup.sh` によるインストール後、doc-db の主要スクリプト（`grep_docs.py`, `build_index.py`, `search_index.py`）が正しく動作することを検証する。

**対象**: doc-db プラグインの「インストール後のスクリプト動作」を検証する。
`setup.sh` 自体のインストールテストは `test_claude_setup/test_optional_plugins.sh` が担当する。

### テスト構成

テストは2層に分かれる。

| 層 | 方式 | API キー | 再現性 | 実行場所 |
| --- | --- | --- | --- | --- |
| **Layer 1: 自動テスト** | Python unittest + Embedding モック | 不要 | 完全再現 | `test_claude_skills/doc_db/` |
| **Layer 2: 手動テスト** | CLI 実行 + 実 API + store/restore | 必須 | API 応答に依存 | DocAdvisor 本体（store/restore で保護） |

### 技法: store/restore パターン

`.doc_structure.yaml` を差し替えて、プロジェクト自身の rules/specs ではなく**テスト専用のドキュメント**を対象にする技法を使用する。
この技法は `bw-cc-plugins/.claude/skills/update-forge-toc/scripts/swap_doc_config.py` に由来し、
`test_claude_skills/init_fixtures.sh` で自動化されている。

```bash
bash test_claude_skills/init_fixtures.sh setup    # インストール + store
bash test_claude_skills/init_fixtures.sh reset    # restore + clean
```

自動テスト（Layer 1）では `tempfile.TemporaryDirectory()` に `.doc_structure.yaml` とテスト用ドキュメントを動的生成するため、store/restore は不要。
手動テスト（Layer 2）で既存プロジェクト上で実行する場合に、この技法を使用する。

テスト環境の詳細設計は `DES-TST-001_test_environment_design.md` を参照。

## 前提条件

### 環境変数

| 変数名 | Layer 1 | Layer 2 | 用途 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 不要（モック） | **必須** | OpenAI API 呼び出し |

> **将来計画**: 汎用の `OPENAI_API_KEY` は権限が広すぎるため、制約を高めた `OPENAI_API_BWCC_KEY` を定義予定。必要な権限は bw-cc-plugins 側の AI と協議して決定する。
> 移行後は本仕様書と関連スクリプトの環境変数名を更新すること。

### 必要な API 権限（暫定・Layer 2 のみ）

| エンドポイント | モデル | 用途 |
| --- | --- | --- |
| `POST /v1/embeddings` | `text-embedding-3-small` | チャンク Embedding 生成 |
| `POST /v1/chat/completions` | `gpt-4o-mini` | LLM Rerank |

### ソフトウェア要件

- Python 3.10+
- Layer 1: 事前インストール不要（bw-cc-plugins ソースからフォールバック）
- Layer 2: `setup.sh` によるインストール済み環境（`--with-doc-db` 指定）
- `.doc_structure.yaml` が正しく設定されていること

### setup.sh のコマンド構文

```bash
# --source は doc-advisor プラグインのパスを指定、TARGET_DIR は位置引数（末尾）
bash setup.sh --source bw-cc-plugins/plugins/doc-advisor --with-doc-db TARGET_DIR

# 例: test_project にインストール
bash setup.sh --source bw-cc-plugins/plugins/doc-advisor --with-doc-db test_claude_setup/test_project

# 例: DocAdvisor 本体にインストール
bash setup.sh --source bw-cc-plugins/plugins/doc-advisor --with-doc-db .
```

> `--target` オプションは存在しない。TARGET_DIR は最後の位置引数として渡す。
> 非対話実行時は `yes |` でパイプする。

---

## Layer 1: 自動テスト（API キー不要）

### 設計方針

bw-cc-plugins のテストパターン（`tests/doc_db/test_integration.py` 等）に準拠する。

- **一時ディレクトリ**: `tempfile.TemporaryDirectory()` にテスト用プロジェクトを構築
- **`.doc_structure.yaml` 動的生成**: テストケースごとに最適な構成を書き出す
- **Embedding モック**: `call_embedding_api` / `call_embedding_api_single` を固定ベクトルに差し替え
- **Rerank モック**: `llm_rerank.rerank` を候補リスト逆順返却に差し替え
- **`OPENAI_API_KEY`**: ダミー値 `"dummy"` を設定（スクリプトの存在チェック通過用）

### テストファイル配置

```
test_claude_skills/doc_db/
├── __init__.py
├── test_doc_db_installed.py      ← Layer 1 自動テスト（本仕様の対象）
└── conftest.py                   ← 共通フィクスチャ（必要に応じて追加）
```

> bw-cc-plugins 内の `tests/doc_db/` はプラグインソースから直接インポートする。
> 本テストは **setup.sh でインストールされた後のスクリプト** を対象とし、
> `test_claude_setup/test_project/.claude/doc-db/scripts/` からインポートする。

### L1-1: テスト用プロジェクト構成

各テストの `setUp` で以下の構造を一時ディレクトリに構築する。

```
<tmpdir>/
├── .doc_structure.yaml          ← 動的生成
├── rules/
│   ├── coding_standards.md      ← テスト用ドキュメント
│   └── naming_convention.md     ← テスト用ドキュメント
└── specs/
    ├── requirements/
    │   └── user_auth.md         ← テスト用ドキュメント
    └── design/
        └── auth_api.md          ← テスト用ドキュメント
```

テスト用ドキュメントの内容は**一意なマーカー文字列**を含める（検索結果の特定に使用）。

```python
DOC_STRUCTURE_YAML = """\
rules:
  root_dirs:
    - rules/
  doc_types_map:
    rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []
specs:
  root_dirs:
    - specs/requirements/
    - specs/design/
  doc_types_map:
    specs/requirements/: requirement
    specs/design/: design
  patterns:
    target_glob: "**/*.md"
    exclude: []
"""

RULES_CODING = """\
# Coding Standards
## Naming
Use camelCase for variables. MARKER_RULE_CODING_001.
"""

RULES_NAMING = """\
# Naming Convention
## Functions
Use snake_case for functions. MARKER_RULE_NAMING_002.
"""

SPECS_REQ = """\
# User Authentication Requirements
## FR-001: Login
Users can log in with email and password. MARKER_SPEC_REQ_003.
"""

SPECS_DESIGN = """\
# Authentication API Design
## Endpoints
POST /api/auth/login. MARKER_SPEC_DES_004.
"""
```

### L1-2: Embedding モック

```python
FIXED_DIM = 1536
FIXED_VEC = [0.1] * FIXED_DIM

def mock_embedding_batch(texts, _api_key):
    return [list(FIXED_VEC) for _ in texts]

def mock_embedding_single(_text, _api_key):
    return list(FIXED_VEC)

def mock_rerank(_query, candidates, _api_key):
    return (
        list(reversed(candidates)),
        {
            "fallback_used": False,
            "rerank_error": None,
            "api_calls": 1,
            "token_usage": 100,
            "candidate_count": len(candidates),
        },
    )
```

### L1-3: テストケース一覧

| テストID | 関数名 | 検証内容 |
| --- | --- | --- |
| L1-3-01 | `test_import_chain` | 全モジュールのインポート成功 |
| L1-3-02 | `test_grep_rules_keyword_match` | grep_docs: rules キーワードヒット |
| L1-3-03 | `test_grep_specs_keyword_match` | grep_docs: specs キーワードヒット |
| L1-3-04 | `test_grep_no_match` | grep_docs: ヒットなし → 空配列 |
| L1-3-05 | `test_grep_doc_type_filter` | grep_docs: --doc-type で requirement のみ |
| L1-3-06 | `test_build_check_no_index` | build_index --check: index 未構築 → stale |
| L1-3-07 | `test_build_full_rules` | build_index --full: rules ビルド成功 |
| L1-3-08 | `test_build_full_specs_multi_doctype` | build_index --full: specs で requirement + design 分離ビルド |
| L1-3-09 | `test_build_no_api_key` | build_index: API キー未設定 → エラー |
| L1-3-10 | `test_build_check_after_build` | build_index --check: ビルド後 → fresh |
| L1-3-11 | `test_search_lex_mode` | search_index: lex モード動作 |
| L1-3-12 | `test_search_emb_mode` | search_index: emb モード動作 |
| L1-3-13 | `test_search_hybrid_mode` | search_index: hybrid モード動作 |
| L1-3-14 | `test_search_rerank_mode` | search_index: rerank モード動作 |
| L1-3-15 | `test_search_result_schema` | search_index: 結果スキーマ検証（全必須フィールド） |
| L1-3-16 | `test_search_doc_type_filter` | search_index: --doc-type で requirement のみ検索 |
| L1-3-17 | `test_search_auto_rebuild` | search_index: ファイル変更 → 自動リビルド |
| L1-3-18 | `test_path_transform_no_plugin_root` | スクリプト内に `CLAUDE_PLUGIN_ROOT` 残留なし |

### L1-4: テスト実行コマンド

```bash
cd /path/to/DocAdvisor

# Layer 1 自動テスト実行（API キー不要）
# bw-cc-plugins ソースから直接インポートするため、setup.sh の事前実行は不要
python3 -m unittest test_claude_skills.doc_db.test_doc_db_installed -v
```

---

## Layer 2: 手動テスト（実 API + store/restore）

Layer 1 でカバーできない「実際の OpenAI API との通信」を検証する。
Embedding の品質（ベクトルの意味的精度）や Rerank の実動作を確認する。

**実行方式**: DocAdvisor 本体に doc-db をインストールし、store/restore パターンで
`.doc_structure.yaml` をテスト用に差し替えて、テスト専用ドキュメントに対してスクリプトを実行する。
プロジェクト実体のドキュメントには一切触れない。

### テスト用リソース

#### テスト用テンプレート

`test_claude_skills/test_doc_structure.yaml` — store 時にプロジェクトルートにコピーされる。

```yaml
rules:
  root_dirs:
    - test_claude_skills/fixtures/rules/
  doc_types_map:
    test_claude_skills/fixtures/rules/: rule
specs:
  root_dirs:
    - test_claude_skills/fixtures/specs/requirements/
    - test_claude_skills/fixtures/specs/design/
  doc_types_map:
    test_claude_skills/fixtures/specs/requirements/: requirement
    test_claude_skills/fixtures/specs/design/: design
```

#### テスト用ドキュメント

```
test_claude_skills/fixtures/
├── rules/
│   └── test_rule.md        ← MARKER_TEST_RULE_001, MARKER_TEST_RULE_002
└── specs/
    ├── requirements/
    │   └── test_req.md     ← MARKER_TEST_REQ_001, MARKER_TEST_REQ_002
    └── design/
        └── test_des.md     ← MARKER_TEST_DES_001, MARKER_TEST_DES_002
```

各ファイルに一意なマーカー文字列を含む。検索結果の正確な照合に使用する。

### L2-0: テスト環境セットアップ

```bash
cd /path/to/DocAdvisor

# OPENAI_API_KEY の確認
python3 -c "import os; k=os.environ.get('OPENAI_API_KEY',''); print('OK' if k else 'NOT SET')"
# → NOT SET の場合、中断

# プラグインインストール + store（未インストールならインストールも実行）
bash test_claude_skills/init_fixtures.sh setup
```

> `init_fixtures.sh setup` は doc-db のインストール確認、.doc_structure.yaml の
> バックアップ・差し替えを自動で行う。

### L2-2: grep テスト（API キー不要）

```bash
# rules 検索
python3 .claude/doc-db/scripts/grep_docs.py --category rules --keyword "MARKER_TEST_RULE"
# → test_claude_skills/fixtures/rules/test_rule.md がヒット

# specs 検索
python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_REQ"
# → test_claude_skills/fixtures/specs/requirements/test_req.md がヒット

# doc_type フィルタ
python3 .claude/doc-db/scripts/grep_docs.py --category specs --keyword "MARKER_TEST_DES" --doc-type design
# → design のみヒット、requirement はヒットしない

# ヒットなし
python3 .claude/doc-db/scripts/grep_docs.py --category rules --keyword "zzz_nonexistent_zzz"
# → results が空配列
```

### L2-3: build テスト（API キー必須）

```bash
# --check（インデックス未構築）
python3 .claude/doc-db/scripts/build_index.py --category rules --check
# → {"status": "stale", "reason": "index_not_found"}

# --full ビルド
python3 .claude/doc-db/scripts/build_index.py --category rules --full
# → {"status": "ok", ..., "build_state": "complete"}

# specs マルチ doc_type ビルド（requirement + design 分離）
python3 .claude/doc-db/scripts/build_index.py --category specs --full
# → {"status": "ok"}
# → .claude/doc-db/index/specs/requirement_index.json 生成
# → .claude/doc-db/index/specs/design_index.json 生成

# --check（ビルド後）
python3 .claude/doc-db/scripts/build_index.py --category rules --check
# → {"status": "fresh"}

# API キー未設定時のエラー確認
OPENAI_API_KEY="" python3 .claude/doc-db/scripts/build_index.py --category rules --full
# → 終了コード 1、"error": "OPENAI_API_KEY is required"
```

### L2-4: search テスト（API キー必須、lex 除く）

> L2-3 でインデックスがビルド済みであること。

```bash
# lex モード（API キー不要）
python3 .claude/doc-db/scripts/search_index.py --category rules --query "variable naming" --mode lex
# → results に test_rule.md のチャンクがヒット

# emb モード
python3 .claude/doc-db/scripts/search_index.py --category rules --query "error handling" --mode emb
# → api_calls.embedding: 1

# hybrid モード
python3 .claude/doc-db/scripts/search_index.py --category rules --query "naming convention" --mode hybrid
# → breakdown に emb + lex スコア

# rerank モード
python3 .claude/doc-db/scripts/search_index.py --category specs --query "authentication" --mode rerank
# → breakdown に emb + lex + rerank、api_calls.rerank: 1

# doc_type フィルタ検索
python3 .claude/doc-db/scripts/search_index.py --category specs --query "session" --mode lex --doc-type requirement
# → requirement のチャンクのみ
```

### L2-5: リセット

```bash
bash test_claude_skills/init_fixtures.sh reset
```

> restore（.doc_structure.yaml 復元）+ clean（ビルド成果物削除）を実行する。
> `git diff .doc_structure.yaml` で差分がないことも自動確認される。
>
> doc-db プラグイン自体（scripts, skills）は再テストに備えて残す。
> 完全削除が必要な場合: `rm -rf .claude/doc-db .claude/skills/build-index .claude/skills/query`

---

## テスト結果記録テンプレート

```markdown
### テスト実行記録

- 実行日: YYYY-MM-DD
- 実行者: <名前>
- bw-cc-plugins ブランチ: <ブランチ名>
- bw-cc-plugins コミット: <short hash>
- 環境: Layer 1 / Layer 2 / 両方
- 環境変数: OPENAI_API_KEY=設定済み/未設定

#### Layer 1（自動テスト）

| テストID | 結果 | 備考 |
| --- | --- | --- |
| L1-3-01 〜 L1-3-18 | PASS/FAIL | unittest 出力を添付 |

#### Layer 2（手動テスト）

| テストID | 内容 | 結果 | 備考 |
| --- | --- | --- | --- |
| L2-0 | init_fixtures.sh setup | PASS/FAIL | |
| L2-2 | grep テスト | PASS/FAIL | |
| L2-3 | build テスト | PASS/FAIL | |
| L2-4 | search テスト | PASS/FAIL | |
| L2-5 | init_fixtures.sh reset | PASS/FAIL | git diff で差分なし確認 |
```

---

## API コスト見積もり（Layer 2 のみ）

| 操作 | 推定トークン数 | 推定コスト |
| --- | --- | --- |
| Embedding（test_project、rules+specs） | ~5,000 tokens | < $0.01 |
| Embedding（DocAdvisor 本体、全 doc_type） | ~50,000 tokens | < $0.01 |
| Rerank（1回の検索） | ~2,000 tokens | < $0.01 |
| **Layer 2 全体** | **~60,000 tokens** | **< $0.05** |

> text-embedding-3-small: $0.02/1M tokens、gpt-4o-mini: $0.15/1M input tokens

---

## 参考: bw-cc-plugins のテストパターン

本仕様の Layer 1 は以下の bw-cc-plugins テストに準拠している。

| bw-cc-plugins テスト | 本仕様の対応テスト | 技法 |
| --- | --- | --- |
| `tests/doc_db/test_build_index.py` | L1-3-06 〜 L1-3-10 | tempdir + Embedding モック |
| `tests/doc_db/test_search_index.py` | L1-3-11 〜 L1-3-17 | tempdir + Embedding/Rerank モック |
| `tests/doc_db/test_grep_docs.py` | L1-3-02 〜 L1-3-05 | tempdir + CLAUDE_PROJECT_DIR 設定 |
| `tests/doc_db/test_integration.py` | L1-3-15, L1-3-08 | E2E シナリオ（モック環境） |
| `.claude/skills/update-forge-toc/scripts/swap_doc_config.py` | `test_claude_skills/init_fixtures.sh` | .doc_structure.yaml 差し替え |
