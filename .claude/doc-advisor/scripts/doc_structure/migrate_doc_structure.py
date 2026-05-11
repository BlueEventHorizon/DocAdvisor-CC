#!/usr/bin/env python3
""".doc_structure.yaml の段階的バージョンマイグレーション。

COMMON-REQ-001 準拠。テキスト操作による変換（NFR-02: 外部ライブラリ不使用）。

Usage:
    python3 migrate_doc_structure.py <file_path>            # マイグレーション実行（stdout 出力）
    python3 migrate_doc_structure.py <file_path> --check    # バージョン情報のみ
    python3 migrate_doc_structure.py <file_path> --dry-run  # 適用内容を表示
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# バージョン検出（resolve_doc_structure.py から再利用）
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent.parent  # doc_structure → scripts → forge
_rds_path = PLUGIN_ROOT / 'skills' / 'doc-structure' / 'scripts'
sys.path.insert(0, str(_rds_path))
from resolve_doc_structure import get_major_version  # noqa: E402

# ---------------------------------------------------------------------------
# 定数（FR-02-5）
# ---------------------------------------------------------------------------

CURRENT_VERSION = 3


# ---------------------------------------------------------------------------
# マイグレーション関数（FR-03-1: fn(str) -> str）
# ---------------------------------------------------------------------------

def migrate_v1_to_v2(content):
    """v1 → v2: doc_type-centric 形式から config.yaml 互換形式へ変換。

    v1 形式:
        version: "1.0"
        specs:
          design:
            paths: [docs/specs/design/]
            description: "..."
        rules:
          rule:
            paths: [docs/rules/]
            description: "..."

    v2 形式:
        # doc_structure_version: 2.0
        rules:
          root_dirs:
            - docs/rules/
          doc_types_map:
            docs/rules/: rule
          ...（doc-advisor フィールド含む）
    """
    # v1 の構造をテキストから解析
    categories = {}  # {category: {doc_type: [paths]}}
    current_category = None
    current_doc_type = None

    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('version:'):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ':' in stripped and not stripped.startswith('-'):
            key = stripped.split(':')[0].strip()
            if key in ('specs', 'rules'):
                current_category = key
                categories[key] = {}
                current_doc_type = None

        elif indent == 2 and current_category and ':' in stripped:
            key = stripped.split(':')[0].strip()
            if key not in ('paths', 'description'):
                current_doc_type = key
                categories[current_category][current_doc_type] = []

        elif indent == 4 and current_category and current_doc_type:
            key_part = stripped.split(':')[0].strip()
            if key_part == 'paths':
                # paths: [docs/specs/design/] 形式のパース
                _, _, value = stripped.partition(':')
                value = value.strip().strip('[]')
                paths = [p.strip().strip('"\'') for p in value.split(',') if p.strip()]
                categories[current_category][current_doc_type] = paths

    # v2 形式を生成
    lines = ['# doc_structure_version: 2.0', '']

    for category in ('rules', 'specs'):
        if category not in categories:
            continue

        doc_types = categories[category]
        all_paths = []
        dt_map = {}

        for doc_type, paths in doc_types.items():
            for p in paths:
                p = p.rstrip('/') + '/'
                all_paths.append(p)
                dt_map[p] = doc_type

        lines.append(f'{category}:')
        lines.append('  root_dirs:')
        for p in all_paths:
            lines.append(f'    - {p}')
        lines.append('  doc_types_map:')
        for p, dt in dt_map.items():
            lines.append(f'    {p}: {dt}')

        # v2 のデフォルトフィールド
        toc_target = category
        lines.append(f'  toc_file: .claude/doc-advisor/toc/{toc_target}/{toc_target}_toc.yaml')
        lines.append(f'  checksums_file: .claude/doc-advisor/toc/{toc_target}/.toc_checksums.yaml')
        lines.append(f'  work_dir: .claude/doc-advisor/toc/{toc_target}/.toc_work/')
        lines.append('  patterns:')
        lines.append('    target_glob: "**/*.md"')
        lines.append('    exclude: []')

        if category == 'rules':
            lines.append('  output:')
            lines.append('    header_comment: "Development documentation search index for query-rules skill"')
            lines.append('    metadata_name: "Development Documentation Search Index"')
        else:
            lines.append('  output:')
            lines.append('    header_comment: "Project specification document search index for query-specs skill"')
            lines.append('    metadata_name: "Project Specification Document Search Index"')

        lines.append('')

    # common セクション
    lines.append('common:')
    lines.append('  parallel:')
    lines.append('    max_workers: 5')
    lines.append('    fallback_to_serial: true')
    lines.append('')

    return '\n'.join(lines)


def migrate_v2_to_v3(content):
    """v2 → v3: Doc Advisor 内部フィールドを除去。

    除去対象: toc_file, checksums_file, work_dir, output セクション, common セクション
    保持対象: root_dirs, doc_types_map, patterns
    """
    result_lines = []
    skip_until_dedent = False
    skip_section = None
    skip_indent = None

    for line in content.split('\n'):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip()) if stripped else 0

        # バージョンマーカー更新
        if '# doc_structure_version: 2.0' in line:
            result_lines.append(line.replace('doc_structure_version: 2.0', 'doc_structure_version: 3.0'))
            continue

        # common セクション全体をスキップ
        if indent == 0 and stripped.startswith('common:'):
            skip_section = 'common'
            skip_indent = 0
            skip_until_dedent = True
            continue

        if skip_until_dedent:
            if stripped and indent <= skip_indent:
                skip_until_dedent = False
                skip_section = None
            else:
                continue

        # 単一行フィールドの除去（indent == 2: カテゴリ直下のフィールドのみ対象）
        if indent == 2 and (stripped.startswith('toc_file:') or stripped.startswith('checksums_file:') or stripped.startswith('work_dir:')):
            continue

        # output セクションの除去（indent=2 の output: から次の indent<=2 まで）
        if indent == 2 and stripped.startswith('output:'):
            skip_section = 'output'
            skip_indent = 2
            skip_until_dedent = True
            continue

        result_lines.append(line)

    # 末尾の余分な空行を整理
    text = '\n'.join(result_lines)
    # 連続する3行以上の空行を2行に
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 末尾の空行を1つに
    text = text.rstrip('\n') + '\n'

    return text


# ---------------------------------------------------------------------------
# マイグレーションレジストリ（FR-02-2）
# ---------------------------------------------------------------------------

MIGRATIONS = {
    2: migrate_v1_to_v2,
    3: migrate_v2_to_v3,
}

MIGRATION_DESCRIPTIONS = {
    2: "Convert v1 doc_type-centric format to v2 config.yaml compatible format",
    3: "Remove doc-advisor internal fields (toc_file, checksums_file, work_dir, output, common)",
}


# ---------------------------------------------------------------------------
# コアロジック（COMMON-REQ-001 設計パターン準拠）
# ---------------------------------------------------------------------------

def detect_version(content):
    """バージョン検出。検出失敗時は 1 を返す（FR-04-3, FR-01-2）。"""
    major = get_major_version(content)
    if major is not None:
        return major

    # v1 形式チェック: version: "1.0" フィールドの存在
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('version:'):
            return 1

    # 検出失敗 → v1 として扱う（FR-04-3: v1 形式にはバージョンフィールドがない）
    return 1


def apply_migrations(content, detected_version):
    """段階的マイグレーションを適用する（FR-02-1, FR-02-3, FR-02-4）。"""
    if detected_version >= CURRENT_VERSION:
        return content  # FR-04-2

    targets = [v for v in sorted(MIGRATIONS.keys())
               if detected_version < v <= CURRENT_VERSION]

    for v in targets:
        content = MIGRATIONS[v](content)

    return content


def get_migration_plan(detected_version):
    """適用されるマイグレーションの一覧を返す。"""
    if detected_version >= CURRENT_VERSION:
        return []

    targets = [v for v in sorted(MIGRATIONS.keys())
               if detected_version < v <= CURRENT_VERSION]

    return [
        {
            "from": v - 1,
            "to": v,
            "description": MIGRATION_DESCRIPTIONS.get(v, ""),
        }
        for v in targets
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: migrate_doc_structure.py <file_path> [--check|--dry-run]", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else None

    valid_modes = {'--check', '--dry-run', None}
    if mode not in valid_modes:
        print(f"Error: 不正な引数です: {mode}（有効な値: --check, --dry-run）", file=sys.stderr)
        sys.exit(1)

    try:
        content = Path(file_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        print(json.dumps({"error": f"File not found: {file_path}"}), file=sys.stderr)
        sys.exit(1)

    detected = detect_version(content)
    needs_migration = detected < CURRENT_VERSION

    if mode == '--check':
        result = {
            "detected_version": detected,
            "current_version": CURRENT_VERSION,
            "needs_migration": needs_migration,
        }
        print(json.dumps(result))
        sys.exit(0)

    if mode == '--dry-run':
        plan = get_migration_plan(detected)
        result = {"migrations": plan}
        print(json.dumps(result))
        sys.exit(0 if plan else 2)

    # 通常モード: マイグレーション実行
    if not needs_migration:
        # 変更なし — 入力をそのまま出力
        print(content, end='')
        sys.exit(0)

    migrated = apply_migrations(content, detected)
    print(migrated, end='')
    sys.exit(0)


if __name__ == '__main__':
    main()
