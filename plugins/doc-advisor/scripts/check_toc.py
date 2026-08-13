#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_toc.py — ToC 鮮度確認（doc-advisor plugin / read-only）

REQ-005 / DES-009 を実装する。指定 key の ToC が「そのまま検索に使えるか（fresh）/
作り直しが必要か（stale）」だけを返す read-only な判定 script。

責務（決定的処理。索引の生成・更新・削除は一切しない / REQ-005 対象外）:
- key 解決（予約 key all / 任意 all reject。toc_store.resolve_key_from_args を使う）
- store_dir/toc.yaml の metadata のみ読み取り（docs: 到達で打ち切り / NFR-C02）
- metadata.generated_at と --max-age の比較による鮮度判定（FR-C02）
- JSON 出力（toc_store.emit_json）。答えは freshness、原因は補助情報 reason

ToC 不在は status=ok / freshness=stale / reason=missing とする（FR-C03-3）。
呼び出し側の後続処理が鮮度超過と同一のため、独立の値にしない。

CLI:
    python3 check_toc.py --key <key> --max-age <秒>
    python3 check_toc.py --all --max-age <秒>

標準ライブラリのみ使用（NFR-C01）。
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from toc_utils import get_project_root
from toc_store import (
    ErrorCode,
    KeyError_,
    STATUS_OK,
    STATUS_ERROR,
    TOC_FILENAME,
    resolve_store_dir,
    resolve_key_from_args,
    emit_json,
    toc_path_rel,
)

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# metadata 読み取りを打ち切る行（DES-009 §2.3）。toc.yaml は metadata が docs より前に置かれる
# （formats/toc_format.md）。この行に到達したらエントリ本体は読まない。
DOCS_SECTION_PREFIX = "docs:"

# freshness の値域（REQ-005 FR-C03-2 / 呼び出し側が読む唯一の答え）
FRESHNESS_FRESH = "fresh"
FRESHNESS_STALE = "stale"

# reason の値域（診断用の補助情報。呼び出し側の分岐に使われることを前提としない）
REASON_MISSING = "missing"
REASON_OUTDATED = "outdated"
REASON_GENERATED_AT_INVALID = "generated_at_invalid"
REASON_GENERATED_AT_FUTURE = "generated_at_future"

# 未来時刻の許容 skew（DES-009 §4.2 / REQ-005 TBD-C01 の確定値）。
# 時計同期の通常のずれを吸収する。これを超える未来時刻は壊れた値として stale にし、
# 再索引で正しい generated_at に置き換わる経路へ乗せる。
FUTURE_SKEW = timedelta(seconds=60)


# ---------------------------------------------------------------------------
# metadata 読み取り（DES-009 §2.3 / NFR-C02）
# ---------------------------------------------------------------------------

def read_toc_metadata(toc_path):
    """toc.yaml の metadata ブロックのスカラを dict で返す。

    docs: に到達した時点で読み取りを打ち切るため、エントリ本体は解析しない。
    metadata ブロックが無い場合は空 dict を返す。

    Raises:
        OSError / UnicodeDecodeError: 読み取り自体が失敗した場合（呼び出し側が
            TOC_READ_ERROR として扱う）
    """
    metadata = {}
    in_metadata = False

    with open(toc_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()

            # docs セクションに到達したら以降は読まない（打ち切り）
            if stripped.startswith(DOCS_SECTION_PREFIX):
                break

            if stripped.startswith("metadata:"):
                in_metadata = True
                continue

            if not in_metadata:
                continue

            # metadata 配下は 2 スペースインデントのスカラ（name / key / generated_at / file_count）
            if not stripped or stripped.startswith("#"):
                continue
            if not line.startswith("  "):
                # インデントが戻ったら metadata ブロックの終わり
                in_metadata = False
                continue
            if ":" not in stripped:
                continue

            name, _, value = stripped.partition(":")
            metadata[name.strip()] = value.strip()

    return metadata


# ---------------------------------------------------------------------------
# generated_at の解析（DES-009 §4.3）
# ---------------------------------------------------------------------------

def parse_generated_at(value):
    """ISO 8601 文字列を timezone-aware datetime へ変換する。解析不能なら None。

    merge_toc.py / remove_toc.py が書く形式は '%Y-%m-%dT%H:%M:%SZ'（UTC）。
    末尾 Z を +00:00 に置換したうえで fromisoformat を使い、他の ISO 8601 表記も受け付ける。
    timezone を持たない値は UTC として解釈する。
    """
    if not value:
        return None

    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


# ---------------------------------------------------------------------------
# 鮮度判定（DES-009 §4.2 / REQ-005 FR-C02）
# ---------------------------------------------------------------------------

def judge(generated_at, now, max_age_seconds):
    """(freshness, reason, age_seconds) を返す純関数。

    Args:
        generated_at: parse_generated_at の結果（None = 解析不能）
        now: 判定時刻（timezone-aware datetime）
        max_age_seconds: 鮮度閾値（正の整数・秒）

    Returns:
        (freshness, reason, age_seconds)。age_seconds は算出できない場合 None。
        skew 内の未来時刻は 0 に丸める（負の age を呼び出し側に解釈させない）。
    """
    if generated_at is None:
        return FRESHNESS_STALE, REASON_GENERATED_AT_INVALID, None

    delta = now - generated_at
    age_seconds = int(delta.total_seconds())

    if delta < -FUTURE_SKEW:
        return FRESHNESS_STALE, REASON_GENERATED_AT_FUTURE, age_seconds

    if age_seconds < 0:
        # skew 内の未来時刻。時計のずれとして吸収する
        age_seconds = 0

    if age_seconds <= max_age_seconds:
        return FRESHNESS_FRESH, None, age_seconds

    return FRESHNESS_STALE, REASON_OUTDATED, age_seconds


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class ArgError(Exception):
    """引数の解析エラー（未知引数・値不足・排他違反）。

    argparse の既定動作（stderr へ usage を出し exit code 2 で終了）は、
    「常に単一 JSON を stdout へ出し exit code は status に対応させる」契約
    （FR-C03 / DES-009 §5.3）を破るため、例外へ変換して main で JSON 化する。
    """


class _JsonArgumentParser(argparse.ArgumentParser):
    """SystemExit せず ArgError を送出する ArgumentParser。

    status によらず常に ArgError にする。`add_help=False` としているため
    「JSON 以外を stdout へ出して正常終了する」経路（help / version）は存在せず、
    ここへ到達するのは常に引数の解析失敗である。
    """

    def error(self, message):  # noqa: D102 - argparse の契約を上書きする
        raise ArgError(message)

    def exit(self, status=0, message=None):  # noqa: D102
        raise ArgError(message or "引数の解析に失敗しました")


def parse_args(argv=None):
    """引数を解析する。解析できない場合は ArgError を送出する。

    Raises:
        ArgError: 未知引数・値不足・`--key` と `--all` の同時指定（FR-C01-4）
    """
    # add_help=False: 自動追加される --help は help テキストを stdout へ出して exit 0 するため、
    # 「最終出力は script の JSON のみ」（FR-C03-4）を破る。無効化して未知引数と同じ経路に乗せる。
    # 利用方法は SKILL.md と DES-009 に記述する。
    parser = _JsonArgumentParser(
        description="指定 key の ToC が fresh か stale かを返す（read-only）",
        add_help=False,
    )
    # --key と --all は排他（--all は「--key 省略」と同義であり、両立させると
    # resolve_key_from_args が --all を優先して別 key の鮮度を黙って返す）。
    # 既存 toc_store.py の CLI と同じ mutually exclusive group を使う。
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--key", help="対象 ToC の opaque key（'all' は予約語のため指定不可）")
    group.add_argument(
        "--all",
        action="store_true",
        dest="all",
        help="単体モード。予約 key 'all' に解決する",
    )
    parser.add_argument(
        "--max-age",
        dest="max_age",
        help="鮮度閾値（正の整数・秒）。必須",
    )
    return parser.parse_args(argv)


def resolve_max_age(raw):
    """--max-age を正の整数へ変換する。不正なら None（呼び出し側が error にする）。"""
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def main(argv=None, now=None):
    # 0. 引数解析（未知引数・値不足・排他違反は JSON へ正規化する / FR-C01-4）
    try:
        args = parse_args(argv)
    except ArgError as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.UNSUPPORTED_ARG,
            message=str(e),
        )
        return 1

    project_root = get_project_root()

    # 1. --max-age の検証（FR-C01-3。閾値の所有者は呼び出し側であり既定値を持たない）
    max_age_seconds = resolve_max_age(args.max_age)
    if max_age_seconds is None:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.INVALID_MAX_AGE,
            message="--max-age は正の整数（秒）で指定してください",
        )
        return 1

    # 2. key 解決（--all / --key 省略 → 予約 all、--key all → KEY_RESERVED）
    try:
        key = resolve_key_from_args(args)
    except KeyError_ as e:
        emit_json(STATUS_ERROR, error_code=e.error_code, message=str(e))
        return 1

    store_dir = resolve_store_dir(key, project_root)
    toc_path = store_dir / TOC_FILENAME
    toc_rel = toc_path_rel(store_dir, project_root)

    # 3. ToC 不在は error ではなく stale（FR-C03-3）
    if not toc_path.exists():
        emit_json(
            STATUS_OK,
            error_code=None,
            key=key,
            toc_path=toc_rel,
            extra={
                "freshness": FRESHNESS_STALE,
                "reason": REASON_MISSING,
                "generated_at": None,
                "age_seconds": None,
                "max_age_seconds": max_age_seconds,
            },
        )
        return 0

    # 4. metadata のみ読む（NFR-C02）。読み取り自体の失敗は error
    try:
        metadata = read_toc_metadata(toc_path)
    except (OSError, UnicodeDecodeError) as e:
        emit_json(
            STATUS_ERROR,
            error_code=ErrorCode.TOC_READ_ERROR,
            message=f"ToC を読み取れません: {toc_rel} ({e.__class__.__name__})",
            key=key,
            toc_path=toc_rel,
        )
        return 1

    # 5. 鮮度判定
    raw_generated_at = metadata.get("generated_at")
    generated_at = parse_generated_at(raw_generated_at)
    if now is None:
        now = datetime.now(timezone.utc)

    freshness, reason, age_seconds = judge(generated_at, now, max_age_seconds)

    emit_json(
        STATUS_OK,
        error_code=None,
        key=key,
        toc_path=toc_rel,
        extra={
            "freshness": freshness,
            "reason": reason,
            "generated_at": raw_generated_at if generated_at is not None else None,
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
