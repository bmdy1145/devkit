#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试版结构校验。

`version_guard.py` 只遍历 `projects/<项目>/code/`，测试版放在
`projects/<项目>/test/` 不在它的范围内。本脚本补上测试版自己的约定：

  · 目录名 ⟷ 文件名 ⟷ 文件头「版本代号」 ⟷ `CURRENT_VERSION` 四处一致
  · 版本号形如 `A1_VI_Φ1_Test1`（基线主干 + `_Test<N>`）
  · 基线的正式主干目录 `code/<基线>/` 必须存在
  · 每个版本目录必须有 `index.html`，且其中出现该版本号（否则站点进不去）
  · 测试版必须带自检标记（`TEST_SELFTEST_START`），正式版必须不带

与其它守卫一样只报告、不拦截退出码的语义由 CI 决定；本脚本自身
有问题时返回 1。

用法：
    python3 .github/scripts/test_guard.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "projects"

VERSION_RE = re.compile(r"^A\d+_[IVX]+_Φ\d+_Test\d+$")
SELFTEST_MARK = "TEST_SELFTEST_START"

problems: list[str] = []
warnings: list[str] = []
infos: list[str] = []


def fail(where: str, msg: str) -> None:
    problems.append(f"{where}: {msg}")


def warn(where: str, msg: str) -> None:
    warnings.append(f"{where}: {msg}")


def info(where: str, msg: str) -> None:
    infos.append(f"{where}: {msg}")


def grab(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def baseline_of(version: str) -> str:
    """A1_VI_Φ1_Test1 → A1_VI_Φ1"""
    return re.sub(r"_Test\d+$", "", version)


def check_version_dir(project_dir: Path, ver_dir: Path) -> None:
    rel = ver_dir.relative_to(ROOT).as_posix()

    name = ver_dir.name
    if not VERSION_RE.match(name):
        fail(rel, f"目录名不符合 A<数字>_<罗马>_Φ<数字>_Test<N>：{name}")
        return

    idx = ver_dir / "index.html"
    if not idx.exists():
        fail(rel, "缺少 index.html（Pages 目录页，缺了站点进不去）")

    files = sorted(ver_dir.glob("deepseek_*.html"))
    if not files:
        fail(rel, "目录内没有 deepseek_*.html")
        return
    if len(files) > 1:
        warn(rel, f"目录内有多份产品文件（{len(files)}），确认是否有意为之")

    expected_file = f"deepseek_{name}_CN.html"
    for f in files:
        if f.name != expected_file:
            fail(rel, f"文件名 {f.name} 与目录名不符，应为 {expected_file}")

    text = files[0].read_text(encoding="utf-8", errors="replace")
    header = grab(text, r"版本代号：(\S+)")
    current = grab(text, r"CURRENT_VERSION\s*=\s*'([^']+)'")
    want = f"{name}_CN"

    if header != want:
        fail(rel, f"文件头版本代号为 {header}，应为 {want}")
    if current != want:
        fail(rel, f"CURRENT_VERSION 为 {current}，应为 {want}")

    if SELFTEST_MARK not in text:
        fail(rel, "测试版缺少自检注入标记 TEST_SELFTEST_START")

    # 基线主干必须在正式目录里真实存在
    base = baseline_of(name)
    if not (project_dir / "code" / base).is_dir():
        fail(rel, f"基线主干 projects/.../code/{base}/ 不存在")

    if idx.exists():
        idx_text = idx.read_text(encoding="utf-8", errors="replace")
        if want not in idx_text:
            fail(rel, "index.html 未出现该版本号，卡片可能没登记")


def check_project(project_dir: Path) -> None:
    test_dir = project_dir / "test"
    if not test_dir.is_dir():
        return
    if not (test_dir / "index.html").exists() and project_dir.name in ("devkit",):
        warn(test_dir.relative_to(ROOT).as_posix(), "缺少 index.html")

    for ver_dir in sorted(p for p in test_dir.iterdir() if p.is_dir()):
        check_version_dir(project_dir, ver_dir)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not PROJECTS.is_dir():
        print(f"[问题] 找不到 projects 目录：{PROJECTS}", file=sys.stderr)
        return 1

    checked = 0
    for project_dir in sorted(p for p in PROJECTS.iterdir() if p.is_dir()):
        test_dir = project_dir / "test"
        if test_dir.is_dir():
            checked += sum(1 for p in test_dir.iterdir() if p.is_dir())
        check_project(project_dir)

    # 反向检查：正式版不得带上自检注入
    for base in PROJECTS.glob("*/code/*/deepseek_*.html"):
        if SELFTEST_MARK in base.read_text(encoding="utf-8", errors="replace"):
            fail(base.relative_to(ROOT).as_posix(), "正式版文件中出现了测试自检标记")

    for p in problems:
        print(f"[问题] {p}")
    for w in warnings:
        print(f"[告警] {w}")
    for i in infos:
        print(f"[信息] {i}")

    print()
    print(f"检查完成：{checked} 个测试版目录，{len(problems)} 个问题，{len(warnings)} 条告警。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
