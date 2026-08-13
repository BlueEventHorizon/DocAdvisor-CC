#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fm_from_toc.py — ToC のメタデータを原本フロントマターへ書き戻す変換
（doc-advisor plugin / frontmatter）

DES-008 §6.1（依存の向き）/ §6.2（責務）/ §8.2（AI 抽出結果の書き戻し）を実装する。

## なぜ必要か

`toc.yaml` の各エントリは `title` / `purpose` / `content_details` / `applicable_tasks` /
`keywords` の 5 フィールドを持つ。これはフロントマターの 5 フィールドと**同一**であり、
`body_hash` 以外は既に揃っている。したがって書き戻しは「ToC の値を写して `body_hash` を
打刻する」決定論的な転記で足りる。

にもかかわらず、当初の書き戻しは AI が対象文書を読み直して 5 フィールドを**再起草**する
形だった。これは 2 つの害があった。

1. 同じ本文に対する AI の読解を 2 回払う（索引時 + 書き戻し時）。フロントマター方式は
   「1 度読めば以後は転記だけ」を目的にしているのに、その 1 度目の結果を捨てていた
2. 再起草は 1 回目と一致する保証がないため、`toc.yaml` と原本フロントマターが食い違う。
   書き戻しでファイル hash が変わるので次回の索引はその文書を updated と見て転記し、
   **本文が 1 文字も変わっていないのに ToC の内容が入れ替わる**

本モジュールは転記を script 側へ移し、AI に残る責務を承認だけにする。

## 依存の向き（DES-008 §6.1）

フロントマターは ToC のスキーマを原本側に前置きした派生機能であり、依存は
**派生 → 中心**へ向かう。本モジュールは `frontmatter/`（派生）に置いたまま
`toc_store` / `toc_utils`（中心）を import する。逆向き、すなわち `scripts/` 直下へ
フロントマター専用の実装を置くことはしない。それをすると「`frontmatter/` の削除で
フロントマター方式を撤回できる」性質が壊れる。

なお `fm_core` / `fm_read` / `fm_write` は ToC を知らないままにする（任意のパスに対して
使える汎用モジュールとして保つ）。ToC を知るのは本モジュールだけである。

## 陳腐化ガード

ToC のメタデータは**索引時点の本文**から作られている。索引後に本文が編集されていれば、
その値は現在の本文を説明していない。それを写して `body_hash` を打刻すると、
「信頼できるフロントマター」として以後の索引が転記だけで済ませてしまい、古い記述が
固定される。したがって checksums（索引時のファイル hash）と現在のファイル hash を
比較し、不一致・照合不能なら転記せず AI 抽出へ回す。

標準ライブラリのみ使用（REQ-001 NFR-N01）。
"""

import os
import sys
from pathlib import Path

from fm_core import LIST_FIELDS, STRING_FIELDS, Violation, validate_field_values

# fm_core が sys.path へ scripts/ を通すが、本モジュールが単体で import される
# 経路（テスト）でも成立させるため明示する。
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from toc_store import (  # noqa: E402
    CHECKSUMS_FILENAME,
    TOC_FILENAME,
    resolve_store_dir,
)
from toc_utils import (  # noqa: E402
    calculate_file_hash,
    get_project_root,
    load_checksums,
    load_existing_toc,
    normalize_path,
)

# ToC から写す 5 フィールド。ここに無いキー（将来 toc.yaml へ増えたもの）は写さない。
# fm_write は doc-advisor が所有しないキーを拒否するため、素通しにはできない。
COPIED_FIELDS = STRING_FIELDS + LIST_FIELDS

# 転記できない理由（AI 抽出へ回す対象の分類）。呼び出し側が値で分岐する契約である。
REASON_NOT_IN_TOC = "not_in_toc"
REASON_INCOMPLETE_ENTRY = "incomplete_entry"
REASON_BODY_CHANGED = "body_changed"
REASON_UNVERIFIABLE = "unverifiable"

NEEDS_AI_REASONS = frozenset({
    REASON_NOT_IN_TOC,
    REASON_INCOMPLETE_ENTRY,
    REASON_BODY_CHANGED,
    REASON_UNVERIFIABLE,
})


class FromTocError(Exception):
    """ToC を読めないため転記を始められない状態。"""


class TocSource:
    """1 つの key の ToC と checksums を保持する読み取り専用のビュー。

    パス解決（key → store_dir）を 1 度だけ行い、以降の判定は本オブジェクトに対して
    行う。呼び出しごとに store_dir を解決し直すと、対象件数に比例して同じ解決を
    繰り返すうえ、途中で解決結果が変わりうる。
    """

    def __init__(self, key, docs, checksums, toc_path, project_root):
        self.key = key
        self.docs = docs
        self.checksums = checksums
        self.toc_path = toc_path
        self.project_root = Path(project_root)

    @property
    def paths(self):
        """ToC に載っている文書パスを昇順で返す（project-root-relative）。

        `--paths` / `--dirs` が渡されなかった場合の既定の対象集合である。対象の列挙は
        決定論的な定型処理であり、AI に ToC を手読みさせない（CLAUDE.md）。
        """
        return sorted(self.docs)


def load_toc(key, project_root=None):
    """key の ToC と checksums を読む。

    project root の解決を本モジュールが引き受けるのは、呼び出し側（`fm_run`）を
    ToC の置き場所から切り離すためである。`fm_run` は key を右から左へ渡すだけで、
    store_dir も project root も知らない。

    Args:
        key: ToC の key。予約 key の単体モードは 'all' を渡す。**読み取りのみを
            行う本モジュールでは 'all' を拒否しない**（`validate_user_key` が任意の
            `all` を拒むのは、ユーザー任意 key で予約 key の ToC を**作らせない**
            ためであり、既にある ToC を読む経路には当てはまらない）
        project_root: project root（省略時は get_project_root()）

    Returns:
        TocSource

    Raises:
        FromTocError: toc.yaml が存在しない場合
    """
    if project_root is None:
        project_root = get_project_root()
    store_dir = resolve_store_dir(key, project_root)
    toc_path = store_dir / TOC_FILENAME

    if not toc_path.exists():
        raise FromTocError(f"toc.yaml が見つかりません: {toc_path}")

    docs = load_existing_toc(toc_path)
    checksums = load_checksums(store_dir / CHECKSUMS_FILENAME)
    return TocSource(key, docs, checksums, toc_path, project_root)


def extract_metadata(entry):
    """ToC のエントリから書き込む 5 フィールドを取り出す。

    doc-advisor が所有する 5 フィールドだけを写す。`body_hash` は `fm_write` が
    整形後に算出・打刻するため写さない（写せない）。`type` は `fm_write` が和集合で
    更新する。

    Args:
        entry: `load_existing_toc` が返したエントリの dict

    Returns:
        dict: COPIED_FIELDS のうちエントリに存在したものだけを含む dict
    """
    return {field: entry[field] for field in COPIED_FIELDS if field in entry}


def entry_violations(metadata):
    """転記前にエントリの充足と値域を検証する。

    `fm_write` は部分指定を許すため欠落を検査しない（DES-008 §6.2）。しかし転記は
    「ToC の内容で 5 フィールドを揃える」操作であり、欠けたまま書くと書き込み後の
    信頼判定が必ず落ちる。したがって欠落は本モジュールで検出し、当該文書を AI 抽出へ
    回す。値域の判定は `fm_core` の実装をそのまま使う（規則を 2 箇所に持たない）。

    Args:
        metadata: `extract_metadata` の戻り値

    Returns:
        list: (violation_code, field, detail) のタプルの列。空なら転記可
    """
    violations = []
    for field in COPIED_FIELDS:
        if field not in metadata:
            violations.append((
                Violation.FIELD_MISSING,
                field,
                f"ToC のエントリに {field} がありません",
            ))
    violations.extend(validate_field_values(metadata))
    return violations


def body_matches_index(source, path):
    """索引時点の本文と現在の本文が一致するかを判定する。

    Args:
        source: TocSource
        path: 正規化済みの project-root-relative パス

    Returns:
        tuple: (matches, reason)。matches が偽のとき reason は
            REASON_BODY_CHANGED（hash 不一致）または REASON_UNVERIFIABLE
            （checksums に記録が無い / 現在の hash を算出できない）
    """
    indexed = source.checksums.get(path)
    if indexed is None:
        # 通常の索引は checksums を全エントリ分書く。記録が無いのは異常であり、
        # 照合できないまま転記すると陳腐化を検出できない。
        return False, REASON_UNVERIFIABLE

    current = calculate_file_hash(source.project_root / path)
    if current is None:
        return False, REASON_UNVERIFIABLE
    if current != indexed:
        return False, REASON_BODY_CHANGED
    return True, None


def resolve_entry(source, path):
    """1 件のパスについて、転記できるか / AI 抽出へ回すかを判定する。

    判定順は「ToC にあるか → 索引時点の本文と一致するか → エントリが揃っているか」
    とする。陳腐化を先に見るのは、古いエントリの値域を検証しても意味がないためである。

    Args:
        source: TocSource
        path: 対象パス（正規化前でよい）

    Returns:
        tuple: (metadata, reason, violations)
            転記可なら (dict, None, [])、不可なら (None, REASON_*, violations)
    """
    normalized = normalize_path(path)
    entry = source.docs.get(normalized)
    if entry is None:
        return None, REASON_NOT_IN_TOC, []

    matches, reason = body_matches_index(source, normalized)
    if not matches:
        return None, reason, []

    metadata = extract_metadata(entry)
    violations = entry_violations(metadata)
    if violations:
        return None, REASON_INCOMPLETE_ENTRY, violations

    return metadata, None, []
