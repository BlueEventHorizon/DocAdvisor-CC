# UXUI デザインガイド

要件定義書の ASCII アート付き画面仕様を入力に、デザイントークンと UI コンポーネント視覚仕様を UX 評価付きで生成する。**`/forge:start-requirements` の Figma なし時補完**として位置づけられ、Figma デザインも既存実装もない状態でゼロから UI を設計する際に使用する。デザイン方向性は Phase 2.0（Design Intent の取得）で要件本文・既存コードから読み取り、または AI が推定して AskUserQuestion で確認する。プロジェクトレベルのモード設定は持たない。

## start-uxui-design

```
/forge:start-uxui-design [feature] [--platform ios|macos]
```

| 引数         | 説明                                  |
| ------------ | ------------------------------------- |
| `feature`    | Feature 名（省略時は対話で確定）      |
| `--platform` | `ios` / `macos`（省略時は対話で選択） |

### いつ使うか

- 要件定義書が完成した後、設計書を作成する前
- iOS / macOS アプリのデザインシステムを構築したいとき
- デザイナーなしで理論に裏付けられた UI を作りたいとき

### パイプラインでの位置づけ

```
start-requirements → start-uxui-design → start-design → start-plan → start-implement
 (何を作るか)          (どう見せるか)       (どう作るか)     (いつ作るか)   (作る)
```

start-uxui-design はオプション。デザイントークンが不要な場合はスキップして start-design に進める。

### 使用例

```bash
# iOS アプリのデザイン生成
/forge:start-uxui-design user-auth --platform ios

# macOS アプリ、Feature 名は対話で決定
/forge:start-uxui-design --platform macos
```

---

## 3 層統合フレームワーク

全デザイン判断の基盤となる階層構造。下層から順に適用し、上層は下層を超えることができない。

| 層                  | 役割           | 例                                         | 制約                          |
| ------------------- | -------------- | ------------------------------------------ | ----------------------------- |
| 第 1 層: 認知の制約 | 従う（不可侵） | Fitts の法則、Hick の法則、コントラスト比  | 違反するデザインは不可        |
| 第 2 層: 構造の道具 | 組み合わせる   | モジュラースケール、色彩調和、8pt グリッド | 第 1 層を破る組み合わせは不可 |
| 第 3 層: 美の方向性 | 選択する       | Dieter Rams、Don Norman、Tufte、わびさび   | 第 1・2 層の範囲内で自由      |

---

## ワークフロー

| Phase | 内容                                                                          | 知識ベース                                         |
| ----- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| 1     | 要件の読み込み（ASCII アート解析）                                            | —                                                  |
| 2.0   | **Design Intent の取得**（要件本文 → 既存コード → AI 推定 + AskUserQuestion） | design_philosophy.md                               |
| 2     | デザイン方向性の決定（緊張軸・参照文化・発散、Design Intent で条件分岐）      | design_philosophy.md                               |
| 3     | デザイントークン創造（色彩・タイポグラフィ・スペーシング・署名ルール）        | apple_design_principles.md、プラットフォームガイド |
| 4     | コンポーネント視覚設計（ASCII → HIG 準拠コンポーネント）                      | プラットフォームガイド、テンプレート               |
| 5     | UX 自己評価（3 層フレームワーク + Distinctiveness / Memorability、条件付き）  | design_philosophy.md                               |
| 6     | 文書生成・品質確認（`/forge:review uxui --auto`）                             | review_criteria_uxui.md                            |

### Design Intent 駆動の分岐

Phase 2.0 で以下を構造化して取得する（ユーザー体験・緊張軸・差別化重要度・参照・禁止事項・署名要素必要性）。値により Phase の発動が決まる:

| Design Intent                                                      | 分岐                                       |
| ------------------------------------------------------------------ | ------------------------------------------ |
| `distinctiveness.importance: 低` & `signature_required: 不要`      | Phase 2.2-2.5 / 3.5 / 4.5 / 5.4 を SKIP    |
| `distinctiveness.importance: 中`                                   | Phase 2.2 / 2.5 のみ実行、2.3-2.4 は簡略化 |
| `distinctiveness.importance: 高` または `signature_required: 必要` | 全 Phase 実行                              |

モード抽象（stable/bold 等）は導入しない。Design Intent の内容から自然に挙動が分岐する。

### 参照画像（任意）

競合スクリーンショットやムードボード画像を `{specs_root}/{feature}/requirements/uxui_references/{competitors,inspirations}/` に配置可能。存在する場合は Phase 5.4 レビューで画像ベースの類似度・整合性検証が追加される。`.gitignore` で `competitors/` / `inspirations/` はデフォルト除外（著作権配慮）。

### 出力

| ドキュメント           | ID 体系   | 内容                                                             |
| ---------------------- | --------- | ---------------------------------------------------------------- |
| デザイントークン       | THEME-xxx | 色彩、タイポグラフィ、スペーシング、エレベーション               |
| コンポーネント視覚仕様 | CMP-xxx   | 各 UI コンポーネントの視覚設計（サイズ、状態、インタラクション） |

---

## UX レビュー

`/forge:review uxui` で独立レビューも可能。4 つの perspectives を優先順位付きで検証する（上位が下位を侵す場合は上位優先）:

| # | Perspective         | 観点                                         | 適用                                                                   |
| - | ------------------- | -------------------------------------------- | ---------------------------------------------------------------------- |
| 1 | **hig_compliance**  | Apple HIG 4 原則への適合                     | 常時                                                                   |
| 2 | **usability**       | Nielsen ヒューリスティクス、アクセシビリティ | 常時                                                                   |
| 3 | **visual_system**   | トークンの一貫性、Gestalt 原則               | 常時                                                                   |
| 4 | **distinctiveness** | 差別化、記憶残存、署名要素、禁止事項の順守   | Design Intent に応じて適用強度を調整（未取得 or 低優先度では 🟢 降格） |

`/forge:review uxui` が start-uxui-design を経ずに呼ばれた場合、Design Intent は対象文書から推定し、レビュー結果の前置きに表示する。distinctiveness の判定基準は AI 検証可能な形式（「5 秒ルック」「競合 5 つ比較」等の人間テスト前提指標は使用しない）。

```bash
# デザイントークンとコンポーネント仕様をレビュー
/forge:review uxui --files specs/user-auth/design/

# 自動修正付き
/forge:review uxui --files specs/user-auth/design/ --auto
```

---

## 適用シナリオ

詳細な適用シナリオは [uxui_scenario.md](../uxui_scenario.md) を参照。

| シナリオ             | 概要                                     |
| -------------------- | ---------------------------------------- |
| 新規 iOS アプリ      | ゼロからデザインシステムを構築           |
| 既存アプリの UI 統一 | 既存コンポーネントをトークンベースに移行 |
| macOS アプリ         | macOS HIG に特化したトークン生成         |
| デザインレビューのみ | 既存デザイン仕様を UX 観点でレビュー     |
| 要件変更後の再生成   | ASCII アート変更に追従してトークンを更新 |
