#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DirCleaner 全功能版（Python / tkinter）

版本：A1_II_Φ8_Python_CN
对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html

图形界面版的完整实现：目录选择、关键目录防护、白名单、可执行文件扫描、
名称确认、进度与统计，与浏览器版一一对应。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

MAX_RECURSION_DEPTH = 20
MAX_FILE_COUNT = 10000
MAX_SCAN_FOR_EXE = 2000
WHITELIST_MARKER = ".dircleaner_whitelist"

CRITICAL_DIR_NAMES = {
    "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
    "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
    "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
}


def format_bytes(n):
    if n == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.0f} {units[i]}" if i == 0 else f"{v:.2f} {units[i]}"


def contains_executables(path, depth, counter):
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


class DirCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DirCleaner（Python tkinter 版）")
        self.root.geometry("760x680")

        self.target = None
        self.exe_found = False
        self.exe_scanned = False
        self.cancelled = False
        self.log_queue = queue.Queue()
        self.worker = None

        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}

        # 目录选择
        f1 = ttk.LabelFrame(self.root, text="1. 选择目录")
        f1.pack(fill="x", **pad)
        self.path_var = tk.StringVar(value="（未选择）")
        ttk.Label(f1, textvariable=self.path_var, foreground="#555").pack(anchor="w", padx=8, pady=4)
        row = ttk.Frame(f1)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Button(row, text="浏览目录…", command=self.choose_dir).pack(side="left")
        ttk.Button(row, text="加入白名单", command=self.add_whitelist).pack(side="left", padx=6)
        self.wl_label = ttk.Label(row, text="", foreground="#0a7a2f")
        self.wl_label.pack(side="left", padx=10)

        # 安全提示
        f2 = ttk.LabelFrame(self.root, text="2. 安全检查")
        f2.pack(fill="x", **pad)
        self.critical_label = ttk.Label(f2, text="请先选择目录", foreground="#888")
        self.critical_label.pack(anchor="w", padx=8, pady=4)
        self.exe_label = ttk.Label(f2, text="", foreground="#b45309")
        self.exe_label.pack(anchor="w", padx=8, pady=4)

        # 确认
        f3 = ttk.LabelFrame(self.root, text="3. 确认")
        f3.pack(fill="x", **pad)
        self.confirm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="我了解此操作不可恢复", variable=self.confirm_var,
                        command=self.update_start_state).pack(anchor="w", padx=8, pady=4)
        crow = ttk.Frame(f3)
        crow.pack(fill="x", padx=8, pady=4)
        ttk.Label(crow, text="输入目录名确认：").pack(side="left")
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(crow, textvariable=self.name_var, width=30)
        self.name_entry.pack(side="left", padx=6)
        self.name_entry.bind("<KeyRelease>", lambda e: self.update_start_state())
        self.exe_confirm_var = tk.BooleanVar(value=False)
        self.exe_confirm_cb = ttk.Checkbutton(
            f3, text="该目录含可执行文件，我了解风险仍要删除",
            variable=self.exe_confirm_var, command=self.update_start_state)
        self.exe_confirm_cb.pack(anchor="w", padx=8, pady=4)

        # 操作
        f4 = ttk.Frame(self.root)
        f4.pack(fill="x", **pad)
        self.start_btn = ttk.Button(f4, text="开始清空", command=self.start, state="disabled")
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(f4, text="取消", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        self.scan_btn = ttk.Button(f4, text="扫描可执行文件", command=self.scan_exe)
        self.scan_btn.pack(side="left", padx=6)

        # 进度
        f5 = ttk.LabelFrame(self.root, text="4. 进度")
        f5.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(f5, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=8, pady=6)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(f5, textvariable=self.status_var).pack(anchor="w", padx=8, pady=2)

        # 统计
        f6 = ttk.LabelFrame(self.root, text="5. 统计")
        f6.pack(fill="x", **pad)
        srow = ttk.Frame(f6)
        srow.pack(fill="x", padx=8, pady=6)
        self.stat_vars = {}
        for key, label in (("files", "文件"), ("dirs", "目录"), ("bytes", "大小"), ("errors", "错误")):
            box = ttk.Frame(srow)
            box.pack(side="left", expand=True, fill="x")
            v = tk.StringVar(value="-")
            self.stat_vars[key] = v
            ttk.Label(box, textvariable=v, font=("Segoe UI", 14, "bold")).pack()
            ttk.Label(box, text=label, foreground="#666").pack()

        # 日志
        f7 = ttk.LabelFrame(self.root, text="6. 日志")
        f7.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(f7, height=10, state="disabled", wrap="none")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=6)

        self.root.after(100, self.pump_log)

    def log(self, msg):
        self.log_queue.put(msg)

    def pump_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.pump_log)

    def choose_dir(self):
        path = filedialog.askdirectory(title="选择要清空的目录")
        if not path:
            return
        self.target = os.path.abspath(path)
        self.path_var.set(self.target)
        name = os.path.basename(self.target)

        self.exe_found = False
        self.exe_scanned = False
        self.exe_label.config(text="")
        self.confirm_var.set(False)
        self.name_var.set("")
        for v in self.stat_vars.values():
            v.set("-")

        if name in CRITICAL_DIR_NAMES:
            self.critical_label.config(text=f"✗ {name} 是受保护的关键目录，禁止清空", foreground="#b00020")
        else:
            self.critical_label.config(text=f"✓ 可以清空（目录名：{name}）", foreground="#0a7a2f")
            self.log(f"已选择: {self.target}")

        self.update_whitelist_label()
        self.update_start_state()

    def is_whitelisted(self):
        if not self.target:
            return False
        return os.path.isfile(os.path.join(self.target, WHITELIST_MARKER))

    def update_whitelist_label(self):
        if self.target and self.is_whitelisted():
            self.wl_label.config(text="✓ 已在白名单（跳过名称确认）")
            self.name_entry.config(state="disabled")
        else:
            self.wl_label.config(text="")
            self.name_entry.config(state="normal")

    def add_whitelist(self):
        if not self.target:
            messagebox.showinfo("提示", "请先选择目录")
            return
        name = os.path.basename(self.target)
        if name in CRITICAL_DIR_NAMES:
            messagebox.showerror("拒绝", "关键目录不能加入白名单")
            return
        marker = os.path.join(self.target, WHITELIST_MARKER)
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("DirCleaner Whitelist Marker")
            self.log(f"已创建白名单标记：{marker}")
            messagebox.showinfo("成功", "已加入白名单")
        except OSError as e:
            messagebox.showerror("失败", f"创建标记文件失败：{e}")
        self.update_whitelist_label()
        self.update_start_state()

    def scan_exe(self):
        if not self.target:
            return
        self.scan_btn.config(state="disabled")
        self.status_var.set("正在扫描可执行文件…")

        def work():
            counter = [0]
            found = contains_executables(self.target, 0, counter)
            self.exe_found = found
            self.exe_scanned = True
            def done():
                self.scan_btn.config(state="normal")
                if found:
                    self.exe_label.config(text="⚠️ 发现可执行文件（.exe / .dll），需额外确认")
                    self.exe_confirm_cb.pack(anchor="w", padx=8, pady=4)
                else:
                    self.exe_label.config(text="✓ 未发现可执行文件", foreground="#0a7a2f")
                    self.exe_confirm_cb.pack_forget()
                self.status_var.set("扫描完成")
                self.update_start_state()
            self.root.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def update_start_state(self):
        if not self.target:
            self.start_btn.config(state="disabled")
            return
        name = os.path.basename(self.target)
        if name in CRITICAL_DIR_NAMES:
            self.start_btn.config(state="disabled")
            return
        ok = self.confirm_var.get()
        if not self.is_whitelisted():
            ok = ok and self.name_var.get().strip() == name
        if self.exe_found and not self.exe_confirm_var.get():
            ok = False
        self.start_btn.config(state="normal" if ok else "disabled")

    def start(self):
        name = os.path.basename(self.target)
        if not messagebox.askyesno("最后确认", f"确定要清空目录 \"{name}\" 下的所有内容吗？\n此操作不可恢复。"):
            return
        self.cancelled = False
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress["value"] = 0
        self.status_var.set("正在清空…")
        self.log("===== 开始清空 =====")

        def work():
            stats = {"files": 0, "dirs": 0, "bytes": 0, "errors": []}
            try:
                self._clear(self.target, 0, [0], self.is_whitelisted(), stats)
            except Exception as e:
                stats["errors"].append(str(e))
            self.root.after(0, lambda: self.finish(stats))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _clear(self, path, depth, file_count, keep_marker, stats):
        if self.cancelled:
            raise RuntimeError("操作已取消")
        if depth > MAX_RECURSION_DEPTH:
            raise RuntimeError(f"已达到最大目录深度限制 ({MAX_RECURSION_DEPTH})")
        try:
            entries = list(os.scandir(path))
        except OSError as e:
            raise RuntimeError(f"无法读取 {path}: {e}")
        for e in entries:
            if self.cancelled:
                raise RuntimeError("操作已取消")
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                self._clear(e.path, depth + 1, file_count, keep_marker, stats)
                try:
                    os.rmdir(e.path)
                    stats["dirs"] += 1
                    self.log(f"已删除目录: {e.name}")
                except OSError as err:
                    stats["errors"].append(f"无法删除目录 {e.name}: {err}")
            else:
                if file_count[0] >= MAX_FILE_COUNT:
                    raise RuntimeError(f"已达到最大文件数限制 ({MAX_FILE_COUNT})")
                if keep_marker and e.name == WHITELIST_MARKER:
                    self.log(f"跳过白名单标记: {e.name}")
                    continue
                try:
                    size = e.stat(follow_symlinks=False).st_size
                except OSError:
                    size = 0
                try:
                    os.remove(e.path)
                    stats["files"] += 1
                    stats["bytes"] += size
                    file_count[0] += 1
                    self.log(f"已删除文件: {e.name} ({format_bytes(size)})")
                except OSError as err:
                    stats["errors"].append(f"无法删除 {e.name}: {err}")

    def finish(self, stats):
        self.progress["value"] = 100
        self.cancel_btn.config(state="disabled")
        self.start_btn.config(state="normal")
        self.status_var.set("完成" if not stats["errors"] else f"完成，{len(stats['errors'])} 个错误")
        self.stat_vars["files"].set(str(stats["files"]))
        self.stat_vars["dirs"].set(str(stats["dirs"]))
        self.stat_vars["bytes"].set(format_bytes(stats["bytes"]))
        self.stat_vars["errors"].set(str(len(stats["errors"])))
        self.log("===== 清空完成 =====")
        for e in stats["errors"]:
            self.log("  " + e)
        self.update_start_state()

    def cancel(self):
        self.cancelled = True
        self.status_var.set("正在取消…")


def main():
    root = tk.Tk()
    DirCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
