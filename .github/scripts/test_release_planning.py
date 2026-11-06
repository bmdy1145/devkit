#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_release 发布决策的单元测试。

这些函数是纯逻辑（只读仓库目录结构、不碰网络），非常适合钉行为：
「改哪个项目发哪个项目的标签」这条规则出错时后果是发错 Release，
错误难以及时发现，值得用测试守住。

用法：
    python3 .github/scripts/test_release_planning.py
    python3 -m unittest discover -s .github/scripts -p 'test_*.py'

退出码：0 = 全部通过；1 = 有用例失败。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

# Windows 控制台默认不是 UTF-8，用例里的中文说明会打印成乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auto_release as ar  # noqa: E402


def f(path: str, status: str = "modified") -> dict:
    return {"filename": path, "status": status}


class TestScanChanges(unittest.TestCase):
    def test_groups_by_project_and_trunk(self):
        files = [
            f("projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_CN.html"),
            f("projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html"),
        ]
        out = ar.scan_changes(files)
        self.assertEqual(out["devkit"]["trunks"], ["A1_V_Φ9"])
        self.assertEqual(out["writer"]["trunks"], ["A1_I_Φ3"])
        self.assertTrue(out["devkit"]["project_touched"])
        self.assertTrue(out["writer"]["project_touched"])

    def test_index_page_only_marks_touched_without_trunk(self):
        out = ar.scan_changes([f("projects/writer/code/index.html")])
        self.assertEqual(out["writer"]["trunks"], [])
        self.assertTrue(out["writer"]["project_touched"])

    def test_skips_renamed(self):
        """整棵目录搬迁的那次提交都是 renamed，不能算成「所有主干都改了」。"""
        out = ar.scan_changes(
            [f("projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_CN.html", "renamed")]
        )
        self.assertEqual(out, {})

    def test_ignores_non_project_paths(self):
        out = ar.scan_changes(
            [f("README.md"), f(".github/scripts/auto_release.py"), f("docs/branching.md")]
        )
        self.assertEqual(out, {})

    def test_dedupes_repeated_trunk(self):
        out = ar.scan_changes(
            [
                f("projects/writer/code/A1_I_Φ3/a.html"),
                f("projects/writer/code/A1_I_Φ3/b.html"),
            ]
        )
        self.assertEqual(out["writer"]["trunks"], ["A1_I_Φ3"])


class TestPlanAuto(unittest.TestCase):
    def test_writer_trunk_change_releases_writer_only(self):
        """这是原始缺陷的直接回归：改 Writer 不能给 DevKit 发 Release。"""
        targets, _ = ar.plan_auto([f("projects/writer/code/A1_I_Φ3/x.html")])
        projects = [p for p, _, _ in targets]
        self.assertNotIn("devkit", projects)
        self.assertIn("writer", projects)
        self.assertEqual(
            [m for p, _, m in targets if p == "writer"],
            ["changed"],
        )

    def test_docs_only_releases_nothing(self):
        targets, reason = ar.plan_auto([f("README.md")])
        self.assertEqual(targets, [])
        self.assertIn("不发布任何 Release", reason)

    def test_index_only_uses_no_changes_mode(self):
        targets, _ = ar.plan_auto([f("projects/writer/code/index.html")])
        self.assertEqual(len(targets), 1)
        project, trunk, mode = targets[0]
        self.assertEqual(project, "writer")
        self.assertEqual(mode, "no_changes")
        self.assertEqual(trunk, ar.latest_trunk("writer"))

    def test_both_projects_changed(self):
        targets, _ = ar.plan_auto(
            [
                f("projects/devkit/code/A1_V_Φ9/x.html"),
                f("projects/writer/code/A1_I_Φ3/y.html"),
            ]
        )
        self.assertEqual(
            sorted((p, t) for p, t, _ in targets),
            sorted([("devkit", "A1_V_Φ9"), ("writer", "A1_I_Φ3")]),
        )

    def test_unknown_comparison_releases_nothing(self):
        """compare 失败时不能退化为全量发版：一次异常会连发十几个 Release。

        改成「本次不自动发版 + 日志说明」，需要时手动 dispatch 补发。
        """
        targets, reason = ar.plan_auto(None)
        self.assertEqual(targets, [])
        self.assertIn("不自动发版", reason)

    def test_targets_are_triples_so_modes_cannot_desync(self):
        targets, _ = ar.plan_auto([f("projects/writer/code/A1_I_Φ3/x.html")])
        for item in targets:
            self.assertEqual(len(item), 3)


class TestTagNaming(unittest.TestCase):
    def test_devkit_keeps_bare_trunk_name(self):
        self.assertEqual(ar.tag_base("devkit", "A1_V_Φ9"), "A1_V_Φ9")

    def test_other_projects_get_prefix(self):
        self.assertEqual(ar.tag_base("writer", "A1_I_Φ3"), "writer/A1_I_Φ3")

    def test_next_tag_first_release(self):
        self.assertEqual(ar.next_tag("writer", "A1_I_Φ3", set()), "writer/A1_I_Φ3")

    def test_next_tag_increments(self):
        existing = {"writer/A1_I_Φ3", "writer/A1_I_Φ3.1", "writer/A1_I_Φ3.2"}
        self.assertEqual(ar.next_tag("writer", "A1_I_Φ3", existing), "writer/A1_I_Φ3.3")

    def test_next_tag_ignores_other_projects(self):
        """别的项目同名主干不能影响本项目的编号。"""
        existing = {"dircleaner/A1_I_Φ3", "dircleaner/A1_I_Φ3.7"}
        self.assertEqual(ar.next_tag("writer", "A1_I_Φ3", existing), "writer/A1_I_Φ3")

    def test_devkit_increment_matches_history(self):
        existing = {"A1_V_Φ9", "A1_V_Φ9.1", "A1_V_Φ9.2", "A1_V_Φ9.3"}
        self.assertEqual(ar.next_tag("devkit", "A1_V_Φ9", existing), "A1_V_Φ9.4")


class TestPlanDispatch(unittest.TestCase):
    def test_existing_trunk(self):
        targets, forced, _ = ar.plan_dispatch("writer", "A1_I_Φ3", "")
        self.assertEqual(targets, [("writer", "A1_I_Φ3", "manual")])
        self.assertIsNone(forced)

    def test_suffix_produces_forced_tag(self):
        _, forced, _ = ar.plan_dispatch("writer", "A1_I_Φ3", "2")
        self.assertEqual(forced, "writer/A1_I_Φ3.2")

    def test_missing_trunk_reports_error(self):
        targets, forced, reason = ar.plan_dispatch("writer", "A1_I_Φ999", "")
        self.assertEqual(targets, [])
        self.assertIsNone(forced)
        self.assertIn("找不到", reason)

    def test_archive_trunk_is_rejected(self):
        """归档目录不能通过手动 dispatch 发布。

        自动路径早就过滤了归档，但 plan_dispatch 之前只查 is_dir()，
        DISPATCH_TRUNK=A1_V_Φ9_fix-archive 能给归档发一个 Release。
        """
        targets, forced, reason = ar.plan_dispatch("devkit", "A1_V_Φ9_fix-archive", "")
        self.assertEqual(targets, [])
        self.assertIsNone(forced)
        self.assertIn("归档", reason)

    def test_dotdot_trunk_is_rejected(self):
        """`..` 能被 is_dir() 放行，必须靠名字校验挡住。"""
        for bad in ("..", ".", "../A1_V_Φ9", "a/b", "a\\b", ""):
            targets, forced, reason = ar.plan_dispatch("devkit", bad, "")
            self.assertEqual(targets, [], f"{bad!r} 不应通过")
            self.assertIsNone(forced)
            self.assertTrue(reason)

    def test_safe_trunk_name_helper(self):
        self.assertTrue(ar.is_safe_trunk_name("A1_V_Φ9"))
        self.assertTrue(ar.is_safe_trunk_name("writer"))
        for bad in ("..", ".", "", "a/b", "a\\b"):
            self.assertFalse(ar.is_safe_trunk_name(bad), f"{bad!r} 不应通过")


class TestArchiveDirsAreNotTrunks(unittest.TestCase):
    """归档目录（*_fix-archive/）不是主干，不参与发布。

    code/ 下除了主干活目录，还有冻结的归档层。若把归档当主干：
      · latest_trunk() 可能选中归档（它的 Φ 号与真主干并列），
        「只改索引页」那次推送就会给归档发 Release；
      · 改动归档文件本身会被判成「动了该主干」，同样发 Release。
    """

    def test_is_trunk_dir_rejects_archive(self):
        code = ar.code_dir("devkit")
        archives = [p for p in code.iterdir() if p.name.endswith("_fix-archive")]
        if not archives:
            self.skipTest("当前仓库没有归档目录")
        for p in archives:
            self.assertFalse(ar.is_trunk_dir(p), f"{p.name} 不应被当作主干")

    def test_is_trunk_dir_accepts_real_trunk(self):
        code = ar.code_dir("devkit")
        real = [p for p in code.iterdir() if p.is_dir() and not p.name.endswith("_fix-archive")]
        if not real:
            self.skipTest("当前仓库没有主干目录")
        for p in real:
            self.assertTrue(ar.is_trunk_dir(p), f"{p.name} 应被当作主干")

    def test_local_trunks_excludes_archives(self):
        for project in ar.local_projects():
            for trunk in ar.local_trunks(project):
                self.assertFalse(trunk.endswith("_fix-archive"), f"{project}/{trunk}")

    def test_latest_trunk_is_not_archive(self):
        """回归：A1_V_Φ9_fix-archive 与 A1_V_Φ9 并列时，最新主干必须是后者。"""
        original = ar.PROJECTS_DIR
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                code = tmp_root / "demo" / "code"
                (code / "A1_V_Φ9").mkdir(parents=True)
                (code / "A1_V_Φ9_fix-archive").mkdir()
                ar.PROJECTS_DIR = tmp_root
                self.assertEqual(ar.latest_trunk("demo"), "A1_V_Φ9")
        finally:
            ar.PROJECTS_DIR = original

    def test_index_only_change_targets_real_trunk_not_archive(self):
        original = ar.PROJECTS_DIR
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                code = tmp_root / "demo" / "code"
                (code / "A1_V_Φ9").mkdir(parents=True)
                (code / "A1_V_Φ9_fix-archive").mkdir()
                ar.PROJECTS_DIR = tmp_root
                targets, _ = ar.plan_auto([f("projects/demo/code/index.html")])
                self.assertEqual(targets, [("demo", "A1_V_Φ9", "no_changes")])
        finally:
            ar.PROJECTS_DIR = original

    def test_archive_file_change_does_not_release_archive(self):
        original = ar.PROJECTS_DIR
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                code = tmp_root / "demo" / "code"
                (code / "A1_V_Φ9").mkdir(parents=True)
                (code / "A1_V_Φ9_fix-archive").mkdir()
                ar.PROJECTS_DIR = tmp_root
                targets, _ = ar.plan_auto(
                    [f("projects/demo/code/A1_V_Φ9_fix-archive/deepseek_A1_V_Φ9_CN.html")]
                )
                # 归档不是主干 → 退化为「该项目未动主干」，给最新真主干发无功能更新
                self.assertEqual(targets, [("demo", "A1_V_Φ9", "no_changes")])
        finally:
            ar.PROJECTS_DIR = original


class TestLocalProjects(unittest.TestCase):
    def test_returns_projects_with_code_dir(self):
        projects = ar.local_projects()
        self.assertIn("devkit", projects)
        self.assertIn("writer", projects)
        for p in projects:
            self.assertTrue(ar.code_dir(p).is_dir())

    def test_missing_projects_dir_returns_empty(self):
        original = ar.PROJECTS_DIR
        try:
            ar.PROJECTS_DIR = Path(original) / "__definitely_not_here__"
            self.assertEqual(ar.local_projects(), [])
        finally:
            ar.PROJECTS_DIR = original


class TestDraftFirstRelease(unittest.TestCase):
    """发布顺序必须是「建草稿 → 传附件 → 发布」。

    仓库开启了 GitHub 的 Immutable Releases：Release 一旦以 draft=false 创建，
    标签与附件就锁死，之后上传附件一律 HTTP 422。2026-11-06 就是这么产生了
    两个 0 附件的空 Release。这里钉住顺序与失败回滚行为。
    """

    def setUp(self):
        # 避开真实目录与网络：造一个只含一个交付物文件的项目结构
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        trunk = root / "demo" / "code" / "A1_X_Φ1"
        trunk.mkdir(parents=True)
        (trunk / "deepseek_A1_X_Φ1_CN.html").write_text("<html></html>", encoding="utf-8")
        self._orig_projects = ar.PROJECTS_DIR
        ar.PROJECTS_DIR = root

        self.calls: list[tuple] = []
        self.burned_tags: set[str] = set()
        self.release_ids: list[int] = []

    def tearDown(self):
        ar.PROJECTS_DIR = self._orig_projects
        self._tmp.cleanup()

    def _fake_api(self, method, url, token, payload=None):
        self.calls.append((method, url, payload))
        if method == "GET" and "/releases/tags/" in url:
            # 仓库里没有同名 Release（探测用）
            return 404, {"message": "Not Found"}
        if method == "GET":  # existing_tags
            return 200, []
        if method == "POST" and url.endswith("/git/refs"):
            return 201, {}
        if method == "POST" and url.endswith("/releases"):
            tag = payload.get("tag_name", "")
            # 模拟被不可变 Release 烧掉的标签名
            if tag in self.burned_tags:
                return 422, {
                    "message": "Validation Failed",
                    "errors": [
                        {
                            "resource": "Release",
                            "code": "custom",
                            "field": "tag_name",
                            "message": "tag_name was used by an immutable release",
                        }
                    ],
                }
            self.release_ids.append(len(self.release_ids) + 1000)
            return 201, {"id": self.release_ids[-1]}
        if method == "PATCH":  # 发布草稿
            return 200, {}
        if method == "DELETE":
            return 204, None
        return 200, {}

    def _run(self, upload_ok: bool = True, forced_tag: str | None = None):
        with mock.patch.object(ar, "api", side_effect=self._fake_api), mock.patch.object(
            ar, "upload_asset", return_value=upload_ok
        ), mock.patch.object(ar, "build_notes", return_value="notes"):
            return ar.release_trunk(
                "o/r", "t", "demo", "A1_X_Φ1", "abc123", "changed", forced_tag
            )

    def test_create_release_as_draft(self):
        self.assertTrue(self._run(upload_ok=True))
        create = next(c for c in self.calls if c[0] == "POST" and c[1].endswith("/releases"))
        self.assertIs(create[2]["draft"], True, "必须建草稿，否则附件锁死")

    def test_publish_after_upload(self):
        self.assertTrue(self._run(upload_ok=True))
        methods = [c[0] for c in self.calls]
        self.assertIn("PATCH", methods)
        # PATCH（发布）必须发生在创建 Release 之后
        patch_idx = methods.index("PATCH")
        create_idx = next(
            i
            for i, c in enumerate(self.calls)
            if c[0] == "POST" and c[1].endswith("/releases")
        )
        self.assertGreater(patch_idx, create_idx)
        self.assertEqual(self.calls[patch_idx][2], {"draft": False})

    def test_upload_failure_rolls_back_release_and_tag(self):
        self.assertFalse(self._run(upload_ok=False))
        deletes = [c for c in self.calls if c[0] == "DELETE"]
        self.assertTrue(deletes, "上传失败必须回滚，不能留空壳 Release")
        urls = " ".join(c[1] for c in deletes)
        self.assertIn("/releases/", urls)
        self.assertIn("refs/tags/", urls)
        self.assertNotIn("PATCH", [c[0] for c in self.calls], "失败时不得发布")

    def test_burned_tag_name_auto_bumps_suffix(self):
        """标签名被不可变 Release 占用时，自动换下一个后缀重试。

        2026-11-06 实测：persona/A1_II_Φ11 发布过又删掉后，同名再也建不了
        Release（422 tag_name was used by an immutable release）。若脚本不
        自动跳后缀，此后每次给该主干发版都会失败。
        """
        self.burned_tags = {"demo/A1_X_Φ1"}
        self.assertTrue(self._run())
        tags = [
            c[2]["tag_name"]
            for c in self.calls
            if c[0] == "POST" and c[1].endswith("/releases")
        ]
        self.assertEqual(tags, ["demo/A1_X_Φ1", "demo/A1_X_Φ1.1"])

    def test_burned_tag_with_forced_name_reports_error(self):
        """手动指定的标签名被占用时不擅自改名，报错让人决定。"""
        self.burned_tags = {"demo/A1_X_Φ1.7"}
        self.assertFalse(self._run(forced_tag="demo/A1_X_Φ1.7"))
        tags = [
            c[2]["tag_name"]
            for c in self.calls
            if c[0] == "POST" and c[1].endswith("/releases")
        ]
        self.assertEqual(tags, ["demo/A1_X_Φ1.7"], "手动指定名字不得被悄悄替换")


if __name__ == "__main__":
    unittest.main(verbosity=2)
