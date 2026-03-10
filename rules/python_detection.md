# Python パス検出ルール

**作成日**: 2026-03-08
**作成者**: k_terada
**目的**: シェルスクリプトで Python を呼び出す際のパス検出方法を統一する

---

## 背景: なぜ `python3` だけでは不十分か

Claude Code はコマンドをシェルラッパー経由で実行する。
ラッパーの存在は `~/.claude/shell-snapshots/` ディレクトリが空でないことで判断できる。

このラッパー環境では `python3` コマンドの PATH 解決が意図通りに動作しない場合があり、
想定外の Python インタープリターが使われるリスクがある。

---

## 2フェーズ設計

```
インストール時                         実行時（tests、スクリプト）
┌─────────────────────────────┐        ┌───────────────────────────────────┐
│ setup.sh                    │        │ tests/*.sh / 実行スクリプト       │
│                             │        │                                   │
│ 1. shell-snapshots 確認     │        │ 1. toc_orchestrator.md を grep    │
│ 2. /usr/bin/which python3   │──────▶ │ 2. eval echo で $HOME を展開      │
│ 3. $HOME を文字列に置換     │        │ → PYTHON_CMD で Python を呼ぶ     │
│ 4. toc_orchestrator.md に   │        └───────────────────────────────────┘
│    {{PYTHON_PATH}} として    │
│    埋め込む                 │
└─────────────────────────────┘
```

**フェーズ1（検出）は `setup.sh` でのみ行う。**
**フェーズ2（再利用）は `toc_orchestrator.md` から読み戻す。**

---

## フェーズ1: パス検出（`setup.sh` のみ）

```bash
# Detect Python path
if [[ -d "$HOME/.claude/shell-snapshots" ]] && [[ -n "$(ls -A "$HOME/.claude/shell-snapshots" 2>/dev/null)" ]]; then
    # シェルラッパーが有効 → /usr/bin/which でシェル関数をスキップし実バイナリパスを取得
    # （wrapSafeChainCommand 等のシェル関数ラッパーもバイパスされる）
    PYTHON_PATH=$(/usr/bin/which python3 2>/dev/null || echo "python3")
    PYTHON_CMD="${PYTHON_PATH}"
    # テンプレートへの埋め込み用: $HOME を文字列 "\$HOME" に置換（実行時に展開される）
    PYTHON_PATH="${PYTHON_PATH/#$HOME/\$HOME}"
else
    # シェルラッパーなし → python3 をそのまま使用
    PYTHON_CMD="python3"
    PYTHON_PATH="python3"
fi
```

**ポイント:**

- `which` ではなく `/usr/bin/which` を使う（shell の `which` は `wrapSafeChainCommand` 等のシェル関数を返す場合があるため）
- `/usr/bin/which` はシェル関数をスキップして実際のバイナリパスを返す。取得した絶対パスで呼ぶとシェル関数ラッパーもバイパスされる
- `PYTHON_CMD`: このスクリプト内での即時実行に使う（`$HOME` が展開済みの実パス）
- `PYTHON_PATH`: テンプレートファイルへの書き込み用（`$HOME` は文字列、実行時に展開）

---

## フェーズ2: パス再利用（tests/*.sh、スクリプト）

```bash
# setup.sh が toc_orchestrator.md に埋め込んだ Python パスを読み戻す
PYTHON_CMD=$(grep -oE '(\$HOME|~|/)[^"]*python3' .claude/doc-advisor/docs/toc_orchestrator.md 2>/dev/null | head -1 || echo "python3")
PYTHON_CMD=$(eval echo "$PYTHON_CMD")
```

**ポイント:**

- `toc_orchestrator.md` には setup 時に決定した Python パスが埋め込まれている
- `eval echo` で `\$HOME` → `$HOME` に展開してから使用
- `|| echo "python3"` は `toc_orchestrator.md` がない環境（未インストール等）へのフォールバック

---

## ルール [MANDATORY]

| シーン                              | すべきこと                                      |
| ----------------------------------- | ----------------------------------------------- |
| `setup.sh` で Python を呼ぶ         | フェーズ1で `PYTHON_CMD` を検出してそのまま使う |
| `tests/*.sh` で Python を呼ぶ       | フェーズ2で `toc_orchestrator.md` から読み戻す  |
| 新しい実行スクリプト（`.sh`）を追加 | フェーズ2のパターンをコピーする                 |
| `setup.sh` の検出ロジックを変更     | フェーズ1のみ修正する（フェーズ2は変更不要）    |

---

## アンチパターン（避けるべき実装）

### ❌ 独自検出を書く

```bash
# NG: 別の検出ロジックを独自に実装する
PYTHON=$(python3 --version 2>&1 | grep -oE "python[0-9.]+" || echo "python3")
```

→ setup.sh の検出結果と乖離する。インストール環境によって動作が変わる。

### ❌ フェーズ1のロジックをコピーして別のスクリプトに書く

```bash
# NG: setup.sh と同じ検出ロジックをテストスクリプトにも書く
if [[ -d "$HOME/.claude/shell-snapshots" ]]; then
    PYTHON_CMD=$(/usr/bin/which python3)
    ...
fi
```

→ フェーズ1はインストール時の一回限りの処理。実行スクリプトでは toc_orchestrator.md を読むだけでよい。

### ❌ `python3` をハードコード

```bash
# NG: 常に python3 を使う
python3 .claude/doc-advisor/scripts/some_script.py
```

→ シェルラッパー環境で意図しない Python が使われる可能性がある。

---

## 参考: `toc_orchestrator.md` への埋め込み

`setup.sh` が `templates/doc-advisor/docs/toc_orchestrator.md` の `{{PYTHON_PATH}}` プレースホルダーを
実際のパスに置換してインストール先にコピーする。

インストール後のファイル例:

```
$HOME/.pyenv/shims/python3 .claude/doc-advisor/scripts/create_pending_yaml.py --target rules --full
```

この文字列を `grep -oE '(\$HOME|~|/)[^"]*python3'` で抽出している。
