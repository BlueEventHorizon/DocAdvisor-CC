# Codex Confirmation Protocol

Use this protocol whenever a forge wrapper reaches a decision point that would
have used a dedicated interactive confirmation in another runtime.

Stop and ask the user before continuing when:

- creating, deleting, moving, or overwriting files or directories
- changing `.doc_structure.yaml` or other project configuration
- choosing between multiple plausible document locations or modes
- proceeding with uncertain classification or incomplete source documents
- applying review findings or making broad edits
- running git operations, version updates, or cleanup operations

Confirmation format:

```text
現在の判断:
推奨案:
選択肢:
1. 推奨案で進める
2. 修正して進める
3. 中止する
```

Wait for the user's reply before taking the action. If the user already gave a
clear instruction for the exact action, continue without repeating the question.
