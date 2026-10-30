#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DevKit 全功能版（Python / tkinter）

版本：A1_V_Φ9_Fix_Python_CN
对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html

图形界面版：项目/页签管理、灵感输入、提示词预览与复制、配置导入导出、
主题切换（含九款皮肤的合并切换）。数据存 JSON 文件。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

CURRENT_VERSION = "A1_V_Φ9_Fix_Python_CN"

THEMES = {
    "Clean":      {"bg": "#F9FAFB", "fg": "#111827", "accent": "#3B82F6", "panel": "#FFFFFF"},
    "Glass":      {"bg": "#12141a", "fg": "#e8ecf4", "accent": "#6ea8ff", "panel": "#1c2230"},
    "Neon":       {"bg": "#08090d", "fg": "#e9f2ec", "accent": "#bbf351", "panel": "#12161c"},
    "Mono":       {"bg": "#0a0a0a", "fg": "#e6e6e6", "accent": "#00ff41", "panel": "#141414"},
    "Material":   {"bg": "#141218", "fg": "#E6E0E9", "accent": "#D0BCFF", "panel": "#211F26"},
    "Minimal":    {"bg": "#F4F4F1", "fg": "#0C0C09", "accent": "#312C85", "panel": "#FFFFFF"},
    "Premium":    {"bg": "#1c1c1e", "fg": "#f5f5f7", "accent": "#2563EB", "panel": "#242426"},
    "Shadcn":     {"bg": "#ffffff", "fg": "#09090b", "accent": "#18181b", "panel": "#f4f4f5"},
    "Baseline":   {"bg": "#1e1e1e", "fg": "#cccccc", "accent": "#569cd6", "panel": "#252526"},
}

TEMPLATES = [
    ("版本规划", "你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("需求分析", "你是一位资深系统分析师。请对下面需求做全面分析。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("安全审计", "你是一位持有 OSCP 认证的安全专家。请审计下面的代码。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("性能审计", "你是一位性能优化专家。请审计下面的代码。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("结构重构", "你是一位资深架构师。请重构下面的代码。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("单元测试", "请为下面的代码编写单元测试。\n\n需求：{inspiration}\n\n代码：\n{code}"),
    ("空白", "需求：{inspiration}\n\n代码：\n{code}"),
]


def gen_id(prefix):
    return f"{prefix}_{int(time.time() * 1000)}_{id(object()) & 0xFFFF}"


def default_state():
    tabs = [{"id": gen_id("tab"), "type": name, "inspiration": ""}
            for name, _ in TEMPLATES]
    return {
        "version": CURRENT_VERSION,
        "activeProjectId": "proj_1",
        "projects": [{"id": "proj_1", "name": "默认项目", "tabs": tabs,
                      "code": "", "result": ""}],
        "settings": {"theme": "Clean"},
    }


class DevKitApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DevKit（Python tkinter 版）")
        self.root.geometry("1180x800")

        self.state = default_state()
        self.path = None
        self.activeTab = 0
        self.dirty = False

        self._build()
        self.apply_theme()

    def _build(self):
        # 顶栏
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text="主题：").pack(side="left")
        self.themeVar = tk.StringVar(value=self.state["settings"]["theme"])
        themeBox = ttk.Combobox(top, textvariable=self.themeVar, values=list(THEMES),
                                width=12, state="readonly")
        themeBox.pack(side="left")
        themeBox.bind("<<ComboboxSelected>>", lambda e: self.apply_theme())

        ttk.Button(top, text="新建项目", command=self.add_project).pack(side="left", padx=6)
        ttk.Button(top, text="打开配置…", command=self.open_config).pack(side="left")
        ttk.Button(top, text="导出配置", command=self.export_config).pack(side="left", padx=4)
        ttk.Button(top, text="导出代码", command=self.export_code).pack(side="left")
        self.statusLabel = ttk.Label(top, text="就绪", foreground="#555")
        self.statusLabel.pack(side="right")

        # 主体：左页签 + 右编辑
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(paned, width=280)
        paned.add(left, weight=1)
        ttk.Label(left, text="工作流步骤", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=4)
        self.tabList = tk.Listbox(left, height=12)
        self.tabList.pack(fill="x", padx=4)
        self.tabList.bind("<<ListboxSelect>>", self.on_tab_select)

        ttk.Label(left, text="灵感").pack(anchor="w", padx=4, pady=(8, 2))
        self.inspText = tk.Text(left, height=6, wrap="word")
        self.inspText.pack(fill="x", padx=4)
        self.inspText.bind("<KeyRelease>", lambda e: self.on_insp_changed())

        ttk.Label(left, text="组合预览").pack(anchor="w", padx=4, pady=(8, 2))
        self.previewText = tk.Text(left, height=14, wrap="word", state="disabled")
        self.previewText.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        pvRow = ttk.Frame(left)
        pvRow.pack(fill="x", padx=4, pady=4)
        ttk.Button(pvRow, text="复制", command=self.copy_preview).pack(side="left")
        ttk.Button(pvRow, text="仅需求", command=self.copy_insp_only).pack(side="left", padx=4)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)
        ttk.Label(right, text="代码编辑区").pack(anchor="w", padx=6, pady=(4, 2))
        self.codeText = tk.Text(right, wrap="none", undo=True)
        self.codeText.pack(fill="both", expand=True, padx=6)
        self.codeText.bind("<KeyRelease>", lambda e: self.on_code_changed())

        self.countLabel = ttk.Label(right, text="", foreground="#555")
        self.countLabel.pack(anchor="w", padx=6, pady=2)

        ttk.Label(right, text="AI 处理结果").pack(anchor="w", padx=6, pady=(6, 2))
        self.resultText = tk.Text(right, height=8, wrap="none")
        self.resultText.pack(fill="x", padx=6, pady=(0, 6))
        rRow = ttk.Frame(right)
        rRow.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(rRow, text="用结果覆盖代码区", command=self.overwrite_code).pack(side="left")

        self.refresh_tabs()
        self.load_tab(0)

    # ---------- 主题 ----------
    def apply_theme(self):
        name = self.themeVar.get()
        t = THEMES.get(name, THEMES["Baseline"])
        self.state["settings"]["theme"] = name
        self.root.configure(bg=t["bg"])
        style = ttk.Style()
        style.configure("TFrame", background=t["bg"])
        style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        style.configure("TButton", background=t["panel"], foreground=t["fg"])
        for w in (self.inspText, self.previewText, self.codeText, self.resultText):
            w.configure(bg=t["panel"], fg=t["fg"], insertbackground=t["fg"],
                        selectbackground=t["accent"])
        self.tabList.configure(bg=t["panel"], fg=t["fg"],
                               selectbackground=t["accent"], selectforeground=t["bg"])

    # ---------- 页签 ----------
    def current_project(self):
        pid = self.state["activeProjectId"]
        return next((p for p in self.state["projects"] if p["id"] == pid), None)

    def refresh_tabs(self):
        proj = self.current_project()
        self.tabList.delete(0, "end")
        if not proj:
            return
        for t in proj["tabs"]:
            self.tabList.insert("end", t["type"])
        if proj["tabs"]:
            self.tabList.selection_set(self.activeTab)

    def on_tab_select(self, _):
        sel = self.tabList.curselection()
        if not sel:
            return
        self.save_tab()
        self.load_tab(sel[0])

    def load_tab(self, idx):
        proj = self.current_project()
        if not proj or idx >= len(proj["tabs"]):
            return
        self.activeTab = idx
        tab = proj["tabs"][idx]
        self.inspText.delete("1.0", "end")
        self.inspText.insert("1.0", tab.get("inspiration", ""))
        self.codeText.delete("1.0", "end")
        self.codeText.insert("1.0", proj.get("code", ""))
        self.resultText.delete("1.0", "end")
        self.resultText.insert("1.0", proj.get("result", ""))
        self.refresh_preview()

    def save_tab(self):
        proj = self.current_project()
        if not proj or self.activeTab >= len(proj["tabs"]):
            return
        proj["tabs"][self.activeTab]["inspiration"] = self.inspText.get("1.0", "end-1c")
        proj["code"] = self.codeText.get("1.0", "end-1c")
        proj["result"] = self.resultText.get("1.0", "end-1c")

    def on_insp_changed(self):
        self.save_tab()
        self.refresh_preview()
        self.dirty = True

    def on_code_changed(self):
        self.save_tab()
        self.refresh_preview()
        body = self.codeText.get("1.0", "end-1c")
        self.countLabel.config(text=f"{len(body)} 字符 · {body.count(chr(10)) + 1} 行")
        self.dirty = True

    # ---------- 预览 ----------
    def compose(self):
        proj = self.current_project()
        if not proj or self.activeTab >= len(proj["tabs"]):
            return ""
        tab = proj["tabs"][self.activeTab]
        tmpl = next((t for n, t in TEMPLATES if n == tab["type"]), "{inspiration}\n{code}")
        insp = tab.get("inspiration") or "（无需求）"
        code = proj.get("code") or "（无代码）"
        return tmpl.replace("{inspiration}", insp).replace("{code}", code)

    def refresh_preview(self):
        text = self.compose()
        self.previewText.config(state="normal")
        self.previewText.delete("1.0", "end")
        self.previewText.insert("1.0", text)
        self.previewText.config(state="disabled")

    def copy_preview(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.compose())
        self.statusLabel.config(text="✅ 已复制")

    def copy_insp_only(self):
        insp = self.inspText.get("1.0", "end-1c") or "（无需求）"
        code = self.codeText.get("1.0", "end-1c") or "（无代码）"
        self.root.clipboard_clear()
        self.root.clipboard_append(f"需求：{insp}\n\n代码：\n{code}")
        self.statusLabel.config(text="✅ 已复制需求")

    # ---------- 项目 ----------
    def add_project(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("新建项目", "项目名称：", parent=self.root)
        if not name:
            return
        self.save_tab()
        proj = {"id": gen_id("proj"), "name": name,
                "tabs": [{"id": gen_id("tab"), "type": n, "inspiration": ""} for n, _ in TEMPLATES],
                "code": "", "result": ""}
        self.state["projects"].append(proj)
        self.state["activeProjectId"] = proj["id"]
        self.activeTab = 0
        self.refresh_tabs()
        self.load_tab(0)
        self.statusLabel.config(text=f"已新建项目：{name}")

    # ---------- 导入导出 ----------
    def open_config(self):
        p = filedialog.askopenfilename(title="打开配置", filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        if "projects" not in data:
            messagebox.showerror("格式错误", "缺少 projects 字段")
            return
        self.state["projects"] = data["projects"]
        self.state["activeProjectId"] = data.get("activeProjectId", data["projects"][0]["id"])
        if "settings" in data and isinstance(data["settings"], dict):
            theme = data["settings"].get("theme")
            if theme in THEMES:
                self.themeVar.set(theme)
                self.apply_theme()
        self.path = p
        self.activeTab = 0
        self.refresh_tabs()
        self.load_tab(0)
        self.statusLabel.config(text=f"已导入：{len(data['projects'])} 个项目")

    def export_config(self):
        self.save_tab()
        self.state["version"] = CURRENT_VERSION
        p = filedialog.asksaveasfilename(defaultextension=".json",
                                          initialfile="devkit_config.json",
                                          filetypes=[("JSON", "*.json")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        self.path = p
        self.dirty = False
        self.statusLabel.config(text=f"已导出：{p}")

    def export_code(self):
        body = self.codeText.get("1.0", "end-1c")
        if not body:
            messagebox.showinfo("提示", "代码区为空")
            return
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                          initialfile="codeoutput", filetypes=[("全部", "*.*")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        self.statusLabel.config(text=f"已导出代码：{p}")

    def overwrite_code(self):
        res = self.resultText.get("1.0", "end-1c")
        if not res:
            messagebox.showinfo("提示", "结果区为空")
            return
        self.codeText.delete("1.0", "end")
        self.codeText.insert("1.0", res)
        self.resultText.delete("1.0", "end")
        self.on_code_changed()
        self.statusLabel.config(text="已覆盖并清空")


def main():
    root = tk.Tk()
    DevKitApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
