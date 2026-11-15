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

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# DevKit 交付物已迁入项目层；glob 仍只覆盖 DevKit 的主干目录，不做投机性泛化
CODE_DIR = ROOT / "projects" / "devkit" / "code"


def discover_app_files() -> list[Path]:
    """自动发现全部项目的应用文件：projects/<项目>/code/<主干>/deepseek_*.html。

    此前 devkit 走 glob、其余项目用 OTHER_APPS 白名单手工登记——每发一个
    新版本都要记得来改名单，漏改就等于新版本不进检查（Writer Φ5 就漏过
    一次）。改为按目录结构自动发现后新增版本零维护。
    项目目录里只要存在 code/<主干>/deepseek_*.html 就会被收入；这不是
    投机泛化——文件名前缀 deepseek_ 是全仓库版本文件的既定惯例。
    """
    seen: set[Path] = set()
    for path in sorted(ROOT.glob("projects/*/code/*/deepseek_*.html")):
        seen.add(path.resolve())
    return sorted(seen)

# 刻意留足余量：当前最大约 290 KB。产品若合理增长，应先调这两个数，
# 而不是让它们长期处在被触发的边缘——长期告警等于没有告警。
WARN_KB = 380
FAIL_KB = 520

problems: list[str] = []
warnings: list[str] = []

# SubMerge Pro Φ11 的 10 个版本共用同一份组件 CSS 与同一份功能脚本，
# 差异只在 body.skin-* 令牌块、字体链接与辅助脚本。体积检查无法发现
# 「只改了其中一份」这类漂移，故在此按目录做哈希一致性校验。
PHI11_DIR = ROOT / "projects" / "submerge-pro" / "code" / "A1_II_Φ11"
THEME_BLOCK_RE = re.compile(
    r"        /\* -+ 主题：.*?\n        \}\n", re.S
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def phi11_parts(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    css = text[text.index("<style>") : text.index("</style>")]
    # 去掉主题令牌块后，剩下的组件 CSS 应逐字一致。
    component_css = THEME_BLOCK_RE.sub("", css)
    start = text.index("<script>")
    end = text.index("</script>", start) + len("</script>")
    return digest(component_css), digest(text[start:end])


def check_phi11_sources() -> None:
    files = sorted(PHI11_DIR.glob("deepseek_*.html"))
    if not files:
        return
    expected = phi11_parts(files[0])
    mother = (
        ROOT / "projects" / "submerge-pro" / "code" / "A1_II_Φ10"
        / "deepseek_html_20261006_d1ca99_Fix.html"
    )
    mother_text = mother.read_text(encoding="utf-8").replace("\r\n", "\n")
    ms = mother_text.index("<script>")
    me = mother_text.index("</script>", ms) + len("</script>")
    mother_script = digest(mother_text[ms:me])

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        css_hash, script_hash = phi11_parts(path)
        if css_hash != expected[0]:
            problems.append(f"{rel}：组件 CSS 与同批 Φ11 版本不一致（{css_hash} ≠ {expected[0]}）")
        if script_hash != expected[1] or script_hash != mother_script:
            problems.append(f"{rel}：功能脚本与母本不一致（{script_hash}）")

    print(f"Φ11 一致性检查：{len(files)} 个文件，组件 CSS {expected[0]}，功能脚本 {mother_script}。")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    files = discover_app_files()
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

    check_phi11_sources()

    for p in problems:
        print(f"[问题] {p}")
    for w in warnings:
        print(f"[告警] {w}")

    print()
    print(f"体积检查完成：{len(files)} 个文件，{len(problems)} 个问题，{len(warnings)} 条告警。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
