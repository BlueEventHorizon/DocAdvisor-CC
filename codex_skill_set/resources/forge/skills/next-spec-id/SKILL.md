---
name: next-spec-id
description: |
    全ブランチ（ローカル+リモート）をスキャンし、指定プレフィックスの次の連番IDを安全に取得する。
    ブランチ間のID重複を防止する。任意のプレフィックス対応（SCR, DES, TASK 等）。
    start-requirements / start-design / start-plan から内部的に呼び出される。
metadata:
  short-description: next spec id
---

## Codex Skill Resource Root

This skill is distributed by the environment-wide Doc Advisor Codex Skill set.
Resolve `$DOC_ADVISOR_CODEX_ROOT` to `${CODEX_HOME:-~/.codex}/doc-advisor`,
the directory that contains `install.yaml`.

Run bundled Python scripts with absolute paths under
`$DOC_ADVISOR_CODEX_ROOT/resources/...` and prefix them with
`PYTHONDONTWRITEBYTECODE=1` so global resources do not accumulate runtime cache
files. Project runtime output stays under the current project's
`.codex/state/doc-advisor/`.

# next-spec-id スキル

## 概要

仕様書（要件定義書・設計書・計画書）の次の連番 ID を、全ブランチスキャンで安全に取得する。
ブランチ間での ID 重複を防止する。

forge 内の他スキルからの呼び出し専用（`user-invocable: false`）。

## スクリプト

`$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/next-spec-id/scripts/scan_spec_ids.py`

### CLI インターフェース

```bash
SCRIPT="$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/next-spec-id/scripts/scan_spec_ids.py"

# 次の ID を取得（プレフィックス指定）
PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" SCR
PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" DES
PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" TASK

# プロジェクトルート指定
PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" --project-root /path/to/project SCR

# .doc_structure.yaml のパス指定
PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" --doc-structure /path/to/.doc_structure.yaml SCR
```

### 出力形式（JSON）

#### 正常時

```json
{
  "status": "ok",
  "next_id": "SCR-016",
  "prefix": "SCR",
  "max_number": 15,
  "base_branch": "develop",
  "branches_scanned": 7,
  "ids_found": 15,
  "duplicates": []
}
```

#### 重複検出時

```json
{
  "status": "ok",
  "next_id": "SCR-016",
  "prefix": "SCR",
  "max_number": 15,
  "base_branch": "develop",
  "branches_scanned": 7,
  "ids_found": 17,
  "duplicates": [
    {
      "id": "SCR-013",
      "branches": ["feature/edit_pickup", "origin/feature/print_letter"]
    },
    {
      "id": "SCR-014",
      "branches": ["feature/edit_pickup", "origin/feature/print_letter"]
    }
  ]
}
```

#### エラー時

```json
{
  "status": "error",
  "message": ".doc_structure.yaml が見つかりません"
}
```

## プレフィックスについて

スクリプトは任意のプレフィックスを引数で受け取る。ID 体系の知識は持たない。

どのプレフィックスを使うかは **呼び出し側のスキル** が決定する:

1. プロジェクト固有の `spec_format.md` やルールがあればそれに従う
2. なければ forge の `$DOC_ADVISOR_CODEX_ROOT/resources/forge/docs/spec_format.md` をフォールバック参照

## 他スキルからの呼び出し方

### 要件定義（start-requirements）での例

```bash
SCRIPT="$DOC_ADVISOR_CODEX_ROOT/resources/forge/skills/next-spec-id/scripts/scan_spec_ids.py"
RESULT=$(PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" SCR)
# → {"status": "ok", "next_id": "SCR-016", ...}
```

JSON の `next_id` フィールドをファイル名の先頭に使用する。

### 設計（start-design）での例

```bash
RESULT=$(PYTHONDONTWRITEBYTECODE=1 python3 "$SCRIPT" DES)
# → {"status": "ok", "next_id": "DES-004", ...}
```

## 動作概要

1. `.doc_structure.yaml` から specs の `root_dirs` を取得
2. `git fetch --quiet` でリモートを最新化
3. ベースブランチ（develop or main）を特定
4. ベースブランチから派生した全ブランチをスキャン（ローカル + リモート）
5. `git ls-tree` で各ブランチの specs ディレクトリを走査
6. 指定プレフィックスの最大番号を検出
7. 重複があれば `duplicates` に記録
8. 最大番号 + 1 を返す
