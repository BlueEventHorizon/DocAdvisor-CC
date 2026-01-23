#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToC Auto-Generation Common Utilities

Common functions used by merge-rules-toc, merge-specs-toc, create-toc-checksums.
Uses only standard library.
"""

import re
import shutil
from pathlib import Path


def get_project_root():
    """
    Detect project root (searches for .git or .claude directory)

    Returns:
        Path: Path to project root

    Raises:
        RuntimeError: When project root cannot be found
    """
    current = Path(__file__).parent.absolute()

    # Search up to 10 levels
    for _ in range(10):
        if (current / ".git").exists() or (current / ".claude").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise RuntimeError("Project root not found (.git or .claude directory required)")


def resolve_config_path(config_value, default_base, project_root):
    """
    Resolve configuration path value.

    If the path starts with '.claude/', it is resolved relative to project_root.
    Otherwise, it is resolved relative to default_base.

    Args:
        config_value: Path string from configuration
        default_base: Default base directory (e.g., SPECS_DIR, RULES_DIR)
        project_root: Project root directory

    Returns:
        Path: Resolved absolute path
    """
    path_str = str(config_value).rstrip('/')
    if path_str.startswith('.claude/'):
        return project_root / path_str
    return default_base / path_str


def find_config_file():
    """
    Find configuration file.

    Location: {CWD}/.claude/doc-advisor/config.yaml

    Returns:
        Path: Path to configuration file

    Raises:
        FileNotFoundError: When no configuration file is found
    """
    project_config = Path.cwd() / ".claude/doc-advisor/config.yaml"
    if project_config.exists():
        return project_config

    raise FileNotFoundError(
        "Configuration file not found. Please create one at:\n"
        "  - .claude/doc-advisor/config.yaml\n"
        "Run setup.sh to generate the configuration file."
    )


def load_config(target=None):
    """
    Load config.yaml and return configuration dictionary

    Args:
        target: 'rules' or 'specs'. If specified, returns only that section

    Returns:
        dict: Configuration dictionary
    """
    try:
        config_path = find_config_file()
    except FileNotFoundError:
        # Return default configuration if no file found
        defaults = _get_default_config()
        if target:
            return defaults.get(target, {})
        return defaults

    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    config = _parse_config_yaml(content)

    if target:
        return config.get(target, {})
    return config


def _get_default_config():
    """Return default configuration"""
    return {
        'rules': {
            'root_dir': 'rules/',
            'toc_file': 'rules_toc.yaml',
            'checksums_file': '.toc_checksums.yaml',
            'work_dir': '.toc_work/',
            'patterns': {
                'target_glob': '**/*.md',
                'exclude': ['.toc_work', 'rules_toc.yaml', 'reference']
            },
            'output': {
                'header_comment': 'Development Document Search Index for rules-advisor Subagent',
                'metadata_name': 'Development Document Search Index'
            }
        },
        'specs': {
            'root_dir': 'specs/',
            'toc_file': 'specs_toc.yaml',
            'checksums_file': '.toc_checksums.yaml',
            'work_dir': '.toc_work/',
            'patterns': {
                'target_dirs': {
                    'requirement': 'requirements',
                    'design': 'design',
                    'plan': 'plan'
                },
                'exclude': ['.toc_work', '.toc_checksums.yaml', 'specs_toc.yaml', 'reference', '/info/']
            },
            'output': {
                'header_comment': 'Requirement & Design Document Search Index for specs-advisor Subagent',
                'metadata_name': 'Requirement & Design Document Search Index'
            }
        },
        'common': {
            'parallel': {
                'max_workers': 5,
                'fallback_to_serial': True
            }
        }
    }


def _parse_config_yaml(content):
    """
    Parse config.yaml (simple YAML parser)

    Handles up to 4 levels of nesting:
    - Level 0: Top-level sections (rules, specs, common)
    - Level 2: Subsections (root_dir, patterns, output)
    - Level 4: Sub-subsections (target_dirs, exclude)
    - Level 6: Items (key-value pairs or list items)
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

        # Skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            continue

        # Calculate indent level
        indent = len(line) - len(line.lstrip())

        if ':' in stripped and not stripped.startswith('- '):
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if indent == 0:
                # Top-level section
                current_section = key
                result[key] = {}
                current_subsection = None
                current_subsubsection = None
                current_list = None
                current_dict = None
            elif indent == 2 and current_section:
                # Subsection
                current_subsection = key
                if value:
                    result[current_section][key] = _parse_value(value)
                else:
                    result[current_section][key] = {}
                current_subsubsection = None
                current_list = None
                current_dict = None
            elif indent == 4 and current_section and current_subsection:
                # Sub-subsection - look ahead to determine if list or dict
                current_subsubsection = key
                if value:
                    result[current_section][current_subsection][key] = _parse_value(value)
                    current_list = None
                    current_dict = None
                else:
                    # Look ahead to determine structure type
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
                # Key-value pair inside sub-subsection dict
                current_dict[key] = _parse_value(value) if value else ''
        elif stripped.startswith('- ') and current_list is not None:
            item = stripped[2:].strip().strip('"\'')
            current_list.append(item)

    return result


def _lookahead_is_list(lines, start_idx):
    """
    Look ahead in lines to determine if the next content is a list or dict.

    Args:
        lines: List of all lines
        start_idx: Index to start looking from

    Returns:
        bool: True if next content is a list (starts with '- ')
    """
    for i in range(start_idx, min(start_idx + 10, len(lines))):
        line = lines[i]
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())

        # If we hit a line with less or equal indent, stop looking
        if indent <= 4:
            break

        # Check if it's a list item or key-value
        if stripped.startswith('- '):
            return True
        if ':' in stripped:
            return False

    # Default to list for backward compatibility
    return True


def _parse_value(value):
    """Parse value (string, number, boolean)"""
    value = value.strip().strip('"\'')

    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    try:
        return int(value)
    except ValueError:
        pass

    return value


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

            if value:
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

    # Check if special character escaping is needed
    needs_quotes = any(c in s for c in ':#{}[]&*!|>\'"%@`\n\r\t,?')
    needs_quotes = needs_quotes or s.startswith('-') or s.startswith(' ')
    needs_quotes = needs_quotes or s.endswith(' ')  # Trailing space

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
        print(f"Backup created: {backup_path}")


def load_checksums(checksums_file):
    """
    Get file list from checksum file

    Args:
        checksums_file: Path to checksum file (str or Path)

    Returns:
        set: Set of file paths
    """
    checksums_file = Path(checksums_file)

    if not checksums_file.exists():
        return set()

    try:
        with open(checksums_file, 'r', encoding='utf-8') as f:
            content = f.read()

        files = set()
        in_checksums = False
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped == 'checksums:':
                in_checksums = True
                continue
            if in_checksums and ':' in stripped:
                filepath = stripped.split(':')[0].strip()
                files.add(filepath)

        return files
    except Exception as e:
        print(f"Warning: Checksum file read error: {e}")
        print("Fallback: Skipping deletion detection")
        return set()


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
            print(f"Cleanup complete: {work_dir}")
            return True
        except (OSError, PermissionError) as e:
            print(f"Warning: Cleanup failed: {work_dir} - {e}")
            print("   Please delete manually")
            return False
    return True


def extract_id_from_filename(filename):
    """
    DEPRECATED: This function is no longer recommended.

    Document identification should use file path instead of filename-based ID.
    See DES-003_document_identifier.md for details.

    This function is kept for backward compatibility but should not be used
    in new code. The file path (relative to the root directory) serves as
    the unique identifier for each document.

    ---
    Original docstring:
    Extract document ID from filename (generic regex version)

    Args:
        filename: Filename (path also accepted)

    Returns:
        str or None: Extracted ID, None if not found

    Examples:
        'SCR-001_foo.md' → 'SCR-001'
        'DES-042_bar.md' → 'DES-042'
        'CUSTOM-123_baz.md' → 'CUSTOM-123'
    """
    import warnings
    warnings.warn(
        "extract_id_from_filename is deprecated. Use file path as document identifier.",
        DeprecationWarning,
        stacklevel=2
    )
    # Get only filename part if path is provided
    if '/' in filename:
        filename = filename.split('/')[-1]

    # Match [A-Z]+-\d+ pattern
    match = re.match(r'([A-Z]+-\d+)', filename)
    if match:
        return match.group(1)
    return None


def should_exclude(filepath, root_dir, exclude_patterns):
    """
    Check if file should be excluded

    Args:
        filepath: File path to check (Path)
        root_dir: Root directory (Path)
        exclude_patterns: List of exclusion patterns

    Returns:
        bool: True if should be excluded
    """
    rel_path = str(filepath.relative_to(root_dir))
    for pattern in exclude_patterns:
        if pattern in rel_path:
            return True
    return False
