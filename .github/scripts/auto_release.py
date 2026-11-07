#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main 一更新就自动发布（多项目）。

每次推送到 main，按项目分别判定、分别发布：

  · 仓库里每个 projects/<项目>/code/ 都是一个独立的交付项目
  · 本次推送改动了哪个项目的哪个主干（code/<主干>/ 下的文件），就给
    「该项目 · 该主干」发一个 Release
  · 某项目的 code/ 有改动但没动到任何主干目录（例如只改了索引页），
    只给**该项目的最新主干**发一个「无功能更新」的 Release
  · 哪个项目都没动到（纯文档 / CI 改动），不发任何 Release，只打印说明
  · 标签命名：DevKit 沿用裸主干名（A1_V_Φ8、A1_V_Φ8.1……）；
    其他项目加项目前缀避免撞名（writer/A1_I_Φ2、writer/A1_I_Φ2.1……）。
    DevKit 用裸名是为了不打乱已有标签的历史。

为什么必须按项目区分：发布脚本原本写死 projects/devkit，于是改 Writer 时
被判定为「没动交付物」，退化成给最新的 DevKit 主干发一个「无功能更新」的
Release——标签名是 DevKit 的，内容却是 Writer 的提交。

为什么先建草稿再发布：仓库开启了 GitHub 的 Immutable Releases（发布后标签与
附件都不可改动）。若按「直接建正式 Release → 再传附件」的顺序，创建那一刻
Release 就已发布并锁定，随后每次上传附件都返回 HTTP 422，结果是「Release
建出来了，附件 0/N」。2026-11-06 persona/A1_II_Φ11 与 persona/A1_II_Φ10_Fix.1
两个空 Release 就是这么来的。正确顺序是：建**草稿** → 传附件 → 再改为发布。
失败时回滚草稿与标签，不留空壳。

用法（由 .github/workflows/release-on-main.yml 调用）：
    GITHUB_REPOSITORY=... GITHUB_TOKEN=... BEFORE_SHA=... AFTER_SHA=... \\
        python3 .github/scripts/auto_release.py

手动补发：
    DISPATCH_PROJECT=writer DISPATCH_TRUNK=A1_I_Φ2 DISPATCH_SUFFIX=1 ...

退出码：0 = 成功；1 = 出错。
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_release_notes import build_notes  # noqa: E402

API = "https://api.github.com"
UPLOAD_API = "https://uploads.github.com"
ZERO_SHA = "0" * 40

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "projects"
# DevKit 是仓库的主项目，标签历史上一直是裸主干名，不加前缀
DEVKIT = "devkit"
PHI_RE = re.compile(r"Φ(\d+)")


def api(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "devkit-auto-release")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        # 出错时也把响应体解析出来：调用方需要区分「标签名已被不可变 Release
        # 占用」这类可重试的错误与其他失败，只拿到状态码是分不出来的。
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def code_dir(project: str) -> Path:
    return PROJECTS_DIR / project / "code"


def local_projects() -> list[str]:
    """所有带 code/ 目录的项目（即真正有交付物的项目）。

    projects/ 本身不存在时返回空列表而不是抛异常：手动触发路径会先调用它
    拼提示信息，抛 FileNotFoundError 出去只会得到一个不带上下文的堆栈。
    """
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir() and code_dir(p.name).is_dir())


# 归档目录不算主干：它们是已冻结的历史层，只供对照与回退，不参与发布。
#
# code/ 下不只有主干，还有 *_fix-archive/ 这类归档目录。若把它们也算作主干，
# 会出现两种错发：latest_trunk() 按 Φ 数字取最大时可能选中归档（例如
# A1_V_Φ9_fix-archive 的 Φ9 与真主干 A1_V_Φ9 并列），于是「只改了索引页」
# 的那次推送会给归档发一个 Release；改动归档文件本身时同理。
#
# 用后缀约定而不是版本号正则：意图更直接，也不必在发布脚本里重实现一遍
# 版本号语法（新增循环扩展层时不会牵连到这里）。
ARCHIVE_SUFFIX = "_fix-archive"


def is_trunk_dir(path: Path) -> bool:
    """目录是否是可发布的主干（归档目录不算）。"""
    return path.is_dir() and not path.name.endswith(ARCHIVE_SUFFIX)


def local_trunks(project: str) -> list[str]:
    d = code_dir(project)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if is_trunk_dir(p))


def latest_trunk(project: str) -> str | None:
    """按 Φ 数字取最大的主干；没有 Φ 时退化为字典序最大的那个。"""
    trunks = local_trunks(project)
    if not trunks:
        return None
    with_phi = [(int(m.group(1)), t) for t in trunks if (m := PHI_RE.search(t))]
    if with_phi:
        return max(with_phi)[1]
    return max(trunks)


def tag_prefix(project: str) -> str:
    """DevKit 用裸主干名，其他项目加 `项目/` 前缀避免不同项目的 Φ 号相撞。"""
    return "" if project == DEVKIT else project + "/"


def tag_base(project: str, trunk: str) -> str:
    return tag_prefix(project) + trunk


def next_tag(project: str, trunk: str, existing: set[str]) -> str:
    """给定已存在的标签集合，算出该主干的下一个标签名。"""
    base = tag_base(project, trunk)
    if base not in existing:
        return base
    nums = [
        int(m.group(1))
        for name in existing
        if (m := re.fullmatch(re.escape(base) + r"\.(\d+)", name))
    ]
    return f"{base}.{(max(nums) + 1) if nums else 1}"


def changed_paths(repo: str, token: str, before: str, after: str) -> list[dict] | None:
    """返回本次推送的改动文件列表；无法比较时返回 None（表示退化为全部）。"""
    if not before or before == ZERO_SHA:
        return None
    status, data = api("GET", f"{API}/repos/{repo}/compare/{before}...{after}", token)
    if status != 200 or not data:
        return None
    return data.get("files", [])


def scan_changes(files: list[dict]) -> dict[str, dict]:
    """把改动文件按项目归拢。

    返回 {项目: {"trunks": [...], "project_touched": bool}}。
    project_touched 表示该项目 code/ 下有改动（含未落到具体主干的情况）。
    """
    result: dict[str, dict] = {}
    for f in files:
        # 跳过纯重命名：整棵 code/ 搬进项目层的那次提交，每个文件都只是换了
        # 路径，若按路径首段判定会被认成所有主干都改了，一次发出多个 Release。
        if f.get("status") == "renamed":
            continue
        parts = f.get("filename", "").split("/")
        # 路径形态：projects/<项目>/code/[<主干>/]<文件>
        if len(parts) < 4 or parts[0] != "projects" or parts[2] != "code":
            continue
        project = parts[1]
        entry = result.setdefault(project, {"trunks": [], "project_touched": False})
        entry["project_touched"] = True
        if len(parts) >= 5:
            trunk = parts[3]
            if trunk not in entry["trunks"]:
                entry["trunks"].append(trunk)
    return result


def existing_tags(repo: str, token: str, project: str, trunk: str) -> set[str]:
    base = tag_base(project, trunk)
    url = f"{API}/repos/{repo}/git/matching-refs/tags/{urllib.parse.quote(base)}"
    status, data = api("GET", url, token)
    if status != 200 or not data:
        return set()
    names = set()
    for ref in data:
        name = ref.get("ref", "").removeprefix("refs/tags/")
        if name == base or name.startswith(base + "."):
            names.add(name)
    return names


def create_tag(repo: str, token: str, tag: str, sha: str) -> bool:
    status, _ = api(
        "POST", f"{API}/repos/{repo}/git/refs", token, {"ref": f"refs/tags/{tag}", "sha": sha}
    )
    return status in (201, 200)


def asset_name(filename: str) -> str:
    """把附件名转成 ASCII 安全形式。

    GitHub 会把 Release 附件名里的非 ASCII 字符换成别的字符：实测 Φ 变成了
    `.`，于是 deepseek_A1_V_Φ8_Fix_CN.html 上传后下载名成了
    deepseek_A1_V_.8_Fix_CN.html。上传时用 Phi 代替 Φ，另用 label 参数保留
    原写法供界面显示（label 若同样被净化也无副作用）。
    """
    return filename.replace("Φ", "Phi")


def upload_asset(repo: str, token: str, release_id: int, path: Path) -> bool:
    url = (
        f"{UPLOAD_API}/repos/{repo}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(asset_name(path.name))}"
        f"&label={urllib.parse.quote(path.name)}"
    )
    body = path.read_bytes()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("User-Agent", "devkit-auto-release")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"[告警] 上传 {path.name} 失败：HTTP {e.code}")
        return False


def _has_release_for_tag(repo: str, token: str, tag: str) -> bool:
    """该标签名下是否已经有 Release 存在（用于避免误删别人的标签）。"""
    status, _ = api(
        "GET", f"{API}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}", token
    )
    return status == 200


def _is_burned_payload(data) -> bool:
    """响应体是否在说「这个标签名已被不可变 Release 占用」。"""
    text = json.dumps(data, ensure_ascii=False) if data is not None else ""
    return "immutable" in text and "tag_name" in text


def publish_release(repo: str, token: str, release_id: int) -> tuple[bool, bool]:
    """把草稿改为正式发布。

    草稿阶段附件可以随便加；一旦 draft=False 且仓库开了 Immutable Releases，
    附件就锁死了。所以发布必须是最后一步，且只在附件全部就位后执行。

    返回 (是否成功, 是否因「标签名被不可变 Release 占用」而失败)。后一种失败
    是可恢复的：换一个带后缀的标签名重来即可，调用方据此自动递增后缀。
    """
    status, data = api(
        "PATCH", f"{API}/repos/{repo}/releases/{release_id}", token, {"draft": False}
    )
    if status in (200, 201):
        return True, False
    return False, _is_burned_payload(data)


def delete_release_and_tag(repo: str, token: str, release_id: int, tag: str) -> None:
    """回滚：删掉空壳 Release 与它占用的标签，避免下次被判定为「标签已存在」。"""
    status, _ = api("DELETE", f"{API}/repos/{repo}/releases/{release_id}", token)
    if status not in (204, 200, 404):
        print(f"[告警] 回滚时删除 Release {release_id} 失败（HTTP {status}），请手动清理。")
    # 标签可能已经挂在 Release 上被一起删掉，404 视为已清理
    status, _ = api(
        "DELETE", f"{API}/repos/{repo}/git/refs/tags/{urllib.parse.quote(tag)}", token
    )
    if status not in (204, 200, 404, 422):
        print(f"[告警] 回滚时删除标签 {tag} 失败（HTTP {status}），请手动清理。")


def release_trunk(
    repo: str,
    token: str,
    project: str,
    trunk: str,
    sha: str,
    mode: str,
    forced_tag: str | None = None,
) -> bool:
    trunk_dir = code_dir(project) / trunk
    # 兜底：即便调用方没过滤，归档目录也不得发布
    if not is_trunk_dir(trunk_dir):
        print(f"[告警] {project}/{trunk} 不是可发布的主干（归档或不存在），跳过。")
        return False
    files = sorted(trunk_dir.glob("deepseek_*.html"))
    if not files:
        print(f"[告警] {project}/{trunk} 下没有版本文件，跳过。")
        return True

    existing = existing_tags(repo, token, project, trunk)
    if forced_tag:
        if forced_tag in existing:
            print(f"[问题] 标签 {forced_tag} 已存在。换一个后缀，或删掉旧标签后重试。")
            return False
        tag = forced_tag
    else:
        tag = next_tag(project, trunk, existing)
    base = tag_base(project, trunk)
    # attempted 记录已试过的名字，被不可变 Release 烧掉后换下一个后缀
    attempted: set[str] = set()

    while True:
        attempted.add(tag)
        print(f"—— {project} · 主干 {trunk} → 标签 {tag}（{len(files)} 个附件）")

        ok, burned = _release_one(repo, token, project, trunk, tag, sha, mode, files)
        if ok:
            return True
        if not burned:
            return False

        # 名字被烧掉：删干净草稿与标签，换一个后缀重来
        print(
            f"[告警] 标签名 {tag} 已被一个不可变 Release 永久占用（删掉 Release 也解不开），"
            "改用下一个后缀重试。"
        )
        if forced_tag:
            # 手动指定了名字，不擅自换名，报错让人决定
            print(
                f"[问题] 手动指定的标签 {forced_tag} 无法使用。"
                f"请换一个后缀，例如 {_bump_tag(base, existing | attempted)}。"
            )
            return False
        tag = _bump_tag(base, existing | attempted)


def _bump_tag(base: str, taken: set[str]) -> str:
    """在 base 之后取一个未被占用的 `.N` 后缀。"""
    n = 1
    while f"{base}.{n}" in taken:
        n += 1
    return f"{base}.{n}"


def _release_one(
    repo: str,
    token: str,
    project: str,
    trunk: str,
    tag: str,
    sha: str,
    mode: str,
    files: list[Path],
) -> tuple[bool, bool]:
    """为一个确定的标签名执行「建标签 → 建草稿 → 传附件 → 发布」。

    返回 (是否成功, 是否因标签名被不可变 Release 占用而失败)。
    """
    if not create_tag(repo, token, tag, sha):
        print(f"[问题] 创建标签 {tag} 失败。")
        return False, False

    status, release = api(
        "POST",
        f"{API}/repos/{repo}/releases",
        token,
        {
            "tag_name": tag,
            "name": tag,
            "body": build_notes(project, trunk, mode),
            # 必须先建草稿：仓库开了 Immutable Releases，正式发布后附件就传不进去了
            "draft": True,
            "prerelease": False,
        },
    )
    if status not in (201, 200) or not release:
        burned = _is_burned_payload(release)
        # 只有确认这个名字是我们刚建的、且没有别的 Release 挂在上面时，才删标签。
        # 否则「该名字已有 Release」的 422 会把别人的标签删掉。
        if not _has_release_for_tag(repo, token, tag):
            api("DELETE", f"{API}/repos/{repo}/git/refs/tags/{urllib.parse.quote(tag)}", token)
        if burned:
            # 建草稿这一步就被判「名字不可用」，与发布时被拒是同一回事
            return False, True
        print(f"[问题] 创建 Release 草稿 {tag} 失败（HTTP {status}）。")
        return False, False

    release_id = release["id"]
    uploaded = 0
    for path in files:
        if upload_asset(repo, token, release_id, path):
            uploaded += 1

    if uploaded != len(files):
        print(f"[问题] {tag} 有附件未上传成功（{uploaded}/{len(files)}），已回滚草稿与标签。")
        delete_release_and_tag(repo, token, release_id, tag)
        return False, False

    published, burned = publish_release(repo, token, release_id)
    if not published:
        if burned:
            # 名字被烧掉是可恢复的，由调用方换后缀重试；先清干净
            delete_release_and_tag(repo, token, release_id, tag)
            return False, True
        print(f"[问题] {tag} 附件已传齐，但发布（draft=false）失败，已回滚草稿与标签。")
        delete_release_and_tag(repo, token, release_id, tag)
        return False, False

    print(f"   已发布 {tag}，附件 {uploaded}/{len(files)}")
    return True, False


# dispatch 的 trunk 来自 workflow_dispatch 的手工输入，会直接被拼进文件路径。
# 只允许单段目录名：挡住 `..`、`../x`、以及任何分隔符，避免读到 projects 之外。
SAFE_TRUNK_RE = re.compile(r"[^/\\]+")


def is_safe_trunk_name(trunk: str) -> bool:
    return bool(trunk) and trunk not in (".", "..") and bool(SAFE_TRUNK_RE.fullmatch(trunk))


def plan_dispatch(
    project: str, trunk: str, suffix: str
) -> tuple[list[tuple[str, str, str]], str | None, str]:
    """手动触发：为指定项目的指定主干补发一个 Release。"""
    if not is_safe_trunk_name(trunk):
        return [], None, f"[问题] 主干名不合法：{trunk!r}（不得包含路径分隔符或为 . / ..）"
    # 与自动路径用同一判定：归档目录（*_fix-archive）不是可发布主干。
    if not is_trunk_dir(code_dir(project) / trunk):
        msg = f"[问题] 找不到可发布的主干 projects/{project}/code/{trunk}。"
        if (code_dir(project) / trunk).is_dir():
            msg += "（该目录是归档，不能发布）"
        trunks = local_trunks(project)
        if trunks:
            msg += "现有主干：" + "、".join(trunks)
        return [], None, msg
    forced = f"{tag_base(project, trunk)}.{suffix}" if suffix else None
    reason = f"手动触发，补发 {project} 的主干 {trunk}"
    if suffix:
        reason += f"（指定标签后缀 {suffix}）"
    return [(project, trunk, "manual")], forced, reason


def plan_auto(
    files: list[dict] | None,
) -> tuple[list[tuple[str, str, str]], str]:
    """自动触发：按改动文件决定发布哪些 (项目, 主干, 模式)。

    目标是三元组而不是「目标 + 模式字典」：两者分开维护时，任何一条新增
    分支只要漏写一处就会失步，最后在 main() 里 KeyError。
    """
    if files is None:
        # 无法比较提交范围（force-push、compare 404 等）。此前的做法是「退化为
        # 给全部项目的全部主干各发一个 Release」——一次异常能连发十几个，
        # 且每个都新建标签，清理起来很麻烦。宁可这次不发，日志写清楚原因，
        # 需要时用 workflow_dispatch 手动补发。
        return [], "无法比较提交范围（可能是 force-push 或 compare 接口异常），为安全起见本次不自动发版；如需发布请手动触发并指定主干"

    changes = scan_changes(files)
    targets: list[tuple[str, str, str]] = []
    reasons: list[str] = []

    for project in sorted(changes):
        if not code_dir(project).is_dir():
            continue
        entry = changes[project]
        # 与 local_trunks 用同一判定：改了归档目录不算「动了主干」，
        # 否则会给归档发一个 changed 模式的 Release。
        real = [t for t in entry["trunks"] if is_trunk_dir(code_dir(project) / t)]
        if real:
            targets.extend((project, t, "changed") for t in real)
            reasons.append(f"{project}：" + "、".join(real))
        elif entry["project_touched"]:
            latest = latest_trunk(project)
            if latest:
                targets.append((project, latest, "no_changes"))
                reasons.append(f"{project}：未动主干（给 {latest} 发「无功能更新」）")

    if not targets:
        return [], "本次推送未改动任何项目的交付物，不发布任何 Release"

    return targets, "；".join(reasons)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    before = os.environ.get("BEFORE_SHA", "").strip()
    after = os.environ.get("AFTER_SHA", "").strip()
    dispatch_project = os.environ.get("DISPATCH_PROJECT", "").strip() or DEVKIT
    dispatch_trunk = os.environ.get("DISPATCH_TRUNK", "").strip()
    dispatch_suffix = os.environ.get("DISPATCH_SUFFIX", "").strip()

    if not repo or not token or not after:
        print("[问题] 需要 GITHUB_REPOSITORY、GITHUB_TOKEN、AFTER_SHA 环境变量。")
        return 1

    forced_tag: str | None = None

    targets: list[tuple[str, str, str]]

    if dispatch_trunk:
        if dispatch_project not in local_projects():
            print(
                f"[问题] 找不到项目 projects/{dispatch_project}/code/。现有项目："
                + ("、".join(local_projects()) or "（无）")
            )
            return 1
        targets, forced_tag, reason = plan_dispatch(
            dispatch_project, dispatch_trunk, dispatch_suffix
        )
        if not targets:
            print(reason)
            return 1
    else:
        files = changed_paths(repo, token, before, after)
        targets, reason = plan_auto(files)

    print(f"仓库 {repo} · {reason}")
    print("将发布：" + ("、".join(f"{p}/{t}" for p, t, _ in targets) if targets else "（无）"))
    print()

    if not targets:
        print("发布完成（无需发布）。")
        return 0

    ok = True
    for project, trunk, mode in targets:
        if not (code_dir(project) / trunk).is_dir():
            print(f"[告警] projects/{project}/code/{trunk} 不存在，跳过。")
            continue
        if not release_trunk(repo, token, project, trunk, after, mode, forced_tag):
            ok = False

    print()
    print("发布完成。" if ok else "发布结束，但存在失败项。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
