# DES-003: 文書識別子の設計

## 概要

本設計書では、Doc Advisor における文書の識別方法を定義する。

## 現状分析と問題点

### 現在の実装

現在、文書IDとして以下の2つの方式が混在している：

1. **ファイル名ベースのID抽出**
   - `toc_utils.py` の `extract_id_from_filename()` 関数
   - 正規表現 `[A-Z]+-\d+` でファイル名からIDを抽出
   - 例: `SCR-001_login.md` → `SCR-001`

2. **ファイルパスベースのキー**
   - `specs_toc.yaml` / `rules_toc.yaml` のキー
   - 例: `specs/requirements/login.md`

### 問題点

```mermaid
flowchart TD
    subgraph 問題点
        P1[ID命名の強制]
        P2[ID重複リスク]
        P3[二重管理]
        P4[意味の曖昧さ]
    end

    P1 --> D1["ユーザーは SCR-001 形式を<br>強制される"]
    P2 --> D2["異なるディレクトリで<br>同じIDが使われる可能性"]
    P3 --> D3["IDとパスの両方で<br>文書を参照"]
    P4 --> D4["SCR, DES, BL の<br>意味が不明確"]
```

#### 問題1: ID命名の強制

| 現状                                     | 問題                                               |
| ---------------------------------------- | -------------------------------------------------- |
| ファイル名に `[A-Z]+-\d+` パターンを期待 | ユーザーの命名自由度を制限                         |
| `SCR-001_login.md` 形式を暗黙的に要求    | `login_screen.md` のようなシンプルな名前が使えない |

#### 問題2: ID重複リスク

```
specs/requirements/SCR-001_login.md
specs/design/SCR-001_login_design.md
```

同じID `SCR-001` が異なるディレクトリで使用される可能性がある。

#### 問題3: 二重管理

| 識別方法                             | 使用箇所                                                                        |
| ------------------------------------ | ------------------------------------------------------------------------------- |
| ID (`SCR-001`)                       | `.claude/doc-advisor/toc/specs/.toc_work/SCR-001.yaml`、validate の重複チェック |
| パス (`specs/requirements/login.md`) | ToC YAML のキー、実際のファイル参照                                             |

2つの識別子を管理する必要があり、冗長である。

#### 問題4: 意味の曖昧さ

| プレフィックス | 想定意味        | 問題                           |
| -------------- | --------------- | ------------------------------ |
| `SCR-`         | Screen?         | ディレクトリ構造との関係が不明 |
| `DES-`         | Design          | ディレクトリで区別すれば不要   |
| `REQ-`         | Requirement     | ディレクトリで区別すれば不要   |
| `BL-`          | Business Logic? | 定義なし                       |
| `APP-`         | Application?    | 定義なし                       |

IDプレフィックスの意味が整理されていない。

## 設計方針

### 原則: ファイルパスを唯一の識別子とする

```mermaid
flowchart LR
    A[文書] --> B[ファイルパス]
    B --> C[唯一の識別子]

    subgraph 不要
        D[ファイル名ID]
        E[連番管理]
    end
```

**理由:**

1. **ファイルパスは必ずユニーク** - ファイルシステムが保証
2. **追加の命名規則が不要** - ユーザーは自由にファイル名を決められる
3. **ToC YAML のキーとして既に使用** - 一貫性がある

### ファイル名は自由

| OK                         | NG（強制しない） |
| -------------------------- | ---------------- |
| `login.md`                 | -                |
| `login_screen.md`          | -                |
| `SCR-001_login.md`         | -                |
| `2024-01-login-feature.md` | -                |

ユーザーがIDプレフィックスを使いたければ使えるが、システムは強制しない。

## 詳細設計

### 文書の識別

```yaml
# 識別子 = ルートディレクトリからの相対パス
identifier: "specs/requirements/login.md"

# これだけでファイルが特定できる
file_path: specs/requirements/login.md
```

### `.claude/doc-advisor/toc/specs/.toc_work/` ファイル名生成

**現在の実装（変更不要）:**

```python
# パスからワークファイル名を生成
# specs/requirements/login.md → specs_requirements_login.yaml
work_filename = rel_path.replace("/", "_").replace(".md", ".yaml")
```

これは既に正しい実装であり、IDに依存していない。

### 廃止すべき機能

| 機能                         | 場所                    | 対応                                   |
| ---------------------------- | ----------------------- | -------------------------------------- |
| `extract_id_from_filename()` | `toc_utils.py`          | 廃止または非推奨化                     |
| ID重複チェック               | `validate_specs_toc.py` | パス重複チェックに変更（既に実装済み） |
| ID抽出コメント               | `default-config.yaml`   | 削除                                   |

### 移行計画

```mermaid
flowchart TD
    A[Phase 1: 文書更新] --> B[Phase 2: コード整理]
    B --> C[Phase 3: 動作確認]

    A --> A1["設計書・README から<br>ID強制の記述を削除"]
    B --> B1["extract_id_from_filename() を<br>非推奨マーク"]
    B --> B2["config コメントを更新"]
    C --> C1["ID なしファイルで<br>ToC 生成テスト"]
```

## 影響範囲

### 変更が必要なファイル

| ファイル                    | 変更内容                                          |
| --------------------------- | ------------------------------------------------- |
| `toc_utils.py`              | `extract_id_from_filename()` に非推奨コメント追加 |
| `default-config.yaml`       | ID関連コメント削除                                |
| `create-specs-toc/SKILL.md` | ID抽出の説明を削除                                |
| `toc_format.md`             | ID要件の記述がないことを確認                      |

### 変更不要なファイル

| ファイル                 | 理由                           |
| ------------------------ | ------------------------------ |
| `merge_toc.py`           | パスベースで動作している       |
| `validate_specs_toc.py`  | パス重複チェックは既に実装     |
| `create_pending_yaml.py` | パスからワークファイル名を生成 |

## 結論

| 項目                                      | 決定                                                 |
| ----------------------------------------- | ---------------------------------------------------- |
| 文書の識別子                              | **ファイルパス**（ルートディレクトリからの相対パス） |
| ファイル名のID                            | **任意**（ユーザーの自由）                           |
| IDプレフィックス規則                      | **なし**（システムは関知しない）                     |
| 既存コードの `extract_id_from_filename()` | **非推奨**（後方互換のため残すが使用しない）         |

### 推奨するファイル命名

システムは強制しないが、可読性のために以下を推奨：

```
# 推奨: 内容がわかる名前
specs/requirements/user_authentication.md
specs/design/login_screen_design.md

# 許容: ユーザーが管理しやすい形式
specs/requirements/REQ-001_user_authentication.md
specs/requirements/001_user_authentication.md
specs/requirements/2024-01_authentication.md
```
