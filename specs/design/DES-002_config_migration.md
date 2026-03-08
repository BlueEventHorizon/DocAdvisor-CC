# DES-002: config.yaml マイグレーション設計

<!-- Created by k_terada -->

## 概要

`merge_config.py` は、Doc Advisor のバージョンアップ時に既存の `config.yaml` ユーザー設定を
新テンプレートへ自動引き継ぎするスクリプト。処理は以下の 2 ステージで構成される。

| ステージ | 処理内容 |
|---------|---------|
| Stage 1 | バージョンマイグレーション（メジャーバージョン間の構造変換） |
| Stage 2 | ユーザー設定引き継ぎ（root_dirs, doc_types_map, exclude 等） |

---

## 現在の設計（v4.x）

### `apply_version_migrations()` の動作

```python
# MIGRATIONS = {new_major: migration_fn}
targets = [v for v in sorted(MIGRATIONS.keys())
           if old_major < v <= new_major]

for v in targets:
    new_content = MIGRATIONS[v](new_content, old_config_dict)
```

v4 → v6 へアップグレードする場合（MIGRATIONS = {5: migrate_to_v5, 6: migrate_to_v6}）：

| ステップ | `new_content` の状態 | `old_config_dict` の状態 |
|---------|---------------------|------------------------|
| 開始時   | v6 テンプレート     | v4 辞書（元）           |
| v=5 実行後 | 中間結果（v5パッチ適用済み） | **v4 辞書のまま** |
| v=6 実行後 | 最終結果            | **v4 辞書のまま** |

### 設計上の制限

**`old_config_dict` は常に元バージョン（v4）の辞書として固定される。**

これは「v4 → v5 → v6 を完全に段階変換する」設計ではなく、
「新テンプレートに対して各マイグレーションがパッチを当てる」設計である。

この制限が問題になるケース：v5 でキー名の変更が発生した場合。

**例**: v5 で `max_workers` → `concurrency` にキー名が変わった場合

```
migrate_to_v5(new_content, v4_dict):
    v4_dict["max_workers"] を参照して new_content の concurrency に書き込む → OK

migrate_to_v6(new_content, v4_dict):  ← v4_dict には concurrency が存在しない
    v4_dict["concurrency"] を参照 → KeyError または None → 値が引き継がれない
```

v5 で変換した値を v6 マイグレーションが参照したい場合、現在の設計では対応できない。

---

## v5 移行時の改修要件

### 改修1: `apply_version_migrations()` の修正

**ファイル**: `templates/doc-advisor/scripts/merge_config.py`

各マイグレーション適用後に `old_config_dict` を中間結果から再パースして更新する。
これにより「v4 → 完全な v5 → 完全な v6」の真の段階変換が実現する。

**改修前（現在）:**
```python
for v in targets:
    new_content = MIGRATIONS[v](new_content, old_config_dict)
```

**改修後:**
```python
for v in targets:
    new_content = MIGRATIONS[v](new_content, old_config_dict)
    old_config_dict = _parse_config_yaml(new_content)  # 中間結果を次マイグレーションに渡す
```

改修後の各マイグレーション関数が受け取る `old_config_dict` の意味が変わる点に注意：

| 関数 | `old_config_dict` の内容（改修後） |
|------|---------------------------------|
| `migrate_to_v5(new_content, old_dict)` | v4 形式の辞書 |
| `migrate_to_v6(new_content, old_dict)` | v5 形式の辞書（前ステップの出力） |

### 改修2: `migrate_to_v5()` 関数の実装

**ファイル**: `templates/doc-advisor/scripts/merge_config.py`

v5 リリース時に config.yaml の構造変更内容に基づき実装し、MIGRATIONS に登録する。

```python
def migrate_to_v5(new_content: str, old_dict: dict) -> str:
    """
    v4 → v5 の構造変更を new_content に適用する。

    Args:
        new_content: v5 テンプレートのテキスト（または前マイグレーションの出力）
        old_dict:    v4 形式の設定辞書

    Returns:
        v5 構造を反映した設定テキスト
    """
    # TODO: v5 の構造変更内容に基づき実装する
    return new_content

MIGRATIONS = {
    5: migrate_to_v5,
}
```

### 改修3: マイグレーション履歴の記録

**ファイル**: `specs/design/DES-001_setup_script.md`

「config.yaml マイグレーション履歴」セクションに v5 の変更内容を追記する。

### 改修4: バージョン管理ルールの更新

**ファイル**: `rules/project_rule.md`（セクション 6.5）

改修後の設計（`old_config_dict` が逐次更新される点）をルールに反映する。

---

## テスト追加要件

**ファイル**: `tests/test_setup_upgrade.sh`

| テスト ID | 内容 |
|---------|------|
| Test 26f | v4 → v5 の単体マイグレーション（v5 で変更されたキーが正しく引き継がれる） |
| Test 26g | v4 → v6 の多段マイグレーション（v5 経由、v5 で変更したキーが v6 に反映される） |
| Test 26h | v5 → v6 の単体マイグレーション（v5 辞書を正しく参照できる） |

---

## 改修の前提条件

- v5 で config.yaml の構造変更（キー追加・変更・削除）が発生すること
- 構造変更がない場合（設定値のみ追加）は改修1は任意（実害なし）
- 構造変更がある場合は改修1〜4をすべて実施すること

---

## 参照

| 文書 | 内容 |
|------|------|
| `specs/design/DES-001_setup_script.md` | setup.sh 詳細設計（config.yaml マイグレーション履歴） |
| `rules/project_rule.md` セクション 6.5 | バージョン管理ルール |
| `templates/doc-advisor/scripts/merge_config.py` | 実装ファイル |
