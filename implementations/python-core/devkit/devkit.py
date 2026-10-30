#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DevKit 内核版（Python）

版本：A1_V_Φ9_Fix_Python_CN
对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html

只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
提示词模板拼接。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import json
import sys

CURRENT_VERSION = "A1_V_Φ9_Fix_Python_CN"

SPECS = [
    {"key": "performanceMode", "kind": "boolean", "default": False},
    {"key": "shortcutsEnabled", "kind": "boolean", "default": True},
    {"key": "hideBtnText", "kind": "boolean", "default": False},
    {"key": "promptActionsAlways", "kind": "boolean", "default": True},
    {"key": "specPromptEnabled", "kind": "boolean", "default": True},
    {"key": "inspirationSyncEnabled", "kind": "boolean", "default": True},
    {"key": "themePref", "kind": "enum", "default": "light",
     "values": ["dark", "light", "auto"]},
]


def parse_version(v):
    """与浏览器版一致：分支代号 + 结构段 + 语言后缀。"""
    t = v.strip()
    if not t or len(t) > 100:
        return None
    suffix = None
    core = t
    if t.endswith("_CN"):
        core, suffix = t[:-3], "CN"
    elif t.endswith("_GLOBAL"):
        core, suffix = t[:-7], "GLOBAL"

    parts = core.split("_")
    if not parts:
        return None
    branch = parts[0]
    if not branch.startswith("A"):
        return None
    if not branch[1:].isdigit() and len(branch) > 1:
        return None
    structure = "_".join(parts[1:])
    return branch, structure, suffix


def is_compatible(v):
    parsed = parse_version(v)
    if not parsed:
        return False
    branch, structure, _ = parsed
    if branch.startswith("A2"):
        return False
    if "A2" in structure.split("_"):
        return False
    return True


def normalize_settings(src):
    out = {}
    for spec in SPECS:
        val = src.get(spec["key"])
        if spec["kind"] == "boolean":
            out[spec["key"]] = val if isinstance(val, bool) else spec["default"]
        elif spec["kind"] == "enum":
            out[spec["key"]] = (val if isinstance(val, str) and val in spec["values"]
                                else spec["default"])
    return out


def validate_import(data):
    if "projects" not in data:
        if "project" in data:
            return 1, None
        return 0, "格式错误：不是有效对象"
    projects = data["projects"]
    if not isinstance(projects, list):
        return 0, "格式错误：projects 不是数组"
    if len(projects) > 20:
        return 0, f"项目数 {len(projects)} 超过上限 20"
    for i, p in enumerate(projects):
        if not isinstance(p, dict):
            return 0, f"第 {i+1} 个项目不是对象"
        if not isinstance(p.get("id"), str) or not p["id"]:
            return 0, f"第 {i+1} 个项目缺少 id"
        if not isinstance(p.get("name"), str) or not p["name"]:
            return 0, f"第 {i+1} 个项目缺少 name"
        tabs = p.get("tabs")
        if not isinstance(tabs, list):
            return 0, f"第 {i+1} 个项目缺少 tabs"
        if len(tabs) > 50:
            return 0, f"第 {i+1} 个项目页签超过 50"
        for j, t in enumerate(tabs):
            if not isinstance(t, dict):
                return 0, f"第 {i+1} 个项目第 {j+1} 个页签不是对象"
            if not isinstance(t.get("id"), str) or not t["id"]:
                return 0, f"第 {i+1} 个项目第 {j+1} 个页签字段不完整"
            if not isinstance(t.get("name"), str) or not t["name"]:
                return 0, f"第 {i+1} 个项目第 {j+1} 个页签字段不完整"
    return len(projects), None


def usage():
    print("DevKit 内核版（Python）")
    print("用法: devkit.py <子命令> [参数]")
    print()
    print("子命令:")
    print("  version")
    print("  parse-version <版本号>")
    print("  check-version <版本号>")
    print("  validate-config <配置文件>")
    print("  normalize <设置JSON>")
    print("  compose <模板文件> <灵感> [代码文件]")


def main():
    args = sys.argv[1:]
    if not args:
        usage()
        return 1

    cmd = args[0]

    if cmd == "version":
        print(CURRENT_VERSION)

    elif cmd == "parse-version":
        if len(args) < 2:
            print("缺少版本号", file=sys.stderr)
            return 1
        parsed = parse_version(args[1])
        if not parsed:
            print("版本号不合规", file=sys.stderr)
            return 1
        branch, structure, suffix = parsed
        print(f"分支: {branch}")
        print(f"结构段: {structure or '（无）'}")
        print(f"语言后缀: {suffix or '（无）'}")

    elif cmd == "check-version":
        if len(args) < 2:
            print("缺少版本号", file=sys.stderr)
            return 1
        print("兼容" if is_compatible(args[1]) else "不兼容")
        if not is_compatible(args[1]):
            return 1

    elif cmd == "validate-config":
        if len(args) < 2:
            print("缺少配置文件路径", file=sys.stderr)
            return 1
        try:
            with open(args[1], encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"读取或解析失败: {e}", file=sys.stderr)
            return 1
        ver = data.get("version")
        if isinstance(ver, str) and not is_compatible(ver):
            print(f"配置文件版本不兼容: {ver}", file=sys.stderr)
            return 1
        n, err = validate_import(data)
        if err:
            print(err, file=sys.stderr)
            return 1
        print(f"校验通过，项目数: {n}")

    elif cmd == "normalize":
        if len(args) < 2:
            print("缺少设置 JSON", file=sys.stderr)
            return 1
        try:
            src = json.loads(args[1])
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}", file=sys.stderr)
            return 1
        print(json.dumps(normalize_settings(src), ensure_ascii=False, indent=2))

    elif cmd == "compose":
        if len(args) < 3:
            print("用法: compose <模板文件> <灵感> [代码文件]", file=sys.stderr)
            return 1
        try:
            with open(args[1], encoding="utf-8") as f:
                tpl = f.read()
        except OSError as e:
            print(f"读取模板失败: {e}", file=sys.stderr)
            return 1
        code = "（无代码）"
        if len(args) >= 4:
            try:
                with open(args[3], encoding="utf-8") as f:
                    code = f.read()
            except OSError:
                pass
        print(tpl.replace("{inspiration}", args[2]).replace("{code}", code), end="")

    else:
        print(f"未知子命令: {cmd}", file=sys.stderr)
        usage()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
