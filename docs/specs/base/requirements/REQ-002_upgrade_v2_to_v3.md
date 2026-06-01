# REQ-002: アップグレード要件（v2.0 → 現行）

## 概要

Doc Advisor を旧バージョン（v2.0 / v3.x）から現行の **key + path 汎用 ToC Provider** バージョンへアップグレードする際に必要な要件を定義する。

## 背景

doc-advisor は以下の構造変更を経てきた:

| 変更         | v2.0                                     | v3.x                                   | 現行（key + path I/F）                   |
| ------------ | ---------------------------------------- | -------------------------------------- | ---------------------------------------- |
| 生成コマンド | `commands/create-*_toc.md`               | `skills/create-*-toc/SKILL.md`         | `skills/index-docs/SKILL.md`             |
| 検索         | agent (`rules-advisor`, `specs-advisor`) | skill (`/query-rules`, `/query-specs`) | skill (`/query-docs`)                    |
| 文書構造設定 | `doc-advisor/config.yaml`                | `.doc_structure.yaml`                  | **なし**（上位層が key + paths を渡す）  |
| 分類         | category + target_dirs                   | category + `doc_types_map`             | opaque `key`（category / doc_type 廃止） |
| ToC 出力先   | `doc-advisor/rules/`                     | `doc-advisor/toc/{rules,specs}/`       | `doc-advisor/toc/{slug}/`           |
| ToC ファイル | `rules_toc.yaml` / `specs_toc.yaml`      | 同左（`toc/{rules,specs}/` 配下）      | `toc.yaml`（key 単位ストア配下）         |

現行版は **clean break**（REQ-001 §6.2）であり、旧 category 別 ToC・`.doc_structure.yaml`・旧 SKILL は廃止された。旧バージョンからアップグレードするユーザーは、旧ファイルの整理と ToC の再生成が必要になる。

---

## アップグレードの原則

### 原則1: 識別子ベースの保護

```
ファイルに doc-advisor 識別子があるか？
  → ある（現行バージョン）: 管理中 → 削除しない
  → ある（旧バージョン）:   更新対象 → 削除OK
  → ない:                   古い残骸 → 削除OK
```

v3.6 で導入された `doc-advisor-version-xK9XmQ` 識別子により、ファイルの管理状態を判定する。

### 原則2: ユーザー資産の保護

Doc Advisor が管理していないファイル（ユーザー独自のコマンド、エージェント等）は削除しない。

### 原則3: ランタイム出力の尊重

ユーザーのワークスペースに生成された ToC ストア（`.claude/doc-advisor/toc/`）は、明示的な確認なしに上書き・削除しない。現行版は `.doc_structure.yaml` を使用しないが、旧バージョンが残した `.doc_structure.yaml` はユーザー資産として一切改変しない（廃止に伴い参照されなくなるのみ）。

---

## プラグイン環境での適用

Doc Advisor がプラグインとして配布される環境では、ファイルのインストール・削除はプラグインマネージャーが管理する。上記3原則はプラグイン環境でも以下のように適用される:

- **識別子ベースの保護**: プラグイン更新時、旧バージョンのファイルはプラグインマネージャーが差し替える。ユーザーのワークスペース内にコピーされた管理ファイル（ToC、チェックサム等）は識別子で判定する
- **ユーザー資産の保護**: プラグインが管理するディレクトリ外のユーザーファイルには一切触れない。ランタイム出力（ToC ストア、チェックサム、作業ディレクトリ）はアップグレード時に保持する
- **設定ファイルの尊重**: 旧バージョンの `.doc_structure.yaml` / `config.yaml` はユーザーのプロジェクトルートに配置され、プラグイン更新で上書き・削除しない（現行版は参照しないだけ）

---

## 機能要件

### REQ-002-01: レガシーファイルの検出と案内

**説明**: 旧バージョンの doc-advisor 管理ファイルが残存している場合、ユーザーに整理を案内する

**検出対象**:

- `.claude/commands/create-rules_toc.md` / `.claude/commands/create-specs_toc.md`（v2.0）
- `.claude/doc-advisor/config.yaml`（v2.0 の旧設定）
- `.claude/doc-advisor/docs/`（v2.0 の旧構造）
- `.doc_structure.yaml`（v3.x の文書構造設定。現行版は参照しない）

**受入条件**:

- [ ] 上記ファイルの存在を検出できる
- [ ] 検出時にユーザーに整理（または無視可能である旨）を案内する
- [ ] ユーザー確認なしの自動削除は行わない（プラグイン環境ではユーザーのワークスペースを直接操作しない）

### REQ-002-02: ユーザー資産の保護

**説明**: ユーザーが独自に作成したファイルは削除しない

**保護対象**:

- `.claude/commands/` 内のユーザー独自コマンド
- `.claude/agents/` 内のユーザー独自エージェント
- `.claude/doc-advisor/toc/`（ランタイム出力: ToC ストア、チェックサム、作業ディレクトリ）

**受入条件**:

- [ ] `commands/` ディレクトリ自体は削除されない
- [ ] `agents/` 内の doc-advisor 以外のファイルは保持される

### REQ-002-03: 旧 ToC・設定からの移行

**説明**: 旧 category 別 ToC（`toc/rules/`, `toc/specs/`）は現行の key 単位ストア（`toc/`）へ**自動移行しない**（clean break、REQ-001 §6.2 / 非目的）。再生成で対応する

**受入条件**:

- [ ] 旧 `toc/rules/rules_toc.yaml` / `toc/specs/specs_toc.yaml` の残存を検出し、`/doc-advisor:index-docs` での再生成を案内する
- [ ] 旧 ToC を現行ストアへ自動コピー・自動変換しない
- [ ] `.doc_structure.yaml` は現行版では不要であり、削除は任意である旨を案内する

### REQ-002-04: 旧検索コンポーネント → query-docs の移行

**説明**: advisor agent（v2.0）および `query-rules` / `query-specs` skill（v3.x）を、現行の `query-docs` skill に置き換える。旧コンポーネントが残存している場合は整理を案内する

**検出対象**:

- `.claude/agents/rules-advisor.md` / `.claude/agents/specs-advisor.md`（v2.0）
- `.claude/skills/query-rules/` / `.claude/skills/query-specs/`（v3.x。プラグイン配布物はプラグインマネージャーが差し替える）

**置き換え先**（プラグインとして提供）:

- `/doc-advisor:query-docs` skill（検索）
- `/doc-advisor:index-docs` skill（生成）

**受入条件**:

- [ ] 旧 advisor agent / 旧 query-* skill の存在を検出できる
- [ ] 現行バージョン識別子を持つファイルは保護される
- [ ] `query-docs` / `index-docs` skill がプラグイン経由で利用可能である

---

## 非機能要件

### REQ-002-NF-01: ToC ストアの保持

**説明**: 既存の ToC ストアはアップグレード時に削除しない

**受入条件**:

- [ ] `.claude/doc-advisor/toc/` 配下の生成物は削除されない
- [ ] 旧 category 別 ToC は再生成（`/doc-advisor:index-docs`）で現行ストアへ移行する

> **Note**: 旧バージョンの ToC（`doc-advisor/rules/` や `doc-advisor/toc/{rules,specs}/`）はパス構造が現行（`toc/`）と異なる。現行版で直接利用できないため、初回は `/doc-advisor:index-docs` での再生成を推奨する。

### REQ-002-NF-02: 識別子対応

**説明**: バージョン識別子ベースでファイルの管理状態を判定する

**原則**:

```
ファイルに doc-advisor 識別子があるか？
  → ある（現行バージョン）: 管理中 → 削除しない
  → ある（旧バージョン）:   更新対象 → 削除OK
  → ない:                   古い残骸 → 削除OK
```

**受入条件**:

- [ ] 管理ファイルに `doc-advisor-version-xK9XmQ` 識別子が含まれる
- [ ] 識別子の一致/不一致で管理状態を判断できる
- [ ] レガシー（v2.0）ファイルは識別子がないためファイル名で判別する

---

## テスト要件

### テストケース

| ID    | 内容                             | 期待結果                                                    |
| ----- | -------------------------------- | ----------------------------------------------------------- |
| T-001 | レガシー commands/ 検出          | doc-advisor コマンドの存在を検出、ユーザーコマンド無視      |
| T-002 | レガシー doc-advisor/ 検出       | config.yaml と docs/ の残存を検出                           |
| T-003 | `.doc_structure.yaml` 検出       | 残存を検出し「現行版では不要」と案内（自動削除しない）      |
| T-004 | agents/ カスタム保持             | ユーザーの独自 agent が保持される                           |
| T-005 | 旧検索コンポーネント検出         | rules-advisor.md / specs-advisor.md / 旧 query-* の残存検出 |
| T-006 | query-docs / index-docs 利用可能 | 現行 skill がプラグイン経由で動作する                       |
| T-007 | ToC ストア保持                   | 既存 ToC ストアがアップグレード後も保持される               |
| T-008 | 旧 category ToC 検出             | `toc/{rules,specs}/` の残存を検出し再生成を案内する         |

---

## 関連ドキュメント

- `REQ-001_doc_advisor.md`: Doc Advisor 要件定義書（現行 key + path I/F）
- `REQ-003_versioned_migration.md`: 段階的バージョンマイグレーション要件
