# Index 候補生成ワークフロー

Embedding（セマンティック検索）ベースで関連文書の候補パスを生成する。
**候補パスの生成まで**が責務。ファイル内容の Read・最終判定は呼び出し元が行う。

## パラメータ

| 変数         | 説明                   |
| ------------ | ---------------------- |
| `{category}` | `rules` または `specs` |
| `{task}`     | 検索対象タスクの説明   |

## Auto-update

インデックスを差分更新する（未作成時は自動フルビルド、変更なし時はスキップ）。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/scripts/embed_docs.py --category {category}
```

- `{"status": "ok", ...}` → Procedure へ
- `{"status": "partial", ...}` → 警告を記録し、Procedure へ
- `{"status": "error", ...}` → 候補なし（空リスト）として返す。エラーにしない

## Procedure

1. セマンティック検索を実行する:
   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/scripts/search_docs.py --category {category} --skip-stale-check --query "{task}"
   ```
2. タスク説明に固有名詞・識別子が含まれる場合は全文検索を補足する:
   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/scripts/grep_docs.py --category {category} --keyword "{固有名詞}"
   ```
3. 検索結果のパスを候補リストとして保持する

## Error Handling

`search_docs.py` が `{"status": "error", ...}` を返した場合:

- **"Model mismatch"** → `--full` で再構築を試行:
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 $DOC_ADVISOR_CODEX_ROOT/resources/doc-advisor/scripts/embed_docs.py --category {category} --full
  ```
  成功後、Procedure の Step 1 をリトライ
- **"API error"** / **"OPENAI_API_KEY not set"** → 候補なし（空リスト）として返す。エラーにしない
