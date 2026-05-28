#!/usr/bin/env python3
"""
session_manager.py のテスト

セッションディレクトリの作成・検索・削除をテストする。
標準ライブラリのみ使用。

実行:
  python3 -m unittest tests.forge.scripts.test_session_manager -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# テスト対象モジュールへのパスを追加
sys.path.insert(0, str(Path(__file__).resolve().parents[3]
                       / 'plugins' / 'forge' / 'scripts'))

from session_manager import (
    SESSION_FIELD_ORDER,
    TEMP_BASE,
    _parse_iso_ts,
    cmd_cleanup,
    cmd_cleanup_stale,
    cmd_complete,
    cmd_find,
    cmd_init,
    cmd_touch,
    generate_session_name,
    parse_extra_args,
    validate_temp_path,
)
from session.yaml_utils import (
    now_iso,
    read_yaml,
    write_flat_yaml,
    yaml_scalar,
)


class _FsTestCase(unittest.TestCase):
    """ファイルシステムを使うテストの基底クラス"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # TEMP_BASE をテスト用に差し替えるため、ワーキングディレクトリを変更
        self.orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        # .claude/.temp/ を作成
        (self.tmpdir / ".claude" / ".temp").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, rel_path, content=''):
        p = self.tmpdir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p


# =========================================================================
# 1. YAML ユーティリティ
# =========================================================================

class TestYamlValue(unittest.TestCase):
    """yaml_scalar のテスト（yaml_utils に委譲）"""

    def test_string_no_special(self):
        self.assertEqual(yaml_scalar("hello"), "hello")

    def test_string_with_colon(self):
        self.assertEqual(yaml_scalar("key: value"), '"key: value"')

    def test_string_with_space(self):
        self.assertEqual(yaml_scalar("hello world"), '"hello world"')

    def test_integer(self):
        self.assertEqual(yaml_scalar(42), "42")

    def test_bool_true(self):
        self.assertEqual(yaml_scalar(True), "true")

    def test_bool_false(self):
        self.assertEqual(yaml_scalar(False), "false")

    def test_empty_string(self):
        self.assertEqual(yaml_scalar(""), '""')

    def test_string_with_quotes(self):
        result = yaml_scalar('say "hello"')
        self.assertIn('\\"', result)


class TestWriteReadYaml(_FsTestCase):
    """write_flat_yaml / read_yaml の往復テスト"""

    def test_roundtrip_basic(self):
        path = self.tmpdir / "test.yaml"
        data = {"skill": "review", "status": "in_progress", "auto_count": 3}
        write_flat_yaml(path, data, field_order=SESSION_FIELD_ORDER)
        result = read_yaml(path)
        self.assertEqual(result["skill"], "review")
        self.assertEqual(result["status"], "in_progress")
        self.assertEqual(result["auto_count"], 3)

    def test_field_order(self):
        """共通フィールドが先に出力されるか"""
        path = self.tmpdir / "test.yaml"
        data = {
            "feature": "login",
            "skill": "start-design",
            "status": "in_progress",
            "started_at": "2026-03-13T10:00:00Z",
            "last_updated": "2026-03-13T10:00:00Z",
        }
        write_flat_yaml(path, data, field_order=SESSION_FIELD_ORDER)
        content = path.read_text(encoding="utf-8")
        lines = [l for l in content.strip().split("\n") if l]
        # 最初の行は skill
        self.assertTrue(lines[0].startswith("skill:"))
        # feature は共通フィールドの後
        skill_idx = next(i for i, l in enumerate(lines) if l.startswith("skill:"))
        feature_idx = next(i for i, l in enumerate(lines) if l.startswith("feature:"))
        self.assertGreater(feature_idx, skill_idx)

    def test_quoted_values_roundtrip(self):
        """スペース・特殊文字を含む値の往復"""
        path = self.tmpdir / "test.yaml"
        data = {"output_dir": "specs/login/design", "skill": "start-design"}
        write_flat_yaml(path, data, field_order=SESSION_FIELD_ORDER)
        result = read_yaml(path)
        self.assertEqual(result["output_dir"], "specs/login/design")

    def test_comments_ignored(self):
        """コメント行はスキップされる"""
        path = self.tmpdir / "test.yaml"
        path.write_text("# コメント\nskill: review\n# もう一つ\nstatus: in_progress\n",
                        encoding="utf-8")
        result = read_yaml(path)
        self.assertEqual(result["skill"], "review")
        self.assertEqual(result["status"], "in_progress")
        self.assertEqual(len(result), 2)

    def test_integer_roundtrip(self):
        """整数値が正しく往復する"""
        path = self.tmpdir / "test.yaml"
        write_flat_yaml(path, {"auto_count": 0, "skill": "review"},
                        field_order=SESSION_FIELD_ORDER)
        result = read_yaml(path)
        self.assertEqual(result["auto_count"], 0)
        self.assertIsInstance(result["auto_count"], int)


# =========================================================================
# 2. ヘルパー
# =========================================================================

class TestHelpers(unittest.TestCase):
    """ヘルパー関数のテスト"""

    def test_now_iso_format(self):
        ts = now_iso()
        # ISO 8601 + Z 表記
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_generate_session_name_format(self):
        name = generate_session_name("start-design")
        # {skill_name}-{6 hex chars}
        self.assertRegex(name, r"^start-design-[0-9a-f]{6}$")

    def test_generate_session_name_various_skills(self):
        """各スキル名がディレクトリ名に含まれること"""
        for skill in ["review", "start-plan", "start-implement"]:
            name = generate_session_name(skill)
            self.assertTrue(name.startswith(f"{skill}-"))

    def test_generate_session_name_unique(self):
        """連続生成で重複しないこと"""
        names = {generate_session_name("start-design") for _ in range(10)}
        self.assertEqual(len(names), 10)

    def test_parse_extra_args(self):
        remaining = ["--feature", "login", "--mode", "new", "--output-dir", "specs/login"]
        result = parse_extra_args(remaining)
        self.assertEqual(result["feature"], "login")
        self.assertEqual(result["mode"], "new")
        # ハイフンはアンダースコアに変換
        self.assertEqual(result["output_dir"], "specs/login")

    def test_parse_extra_args_integer(self):
        remaining = ["--auto-count", "3"]
        result = parse_extra_args(remaining)
        self.assertEqual(result["auto_count"], 3)
        self.assertIsInstance(result["auto_count"], int)

    def test_parse_iso_ts_z_is_aware(self):
        """Z 表記は aware datetime（tzinfo あり）になる"""
        dt = _parse_iso_ts("2026-01-01T00:00:00Z")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)

    def test_parse_iso_ts_naive_normalized_to_utc(self):
        """tz なし naive 文字列は UTC として aware 化される（#93 レビュー指摘）"""
        dt = _parse_iso_ts("2026-01-01T00:00:00")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.utcoffset().total_seconds(), 0)

    def test_parse_iso_ts_invalid_returns_none(self):
        """パース不能な文字列は None（skipped に分類される）"""
        self.assertIsNone(_parse_iso_ts("not-a-date"))
        self.assertIsNone(_parse_iso_ts(""))
        self.assertIsNone(_parse_iso_ts(None))


class TestValidateTempPath(_FsTestCase):
    """validate_temp_path のテスト"""

    def test_valid_path(self):
        path = os.path.join(TEMP_BASE, "start-design-a3f7b2")
        os.makedirs(path, exist_ok=True)
        self.assertTrue(validate_temp_path(path))

    def test_traversal_rejected(self):
        self.assertFalse(validate_temp_path("../../etc/passwd"))

    def test_outside_temp_rejected(self):
        self.assertFalse(validate_temp_path("/tmp/something"))


# =========================================================================
# 3. cmd_init
# =========================================================================

class TestCmdInit(_FsTestCase):
    """cmd_init のテスト"""

    def _make_args(self, skill):
        """argparse の Namespace を模擬する"""
        class Args:
            pass
        a = Args()
        a.skill = skill
        return a

    def _create_leftover(self, skill, name, hours_ago, status):
        """init 前の残骸セッションを作成する"""
        from datetime import datetime, timedelta, timezone
        session_dir = os.path.join(TEMP_BASE, name)
        os.makedirs(session_dir, exist_ok=True)
        past = (datetime.now(timezone.utc)
                - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {"skill": skill, "started_at": past,
             "last_updated": past, "status": status},
            field_order=SESSION_FIELD_ORDER,
        )
        return session_dir

    def test_creates_directory_and_refs(self):
        result = cmd_init(self._make_args("start-design"), [])
        session_dir = result["session_dir"]
        self.assertTrue(os.path.isdir(session_dir))
        self.assertTrue(os.path.isdir(os.path.join(session_dir, "refs")))

    def test_creates_session_yaml(self):
        result = cmd_init(self._make_args("start-design"), [])
        yaml_path = os.path.join(result["session_dir"], "session.yaml")
        self.assertTrue(os.path.isfile(yaml_path))
        data = read_yaml(yaml_path)
        self.assertEqual(data["skill"], "start-design")
        self.assertEqual(data["status"], "in_progress")

    def test_auto_timestamps(self):
        result = cmd_init(self._make_args("start-design"), [])
        data = read_yaml(os.path.join(result["session_dir"], "session.yaml"))
        self.assertRegex(str(data["started_at"]),
                         r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
        self.assertEqual(data["started_at"], data["last_updated"])

    def test_only_common_fields_by_default(self):
        """進行状態フィールドが session.yaml に書かれないこと"""
        result = cmd_init(self._make_args("review"), [])
        data = read_yaml(os.path.join(result["session_dir"], "session.yaml"))
        for removed in (
            "phase", "phase_status", "focus", "waiting_type",
            "waiting_reason", "active_artifact", "resume_policy",
        ):
            self.assertNotIn(removed, data)

    def test_extra_fields(self):
        """任意の --key value がsession.yaml に含まれる"""
        result = cmd_init(
            self._make_args("start-design"),
            ["--feature", "login", "--mode", "new", "--output-dir", "specs/login"],
        )
        data = read_yaml(os.path.join(result["session_dir"], "session.yaml"))
        self.assertEqual(data["feature"], "login")
        self.assertEqual(data["mode"], "new")
        self.assertEqual(data["output_dir"], "specs/login")

    def test_json_output_structure(self):
        result = cmd_init(self._make_args("start-design"), [])
        self.assertEqual(result["status"], "created")
        self.assertIn("session_dir", result)
        self.assertTrue(result["session_dir"].startswith(TEMP_BASE))

    def test_hyphen_to_underscore(self):
        """--output-dir → output_dir に変換"""
        result = cmd_init(
            self._make_args("start-design"),
            ["--output-dir", "specs/login/design"],
        )
        data = read_yaml(os.path.join(result["session_dir"], "session.yaml"))
        self.assertIn("output_dir", data)
        self.assertNotIn("output-dir", data)

    def test_auto_cleanup_field_present(self):
        """init の戻り値に auto_cleanup フィールドが含まれる（#93）"""
        result = cmd_init(self._make_args("start-design"), [])
        self.assertIn("auto_cleanup", result)
        self.assertIn("deleted", result["auto_cleanup"])
        self.assertIn("skipped", result["auto_cleanup"])

    def test_auto_cleanup_removes_completed_leftover(self):
        """init 時に completed 残骸が全スキル横断で削除される（#93）"""
        leftover = self._create_leftover(
            "start-plan", "start-plan-done", hours_ago=1, status="completed",
        )
        result = cmd_init(self._make_args("review"), [])
        # 他スキルの completed 残骸が回収される
        self.assertFalse(os.path.exists(leftover))
        deleted_paths = [d["path"] for d in result["auto_cleanup"]["deleted"]]
        self.assertIn(leftover, deleted_paths)
        # 新規セッションは作成されている
        self.assertTrue(os.path.isdir(result["session_dir"]))

    def test_auto_cleanup_preserves_in_progress_leftover(self):
        """init 時に古い in_progress 残骸は削除されない（誤削除防止、#93）"""
        leftover = self._create_leftover(
            "start-plan", "start-plan-stale", hours_ago=1000, status="in_progress",
        )
        result = cmd_init(self._make_args("review"), [])
        # 中断中セッションは age に関わらず温存される
        self.assertTrue(os.path.exists(leftover))
        deleted_paths = [d["path"] for d in result["auto_cleanup"]["deleted"]]
        self.assertNotIn(leftover, deleted_paths)

    def test_auto_cleanup_does_not_touch_new_session(self):
        """自動 cleanup は新規作成するセッション自身を削除しない"""
        result = cmd_init(self._make_args("review"), [])
        self.assertTrue(os.path.isdir(result["session_dir"]))
        deleted_paths = [d["path"] for d in result["auto_cleanup"]["deleted"]]
        self.assertNotIn(result["session_dir"], deleted_paths)

    def test_auto_cleanup_handles_naive_timestamp(self):
        """naive(tzなし) timestamp の completed 残骸でも init がクラッシュしない（#93 レビュー指摘）。

        naive datetime と aware な now の減算は TypeError を投げるため、回帰防止する。
        """
        session_dir = os.path.join(TEMP_BASE, "start-plan-naive")
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {"skill": "start-plan",
             "started_at": "2026-01-01T00:00:00",  # tz 情報なし（手書き想定）
             "last_updated": "2026-01-01T00:00:00",
             "status": "completed"},
            field_order=SESSION_FIELD_ORDER,
        )
        result = cmd_init(self._make_args("review"), [])
        self.assertEqual(result["status"], "created")
        # naive completed 残骸を UTC とみなして回収できる
        self.assertFalse(os.path.exists(session_dir))
        deleted_paths = [d["path"] for d in result["auto_cleanup"]["deleted"]]
        self.assertIn(session_dir, deleted_paths)

    def test_auto_cleanup_failure_does_not_block_init(self):
        """自動回収が予期せぬ例外を投げても init は成功する（fail-open 契約、#93 レビュー指摘）"""
        import session_manager
        with mock.patch.object(
            session_manager, "_cleanup_stale_core",
            side_effect=RuntimeError("予期しないエラー"),
        ):
            result = cmd_init(self._make_args("review"), [])
        self.assertEqual(result["status"], "created")
        self.assertTrue(os.path.isdir(result["session_dir"]))
        self.assertIn("error", result["auto_cleanup"])


# =========================================================================
# 4. cmd_find
# =========================================================================

class TestCmdFind(_FsTestCase):
    """cmd_find のテスト"""

    def _make_args(self, skill=None, all_skills=False):
        class Args:
            pass
        a = Args()
        a.skill = skill
        a.all_skills = all_skills
        return a

    def _create_session(self, skill, name=None):
        """テスト用セッションを手動作成する"""
        if name is None:
            name = f"{skill}-aaaaaa"
        session_dir = os.path.join(TEMP_BASE, name)
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {"skill": skill, "started_at": "2026-03-13T18:00:00Z",
             "last_updated": "2026-03-13T18:00:00Z",
             "status": "in_progress"},
            field_order=SESSION_FIELD_ORDER,
        )
        return session_dir

    def test_find_matching(self):
        self._create_session("start-design")
        result = cmd_find(self._make_args(skill="start-design"))
        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["skill"], "start-design")

    def test_find_no_match(self):
        self._create_session("start-design")
        result = cmd_find(self._make_args(skill="review"))
        self.assertEqual(result["status"], "none")

    def test_find_multiple(self):
        self._create_session("start-design", "start-design-aaaaaa")
        self._create_session("start-design", "start-design-bbbbbb")
        result = cmd_find(self._make_args(skill="start-design"))
        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["sessions"]), 2)

    def test_find_ignores_other_skills(self):
        self._create_session("start-design", "start-design-aaaaaa")
        self._create_session("start-plan", "start-plan-bbbbbb")
        result = cmd_find(self._make_args(skill="start-design"))
        self.assertEqual(len(result["sessions"]), 1)

    def test_find_returns_last_updated(self):
        """sessions[] エントリに last_updated が含まれること"""
        self._create_session("start-design")
        result = cmd_find(self._make_args(skill="start-design"))
        self.assertIn("last_updated", result["sessions"][0])
        self.assertEqual(
            result["sessions"][0]["last_updated"], "2026-03-13T18:00:00Z"
        )

    def test_find_all_skills_returns_all(self):
        """--all-skills で全スキルのセッションを返す"""
        self._create_session("start-design", "start-design-aaaaaa")
        self._create_session("start-plan", "start-plan-bbbbbb")
        self._create_session("review", "review-cccccc")
        result = cmd_find(self._make_args(all_skills=True))
        self.assertEqual(result["status"], "found")
        self.assertEqual(len(result["sessions"]), 3)
        skills_seen = {s["skill"] for s in result["sessions"]}
        self.assertEqual(skills_seen, {"start-design", "start-plan", "review"})

    def test_find_all_skills_none(self):
        """--all-skills でセッションが無い場合は status: none"""
        result = cmd_find(self._make_args(all_skills=True))
        self.assertEqual(result["status"], "none")


# =========================================================================
# 5. cmd_cleanup
# =========================================================================

class TestCmdCleanup(_FsTestCase):
    """cmd_cleanup のテスト"""

    def _make_args(self, session_dir):
        class Args:
            pass
        a = Args()
        a.session_dir = session_dir
        return a

    def test_deletes_directory(self):
        session_dir = os.path.join(TEMP_BASE, "start-design-aaaaaa")
        os.makedirs(session_dir, exist_ok=True)
        result = cmd_cleanup(self._make_args(session_dir))
        self.assertEqual(result["status"], "deleted")
        self.assertFalse(os.path.exists(session_dir))

    def test_rejects_unsafe_path(self):
        result = cmd_cleanup(self._make_args("/tmp/dangerous"))
        self.assertEqual(result["status"], "error")

    def test_nonexistent_path(self):
        result = cmd_cleanup(self._make_args(
            os.path.join(TEMP_BASE, "nonexistent")))
        self.assertEqual(result["status"], "error")

    def test_traversal_rejected(self):
        result = cmd_cleanup(self._make_args(
            os.path.join(TEMP_BASE, "..", "..", "etc")))
        self.assertEqual(result["status"], "error")


# =========================================================================
# 5a-1. cmd_touch
# =========================================================================

class TestCmdTouch(_FsTestCase):
    """cmd_touch のテスト"""

    def _make_args(self, session_dir):
        class Args:
            pass
        a = Args()
        a.session_dir = session_dir
        return a

    def _create_session(self, skill, name, started_at):
        session_dir = os.path.join(TEMP_BASE, name)
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {
                "skill": skill,
                "started_at": started_at,
                "last_updated": started_at,
                "status": "in_progress",
            },
            field_order=SESSION_FIELD_ORDER,
        )
        return session_dir

    def test_updates_last_updated(self):
        """last_updated が現在時刻に更新される"""
        session_dir = self._create_session(
            "start-design", "start-design-aaaaaa", "2026-01-01T00:00:00Z"
        )
        result = cmd_touch(self._make_args(session_dir))
        self.assertEqual(result["status"], "ok")
        # 戻り値の last_updated が更新されている
        self.assertNotEqual(result["last_updated"], "2026-01-01T00:00:00Z")
        self.assertRegex(
            result["last_updated"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        )
        # session.yaml も更新されている
        data = read_yaml(os.path.join(session_dir, "session.yaml"))
        self.assertEqual(data["last_updated"], result["last_updated"])

    def test_started_at_preserved(self):
        """touch しても started_at は変わらない"""
        session_dir = self._create_session(
            "start-design", "start-design-aaaaaa", "2026-01-01T00:00:00Z"
        )
        cmd_touch(self._make_args(session_dir))
        data = read_yaml(os.path.join(session_dir, "session.yaml"))
        self.assertEqual(data["started_at"], "2026-01-01T00:00:00Z")

    def test_status_preserved(self):
        """touch しても status は変わらない"""
        session_dir = self._create_session(
            "start-design", "start-design-aaaaaa", "2026-01-01T00:00:00Z"
        )
        cmd_touch(self._make_args(session_dir))
        data = read_yaml(os.path.join(session_dir, "session.yaml"))
        self.assertEqual(data["status"], "in_progress")

    def test_extra_fields_preserved(self):
        """touch してもスキル固有フィールドは保持される"""
        session_dir = os.path.join(TEMP_BASE, "start-design-bbbbbb")
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {
                "skill": "start-design",
                "started_at": "2026-01-01T00:00:00Z",
                "last_updated": "2026-01-01T00:00:00Z",
                "status": "in_progress",
                "feature": "login",
                "mode": "new",
            },
            field_order=SESSION_FIELD_ORDER,
        )
        cmd_touch(self._make_args(session_dir))
        data = read_yaml(os.path.join(session_dir, "session.yaml"))
        self.assertEqual(data["feature"], "login")
        self.assertEqual(data["mode"], "new")

    def test_rejects_unsafe_path(self):
        result = cmd_touch(self._make_args("/tmp/dangerous"))
        self.assertEqual(result["status"], "error")

    def test_missing_session_yaml(self):
        """session.yaml がないディレクトリは error"""
        session_dir = os.path.join(TEMP_BASE, "start-design-empty")
        os.makedirs(session_dir, exist_ok=True)
        result = cmd_touch(self._make_args(session_dir))
        self.assertEqual(result["status"], "error")


# =========================================================================
# 5a-2. cmd_complete
# =========================================================================

class TestCmdComplete(_FsTestCase):
    """cmd_complete のテスト"""

    def _make_args(self, session_dir):
        class Args:
            pass
        a = Args()
        a.session_dir = session_dir
        return a

    def _create_session(self, skill, name):
        session_dir = os.path.join(TEMP_BASE, name)
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {
                "skill": skill,
                "started_at": "2026-01-01T00:00:00Z",
                "last_updated": "2026-01-01T00:00:00Z",
                "status": "in_progress",
            },
            field_order=SESSION_FIELD_ORDER,
        )
        return session_dir

    def test_transitions_to_completed(self):
        """status が completed に遷移する"""
        session_dir = self._create_session("start-design", "start-design-aaaaaa")
        result = cmd_complete(self._make_args(session_dir))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["session_status"], "completed")
        data = read_yaml(os.path.join(session_dir, "session.yaml"))
        self.assertEqual(data["status"], "completed")

    def test_updates_last_updated(self):
        """complete でも last_updated が更新される"""
        session_dir = self._create_session("start-design", "start-design-aaaaaa")
        result = cmd_complete(self._make_args(session_dir))
        self.assertNotEqual(result["last_updated"], "2026-01-01T00:00:00Z")
        self.assertRegex(
            result["last_updated"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        )

    def test_idempotent(self):
        """既に completed のセッションに complete を呼んでも問題ない"""
        session_dir = self._create_session("start-design", "start-design-aaaaaa")
        cmd_complete(self._make_args(session_dir))
        result = cmd_complete(self._make_args(session_dir))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["session_status"], "completed")

    def test_rejects_unsafe_path(self):
        result = cmd_complete(self._make_args("/tmp/dangerous"))
        self.assertEqual(result["status"], "error")

    def test_missing_session_yaml(self):
        session_dir = os.path.join(TEMP_BASE, "start-design-empty")
        os.makedirs(session_dir, exist_ok=True)
        result = cmd_complete(self._make_args(session_dir))
        self.assertEqual(result["status"], "error")


# =========================================================================
# 5b. cmd_cleanup_stale
# =========================================================================

class TestCmdCleanupStale(_FsTestCase):
    """cmd_cleanup_stale のテスト"""

    def _make_args(self, older_than_hours=48, skill=None, dry_run=False,
                   completed_only=False):
        class Args:
            pass
        a = Args()
        a.older_than_hours = older_than_hours
        a.skill = skill
        a.dry_run = dry_run
        a.completed_only = completed_only
        return a

    def _create_session(self, skill, name, hours_ago, status="in_progress"):
        """指定スキルで hours_ago 時間前のセッションを作成する"""
        from datetime import datetime, timedelta, timezone
        session_dir = os.path.join(TEMP_BASE, name)
        os.makedirs(session_dir, exist_ok=True)
        past = (datetime.now(timezone.utc)
                - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {
                "skill": skill,
                "started_at": past,
                "last_updated": past,
                "status": status,
            },
            field_order=SESSION_FIELD_ORDER,
        )
        return session_dir

    def test_deletes_only_stale(self):
        """期限超過セッションのみ削除される"""
        fresh = self._create_session("start-design", "start-design-fresh", hours_ago=1)
        stale = self._create_session("start-design", "start-design-stale", hours_ago=100)

        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))

        self.assertEqual(result["status"], "ok")
        deleted_paths = [d["path"] for d in result["deleted"]]
        self.assertIn(stale, deleted_paths)
        self.assertNotIn(fresh, deleted_paths)
        self.assertTrue(os.path.exists(fresh))
        self.assertFalse(os.path.exists(stale))

    def test_dry_run_does_not_delete(self):
        """--dry-run では削除されない"""
        stale = self._create_session("start-plan", "start-plan-stale", hours_ago=100)

        result = cmd_cleanup_stale(self._make_args(older_than_hours=48, dry_run=True))

        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(len(result["deleted"]), 1)
        # 物理削除されていない
        self.assertTrue(os.path.exists(stale))

    def test_skill_filter(self):
        """--skill 指定で他スキルの古いセッションは残る"""
        design = self._create_session("start-design", "start-design-stale", hours_ago=100)
        plan = self._create_session("start-plan", "start-plan-stale", hours_ago=100)

        result = cmd_cleanup_stale(self._make_args(older_than_hours=48, skill="start-design"))

        self.assertEqual(result["status"], "ok")
        deleted_paths = [d["path"] for d in result["deleted"]]
        self.assertIn(design, deleted_paths)
        self.assertNotIn(plan, deleted_paths)
        self.assertFalse(os.path.exists(design))
        self.assertTrue(os.path.exists(plan))

    def test_zero_hours_deletes_all(self):
        """--older-than-hours 0 で全 in_progress セッションが対象"""
        # 30 分前のセッションでも 0 時間以上なので削除対象
        recent = self._create_session("review", "review-stale", hours_ago=0.5)

        result = cmd_cleanup_stale(self._make_args(older_than_hours=0))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["deleted"]), 1)
        self.assertFalse(os.path.exists(recent))

    def test_negative_hours_rejected(self):
        """--older-than-hours が負数なら error"""
        result = cmd_cleanup_stale(self._make_args(older_than_hours=-1))
        self.assertEqual(result["status"], "error")

    def test_invalid_timestamp_skipped(self):
        """タイムスタンプが不正な session.yaml は skipped に分類"""
        session_dir = os.path.join(TEMP_BASE, "start-design-broken")
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {
                "skill": "start-design",
                "started_at": "not-a-date",
                "last_updated": "not-a-date",
                "status": "in_progress",
            },
            field_order=SESSION_FIELD_ORDER,
        )

        result = cmd_cleanup_stale(self._make_args(older_than_hours=0))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["deleted"]), 0)
        skipped_paths = [s["path"] for s in result["skipped"]]
        self.assertIn(session_dir, skipped_paths)
        # 安全側に倒し、削除されない
        self.assertTrue(os.path.exists(session_dir))

    def test_no_sessions(self):
        """対象ディレクトリが空でも例外を出さない"""
        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["deleted"], [])

    def test_completed_sessions_deleted_regardless_of_age(self):
        """status: completed のセッションは cutoff_hours に関わらず削除される"""
        fresh_completed = self._create_session(
            "start-design", "start-design-done", hours_ago=0.1, status="completed",
        )
        fresh_in_progress = self._create_session(
            "start-plan", "start-plan-running", hours_ago=0.1, status="in_progress",
        )

        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))

        self.assertEqual(result["status"], "ok")
        deleted_paths = [d["path"] for d in result["deleted"]]
        # completed は即削除
        self.assertIn(fresh_completed, deleted_paths)
        self.assertFalse(os.path.exists(fresh_completed))
        # in_progress でまだ若いセッションは残る
        self.assertNotIn(fresh_in_progress, deleted_paths)
        self.assertTrue(os.path.exists(fresh_in_progress))

    def test_completed_entry_includes_status(self):
        """deleted エントリに session_status フィールドが含まれる"""
        self._create_session(
            "start-design", "start-design-done", hours_ago=0.1, status="completed",
        )
        result = cmd_cleanup_stale(self._make_args(older_than_hours=48, dry_run=True))
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(len(result["deleted"]), 1)
        self.assertEqual(result["deleted"][0]["session_status"], "completed")

    def test_completed_only_skips_in_progress(self):
        """--completed-only では古い in_progress でも削除されない（#93）"""
        stale_in_progress = self._create_session(
            "start-design", "start-design-stale", hours_ago=100, status="in_progress",
        )
        completed = self._create_session(
            "start-plan", "start-plan-done", hours_ago=100, status="completed",
        )

        result = cmd_cleanup_stale(
            self._make_args(older_than_hours=48, completed_only=True)
        )

        self.assertEqual(result["status"], "ok")
        deleted_paths = [d["path"] for d in result["deleted"]]
        # completed のみ削除、in_progress は age に関わらず温存
        self.assertIn(completed, deleted_paths)
        self.assertNotIn(stale_in_progress, deleted_paths)
        self.assertFalse(os.path.exists(completed))
        self.assertTrue(os.path.exists(stale_in_progress))

    def test_completed_only_default_false_still_deletes_in_progress(self):
        """completed_only 未指定（既存挙動）では古い in_progress も削除される"""
        stale_in_progress = self._create_session(
            "start-design", "start-design-stale", hours_ago=100, status="in_progress",
        )

        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))

        self.assertEqual(result["status"], "ok")
        self.assertFalse(os.path.exists(stale_in_progress))

    def test_naive_timestamp_treated_as_utc(self):
        """tz 情報なし naive timestamp を UTC とみなし TypeError で落ちない（#93 レビュー指摘）"""
        session_dir = os.path.join(TEMP_BASE, "start-design-naive")
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {"skill": "start-design",
             "started_at": "2026-01-01T00:00:00",
             "last_updated": "2026-01-01T00:00:00",
             "status": "completed"},
            field_order=SESSION_FIELD_ORDER,
        )
        # 例外を出さず、completed は age 無視で削除される
        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))
        self.assertEqual(result["status"], "ok")
        self.assertFalse(os.path.exists(session_dir))

    def test_naive_in_progress_timestamp_handled(self):
        """naive な in_progress も TypeError を出さず age 判定される（#93）"""
        session_dir = os.path.join(TEMP_BASE, "start-plan-naive-ip")
        os.makedirs(session_dir, exist_ok=True)
        write_flat_yaml(
            os.path.join(session_dir, "session.yaml"),
            {"skill": "start-plan",
             "started_at": "2026-01-01T00:00:00",
             "last_updated": "2026-01-01T00:00:00",
             "status": "in_progress"},
            field_order=SESSION_FIELD_ORDER,
        )
        # 2026-01-01 は十分過去なので 48h 超過で削除対象（例外なく処理される）
        result = cmd_cleanup_stale(self._make_args(older_than_hours=48))
        self.assertEqual(result["status"], "ok")
        self.assertFalse(os.path.exists(session_dir))


# =========================================================================
# 6. CLI 統合テスト
# =========================================================================

class TestCLI(_FsTestCase):
    """subprocess で CLI を呼び出すテスト"""

    SCRIPT = str(Path(__file__).resolve().parents[3]
                 / "plugins" / "forge" / "scripts" / "session_manager.py")

    def _run(self, *cli_args):
        result = subprocess.run(
            [sys.executable, self.SCRIPT] + list(cli_args),
            capture_output=True, text=True, cwd=self.tmpdir,
        )
        return result

    def test_init_cli(self):
        r = self._run("init", "--skill", "start-design", "--feature", "login")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "created")
        # ディレクトリが実際に作成されている
        self.assertTrue(os.path.isdir(
            os.path.join(self.tmpdir, data["session_dir"])))

    def test_find_cli_none(self):
        r = self._run("find", "--skill", "start-design")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "none")

    def test_init_find_cleanup_cycle(self):
        """init → find → cleanup の往復テスト"""
        # init
        r = self._run("init", "--skill", "start-plan", "--feature", "test")
        self.assertEqual(r.returncode, 0)
        init_data = json.loads(r.stdout)
        session_dir = init_data["session_dir"]

        # find
        r = self._run("find", "--skill", "start-plan")
        self.assertEqual(r.returncode, 0)
        find_data = json.loads(r.stdout)
        self.assertEqual(find_data["status"], "found")
        self.assertEqual(len(find_data["sessions"]), 1)

        # cleanup
        r = self._run("cleanup", session_dir)
        self.assertEqual(r.returncode, 0)
        cleanup_data = json.loads(r.stdout)
        self.assertEqual(cleanup_data["status"], "deleted")

        # find で消えている
        r = self._run("find", "--skill", "start-plan")
        find_data = json.loads(r.stdout)
        self.assertEqual(find_data["status"], "none")

    def test_no_command_shows_help(self):
        r = self._run()
        self.assertNotEqual(r.returncode, 0)

    def test_touch_cli(self):
        """init → touch → find で last_updated が反映される"""
        r = self._run("init", "--skill", "start-design")
        self.assertEqual(r.returncode, 0)
        session_dir = json.loads(r.stdout)["session_dir"]
        initial_data = json.loads(self._run(
            "find", "--skill", "start-design",
        ).stdout)
        initial_last_updated = initial_data["sessions"][0]["last_updated"]

        # touch
        import time
        time.sleep(1)
        r = self._run("touch", session_dir)
        self.assertEqual(r.returncode, 0)
        touch_data = json.loads(r.stdout)
        self.assertEqual(touch_data["status"], "ok")
        self.assertNotEqual(touch_data["last_updated"], initial_last_updated)

    def test_complete_cli(self):
        """init → complete で status が completed に遷移する"""
        r = self._run("init", "--skill", "start-design")
        self.assertEqual(r.returncode, 0)
        session_dir = json.loads(r.stdout)["session_dir"]

        r = self._run("complete", session_dir)
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["session_status"], "completed")

        # find で見たときも completed になっている
        r = self._run("find", "--skill", "start-design")
        find_data = json.loads(r.stdout)
        self.assertEqual(find_data["sessions"][0]["status"], "completed")

    def test_find_all_skills_cli(self):
        """--all-skills で全スキルのセッションを取得する"""
        self._run("init", "--skill", "start-design")
        self._run("init", "--skill", "start-plan")

        r = self._run("find", "--all-skills")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["status"], "found")
        self.assertEqual(len(data["sessions"]), 2)

    def test_find_requires_skill_or_all_skills(self):
        """find に --skill / --all-skills のどちらも指定しないとエラー"""
        r = self._run("find")
        self.assertNotEqual(r.returncode, 0)

    def test_find_skill_and_all_skills_mutually_exclusive(self):
        """--skill と --all-skills を同時に指定するとエラー"""
        r = self._run("find", "--skill", "start-design", "--all-skills")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
