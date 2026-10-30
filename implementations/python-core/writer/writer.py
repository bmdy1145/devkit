#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Writer 内核版（Python）

版本：A1_I_Φ3_Python_CN
对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html

只实现纯逻辑内核：书籍 / 卷 / 章节结构的 JSON 持久化、字数统计、
章节排序、跨卷移动、引用管理、提示词模板合成。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import json
import os
import sys
import time

_counter = [0]


def gen_id(prefix):
    _counter[0] += 1
    return f"{prefix}_{int(time.time() * 1000)}_{_counter[0]}"


def now_ts():
    return int(time.time() * 1000)


def _is_cjk(code):
    return (0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF
            or 0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7AF
            or 0xF900 <= code <= 0xFAFF)


def count_words(text):
    """与浏览器版一致：CJK 每字算 1 词，拉丁词按整词算。"""
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


def load(path):
    if not os.path.exists(path):
        return {"books": [], "volumes": [], "chapters": [], "entities": []}
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return {"books": [], "volumes": [], "chapters": [], "entities": []}
    data = json.loads(raw)
    for k in ("books", "volumes", "chapters", "entities"):
        data.setdefault(k, [])
    return data


def save(path, lib):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)


def chapters_of(lib, vol_id):
    return sorted([c for c in lib["chapters"] if c["volume_id"] == vol_id],
                  key=lambda c: c["order"])


def reorder_volume(lib, vol_id):
    for i, c in enumerate(chapters_of(lib, vol_id)):
        c["order"] = i


def usage():
    print("Writer 内核版（Python）")
    print("用法: writer.py <库文件.json> <子命令> [参数]")
    print()
    print("子命令:")
    print("  init <书名>")
    print("  add-volume <书籍ID> <卷名>")
    print("  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]")
    print("  list <书籍ID>")
    print("  stats <书籍ID>")
    print("  move-chapter <章节ID> <目标卷ID>")
    print("  add-entity <书籍ID> <名称> [类型] [描述]")
    print("  prompt <书籍ID> <章节ID>")
    print("  reindex <书籍ID>")


def main():
    if len(sys.argv) < 3:
        usage()
        return 1

    lib_path = sys.argv[1]
    cmd = sys.argv[2]
    args = sys.argv[3:]
    lib = load(lib_path)

    if cmd == "init":
        if not args:
            print("缺少书名", file=sys.stderr)
            return 1
        b = {"id": gen_id("book"), "title": args[0], "author": "", "updated_at": now_ts()}
        print(f"已创建书籍: {b['title']} ({b['id']})")
        lib["books"].append(b)

    elif cmd == "add-volume":
        if len(args) < 2:
            print("缺少参数", file=sys.stderr)
            return 1
        book_id, title = args[0], args[1]
        if not any(b["id"] == book_id for b in lib["books"]):
            print(f"找不到书籍 {book_id}", file=sys.stderr)
            return 1
        order = sum(1 for v in lib["volumes"] if v["book_id"] == book_id)
        v = {"id": gen_id("vol"), "book_id": book_id, "title": title, "order": order}
        print(f"已新增卷: {v['title']} ({v['id']})")
        lib["volumes"].append(v)

    elif cmd == "add-chapter":
        if len(args) < 3:
            print("缺少参数", file=sys.stderr)
            return 1
        book_id, vol_id, title = args[0], args[1], args[2]
        text = ""
        if len(args) >= 4 and os.path.exists(args[3]):
            with open(args[3], encoding="utf-8") as f:
                text = f.read()
        if not any(v["id"] == vol_id for v in lib["volumes"]):
            print(f"找不到卷 {vol_id}", file=sys.stderr)
            return 1
        order = sum(1 for c in lib["chapters"] if c["volume_id"] == vol_id)
        wc = count_words(text)
        ch = {"id": gen_id("ch"), "book_id": book_id, "volume_id": vol_id,
              "title": title, "order": order, "word_count": wc,
              "updated_at": now_ts(), "text": text}
        print(f"已新增章节: {ch['title']} ({ch['id']}) · {wc} 字")
        lib["chapters"].append(ch)

    elif cmd == "list":
        if not args:
            print("缺少书籍ID", file=sys.stderr)
            return 1
        book_id = args[0]
        book = next((b for b in lib["books"] if b["id"] == book_id), None)
        if not book:
            print("找不到书籍", file=sys.stderr)
            return 1
        print(f"书籍: {book['title']} ({book['id']})")
        vols = sorted([v for v in lib["volumes"] if v["book_id"] == book_id],
                      key=lambda v: v["order"])
        for v in vols:
            print(f"  卷: {v['title']} (order {v['order']})")
            for c in chapters_of(lib, v["id"]):
                print(f"    - [{c['order']}] {c['title']} · {c['word_count']} 字")

    elif cmd == "stats":
        if not args:
            print("缺少书籍ID", file=sys.stderr)
            return 1
        book_id = args[0]
        chs = [c for c in lib["chapters"] if c["book_id"] == book_id]
        print(f"章节数: {len(chs)}")
        print(f"总字数: {sum(c['word_count'] for c in chs)}")
        print(f"总字符: {sum(len(c.get('text', '')) for c in chs)}")

    elif cmd == "move-chapter":
        if len(args) < 2:
            print("缺少参数", file=sys.stderr)
            return 1
        ch_id, target_vol = args[0], args[1]
        ch = next((c for c in lib["chapters"] if c["id"] == ch_id), None)
        if not ch:
            print("找不到章节", file=sys.stderr)
            return 1
        if not any(v["id"] == target_vol for v in lib["volumes"]):
            print(f"找不到目标卷 {target_vol}", file=sys.stderr)
            return 1
        source_vol = ch["volume_id"]
        ch["volume_id"] = target_vol
        ch["order"] = sum(1 for c in lib["chapters"] if c["volume_id"] == target_vol)
        reorder_volume(lib, target_vol)
        reorder_volume(lib, source_vol)
        print("已将章节移至目标卷，并重排源卷与目标卷的顺序")

    elif cmd == "add-entity":
        if len(args) < 2:
            print("缺少参数", file=sys.stderr)
            return 1
        book_id, name = args[0], args[1]
        kind = args[2] if len(args) >= 3 else "其他"
        desc = args[3] if len(args) >= 4 else ""
        e = {"id": gen_id("ent"), "book_id": book_id, "name": name,
             "kind": kind, "description": desc}
        print(f"已添加资料: {e['name']} ({e['id']})")
        lib["entities"].append(e)

    elif cmd == "prompt":
        if len(args) < 2:
            print("缺少参数", file=sys.stderr)
            return 1
        book_id, ch_id = args[0], args[1]
        ch = next((c for c in lib["chapters"] if c["id"] == ch_id), None)
        if not ch:
            print("找不到章节", file=sys.stderr)
            return 1
        lst = chapters_of(lib, ch["volume_id"])
        pos = next((i for i, c in enumerate(lst) if c["id"] == ch_id), 0)
        prev = "（本章为卷首，无上一章）"
        if pos > 0:
            prev = lst[pos - 1].get("text", "")[-500:]
        ents = [e for e in lib["entities"] if e["book_id"] == book_id]
        chars = "\n".join(f"- {e['name']}（{e['kind']}）：{e['description']}" for e in ents) or "（未填写）"
        body = ch.get("text") or "（当前章为空）"
        print("你是一位与作者合写的小说作者。请续写下一段情节。")
        print()
        print("【设定】")
        print(chars)
        print("【上一章结尾】")
        print(prev)
        print()
        print("【本章已有正文】")
        print(body)

    elif cmd == "reindex":
        if not args:
            print("缺少书籍ID", file=sys.stderr)
            return 1
        book_id = args[0]
        for v in lib["volumes"]:
            if v["book_id"] == book_id:
                reorder_volume(lib, v["id"])
        print("已重排全部卷的章节顺序")

    else:
        print(f"未知子命令: {cmd}", file=sys.stderr)
        return 1

    save(lib_path, lib)
    return 0


if __name__ == "__main__":
    sys.exit(main())
