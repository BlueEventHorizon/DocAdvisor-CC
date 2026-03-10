# Claude Code シェルラッパーと Python パス取得

**作成日**: 2026-03-08
**作成者**: k_terada
**目的**: Claude Code 環境下でのシェルコマンド実行の注意点と、Python パス取得の汎用パターンを記述する
**適用範囲**: Claude Code から Bash を経由して Python を呼び出すあらゆるスクリプト

---

## Claude Code のシェルラッパー

Claude Code はシェルコマンドを直接実行せず、ラッパー経由で実行する。
このラッパーが有効かどうかは以下で判定できる：

```bash
# ラッパーが有効 = shell-snapshots ディレクトリが存在して空でない
[[ -d "$HOME/.claude/shell-snapshots" ]] && [[ -n "$(ls -A "$HOME/.claude/shell-snapshots" 2>/dev/null)" ]]
```

---

## ラッパーの種類と動作

Python の実行には複数のラッパーが関与する場合がある。

### シェル関数ラッパー（コマンド名で呼んだときだけ介入）

セキュリティツール等が `python3` をシェル関数としてラップしている場合がある：

```bash
# which python3 の結果がパスではなくシェル関数になる例
python3 () {
    wrapSafeChainCommand "python3" "$@"
}
```

シェル関数は**コマンド名で呼んだときのみ**介入する。絶対パスで呼んだ場合はスキップされる。

| 呼び方                       | `wrapSafeChainCommand` の介入 |
| ---------------------------- | ----------------------------- |
| `python3 script.py`          | あり（シェル関数が呼ばれる）  |
| `/usr/bin/python3 script.py` | なし（シェル関数をバイパス）  |

### /usr/bin/which の動作

```bash
which python3       # シェル関数の定義を返す（パスではない）
/usr/bin/which python3  # シェル関数をスキップ → 実際のバイナリパスを返す
```

`/usr/bin/which python3` は Claude Code のシェルラッパーと `wrapSafeChainCommand` の**両方をバイパス**する。
返ってきた絶対パスで Python を実行する際も、シェル関数は介入しない。

```bash
# NG: Claude Code ラッパー環境では意図しない解決になる可能性がある
python3 some_script.py

# NG: shell の which はシェル関数を返す（パスではない）
PYTHON=$(which python3)

# OK: /usr/bin/which で実際のバイナリパスを取得
#     （シェル関数ラッパーはバイパスされる）
PYTHON=$(/usr/bin/which python3)
"$PYTHON" some_script.py
```

---

## 汎用パターン: Python パスの安全な取得

### パターンA: スクリプト実行時に毎回検出する

ツールを単体で配布する場合や、インストール先に保存場所がない場合に使う。

```bash
detect_python() {
    if [[ -d "$HOME/.claude/shell-snapshots" ]] && \
       [[ -n "$(ls -A "$HOME/.claude/shell-snapshots" 2>/dev/null)" ]]; then
        # /usr/bin/which でシェル関数をスキップし、実際のバイナリパスを取得
        # （wrapSafeChainCommand 等のシェル関数ラッパーもバイパスされる）
        /usr/bin/which python3 2>/dev/null || echo "python3"
    else
        echo "python3"
    fi
}

PYTHON_CMD=$(detect_python)
"$PYTHON_CMD" some_script.py
```

### パターンB: インストール時に検出してファイルに保存し、実行時に読み戻す

セットアップスクリプトがある場合（推奨）。一度だけ検出し、設定ファイルやドキュメントに埋め込む。

**インストール時（一回のみ）:**

```bash
if [[ -d "$HOME/.claude/shell-snapshots" ]] && \
   [[ -n "$(ls -A "$HOME/.claude/shell-snapshots" 2>/dev/null)" ]]; then
    PYTHON_PATH=$(/usr/bin/which python3 2>/dev/null || echo "python3")
    # $HOME を文字列として保存（実行時に展開するため）
    PYTHON_PATH="${PYTHON_PATH/#$HOME/\$HOME}"
else
    PYTHON_PATH="python3"
fi
# PYTHON_PATH を設定ファイルに書き込む
echo "PYTHON_PATH=${PYTHON_PATH}" >> config.sh
```

**実行時（毎回）:**

```bash
# 設定ファイルから読み戻す
source config.sh
PYTHON_CMD=$(eval echo "$PYTHON_PATH")
"$PYTHON_CMD" some_script.py
```

---

## 設計原則

| 原則                            | 理由                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `/usr/bin/which` を使う         | shell の `which` はシェル関数を返す場合がある。`/usr/bin/which` はシェル関数をスキップして実際のバイナリパスを返す |
| 保存時は `$HOME` を文字列に置換 | 実行ユーザーの `$HOME` が異なる環境への移植性のため                                                                |
| 読み戻し時は `eval echo` で展開 | 文字列 `\$HOME` を実際のパスに変換するため                                                                         |
| 検出ロジックは一箇所にまとめる  | 複数箇所に書くと環境変化への追従が困難になる                                                                       |

---

## 参考: Doc Advisor での実装

Doc Advisor は パターンB を採用している。

- **インストール時**: `setup.sh` が Python パスを検出し、`toc_orchestrator.md` の `{{PYTHON_PATH}}` プレースホルダーに埋め込む
- **実行時**: テストスクリプト等が `toc_orchestrator.md` を grep して Python パスを読み戻す
