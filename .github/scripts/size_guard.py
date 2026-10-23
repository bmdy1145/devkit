#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DevKit 版本文件体积看门狗。

交付物是自包含的单文件 HTML，体积本身就是产品的一部分：用户要下载它、
浏览器要解析它。目前各皮肤稳定在 250–290 KB 区间，一旦某次改动无意中把
图片转成 base64、或把整份源码塞进注释里，体积会成倍膨胀，而这类问题在
diff 里几乎看不出来。

阈值刻意取得宽松，只抓"成倍膨胀"这种量级，不干涉正常的版本迭代。

用法：
    本地： python3 .github/scripts/size_guard.py
    CI  ： 由 .github/workflows/repo-checks.yml 调用

退出码：0 = 通过；1 = 有文件超过硬上限。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# DevKit 交付物已迁入项目层；glob 仍只覆盖 DevKit 的主干目录，不做投机性泛化
CODE_DIR = ROOT / "projects" / "devkit" / "code"
# 其他项目的应用文件：显式登记，沿用同一套阈值。各项目的体积基线不同，
# 泛化扫描会把小项目也套上 DevKit 的余量，失去告警意义。
OTHER_APPS = (
    ROOT / "projects" / "writer" / "code" / "A1_I_Φ1" / "deepseek_A1_I_Φ1_CN.html",
    ROOT / "projects" / "writer" / "code" / "A1_I_Φ2" / "deepseek_A1_I_Φ2_CN.html",
)

# 刻意留足余量：当前最大约 290 KB。产品若合理增长，应先调这两个数，
# 而不是让它们长期处在被触发的边缘——长期告警等于没有告警。
WARN_KB = 380
FAIL_KB = 520

problems: list[str] = []
warnings: list[str] = []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    files = sorted(CODE_DIR.glob("*/deepseek_*.html"))
    for app in OTHER_APPS:
        if app.exists():
            files.append(app)
        else:
            warnings.append(f"{app.relative_to(ROOT).as_posix()}：登记在 OTHER_APPS 中但文件不存在")
    if not files:
        print("[问题] code/ 下没有找到任何版本文件。")
        return 1

    sizes: list[tuple[str, float]] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        kb = path.stat().st_size / 1024
        sizes.append((rel, kb))
        if kb > FAIL_KB:
            problems.append(f"{rel}：{kb:.0f} KB，超过硬上限 {FAIL_KB} KB")
        elif kb > WARN_KB:
            warnings.append(f"{rel}：{kb:.0f} KB，超过告警阈值 {WARN_KB} KB")

    sizes.sort(key=lambda item: item[1], reverse=True)
    print("最大的 3 个文件：")
    for rel, kb in sizes[:3]:
        print(f"  {kb:7.1f} KB  {rel}")

    for p in problems:
        print(f"[问题] {p}")
    for w in warnings:
        print(f"[告警] {w}")

    print()
    print(f"体积检查完成：{len(files)} 个文件，{len(problems)} 个问题，{len(warnings)} 条告警。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
