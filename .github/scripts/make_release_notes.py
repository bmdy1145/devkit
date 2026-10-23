#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从版本历史生成 Release 说明。

每个版本 HTML 里都嵌着 VERSION_HISTORY 数组，记录了这一代产品的每次改动。
本脚本把它解析出来，汇总成本次发布的说明，避免 Releases 页面只有一句
「主干 X 下的全部版本文件」而看不出改了什么。

发布按项目区分（projects/<项目>/code/<主干>/），本脚本同样接受项目名，
避免把 Writer 的文件按 DevKit 的规则去解析。

汇总规则：
  · 扫描 projects/<项目>/code/<主干>/ 下所有版本文件，把各文件的 VERSION_HISTORY 合并
  · 只保留版本号以该主干开头的条目
  · 按「说明内容」去重，而不是按版本号 —— 同一个主干下各皮肤会各自记一条
    改动，但内容往往是同一段话（例如「全站响应式适配」在四个旧皮肤里各记
    一遍），按版本号去重挡不住，会连续重复四遍
  · 同一个版本号出现多次时，保留说明最长的那一条
  · 跳过「中文版：同步应用主干版本号 …」这类纯语言后缀样板条目 —— 它们不
    携带改动信息，列出来只是噪音
  · 每条说明截断到 MAX_NOTE_CHARS 字
  · 附件一律列出体积与 sha256 前 12 位，便于跨版本比对「文件是否一致」

用法：
    python3 .github/scripts/make_release_notes.py <项目名> <主干名> [--no-changes]

--no-changes 表示本次 main 更新没有改动交付物文件，说明里会写明「无功能更新」。

为兼容旧调用，只给一个参数时按 DevKit 处理：
    python3 .github/scripts/make_release_notes.py A1_V_Φ9
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "projects"
DEFAULT_PROJECT = "devkit"

MAX_NOTE_CHARS = 240
BOILERPLATE = "中文版：同步应用主干版本号"
CHECKSUM_PREFIX = 12


def code_dir(project: str) -> Path:
    return PROJECTS_DIR / project / "code"

ENTRY_RE = re.compile(
    r"\{\s*version:\s*'((?:[^'\\]|\\.)*)',\s*note:\s*'((?:[^'\\]|\\.)*)'",
    re.S,
)


def unescape(text: str) -> str:
    return text.replace("\\'", "'").replace("\\\\", "\\")


def collect(project: str, trunk: str) -> list[tuple[str, str]]:
    """返回 [(版本号, 说明)]，按说明内容去重且保持首次出现顺序。"""
    files = sorted((code_dir(project) / trunk).glob("deepseek_*.html"))
    best: dict[str, str] = {}
    order: list[str] = []

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for version, note in ENTRY_RE.findall(text):
            version = unescape(version).strip()
            note = " ".join(unescape(note).split())
            if not version.startswith(trunk):
                continue
            if BOILERPLATE in note:
                continue
            if version not in best:
                order.append(version)
                best[version] = note
            elif len(note) > len(best[version]):
                best[version] = note

    seen_notes: set[str] = set()
    result: list[tuple[str, str]] = []
    for version in order:
        note = best[version]
        if note in seen_notes:
            continue
        seen_notes.add(note)
        result.append((version, note))
    return result


def truncate(note: str) -> str:
    if len(note) <= MAX_NOTE_CHARS:
        return note
    return note[:MAX_NOTE_CHARS].rstrip() + "……"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:CHECKSUM_PREFIX]


def build_notes(project: str, trunk: str, mode: str = "changed") -> str:
    """mode 取 changed / no_changes / manual 三者之一。"""
    trunk_dir = code_dir(project) / trunk
    files = sorted(trunk_dir.glob("deepseek_*.html"))
    entries = collect(project, trunk)

    lines: list[str] = []
    lines.append(
        f"项目 `{project}` · 主干 `{trunk}`，本 Release 附带 {len(files)} 个版本文件"
        "（每个都是自包含的单文件应用，下载后可直接用浏览器打开）。"
    )
    lines.append("")

    lines.append("## 本次更新")
    lines.append("")
    if mode == "no_changes":
        lines.append(
            f"**无功能更新。** 本次 `main` 的更新未修改任何交付物文件，"
            f"因此附件仍为 `{trunk}` 的同一批文件，与上一次发布完全一致"
            "（可用下方校验和比对）。"
        )
    elif mode == "manual":
        lines.append(
            f"本 Release 由手动触发补发，为该主干留下一个固定的下载入口。"
            f"附件是 `{trunk}` 当前的全部版本文件。"
        )
    else:
        lines.append(f"本次更新改动了主干 `{trunk}` 下的交付物文件。")
    lines.append("")

    if entries:
        lines.append(f"## `{trunk}` 的改动历程")
        lines.append("")
        for version, note in entries:
            lines.append(f"- **{version}** — {truncate(note)}")
        lines.append("")

    lines.append("## 附件")
    lines.append("")
    # 十进制（÷1000）而非 KiB（÷1024）：导航页手写的大小用的是十进制，
    # 两处数字必须对得上，否则同一个文件会显示成两个大小。
    for path in files:
        kb = path.stat().st_size / 1000
        lines.append(f"- `{path.name}`（约 {kb:.0f} KB，sha256 `{digest(path)}`）")

    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(sys.argv[1:])

    # 一个参数 = 只给主干名，按 DevKit 处理（兼容旧用法）
    if len(args) == 1:
        project, trunk = DEFAULT_PROJECT, args[0]
    elif len(args) == 2:
        project, trunk = args
    else:
        print(
            "用法：make_release_notes.py [<项目名>] <主干名> [--no-changes|--manual]",
            file=sys.stderr,
        )
        return 1

    if "--no-changes" in flags:
        mode = "no_changes"
    elif "--manual" in flags:
        mode = "manual"
    else:
        mode = "changed"

    if not (code_dir(project) / trunk).is_dir():
        print(f"找不到目录 projects/{project}/code/{trunk}", file=sys.stderr)
        return 1

    print(build_notes(project, trunk, mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
