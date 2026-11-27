#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""devkit_logic_test.py 中纯辅助函数的单元测试。

行为断言本身要起无头浏览器、依赖产品文件带测试缝，跑得慢且只在特定
版本上可用；但里面几个辅助函数是纯逻辑，值得单独钉住——它们出错时
表现为「断言明明不对却报通过」或「报错信息指向错误的地方」。

用法：
    python3 .github/scripts/test_devkit_logic_helpers.py
    python3 -m unittest discover -s .github/scripts -p 'test_*.py'

退出码：0 = 全部通过；1 = 有用例失败。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import devkit_logic_test as dl  # noqa: E402


class TestExpectedVersion(unittest.TestCase):
    """expected_version() 从文件名推导版本号，供 CURRENT_VERSION 断言使用。"""

    def test_plain_devkit_version(self):
        got = dl.expected_version(Path("deepseek_A1_VI_Φ1_CN.html"))
        self.assertEqual(got, "A1_VI_Φ1_CN")

    def test_version_with_refactor_tag(self):
        got = dl.expected_version(Path("deepseek_A1_V_Φ11_Refactor_CN.html"))
        self.assertEqual(got, "A1_V_Φ11_Refactor_CN")

    def test_version_with_skin_variant(self):
        got = dl.expected_version(Path("deepseek_A1_II_Φ15_Clean_CN.html"))
        self.assertEqual(got, "A1_II_Φ15_Clean_CN")

    def test_dotted_version_kept_intact(self):
        """循环扩展层可能带点号（如 A1_V_Φ8.1），不能被 stem 截断。"""
        got = dl.expected_version(Path("deepseek_A1_V_Φ8.1_CN.html"))
        self.assertEqual(got, "A1_V_Φ8.1_CN")

    def test_rejects_name_without_prefix(self):
        """非 deepseek_ 前缀时立刻报错，而不是让断言悄悄退化。"""
        with self.assertRaises(SystemExit) as cm:
            dl.expected_version(Path("my-build.html"))
        self.assertIn("deepseek_", str(cm.exception))

    def test_rejects_empty_version(self):
        """只有前缀没有版本号同样应报错。"""
        with self.assertRaises(SystemExit) as cm:
            dl.expected_version(Path("deepseek_.html"))
        self.assertIn("deepseek_", str(cm.exception))

    def test_defaults_to_module_target(self):
        """不传参时用模块级 TARGET，保证生产路径与测试路径同源。"""
        got = dl.expected_version()
        self.assertEqual(got, dl.TARGET.stem.removeprefix("deepseek_"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
