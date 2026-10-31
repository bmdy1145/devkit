#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本结构校验（DevKit 与 Writer）。

检查各项目 code/ 下每个版本 HTML 的版本号结构、四处版本号一致性、脚本可
解析性、结构块与目录内容的相互覆盖，以及同一主干下各皮肤的迭代层是否一致。

用法：
    本地： python3 .github/scripts/version_guard.py
    CI  ： 由 .github/workflows/version-guard.yml 调用

退出码：0 = 通过（可能有告警）；1 = 存在必须修复的问题。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 参与校验的项目：交付物已迁入项目层，各项目独立维护版本。
#
# 只收录「符合本套版本规范」的项目：文件名是 deepseek_<版本号>.html，
# 且文件内带 CURRENT_VERSION / 版本代号 / 结构块。dircleaner 与 submerge-pro
# 的产物文件名是 deepseek_html_<日期>_<随机>.html、也没有 CURRENT_VERSION，
# 硬套会全是误报，等它们的版本规范对齐再纳入。
CHECKED_PROJECTS = ("devkit", "writer")


def code_dir(project: str) -> Path:
    return ROOT / "projects" / project / "code"

BRANCH_RE = re.compile(r"^A\d+$")
ROMAN_RE = re.compile(r"^[IVX]+$")
PHI_RE = re.compile(r"^Φ\d+$")
CYCLE_LETTER_RE = re.compile(r"^[B-Z]\d+$")
CYCLE_SYMBOL_RE = re.compile(r"^[ΨΩΣΛΠΔ]\d+$")
ENGLISH_TAGS = {"Fix", "Perf", "Refactor", "Style", "Doc", "Hotfix", "Promotion_Hotfix"}
LANGUAGES = {"CN", "GLOBAL"}
VARIANTS = {"Glass", "Neon", "Mono", "Clean", "Material", "Minimal", "Premium", "Shadcn"}

problems: list[str] = []
warnings: list[str] = []
infos: list[str] = []


def fail(where: str, msg: str) -> None:
    problems.append(f"{where}: {msg}")


def warn(where: str, msg: str) -> None:
    warnings.append(f"{where}: {msg}")


def info(where: str, msg: str) -> None:
    infos.append(f"{where}: {msg}")


def split_version(version: str):
    """把版本号拆成 (结构问题列表, 段列表, 变体标识或 None)。"""
    errs: list[str] = []
    tokens = version.split("_")
    if len(tokens) < 4:
        return [f"版本号段数不足：{version}"], tokens, None
    if not BRANCH_RE.match(tokens[0]):
        errs.append(f"第 1 层分支代号不合规：{tokens[0]}")
    if not ROMAN_RE.match(tokens[1]):
        errs.append(f"第 2 层罗马数字不合规：{tokens[1]}")
    if not PHI_RE.match(tokens[2]):
        errs.append(f"第 3 层 Φ 层不合规：{tokens[2]}")
    if tokens[-1] not in LANGUAGES:
        errs.append(f"末尾语言后缀不合规：{tokens[-1]}")
        body = tokens[3:]
    else:
        body = tokens[3:-1]

    variant = None
    for tok in body:
        if tok in VARIANTS:
            if variant is not None:
                errs.append(f"出现多个变体标识：{variant} 与 {tok}")
            variant = tok
        elif tok in ENGLISH_TAGS:
            continue
        elif (
            ROMAN_RE.match(tok)
            or CYCLE_LETTER_RE.match(tok)
            or CYCLE_SYMBOL_RE.match(tok)
        ):
            continue
        else:
            errs.append(f"无法归类的版本段：{tok}")
    return errs, tokens, variant


def strip_variant(version: str) -> str:
    """去掉变体标识，用于判断同一主干下各皮肤的迭代层是否一致。"""
    return "_".join(t for t in version.split("_") if t not in VARIANTS)


def grab(text: str, pattern: str):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def check_js_syntax(path: Path, rel: str) -> None:
    node = shutil.which("node")
    if node is None:
        warn(rel, "未找到 node，已跳过 <script> 语法检查（CI 环境中会执行）")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    # 大小写不敏感：HTML 中 <SCRIPT> 与 <script> 等价。原先只匹配小写，
    # CodeQL 的 py/bad-tag-filter 会报「漏掉大写标签」；本仓库交付物一律
    # 小写，但脚本不应依赖这一点。
    # 闭合标签用 [^>]* 而非 \s*：\s* 只认空白，漏掉 </script foo>、
    # </script/>、</script\nbar> 这些带内容的形态，会整块漏检。
    blocks = re.findall(r"<script\b[^>]*>(.*?)</script[^>]*>", text, re.S | re.I)
    if not blocks:
        warn(rel, "未找到 <script> 块")
        return
    for i, block in enumerate(blocks, 1):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(block)
            tmp = fh.name
        try:
            proc = subprocess.run(
                [node, "--check", tmp], capture_output=True, text=True
            )
            if proc.returncode != 0:
                tail = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
                fail(rel, f"第 {i} 个 <script> 存在语法错误：{tail[-1] if tail else '未知'}")
        finally:
            Path(tmp).unlink(missing_ok=True)


def check_trunk(trunk: Path) -> None:
    rel_dir = trunk.relative_to(ROOT).as_posix()
    files = sorted(trunk.glob("deepseek_*.html"))
    if not files:
        return

    index_path = trunk / "index.html"
    index_text = index_path.read_text(encoding="utf-8", errors="replace") if index_path.exists() else ""
    if not index_path.exists():
        fail(rel_dir, "缺少 index.html")

    versions: dict[str, str] = {}
    core_layers: dict[str, str] = {}

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        version = path.stem.replace("deepseek_", "")
        versions[rel] = version
        text = path.read_text(encoding="utf-8", errors="replace")

        errs, tokens, variant = split_version(version)
        for e in errs:
            fail(rel, e)
        if variant is not None:
            core_layers[rel] = strip_variant(version)

        header = grab(text, r"版本代号：(\S+)")
        current = grab(text, r"CURRENT_VERSION\s*=\s*'([^']+)'")
        latest = grab(text, r"当前最新版本：(\S+)")
        for label, value in (
            ("文件头版本代号", header),
            ("CURRENT_VERSION", current),
            ("结构块当前最新版本", latest),
        ):
            if value is None:
                fail(rel, f"缺少{label}")
            elif value != version:
                fail(rel, f"{label}（{value}）与文件名版本（{version}）不一致")

        if "本程序是自由软件" not in text:
            fail(rel, "未找到文件末尾的许可证声明")

        if not index_text or version not in index_text:
            fail(rel, "所在目录的 index.html 未列出该版本")

        check_js_syntax(path, rel)

    # 同一主干下各皮肤的迭代层必须一致
    if len(set(core_layers.values())) > 1:
        detail = "；".join(f"{Path(k).name} → {v}" for k, v in sorted(core_layers.items()))
        fail(rel_dir, f"同一主干下各皮肤的迭代层不一致：{detail}")

    # 结构块是否列出同主干的全部版本。
    # 仅作信息，既不是问题也不计告警：本项目惯例是「结构块 = 该文件创建那一刻
    # 的快照」，后续新增的版本不会回填进老文件，因此老文件列不全属正常。
    expected = set(versions.values())
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"当前最新版本.*?(?=-->)", text, re.S)
        if not m:
            fail(rel, "未找到「完整版本结构文字表述」块")
            continue
        block = m.group(0)
        missing = sorted(v for v in expected if v not in block)
        if missing:
            info(rel, f"结构块未列出同主干的这些版本（快照惯例下属正常）：{', '.join(missing)}")


def main() -> int:
    # 中文输出固定按 UTF-8 打印，避免 Windows 本地与 CI 日志乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    found_any = False
    for project in CHECKED_PROJECTS:
        d = code_dir(project)
        if not d.is_dir():
            print(f"[告警] 找不到目录：{d}", file=sys.stderr)
            continue
        found_any = True
        for trunk in sorted(p for p in d.iterdir() if p.is_dir()):
            check_trunk(trunk)
    if not found_any:
        print("没有任何可校验的项目目录。", file=sys.stderr)
        return 1

    for p in problems:
        print(f"[问题] {p}")
    for w in warnings:
        print(f"[告警] {w}")
    for i in infos:
        print(f"[信息] {i}")

    print()
    print(f"检查完成：{len(problems)} 个问题，{len(warnings)} 条告警，{len(infos)} 条信息。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
