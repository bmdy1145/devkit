#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DirCleaner 内核版（Python）

版本：A1_II_Φ8_Python_CN
对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html

只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import argparse
import os
import sys

MAX_RECURSION_DEPTH = 20
MAX_FILE_COUNT = 10000
MAX_SCAN_FOR_EXE = 2000
WHITELIST_MARKER_FILENAME = ".dircleaner_whitelist"

CRITICAL_DIR_NAMES = {
    "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
    "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
    "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
}


def format_bytes(n: int) -> str:
    if n == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.0f} {units[i]}" if i == 0 else f"{v:.2f} {units[i]}"


def contains_executables(path: str, depth: int, counter: list) -> bool:
    """与浏览器版 containsExecutables 等价。counter 用单元素列表模拟引用传递。"""
    if depth > 10 or counter[0] >= MAX_SCAN_FOR_EXE:
        return False
    try:
        entries = list(os.scandir(path))
    except OSError:
        return False
    for e in entries:
        if counter[0] >= MAX_SCAN_FOR_EXE:
            break
        try:
            if e.is_dir(follow_symlinks=False):
                if contains_executables(e.path, depth + 1, counter):
                    return True
            else:
                counter[0] += 1
                n = e.name.lower()
                if n.endswith(".exe") or n.endswith(".dll"):
                    return True
        except OSError:
            continue
    return False


def clear_directory(path, depth, file_count, keep_marker, dry_run, stats):
    if depth > MAX_RECURSION_DEPTH:
        raise RuntimeError(f"已达到最大目录深度限制 ({MAX_RECURSION_DEPTH})")
    try:
        entries = list(os.scandir(path))
    except OSError as e:
        raise RuntimeError(f"无法读取 {path}: {e}")

    for e in entries:
        name = e.name
        try:
            is_dir = e.is_dir(follow_symlinks=False)
        except OSError as err:
            stats["errors"].append(f"无法读取 {e.path}: {err}")
            continue

        if is_dir:
            clear_directory(e.path, depth + 1, file_count, keep_marker, dry_run, stats)
            if dry_run:
                print(f"[dry-run] 将删除目录: {name}")
                stats["deleted_dirs"] += 1
            else:
                try:
                    os.rmdir(e.path)
                    print(f"已删除目录: {name}")
                    stats["deleted_dirs"] += 1
                except OSError as err:
                    msg = f"无法删除目录 {name}: {err}"
                    stats["errors"].append(msg)
                    print(msg, file=sys.stderr)
            continue

        if file_count[0] >= MAX_FILE_COUNT:
            raise RuntimeError(f"已达到最大文件数限制 ({MAX_FILE_COUNT})")
        if keep_marker and name == WHITELIST_MARKER_FILENAME:
            print(f"跳过白名单标记文件: {name}")
            continue

        try:
            size = e.stat(follow_symlinks=False).st_size
        except OSError:
            size = 0

        if dry_run:
            print(f"[dry-run] 将删除文件: {name} ({format_bytes(size)})")
        else:
            try:
                os.remove(e.path)
                print(f"已删除文件: {name} ({format_bytes(size)})")
            except OSError as err:
                msg = f"无法删除 {name}: {err}"
                stats["errors"].append(msg)
                print(msg, file=sys.stderr)
                continue
        stats["deleted_files"] += 1
        stats["total_bytes"] += size
        file_count[0] += 1


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="dircleaner",
        description="DirCleaner 内核版（Python）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", help="要清空的目录")
    ap.add_argument("--dry-run", action="store_true", help="只列出将删除的内容，不实际删除")
    ap.add_argument("--whitelist", action="store_true", help="该目录在白名单中（保留标记文件，跳过名称确认）")
    ap.add_argument("--confirm", default="", help="确认待清空目录的名称（非白名单目录必须提供且一致）")
    args = ap.parse_args()

    target = args.target
    if not os.path.isdir(target):
        print(f"错误：{target} 不是目录", file=sys.stderr)
        return 1

    dir_name = os.path.basename(os.path.normpath(os.path.abspath(target)))
    if dir_name in CRITICAL_DIR_NAMES:
        print(f"错误：{dir_name} 是受保护的关键目录，禁止清空", file=sys.stderr)
        return 1
    if not args.whitelist:
        if not args.confirm:
            print(f'错误：非白名单目录必须用 --confirm "{dir_name}" 确认', file=sys.stderr)
            return 1
        if args.confirm != dir_name:
            print(f'错误：确认名称 "{args.confirm}" 与目录名 "{dir_name}" 不一致', file=sys.stderr)
            return 1

    counter = [0]
    if contains_executables(target, 0, counter):
        print("⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。")
        try:
            ans = input("确认继续？输入 yes: ")
        except EOFError:
            ans = ""
        if ans.strip() != "yes":
            print("已取消。")
            return 1

    print("===== 开始清空操作 =====")
    print(f"目标目录: {target}")
    if args.dry_run:
        print("模式: 试运行（不实际删除）")

    stats = {"deleted_files": 0, "deleted_dirs": 0, "total_bytes": 0, "errors": []}
    file_count = [0]
    try:
        clear_directory(target, 0, file_count, args.whitelist, args.dry_run, stats)
    except RuntimeError as e:
        print(f"操作中止: {e}", file=sys.stderr)
        print(f"已删除文件: {stats['deleted_files']}，目录: {stats['deleted_dirs']}，"
              f"释放空间: {format_bytes(stats['total_bytes'])}")
        return 1

    print("===== 清空完成 =====")
    print(f"本次删除文件: {stats['deleted_files']}")
    print(f"本次删除目录: {stats['deleted_dirs']}")
    print(f"本次释放空间: {format_bytes(stats['total_bytes'])}")
    if stats["errors"]:
        print(f"错误数: {len(stats['errors'])}")
        for e in stats["errors"]:
            print(f"  {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
