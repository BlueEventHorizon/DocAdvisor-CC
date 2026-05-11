# DES-TST-001: プレリリーステスト環境 設計書

> Created by k2moons
> 作成日: 2026-05-09
> 最終更新: 2026-05-09
> ステータス: 初版

## 概要

bw-cc-plugins のプレリリーステストを DocAdvisor 上で実施するためのテスト環境設計。
DocAdvisor 本体にプラグインをインストールし、store/restore パターンで `.doc_structure.yaml` を
テスト用に差し替えることで、テスト専用ドキュメントに対してインストール済みスクリプトを実行する。

## 背景

bw-cc-plugins は `main` にリリースしなければ一般のターゲットプロジェクトでテストできない。
しかしテストしていないものをリリースすべきではない。
DocAdvisor は bw-cc-plugins の `develop` ブランチを submodule として参照できるため、
このジレンマを解消するプレリリース品質ゲートとして機能する。

```
bw-cc-plugins (develop)   ← 未リリース
  ↓ submodule
DocAdvisor                 ← ここでプレリリーステスト
  ↓ テスト合格
bw-cc-plugins (main)       ← リリース
  ↓ setup.sh
target-project             ← 一般ユーザーが利用
```

## 設計方針

### 原則

1. **テスト対象はインストール後の成果物**: bw-cc-plugins のソースを直接 import するのではなく、`setup.sh` で DocAdvisor にインストールされた `.claude/` 配下のスクリプトをテストする
2. **プロジェクト実体には触れない**: store/restore で `.doc_structure.yaml` を差し替え、テスト専用ドキュメントのみを対象にする
3. **初期化可能**: スクリプト一つで環境のセットアップ・リセットができる
4. **拡張可能**: doc-db だけでなく、将来 doc-advisor・forge のテストにも同じフィクスチャを共有する

### テスト層

| 層 | 内容 | API キー | 対象 |
| --- | --- | --- | --- |
| **L1: 自動テスト** | tempdir + API モックで再現可能なテスト | 不要 | スクリプトロジック |
| **L2: 機能テスト** | store/restore + インストール済みスクリプトで実 API 実行 | 必須 | インストール後の動作 |
| **L3: 品質テスト** | ゴールデンセットで recall/precision を測定 | 必須 | 検索精度 |

L1 は tempdir を使うため本設計のテスト環境には依存しない。
本設計は主に **L2 以上** のテスト実行基盤を定義する。

## テスト環境の構成

### ディレクトリ構造

```
DocAdvisor/（プロジェクトルート）
├── .doc_structure.yaml          ← 本物（store で退避、テスト用に差し替え）
├── .claude/
│   ├── doc-advisor/scripts/     ← setup.sh でインストール済み
│   ├── doc-db/scripts/          ← setup.sh --with-doc-db でインストール済み
│   ├── doc-db/index/            ← build テストで生成（clean で削除）
│   └── skills/                  ← setup.sh でインストール済み
│
├── test_claude_skills/
│   ├── fixtures/                ← テスト専用ドキュメント（仮想プロジェクトの文書）
│   │   ├── rules/
│   │   │   └── test_rule.md
│   │   └── specs/
│   │       ├── requirements/
│   │       │   └── test_req.md
│   │       └── design/
│   │           └── test_des.md
│   │
│   ├── test_doc_structure.yaml  ← store 時にルートにコピーするテンプレート
│   ├── init_fixtures.sh         ← 初期化スクリプト
│   │
│   └── doc_db/                  ← L1 自動テスト（tempdir ベース、本環境に非依存）
│       └── test_doc_db_installed.py
├── test_claude_setup/           ← setup.sh インストールテスト専用（別用途）
├── test_codex/                  ← Codex 環境テスト専用
```

### store/restore の仕組み

スクリプト（`build_index.py`, `search_index.py`, `grep_docs.py` 等）は
**プロジェクトルートの `.doc_structure.yaml`** を読み取って対象ドキュメントを特定する。
テスト時は store/restore パターンでこのファイルをテスト用テンプレートに差し替える。

```
[通常時]
.doc_structure.yaml
  → rules/         （プロジェクト本体のルール文書）
  → specs/         （プロジェクト本体の仕様書）

[テスト時（store 後）]
.doc_structure.yaml  ← test_claude_skills/test_doc_structure.yaml のコピー
  → test_claude_skills/fixtures/rules/         （テスト専用ルール文書）
  → test_claude_skills/fixtures/specs/         （テスト専用仕様書）
```

### テスト用テンプレート

`test_claude_skills/test_doc_structure.yaml`:

```yaml
# doc_structure_version: 3.0
# Test environment template - copied to project root during store

rules:
  root_dirs:
    - test_claude_skills/fixtures/rules/
  doc_types_map:
    test_claude_skills/fixtures/rules/: rule
  patterns:
    target_glob: "**/*.md"
    exclude: []

specs:
  root_dirs:
    - test_claude_skills/fixtures/specs/requirements/
    - test_claude_skills/fixtures/specs/design/
  doc_types_map:
    test_claude_skills/fixtures/specs/requirements/: requirement
    test_claude_skills/fixtures/specs/design/: design
  patterns:
    target_glob: "**/*.md"
    exclude: []
```

### テスト用ドキュメント

`test_claude_skills/fixtures/` 配下のドキュメントは以下の要件を満たす:

- **一意なマーカー文字列**（`MARKER_TEST_RULE_001` 等）を含み、検索結果を確実に照合できる
- **複数の doc_type** を持ち（rule, requirement, design）、doc_type フィルタのテストが可能
- **最小限のサイズ** で、API コストを抑制する
- **安定した見出し構造** を持ち、チャンク分割の検証が可能

現在のフィクスチャ:

| ファイル | doc_type | マーカー |
| --- | --- | --- |
| `rules/test_rule.md` | rule | `MARKER_TEST_RULE_001`, `MARKER_TEST_RULE_002` |
| `specs/requirements/test_req.md` | requirement | `MARKER_TEST_REQ_001`, `MARKER_TEST_REQ_002` |
| `specs/design/test_des.md` | design | `MARKER_TEST_DES_001`, `MARKER_TEST_DES_002` |

## 初期化スクリプト

### `test_claude_skills/init_fixtures.sh`

テスト環境のライフサイクルを管理するシェルスクリプト。

#### サブコマンド

| コマンド | 動作 |
| --- | --- |
| `setup` | プラグインインストール（`setup.sh --with-doc-db .`）+ store |
| `store` | `.doc_structure.yaml` をバックアップし、テスト用テンプレートで差し替え |
| `restore` | `.doc_structure.yaml` をバックアップから復元 |
| `clean` | ビルド成果物（`.claude/doc-db/index/` 等）を削除 |
| `reset` | restore + clean（テスト環境の完全リセット） |
| `status` | 現在の状態を表示（store 済みか、インストール済みか） |

#### 使用例

```bash
# 初回セットアップ（プラグインインストール + テスト環境準備）
bash test_claude_skills/init_fixtures.sh setup

# テスト実行（SKILL や手動で）
# ...

# テスト終了後のリセット
bash test_claude_skills/init_fixtures.sh reset
```

#### 安全機構

- store 時に `.doc_structure.yaml.bak` が既に存在する場合はエラー（二重 store 防止）
- restore 時に `.doc_structure.yaml.bak` が存在しない場合はエラー（未 store 時の誤 restore 防止）
- restore 後に `git diff .doc_structure.yaml` で差分がないことを確認表示

#### 設計制約

- `sed -i` は使用しない（macOS/Linux 非互換）
- システムディレクトリへの書き込みは行わない
- bw-cc-plugins への書き込みは行わない

## テスト実行フロー

### L2 機能テストの実行フロー

```
1. bash test_claude_skills/init_fixtures.sh setup
   ├── setup.sh --with-doc-db . でプラグインインストール
   ├── .doc_structure.yaml をバックアップ
   └── テスト用テンプレートで差し替え

2. テスト実行（/test-doc-db --layer2 または手動）
   ├── grep_docs.py → MARKER 文字列でフィクスチャがヒット
   ├── build_index.py → .claude/doc-db/index/ にインデックス生成
   └── search_index.py → 全モード（lex/emb/hybrid/rerank）検索

3. bash test_claude_skills/init_fixtures.sh reset
   ├── .doc_structure.yaml を復元
   └── .claude/doc-db/index/ を削除
```

### SKILL からの利用

`/test-doc-db` スキルは `init_fixtures.sh` を内部的に使用する:

```
/test-doc-db --layer2
  → init_fixtures.sh setup（未セットアップの場合）
  → テスト実行
  → init_fixtures.sh reset
```

## test_claude_setup/ との棲み分け

| 環境 | 用途 | 対象テスト |
| --- | --- | --- |
| **test_claude_skills/fixtures/** | プラグイン機能テスト（L2/L3） | `/test-doc-db` 等 |
| **test_claude_setup/test_project/** | setup.sh インストールテスト | `test_optional_plugins.sh` 等 |
| **test_codex/** | Codex 環境テスト | `test_codex_*.sh` 等 |

`test_claude_setup/` は setup.sh のインストール結果（ファイル配置・パス変換）の検証に特化する。
プラグイン機能テスト（スクリプトの動作検証）は `test_claude_skills/fixtures/` に一本化する。

## 拡張計画

### 将来のフィクスチャ追加

doc-advisor や forge のテスト時にも、同じ `test_claude_skills/fixtures/` のドキュメントを使用する。
テストシナリオに応じてフィクスチャを追加する:

```
test_claude_skills/fixtures/
├── rules/
│   ├── test_rule.md           ← 既存（doc-db + doc-advisor 共用）
│   └── test_coding_guide.md   ← 将来追加（ToC 生成テスト用等）
└── specs/
    ├── requirements/
    │   └── test_req.md        ← 既存
    └── design/
        └── test_des.md        ← 既存
```

### 将来のテストスキル追加

| プラグイン | テストスキル | テスト仕様書 |
| --- | --- | --- |
| doc-db | `/test-doc-db`（作成済み） | `TST-001`（作成済み） |
| doc-advisor | `/test-doc-advisor`（将来） | `TST-002`（将来） |
| forge | `/test-forge`（将来） | `TST-003`（将来） |

全テストスキルが `init_fixtures.sh` を共有し、同じ store/restore メカニズムを使用する。

## 関連ドキュメント

- [CLAUDE.md](../../CLAUDE.md) — プレリリーステストの責務定義
- [TST-001_doc_db_functional_test.md](TST-001_doc_db_functional_test.md) — doc-db テスト仕様書
- [.claude/skills/test-doc-db/SKILL.md](../../.claude/skills/test-doc-db/SKILL.md) — doc-db テストスキル

## 変更履歴

| 日付 | 変更者 | 内容 |
| --- | --- | --- |
| 2026-05-09 | k2moons | 初版作成 |
