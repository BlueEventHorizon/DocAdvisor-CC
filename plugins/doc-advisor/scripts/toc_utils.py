#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC Auto-Generation Common Utilities (doc-advisor plugin)

doc-advisor プラグインの ToC 生成で使用する共通関数。
標準ライブラリのみ使用。
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


class PathRejection(ValueError):
    """path 検証で reject されたことを表す。error_code を保持する。

    error_code は toc_store.py の ErrorCode 定数と整合する文字列。
    検証フロー（validate_path）の呼び出し側が rejected_paths に
    `{"path": ..., "reason": error_code}` を積むために使う。
    """

    def __init__(self, message, error_code):
        super().__init__(message)
        self.error_code = error_code


def resolve_within_root(path, project_root):
    """symlink 実体を解決し、project root 配下にあることを保証する（DES-005 §5.2 / NFR-N06）。

    `validate_path_within_base()` が担う論理パス検証（traversal / CWE-22）とは
    **別ロジック**であり、symlink の実体解決による root 外参照の reject を担う。

    手順:
    1. `Path.resolve(strict=True)` で symlink を辿り実体を解決する。
       実体が存在しない場合は `FileNotFoundError` を送出する
       （呼び出し側で NOT_FOUND 扱いにする。REQ-001 FR-N03-4 の不在 reject と兼ねる）。
    2. `Path.is_relative_to(project_root)`（Python 3.9 で追加。サポート下限は
       REQ-001 NFR-N01 で 3.11）で解決後の実体が project root 配下かを判定する。
       root 外を指す symlink は reject する。

    Args:
        path: 検証対象パス（str or Path）。絶対 / 相対いずれも resolve される。
        project_root: project root（str or Path）

    Returns:
        Path: resolve 済みの実体パス（project root 配下であることが保証される）

    Raises:
        FileNotFoundError: 実体が存在しない場合（strict=True）
        PathRejection: 解決後の実体が project root 外の場合（OUTSIDE_ROOT）
    """
    resolved = Path(path).resolve(strict=True)
    root_resolved = Path(project_root).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise PathRejection(
            f"Resolved path escapes project root: {path}",
            "OUTSIDE_ROOT",
        )
    return resolved


def find_escaping_symlink(rel_path, project_root):
    """rel_path（project-root-relative の正規化済み path）上で、project root の外へ
    越境している **最上位の symlink** の project-root-relative prefix を返す（NFR-N06）。

    root から path コンポーネントを順に辿り、最初に「symlink かつ実体が root 配下でない」
    prefix を返す。これが承認の単位になる（配下に何ファイルあっても prefix は 1 つ）。
    越境している symlink が無ければ None（= traversal でない真の root 外。理論上は
    §5.1 の traversal 検証で先に弾かれるため到達しない想定）。

    Args:
        rel_path: project-root-relative の正規化済み path（str or Path）
        project_root: project root（str or Path）

    Returns:
        str | None: 越境 symlink の rel prefix（POSIX 区切り）、無ければ None
    """
    root = Path(project_root)
    try:
        root_resolved = root.resolve()
    except (OSError, RuntimeError):
        return None
    parts = Path(rel_path).parts
    prefix = root
    for i, part in enumerate(parts):
        prefix = prefix / part
        if prefix.is_symlink():
            try:
                target = prefix.resolve()
            except (OSError, RuntimeError):
                # 解決不能な symlink も越境扱いにして承認対象に挙げる
                return Path(*parts[: i + 1]).as_posix()
            if not target.is_relative_to(root_resolved):
                return Path(*parts[: i + 1]).as_posix()
    return None


# Markdown 拡張子（非 Markdown reject 判定用。DES-005 §5.1）
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})


def validate_path(path, project_root):
    """単一 path を REQ-001 §6.1 / DES-005 §5.1 の検証フローに従って検証する。

    検証順（フロー図 §5.1）:
    1. 絶対パス → reject（ABSOLUTE_PATH）
    2. NFC 正規化 + `./` 解決
    3. 論理パス検証（traversal） → reject（PATH_TRAVERSAL）。既存 `validate_path_within_base` を流用
    4. symlink 実体解決（strict） → 不在は reject（NOT_FOUND）
    5. root 配下判定 → root 外実体は次の分岐:
       - 越境 symlink 経由 → **受理する**。越境した symlink prefix を戻り値で通知する
       - symlink を介さない真の root 外 → reject（OUTSIDE_ROOT）
    6. Markdown 判定 → 非 Markdown は reject（NOT_MARKDOWN）
    7. すべて通れば project-root-relative の正規化済み path を返す（accept）

    `./a.md` と `a.md` は同一視され、いずれも `a.md` に正規化される。

    error_code は toc_store.py の ErrorCode 定数と整合する文字列で
    PathRejection に保持される。

    **越境 symlink を拒否しない [MANDATORY]**: 明示 paths は呼び出し元（上位層）が
    索引対象として決めたものであり、それが symlink であることは渡す側が知っている
    （NFR-N06）。doc-advisor が別の理由でここを塞ぐと、判断が複数箇所に分かれ、
    上位層は自分の指定が通らない理由を知り得ない。注意喚起は warning で行い、
    索引するか否かの決定は呼び出し元に残す。

    Args:
        path: 検証対象の入力 path（str）。project-root-relative であることを期待する。
        project_root: project root（str or Path）

    Returns:
        tuple[str, str | None]: (project-root-relative の正規化済み path,
            root 境界を越えた symlink の rel prefix。越境していなければ None)

    Raises:
        PathRejection: 検証失敗時。error_code に reject 理由を保持する。
    """
    root = Path(project_root)
    external_symlink = None

    # 1. 絶対パス reject
    raw = normalize_path(path)
    if os.path.isabs(raw):
        raise PathRejection(f"Absolute path is not allowed: {path}", "ABSOLUTE_PATH")

    # 2. NFC 正規化 + ./ 解決（os.path.normpath が "./a.md" → "a.md" を行う）
    rel_normalized = normalize_path(os.path.normpath(raw))

    # 3. 論理パス検証（traversal）。既存関数を流用（symlink は辿らない）。
    try:
        validate_path_within_base(rel_normalized, root)
    except ValueError as e:
        raise PathRejection(str(e), "PATH_TRAVERSAL") from e

    # 4-5. symlink 実体解決 + root 配下判定
    candidate = root / rel_normalized
    try:
        resolve_within_root(candidate, root)
    except FileNotFoundError as e:
        raise PathRejection(f"Path does not exist: {path}", "NOT_FOUND") from e
    except PathRejection as e:
        if e.error_code != "OUTSIDE_ROOT":
            raise
        # root 外実体: 越境している symlink を特定する（NFR-N06）。
        sym = find_escaping_symlink(rel_normalized, root)
        if sym is None:
            # symlink を介さない真の root 外（理論上 traversal で先に弾かれる）。reject。
            raise
        # 越境 symlink 経由 → 受理し、prefix を呼び出し元へ通知して Markdown 判定へ続行
        external_symlink = sym

    # 6. Markdown 判定（論理パスの拡張子で判定。symlink 先の実体拡張子に依存しない）
    if Path(rel_normalized).suffix.lower() not in MARKDOWN_SUFFIXES:
        raise PathRejection(f"Not a Markdown file: {path}", "NOT_MARKDOWN")

    # 7. accept: project-root-relative の正規化済み path
    return rel_normalized, external_symlink


def detect_case_collisions(normalized_paths):
    """正規化済み path 集合から case-insensitive 衝突を検出する（DES-005 §5.2）。

    大文字小文字のみが異なる path が混在する場合に warning メッセージを返す。
    処理は継続する（reject しない）。REQ-001 §6.1「大小衝突」/ NFR-N06。

    Args:
        normalized_paths: 正規化済み path のリスト（validate_path の戻り値）

    Returns:
        list[str]: warning メッセージのリスト（衝突なしなら空リスト）
    """
    warnings = []
    lower_map = {}
    for p in normalized_paths:
        lower = p.lower()
        if lower in lower_map:
            existing = lower_map[lower]
            if existing != p:
                warnings.append(
                    f"case-insensitive collision: {existing} vs {p}"
                )
        else:
            lower_map[lower] = p
    return warnings




def parse_simple_yaml(content):
    """
    Simple YAML parser (for entry files)

    Separates _meta section and normal entries.

    Args:
        content: YAML file content

    Returns:
        tuple: (meta_dict, entry_dict)
    """
    result = {}
    current_key = None
    current_list = None
    in_meta = False
    meta = {}

    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        if stripped == '_meta:':
            in_meta = True
            i += 1
            continue

        if in_meta:
            if line.startswith('  ') and ':' in stripped:
                key, _, value = stripped.partition(':')
                meta[key.strip()] = value.strip().strip('"\'')
            elif not line.startswith(' '):
                in_meta = False
            else:
                i += 1
                continue

        if not line.startswith(' ') and ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()

            if value == '[]':
                # Inline empty array (e.g., "keywords: []")
                current_key = key
                current_list = []
                result[key] = current_list
            elif value:
                result[key] = value.strip('"\'')
                current_key = None
                current_list = None
            else:
                current_key = key
                current_list = []
                result[key] = current_list
            i += 1
            continue

        if current_list is not None and stripped.startswith('- '):
            item = stripped[2:].strip().strip('"\'')
            current_list.append(item)
            i += 1
            continue

        i += 1

    return meta, result


def load_entry_file(filepath):
    """
    Load and parse entry file

    Args:
        filepath: File path (str or Path)

    Returns:
        tuple: (meta_dict, entry_dict)

    Raises:
        IOError: When file read fails
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return parse_simple_yaml(content)
    except (IOError, OSError, PermissionError) as e:
        raise IOError(f"Entry file read error: {filepath} - {e}") from e


def normalize_field_value(value):
    """メタデータ値を、意味を変えずに値域内へ収める。

    値域から外れる文字のうち、**意味を保つ代替が存在するもの**は書き込みの入口で
    変換する。拒否すると文字 1 つのために文書のメタデータ全体が AI 再抽出へ回るが、
    再抽出の原因は意味に関わらない表記であり、その費用を払う理由がない。

    変換するもの:

    - 二重引用符 → バッククォート（英語の記述文で意味は変わらない）
    - 改行 / CR / タブ → 空白（連続する空白は畳む。フィールドは単一行と定義済み）
    - **先頭・末尾の**単一引用符 → バッククォート。読み側が両端の引用符を削るため
      この位置だけが問題になる。`don't` のような中間の `'` は温存する（変換範囲を
      最小に保つ。両端だけを替えると表記が非対称に見えることがあるが、意味を保つ
      ことを優先する）

    **バックスラッシュは変換しない。** 落とせば `\\n handling` が `n handling` に、
    `/` へ替えればエスケープ表記の意味が変わる。パス表記なのかエスケープ表記なのかは
    値から決まらないため、意味を保つ代替が存在しない。値域検証側で拒否する。

    変換したことは呼び出し側が報告する（書いた値と原本に入る値が違うことを黙って
    済ませない）。そのため変更の有無を返す。

    Args:
        value: メタデータの値（str 以外はそのまま返す）

    Returns:
        tuple: (正規化後の値, 変換したか)
    """
    if not isinstance(value, str):
        return value, False

    normalized = value
    for ch in "\n\r\t":
        normalized = normalized.replace(ch, " ")
    if normalized != value:
        normalized = " ".join(normalized.split())
    normalized = normalized.replace('"', "`")

    stripped = normalized.strip()
    if stripped.startswith("'"):
        head = normalized.index("'")
        normalized = normalized[:head] + "`" + normalized[head + 1:]
    stripped = normalized.strip()
    if stripped.endswith("'"):
        tail = normalized.rindex("'")
        normalized = normalized[:tail] + "`" + normalized[tail + 1:]

    return normalized, normalized != value


def sanitize_uncontrolled_text(s):
    """統制できない外部由来テキストを、YAML 値として往復できる形へ正規化する。

    doc-advisor が書く YAML の値のうち、内容を統制できるもの（メタデータ 5
    フィールド）は値域規則で「単一行の平文」を機械的に強制する。しかし捕捉した
    例外メッセージのように**内容を選べない値**もあり、そこへ同じ制約を課せない。

    そこで入口で正規化する。`yaml_escape` のバックスラッシュ・エスケープに頼らないのは、
    `toc.yaml` / pending の読み側（`parse_simple_yaml` / `load_existing_toc`）が引用符を
    外すだけでエスケープを復元しないためである。実際に
    `FileNotFoundError: [Errno 2] No such file or directory: 'docs/x.md'` は読み戻しで
    末尾のアポストロフィを失っていた（Issue #41）。

    診断メッセージは非可逆な正規化を許容できる。それが「データ」ではなく「診断」で
    あることの意味であり、だからこの関数は値を捨てる方向へ寄せてよい。

    Args:
        s: 正規化対象（str 以外は str() を通す）

    Returns:
        str: 単一行で、引用符・バックスラッシュを含まないテキスト
    """
    if s is None:
        return ""
    s = str(s)
    # 改行・タブは単一行化のため空白へ倒し、連続空白を畳む
    for ch in "\n\r\t":
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    # 引用符はバッククォートへ倒す（読みやすさを保ったまま往復可能にする）
    s = s.replace('"', "`").replace("'", "`")
    # バックスラッシュは復元できないため落とす
    s = s.replace("\\", "")
    return s


def yaml_escape(s):
    """
    Escape string for YAML output

    Args:
        s: String to escape

    Returns:
        str: Escaped string
    """
    if not s:
        return '""'

    # Convert to string if not already
    s = str(s)

    # Check if first character is a YAML indicator (block plain scalar rule)
    first_char_indicators = set('-?:,[]{}#&*!|>\'"% @`~')
    needs_quotes = s[0] in first_char_indicators

    # Patterns special ANYWHERE in block plain scalar
    # ": " and " #" are YAML spec restrictions
    # '"' and "'" cause round-trip issues with parse_simple_yaml's strip()
    if not needs_quotes:
        needs_quotes = ': ' in s or ' #' in s or '"' in s or "'" in s

    # Trailing colon or trailing space
    if not needs_quotes:
        needs_quotes = s.endswith(':') or s.endswith(' ')

    # Control characters always need quoting
    if not needs_quotes:
        needs_quotes = any(c in s for c in '\n\r\t')

    # Check if it looks like a number (would be parsed as int/float)
    if not needs_quotes:
        try:
            float(s)
            needs_quotes = True
        except ValueError:
            pass

    # Check if it's a YAML boolean or null keyword
    if s.lower() in ('true', 'false', 'yes', 'no', 'on', 'off', 'null', 'none', '~'):
        needs_quotes = True

    if needs_quotes:
        # Escape backslash first, then double quote
        escaped = s.replace('\\', '\\\\').replace('"', '\\"')
        # Escape newline and tab
        escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return f'"{escaped}"'

    return s


def load_existing_toc(toc_path):
    """
    既存の {category}_toc.yaml を読み込む（docs: セクション形式対応）

    Args:
        toc_path: ToC ファイルパス (str or Path)

    Returns:
        dict: source_file → entry_dict のマッピング
    """
    toc_path = Path(toc_path)
    if not toc_path.exists():
        return {}

    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, OSError, PermissionError) as e:
        log(f"Warning: Failed to read {toc_path}: {e}")
        return {}

    docs = {}
    current_section = None
    current_path = None
    current_entry = {}
    current_list = None

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('#') or not stripped:
            continue

        if stripped == 'docs:':
            current_section = 'docs'
            continue
        elif stripped.startswith('metadata:'):
            current_section = 'metadata'
            continue

        if current_section != 'docs':
            continue

        # ファイルパスキーの検出（2スペースインデント）
        if line.startswith('  ') and not line.startswith('    '):
            key_candidate = stripped.rstrip(':')
            # クォートされた YAML キーを処理: "path/to/file.md"
            if key_candidate.startswith('"') and key_candidate.endswith('"'):
                key_candidate = key_candidate[1:-1]
            if key_candidate.endswith('.md'):
                if current_path and current_entry:
                    docs[current_path] = current_entry
                current_path = normalize_path(key_candidate)
                current_entry = {}
                current_list = None
        elif line.startswith('    ') and ':' in stripped and not stripped.startswith('-'):
            if current_path:
                key, _, val = stripped.partition(':')
                key = key.strip()
                val = val.strip().strip('"\'')
                if val == '[]':
                    current_list = []
                    current_entry[key] = current_list
                elif val:
                    current_entry[key] = val
                    current_list = None
                else:
                    current_list = []
                    current_entry[key] = current_list
        elif stripped.startswith('- ') and current_list is not None:
            item = stripped[2:].strip().strip('"\'')
            current_list.append(item)

    if current_path and current_entry:
        docs[current_path] = current_entry

    return docs


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
        - Patterns without '/' are matched as an exact directory name at any
          depth; filenames are NOT matched (so 'plan' never excludes
          'planning.md')
        - Patterns containing '/' are matched against the full relative path at
          segment boundaries: the path must equal the pattern (file/dir exact)
          or start with `pattern + '/'` (subtree). This covers both file
          targets ('docs/drop.md') and subtree targets ('docs/draft'), while
          avoiding the over-match where 'a/b' would otherwise hit 'za/bc'.
        - NFC normalization is applied for macOS NFD compatibility
        - This matcher is shared by both the system-fixed excludes
          (SYSTEM_EXCLUDE_PATTERNS) and the user excludes (--exclude-json), so
          the two stay self-consistent.
    """
    rel_path = normalize_path(filepath.relative_to(root_dir))
    path_parts = rel_path.split('/')
    dir_parts = path_parts[:-1]  # ファイル名を除いたディレクトリセグメント

    for pattern in exclude_patterns:
        # 先頭・末尾の / を除去し NFC 正規化
        normalized = normalize_path(pattern.strip('/'))
        if not normalized:
            continue

        if '/' in normalized:
            # パスを含むパターン: rel_path 全体とのセグメント境界マッチ。
            # 完全一致（ファイル/ディレクトリ指定）または pattern + '/' 前置き（サブツリー指定）。
            if rel_path == normalized or rel_path.startswith(normalized + '/'):
                return True
        else:
            # ディレクトリ名として完全一致でチェック（ファイル名は対象外）
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


# ---------------------------------------------------------------------------
# 公開定数（他スクリプトから共有）
# ---------------------------------------------------------------------------

# 固定除外パターン（DES-005 §9.1）。
# should_exclude はディレクトリ名完全一致 / path セグメント境界マッチで適用する。
# ".claude" 除外で生成済み ToC / work files も同時にカバーされる。
SYSTEM_EXCLUDE_PATTERNS = [
    ".git",            # .git/**
    ".claude",         # .claude/** runtime state + 生成済み ToC / work files
    ".codex",          # .codex/**
    "node_modules",    # node_modules/**
    "vendor",          # vendor/**
    "dist",            # dist/**
    "build",           # build/**
    "__pycache__",     # __pycache__/**
    ".venv",           # .venv/**
    "target",          # target/**
    "coverage",        # coverage/**
    ".pytest_cache",   # .pytest_cache/**
    ".mypy_cache",     # .mypy_cache/**
]

# Markdown 走査グロブ
MARKDOWN_GLOB = "**/*.md"
