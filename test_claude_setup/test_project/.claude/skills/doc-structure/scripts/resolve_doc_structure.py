#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.doc_structure.yaml のパーサー・パス解決スクリプト。

config.yaml 互換フォーマットを読み込み、root_dirs の glob 展開、
doc_types_map の逆引き、exclude 適用、.md ファイル収集を行う。
doc-advisor の toc_utils.py 互換ロジックで実装。

使用例:
    python3 resolve_doc_structure.py --type rules
    python3 resolve_doc_structure.py --type specs
    python3 resolve_doc_structure.py --type all
    python3 resolve_doc_structure.py --features
    python3 resolve_doc_structure.py --doc-type design
    python3 resolve_doc_structure.py --version
"""

import argparse
import fnmatch
import glob as glob_module
import json
import os
import re
import sys
import unicodedata
from pathlib import Path


# ---------------------------------------------------------------------------
# バージョン検出
# ---------------------------------------------------------------------------

VERSION_MARKER = 'doc_structure_version:'


def get_version(content):
    """.doc_structure.yaml からバージョン文字列を取得する。

    コメント行 `# doc_structure_version: X.Y` を検索する。

    Args:
        content: ファイル内容（文字列）

    Returns:
        str | None: バージョン文字列（例: "2.0"）。見つからなければ None
    """
    for line in content.split('\n'):
        stripped = line.strip()
        if VERSION_MARKER in stripped:
            _, _, version_str = stripped.partition(VERSION_MARKER)
            version_str = version_str.strip()
            if version_str:
                return version_str
    return None


def get_major_version(content):
    """メジャーバージョン番号を整数で取得する。

    Args:
        content: ファイル内容（文字列）

    Returns:
        int | None: メジャーバージョン（例: 4）。取得失敗時は None
    """
    version = get_version(content)
    if version:
        try:
            return int(version.split('.')[0])
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# パス正規化
# ---------------------------------------------------------------------------

def normalize_path(path_str):
    """パス文字列を NFC 正規化する。

    macOS は NFD（分解形）でファイル名を保存するが、設定ファイルや
    ユーザー入力は NFC（合成形）が一般的。日本語の濁点・半濁点で
    不一致が発生するため、NFC に統一する。
    """
    return unicodedata.normalize('NFC', str(path_str))


# ---------------------------------------------------------------------------
# プロジェクトルートの検出
# ---------------------------------------------------------------------------

def find_project_root(start_path=None):
    """Return the project root directory.

    Claude Code's Bash tool always sets cwd to the project root,
    so upward traversal is unnecessary and risky (can hit ~/.claude/).

    Args:
        start_path: Explicit project root path (used by --project-root CLI arg)
                    If None, returns cwd (= project root in Claude Code context)

    Returns:
        str: Absolute path to the project root
    """
    if start_path:
        return str(Path(start_path).resolve())
    return str(Path.cwd().resolve())


# ---------------------------------------------------------------------------
# config.yaml 形式の YAML パーサー
# ---------------------------------------------------------------------------

def parse_config(content):
    """config.yaml 形式の YAML を行ベースでパースする。

    toc_utils.py の _parse_config_yaml() 互換ロジック。
    最大4レベルのネストに対応:
      - Level 0: トップレベルセクション（rules, specs, common）
      - Level 2: サブセクション（root_dirs, patterns, output）
      - Level 4: サブサブセクション（target_glob, exclude）
      - Level 6: 項目（キー値ペアまたはリスト要素）

    Args:
        content: YAML ファイル内容（文字列）

    Returns:
        dict: パース結果の辞書
    """
    result = {}
    current_section = None
    current_subsection = None
    current_subsubsection = None
    current_list = None
    current_dict = None

    lines = content.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()

        # コメント・空行をスキップ
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())

        if ':' in stripped and not stripped.startswith('- '):
            key, _, value = stripped.partition(':')
            key = key.strip().strip('"\'')
            value = value.strip()

            if indent == 0:
                # トップレベルセクション
                current_section = key
                result[key] = {}
                current_subsection = None
                current_subsubsection = None
                current_list = None
                current_dict = None
            elif indent == 2 and current_section:
                # サブセクション
                current_subsection = key
                if value:
                    result[current_section][key] = _parse_value(value)
                    current_list = None
                else:
                    if _lookahead_is_list(lines, i + 1, parent_indent=2):
                        result[current_section][key] = []
                        current_list = result[current_section][key]
                    else:
                        result[current_section][key] = {}
                        current_list = None
                current_subsubsection = None
                current_dict = None
            elif indent == 4 and current_section and current_subsection:
                # サブサブセクション
                current_subsubsection = key
                if value:
                    result[current_section][current_subsection][key] = _parse_value(value)
                    current_list = None
                    current_dict = None
                else:
                    is_list = _lookahead_is_list(lines, i + 1)
                    if is_list:
                        result[current_section][current_subsection][key] = []
                        current_list = result[current_section][current_subsection][key]
                        current_dict = None
                    else:
                        result[current_section][current_subsection][key] = {}
                        current_dict = result[current_section][current_subsection][key]
                        current_list = None
            elif indent == 6 and current_dict is not None:
                # サブサブセクション内のキー値ペア
                current_dict[key] = _parse_value(value) if value else ''
        elif stripped.startswith('- ') and current_list is not None:
            item = stripped[2:].strip().strip('"\'')
            # インラインコメント除去
            if '  #' in item and not item.startswith('"'):
                item = item[:item.index('  #')].strip()
            current_list.append(item)

    return result


def _lookahead_is_list(lines, start_idx, parent_indent=4):
    """次のコンテンツがリストか辞書かを先読みで判定する。

    Args:
        lines: 全行のリスト
        start_idx: 先読み開始インデックス
        parent_indent: 親キーのインデントレベル

    Returns:
        bool: リスト（'- ' で始まる）の場合 True
    """
    for i in range(start_idx, min(start_idx + 10, len(lines))):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= parent_indent:
            break

        if stripped.startswith('- '):
            return True
        if ':' in stripped:
            return False

    return True


def _parse_value(value):
    """YAML 値をパースする（文字列、数値、真偽値、インライン配列）。"""
    value = value.strip()

    # インラインコメント除去（クォート外）
    if not value.startswith('"') and '  #' in value:
        value = value[:value.index('  #')].strip()

    # インライン配列: [] or [a, b, c]
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"\'') for item in inner.split(',')]

    value = value.strip('"\'')

    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    try:
        return int(value)
    except ValueError:
        pass

    return value


# ---------------------------------------------------------------------------
# glob 展開
# ---------------------------------------------------------------------------

def expand_globs(dirs, project_root):
    """root_dirs 内の glob パターンを展開する。

    toc_utils.py の expand_root_dir_globs() 互換。

    Args:
        dirs: ディレクトリパスのリスト（glob パターン含む可能性あり）
        project_root: プロジェクトルートの絶対パス

    Returns:
        list[str]: 展開後のディレクトリパス（project_root からの相対パス、末尾 /）
    """
    expanded = []
    root = Path(project_root)

    for dir_path in dirs:
        if '*' in dir_path or '?' in dir_path:
            pattern = dir_path.rstrip('/')
            matches = sorted(root.glob(pattern))
            for match in matches:
                if match.is_dir():
                    rel = str(match.relative_to(root))
                    expanded.append(rel + '/')
        else:
            expanded.append(dir_path)

    return expanded if expanded else dirs


# ---------------------------------------------------------------------------
# exclude 判定
# ---------------------------------------------------------------------------

def is_excluded(filepath, root_dir, exclude_patterns):
    """ファイルが exclude パターンにマッチするか判定する。

    toc_utils.py の should_exclude() 互換。
    ディレクトリパスのみでマッチし、ファイル名は対象外。

    Args:
        filepath: チェック対象のパス（Path オブジェクト）
        root_dir: ルートディレクトリ（Path オブジェクト）
        exclude_patterns: 除外パターンのリスト

    Returns:
        bool: 除外すべき場合 True
    """
    if not exclude_patterns:
        return False

    rel_path = normalize_path(filepath.relative_to(root_dir))
    path_parts = rel_path.split('/')
    dir_parts = path_parts[:-1]  # ファイル名を除く
    dir_path = '/'.join(dir_parts)

    for pattern in exclude_patterns:
        normalized = normalize_path(pattern.strip('/'))
        if '/' in normalized:
            if normalized in dir_path:
                return True
        else:
            if normalized in dir_parts:
                return True
    return False


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------

def collect_md_files(directory, exclude_patterns, project_root):
    """.md ファイルをディレクトリ以下から再帰的に収集する。

    Args:
        directory: 検索対象ディレクトリの絶対パス
        exclude_patterns: 除外パターンのリスト
        project_root: プロジェクトルートの絶対パス

    Returns:
        list[str]: project_root からの相対パス
    """
    root = Path(project_root)
    dir_path = Path(directory)

    if not dir_path.is_dir():
        return []

    pattern = os.path.join(str(dir_path), '**', '*.md')
    md_files = glob_module.glob(pattern, recursive=True)

    result = []
    for f in sorted(md_files):
        fp = Path(f)
        if not fp.is_file():
            continue
        if is_excluded(fp, root, exclude_patterns):
            continue
        rel = str(fp.relative_to(root))
        result.append(rel)

    return result


# ---------------------------------------------------------------------------
# doc_types_map ユーティリティ
# ---------------------------------------------------------------------------

def invert_doc_types_map(doc_types_map):
    """doc_types_map（path→type）を逆引き（type→paths[]）に変換する。

    Args:
        doc_types_map: {path: doc_type} 辞書

    Returns:
        dict: {doc_type: [path1, path2, ...]} 辞書
    """
    inverted = {}
    for path, doc_type in doc_types_map.items():
        if doc_type not in inverted:
            inverted[doc_type] = []
        inverted[doc_type].append(path)
    return inverted


def match_path_to_doc_type(file_path, doc_types_map, project_root):
    """ファイルパスから doc_type を判定する。

    doc_types_map のキーが glob パターンの場合はパターンマッチングで判定する。

    Args:
        file_path: チェック対象のファイルパス（project_root からの相対パス）
        doc_types_map: {path_pattern: doc_type} 辞書
        project_root: プロジェクトルートの絶対パス

    Returns:
        str | None: マッチした doc_type、見つからなければ None
    """
    file_path = normalize_path(file_path)

    for pattern, doc_type in doc_types_map.items():
        pattern_normalized = normalize_path(pattern.rstrip('/'))

        if '*' in pattern_normalized or '?' in pattern_normalized:
            # glob パターン: 展開して照合
            root = Path(project_root)
            expanded = sorted(root.glob(pattern_normalized))
            for expanded_dir in expanded:
                if expanded_dir.is_dir():
                    rel = normalize_path(str(expanded_dir.relative_to(root)))
                    if file_path.startswith(rel + '/') or file_path.startswith(rel + os.sep):
                        return doc_type
        else:
            # リテラルパス
            if file_path.startswith(pattern_normalized.rstrip('/') + '/'):
                return doc_type
            if file_path.startswith(pattern_normalized.rstrip('/') + os.sep):
                return doc_type

    return None


# ---------------------------------------------------------------------------
# Feature 検出
# ---------------------------------------------------------------------------

def detect_features(config, project_root):
    """root_dirs の glob パターンから Feature 名を抽出する。

    `docs/specs/*/design/` の `*` や `docs/specs/**/design/` の `**` が
    キャプチャしたディレクトリ名を Feature とみなす。
    rules カテゴリは Feature 検出の対象外。

    Args:
        config: parse_config() の戻り値
        project_root: プロジェクトルートの絶対パス

    Returns:
        list[str]: Feature 名のソート済みリスト
    """
    features = set()
    root = Path(project_root)

    specs = config.get('specs', {})
    root_dirs = specs.get('root_dirs', [])
    exclude_patterns = specs.get('patterns', {}).get('exclude', [])

    for dir_pattern in root_dirs:
        if '*' not in dir_pattern:
            continue

        pattern = dir_pattern.rstrip('/')
        matches = sorted(root.glob(pattern))

        for match in matches:
            if not match.is_dir():
                continue
            if is_excluded(
                match / 'dummy.md',  # is_excluded はファイルパスを要求
                root,
                exclude_patterns,
            ):
                continue

            # glob パターン中の * 位置から Feature 名を抽出
            rel = str(match.relative_to(root))
            feature = _extract_feature_from_match(pattern, rel)
            if feature:
                features.add(feature)

    return sorted(features)


def _extract_feature_from_match(pattern, matched_path):
    """glob パターンとマッチ結果から Feature 名を抽出する。

    単一 * パターン:
        'docs/specs/*/design' + 'docs/specs/forge/design' → 'forge'

    ** パターン（再帰 glob）:
        'docs/specs/**/design' + 'docs/specs/forge/design' → 'forge'
        'docs/specs/**/design' + 'docs/specs/forge/review-PR/design' → 'forge'
    """
    pattern_parts = pattern.split('/')
    matched_parts = matched_path.split('/')

    if '**' not in pattern_parts:
        # 従来ロジック（後方互換）
        if len(pattern_parts) != len(matched_parts):
            return None
        for pp, mp in zip(pattern_parts, matched_parts):
            if pp == '*':
                return mp
        return None

    # 複数 ** は未対応
    if pattern_parts.count('**') > 1:
        return None

    # prefix / ** / suffix に分割
    ds_idx = pattern_parts.index('**')
    prefix = pattern_parts[:ds_idx]
    suffix = pattern_parts[ds_idx + 1:]

    # ** が少なくとも1セグメントをキャプチャしているか確認
    captured_count = len(matched_parts) - len(prefix) - len(suffix)
    if captured_count < 1:
        return None

    # prefix 内に * があればそちらを優先
    for i, pp in enumerate(prefix):
        if pp == '*':
            return matched_parts[i]

    # suffix 内に * があれば対応するセグメントを返す
    for j, sp in enumerate(suffix):
        if sp == '*':
            matched_idx = len(matched_parts) - len(suffix) + j
            return matched_parts[matched_idx]

    # ** がキャプチャした最初のセグメント = Feature
    return matched_parts[ds_idx]


# ---------------------------------------------------------------------------
# バリデーション
# ---------------------------------------------------------------------------

def validate_doc_structure(config, raw_content):
    """構造とバージョンの妥当性を検証する。

    検証優先順:
      1. 構造チェック: rules/specs に root_dirs が存在するか
      2. バージョンチェック: メジャーバージョンが 3 未満でないか

    Args:
        config: parse_config() の戻り値
        raw_content: ファイル内容（文字列）

    Returns:
        dict: {"valid": True} or
              {"valid": False, "error": "...", "suggestion": "..."}
    """
    suggestion = (
        "setup-doc-structure を実行して "
        ".doc_structure.yaml を再生成してください"
    )

    # 1. 構造チェック: rules または specs に root_dirs があるか
    has_root_dirs = False
    for section_name in ('rules', 'specs'):
        section = config.get(section_name, {})
        if isinstance(section, dict):
            root_dirs = section.get('root_dirs')
            if isinstance(root_dirs, list):
                has_root_dirs = True
                break

    if not has_root_dirs:
        major = get_major_version(raw_content)
        if major is not None and major < 3:
            error = (
                f".doc_structure.yaml は旧フォーマット（v{major}）です。"
                f" root_dirs が存在しないためパス解決ができません"
            )
        else:
            error = (
                ".doc_structure.yaml に root_dirs が定義されていません。"
                " パス解決ができません"
            )
        return {"valid": False, "error": error, "suggestion": suggestion}

    # 2. バージョンチェック（root_dirs があっても警告レベルで確認）
    major = get_major_version(raw_content)
    if major is not None and major < 3:
        # v2 は root_dirs を持つ場合があり動作するため valid
        # ただし情報として返す
        return {
            "valid": True,
            "version_warning": (
                f"v{major} フォーマットです。"
                f" 最新の v3 へのマイグレーションを推奨します"
            ),
            "suggestion": suggestion,
        }

    return {"valid": True}


# ---------------------------------------------------------------------------
# メイン解決ロジック
# ---------------------------------------------------------------------------

def load_doc_structure(project_root, doc_structure_path=None):
    """.doc_structure.yaml を読み込んでパースする。

    Args:
        project_root: プロジェクトルートの絶対パス
        doc_structure_path: .doc_structure.yaml のパス（省略時は自動決定）

    Returns:
        tuple: (config_dict, raw_content)

    Raises:
        FileNotFoundError: ファイルが見つからない場合
    """
    if doc_structure_path is None:
        doc_structure_path = os.path.join(project_root, '.doc_structure.yaml')

    if not os.path.isfile(doc_structure_path):
        raise FileNotFoundError(
            f".doc_structure.yaml が見つかりません: {doc_structure_path}"
        )

    with open(doc_structure_path, 'r', encoding='utf-8') as f:
        content = f.read()

    config = parse_config(content)
    return config, content


def resolve_files(config, category, project_root):
    """カテゴリ（rules/specs）の .md ファイルを解決する。

    Args:
        config: parse_config() の戻り値
        category: 'rules' または 'specs'
        project_root: プロジェクトルートの絶対パス

    Returns:
        list[str]: project_root からの相対パス（.md ファイルのみ）
    """
    section = config.get(category, {})
    root_dirs = section.get('root_dirs', [])
    exclude_patterns = section.get('patterns', {}).get('exclude', [])

    # glob 展開
    expanded_dirs = expand_globs(root_dirs, project_root)

    # ファイル収集
    resolved = []
    seen = set()

    for dir_path in expanded_dirs:
        full_path = os.path.join(project_root, dir_path.rstrip('/'))
        md_files = collect_md_files(full_path, exclude_patterns, project_root)
        for f in md_files:
            if f not in seen:
                seen.add(f)
                resolved.append(f)

    return resolved


def resolve_files_by_doc_type(config, category, doc_type, project_root):
    """特定 doc_type の .md ファイルのみを解決する。

    Args:
        config: parse_config() の戻り値
        category: 'rules' または 'specs'
        doc_type: ドキュメント種別（例: 'design', 'plan', 'requirement'）
        project_root: プロジェクトルートの絶対パス

    Returns:
        list[str]: project_root からの相対パス（.md ファイルのみ）
    """
    section = config.get(category, {})
    doc_types_map = section.get('doc_types_map', {})
    exclude_patterns = section.get('patterns', {}).get('exclude', [])

    # doc_type に対応するパスを逆引き
    inverted = invert_doc_types_map(doc_types_map)
    paths = inverted.get(doc_type, [])

    if not paths:
        return []

    # glob 展開
    expanded_dirs = expand_globs(paths, project_root)

    # ファイル収集
    resolved = []
    seen = set()

    for dir_path in expanded_dirs:
        full_path = os.path.join(project_root, dir_path.rstrip('/'))
        md_files = collect_md_files(full_path, exclude_patterns, project_root)
        for f in md_files:
            if f not in seen:
                seen.add(f)
                resolved.append(f)

    return resolved


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------

def parse_args():
    """コマンドライン引数をパースする。"""
    parser = argparse.ArgumentParser(
        description='.doc_structure.yaml からドキュメント情報を解決して JSON で出力する'
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--type',
        choices=['rules', 'specs', 'all'],
        help='解決対象カテゴリ: rules / specs / all',
    )
    group.add_argument(
        '--features',
        action='store_true',
        help='Feature 名一覧を出力する',
    )
    group.add_argument(
        '--doc-type',
        help='特定 doc_type のファイルを解決する（例: design, plan, requirement）',
    )
    group.add_argument(
        '--version',
        action='store_true',
        help='.doc_structure.yaml のバージョンを出力する',
    )
    parser.add_argument(
        '--project-root',
        default=None,
        help='プロジェクトルートのパス（省略時: .git/.claude を遡って自動検出）',
    )
    parser.add_argument(
        '--doc-structure',
        default=None,
        help='.doc_structure.yaml のパス（省略時: project_root/.doc_structure.yaml）',
    )
    parser.add_argument(
        '--category',
        choices=['rules', 'specs'],
        default='specs',
        help='--doc-type 使用時のカテゴリ（デフォルト: specs）',
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # プロジェクトルートの決定
    project_root = args.project_root
    if project_root:
        project_root = os.path.abspath(project_root)
    else:
        try:
            project_root = find_project_root()
        except RuntimeError as e:
            print(json.dumps({'status': 'error', 'message': str(e)},
                             ensure_ascii=False), file=sys.stderr)
            sys.exit(1)

    # .doc_structure.yaml パスの決定
    doc_structure_path = args.doc_structure
    if doc_structure_path:
        doc_structure_path = os.path.abspath(doc_structure_path)

    # 読み込み
    try:
        config, raw_content = load_doc_structure(project_root, doc_structure_path)
    except FileNotFoundError as e:
        print(json.dumps({'status': 'error', 'message': str(e)},
                         ensure_ascii=False))
        sys.exit(1)

    # コマンド実行
    if args.version:
        # --version は情報取得のみのためバリデーション不要
        version = get_version(raw_content)
        result = {
            'status': 'ok',
            'version': version,
            'major_version': get_major_version(raw_content),
        }
    else:
        # --type / --features / --doc-type はバリデーション必須
        validation = validate_doc_structure(config, raw_content)
        if not validation.get('valid'):
            error_result = {
                'status': 'error',
                'message': validation['error'],
                'suggestion': validation.get('suggestion', ''),
            }
            print(json.dumps(error_result, indent=2, ensure_ascii=False))
            sys.exit(1)

        if args.features:
            features = detect_features(config, project_root)
            result = {
                'status': 'ok',
                'features': features,
            }
        elif args.doc_type:
            files = resolve_files_by_doc_type(
                config, args.category, args.doc_type, project_root
            )
            result = {
                'status': 'ok',
                'category': args.category,
                'doc_type': args.doc_type,
                'files': files,
            }
        else:
            # --type
            result = {
                'status': 'ok',
                'project_root': project_root,
            }
            if args.type in ('rules', 'all'):
                result['rules'] = resolve_files(config, 'rules', project_root)
            if args.type in ('specs', 'all'):
                result['specs'] = resolve_files(config, 'specs', project_root)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
