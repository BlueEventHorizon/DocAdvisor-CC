# REQ-002: アップグレード要件（v2.0 → v4.x）

## 概要

Doc Advisor v2.0 から v4.x へのアップグレード時に必要な要件を定義する。

## 背景

v3.0 以降で以下の構造変更が行われた:

| 変更 | v2.0 | v3.x |
|------|------|------|
| コマンド | `commands/create-*_toc.md` | `skills/create-*-toc/SKILL.md` |
| 設定 | `doc-advisor/config.yaml` | `doc-advisor/config.yaml`（場所は同じ） |
| ドキュメント | `doc-advisor/docs/` | `doc-advisor/docs/`（場所は同じ） |
| コマンド形式 | `/create-rules_toc` | `/create-rules-toc` |
| ToC 出力先 | `doc-advisor/rules/` | `doc-advisor/toc/rules/` |
| Advisor | agent (`rules-advisor`, `specs-advisor`) | skill (`/query-rules`, `/query-specs`) |
| 設定構造 | `root_dir` (単数) + `target_dirs` | `root_dirs` (複数) + `target_glob` |

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

## 機能要件

### REQ-002-01: レガシーファイルの自動削除

**説明**: v2.0 の doc-advisor 管理ファイルを自動的に削除する

**削除対象**:
- `.claude/commands/create-rules_toc.md`
- `.claude/commands/create-specs_toc.md`
- `.claude/doc-advisor/config.yaml`（v2.0 の旧パス）
- `.claude/doc-advisor/docs/`（v2.0 の旧構造）

**受入条件**:
- [ ] setup.sh 実行時に上記ファイルが存在すれば自動削除される
- [ ] 削除されたファイルがコンソールに表示される
- [ ] ユーザー確認は不要（doc-advisor 管理ファイルのため）

### REQ-002-02: ユーザー資産の保護

**説明**: ユーザーが独自に作成したファイルは削除しない

**保護対象**:
- `.claude/commands/` 内のユーザー独自コマンド
- `.claude/agents/` 内のユーザー独自エージェント
- `.claude/doc-advisor/toc/rules/`（ランタイム出力: ToC、チェックサム、作業ディレクトリ）
- `.claude/doc-advisor/toc/specs/`（ランタイム出力: ToC、チェックサム、作業ディレクトリ）

**受入条件**:
- [ ] `commands/` ディレクトリ自体は削除されない（空でも残る）
- [ ] `agents/` 内の doc-advisor 以外のファイルは保持される
- [ ] 保持されるファイルがコンソールに表示される（「Preserving: xxx.md」）

### REQ-002-03: config.yaml の保護

**説明**: 既存の config.yaml がある場合、ユーザーに処理方法を選択させる

**選択肢**:
- `[o]` Overwrite: バックアップ（config.yaml.bak）を作成して上書き
- `[s]` Skip: 既存設定を保持（デフォルト）
- `[m]` Merge: セットアップ後に差分を表示

**受入条件**:
- [ ] 既存 config.yaml がある場合のみプロンプトが表示される
- [ ] デフォルトは Skip（Enter で既存設定を保持）
- [ ] Overwrite 選択時はバックアップが作成される
- [ ] バックアップは `doc-advisor/config.yaml.bak` に保存される

### REQ-002-04: agents/ の上書き方式

**説明**: agents/ はディレクトリ削除せず、ファイル上書きのみ行う

**理由**:
- ユーザーが独自に追加した agent を保護するため
- doc-advisor 管理の agent（toc-updater.md）は上書き更新

**受入条件**:
- [ ] `agents/` ディレクトリは `rm -rf` されない
- [ ] doc-advisor 管理の 2 ファイルは上書きされる
- [ ] それ以外のファイルは保持される

### REQ-002-05: skills/doc-advisor/ のクリーンインストール

**説明**: skills/doc-advisor/ は旧バージョンまたはバージョン識別子なしの場合に削除→再作成する

**理由**:
- doc-advisor 専用ディレクトリなので旧バージョンのファイルが残らないようにする
- ただし現行バージョン識別子を持つファイルはユーザーが意図的に配置した可能性があるため保護する（v3.5 でバージョン保護を導入）

**受入条件**:
- [ ] `skills/doc-advisor/` はバージョン識別子が旧版または未設定の場合に `rm -rf` で削除される
- [ ] 現行バージョン識別子を持つ `skills/doc-advisor/` は保護される
- [ ] 削除前に config.yaml の保護処理が完了している
- [ ] 削除された場合、再作成後に全ての必要ファイルが存在する

### REQ-002-06: advisor agent → query-\* skill の移行（v3.7）

**説明**: advisor agent を query-\* skill に置き換え、旧 agent ファイルを自動削除する

**削除対象**:
- `.claude/agents/rules-advisor.md`
- `.claude/agents/specs-advisor.md`

**置き換え先**:
- `.claude/skills/query-rules/SKILL.md`
- `.claude/skills/query-specs/SKILL.md`

**受入条件**:
- [ ] setup.sh 実行時に旧 advisor agent が存在すれば自動削除される
- [ ] 現行バージョン識別子を持つファイルは保護される
- [ ] 削除されたファイルがコンソールに表示される
- [ ] query-\* skill が正しくインストールされる

---

## 非機能要件

### REQ-002-NF-01: ToC ファイルの保持

**説明**: 既存の ToC ファイルはアップグレード時に削除しない

**受入条件**:
- [ ] `doc-advisor/toc/rules/rules_toc.yaml` は削除されない
- [ ] `doc-advisor/toc/specs/specs_toc.yaml` は削除されない
- [ ] v3.x のスキルで差分更新が可能

> **Note**: v2.0 の ToC は `doc-advisor/rules/rules_toc.yaml`（`toc/` なし）に存在する。パスが異なるため、v2.0 の ToC を v3.x で直接利用するには手動でファイルを移動する必要がある。初回は `--full` での再生成を推奨。

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
- [ ] v3.6 以降の全管理ファイルに `doc-advisor-version-xK9XmQ` 識別子が含まれる
- [ ] 識別子の一致/不一致で削除判断が行われる
- [ ] レガシー（v2.0）ファイルは識別子がないためファイル名指定で削除する

---

## テスト要件

### テストケース

| ID | 内容 | 期待結果 |
|----|------|----------|
| T-001 | クリーンインストール | 全ファイルが正常に配置される |
| T-002 | レガシー commands/ 削除 | doc-advisor コマンドのみ削除、ユーザーコマンド保持 |
| T-003 | レガシー doc-advisor/ 削除 | config.yaml と docs/ が削除される |
| T-004 | config.yaml スキップ | 既存設定が保持される |
| T-005 | config.yaml 上書き | バックアップが作成され、新設定が適用される |
| T-006 | skills/doc-advisor/ クリーン | 古いファイルが残らない |
| T-007 | agents/ カスタム保持 | ユーザーの独自 agent が保持される |
| T-008 | advisor agent 削除（v3.7） | rules-advisor.md, specs-advisor.md が削除される |
| T-009 | query-\* skill インストール | query-rules/SKILL.md, query-specs/SKILL.md が存在する |
| T-010 | classify-docs skill インストール（v4.0） | classify-docs/SKILL.md が存在する |
| T-011 | check_config.sh コピー（v4.0） | scripts/check_config.sh が存在し実行権限がある |
| T-012 | スキル Pre-check（v4.0） | create-*-toc, query-* の SKILL.md に Pre-check セクションが含まれる |

**テストスクリプト**: `tests/test_setup_upgrade.sh`

---

### REQ-002-07: classify-docs スキルの復活（v4.0）

**説明**: v3.9 で削除された classify-docs スキルを復活し、AI 駆動のディレクトリ分類に変更する

**変更内容**:
- `setup_dirs.sh` を廃止（対話的な手動ディレクトリ入力は不要に）
- `--skip-doc-structure` フラグを廃止
- `/classify-docs` スキルをテンプレートとして `templates/skills/classify-docs/SKILL.md` に配置
- `classify_dirs.py` と `classification_rules.md` をテンプレートに追加

**受入条件**:
- [ ] setup.sh 実行後に `skills/classify-docs/SKILL.md` が存在する
- [ ] `classify_dirs.py` と `classification_rules.md` が `doc-advisor/scripts/` と `doc-advisor/docs/` にコピーされる
- [ ] `/classify-docs` 実行で AI がディレクトリを分類し `config.yaml` の `root_dirs` を更新する

### REQ-002-08: スキル Pre-check の導入（v4.0）

**説明**: ドキュメントディレクトリ未設定時に `/classify-docs` を先に実行させるスキル Pre-check を導入する

**変更内容**:
- `check_config.sh` を `templates/doc-advisor/scripts/` に追加
- 各スキル（create-*-toc, query-*）の SKILL.md 先頭に Pre-check ステップを追加
- Pre-check は `check_config.sh` を実行し、出力があれば `/classify-docs` を先に実行させる

**受入条件**:
- [ ] setup.sh 実行後に `scripts/check_config.sh` が存在し実行権限がある
- [ ] 対象カテゴリの `root_dirs` が `config.yaml` に設定済みの場合、`check_config.sh` は何も出力しない（`.doc_structure.yaml` がある場合は setup.sh が取り込み済みのため `root_dirs` は設定済み）
- [ ] 未設定時のみ `/classify-docs` を案内する `[ACTION REQUIRED]` メッセージが出力される
- [ ] `check_config.sh` はカテゴリ引数（rules/specs）を受け付け、対象カテゴリ単位で検証する
- [ ] 4 スキル（create-rules-toc, create-specs-toc, query-rules, query-specs）の SKILL.md に Pre-check セクションがある

---

## 関連ドキュメント

- `DES-001_setup_script.md`: setup.sh 詳細設計
- `meta/setup_design_decisions.md`: 設計決定書
- `TECHNICAL_GUIDE.md`: Migration セクション
