#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从正式版产品文件生成测试版（注入内置自检）。

测试版 = 正式版的逐字节副本 + 版本标识改写 + TEST_SELFTEST 注入。
手改测试版会在 CI 的 --check 模式下报「漂移」，必须重新生成。

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
TARGETS = [
    {
        "project": "devkit",
        "base_version": "A1_VI_Φ1_CN",
        "base_path": ROOT / "projects/devkit/code/A1_VI_Φ1/deepseek_A1_VI_Φ1_CN.html",
        "test_name": "A1_VI_Φ1_Test1",
        "out_dir": ROOT / "projects/devkit/test/A1_VI_Φ1_Test1",
    },
]

SELFTEST_JS = SCRIPTS / "test_selftest.js"

MARK_START = "<!-- TEST_SELFTEST_START -->"
MARK_END = "<!-- TEST_SELFTEST_END -->"


def die(msg: str) -> None:
    print(f"[问题] {msg}", file=sys.stderr)
    raise SystemExit(1)


def build_one(spec: dict) -> tuple[Path, bytes]:
    base: Path = spec["base_path"]
    if not base.exists():
        die(f"基线文件不存在：{base}")

    src = base.read_text(encoding="utf-8", newline="")
    base_ver: str = spec["base_version"]
    test_name: str = spec["test_name"]
    test_ver = f"{test_name}_CN"

    # ---- 1. 文件头版本代号 ----
    old = f"    版本代号：{base_ver}\n"
    if src.count(old) != 1:
        die(f"版本代号锚点未唯一命中（{src.count(old)} 次）")
    src = src.replace(old, f"    版本代号：{test_ver}\n", 1)

    # ---- 2. <title> 加【test】前缀 ----
    m = re.search(r"<title>(.*?)</title>", src, re.S)
    if not m:
        die("<title> 未找到")
    src = src[:m.start(1)] + "【测试】" + m.group(1) + src[m.end(1):]

    # ---- 3. CURRENT_VERSION ----
    old = f"const CURRENT_VERSION = '{base_ver}';"
    if src.count(old) != 1:
        die(f"CURRENT_VERSION 锚点未唯一命中（{src.count(old)} 次）")
    src = src.replace(old, f"const CURRENT_VERSION = '{test_ver}';", 1)

    # ---- 4. VERSION_HISTORY 追加测试版条目 ----
    base_trunk = base_ver[:-3]  # 去掉 _CN
    entry = (
        f"            ,{{ version: '{test_name}', note: "
        f"'测试版（基线 {base_ver}）：内置 17 项自检，仅用于内部验证', "
        f"important: true, parent: '{base_trunk}' }}\n"
    )
    # 锚在最后一条 VERSION_HISTORY 之后的 `];`
    idx = src.rfind("\n        ];\n")
    if idx < 0:
        die("未找到 VERSION_HISTORY 的收尾 `];`")
    src = src[: idx + 1] + entry + src[idx + 1:]

    # ---- 5. 注入自检模块 ----
    if not SELFTEST_JS.exists():
        die(f"自检脚本缺失：{SELFTEST_JS}")
    js = SELFTEST_JS.read_text(encoding="utf-8", newline="")

    base_sha = hashlib.sha256(base.read_bytes()).hexdigest()[:12]
    block = (
        f"\n{MARK_START}\n"
        f"<!-- TEST-BUILD base={base_ver} baseSha={base_sha} -->\n"
        f"<style>\n"
        f"/* 测试版自检按钮的极简样式补充；其余复用产品既有 .icon-btn / .modal */\n"
        f"#selftestModal .modal-content {{ max-height: 86vh; }}\n"
        f"#selftestModal .modal-body {{ overflow-y: auto; }}\n"
        f"</style>\n"
        f"<script>\n{js}\n</script>\n"
        f"{MARK_END}\n"
    )
    if src.count("</body>") != 1:
        die(f"</body> 未唯一命中（{src.count('</body>')} 次）")
    src = src.replace("</body>", block + "</body>", 1)

    out_dir: Path = spec["out_dir"]
    out = out_dir / f"deepseek_{test_ver}.html"
    return out, src.encode("utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    check_only = "--check" in sys.argv

    drift = 0
    for spec in TARGETS:
        out, data = build_one(spec)
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
