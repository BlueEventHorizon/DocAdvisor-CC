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

| 色       | 用途                              | 例                         |
| -------- | --------------------------------- | -------------------------- |
| **緑**   | 成功メッセージ、ヘッダー/フッター | `Setup Complete`, バナー   |
| **青**   | 設定値、パス、変数の値            | `RULES_DIR: rules`         |
| **黄**   | ユーザーが実行すべきコマンド      | `/create-rules-toc --full` |
| **赤**   | 警告、エラー、注意が必要な情報    | `python3 may be wrapped`   |
| **なし** | ラベル、説明文、通常のテキスト    | `Configuration:`           |

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
echo -e "  1. Run ${YELLOW}/create-rules-toc --full${NC} for initial ToC generation"
echo -e "  2. Run ${YELLOW}/create-specs-toc --full${NC} for initial ToC generation"
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
