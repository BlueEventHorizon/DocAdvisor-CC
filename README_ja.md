# Doc Advisor

[![License MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## はじめに

生成AIに「ドキュメントを読んで」と指示しても、重要な仕様を見落とすことがあります。
Doc Advisor は、この構造的な限界を前提に「必要な文書だけを確実に読ませる」ための運用を実現する仕組みです。

## 前提

[なぜ生成AIは「ドキュメントを読んで」と言っても読まないのか？ ― コンテキスト・エンジニアリングと Doc Advisor](https://zenn.dev/k2moons/articles/ff6399ee33346e) の問題意識を土台にしています。
指摘されている主な制約は次の通りです。

- Context Rot: 長い文脈ほど「真ん中」の情報が読まれにくい
- Attention Budget: 注意資源は有限であり、情報過多で精度が落ちる
- Satisficing: 探索を十分に行わず「それっぽい答え」で止まる

## Doc Advisor の目的と機能

Doc Advisor の目的は「必要な文書を、短時間で、確実に特定できるようにすること」です。
主な機能は次の通りです。

- **ドキュメント分類**: rules と specs を分離
- **doc_type 管理**: requirement / design / plan
- **ToC 自動生成**: `.md` を解析してメタデータを抽出し YAML 化
- **差分更新**: SHA-256 で変更検出
- **並列処理**: 最大 5 並列
- **中断耐性**: 完了分を保持し再開可能
- **シンボリックリンク対応**: シンボリックリンク経由で外部ドキュメントを統合 (v3.2+)

詳細は [TECHNICAL_GUIDE_ja.md](TECHNICAL_GUIDE_ja.md) を参照してください。

## 設計の意図（要点）

- **rules / specs の分離**: 開発ドキュメントと仕様書を明確に分け、参照コストを下げる
- **plan の除外**: plan は作業時に全文読み込みする前提のため、ToC から外す
- **パスによる doc_type 判定**: ファイル名の命名自由度を保ちつつ判定を安定化
- **ファイルパスの識別子化**: 余分なID強制を避け、参照を一貫させる
- **差分更新**: 変更分のみ処理して運用負荷を削減
- **中断前提**: `.toc_work/` に成果物を保持し、途中から再開できる

## 想定ケース

- 大量ドキュメント: 必要文書だけを検索で抽出
- 頻繁な更新: 変更分のみ再処理
- 途中中断: 未完了のみ再開
- 削除反映: チェックサム差分で delete-only
- 並列失敗: 直列フォールバックで継続

## クイックスタート

1. リポジトリをクローン

```bash
git clone https://github.com/BlueEventHorizon/DocAdvisor-CC.git
```

2. ターゲットプロジェクトにセットアップ

```bash
cd DocAdvisor-CC
./setup.sh /path/to/your-project
```

3. Claude Code を起動

```bash
cd /path/to/your-project
claude
```

4. ドキュメントディレクトリの設定

`setup.sh` が `.doc_structure.yaml` を検出した場合、ディレクトリは自動設定されます。
検出されなかった場合は、分類スキルを実行してください:

```bash
/setup-config
```

5. 初回 ToC 生成

```bash
/create-rules-toc --full
/create-specs-toc --full
```

> Makefile を使う場合:
>
> ```bash
> make setup
> make setup TARGET=/path/to/your-project
> ```

## 使い方

### ToC 生成コマンド

```bash
/create-rules-toc          # 差分更新
/create-rules-toc --full   # 全件再生成

/create-specs-toc          # 差分更新
/create-specs-toc --full   # 全件再生成
```

### ドキュメント検索スキル

```bash
/query-rules 認証機能の実装に必要な文書を特定
/query-specs 画面遷移の要件を特定
```

## 設定

設定ファイル: `.claude/doc-advisor/config.yaml`

- `rules` / `specs` のルートディレクトリや doc_type ディレクトリ名を変更可能
- 除外パターンはユーザー定義で追加可能
- システムファイル（`.toc_work/`, `*_toc.yaml`, `.toc_checksums.yaml`）は自動除外

## ドキュメント

- 日本語: [TECHNICAL_GUIDE_ja.md](TECHNICAL_GUIDE_ja.md)
- 英語: [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md)

## 必要要件

- Python 3（標準ライブラリのみ）
- Claude Code
- Bash シェル

## ライセンス

MIT License
