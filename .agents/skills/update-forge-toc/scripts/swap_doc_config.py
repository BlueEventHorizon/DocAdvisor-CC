#!/usr/bin/env python3
"""
Swap .doc_structure.yaml for forge internal ToC generation.

Usage:
    python3 .claude/skills/update-forge-toc/scripts/swap_doc_config.py --store [--force]
    python3 .claude/skills/update-forge-toc/scripts/swap_doc_config.py --restore

--store:
    1. Back up project .doc_structure.yaml
    2. Copy forge_doc_structure.yaml to project root as .doc_structure.yaml

--restore:
    1. Restore all backed-up files to their original locations
    2. Remove backup directory

Run from: Project root
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = SKILL_DIR / ".backup"
FORGE_DOC_STRUCTURE = SKILL_DIR / "forge_doc_structure.yaml"

BACKUP_TARGETS = [
    ".doc_structure.yaml",
]


def get_project_root():
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
    return Path.cwd()


def store(project_root, force=False):
    if BACKUP_DIR.exists():
        if not force:
            print(json.dumps({
                "status": "error",
                "message": f"Backup already exists at {BACKUP_DIR}. Use --force to overwrite, or --restore to recover.",
            }))
            return 1
        shutil.rmtree(BACKUP_DIR)

    BACKUP_DIR.mkdir(parents=True)

    backed_up = []
    for rel_path in BACKUP_TARGETS:
        src = project_root / rel_path
        if src.exists():
            dst = BACKUP_DIR / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            backed_up.append(rel_path)

    if not FORGE_DOC_STRUCTURE.exists():
        shutil.rmtree(BACKUP_DIR)
        print(json.dumps({
            "status": "error",
            "message": f"forge_doc_structure.yaml not found at {FORGE_DOC_STRUCTURE}",
        }))
        return 1

    shutil.copy2(FORGE_DOC_STRUCTURE, project_root / ".doc_structure.yaml")

    print(json.dumps({
        "status": "ok",
        "action": "store",
        "backed_up": backed_up,
        "doc_structure_replaced": True,
        "backup_dir": str(BACKUP_DIR),
    }))
    return 0


def restore(project_root):
    if not BACKUP_DIR.exists():
        print(json.dumps({
            "status": "error",
            "message": f"No backup found at {BACKUP_DIR}. Nothing to restore.",
        }))
        return 1

    restored = []
    for rel_path in BACKUP_TARGETS:
        backup_file = BACKUP_DIR / rel_path
        dst = project_root / rel_path
        if backup_file.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, dst)
            restored.append(rel_path)

    shutil.rmtree(BACKUP_DIR)

    print(json.dumps({
        "status": "ok",
        "action": "restore",
        "restored": restored,
        "backup_removed": True,
    }))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Swap .doc_structure.yaml for forge ToC generation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--store", action="store_true", help="Back up current config and replace with forge config")
    group.add_argument("--restore", action="store_true", help="Restore backed-up config")
    parser.add_argument("--force", action="store_true", help="Overwrite existing backup (with --store)")
    args = parser.parse_args()

    project_root = get_project_root()

    if args.store:
        return store(project_root, force=args.force)
    else:
        return restore(project_root)


if __name__ == "__main__":
    sys.exit(main())
