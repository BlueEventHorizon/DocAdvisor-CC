# REQ-002: アップグレード要件（v2.0 → v4.x）

## 概要

Doc Advisor v2.0 から v4.x へのアップグレード時に必要な要件を定義する。

## 背景

v3.0 以降で以下の構造変更が行われた:

| 変更         | v2.0                                     | v3.x                                    |
| ------------ | ---------------------------------------- | --------------------------------------- |
| コマンド     | `commands/create-*_toc.md`               | `skills/create-*-toc/SKILL.md`          |
| 設定         | `doc-advisor/config.yaml`                | `doc-advisor/config.yaml`（場所は同じ） |
| ドキュメント | `doc-advisor/docs/`                      | `doc-advisor/docs/`（場所は同じ）       |
| コマンド形式 | `/create-rules_toc`                      | `/create-rules-toc`                     |
| ToC 出力先   | `doc-advisor/rules/`                     | `doc-advisor/toc/rules/`                |
| Advisor      | agent (`rules-advisor`, `specs-advisor`) | skill (`/query-rules`, `/query-specs`)  |
| 設定構造     | `root_dir` (単数) + `target_dirs`        | `root_dirs` (複数) + `target_glob`      |

これにより、v2.0 からアップグレードするユーザーは旧ファイルの削除と新ファイルの配置が必要になる。

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

### 原則3: config.yaml の尊重

ユーザーがカスタマイズした設定は明示的な確認なしに上書きしない。

---

## プラグイン環境での適用

Doc Advisor がプラグインとして配布される環境では、ファイルのインストール・削除はプラグインマネージャーが管理する。上記3原則はプラグイン環境でも以下のように適用される:

- **識別子ベースの保護**: プラグイン更新時、旧バージョンのファイルはプラグインマネージャーが差し替える。ユーザーのワークスペース内にコピーされた管理ファイル（ToC、チェックサム等）は識別子で判定する
- **ユーザー資産の保護**: プラグインが管理するディレクトリ外のユーザーファイルには一切触れない。ランタイム出力（ToC、チェックサム、作業ディレクトリ）はアップグレード時に保持する
- **config.yaml の尊重**: `.doc_structure.yaml`（旧 config.yaml に相当）はユーザーのプロジェクトルートに配置され、プラグイン更新で上書きされない

---

## 機能要件

### REQ-002-01: レガシーファイルの検出と案内

**説明**: v2.0 の doc-advisor 管理ファイルが残存している場合、ユーザーに削除を案内する

**検出対象**:

- `.claude/commands/create-rules_toc.md`
- `.claude/commands/create-specs_toc.md`
- `.claude/doc-advisor/config.yaml`（v2.0 の旧パス）
- `.claude/doc-advisor/docs/`（v2.0 の旧構造）

**受入条件**:

- [ ] 上記ファイルの存在を検出できる
- [ ] 検出時にユーザーに削除を案内する
- [ ] ユーザー確認なしの自動削除は行わない（プラグイン環境ではユーザーのワークスペースを直接操作しない）

### REQ-002-02: ユーザー資産の保護

**説明**: ユーザーが独自に作成したファイルは削除しない

**保護対象**:

- `.claude/commands/` 内のユーザー独自コマンド
- `.claude/agents/` 内のユーザー独自エージェント
- `.claude/doc-advisor/toc/rules/`（ランタイム出力: ToC、チェックサム、作業ディレクトリ）
- `.claude/doc-advisor/toc/specs/`（ランタイム出力: ToC、チェックサム、作業ディレクトリ）

**受入条件**:

- [ ] `commands/` ディレクトリ自体は削除されない
- [ ] `agents/` 内の doc-advisor 以外のファイルは保持される

### REQ-002-03: config.yaml / .doc_structure.yaml の保護

**説明**: 既存の設定ファイルがある場合、上書きしない

**受入条件**:

- [ ] `.doc_structure.yaml` はプラグイン更新時に上書きされない
- [ ] ユーザーがカスタマイズした `root_dirs`・`doc_types_map` が保持される

### REQ-002-04: advisor agent → query-\* skill の移行

**説明**: advisor agent を query-\* skill に置き換える。旧 agent ファイルが残存している場合は削除を案内する

**検出対象**:

- `.claude/agents/rules-advisor.md`
- `.claude/agents/specs-advisor.md`

**置き換え先**（プラグインとして提供）:

- `/query-rules` skill
- `/query-specs` skill

**受入条件**:

- [ ] 旧 advisor agent の存在を検出できる
- [ ] 現行バージョン識別子を持つファイルは保護される
- [ ] query-\* skill がプラグイン経由で利用可能である

---

## 非機能要件

### REQ-002-NF-01: ToC ファイルの保持

**説明**: 既存の ToC ファイルはアップグレード時に削除しない

**受入条件**:

- [ ] `doc-advisor/toc/rules/rules_toc.yaml` は削除されない
- [ ] `doc-advisor/toc/specs/specs_toc.yaml` は削除されない
- [ ] 差分更新が可能

> **Note**: v2.0 の ToC は `doc-advisor/rules/rules_toc.yaml`（`toc/` なし）に存在する。パスが異なるため、v2.0 の ToC を v3.x 以降で直接利用するには手動でファイルを移動する必要がある。初回は `--full` での再生成を推奨。

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

| ID    | 内容                                   | 期待結果                                               |
| ----- | -------------------------------------- | ------------------------------------------------------ |
| T-001 | レガシー commands/ 検出                | doc-advisor コマンドの存在を検出、ユーザーコマンド無視 |
| T-002 | レガシー doc-advisor/ 検出             | config.yaml と docs/ の残存を検出                      |
| T-003 | config.yaml / .doc_structure.yaml 保護 | 既存設定が上書きされない                               |
| T-004 | agents/ カスタム保持                   | ユーザーの独自 agent が保持される                      |
| T-005 | advisor agent 検出                     | rules-advisor.md, specs-advisor.md の残存を検出        |
| T-006 | query-\* skill 利用可能                | query-rules, query-specs がプラグイン経由で動作する    |
| T-007 | ToC ファイル保持                       | 既存 ToC がアップグレード後も保持される                |

---

## 関連ドキュメント

- `REQ-001_doc_advisor.md`: Doc Advisor 基本要件
- `REQ-003_versioned_migration.md`: 段階的バージョンマイグレーション要件
