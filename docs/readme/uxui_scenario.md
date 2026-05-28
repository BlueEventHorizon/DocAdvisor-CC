# /forge:start-uxui-design 適用シナリオ

要件定義書（ASCII アート付きの画面仕様）を入力に、**デザイントークン（THEME-xxx）** と **UI コンポーネント視覚仕様（CMP-xxx）** を創造するスキルの活用例。Apple HIG・Don Norman・Dieter Rams・Nielsen・Gestalt の知識ベースに基づき、理論的根拠のある「かっこいい」デザインを設計する。

> **Figma デザインがある場合**: UX/UI デザインはデザイナーにより完了済みと見なす。`/forge:start-requirements {feature} --mode from-figma` で要件抽出に進む。Figma デザインの UX 品質を検証したい場合は `/forge:review uxui` を使用する。

---

## スキルの位置づけ

```
start-requirements → start-uxui-design → start-design → start-plan → start-implement
 (何を作るか)          (どう見せるか)       (どう作るか)     (いつ作るか)   (作る)
```

Figma がない場合、要件定義書の ASCII アートで表現された画面構成を「かっこいいデザイン」に変換するのが本スキルの核心的役割。

---

## シナリオ 1: 要件定義からのデザイン創造（メインシナリオ）

**状況**: カフェ注文アプリの要件定義書が完成した。ASCII アートで画面レイアウトが定義済み。デザイナーは不在で、エンジニアがデザインも含めて実装する。

```
/forge:start-uxui-design cafe-order --platform ios
```

**前提**: `/forge:start-requirements cafe-order` が完了済みで、以下が揃っている:

- `SCR-001_menu_list.md` — メニュー一覧画面（ASCII アート付き）
- `SCR-002_drink_detail.md` — ドリンク詳細画面
- `CMP-001_menu_item_card.md` — メニューアイテムカード
- `FNC-001_cart_management.md` — カート管理機能

**フロー**:

1. Phase 1: 要件定義書を自動読み込み → 画面構成・ASCII アート・コンポーネントを把握
2. Phase 2: アプリの性格を「モダン・洗練」と分析 → Minimal Clean スタイルを提案 → カラー方向性を提示
3. Phase 3: 60-30-10 ルールに基づくカラーパレット、SF Pro タイポグラフィスケール、8pt グリッドのスペーシングを設計
4. Phase 4: ASCII アートの `[カートに追加]` → 「50pt 高さ、角丸 12pt、accent カラー、Semibold 17pt」の具体的視覚仕様に変換
5. Phase 5: Don Norman 3 層 + Rams 原則で自己評価
6. Phase 6: `THEME-001` / `CMP-001` / `UXEVAL-001` を生成 → `/forge:review uxui` で検証

**価値**: デザイナー不在でも、学術的根拠に基づいた一貫性のあるデザインシステムを構築できる。ASCII アートから実装可能な具体的仕様（HEX 値、pt 値）に変換される。

---

## シナリオ 2: デザイン文書の UX レビュー（独立実行）

**状況**: `start-uxui-design` のワークフロー内にレビューは組み込み済みだが、以下の場合に独立してレビューを実行する:

- チームメンバーが作成したデザイン文書を評価したい
- `start-requirements --mode from-figma` で生成された THEME/CMP 文書の UX 品質を検証したい
- 既存のデザイン文書を修正後に再レビューしたい

```
/forge:review uxui --files specs/cafe-order/requirements/THEME-001_cafe_order_design_tokens.md
```

3 つの perspectives で検証する:

| Perspective      | 検証内容                                       |
| ---------------- | ---------------------------------------------- |
| `hig_compliance` | HIG 4 原則への適合、プラットフォーム標準の使用 |
| `usability`      | Nielsen ヒューリスティクス、アクセシビリティ   |
| `visual_system`  | トークンの一貫性、Gestalt 原則の活用           |

`--auto` を付ければ指摘の自動修正まで行う。

**Figma デザインのレビューにも使える**: `start-requirements --mode from-figma` で生成された THEME/CMP 文書に対して `/forge:review uxui` を実行すれば、Figma デザインの UX 品質を間接的に検証できる。

---

## シナリオ 3: Forge パイプライン連携 — 要件から実装まで一気通貫

**状況**: 新機能「お気に入り一覧」の追加。デザイナー不在の個人開発。

**フロー全体**:

```
1. /forge:start-requirements favorites         # 要件定義（ASCII アート付き画面仕様）
2. /forge:start-uxui-design favorites           # デザイン創造 → THEME + CMP + UXEVAL（レビュー込み）
3. /forge:start-design favorites                # 技術設計書作成（THEME/CMP を参照）
4. /forge:start-plan favorites                  # 計画書作成
5. /forge:start-implement favorites             # タスク実行
```

他の `start-xxx` スキルと同様、`start-uxui-design` のワークフロー内に `/forge:review uxui --auto` が含まれているため、手動でレビューを実行する必要はない。

**価値**: 要件の ASCII アートから一貫したデザインシステムが生まれ、それが設計書のデータモデルや定数定義に反映される。デザイナーなしでも品質の高いアプリが作れる。

---

## シナリオ 4: 参考デザイン付きの創造

**状況**: タスク管理アプリを作りたい。Pinterest や Dribbble で見つけた「かっこいい」デザインの雰囲気を取り入れたい。

```
/forge:start-uxui-design task-manager --platform ios
```

**フロー**:

1. Phase 1: 要件定義書を読み込み + 参考画像/URL を提示（「こんな雰囲気で」）
2. Phase 2: 参考デザインの雰囲気を分析 → 「Soft Depth スタイル、暖色系アクセント」と方向性を設定
3. Phase 3-4: 参考デザインのトーンを活かしつつ、HIG 準拠のトークン・コンポーネントを設計
4. Phase 5: HIG からの逸脱がないかチェック（「かっこいいけど使いにくい」を防止）

**注意**: 参考デザインはあくまで「方向性の手がかり」であり、値を逆解析・コピーする対象ではない。デザイントークンの値は知識ベースの理論に基づいて独自に設計する。

---

## シナリオ 5: 既存アプリのリデザイン

**状況**: macOS のファイル管理ユーティリティが古くなった。リデザインを計画中。

```
1. /forge:start-requirements file-manager --mode reverse-engineering   # 既存アプリから要件を逆解析
2. /forge:start-uxui-design file-manager --platform macos              # 新しいデザインを創造
```

**フロー**:

1. まず `start-requirements --mode reverse-engineering` で既存アプリの要件を抽出
2. 要件定義書ができたら `start-uxui-design` で新しいデザインを創造
3. 現行のスクリーンショットを「参考デザイン」として提示し、変えたい点・残したい点を伝える
4. Liquid Glass 対応、ダークモード対応など最新トレンドを反映

---

## 推奨シナリオ

| 優先度 | シナリオ                        | 理由                                                                   |
| ------ | ------------------------------- | ---------------------------------------------------------------------- |
| 最高   | シナリオ 1（要件→デザイン創造） | 本スキルの核心機能。デザイナー不在でも品質の高いデザインシステムを構築 |
| 最高   | シナリオ 2（UX レビュー）       | 作成したデザインの品質を継続的に検証。Figma デザインのレビューにも対応 |
| 高     | シナリオ 3（パイプライン連携）  | forge の全工程を繋げる本来の使い方                                     |
| 中     | シナリオ 4（参考デザイン付き）  | 方向性の指定で創造の精度が上がる                                       |
| 中     | シナリオ 5（リデザイン）        | 既存アプリの改善に直結                                                 |
