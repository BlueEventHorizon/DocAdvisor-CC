#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# doc-advisor-version-xK9XmQ: {{DOC_ADVISOR_VERSION}}
"""
External Sources Synchronization Script

Syncs external document sources defined in config.yaml to
.claude/doc-advisor/docs/ via git submodule or local symlink.

Usage:
    python3 .claude/doc-advisor/scripts/sync_external_sources.py [options]

Options:
    (none)      Sync all external sources (add new / update existing)
    --force     Force re-add even if source already exists
    --status    Show current external source status only
    --cleanup   Remove orphaned sources not in config

Run from: Project root
"""

import os
import sys
import subprocess
from pathlib import Path

from toc_utils import get_project_root, find_config_file

# Valid categories for external sources
VALID_CATEGORIES = ('rules', 'requirements', 'design')

# Global configuration (initialized in init_config())
PROJECT_ROOT = None
DOCS_DIR = None
SUBMODULES_DIR = None
CONFIG_PATH = None


# =============================================================================
# Configuration parser
# =============================================================================

def parse_external_sources(config_path):
    """
    Parse external_sources section from config.yaml.

    Handles YAML list-of-dicts syntax that _parse_config_yaml() cannot:
        external_sources:
          rules:
            - name: org-standards
              type: git
              url: https://...

    Args:
        config_path: Path to config.yaml

    Returns:
        dict: {category: [source_dict, ...]}
              e.g. {'rules': [{'name': 'org-standards', 'type': 'git', ...}]}
              Returns empty dict if no external_sources section found.
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    result = {}
    in_external = False
    current_category = None
    current_source = None

    for line in lines:
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())

        # Detect external_sources: section (indent 0)
        if indent == 0 and stripped == 'external_sources:':
            in_external = True
            continue

        if not in_external:
            continue

        # Exit external_sources when indent returns to 0
        if indent == 0:
            break

        # Category level (indent 2): "rules:", "requirements:", "design:"
        if indent == 2 and stripped.endswith(':') and not stripped.startswith('-'):
            current_category = stripped[:-1].strip()
            result[current_category] = []
            current_source = None
            continue

        # List item start (indent 4): "- name: org-standards"
        if indent == 4 and stripped.startswith('- ') and current_category is not None:
            current_source = {}
            result[current_category].append(current_source)
            # Parse key-value on the same line as '-'
            kv = stripped[2:].strip()
            if ':' in kv:
                key, _, value = kv.partition(':')
                current_source[key.strip()] = value.strip()
            continue

        # Continuation of list item (indent 6): "  type: git"
        if indent == 6 and current_source is not None and ':' in stripped:
            key, _, value = stripped.partition(':')
            current_source[key.strip()] = value.strip()
            continue

    return result


def validate_source(source, category):
    """
    Validate a single source entry.

    Args:
        source: dict with name, type, url/path, etc.
        category: Category name

    Returns:
        tuple: (is_valid: bool, errors: list[str])
    """
    errors = []

    name = source.get('name', '').strip()
    if not name:
        errors.append("'name' is required")

    source_type = source.get('type', '').strip()
    if source_type not in ('git', 'local'):
        errors.append(f"'type' must be 'git' or 'local', got '{source_type}'")

    if source_type == 'git':
        url = source.get('url', '').strip()
        if not url:
            errors.append("'url' is required for git type")
    elif source_type == 'local':
        path = source.get('path', '').strip()
        if not path:
            errors.append("'path' is required for local type")

    if category not in VALID_CATEGORIES:
        errors.append(f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}")

    return (len(errors) == 0, errors)


# =============================================================================
# Git submodule operations
# =============================================================================

def run_git_command(args, cwd=None):
    """
    Run a git command and return (returncode, stdout, stderr).

    Args:
        args: list of command arguments (without 'git')
        cwd: working directory (defaults to PROJECT_ROOT)

    Returns:
        tuple: (returncode, stdout, stderr)
    """
    cmd = ['git'] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd or PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (1, '', 'Git command timed out after 120 seconds')
    except FileNotFoundError:
        return (1, '', 'git command not found')


def is_submodule_registered(target_path):
    """
    Check if a path is already registered as a git submodule.

    Args:
        target_path: relative path from project root

    Returns:
        bool
    """
    rc, stdout, _ = run_git_command(
        ['config', '--file', '.gitmodules', '--get-regexp', r'submodule\..*\.path']
    )
    if rc != 0:
        return False

    target = str(target_path).rstrip('/')
    for line in stdout.strip().split('\n'):
        if not line.strip():
            continue
        # Format: "submodule.NAME.path VALUE"
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].rstrip('/') == target:
            return True
    return False


def add_git_submodule(url, target_path, branch=None):
    """
    Add a new git submodule.

    Args:
        url: git repository URL
        target_path: relative path for the submodule
        branch: optional branch name

    Returns:
        tuple: (success: bool, message: str)
    """
    args = ['submodule', 'add']
    if branch:
        args.extend(['--branch', branch])
    args.extend([url, str(target_path)])

    rc, stdout, stderr = run_git_command(args)
    if rc != 0:
        return (False, f"git submodule add failed: {stderr.strip()}")
    return (True, f"Added submodule: {target_path}")


def update_git_submodule(target_path):
    """
    Update existing git submodule to latest remote.

    Args:
        target_path: relative path of the submodule

    Returns:
        tuple: (success: bool, message: str)
    """
    rc, stdout, stderr = run_git_command(
        ['submodule', 'update', '--remote', str(target_path)]
    )
    if rc != 0:
        return (False, f"git submodule update failed: {stderr.strip()}")
    return (True, f"Updated submodule: {target_path}")


def remove_git_submodule(target_path):
    """
    Remove a git submodule.

    Args:
        target_path: relative path of the submodule

    Returns:
        tuple: (success: bool, message: str)
    """
    # Step 1: deinit
    rc, _, stderr = run_git_command(['submodule', 'deinit', '-f', str(target_path)])
    if rc != 0:
        return (False, f"git submodule deinit failed: {stderr.strip()}")

    # Step 2: remove from index
    rc, _, stderr = run_git_command(['rm', '-f', str(target_path)])
    if rc != 0:
        return (False, f"git rm failed: {stderr.strip()}")

    # Step 3: remove .git/modules entry
    modules_path = PROJECT_ROOT / '.git' / 'modules' / target_path
    if modules_path.exists():
        import shutil
        shutil.rmtree(modules_path, ignore_errors=True)

    return (True, f"Removed submodule: {target_path}")


# =============================================================================
# Symlink operations
# =============================================================================

def create_symlink(source_path, link_path):
    """
    Create a symlink, handling existing links.

    Args:
        source_path: path to source (absolute or relative)
        link_path: absolute path for the symlink

    Returns:
        tuple: (success: bool, message: str)
    """
    link_path = Path(link_path)

    if link_path.is_symlink():
        current_target = os.readlink(str(link_path))
        if str(current_target) == str(source_path):
            return (True, f"Symlink already exists: {link_path.name}")
        # Remove old symlink and create new one
        link_path.unlink()

    if link_path.exists():
        return (False, f"Path already exists and is not a symlink: {link_path}")

    # Ensure parent directory exists
    link_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.symlink(str(source_path), str(link_path))
        return (True, f"Created symlink: {link_path.name} → {source_path}")
    except OSError as e:
        return (False, f"Failed to create symlink: {e}")


# =============================================================================
# Source sync logic
# =============================================================================

class SyncResult:
    """Result of a single source sync operation."""

    def __init__(self, name, category, source_type, success, message, action):
        self.name = name
        self.category = category
        self.source_type = source_type  # 'git' or 'local'
        self.success = success
        self.message = message
        self.action = action  # 'added', 'updated', 'skipped', 'failed'

    def __str__(self):
        status = "OK" if self.success else "FAIL"
        return f"  [{status}] {self.category}/{self.name} ({self.source_type}): {self.message}"


def sync_git_source(source, category, force=False):
    """
    Sync a single git-type external source.

    If sparse_path is set:
        - submodule → .submodules/{name}/
        - symlink docs/{category}/{name} → .submodules/{name}/{sparse_path}
    If no sparse_path:
        - submodule → docs/{category}/{name}/

    Args:
        source: source config dict
        category: document category
        force: force re-add

    Returns:
        SyncResult
    """
    name = source['name']
    url = source['url']
    branch = source.get('branch', '').strip() or None
    sparse_path = source.get('sparse_path', '').strip().rstrip('/') or None

    if sparse_path:
        # Submodule goes to .submodules/{name}
        submodule_rel = Path('.claude/doc-advisor/.submodules') / name
        submodule_abs = PROJECT_ROOT / submodule_rel
        # Symlink from docs/{category}/{name}
        link_abs = DOCS_DIR / category / name
    else:
        # Submodule goes directly to docs/{category}/{name}
        submodule_rel = Path('.claude/doc-advisor/docs') / category / name
        submodule_abs = PROJECT_ROOT / submodule_rel
        link_abs = None  # No symlink needed

    already_registered = is_submodule_registered(submodule_rel)

    if already_registered and not force:
        # Update existing submodule
        success, msg = update_git_submodule(submodule_rel)
        if not success:
            return SyncResult(name, category, 'git', False, msg, 'failed')

        # Ensure symlink for sparse_path
        if sparse_path and link_abs:
            rel_target = os.path.relpath(
                str(submodule_abs / sparse_path),
                str(link_abs.parent)
            )
            create_symlink(rel_target, link_abs)

        return SyncResult(name, category, 'git', True, f"Updated: {url}", 'updated')

    if already_registered and force:
        # Remove and re-add
        remove_git_submodule(submodule_rel)

    # Add new submodule
    success, msg = add_git_submodule(url, submodule_rel, branch)
    if not success:
        return SyncResult(name, category, 'git', False, msg, 'failed')

    # Create symlink for sparse_path
    if sparse_path and link_abs:
        rel_target = os.path.relpath(
            str(submodule_abs / sparse_path),
            str(link_abs.parent)
        )
        sym_ok, sym_msg = create_symlink(rel_target, link_abs)
        if not sym_ok:
            return SyncResult(name, category, 'git', False, sym_msg, 'failed')

    return SyncResult(name, category, 'git', True, f"Added: {url}", 'added')


def sync_local_source(source, category):
    """
    Sync a single local-type external source.

    Creates symlink from docs/{category}/{name} to the local path.

    Args:
        source: source config dict
        category: document category

    Returns:
        SyncResult
    """
    name = source['name']
    source_path = source['path']
    link_abs = DOCS_DIR / category / name

    # Verify source directory exists
    source_abs = Path(source_path).expanduser()
    if not source_abs.is_absolute():
        source_abs = PROJECT_ROOT / source_abs

    if not source_abs.exists():
        return SyncResult(
            name, category, 'local', False,
            f"Source path does not exist: {source_abs}", 'failed'
        )

    # Check if symlink already exists and points to same target
    if link_abs.is_symlink():
        current = Path(os.readlink(str(link_abs)))
        if current.is_absolute():
            current_resolved = current
        else:
            current_resolved = (link_abs.parent / current).resolve()

        if current_resolved == source_abs.resolve():
            return SyncResult(
                name, category, 'local', True,
                f"Already linked: {source_path}", 'skipped'
            )

    success, msg = create_symlink(str(source_abs), link_abs)
    if not success:
        return SyncResult(name, category, 'local', False, msg, 'failed')

    return SyncResult(name, category, 'local', True, f"Linked: {source_path}", 'added')


# =============================================================================
# link_list.md generation
# =============================================================================

def detect_primary_links(docs_dir):
    """
    Detect existing primary symlinks (created by setup.sh).

    Returns:
        dict: {category: [{name, type, source}, ...]}
    """
    primary = {}
    for category in VALID_CATEGORIES:
        cat_dir = docs_dir / category
        if not cat_dir.is_dir():
            continue
        primary[category] = []
        for item in sorted(cat_dir.iterdir()):
            if item.is_symlink():
                target = os.readlink(str(item))
                # Primary links use relative paths like ../../../../rules
                if target.startswith('../../../../') or target.startswith('../../../'):
                    primary[category].append({
                        'name': item.name,
                        'type': 'symlink',
                        'source': target,
                    })
    return primary


def generate_link_list(docs_dir, external_sources_config, sync_results):
    """
    Generate link_list.md with both primary and external sources.

    Args:
        docs_dir: path to .claude/doc-advisor/docs/
        external_sources_config: parsed external_sources dict
        sync_results: list of SyncResult
    """
    primary = detect_primary_links(docs_dir)
    link_list_path = docs_dir / 'link_list.md'

    lines = [
        '# Document Sources',
        '',
        'Generated by Doc Advisor.',
        '',
    ]

    # Build external sources lookup by category
    external_by_category = {}
    for result in sync_results:
        if result.success:
            if result.category not in external_by_category:
                external_by_category[result.category] = []
            # Find the source config for this result
            for src in external_sources_config.get(result.category, []):
                if src.get('name') == result.name:
                    source_info = src.get('url', '') or src.get('path', '')
                    external_by_category[result.category].append({
                        'name': result.name,
                        'type': f'git-submodule' if result.source_type == 'git' else 'symlink',
                        'source': source_info,
                    })
                    break

    for category in VALID_CATEGORIES:
        entries = primary.get(category, [])
        ext_entries = external_by_category.get(category, [])

        if not entries and not ext_entries:
            continue

        lines.append(f'## {category}')
        lines.append('| Name | Type | Source |')
        lines.append('|------|------|--------|')

        for entry in entries:
            lines.append(f"| {entry['name']} | {entry['type']} | {entry['source']} |")

        for entry in ext_entries:
            lines.append(f"| {entry['name']} | {entry['type']} | {entry['source']} |")

        lines.append('')

    with open(link_list_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# =============================================================================
# Status and cleanup
# =============================================================================

def detect_orphans(docs_dir, submodules_dir, external_sources_config):
    """
    Find sources that exist on disk but not in config.

    Returns:
        list of dict: [{category, name, path, is_submodule}, ...]
    """
    # Collect all configured source names per category
    configured = {}
    for category, sources in external_sources_config.items():
        configured[category] = {s['name'] for s in sources if 'name' in s}

    orphans = []

    # Check docs/{category}/ for non-primary links/dirs
    primary = detect_primary_links(docs_dir)
    primary_names = {}
    for cat, entries in primary.items():
        primary_names[cat] = {e['name'] for e in entries}

    for category in VALID_CATEGORIES:
        cat_dir = docs_dir / category
        if not cat_dir.is_dir():
            continue

        cat_primary = primary_names.get(category, set())
        cat_configured = configured.get(category, set())

        for item in sorted(cat_dir.iterdir()):
            if item.name in cat_primary:
                continue
            if item.name in cat_configured:
                continue
            # This is an orphan
            rel_path = item.relative_to(PROJECT_ROOT)
            is_sub = is_submodule_registered(rel_path) if not item.is_symlink() else False
            orphans.append({
                'category': category,
                'name': item.name,
                'path': str(rel_path),
                'is_submodule': is_sub,
            })

    # Check .submodules/ for orphaned submodules
    if submodules_dir.exists():
        all_sparse_names = set()
        for sources in external_sources_config.values():
            for s in sources:
                if s.get('sparse_path'):
                    all_sparse_names.add(s['name'])

        for item in sorted(submodules_dir.iterdir()):
            if item.name not in all_sparse_names:
                rel_path = item.relative_to(PROJECT_ROOT)
                orphans.append({
                    'category': '.submodules',
                    'name': item.name,
                    'path': str(rel_path),
                    'is_submodule': is_submodule_registered(rel_path),
                })

    return orphans


def show_status(external_sources_config):
    """Show status of all external sources."""
    print("External Sources Status")
    print("=" * 50)

    if not external_sources_config:
        print("\nNo external_sources configured in config.yaml.")

    for category, sources in external_sources_config.items():
        print(f"\n## {category}")
        for source in sources:
            name = source.get('name', '(unnamed)')
            stype = source.get('type', '?')
            url_or_path = source.get('url', '') or source.get('path', '')

            if stype == 'git':
                sparse = source.get('sparse_path', '')
                if sparse:
                    submodule_rel = Path('.claude/doc-advisor/.submodules') / name
                    link_path = DOCS_DIR / category / name
                else:
                    submodule_rel = Path('.claude/doc-advisor/docs') / category / name
                    link_path = None

                sub_exists = is_submodule_registered(submodule_rel)
                sub_path = PROJECT_ROOT / submodule_rel

                if sub_exists and sub_path.exists():
                    status = "synced"
                elif sub_exists:
                    status = "registered but not checked out"
                else:
                    status = "not synced"

                sparse_info = f" (sparse: {sparse})" if sparse else ""
                print(f"  [{status}] {name} (git{sparse_info}): {url_or_path}")

            elif stype == 'local':
                link_path = DOCS_DIR / category / name
                if link_path.is_symlink():
                    if link_path.exists():
                        status = "linked"
                    else:
                        status = "broken link"
                else:
                    status = "not linked"
                print(f"  [{status}] {name} (local): {url_or_path}")

    # Check for orphans
    orphans = detect_orphans(DOCS_DIR, SUBMODULES_DIR, external_sources_config)
    if orphans:
        print(f"\nOrphaned sources (not in config):")
        for o in orphans:
            sub_mark = " [submodule]" if o['is_submodule'] else ""
            print(f"  - {o['category']}/{o['name']}{sub_mark}")
        print("\nRun /sync-docs --cleanup to remove orphans.")


def cleanup_orphans_interactive(external_sources_config):
    """Remove orphaned sources."""
    orphans = detect_orphans(DOCS_DIR, SUBMODULES_DIR, external_sources_config)

    if not orphans:
        print("No orphaned sources found.")
        return

    print(f"Found {len(orphans)} orphaned source(s):")
    for o in orphans:
        sub_mark = " [submodule]" if o['is_submodule'] else ""
        print(f"  - {o['category']}/{o['name']}{sub_mark}: {o['path']}")

    removed = 0
    for o in orphans:
        full_path = PROJECT_ROOT / o['path']
        if o['is_submodule']:
            success, msg = remove_git_submodule(o['path'])
            if success:
                print(f"  Removed submodule: {o['path']}")
                removed += 1
            else:
                print(f"  Failed to remove submodule: {msg}")
        elif full_path.is_symlink():
            full_path.unlink()
            print(f"  Removed symlink: {o['path']}")
            removed += 1
        elif full_path.is_dir():
            import shutil
            shutil.rmtree(full_path, ignore_errors=True)
            print(f"  Removed directory: {o['path']}")
            removed += 1

    print(f"\nRemoved {removed}/{len(orphans)} orphan(s).")


# =============================================================================
# Main
# =============================================================================

def init_config():
    """
    Initialize configuration.

    Returns:
        bool: True on success, False on failure
    """
    global PROJECT_ROOT, DOCS_DIR, SUBMODULES_DIR, CONFIG_PATH

    try:
        PROJECT_ROOT = get_project_root()
        CONFIG_PATH = find_config_file()
    except RuntimeError as e:
        print(f"Error: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    DOCS_DIR = PROJECT_ROOT / '.claude' / 'doc-advisor' / 'docs'
    SUBMODULES_DIR = PROJECT_ROOT / '.claude' / 'doc-advisor' / '.submodules'

    return True


def main():
    """
    Main entry point.

    Flow:
    1. Parse arguments (--force, --status, --cleanup)
    2. Load config and parse external_sources
    3. If --status: show status and exit
    4. For each source in each category:
       a. Validate entry
       b. Sync (git submodule or symlink)
       c. Record result
    5. Update link_list.md
    6. If --cleanup: remove orphans
    7. Print summary
    """
    if not init_config():
        sys.exit(1)

    # Parse arguments
    args = sys.argv[1:]
    force = '--force' in args
    status_only = '--status' in args
    cleanup = '--cleanup' in args

    # Parse external sources from config
    external_sources = parse_external_sources(CONFIG_PATH)

    # --status mode
    if status_only:
        show_status(external_sources)
        sys.exit(0)

    # --cleanup mode
    if cleanup:
        cleanup_orphans_interactive(external_sources)
        sys.exit(0)

    # Sync mode
    if not external_sources:
        print("No external_sources configured in config.yaml.")
        print("Add sources to the external_sources section and run again.")
        print("See config.yaml for example format.")
        sys.exit(0)

    print("Syncing external sources...")
    print("=" * 50)

    results = []
    git_changes = False

    for category, sources in external_sources.items():
        for source in sources:
            # Validate
            valid, errors = validate_source(source, category)
            if not valid:
                name = source.get('name', '(unnamed)')
                msg = '; '.join(errors)
                results.append(SyncResult(name, category, '?', False, msg, 'failed'))
                print(f"  [FAIL] {category}/{name}: {msg}")
                continue

            source_type = source['type']

            if source_type == 'git':
                result = sync_git_source(source, category, force=force)
            elif source_type == 'local':
                result = sync_local_source(source, category)
            else:
                result = SyncResult(
                    source['name'], category, source_type,
                    False, f"Unknown type: {source_type}", 'failed'
                )

            results.append(result)
            print(str(result))

            if result.success and result.source_type == 'git' and result.action in ('added', 'updated'):
                git_changes = True

    # Update link_list.md
    print("")
    generate_link_list(DOCS_DIR, external_sources, results)
    print("Updated: link_list.md")

    # Check for orphans
    orphans = detect_orphans(DOCS_DIR, SUBMODULES_DIR, external_sources)
    if orphans:
        print(f"\nWarning: {len(orphans)} orphaned source(s) found:")
        for o in orphans:
            print(f"  - {o['category']}/{o['name']}")
        print("Run /sync-docs --cleanup to remove them.")

    # Summary
    added = sum(1 for r in results if r.action == 'added')
    updated = sum(1 for r in results if r.action == 'updated')
    skipped = sum(1 for r in results if r.action == 'skipped')
    failed = sum(1 for r in results if r.action == 'failed')

    print("")
    print("=" * 50)
    print(f"Summary: {added} added, {updated} updated, {skipped} skipped, {failed} failed")

    if git_changes:
        print("")
        print("Git submodules were modified. Please commit the changes:")
        print("  git add .gitmodules .claude/doc-advisor/")
        print("  git commit -m 'Add external document sources'")

    if added > 0 or updated > 0:
        print("")
        print("Regenerate ToC to index new documents:")
        print("  /create-rules-toc --full")
        print("  /create-specs-toc --full")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
