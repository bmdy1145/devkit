#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SubMerge Pro 内核版（Python）

版本：A1_II_Φ10_Python_CN
对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html

只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。

版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
许可证：GPLv3
"""
import argparse
import re
import sys

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CJK_SPLIT = re.compile(r"([\u4e00-\u9fff]+)")
TIME_RE = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})$")
IDX_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")
BOUND1 = re.compile(r"([a-zA-Z0-9])([\u4e00-\u9fff])")
BOUND2 = re.compile(r"([\u4e00-\u9fff])([a-zA-Z0-9])")


def is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff"


def count_words(text):
    total = 0
    for seg in CJK_SPLIT.split(text):
        if not seg:
            continue
        if CJK_RE.search(seg):
            total += (len(seg) + 1) // 2
        else:
            total += len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", seg))
    return total


def tokenize(text):
    tokens = []
    for seg in CJK_SPLIT.split(text):
        if not seg:
            continue
        if CJK_RE.search(seg):
            for i in range(0, len(seg), 2):
                tokens.append(seg[i:i + 2])
        else:
            tokens.extend(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S", seg))
    return tokens


def join_tokens(tokens):
    out = []
    for i, tok in enumerate(tokens):
        if i > 0 and not is_cjk(tokens[i - 1][-1]) and not is_cjk(tok[0]):
            out.append(" ")
        out.append(tok)
    return "".join(out)


def add_boundary(s):
    s = BOUND1.sub(r"\1 \2", s)
    return BOUND2.sub(r"\1 \2", s)


def split_paired(orig, trans, max_words=10):
    if not orig and not trans:
        return [("", "")]
    o, t = tokenize(orig), tokenize(trans)
    chunks, oi, ti = [], 0, 0
    while oi < len(o) or ti < len(t):
        oc, tc, words = [], [], 0
        while (oi < len(o) or ti < len(t)) and words < max_words:
            can_o, can_t = oi < len(o), ti < len(t)
            if can_o and can_t:
                if words + 2 <= max_words:
                    oc.append(o[oi]); oi += 1
                    tc.append(t[ti]); ti += 1
                    words += 2
                else:
                    break
            elif can_o:
                if words + 1 <= max_words:
                    oc.append(o[oi]); oi += 1; words += 1
                else:
                    break
            elif can_t:
                if words + 1 <= max_words:
                    tc.append(t[ti]); ti += 1; words += 1
                else:
                    break
        chunks.append((add_boundary(join_tokens(oc)).strip(),
                       add_boundary(join_tokens(tc)).strip()))
    return chunks or [(orig, trans)]


def time_to_ms(s, fps=25.0):
    parts = s.split(":")
    if len(parts) != 3:
        return 0
    h, m = int(parts[0]), int(parts[1])
    sp = parts[2]
    if "," in sp:
        a, b = sp.split(",", 1)
        sec, ms = int(a), int((b + "000")[:3])
    elif "." in sp:
        a, b = sp.split(".", 1)
        sec = int(a)
        ms = round(float((b + "00")[:2]) * (1000.0 / fps))
    else:
        sec, ms = int(sp), 0
    return (h * 3600 + m * 60 + sec) * 1000 + ms


def ms_to_time(ms):
    h = ms // 3600000; ms %= 3600000
    m = ms // 60000; ms %= 60000
    s = ms // 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms % 1000:03d}"


def parse_subtitle(content):
    clean = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    entries, seen = [], set()
    for block in re.split(r"\n\s*\n", clean):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3 or not re.fullmatch(r"\d+", lines[0]):
            continue
        mt = TIME_RE.match(lines[1])
        if not mt:
            continue
        idx = int(lines[0])
        if idx in seen:
            continue
        seen.add(idx)
        start = mt.group(1).replace(".", ",", 1)
        end = mt.group(2).replace(".", ",", 1)
        sm = time_to_ms(start)
        if sm >= time_to_ms(end):
            end = ms_to_time(sm + 1)
        text = "\n".join(lines[2:]).strip()
        if not text:
            continue
        entries.append({"index": idx, "start": start, "end": end,
                        "text": text, "translated": None})
    entries.sort(key=lambda e: e["index"])
    return entries


def apply_time_fix(entries, strategy):
    if strategy == "keep":
        return entries
    if strategy == "delete":
        return [e for e in entries if time_to_ms(e["end"]) - time_to_ms(e["start"]) >= 10]
    if strategy == "extend":
        for i, e in enumerate(entries):
            s = time_to_ms(e["start"])
            en = time_to_ms(e["end"])
            if en - s < 10:
                new_end = s + 10
                e["end"] = ms_to_time(new_end)
                shift = new_end - en
                for j in range(i + 1, len(entries)):
                    entries[j]["start"] = ms_to_time(time_to_ms(entries[j]["start"]) + shift)
                    entries[j]["end"] = ms_to_time(time_to_ms(entries[j]["end"]) + shift)
    return entries


def apply_translation(entries, trans_str):
    mapping, cur, buf = {}, None, []
    for line in trans_str.split("\n"):
        mt = IDX_RE.match(line.strip())
        if mt:
            if cur is not None:
                mapping[cur] = "\n".join(buf).strip()
            cur = int(mt.group(1))
            buf = [mt.group(2).strip()] if mt.group(2).strip() else []
            continue
        if cur is not None and line.strip():
            buf.append(line.strip())
    if cur is not None:
        mapping[cur] = "\n".join(buf).strip()

    applied = 0
    for e in entries:
        if e["index"] in mapping:
            e["translated"] = mapping[e["index"]]
            applied += 1
    return applied


def export_srt(entries, mode):
    out = []
    for e in entries:
        if mode == "orig":
            text = e["text"]
        elif mode == "trans":
            text = e["translated"] or ""
        else:
            if e["translated"] and e["text"]:
                text = e["text"] + "\n" + e["translated"]
            elif e["translated"]:
                text = e["translated"]
            else:
                text = e["text"]
        out.append(f"{e['index']}\n{e['start']} --> {e['end']}\n{text}\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(prog="submerge", description="SubMerge Pro 内核版（Python）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("parse", "export", "merge-prompt"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--trans", default=None)
        p.add_argument("--mode", default="both", choices=["both", "orig", "trans"])
        p.add_argument("--time-fix", default="keep", choices=["keep", "delete", "extend"])
        p.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    with open(args.file, encoding="utf-8", errors="replace") as f:
        content = f.read()
    entries = parse_subtitle(content)
    if not entries:
        print("解析失败：未找到字幕条目", file=sys.stderr)
        return 1
    entries = apply_time_fix(entries, args.time_fix)

    if args.trans:
        with open(args.trans, encoding="utf-8", errors="replace") as f:
            n = apply_translation(entries, f.read())
        print(f"已应用 {n} 条译文")

    if args.cmd == "parse":
        total = sum(count_words(e["text"]) for e in entries)
        print(f"条目数: {len(entries)}")
        print(f"总词数: {total}")
        f0, l0 = entries[0], entries[-1]
        print(f"首条: [{f0['index']}] {f0['start']} --> {f0['end']} | {f0['text']}")
        print(f"末条: [{l0['index']}] {l0['start']} --> {l0['end']} | {l0['text']}")
    elif args.cmd == "export":
        print(export_srt(entries, args.mode))
    elif args.cmd == "merge-prompt":
        for e in entries:
            for orig, trans in split_paired(e["text"], e["translated"] or "", args.max):
                body = orig if not trans else f"{orig}\n{trans}"
                print(f"[{e['index']}] {body.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
