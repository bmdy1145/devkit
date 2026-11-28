#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试版结构校验。

`version_guard.py` 只遍历 `projects/<项目>/code/`，测试版放在
`projects/<项目>/test/` 不在它的范围内。本脚本补上测试版自己的约定：

  · 文件名 ⟷ 文件头「版本代号」 ⟷ `CURRENT_VERSION` 三方一致
    （常量可缺省——dircleaner / submerge-pro 的产物本来就没有它，
    与 version_guard 对这两个项目的豁免口径一致）
  · 版本号形如 `A1_VI_Φ1_Test1`（基线主干 + `_Test<N>`）
  · 基线的正式主干目录 `code/<基线>/` 必须存在
  · 每个版本目录必须有 `index.html`，且其中出现该版本号（否则站点进不去）
  · 测试版必须带自检标记（`TEST_SELFTEST_START`），正式版必须不带
  · 构建清单（build_test_version.py 的 TARGETS）与磁盘上的测试版目录
    必须双向对齐：清单里的目录要存在，磁盘上的目录也要有清单条目——
    否则 --check 只校验清单内文件，手放的测试版会绕过漂移检测
  · 测试版导航页的 HTML 骨架必须闭合（doctype / html / head / body）。
    浏览器容错会把缺 </head> 的页面照常渲染，现有守卫全看不出来，
    但生成脚本一旦手写拼接就会反复犯这个错

与其它守卫一样只报告、不拦截退出码的语义由 CI 决定；本脚本自身
有问题时返回 1。

用法：
    python3 .github/scripts/test_guard.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "projects"

# 允许基线带第四层英文标识（如 A1_V_Φ9_Fix_Fix_Test1）——`_Test<N>` 只是
# 追加在基线之后的测试标记，不对基线的层数作额外限制。
#
# 但 `_CN` 不能出现在中间：`A1_VI_Φ1_CN_Test1` 会被产品自己的版本号解析器
# 判为非法（语言后缀只认末尾），导出的配置将无法再导回。语言后缀应写在
# 最后，即 `A1_VI_Φ1_Test1_CN`；目录名则一律不带后缀。
VERSION_RE = re.compile(
    r"^A\d+_[IVX]+_Φ\d+(?:_(?!CN_Test\d+$)[A-Za-z][A-Za-z0-9]*)*_Test\d+$"
)
SELFTEST_MARK = "TEST_SELFTEST_START"

# 目录名不带语言后缀的项目：测试版文件名与目录名完全一致（无 _CN）。
# dircleaner 的正式产物连版本号都不写在文件名里，没有语言变体传统。
NO_LANG_SUFFIX = {"dircleaner"}

# 产物里本来就没有 CURRENT_VERSION 常量的项目。与 version_guard.py
# 的 CHECKED_PROJECTS 口径一致：这两个项目硬套常量检查只会误报。
NO_CURRENT_VERSION = {"dircleaner", "submerge-pro"}

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
    """A1_VI_Φ1_Test1 → A1_VI_Φ1；A1_V_Φ9_Fix_Fix_Test1 → A1_V_Φ9_Fix_Fix"""
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
    else:
        problems.extend(check_html_skeleton(idx))

    files = sorted(ver_dir.glob("deepseek_*.html"))
    if not files:
        fail(rel, "目录内没有 deepseek_*.html")
        return
    if len(files) > 1:
        warn(rel, f"目录内有多份产品文件（{len(files)}），确认是否有意为之")

    # dircleaner 没有 _CN 语言后缀传统（基线 deepseek_html_<日期>_phi9.html
    # 连版本号都不在文件名里），测试版沿用不带后缀的写法。其余项目按
    # `<目录名>_CN` 命名。
    want = name if project_dir.name in NO_LANG_SUFFIX else f"{name}_CN"
    expected_file = f"deepseek_{want}.html"
    for f in files:
        if f.name != expected_file:
            fail(rel, f"文件名 {f.name} 与目录名不符，应为 {expected_file}")

    text = files[0].read_text(encoding="utf-8", errors="replace")
    header = grab(text, r"版本代号：(\S+)")
    current = grab(text, r"CURRENT_VERSION\s*=\s*'([^']+)'")

    if header != want:
        fail(rel, f"文件头版本代号为 {header}，应为 {want}")
    if current is None:
        if project_dir.name not in NO_CURRENT_VERSION:
            fail(rel, "缺少 CURRENT_VERSION 常量")
    elif current != want:
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


def check_html_skeleton(path: Path) -> list[str]:
    """导航页的骨架标签必须成对出现，返回问题描述列表。

    浏览器对缺 `</head>` 的页面照常渲染（自动补全），所以 smoke 与
    link_check 都抓不到；但缺了说明生成脚本的字符串拼接漏了一段，
    下次多半还会再漏。这里只检查结构性闭合，不引入 HTML 解析依赖。

    返回列表而不是直接写全局 problems：单测可以直接断言返回值，
    不依赖执行顺序或全局状态。
    """
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        # 单测会传临时目录里的文件；这里只用于报告，不是否定条件
        rel = str(path)
    out: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"<!doctype\s+html", text, re.I):
        out.append(f"{rel}: 缺少 <!DOCTYPE html>")
    for tag in ("html", "head", "body"):
        # 用词边界避开 <header> / <body-content> 这类前缀相同的标签
        if not re.search(rf"<{tag}(?:\s|>)", text, re.I):
            out.append(f"{rel}: 缺少 <{tag}> 起始标签")
        elif f"</{tag}>" not in text:
            out.append(f"{rel}: 缺少 </{tag}> 闭合标签")
    return out


def check_project(project_dir: Path) -> None:
    test_dir = project_dir / "test"
    if not test_dir.is_dir():
        return
    idx = test_dir / "index.html"
    if not idx.exists():
        warn(test_dir.relative_to(ROOT).as_posix(), "缺少 index.html")
    else:
        problems.extend(check_html_skeleton(idx))

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

    # 双向对齐：生成清单 ↔ 磁盘目录。
    # 只靠 --check 的话，清单外的目录不会被重新生成，也就永远「同步」。
    spec = importlib.util.spec_from_file_location(
        "build_test_version", ROOT / ".github/scripts/build_test_version.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    planned = {(t["project"], t["out_dir"].name) for t in mod.TARGETS}
    on_disk = {
        (p.name, d.name)
        for p in PROJECTS.iterdir()
        if p.is_dir() and (p / "test").is_dir()
        for d in (p / "test").iterdir()
        if d.is_dir()
    }
    for project, ver in sorted(planned - on_disk):
        fail(f"projects/{project}/test/{ver}", "在 build_test_version.py 清单里但目录不存在")
    for project, ver in sorted(on_disk - planned):
        fail(f"projects/{project}/test/{ver}", "目录存在但不在 build_test_version.py 清单里")

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
