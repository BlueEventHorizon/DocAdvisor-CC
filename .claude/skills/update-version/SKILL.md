---
name: update-version
description: |
  Doc Advisor のバージョン番号を一括更新するスキル。
  setup.sh の DOC_ADVISOR_VERSION を単一の真実の源として、関連する全ファイルのバージョン表記を更新する。

  トリガー:
  - 「バージョンを更新」「version を上げる」「リリース準備」
  - 「X.Y にバージョンアップ」のような具体的なバージョン指定
---

# Update Version Skill

Doc Advisor のバージョン番号を一括更新する。

## バージョン管理の仕組み

### 単一の真実の源

`setup.sh` の `DOC_ADVISOR_VERSION` 変数が唯一のバージョン定義:

```bash
DOC_ADVISOR_VERSION="X.Y"
```

### テンプレートのプレースホルダー

`templates/` 配下のファイルは `{{DOC_ADVISOR_VERSION}}` プレースホルダーを使用:

```yaml
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
```

`setup.sh` 実行時に実際のバージョンに置換される。

### ハードコードされたバージョン

バージョンがハードコードされているのは `setup.sh` のみ:

| ファイル | パターン |
|----------|----------|
| setup.sh | `DOC_ADVISOR_VERSION="X.Y"` |
| CHANGELOG.md | バージョン履歴 |

他のファイル（Makefile, テスト等）は `setup.sh` から動的に取得する。
README.md, TECHNICAL_GUIDE.md 等にはバージョン表記を含めない。

## 使用方法

### 引数付き実行

```
/update-version X.Y
```

### 対話的実行

```
/update-version
```

プロンプト: 「新しいバージョン番号を入力してください」

## 手順

### 1. 現在のバージョンを確認

```bash
grep 'DOC_ADVISOR_VERSION=' setup.sh
```

### 2. バージョン更新スクリプトを実行（dry-run）

```bash
python3 .claude/skills/update-version/scripts/update_version.py NEW_VERSION --dry-run --project-root .
```

例: `python3 .claude/skills/update-version/scripts/update_version.py X.Y --dry-run --project-root .`

### 3. 変更内容を確認して実行

```bash
python3 .claude/skills/update-version/scripts/update_version.py NEW_VERSION --project-root .
```

注: `--project-root .` はカレントディレクトリがプロジェクトルートの場合に使用。省略するとスクリプト位置から自動検出を試みる。

### 4. CHANGELOG.md を編集

スクリプトはプレースホルダーセクションを追加するのみ。実際の変更内容を記入:

```markdown
## [X.Y.0] - YYYY-MM-DD

### Added
- (実際の追加機能を記載)

### Changed
- **Version identifier**: Updated from `OLD` to `NEW` across all managed files

### Fixed
- (実際の修正を記載)
```

### 5. テスト実行

```bash
cd tests && ./run_all_tests.sh
```

### 6. コミット

```bash
git add -A
git commit -m "chore: bump version to NEW_VERSION"
```

## 注意事項

- `templates/` 配下のファイルはプレースホルダーを使用しているため、直接編集不要
- `test_project*/` は `setup.sh` 再実行で更新される（通常は tests/ で自動的に再生成）
- CHANGELOG.md の「Version Comparison」テーブルは手動更新が必要な場合がある
