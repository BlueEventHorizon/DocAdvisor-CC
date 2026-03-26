# DES-006: 柔軟性拡張設計書

## 概要

本設計書では、Doc Advisor の以下2点の拡張設計を定義する。

1. **用語の統一**：スクリプトの `--target` を仕様書の「カテゴリ」に合わせて `--category` にリネームする
2. **`doc_type` の拡張**：組み込み7種に加え、カスタムタイプ（例: `adr`）を公式にサポートする

## 関連要件

- REQ-001 FR-01: ドキュメント管理
- REQ-001 NFR-02: 設定可能性

---

## 1. 用語の統一（`--target` → `--category`）

### 現状の問題

| 用語 | 使用箇所 | 指す概念 |
|-----|---------|---------|
| `--target rules/specs` | スクリプト CLI 引数 | ドキュメントの大分類 |
| 「カテゴリ」 | REQ-001 用語定義 | 同じもの |
| 「ターゲット」 | FR-07 タイトル等 | **別の概念**（インストール先プロジェクト） |

`--target` はインストール先プロジェクトの「ターゲット」と混同されるため、
仕様書の「カテゴリ」に統一する。

### 設計

スクリプトの CLI 引数 `--target` を `--category` にリネームする。

**変更対象（Python スクリプト）**：

| ファイル | 変更箇所 |
|---------|---------|
| `create_pending_yaml.py` | argparse `--target` → `--category`、docstring |
| `merge_toc.py` | argparse `--target` → `--category`、docstring |
| `write_pending.py` | argparse `--target` → `--category`、docstring |
| `validate_toc.py` | sys.argv `--target` → `--category`、エラーメッセージ |
| `create_checksums.py` | sys.argv `--target` → `--category`、エラーメッセージ |

**変更対象（Markdown ドキュメント）**：

| ファイル | 変更内容 |
|---------|---------|
| `doc-advisor/docs/toc_orchestrator.md` | コード例・テキスト（約11箇所） |
| `agents/toc-updater.md` | パラメータ説明（2箇所） |
| `skills/query-rules/SKILL.md` | コード例（1箇所） |
| `skills/query-specs/SKILL.md` | コード例（1箇所） |

**`check_config.sh` への影響**：なし。
`check_config.sh` は `--category/--target` 形式ではなく位置引数（`$1`）で `rules|specs` を受け取り、
内部ではすでに `CATEGORY` 変数として処理しているため変更不要。

---

## 2. `doc_type` の拡張

### 現状の問題

REQ-001 FR-01-5 が「固定7種」と規定しているが、コードは実際には任意文字列を受け入れる。
`adr`（Architecture Decision Record）等の標準的なドキュメントタイプを公式に使えない。

### 設計

`doc_type` を「組み込み7種 + カスタムタイプ」として再定義する。

**組み込みタイプ**（変更なし）：

| doc_type | 用途 |
|---------|------|
| rule | 開発ルール・規約・手順 |
| requirement | ゴール定義（機能・非機能要件） |
| design | 技術的構造（アーキテクチャ、DB スキーマ） |
| plan | 作業計画（タスク分割、マイルストーン） |
| api | 外部インターフェース契約 |
| reference | 補助文書（調査メモ、用語集） |
| spec | 上記に該当しない仕様文書 |

**カスタムタイプ**：`doc_types_map` に任意の識別子文字列を指定できる。

```yaml
specs:
  doc_types_map:
    specs/requirements/: requirement
    specs/adr/: adr        # カスタムタイプ
```

**コード変更**：不要。`validate_toc.py` は `doc_type` を非空文字列としてのみ検証しており、
固定リストへの照合は行っていない。仕様書側の記述を現実に合わせるのみ。

**下流への影響**: カスタム doc_type は検索スキル（`/query-rules`, `/query-specs`）の動作に影響しない。検索スキルは ToC 全件を AI が解釈する方式であり、doc_type による固定リストフィルタリングは行っていない。なお、検索スキルは別途改修予定。

**検証ポリシー**: `doc_type` のフォーマット制約は設けない。`validate_toc.py` の非空文字列チェックで運用上問題がないため。タイポ検出はプロジェクトオーナーの責任とする。

---

## 仕様書への反映

### REQ-001

| 箇所 | 変更内容 |
|-----|---------|
| FR-01-5 | 「固定7種」→「組み込み7種 + カスタムタイプ可」 |
| 用語定義「カテゴリ」 | `--category` への言及を追加 |
| 用語定義「doc_type」 | 「固定7種」→「組み込み7種 + カスタムタイプ可」 |

### DES-004

| 箇所 | 変更内容 |
|-----|---------|
| doc_type 一覧 | カスタムタイプ可の注記追加 |
| コンポーネント一覧内の `--target` | `--category` に更新 |

### DES-005

| 箇所 | 変更内容 |
|-----|---------|
| コンポーネント一覧内の `--target` | `--category` に更新 |
| validate_rules_toc.py / validate_specs_toc.py | validate_toc.py に更新（共通化済み） |

---

## 関連設計書

- DES-004: ドキュメントモデル設計書（設定ファイル仕様）
- DES-005: ToC 生成フロー設計書（スクリプト呼び出しチェーン）
