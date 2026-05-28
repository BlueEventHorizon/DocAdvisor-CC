# バージョンアップ・マイグレーション設計ルール

Created by: k_terada
Created at: 2026-03-08
Status: Stable

---

## 1. なぜマイグレーションが必要か

アプリやツールが進化すると、設定ファイルやデータベースの**構造**が変わる。
古いバージョンのデータを新しいバージョンのコードで読もうとすると、次のような問題が起きる。

| 問題             | 例                            |
| ---------------- | ----------------------------- |
| キー名の変更     | `max_workers` → `concurrency` |
| 構造の変更       | フラット → ネスト             |
| 型の変更         | 数値 → 文字列                 |
| キーの追加・削除 | 必須フィールドが増えた        |

これらを安全に変換するのが**マイグレーション**の役割。

---

## 2. 失敗するアンチパターン

### アンチパターン1: 「古いデータをそのまま読もうとする」

```python
# NG: v4のキーがなければ None になってしまう
settings = load_config()
concurrency = settings.get("concurrency")  # v4には存在しない → None
```

### アンチパターン2: 「元データを全マイグレーションに固定で渡す」

DocAdvisor v4.x で発見した問題。v4 → v6 の多段マイグレーション時に発生する。

```python
# NG: old_data が v4 形式で固定されている
for v in [5, 6]:
    new_content = MIGRATIONS[v](new_content, old_data)  # old_data は v4 のまま
```

v5 でキーが変わった場合、v6 マイグレーションは v4 の古いキーしか参照できず、
v5 で変換した値が v6 に引き継がれない。

```
v5マイグレーション: v4の max_workers → v5の concurrency に書き込む  → OK
v6マイグレーション: old_data["concurrency"] を参照 → v4辞書にないので None  → NG
```

---

## 3. 確実に動くパターン：パイプライン原則

**各マイグレーションは「前のステップの出力」を入力として受け取る。**

```
v4データ
  ↓ migrate_v4_to_v5(v4データ)
v5データ（完全なv5形式）
  ↓ migrate_v5_to_v6(v5データ)  ← v4ではなくv5を受け取る
v6データ（完全なv6形式）
```

バージョンを飛ばした場合（v4 → v6）も、中間ステップを通ることで安全に変換できる。

---

## 4. 基本原則

### 原則1: パイプライン（各ステップが前ステップの出力を受け取る）

多段マイグレーションの唯一確実な設計。

### 原則2: バージョン番号の単一の真実の源（Single Source of Truth）

バージョン番号はコード1箇所で管理し、データ自体にも埋め込む（セルフ記述型）。

```yaml
# config.yaml（セルフ記述型の例）
# doc-advisor-version-xK9XmQ: 4.3
```

### 原則3: 冪等性（Idempotency）

同じマイグレーションを2回適用しても結果が変わらないようにする。

```sql
-- NG: 2回目に失敗する
ALTER TABLE settings ADD COLUMN timeout_sec INTEGER;

-- OK: 2回目は何もしない
ALTER TABLE settings ADD COLUMN IF NOT EXISTS timeout_sec INTEGER DEFAULT 30;
```

### 原則4: 未知のキーは保持する（フォワード互換性）

マイグレーション関数は自分が知っているキーだけを変換し、
**知らないキーは削除せずそのまま残す**。

### 原則5: 適用履歴の永続化

どのバージョンまで適用済みかを必ず記録する。再実行防止と診断に使う。

---

## 5. 形式別実装パターン

### 5.1 YAML / JSON（設定ファイル）

```python
# マイグレーション登録テーブル
MIGRATIONS = {
    5: migrate_v4_to_v5,  # v4 → v5 の変換
    6: migrate_v5_to_v6,  # v5 → v6 の変換
}

def apply_migrations(old_data: dict, old_ver: int, new_ver: int) -> dict:
    """
    old_ver から new_ver まで順次マイグレーションを適用する。
    各ステップが前ステップの出力を受け取るパイプライン設計。
    """
    targets = [v for v in sorted(MIGRATIONS.keys())
               if old_ver < v <= new_ver]
    current = old_data
    for v in targets:
        current = MIGRATIONS[v](current)  # 前ステップの出力を次に渡す
    return current


def migrate_v4_to_v5(data: dict) -> dict:
    """v4 → v5: max_workers を concurrency にリネーム"""
    result = dict(data)  # コピー（元データを変更しない）
    if "max_workers" in result:
        result["concurrency"] = result.pop("max_workers")
    return result


def migrate_v5_to_v6(data: dict) -> dict:
    """v5 → v6: timeout_sec を追加"""
    result = dict(data)
    result.setdefault("timeout_sec", 30)  # デフォルト値で追加
    return result
```

**ポイント:**

- 各マイグレーション関数のシグネチャは `fn(data: dict) -> dict`（前バージョンの dict を受け取る）
- 元データを変更しない（コピーして操作する）
- `setdefault` で既存値を上書きしない

### 5.2 Swift Codable / PropertyList

versioned struct パターン。各バージョンのモデルを型として保持する。

```swift
// 各バージョンのモデルを定義
struct SettingsV4: Codable {
    let maxWorkers: Int
}

struct SettingsV5: Codable {
    let concurrency: Int  // maxWorkers からリネーム
}

struct SettingsV6: Codable {
    let concurrency: Int
    let timeoutSec: Int   // 追加
}

typealias SettingsLatest = SettingsV6

// バージョンラッパー（セルフ記述型）
struct VersionedData: Codable {
    let version: Int
    let rawData: Data  // 生のJSONバイト列
}

// 読み込み時に自動マイグレーション
func loadSettings(from data: Data) throws -> SettingsLatest {
    let versioned = try JSONDecoder().decode(VersionedData.self, from: data)
    return try migrateToLatest(version: versioned.version, rawData: versioned.rawData)
}

func migrateToLatest(version: Int, rawData: Data) throws -> SettingsLatest {
    switch version {
    case 4:
        let v4 = try JSONDecoder().decode(SettingsV4.self, from: rawData)
        let v5 = migrateV4toV5(v4)          // v4 → v5
        return migrateV5toV6(v5)            // v5 → v6
    case 5:
        let v5 = try JSONDecoder().decode(SettingsV5.self, from: rawData)
        return migrateV5toV6(v5)            // v5 → v6
    case 6:
        return try JSONDecoder().decode(SettingsV6.self, from: rawData)
    default:
        throw MigrationError.unknownVersion(version)
    }
}

func migrateV4toV5(_ v4: SettingsV4) -> SettingsV5 {
    return SettingsV5(concurrency: v4.maxWorkers)  // リネーム
}

func migrateV5toV6(_ v5: SettingsV5) -> SettingsV6 {
    return SettingsV6(concurrency: v5.concurrency, timeoutSec: 30)  // デフォルト追加
}
```

**ポイント:**

- 各バージョンの struct を削除せずに保持する（過去バージョンのデコードに必要）
- `switch` でバージョンごとに分岐し、段階的に変換する
- CoreData を使う場合は NSMigrationPolicy と Mapping Model を使用する

### 5.3 データベース（SQLite / PostgreSQL / CoreData）

マイグレーションファイルの連番管理パターン（Rails / Flyway / Alembic と同じ考え方）。

**ディレクトリ構造:**

```
migrations/
  005_rename_max_workers.sql
  006_add_timeout_sec.sql
  007_create_audit_log.sql
```

**各マイグレーションファイルの例:**

```sql
-- migrations/005_rename_max_workers.sql
-- 冪等性: すでにリネーム済みの場合は何もしない
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='settings' AND column_name='max_workers') THEN
        ALTER TABLE settings RENAME COLUMN max_workers TO concurrency;
    END IF;
END $$;
```

**適用履歴テーブル（必須）:**

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**マイグレーション実行ロジック:**

```python
def apply_db_migrations(conn, current_version: int, target_version: int):
    """未適用のマイグレーションを昇順に適用する"""
    applied = get_applied_versions(conn)
    pending = [v for v in sorted(ALL_MIGRATIONS.keys())
               if current_version < v <= target_version and v not in applied]

    for v in pending:
        with conn.transaction():
            ALL_MIGRATIONS[v](conn)             # マイグレーション実行
            record_migration(conn, version=v)   # 適用履歴を記録
```

**ポイント:**

- トランザクションで包む（失敗したらロールバック）
- 各マイグレーションは冪等にする
- 適用履歴テーブルに記録して再実行を防ぐ
- `DOWN` マイグレーション（ロールバック用）も用意しておく

---

## 6. バージョンを飛ばした更新（v4 → v6）の確実な処理

### 選出ロジック（共通）

```
適用すべきマイグレーション = current_version < v <= target_version
```

MIGRATIONS テーブルのキーが連続していなくてもよい。
`sorted()` で昇順に並べ、順次適用する。

### 処理フロー

```
current_version = 4, target_version = 6
MIGRATIONS = {5: fn_v5, 6: fn_v6}

targets = [5, 6]  (sorted, 4 < v <= 6)

  fn_v5(v4_data) → v5_data
  fn_v6(v5_data) → v6_data  ← パイプライン: v5の出力を受け取る
```

---

## 7. リリース前チェックリスト

バージョンアップ（メジャー番号変更）の際に確認する。

### 設計確認

- [ ] バージョン番号を1箇所で管理しているか（Single Source of Truth）
- [ ] データ自体にバージョン番号を埋め込んでいるか（セルフ記述型）
- [ ] 各マイグレーション関数は「前ステップの出力」を入力として受け取るか（パイプライン原則）
- [ ] 未知のキーを削除せずに保持しているか（フォワード互換性）

### 実装確認

- [ ] 各マイグレーション関数を MIGRATIONS テーブルに登録したか
- [ ] マイグレーション適用履歴を記録する仕組みがあるか
- [ ] ロールバック手順を定義しているか

### テスト確認

- [ ] 直前バージョンからのマイグレーションテスト（v5 → v6）
- [ ] **バージョンを飛ばした多段テスト（v4 → v6）** ← 必須・見落としやすい
- [ ] 冪等性テスト（同じマイグレーションを2回適用しても結果が変わらない）
- [ ] 本番相当データでの動作確認

---

## 8. .doc_structure.yaml への適用

`.doc_structure.yaml` のバージョンマイグレーションについては以下を参照:

- 要件定義: `docs/specs/common/requirement/COMMON-REQ-001_versioned_migration.md`
- 設計: `docs/specs/forge/design/DES-016_doc_structure_version_management_design.md`
- 実装: `plugins/forge/scripts/migrate_doc_structure.py`

本ルール文書の原則（パイプライン、冪等性等）に準拠し、テキスト操作（`fn(str) -> str`）で実装されている。
