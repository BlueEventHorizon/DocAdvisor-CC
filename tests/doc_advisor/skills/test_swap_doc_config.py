#!/usr/bin/env python3
"""
swap-doc-config SKILL の CLI E2E テスト。

SKILL の境界（CLI）に対してテストする。内部関数 import は行わない。
tmpdir を擬似プロジェクトルート (CLAUDE_PROJECT_DIR) として隔離するため、
実 repo の .doc_structure.yaml には一切影響しない。

検証対象:
- --store: バックアップ作成と .doc_structure.yaml 置換
- --restore: バックアップからの復元とバックアップディレクトリ削除
- 異常系: --target 不在、--backup-dir 既存（=restore 忘れ）、--restore 時バックアップ不在
- 安全性: 既存バックアップは絶対に上書きされない（--force のような迂回手段が存在しない）
- store → restore サイクル後の bit 単位一致
- project_root に元の .doc_structure.yaml が存在しないケースの正しい復元
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SWAP_SCRIPT = REPO_ROOT / ".claude" / "skills" / "swap-doc-config" / "scripts" / "swap_doc_config.py"

# /tmp 不可環境のためプロジェクト内に temp ベースを置く（既存ルール踏襲）
TEMP_BASE = Path(__file__).resolve().parent / ".temp"


class SwapDocConfigBase(unittest.TestCase):
    """擬似プロジェクトルートを tmpdir に用意し、swap-doc-config を CLI 経由で呼び出す。"""

    def setUp(self):
        TEMP_BASE.mkdir(parents=True, exist_ok=True)
        self.project_root = Path(tempfile.mkdtemp(dir=str(TEMP_BASE)))
        (self.project_root / ".git").mkdir()  # get_project_root() の判定用

        self.backup_dir = self.project_root / ".backup"
        self.original_yaml_text = (
            "# original .doc_structure.yaml\n"
            "rules:\n"
            "  root_dirs:\n"
            "    - docs/rules/\n"
        )
        self.original_yaml_path = self.project_root / ".doc_structure.yaml"
        self.original_yaml_path.write_text(self.original_yaml_text, encoding="utf-8")

        self.target_yaml_text = (
            "# target .doc_structure.yaml\n"
            "rules:\n"
            "  root_dirs:\n"
            "    - other/\n"
        )
        self.target_yaml_path = self.project_root / "target.yaml"
        self.target_yaml_path.write_text(self.target_yaml_text, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def _swap(self, *args):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.project_root)}
        return subprocess.run(
            [sys.executable, str(SWAP_SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(self.project_root),
            env=env,
        )


class TestStore(SwapDocConfigBase):
    """--store の挙動。"""

    def test_store_creates_backup_and_replaces_config(self):
        result = self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["action"], "store")
        self.assertIn(".doc_structure.yaml", payload["backed_up"])

        # 1) project_root の .doc_structure.yaml が target の内容で置換されている
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.target_yaml_text,
        )

        # 2) backup_dir に元の内容がバイト単位で保存されている
        backup_file = self.backup_dir / ".doc_structure.yaml"
        self.assertTrue(backup_file.exists())
        self.assertEqual(backup_file.read_text(encoding="utf-8"), self.original_yaml_text)

    def test_store_when_target_missing_returns_error(self):
        missing_target = self.project_root / "does_not_exist.yaml"
        result = self._swap(
            "--store",
            "--target", str(missing_target),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("--target not found", payload["message"])
        # 元の .doc_structure.yaml は破壊されていない
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.original_yaml_text,
        )
        # backup_dir は作成されていない
        self.assertFalse(self.backup_dir.exists())

    def test_store_when_backup_dir_exists_returns_error(self):
        """既存 backup_dir がある状態での --store は **必ず** 拒否される。

        これは「前回 --restore し忘れ」状態の可能性があり、上書きすると
        本物の元 .doc_structure.yaml バックアップを永久に失う。
        """
        # 既存 backup_dir
        self.backup_dir.mkdir()
        (self.backup_dir / "dummy.txt").write_text("preexisting", encoding="utf-8")

        result = self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("Backup already exists", payload["message"])
        # 元の .doc_structure.yaml は破壊されていない
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.original_yaml_text,
        )
        # 既存 backup_dir の内容も破壊されていない
        self.assertEqual(
            (self.backup_dir / "dummy.txt").read_text(encoding="utf-8"),
            "preexisting",
        )

    def test_no_force_option_exists(self):
        """--force は意図的に提供しない（既存バックアップを上書きする手段を作らない）。

        argparse が unknown arg として弾けば設計どおり。
        """
        result = self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
            "--force",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--force", result.stderr)

    def test_store_without_target_argument_errors(self):
        """--store 時に --target を省略すると argparse がエラーを返す。"""
        result = self._swap("--store", "--backup-dir", str(self.backup_dir))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target", result.stderr)

    def test_store_when_no_original_doc_structure(self):
        """project_root に .doc_structure.yaml が無くても --store は成功する。

        backed_up は空配列、置換は実行される。
        """
        self.original_yaml_path.unlink()
        result = self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["backed_up"], [])
        # target の内容が project_root に配置されている
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.target_yaml_text,
        )
        # backup_dir は作成される（中身は空）
        self.assertTrue(self.backup_dir.exists())
        self.assertFalse((self.backup_dir / ".doc_structure.yaml").exists())


class TestRestore(SwapDocConfigBase):
    """--restore の挙動。"""

    def _store(self):
        return self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )

    def test_restore_recovers_original_content(self):
        self.assertEqual(self._store().returncode, 0)
        # store 後は target 内容に置換されている
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.target_yaml_text,
        )

        result = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["action"], "restore")
        self.assertIn(".doc_structure.yaml", payload["restored"])

        # 元の内容に戻っている
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.original_yaml_text,
        )
        # backup_dir は削除されている
        self.assertFalse(self.backup_dir.exists())

    def test_restore_when_no_backup_returns_error(self):
        # store なしでいきなり restore
        result = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("No backup found", payload["message"])
        # .doc_structure.yaml は不変
        self.assertEqual(
            self.original_yaml_path.read_text(encoding="utf-8"),
            self.original_yaml_text,
        )

    def test_restore_after_no_original_removes_project_file(self):
        """元々 .doc_structure.yaml が無かったケースで restore すると、
        store 後の差し替えファイルも消えて元の「ファイル無し」状態へ戻る。
        """
        self.original_yaml_path.unlink()
        self.assertEqual(self._store().returncode, 0)
        # store 後は target 内容が配置されている
        self.assertTrue(self.original_yaml_path.exists())

        result = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn(".doc_structure.yaml", payload["removed_unbacked"])

        # 元の「ファイル無し」状態に戻る
        self.assertFalse(self.original_yaml_path.exists())
        self.assertFalse(self.backup_dir.exists())


class TestStoreRestoreCycle(SwapDocConfigBase):
    """store → restore のサイクル一貫性。"""

    def test_byte_identical_after_cycle(self):
        # マルチバイト・改行を含む現実的な YAML
        rich_yaml = (
            "# doc_structure_version: 3.0\n"
            "# 日本語コメントとマルチバイト文字 ✓ を含む\n"
            "rules:\n"
            "  root_dirs:\n"
            '    - "docs/rules with spaces/"\n'
            "  doc_types_map:\n"
            '    "docs/rules with spaces/": rule\n'
            "  patterns:\n"
            "    target_glob: \"**/*.md\"\n"
            "    exclude: []\n"
        )
        self.original_yaml_path.write_text(rich_yaml, encoding="utf-8")
        original_bytes = self.original_yaml_path.read_bytes()

        # store
        r1 = self._swap(
            "--store",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)

        # restore
        r2 = self._swap("--restore", "--backup-dir", str(self.backup_dir))
        self.assertEqual(r2.returncode, 0, r2.stderr)

        # バイト単位で完全一致
        self.assertEqual(self.original_yaml_path.read_bytes(), original_bytes)


class TestMutualExclusion(SwapDocConfigBase):
    """--store と --restore の排他制御。"""

    def test_neither_store_nor_restore_errors(self):
        result = self._swap("--backup-dir", str(self.backup_dir))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--store", result.stderr)
        self.assertIn("--restore", result.stderr)

    def test_both_store_and_restore_errors(self):
        result = self._swap(
            "--store", "--restore",
            "--target", str(self.target_yaml_path),
            "--backup-dir", str(self.backup_dir),
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
