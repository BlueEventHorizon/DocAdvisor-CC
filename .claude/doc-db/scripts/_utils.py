#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc-db plugin 共通基盤モジュール（_utils）

plugins/doc-advisor/scripts/toc_utils.py から必要関数のみ抽出してコピー。
AC-01 厳守: doc-advisor 本体への runtime 依存は持たない。

抽出対象（DES-026 §3.1 の責務に対応）:
- ロギング: log
- パス正規化: normalize_path（NFC）
- プロジェクトルート / 設定ファイル: get_project_root, find_config_file
- パスバリデーション: validate_path_within_base, resolve_config_path
- ハッシュ / checksum: calculate_file_hash, write_checksums_yaml, load_checksums
- glob / 除外判定: should_exclude, rglob_follow_symlinks
- ファイル操作: backup_existing_file, cleanup_work_dir

抽出した関数の実装は、コピー時点の toc_utils.py と同一に保つ。同期対象は上記
「抽出対象」の関数のみで、toc_utils.py 側にそれ以外の関数が追加されても自動追随
しない（必要時に明示的に再抽出する）。バグ修正・機能改善は両側へ還元する。
標準ライブラリのみ使用（NFR-005 / DEP-01）。
"""

import fnmatch
import hashlib
import os
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def log(*args, **kwargs):
    """stderr にログメッセージを出力する。stdout の JSON 出力を汚染しない。"""
    kwargs.setdefault('file', sys.stderr)
    print(*args, **kwargs)


def normalize_path(path_str):
    """
    Normalize path string to NFC for consistent comparison.

    macOS stores filenames in NFD (decomposed) form, while config files
    and user input typically use NFC (composed) form. This causes string
    comparison to fail for Japanese characters with dakuten/handakuten
    (e.g., プ as U+30D7 vs フ+゚ as U+30D5+U+309A).
    """
    return unicodedata.normalize('NFC', str(path_str))


def get_project_root():
    """
    Return the project root directory.

    Claude Code's Bash tool always sets cwd to the project root,
    so upward traversal is unnecessary and risky (can hit ~/.claude/).

    Fallback order:
    1. CLAUDE_PROJECT_DIR environment variable (if set and valid)
    2. Current working directory (= project root in Claude Code context)

    Returns:
        Path: Path to project root
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        p = Path(project_dir)
        if p.is_dir():
            return p
        else:
            log(
                f"Warning: CLAUDE_PROJECT_DIR='{project_dir}' does not exist or is not a directory. "
                "Falling back to CWD."
            )

    return Path.cwd().resolve()


def validate_path_within_base(path, base_dir):
    """
    Validate that a path resolves within the base directory.
    Prevents path traversal attacks via ../ sequences (CWE-22).
    Supports symlinked directories by checking the logical path
    (without resolving symlinks) for containment, then returning
    the joined path for file access.

    Args:
        path: Path to validate (str or Path)
        base_dir: Allowed base directory (str or Path)

    Returns:
        Path: The joined path (base_dir / path) for existence checks

    Raises:
        ValueError: If path contains traversal sequences escaping base_dir

    Note:
        Symlinks within base_dir may point outside it; such access is intentionally
        permitted (project-configured symlinks). Only ../ traversal sequences that
        escape base_dir in the logical path are rejected.
    """
    # シンボリックリンクを解決せずに論理パスで包含チェック
    # （.. を正規化しつつシンボリックリンクは辿らない）
    joined = Path(base_dir, path)
    # os.path.normpath で .. を解決（シンボリックリンクは辿らない）
    normalized = os.path.normpath(str(joined))
    base_normalized = os.path.normpath(str(base_dir))
    if not normalized.startswith(base_normalized + os.sep) and normalized != base_normalized:
        raise ValueError(f"Path traversal detected: {path}")
    return joined


def resolve_config_path(config_value, default_base, project_root):
    """
    Resolve configuration path value.

    Multi-component paths (containing '/') are resolved relative to project_root.
    Simple names (no '/') are resolved relative to default_base.

    This supports both default paths (.claude/doc-db/...) and
    output_dir-derived paths as project-relative,
    while keeping simple fallback names (.embedding_checksums.yaml etc.) as
    default_base-relative.

    Args:
        config_value: Path string from configuration
        default_base: Default base directory
        project_root: Project root directory

    Returns:
        Path: Resolved absolute path
    """
    path_str = str(config_value).rstrip('/')
    if '/' in path_str:
        return project_root / path_str
    return default_base / path_str


def find_config_file():
    """
    Find .doc_structure.yaml at project root.

    Returns:
        Path: Path to .doc_structure.yaml

    Raises:
        FileNotFoundError: When no configuration file is found
    """
    project_root = get_project_root()
    doc_structure = project_root / ".doc_structure.yaml"
    if doc_structure.exists():
        return doc_structure

    raise FileNotFoundError(
        ".doc_structure.yaml not found.\n"
        "Run setup-doc-structure to create it."
    )


def calculate_file_hash(path, chunk_size=65536):
    """
    ファイルの SHA-256 ハッシュをチャンク読み込みで計算する（大ファイル対応）

    Args:
        path: ファイルパス (str or Path)
        chunk_size: 読み込みチャンクサイズ（デフォルト 64KB）

    Returns:
        str: SHA-256 ハッシュ値（16進数文字列）。エラー時は None
    """
    try:
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: File read error: {path} - {e}")
        return None


def write_checksums_yaml(checksums, output_path, header_comment="Auto-generated checksum file"):
    """Write checksums dict to YAML format file.

    Args:
        checksums: dict of {filepath: hash_value}
        output_path: Output file path (str or Path)
        header_comment: First line comment in the output file

    Returns:
        bool: True on success, False on failure
    """
    lines = [
        f"# {header_comment}",
        "# Auto-generated - do not edit",
        f"generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"file_count: {len(checksums)}",
        "checksums:",
    ]

    for rel_path, hash_value in sorted(checksums.items()):
        lines.append(f"  {rel_path}: {hash_value}")

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"Error: Failed to write file: {output_path} - {e}")
        return False


def load_checksums(checksums_file):
    """
    チェックサムファイルを読み込み、ファイルパス→ハッシュ値の辞書を返す

    Args:
        checksums_file: Path to checksum file (str or Path)

    Returns:
        dict: ファイルパス → ハッシュ値のマッピング
    """
    checksums_file = Path(checksums_file)

    if not checksums_file.exists():
        return {}

    try:
        with open(checksums_file, 'r', encoding='utf-8') as f:
            content = f.read()

        checksums = {}
        in_checksums = False
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped == 'checksums:':
                in_checksums = True
                continue
            if in_checksums:
                # Skip blank lines within checksums section
                if not stripped:
                    continue
                # Next top-level section (no indent + contains ': ') ends checksums
                if ': ' in stripped and not line.startswith(' '):
                    in_checksums = False
                    continue
                if ': ' in stripped:
                    # SHA-256 ハッシュのみを想定（ハッシュ値自体に ': ' は含まれない前提）
                    parts = stripped.rsplit(': ', 1)
                    if len(parts) == 2:
                        filepath = parts[0].strip()
                        hash_val = parts[1].strip()
                        checksums[filepath] = hash_val

        return checksums
    except (FileNotFoundError, ValueError, KeyError, OSError) as e:
        log(f"Warning: Checksum file read error: {e}")
        log("Fallback: Skipping deletion detection")
        return {}


def should_exclude(filepath, root_dir, exclude_patterns):
    """
    Check if file should be excluded

    Args:
        filepath: File path to check (Path)
        root_dir: Root directory (Path)
        exclude_patterns: List of exclusion patterns

    Returns:
        bool: True if should be excluded

    Note:
        - All patterns are matched against directory path only (filename excluded)
        - Patterns containing '/' are matched as path substring
        - Patterns without '/' are matched as exact directory name
        - This prevents 'plan' from excluding 'planning.md'
        - NFC normalization is applied for macOS NFD compatibility
    """
    rel_path = normalize_path(filepath.relative_to(root_dir))
    path_parts = rel_path.split('/')
    dir_parts = path_parts[:-1]  # ファイル名を除く
    dir_path = '/'.join(dir_parts)  # ディレクトリパスのみ

    for pattern in exclude_patterns:
        # 先頭・末尾の / を除去し NFC 正規化
        normalized = normalize_path(pattern.strip('/'))

        if '/' in normalized:
            # パターンに / が含まれる場合はパス部分文字列としてマッチ
            if normalized in dir_path:
                return True
        else:
            # ディレクトリ名として完全一致でチェック
            if normalized in dir_parts:
                return True
    return False


def rglob_follow_symlinks(root_dir, pattern):
    """
    シンボリックリンクを follow して再帰的にファイルを検索する。

    inode を追跡してシンボリックリンクループを防止し、
    同じファイルへの複数パスを重複排除する。

    Args:
        root_dir: 検索開始ディレクトリ (Path or str)
        pattern: glob パターン (例: "*.md", "**/*.md")

    Yields:
        Path: マッチしたファイルパス

    Note:
        - シンボリックリンクのループを検出して無限再帰を防止
        - 同じファイルへの複数パス（シンボリックリンク経由）は一度だけ yield
        - "**/" を含むパターンは再帰的に検索、含まないパターンは直下のみ
    """
    root_dir = Path(root_dir)
    seen_inodes = set()

    # パターンを解析
    # "**/*.md" -> 再帰的に検索、"*.md" -> 直下のみ
    if '**' in pattern:
        # "**/*.md" -> "*.md", "**/*.yaml" -> "*.yaml"
        file_pattern = pattern.replace('**/', '').replace('**', '')
        if not file_pattern:
            file_pattern = '*'
        recursive = True
    else:
        file_pattern = pattern
        recursive = False

    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=True):
        current_path = Path(dirpath)

        # ディレクトリの inode をチェック（ループ防止）
        try:
            stat_info = current_path.stat()
            dir_inode = (stat_info.st_dev, stat_info.st_ino)
            if dir_inode in seen_inodes:
                # シンボリックリンクループを検出、このディレクトリをスキップ
                dirnames.clear()  # サブディレクトリへの再帰を防止
                continue
            seen_inodes.add(dir_inode)
        except OSError:
            # stat に失敗した場合はスキップ
            continue

        # ファイルをマッチング
        for filename in filenames:
            if fnmatch.fnmatch(filename, file_pattern):
                filepath = current_path / filename
                # ファイルの inode もチェック（同じファイルへの複数パスを防止）
                try:
                    file_stat = filepath.stat()
                    file_inode = (file_stat.st_dev, file_stat.st_ino)
                    if file_inode in seen_inodes:
                        continue
                    seen_inodes.add(file_inode)
                except OSError:
                    continue
                yield filepath

        # 非再帰モードの場合は最初のディレクトリのみ
        if not recursive:
            break


def backup_existing_file(file_path):
    """
    Backup existing file (with .bak extension)

    Args:
        file_path: File path to backup (str or Path)
    """
    file_path = Path(file_path)
    if file_path.exists():
        backup_path = file_path.with_suffix('.yaml.bak')
        shutil.copy(file_path, backup_path)
        log(f"Backup created: {backup_path}")


def cleanup_work_dir(work_dir):
    """
    Delete work directory

    Args:
        work_dir: Directory path to delete (str or Path)

    Returns:
        bool: True on success, False on failure
    """
    work_dir = Path(work_dir)
    if work_dir.exists():
        try:
            shutil.rmtree(work_dir)
            log(f"Cleanup complete: {work_dir}")
            return True
        except (OSError, PermissionError) as e:
            log(f"Warning: Cleanup failed: {work_dir} - {e}")
            log("   Please delete manually")
            return False
    return True
