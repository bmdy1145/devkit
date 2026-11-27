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
from collections import Counter
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
    for pattern in (
        "projects/*/code/*/deepseek_*.html",   # 正式交付物
        "projects/*/test/*/deepseek_*.html",   # 测试版（同样要盯体积）
    ):
        for path in sorted(ROOT.glob(pattern)):
            seen.add(path.resolve())
    return sorted(seen)

# 刻意留足余量：当前最大约 290 KB。产品若合理增长，应先调这两个数，
# 而不是让它们长期处在被触发的边缘——长期告警等于没有告警。
WARN_KB = 380
FAIL_KB = 520

problems: list[str] = []
warnings: list[str] = []

# SubMerge Pro Φ11 的 10 个版本共用同一份组件 CSS、同一份功能脚本与同一份
# 拖拽辅助脚本，差异只在 body.skin-* 令牌块、字体链接与九合一专用切换脚本。
# 体积检查无法发现「只改了其中一份」这类漂移，故在此按目录做哈希一致性校验。
PHI11_DIR = ROOT / "projects" / "submerge-pro" / "code" / "A1_II_Φ11"
# 生成器在每套主题块前后写入稳定标记，避免校验依赖注释文字或缩进格式。
# START 标记是注释的开头（后面还有说明行），END 标记是独立注释。
THEME_BLOCK_RE = re.compile(
    r"[ \t]*/\* __THEME_BLOCK_START__.*?/\* __THEME_BLOCK_END__ \*/[ \t]*\n?", re.S
)
SCRIPT_RE = re.compile(r"<script>.*?</script>", re.S)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def majority(items: list[str]) -> tuple[str, int]:
    """取出现次数最多的哈希；并列时取字典序最小者，保证结果稳定。"""
    counts = Counter(items)
    best = max(counts.values())
    return min(h for h, n in counts.items() if n == best), best


def phi11_parts(path: Path) -> tuple[str, str, str, int]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    css = text[text.index("<style>") : text.index("</style>")]
    blocks = THEME_BLOCK_RE.findall(css)
    if not blocks:
        problems.append(f"{path.name}：找不到 __THEME_BLOCK_START__/__END__ 标记，无法校验组件 CSS")
    # 去掉主题令牌块后，剩下的组件 CSS 应逐字一致。
    component_css = THEME_BLOCK_RE.sub("", css)
    scripts = SCRIPT_RE.findall(text)
    func = scripts[0] if scripts else ""
    drag = scripts[1] if len(scripts) > 1 else ""
    return digest(component_css), digest(func), digest(drag), len(blocks)


def check_phi11_sources() -> None:
    files = sorted(PHI11_DIR.glob("deepseek_*.html"))
    if not files:
        return
    mother = (
        ROOT / "projects" / "submerge-pro" / "code" / "A1_II_Φ10"
        / "deepseek_html_20261006_d1ca99_Fix.html"
    )
    mother_text = mother.read_text(encoding="utf-8").replace("\r\n", "\n")
    mother_script = digest(SCRIPT_RE.search(mother_text).group(0))

    parts = {p: phi11_parts(p) for p in files}
    css_base, css_votes = majority([v[0] for v in parts.values()])
    drag_base, drag_votes = majority([v[2] for v in parts.values()])

    for path, (css_hash, func_hash, drag_hash, blocks) in parts.items():
        rel = path.relative_to(ROOT).as_posix()
        expected_blocks = 9 if path.name.endswith("_All.html") else 1
        if blocks != expected_blocks:
            problems.append(f"{rel}：主题块 {blocks} 个，应为 {expected_blocks} 个")
        if css_hash != css_base:
            problems.append(f"{rel}：组件 CSS 偏离同批多数版本（{css_hash} ≠ {css_base}，{css_votes}/{len(files)} 票）")
        if func_hash != mother_script:
            problems.append(f"{rel}：功能脚本与母本不一致（{func_hash} ≠ {mother_script}）")
        if drag_hash != drag_base:
            problems.append(f"{rel}：拖拽辅助脚本偏离同批多数版本（{drag_hash} ≠ {drag_base}，{drag_votes}/{len(files)} 票）")

    print(
        f"Φ11 一致性检查：{len(files)} 个文件，组件 CSS {css_base}（{css_votes} 票），"
        f"功能脚本 {mother_script}，拖拽脚本 {drag_base}（{drag_votes} 票）。"
    )


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
