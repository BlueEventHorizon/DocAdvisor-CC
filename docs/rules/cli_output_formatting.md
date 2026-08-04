---
type: doc-advisor
title: CLI Output Formatting Guidelines
purpose: Defines how shell scripts and CLI tools color and lay out their output, assigning a role to each of the four colors and giving the echo patterns for each role.
content_details:
  - ANSI color code definitions RED / GREEN / BLUE / YELLOW and the NC reset sequence
  - "Role assigned to each color: green for success and banners, blue for configuration values and paths, yellow for commands the user should run, red for warnings and errors, uncolored for labels and prose"
  - Header and footer banner pattern using a green line of equals signs around the tool name and version
  - Configuration display pattern that colors only the value, leaving the label uncolored
  - Warning and error message patterns, including the parenthesized note form
  - Next-steps pattern that numbers the commands and colors only the command itself
  - PASS and FAIL prefixes for test result lines
  - Requirement to use echo -e so escape sequences are interpreted
  - Requirement to always reset with NC after a colored string
  - Accessibility rule that information must be conveyed by text as well, never by color alone
applicable_tasks:
  - Writing output for a new shell script
  - Adding colored output to an existing CLI tool
  - "Reviewing whether a script's color usage is consistent with the project"
  - Deciding which color a message belongs to
keywords:
  - echo -e
  - NC
  - ANSI escape sequence
  - banner
  - PASS
  - FAIL
  - Next steps
  - color reset
  - accessibility
body_hash: sha256:3790354118e6fb35e6e842ea3bcc7c02bba80c502e182ddbeddd825a5336404b
---

# CLI 出力フォーマット指針

シェルスクリプトやCLIツールの出力における色分けと表示形式の指針。

## 色コード定義

```bash
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color (リセット)
```

## 色の使い分け

| 色       | 用途                              | 例                       |
| -------- | --------------------------------- | ------------------------ |
| **緑**   | 成功メッセージ、ヘッダー/フッター | `Setup Complete`, バナー |
| **青**   | 設定値、パス、変数の値            | `RULES_DIR: rules`       |
| **黄**   | ユーザーが実行すべきコマンド      | `/index-docs --all`      |
| **赤**   | 警告、エラー、注意が必要な情報    | `python3 may be wrapped` |
| **なし** | ラベル、説明文、通常のテキスト    | `Configuration:`         |

## 出力パターン

### ヘッダー/フッターバナー（緑）

```bash
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}Tool Name (vX.X)${NC}"
echo -e "${GREEN}==========================================${NC}"
```

### 設定値の表示（青）

```bash
echo "Configuration:"
echo -e "  RULES_DIR: ${BLUE}${RULES_DIR}${NC}"
echo -e "  PYTHON_PATH: ${BLUE}${PYTHON_PATH}${NC}"
```

### 警告メッセージ（赤）

```bash
echo -e "  ${RED}(python3 may be wrapped: using explicit path for reliability)${NC}"
echo -e "${RED}Warning: File not found${NC}"
```

### 次のステップ/コマンド（黄）

```bash
echo "Next steps:"
echo -e "  1. Run ${YELLOW}/index-docs --key rules${NC} for initial ToC generation"
echo -e "  2. Run ${YELLOW}/index-docs --key specs${NC} for initial ToC generation"
```

### 成功メッセージ（緑）

```bash
echo -e "${GREEN}PASS${NC}: Test completed successfully"
echo -e "${GREEN}All tests passed!${NC}"
```

### エラーメッセージ（赤）

```bash
echo -e "${RED}FAIL${NC}: Test failed"
echo -e "${RED}Error: Invalid argument${NC}"
```

## 注意事項

1. **`echo -e` を使用**: エスケープシーケンスを解釈するために必須
2. **必ずリセット**: 色付き文字列の後に `${NC}` でリセット
3. **一貫性**: プロジェクト内で色の使い方を統一
4. **アクセシビリティ**: 色だけに依存せず、テキストでも情報を伝える

## 適用例

```bash
#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Header
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}My Script (v1.0)${NC}"
echo -e "${GREEN}==========================================${NC}"

# Configuration
echo ""
echo "Configuration:"
echo -e "  TARGET: ${BLUE}/path/to/target${NC}"

# Warning (if needed)
if [[ some_condition ]]; then
    echo -e "  ${RED}(Warning message here)${NC}"
fi

# Success
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}Complete${NC}"
echo -e "${GREEN}==========================================${NC}"

# Next steps
echo ""
echo "Next steps:"
echo -e "  1. Run ${YELLOW}some-command${NC}"
```
