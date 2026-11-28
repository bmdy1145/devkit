#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从正式版产品文件生成测试版（注入内置自检）。

测试版 = 正式版的逐字节副本 + 版本标识改写 + TEST_SELFTEST 注入。
手改测试版会在 CI 的 --check 模式下报「漂移」，必须重新生成。

每个项目一份自检脚本（结构 / 样式 / 核心交互各不相同），清单见 TARGETS：

  · devkit       → test_selftest.js
  · writer       → test_selftest_writer.js
  · persona      → test_selftest_persona.js
  · dircleaner   → test_selftest_dircleaner.js
  · submerge-pro → test_selftest_submerge.js

版本标识改写只做五处（与 devkit 既有产物一致）：
  1. 文件头「版本代号：」行
  2. `<title>` 加【测试】前缀
  3. `CURRENT_VERSION`（仅部分项目有该常量）
  4. 「关于」弹窗里的版本号（仅 writer / persona 把版本号写死在正文）
  5. 脚本头部的横幅注释（`* 项目名 · 副标题（版本号）`，同样只在这两个项目里）

「当前最新版本：」结构块是主线快照，**故意保留基线值**——它记录的是
正式版版本树，不是这份副本的身份。

用法：
    python3 .github/scripts/build_test_version.py            # 生成/覆盖
    python3 .github/scripts/build_test_version.py --check    # 只校验是否与已提交的一致

退出码：0 = 成功 / 无漂移；1 = 漂移或锚点缺失。
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent

# ---- 生成清单：基线产品文件 → 测试版落点 ----------------------------------
#
# 字段说明：
#   project              项目名（projects/<项目>/）
#   base_version         基线文件头的「版本代号」，也是 CURRENT_VERSION
#   base_path            基线产品文件
#   test_name            测试版目录名（= 测试版版本号，不含语言后缀）
#   test_version         测试版文件头版本代号 / CURRENT_VERSION / 文件名
#                        （dircleaner 没有 _CN 语言后缀传统，故不带）
#   out_dir              落点目录
#   selftest             自检脚本（本目录下）
#   header_indent        「版本代号：」行前导空白，各项目缩进不同
#   has_current_version  产品里是否有 `const CURRENT_VERSION = '...';`
#   about_version_tag    关于弹窗里写死的 `<code>版本</code>`，无则为 None
#   js_banner            脚本头部横幅的完整文本（`* 项目名 · 副标题（版本号）`），
#                        `{v}` 由生成器替换；无则为 None
#   append_history       产品里是否有 devkit 式 VERSION_HISTORY 数组
#   style_block          注入到自检脚本前的附加样式（仅 devkit 既有产物
#                        沿用；其余项目由自检脚本自建样式，保持可移植）
TARGETS = [
    {
        "project": "devkit",
        "base_version": "A1_VI_Φ1_CN",
        "base_path": ROOT / "projects/devkit/code/A1_VI_Φ1/deepseek_A1_VI_Φ1_CN.html",
        "test_name": "A1_VI_Φ1_Test1",
        "test_version": "A1_VI_Φ1_Test1_CN",
        "out_dir": ROOT / "projects/devkit/test/A1_VI_Φ1_Test1",
        "selftest": "test_selftest.js",
        "header_indent": "    ",
        "has_current_version": True,
        "about_version_tag": None,
        "js_banner": None,
        "append_history": True,
        "style_block": (
            "<style>\n"
            "/* 测试版自检按钮的极简样式补充；其余复用产品既有 .icon-btn / .modal */\n"
            "#selftestModal .modal-content { max-height: 86vh; }\n"
            "#selftestModal .modal-body { overflow-y: auto; }\n"
            "</style>\n"
        ),
    },
    {
        "project": "writer",
        "base_version": "A1_I_Φ6_CN",
        "base_path": ROOT / "projects/writer/code/A1_I_Φ6/deepseek_A1_I_Φ6_CN.html",
        "test_name": "A1_I_Φ6_Test1",
        "test_version": "A1_I_Φ6_Test1_CN",
        "out_dir": ROOT / "projects/writer/test/A1_I_Φ6_Test1",
        "selftest": "test_selftest_writer.js",
        "header_indent": "    ",
        "has_current_version": True,
        "about_version_tag": "<code>{v}</code>",
        "js_banner": "* Writer · 小说编辑器（{v}）",
        "append_history": False,
        "style_block": "",
    },
    {
        "project": "persona",
        "base_version": "A1_II_Φ15_CN",
        "base_path": ROOT / "projects/persona/code/A1_II_Φ15/deepseek_A1_II_Φ15_CN.html",
        "test_name": "A1_II_Φ15_Test1",
        "test_version": "A1_II_Φ15_Test1_CN",
        "out_dir": ROOT / "projects/persona/test/A1_II_Φ15_Test1",
        "selftest": "test_selftest_persona.js",
        "header_indent": "    ",
        "has_current_version": True,
        "about_version_tag": "<code>{v}</code>",
        "js_banner": "* Persona · 人设编辑器（{v}）",
        "append_history": False,
        "style_block": "",
    },
    {
        "project": "dircleaner",
        "base_version": "A1_II_Φ9",
        "base_path": ROOT / "projects/dircleaner/code/A1_II_Φ9/deepseek_html_20261115_phi9.html",
        "test_name": "A1_II_Φ9_Test1",
        "test_version": "A1_II_Φ9_Test1",
        "out_dir": ROOT / "projects/dircleaner/test/A1_II_Φ9_Test1",
        "selftest": "test_selftest_dircleaner.js",
        "header_indent": "  ",
        "has_current_version": False,
        "about_version_tag": None,
        "js_banner": None,
        "append_history": False,
        "style_block": "",
    },
    {
        "project": "submerge-pro",
        "base_version": "A1_II_Φ11_CN",
        "base_path": ROOT
        / "projects/submerge-pro/code/A1_II_Φ11/deepseek_A1_II_Φ11_CN.html",
        "test_name": "A1_II_Φ11_Test1",
        "test_version": "A1_II_Φ11_Test1_CN",
        "out_dir": ROOT / "projects/submerge-pro/test/A1_II_Φ11_Test1",
        "selftest": "test_selftest_submerge.js",
        "header_indent": "    ",
        "has_current_version": False,
        "about_version_tag": None,
        "js_banner": None,
        "append_history": False,
        "style_block": "",
    },
]

MARK_START = "<!-- TEST_SELFTEST_START -->"
MARK_END = "<!-- TEST_SELFTEST_END -->"


class BuildError(Exception):
    """单个测试版生成失败（锚点缺失、基线不存在等）。

    调用方按项目捕获并继续处理其余项目：一次运行要能列出全部问题，
    而不是修好第一个才看见第二个。
    """


def die(msg: str) -> None:
    raise BuildError(msg)


def build_one(spec: dict) -> tuple[Path, bytes]:
    base: Path = spec["base_path"]
    if not base.exists():
        die(f"基线文件不存在：{base}")

    src = base.read_text(encoding="utf-8", newline="")
    base_ver: str = spec["base_version"]
    test_name: str = spec["test_name"]
    test_ver: str = spec["test_version"]

    # ---- 1. 文件头版本代号 ----
    old = f"{spec['header_indent']}版本代号：{base_ver}\n"
    if src.count(old) != 1:
        die(f"版本代号锚点未唯一命中（{src.count(old)} 次）：{base}")
    src = src.replace(old, f"{spec['header_indent']}版本代号：{test_ver}\n", 1)

    # ---- 2. <title> 加【测试】前缀 ----
    m = re.search(r"<title>(.*?)</title>", src, re.S)
    if not m:
        die(f"<title> 未找到：{base}")
    src = src[: m.start(1)] + "【测试】" + m.group(1) + src[m.end(1):]

    # ---- 3. CURRENT_VERSION（仅带该常量的项目） ----
    if spec["has_current_version"]:
        old = f"const CURRENT_VERSION = '{base_ver}';"
        if src.count(old) != 1:
            die(f"CURRENT_VERSION 锚点未唯一命中（{src.count(old)} 次）：{base}")
        src = src.replace(old, f"const CURRENT_VERSION = '{test_ver}';", 1)

    # ---- 3b. 关于弹窗里写死的版本号（writer / persona） ----
    if spec["about_version_tag"]:
        old = spec["about_version_tag"].format(v=base_ver)
        if src.count(old) != 1:
            die(f"关于弹窗版本号锚点未唯一命中（{src.count(old)} 次）：{base}")
        src = src.replace(old, spec["about_version_tag"].format(v=test_ver), 1)

    # ---- 3c. 脚本头部横幅（writer / persona） ----
    # 单行注释里的版本号同样会让人误判副本血缘；它不影响任何行为，
    # 但属于「文件里唯一的版本号残留」，一并改写。
    if spec["js_banner"]:
        old = spec["js_banner"].format(v=base_ver)
        if src.count(old) != 1:
            die(f"脚本横幅锚点未唯一命中（{src.count(old)} 次）：{base}")
        src = src.replace(old, spec["js_banner"].format(v=test_ver), 1)

    # ---- 4. VERSION_HISTORY 追加测试版条目（仅 devkit 式结构） ----
    if spec["append_history"]:
        base_trunk = base_ver[:-3]  # 去掉 _CN
        entry = (
            f"            ,{{ version: '{test_name}', note: "
            f"'测试版（基线 {base_ver}）：内置 17 项自检，仅用于内部验证', "
            f"important: true, parent: '{base_trunk}' }}\n"
        )
        # 锚在最后一条 VERSION_HISTORY 之后的 `];`
        idx = src.rfind("\n        ];\n")
        if idx < 0:
            die(f"未找到 VERSION_HISTORY 的收尾 `];`：{base}")
        src = src[: idx + 1] + entry + src[idx + 1:]

    # ---- 5. 注入自检模块 ----
    selftest = SCRIPTS / spec["selftest"]
    if not selftest.exists():
        die(f"自检脚本缺失：{selftest}")
    js = selftest.read_text(encoding="utf-8", newline="")

    base_sha = hashlib.sha256(base.read_bytes()).hexdigest()[:12]
    block = (
        f"\n{MARK_START}\n"
        f"<!-- TEST-BUILD base={base_ver} baseSha={base_sha} -->\n"
        + spec["style_block"]
        + f"<script>\n{js}\n</script>\n"
        f"{MARK_END}\n"
    )
    if src.count("</body>") != 1:
        die(f"</body> 未唯一命中（{src.count('</body>')} 次）：{base}")
    src = src.replace("</body>", block + "</body>", 1)

    out_dir: Path = spec["out_dir"]
    out = out_dir / f"deepseek_{test_ver}.html"
    return out, src.encode("utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    check_only = "--check" in sys.argv

    drift = 0
    failed: list[str] = []
    for spec in TARGETS:
        project = spec["project"]
        try:
            out, data = build_one(spec)
        except BuildError as e:
            # 单个项目失败不打断整批：其余项目照常生成/校验，
            # 最后统一汇总，一次运行能暴露全部问题。
            print(f"[问题] {project}：{e}")
            failed.append(project)
            continue

        rel = out.relative_to(ROOT).as_posix()

        if check_only:
            if not out.exists():
                print(f"[问题] 测试版文件不存在：{rel}")
                drift += 1
                continue
            if out.read_bytes() != data:
                print(f"[问题] 测试版与正式版不同步（需重新生成）：{rel}")
                drift += 1
                continue
            print(f"[信息] 已同步：{rel}")
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            print(f"[写入] {rel}（{len(data) // 1024} KB）")

    if failed:
        print()
        print(f"检查完成：{len(failed)} 个项目无法生成（{'、'.join(failed)}），{drift} 个测试版需要重新生成。")
        return 1

    if drift:
        print()
        print(f"检查完成：{drift} 个测试版需要重新生成。")
        return 1

    if check_only:
        print()
        print("检查完成：全部测试版与正式版同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
