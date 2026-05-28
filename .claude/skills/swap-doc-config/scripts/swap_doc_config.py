#!/usr/bin/env python3
"""
Swap `.doc_structure.yaml` with a target file for the duration of a workflow.

Usage:
    swap_doc_config.py --store   --target <yaml> --backup-dir <dir>
    swap_doc_config.py --restore --backup-dir <dir>

`--store`:
    1. Back up current `<project_root>/.doc_structure.yaml` into `<backup-dir>/`
    2. Copy `<target>` to `<project_root>/.doc_structure.yaml`

`--restore`:
    1. Restore the backed-up file from `<backup-dir>/` to project root
    2. Remove `<backup-dir>/`

`--backup-dir` が既に存在する場合は `--store` を拒否する。これは前回の
`--store` 後に `--restore` を呼び忘れた状態 — そのまま新たな `--store` を
許すと、本物の元ファイルのバックアップを上書きで永久に失う。安全に
復旧するには先に `--restore` を実行すること（または backup-dir の内容を
手動で確認）。--force のような上書き手段は意図的に提供しない。

Run from: project root (or set `CLAUDE_PROJECT_DIR`).
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


BACKUP_TARGETS = [".doc_structure.yaml"]


def get_project_root() -> Path:
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
    return Path.cwd()


def store(project_root: Path, target: Path, backup_dir: Path) -> int:
    if not target.exists():
        print(json.dumps({
            "status": "error",
            "message": f"--target not found: {target}",
        }))
        return 1

    if backup_dir.exists():
        # 既存 backup を上書きすると、前回の --store で退避した本物の元ファイルを
        # 永久に失う。意図的に拒否し、ユーザーに --restore を促す（--force は提供しない）。
        print(json.dumps({
            "status": "error",
            "message": (
                f"Backup already exists at {backup_dir}. "
                "Run --restore first to recover the previous original, "
                "or inspect the directory manually. Overwrite is not supported."
            ),
        }))
        return 1

    backup_dir.mkdir(parents=True)

    backed_up = []
    for rel_path in BACKUP_TARGETS:
        src = project_root / rel_path
        if src.exists():
            dst = backup_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            backed_up.append(rel_path)

    shutil.copy2(target, project_root / ".doc_structure.yaml")

    print(json.dumps({
        "status": "ok",
        "action": "store",
        "backed_up": backed_up,
        "doc_structure_replaced": True,
        "backup_dir": str(backup_dir),
    }))
    return 0


def restore(project_root: Path, backup_dir: Path) -> int:
    if not backup_dir.exists():
        print(json.dumps({
            "status": "error",
            "message": f"No backup found at {backup_dir}. Nothing to restore.",
        }))
        return 1

    restored = []
    missing_in_backup = []
    for rel_path in BACKUP_TARGETS:
        backup_file = backup_dir / rel_path
        dst = project_root / rel_path
        if backup_file.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, dst)
            restored.append(rel_path)
        else:
            # 元の project_root に元ファイルが存在しなかった場合、
            # store 時にバックアップが作られていない。restore 時には
            # project_root 側のファイルも消す（store 直前の状態へ戻す）。
            if dst.exists():
                dst.unlink()
            missing_in_backup.append(rel_path)

    shutil.rmtree(backup_dir)

    print(json.dumps({
        "status": "ok",
        "action": "restore",
        "restored": restored,
        "removed_unbacked": missing_in_backup,
        "backup_removed": True,
    }))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Swap .doc_structure.yaml with a target file (store/restore)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--store",
        action="store_true",
        help="Back up current config and replace with --target",
    )
    group.add_argument(
        "--restore",
        action="store_true",
        help="Restore previously backed-up config",
    )
    parser.add_argument(
        "--target",
        help="YAML file to copy into project root as .doc_structure.yaml (required for --store)",
    )
    parser.add_argument(
        "--backup-dir",
        required=True,
        help="Directory to store/restore the backup from",
    )
    args = parser.parse_args()

    if args.store and not args.target:
        parser.error("--target is required when using --store")

    return args


def main() -> int:
    args = parse_args()
    project_root = get_project_root()
    backup_dir = Path(args.backup_dir).resolve()

    if args.store:
        target = Path(args.target).resolve()
        return store(project_root, target, backup_dir)
    return restore(project_root, backup_dir)


if __name__ == "__main__":
    sys.exit(main())
