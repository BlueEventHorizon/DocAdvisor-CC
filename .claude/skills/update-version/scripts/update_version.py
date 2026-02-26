#!/usr/bin/env python3
"""
Doc Advisor Version Update Script

Updates version numbers across all project files.
Handles both source files (with hardcoded versions) and templates (with placeholders).

Usage:
    python3 update_version.py NEW_VERSION [--dry-run]

Examples:
    python3 update_version.py 3.4            # Update to version 3.4
    python3 update_version.py 3.4 --dry-run  # Preview changes without applying
"""

import argparse
import re
import sys
from pathlib import Path


def get_project_root(specified_root: str = None) -> Path:
    """Get the project root directory (where setup.sh is located).

    Args:
        specified_root: If provided, use this as the project root.
                       Otherwise, auto-detect from script location.
    """
    if specified_root:
        root = Path(specified_root).resolve()
        if (root / "setup.sh").exists():
            return root
        raise RuntimeError(f"setup.sh not found in specified root: {specified_root}")

    # Start from script location and go up to find setup.sh
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "setup.sh").exists():
            return parent

    # Also try current working directory
    cwd = Path.cwd()
    if (cwd / "setup.sh").exists():
        return cwd

    raise RuntimeError("Could not find project root (setup.sh not found). Use --project-root option.")


def validate_version(version: str) -> bool:
    """Validate version format (e.g., 3.3, 3.4, 4.0)."""
    return bool(re.match(r'^\d+\.\d+$', version))


def get_current_version(project_root: Path) -> str:
    """Extract current version from setup.sh."""
    setup_sh = project_root / "setup.sh"
    content = setup_sh.read_text()

    match = re.search(r'DOC_ADVISOR_VERSION="(\d+\.\d+)"', content)
    if match:
        return match.group(1)
    raise RuntimeError("Could not find DOC_ADVISOR_VERSION in setup.sh")


def update_file(filepath: Path, patterns: list, dry_run: bool) -> list:
    """
    Update version patterns in a file.

    Args:
        filepath: Path to the file
        patterns: List of (old_pattern, new_replacement) tuples
        dry_run: If True, only report changes without applying

    Returns:
        List of changes made (tuples of (line_num, old_line, new_line))
    """
    if not filepath.exists():
        return []

    content = filepath.read_text()
    original_content = content
    changes = []

    for old_pattern, new_replacement in patterns:
        # Find all matches before replacement for reporting
        for match in re.finditer(old_pattern, content):
            # Get line number
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            if line_end == -1:
                line_end = len(content)
            line_num = content[:match.start()].count('\n') + 1
            old_line = content[line_start:line_end]

            # Perform replacement for this specific match
            new_line = old_line.replace(match.group(0),
                                        re.sub(old_pattern, new_replacement, match.group(0)))
            if old_line != new_line:
                changes.append((line_num, old_line.strip(), new_line.strip()))

        # Apply replacement
        content = re.sub(old_pattern, new_replacement, content)

    if content != original_content and not dry_run:
        filepath.write_text(content)

    return changes


def update_setup_sh(project_root: Path, old_version: str, new_version: str, dry_run: bool) -> list:
    """Update version in setup.sh."""
    filepath = project_root / "setup.sh"
    patterns = [
        # DOC_ADVISOR_VERSION="3.3"
        (rf'DOC_ADVISOR_VERSION="{re.escape(old_version)}"',
         f'DOC_ADVISOR_VERSION="{new_version}"'),
    ]
    return update_file(filepath, patterns, dry_run)




def update_changelog(project_root: Path, old_version: str, new_version: str, dry_run: bool) -> list:
    """
    Add new version section to CHANGELOG.md.
    Note: Only adds placeholder section. Actual changes should be documented manually.
    """
    filepath = project_root / "CHANGELOG.md"
    if not filepath.exists():
        return []

    content = filepath.read_text()

    # Check if new version already exists
    if f"## [{new_version}.0]" in content:
        return []

    # Find the position after the header and insert new section
    # Look for the first "## [" after the header
    match = re.search(r'\n(## \[\d+\.\d+\.\d+\])', content)
    if not match:
        return []

    from datetime import date
    today = date.today().isoformat()

    new_section = f"""
## [{new_version}.0] - {today}

### Added
- (記入してください / To be documented)

### Changed
- **Version identifier**: Updated from `{old_version}` to `{new_version}` across all managed files

### Fixed
- (該当があれば記入 / Document if applicable)

---
"""

    insert_pos = match.start() + 1
    new_content = content[:insert_pos] + new_section + content[insert_pos:]

    if not dry_run:
        filepath.write_text(new_content)

    return [(0, "(new section)", f"## [{new_version}.0] - {today}")]


def update_version_comparison_table(project_root: Path, old_version: str, new_version: str, dry_run: bool) -> list:
    """Update version comparison table in CHANGELOG.md."""
    filepath = project_root / "CHANGELOG.md"
    if not filepath.exists():
        return []

    content = filepath.read_text()
    changes = []

    # Find the version comparison table and add new column
    # Pattern: | Feature | v1.x | v2.0 | v3.0 | v3.1 | v3.2 |
    header_pattern = rf'(\| Feature .* v{re.escape(old_version)} \|)'
    header_match = re.search(header_pattern, content)

    if header_match:
        old_header = header_match.group(1)
        new_header = old_header.rstrip(' |') + f' v{new_version} |'
        changes.append((0, old_header, new_header))

        if not dry_run:
            content = content.replace(old_header, new_header)

    # Update separator line
    sep_pattern = rf'(\|[-]+\|.* \|)'
    for match in re.finditer(sep_pattern, content):
        old_sep = match.group(1)
        if f'v{old_version}' in content[max(0, match.start()-200):match.start()]:
            # This is likely the table we want
            new_sep = old_sep.rstrip(' |') + '------|'
            if old_sep != new_sep:
                changes.append((0, old_sep[:50] + "...", new_sep[:50] + "..."))
                if not dry_run:
                    content = content.replace(old_sep, new_sep, 1)
            break

    # Update data rows in the comparison table
    # Pattern: | Installation | Plugin mode | Project-based | ... | Project-based |
    table_row_pattern = rf'(\| [^|]+ \|(?:[^|]+\|)+) Project-based \|(\n)'

    # Find all rows that end with "Project-based |" and add another column
    for match in re.finditer(table_row_pattern, content):
        old_row = match.group(0)
        # Add new column with same value as last
        last_value = re.search(r'\| ([^|]+) \|$', old_row.strip())
        if last_value:
            value = last_value.group(1).strip()
            new_row = old_row.rstrip('\n').rstrip(' |') + f' {value} |\n'
            if old_row != new_row:
                if not dry_run:
                    content = content.replace(old_row, new_row, 1)

    if not dry_run and changes:
        filepath.write_text(content)

    return changes


def main():
    parser = argparse.ArgumentParser(
        description='Update Doc Advisor version across all files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 update_version.py 3.4            # Update to version 3.4
    python3 update_version.py 3.4 --dry-run  # Preview changes without applying
        """
    )
    parser.add_argument('new_version', help='New version number (e.g., 3.4)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without applying them')
    parser.add_argument('--project-root', '-r',
                       help='Project root directory (auto-detected if not specified)')

    args = parser.parse_args()

    if not validate_version(args.new_version):
        print(f"Error: Invalid version format '{args.new_version}'. Expected format: X.Y (e.g., 3.4)")
        sys.exit(1)

    try:
        project_root = get_project_root(args.project_root)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        current_version = get_current_version(project_root)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if current_version == args.new_version:
        print(f"Version is already {args.new_version}. No changes needed.")
        sys.exit(0)

    print(f"Updating version: {current_version} → {args.new_version}")
    if args.dry_run:
        print("(DRY RUN - no files will be modified)")
    print()

    all_changes = {}

    # Update setup.sh (single source of truth)
    changes = update_setup_sh(project_root, current_version, args.new_version, args.dry_run)
    if changes:
        all_changes["setup.sh"] = changes

    # Update CHANGELOG
    changes = update_changelog(project_root, current_version, args.new_version, args.dry_run)
    if changes:
        all_changes["CHANGELOG.md (new section)"] = changes

    # Report changes
    if all_changes:
        print("Changes:")
        for filename, changes in all_changes.items():
            print(f"\n  {filename}:")
            for line_num, old, new in changes:
                if line_num > 0:
                    print(f"    L{line_num}: {old}")
                    print(f"      → {new}")
                else:
                    print(f"    {old}")
                    print(f"      → {new}")

        print()
        if args.dry_run:
            print("Run without --dry-run to apply changes.")
        else:
            print("Version updated successfully.")
            print()
            print("Next steps:")
            print("  1. Review changes in CHANGELOG.md and document actual changes")
            print("  2. Run tests: cd tests && ./run_all_tests.sh")
            print("  3. Commit changes")
    else:
        print("No changes needed.")


if __name__ == '__main__':
    main()
