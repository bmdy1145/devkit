#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试版体系（build_test_version.py / test_guard.py / make_release_notes.py）的单测。

这套体系有两条容易悄悄坏掉的不变量：

  · 生成清单 ↔ 磁盘目录双向对齐。只校验清单内文件的话，手放一个
    测试版目录会绕过 --check 的漂移检测。
  · 各项目「文件该叫什么」的规则不同（dircleaner 没有 _CN 后缀、
    没有 CURRENT_VERSION；submerge-pro 没有 CURRENT_VERSION）。规则
    写错时 test_guard 会对全部测试版误报，或反过来全都放行。

用法：
    python3 .github/scripts/test_test_version_system.py
    python3 -m unittest discover -s .github/scripts -p 'test_*.py'

退出码：0 = 全部通过；1 = 有用例失败。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]

sys.path.insert(0, str(SCRIPTS))

import make_release_notes as notes  # noqa: E402
import test_guard as guard  # noqa: E402


def _load_module(name: str, filename: str):
    """文件名以 test_ 开头，unittest discover 会把它当测试模块导入；
    生成器与 runner 同理需要按路径加载，不能直接 import。"""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = _load_module("build_test_version", "build_test_version.py")
runner = _load_module("test_selftest_runner", "test_selftest_runner.py")


class TestTargetsManifest(unittest.TestCase):
    """生成清单本身必须自洽，否则 --check 会漏检或错检。"""

    def test_covers_all_five_projects(self):
        projects = {t["project"] for t in builder.TARGETS}
        self.assertEqual(
            projects,
            {"devkit", "writer", "persona", "dircleaner", "submerge-pro"},
        )

    def test_each_target_has_selftest_file(self):
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                self.assertTrue(
                    (SCRIPTS / t["selftest"]).exists(),
                    f"{t['selftest']} 不存在",
                )

    def test_base_paths_exist(self):
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                self.assertTrue(t["base_path"].exists(), t["base_path"])

    def test_out_dir_name_matches_test_name(self):
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                self.assertEqual(t["out_dir"].name, t["test_name"])

    def test_test_version_matches_language_suffix_rule(self):
        """dircleaner 不带 _CN，其余项目必须带。文件名与版本代号都由
        这一条规则推出，写错会让 test_guard 对整批测试版误报。"""
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                want_cn = t["project"] not in guard.NO_LANG_SUFFIX
                self.assertEqual(t["test_version"].endswith("_CN"), want_cn)

    def test_version_regex_accepts_all_test_names(self):
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                self.assertRegex(t["test_name"], guard.VERSION_RE)

    def test_baseline_dir_exists_in_code(self):
        """每个测试版的基线主干必须真实存在于 code/ 下。"""
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                base = guard.baseline_of(t["test_name"])
                self.assertTrue(
                    (ROOT / "projects" / t["project"] / "code" / base).is_dir(),
                    base,
                )

    def test_runner_covers_every_target(self):
        """runner 的 FILES 必须与生成器 TARGETS 一一对应。

        两份清单是分开维护的：新增项目时只改一处，自检实测会静默跳过
        那个项目，CI 仍然全绿——这是最危险的一类漏检。
        """
        targets = {(t["project"], t["out_dir"].name) for t in builder.TARGETS}
        files = {(p, v) for p, v, _ in runner.FILES}
        self.assertEqual(targets - files, set(), "TARGETS 里有、FILES 里没有")
        self.assertEqual(files - targets, set(), "FILES 里有、TARGETS 里没有")

    def test_runner_filenames_match_targets(self):
        """runner 里写的文件名必须等于生成器实际产出的文件名。"""
        by_project = {p: (v, f) for p, v, f in runner.FILES}
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                ver, fname = by_project[t["project"]]
                self.assertEqual(ver, t["test_name"])
                self.assertEqual(fname, f"deepseek_{t['test_version']}.html")


class TestGuardRules(unittest.TestCase):
    """test_guard 的项目级豁免，与 version_guard 的口径保持一致。"""

    def test_baseline_of_strips_only_test_suffix(self):
        self.assertEqual(guard.baseline_of("A1_VI_Φ1_Test1"), "A1_VI_Φ1")
        self.assertEqual(
            guard.baseline_of("A1_V_Φ9_Fix_Fix_Test2"), "A1_V_Φ9_Fix_Fix"
        )

    def test_baseline_of_keeps_skin_like_segments(self):
        """`_Fix` / `_Clean` 这类英文标识不是测试标记，不能被剥掉。"""
        self.assertEqual(guard.baseline_of("A1_I_Φ6_Test1"), "A1_I_Φ6")

    def test_version_regex(self):
        ok = ["A1_VI_Φ1_Test1", "A1_II_Φ15_Test1", "A1_V_Φ9_Fix_Fix_Test12"]
        bad = ["A1_VI_Φ1", "A1_VI_Φ1_Test", "T1", "A1_VI_Φ1_CN_Test1"]
        for v in ok:
            with self.subTest(v=v):
                self.assertRegex(v, guard.VERSION_RE)
        for v in bad:
            with self.subTest(v=v):
                self.assertIsNone(guard.VERSION_RE.match(v))

    def test_no_lang_suffix_matches_dircleaner_only(self):
        self.assertEqual(guard.NO_LANG_SUFFIX, {"dircleaner"})

    def test_no_current_version_covers_dircleaner_and_submerge(self):
        self.assertEqual(
            guard.NO_CURRENT_VERSION, {"dircleaner", "submerge-pro"}
        )


class TestHtmlSkeletonCheck(unittest.TestCase):
    """导航页骨架检查：浏览器会容错，守卫必须自己抓。

    回归点：writer / persona / dircleaner / submerge-pro 的测试版导航页
    曾因生成脚本只切到 `</style>` 而漏掉 `</head>`，八个页面全部静默通过
    了 link_check、smoke 与 test_guard，直到人工审查才发现。
    """

    def _check(self, body: str):
        """直接断言返回值，不读模块级 problems——避免测试间互相污染。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(body, encoding="utf-8")
            return guard.check_html_skeleton(path)

    def test_complete_page_passes(self):
        page = (
            "<!DOCTYPE html><html lang='zh-CN'><head><title>t</title></head>"
            "<body><p>x</p></body></html>"
        )
        self.assertEqual(self._check(page), [])

    def test_missing_head_close_is_reported(self):
        page = "<!DOCTYPE html><html><head><title>t</title><body>x</body></html>"
        problems = self._check(page)
        self.assertTrue(any("</head>" in p for p in problems), problems)

    def test_missing_doctype_is_reported(self):
        page = "<html><head></head><body>x</body></html>"
        problems = self._check(page)
        self.assertTrue(any("DOCTYPE" in p for p in problems), problems)

    def test_header_tag_does_not_satisfy_head(self):
        """`<header>` 与 `<head>` 前缀相同，必须按词边界识别，不能误判通过。"""
        page = (
            "<!DOCTYPE html><html><header></header><body>x</body></html>"
        )
        problems = self._check(page)
        self.assertTrue(any("<head> 起始标签" in p for p in problems), problems)


class TestSelftestCounts(unittest.TestCase):
    """发布说明里的自检项数按项目取值，不再是写死的 17。"""

    def test_each_project_has_an_entry(self):
        for t in builder.TARGETS:
            with self.subTest(project=t["project"]):
                self.assertIn(t["project"], notes.SELFTEST_COUNTS)

    def test_unknown_project_falls_back(self):
        self.assertEqual(
            notes.selftest_count("no-such-project"), notes.SELFTEST_COUNT
        )

    def test_known_project_returns_its_own_count(self):
        self.assertEqual(notes.selftest_count("submerge-pro"), 14)
        self.assertEqual(notes.selftest_count("devkit"), 17)


if __name__ == "__main__":
    unittest.main(verbosity=2)
