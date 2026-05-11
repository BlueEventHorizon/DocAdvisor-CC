---
name: build-index
description: |
  doc-db の index を構築・更新する薄いラッパー。
  トリガー: "/build-index", "doc-db の index を作る"
user-invocable: true
argument-hint: "[--category rules|specs] [--full] [--check] [--doc-type requirement,design,plan]"
allowed-tools: Bash
---

# /build-index

`plugins/doc-db/scripts/build_index.py` を呼び出して index を構築する。

```bash
python3 ".claude/doc-db/scripts/build_index.py" "$@"
```
