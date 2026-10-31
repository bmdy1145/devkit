#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writer 全功能版（Python / tkinter）

版本：A1_I_Φ5_Python_CN
对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html

图形界面版：左侧章节树（书/卷/章）、中间正文编辑、右侧资料库与提示词预览、
字数统计、自动保存，与浏览器版的左侧单列四页签形态对应。

数据存 JSON 文件（浏览器版用 IndexedDB，桌面版用文件更合适）。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

COUNTER = [0]

# 人称转换的目标人称。key 与 HTML 版 A1_I_Φ5_CN 的 #povTarget option
# value 一一对应。
POV_TARGETS = {
    "first": "第一人称（我）",
    "second": "第二人称（你）",
    "third": "第三人称（他 / 她 / 它）",
}


def build_pov_prompt(body, chars, target, keep_inner):
    """合成「人称转换」提示词，与 HTML 版 A1_I_Φ5_CN 的 pov 模板一致。"""
    inner = (
        "保留：原视角的内心活动改写为目标视角可知的部分"
        "（用表情、动作、语气或外部观察替代直接叙述他人内心）"
        if keep_inner
        else "不保留：删去目标视角无法感知的心理描写，只保留外在可见的行为与对白"
    )
    return "\n".join([
        f"你是一位精通叙述视角的小说编辑。请把下面的正文转换为【{target}】，"
        "情节、人物、场景与对白内容一律不变，只换叙述人称与视角。",
        "",
        "【目标人称】" + target,
        "",
        "【心理描写处理】" + inner,
        "",
        "【相关设定】",
        chars,
        "",
        "【需要转换的正文】",
        body,
        "",
        "【转换规则】",
        "1) 只改人称代词与由此引起的视角变化，不增删情节、"
        "不改变人物性格与说话方式；",
        "2) 第一人称：叙述者用「我」，只能写出「我」能感知到的内容"
        "（看到、听到、想到），不能直接叙述旁人心里在想什么；",
        "3) 第二人称：叙述者用「你」，把读者带入场景，"
        "动作与感受都落在「你」身上；",
        "4) 第三人称：叙述者用「他 / 她 / 它」或人物姓名，"
        "人物之间用姓名或称谓区分，避免代词指向不明；",
        "5) 时间线、场景顺序、对白内容保持原样，"
        "对白中人物自称按其在故事中的实际人称调整；",
        "6) 转换后通读一遍，确保没有残留的原人称代词、"
        "没有视角越界、没有半途切换人称。",
        "",
        "【输出要求】直接输出转换后的完整正文，不要加解释、不要加标题、"
        "不要用「以下是」之类的开场白，便于直接替换当前章。",
    ])


def gen_id(prefix):
    COUNTER[0] += 1
    return f"{prefix}_{int(time.time() * 1000)}_{COUNTER[0]}"


def now_ts():
    return int(time.time() * 1000)


def _is_cjk(code):
    return (0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF
            or 0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7AF
            or 0xF900 <= code <= 0xFAFF)


def count_words(text):
    total = 0
    in_latin = False
    for ch in text:
        if _is_cjk(ord(ch)):
            total += 1
            in_latin = False
        elif ch.isalnum():
            if not in_latin:
                total += 1
                in_latin = True
        else:
            in_latin = False
    return total


EMPTY = {"books": [], "volumes": [], "chapters": [], "entities": []}


def load(p):
    if not os.path.exists(p):
        return dict(EMPTY)
    with open(p, encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return dict(EMPTY)
    d = json.loads(raw)
    for k in EMPTY:
        d.setdefault(k, [])
    return d


def save(p, lib):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)


class WriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Writer（Python tkinter 版）")
        self.root.geometry("1180x780")

        self.libPath = None
        self.lib = dict(EMPTY)
        self.bookId = None
        self.volumeId = None
        self.chapterId = None
        self.dirty = False

        self._build()
        self.root.after(1500, self._autosave)

    # ---------- UI ----------
    def _build(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Button(bar, text="新建/打开库…", command=self.open_lib).pack(side="left")
        ttk.Button(bar, text="保存", command=self.save_lib).pack(side="left", padx=6)
        self.libLabel = ttk.Label(bar, text="（未打开）", foreground="#555")
        self.libLabel.pack(side="left", padx=10)

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        # 左：章节树
        left = ttk.Frame(paned, width=280)
        paned.add(left, weight=1)
        ttk.Label(left, text="章节树", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=4)
        self.tree = ttk.Treeview(left, show="tree", height=20)
        self.tree.pack(fill="both", expand=True, padx=4)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        btnRow = ttk.Frame(left)
        btnRow.pack(fill="x", padx=4, pady=4)
        ttk.Button(btnRow, text="+卷", width=5, command=self.add_volume).pack(side="left")
        ttk.Button(btnRow, text="+章", width=5, command=self.add_chapter).pack(side="left", padx=3)
        ttk.Button(btnRow, text="删章", width=6, command=self.del_chapter).pack(side="left")

        # 中：正文
        center = ttk.Frame(paned)
        paned.add(center, weight=3)
        self.titleVar = tk.StringVar()
        ttk.Entry(center, textvariable=self.titleVar).pack(fill="x", padx=6, pady=(4, 2))
        self.titleVar.trace_add("write", lambda *_: self.mark_dirty())
        self.text = tk.Text(center, wrap="word", undo=True)
        self.text.pack(fill="both", expand=True, padx=6, pady=4)
        self.text.bind("<<Modified>>", self.on_text_modified)
        self.statusVar = tk.StringVar(value="就绪")
        ttk.Label(center, textvariable=self.statusVar, foreground="#555").pack(anchor="w", padx=6)

        # 右：资料库 + 提示词
        right = ttk.Notebook(paned, width=320)
        paned.add(right, weight=1)

        entFrame = ttk.Frame(right)
        right.add(entFrame, text="资料")
        self.entList = tk.Listbox(entFrame, height=14)
        self.entList.pack(fill="both", expand=True, padx=4, pady=4)
        eRow = ttk.Frame(entFrame)
        eRow.pack(fill="x", padx=4, pady=4)
        ttk.Button(eRow, text="+ 资料", command=self.add_entity).pack(side="left")

        promptFrame = ttk.Frame(right)
        right.add(promptFrame, text="提示词")
        ttk.Button(promptFrame, text="生成续写提示词", command=self.gen_prompt).pack(anchor="w", padx=4, pady=4)
        povRow = ttk.Frame(promptFrame)
        povRow.pack(fill="x", padx=4, pady=2)
        ttk.Label(povRow, text="目标人称").pack(side="left")
        self.povVar = tk.StringVar(value="third")
        ttk.Combobox(povRow, textvariable=self.povVar, width=20, state="readonly",
                     values=["first", "second", "third"]).pack(side="left", padx=4)
        self.povInnerVar = tk.BooleanVar(value=True)
        ttk.Checkbutton(povRow, text="保留心理描写",
                        variable=self.povInnerVar).pack(side="left")
        ttk.Button(povRow, text="人称转换", command=self.gen_pov).pack(side="left", padx=4)
        self.promptText = tk.Text(promptFrame, height=20, wrap="word")
        self.promptText.pack(fill="both", expand=True, padx=4, pady=4)

    # ---------- 库 ----------
    def open_lib(self):
        p = filedialog.askopenfilename(title="打开或新建库", defaultextension=".json",
                                       filetypes=[("JSON", "*.json"), ("全部", "*.*")])
        if not p:
            return
        self.libPath = p
        self.lib = load(p) if os.path.exists(p) else dict(EMPTY)
        self.libLabel.config(text=p)
        if not self.lib["books"]:
            title = tk.simpledialog.askstring("新建书籍", "请输入书名：", parent=self.root) if hasattr(tk, "simpledialog") else None
            if title is None:
                from tkinter import simpledialog
                title = simpledialog.askstring("新建书籍", "请输入书名：", parent=self.root)
            if title:
                b = {"id": gen_id("book"), "title": title, "author": "", "updated_at": now_ts()}
                self.lib["books"].append(b)
                self.bookId = b["id"]
        else:
            self.bookId = self.lib["books"][0]["id"]
        self.refresh_tree()
        self.refresh_entities()

    def save_lib(self):
        if not self.libPath:
            return
        self.sync_current()
        save(self.libPath, self.lib)
        self.dirty = False
        self.statusVar.set(f"已保存 {time.strftime('%H:%M:%S')}")

    def _autosave(self):
        if self.dirty and self.libPath:
            self.save_lib()
        self.root.after(1500, self._autosave)

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for v in sorted([x for x in self.lib["volumes"] if x["book_id"] == self.bookId],
                        key=lambda x: x["order"]):
            vid = self.tree.insert("", "end", iid=v["id"], text=v["title"], open=True)
            for c in sorted([x for x in self.lib["chapters"] if x["volume_id"] == v["id"]],
                            key=lambda x: x["order"]):
                self.tree.insert(vid, "end", iid=c["id"],
                                 text=f"{c['title']}（{c.get('word_count', 0)} 字）")

    def refresh_entities(self):
        self.entList.delete(0, "end")
        for e in self.lib["entities"]:
            if e["book_id"] == self.bookId:
                self.entList.insert("end", f"{e['name']}（{e.get('kind', '')}）")

    def on_tree_select(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        nodeId = sel[0]
        if any(c["id"] == nodeId for c in self.lib["chapters"]):
            self.sync_current()
            self.load_chapter(nodeId)

    def load_chapter(self, chId):
        ch = next((c for c in self.lib["chapters"] if c["id"] == chId), None)
        if not ch:
            return
        self.chapterId = chId
        self.volumeId = ch["volume_id"]
        self.titleVar.set(ch["title"])
        self.text.delete("1.0", "end")
        self.text.insert("1.0", ch.get("text", ""))
        self.text.edit_modified(False)
        self.update_status()

    def sync_current(self):
        if not self.chapterId:
            return
        ch = next((c for c in self.lib["chapters"] if c["id"] == self.chapterId), None)
        if not ch:
            return
        ch["title"] = self.titleVar.get()
        ch["text"] = self.text.get("1.0", "end-1c")
        ch["word_count"] = count_words(ch["text"])
        ch["updated_at"] = now_ts()

    def mark_dirty(self):
        self.dirty = True

    def on_text_modified(self, _):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.mark_dirty()
            self.update_status()

    def update_status(self):
        body = self.text.get("1.0", "end-1c")
        self.statusVar.set(f"本章 {count_words(body)} 字 · {len(body)} 字符")

    # ---------- 增删 ----------
    def add_volume(self):
        if not self.bookId:
            messagebox.showinfo("提示", "请先打开库")
            return
        from tkinter import simpledialog
        title = simpledialog.askstring("新增卷", "卷名：", parent=self.root)
        if not title:
            return
        order = len([v for v in self.lib["volumes"] if v["book_id"] == self.bookId])
        self.lib["volumes"].append({"id": gen_id("vol"), "book_id": self.bookId,
                                    "title": title, "order": order})
        self.refresh_tree()
        self.mark_dirty()

    def add_chapter(self):
        if not self.bookId:
            return
        vols = [v for v in self.lib["volumes"] if v["book_id"] == self.bookId]
        if not vols:
            messagebox.showinfo("提示", "请先新增一卷")
            return
        from tkinter import simpledialog
        title = simpledialog.askstring("新增章节", "章节名：", parent=self.root)
        if not title:
            return
        target = self.volumeId if any(v["id"] == self.volumeId for v in vols) else vols[0]["id"]
        order = len([c for c in self.lib["chapters"] if c["volume_id"] == target])
        ch = {"id": gen_id("ch"), "book_id": self.bookId, "volume_id": target,
              "title": title, "order": order, "word_count": 0,
              "updated_at": now_ts(), "text": ""}
        self.lib["chapters"].append(ch)
        self.refresh_tree()
        self.load_chapter(ch["id"])
        self.mark_dirty()

    def del_chapter(self):
        if not self.chapterId:
            return
        if not messagebox.askyesno("确认", "删除当前章节？"):
            return
        self.lib["chapters"] = [c for c in self.lib["chapters"] if c["id"] != self.chapterId]
        self.chapterId = None
        self.text.delete("1.0", "end")
        self.titleVar.set("")
        self.refresh_tree()
        self.mark_dirty()

    def add_entity(self):
        if not self.bookId:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("新增资料", "名称：", parent=self.root)
        if not name:
            return
        kind = simpledialog.askstring("新增资料", "类型（如 人物/地点）：", parent=self.root) or "其他"
        desc = simpledialog.askstring("新增资料", "描述：", parent=self.root) or ""
        self.lib["entities"].append({"id": gen_id("ent"), "book_id": self.bookId,
                                     "name": name, "kind": kind, "description": desc})
        self.refresh_entities()
        self.mark_dirty()

    # ---------- 提示词 ----------
    def gen_prompt(self):
        if not self.chapterId:
            messagebox.showinfo("提示", "请先选择一个章节")
            return
        ch = next((c for c in self.lib["chapters"] if c["id"] == self.chapterId), None)
        if not ch:
            return
        lst = sorted([c for c in self.lib["chapters"] if c["volume_id"] == ch["volume_id"]],
                     key=lambda c: c["order"])
        pos = next((i for i, c in enumerate(lst) if c["id"] == self.chapterId), 0)
        prev = "（本章为卷首，无上一章）" if pos == 0 else lst[pos - 1].get("text", "")[-500:]
        ents = [e for e in self.lib["entities"] if e["book_id"] == self.bookId]
        chars = "\n".join(f"- {e['name']}（{e.get('kind', '')}）：{e.get('description', '')}"
                          for e in ents) or "（未填写）"
        body = ch.get("text") or "（当前章为空）"
        prompt = (f"你是一位与作者合写的小说作者。请续写下一段情节。\n\n"
                  f"【设定】\n{chars}\n\n【上一章结尾】\n{prev}\n\n【本章已有正文】\n{body}")
        self.promptText.delete("1.0", "end")
        self.promptText.insert("1.0", prompt)


    def gen_pov(self):
        """人称转换：与 core 版 pov 子命令输出同一套提示词。"""
        if not self.chapterId:
            messagebox.showinfo("提示", "请先选择一个章节")
            return
        ch = next((c for c in self.lib["chapters"] if c["id"] == self.chapterId), None)
        if not ch:
            return
        ents = [e for e in self.lib["entities"] if e["book_id"] == self.bookId]
        chars = "\n".join(f"- {e['name']}（{e.get('kind', '')}）：{e.get('description', '')}"
                          for e in ents) or "（未填写）"
        body = ch.get("text") or "（当前章为空）"
        target = POV_TARGETS.get(self.povVar.get(), POV_TARGETS["third"])
        prompt = build_pov_prompt(body, chars, target, self.povInnerVar.get())
        self.promptText.delete("1.0", "end")
        self.promptText.insert("1.0", prompt)


def main():
    root = tk.Tk()
    WriterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
