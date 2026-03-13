# Python 呼び出しルール

**作成日**: 2026-03-08
**更新日**: 2026-03-10
**作成者**: k_terada
**目的**: シェルスクリプトで Python を呼び出す際の方法を統一する

---

## 結論: `python3` をそのまま使う

Claude Code の shell wrapper（`wrapSafeChainCommand`）経由でも `python3` は正しく
pyenv 管理インタープリターを解決することが実証された。

```bash
$ command -v python3
python3               # shell function（フルパスではない）

$ python3 --version
Python 3.14.3         # pyenv の python3 が使われている
```

フルパス検出は不要。すべてのスクリプトで `python3` をそのまま使う。

---

## ルール [MANDATORY]

| シーン                                               | すべきこと                    |
| ---------------------------------------------------- | ----------------------------- |
| `setup.sh` で Python を呼ぶ                          | `PYTHON_CMD="python3"` を使う |
| `tests/*.sh` で Python を呼ぶ                        | `PYTHON_CMD=python3` を使う   |
| インストール先のコマンド（`toc_orchestrator.md` 等） | `python3` をそのまま記述する  |

---

## アンチパターン（避けるべき実装）

### ❌ フルパスを検出して使う

```bash
# NG: shell-snapshots の存在でフルパスを取得する
if [[ -d "$HOME/.claude/shell-snapshots" ]]; then
    PYTHON_PATH=$(/usr/bin/which python3)
fi
```

→ `python3` は wrapper 経由でも正しく動く。フルパス検出は不要な複雑性。

### ❌ `toc_orchestrator.md` から grep して使う

```bash
# NG: インストール先から Python パスを読み戻す
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/toc_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
```

→ `python3` で動作するため、このような間接参照は不要。

---

## 背景（旧設計との違い）

旧設計（v4.4 以前）では 2 フェーズ検出を採用していた:

- Phase 1（`setup.sh`）: `/usr/bin/which python3` でフルパスを取得し `toc_orchestrator.md` に埋め込む
- Phase 2（`tests/*.sh`）: `toc_orchestrator.md` を grep してパスを読み戻す

この設計は「wrapper 経由では `python3` が意図しないインタープリターになるリスクがある」という
仮説に基づいていた。しかし実証検証の結果、`python3`（`wrapSafeChainCommand` 経由）は
pyenv 管理インタープリターを正しく解決することが確認されたため、旧設計を廃止した。
