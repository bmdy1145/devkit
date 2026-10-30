#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理已合并 PR 遗留的分支。

GitHub 的「自动删除头部分支」只对同仓分支生效：来自 fork 的 PR 合并后，
head 分支留在 fork 上；而为了让堆叠 PR 能指定 base，feature 分支又在上游
也放了一份。两边都会越积越多，本脚本负责清理上游这一份。

每次运行都做全量扫描：拉取最近 100 个已关闭的 PR，凡是已合并的，就把它
head 分支在本仓库的残留删掉。这个动作是幂等的，多处触发（PR 合并时、每周
定时、手动）同时存在也不会互相干扰，且每次运行都会顺带清掉历史积压。

安全规则（任一命中即跳过）：
  · 默认分支（main）永不删除
  · 任何仍被「打开的 PR」当作 base 的分支不删 —— 堆叠链上的父分支要等
    子 PR 合并后才轮到它，否则会把子 PR 的 base 抽掉
  · 未合并就被关闭的 PR，其分支不删（可能还要继续用）
  · 该分支不存在于本仓库时跳过（正常情况：它只存在于 fork）
  · 分支当前 tip 与已合并 PR 的 head sha 不一致时跳过 —— 说明这个分支要么
    已被同名重建、要么被人续了新提交，都不是「已完成使命可以删」的状态

只清理本仓库（上游）的分支。fork 上的分支 GITHUB_TOKEN 无权删除——那需要
另配一个有 fork 写权限的令牌，本脚本刻意不碰。

用法：
    本地试跑（只打印不删）：
        DRY_RUN=1 GITHUB_REPOSITORY=bmdy1145/devkit GITHUB_TOKEN=xxx \\
            python3 .github/scripts/cleanup_branches.py

退出码：0 = 执行完毕（含跳过）；1 = 出现无法忽略的错误。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
MAX_PRS = 100


def api(method: str, url: str, token: str):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "devkit-cleanup-branches")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    dry_run = os.environ.get("DRY_RUN", "") not in ("", "0", "false")

    if not repo or not token:
        print("[问题] 需要 GITHUB_REPOSITORY 与 GITHUB_TOKEN 环境变量。")
        return 1

    status, repo_info = api("GET", f"{API}/repos/{repo}", token)
    if status != 200 or not repo_info:
        print(f"[问题] 读取仓库信息失败（HTTP {status}）。")
        return 1
    default_branch = repo_info.get("default_branch", "main")

    status, branches = api("GET", f"{API}/repos/{repo}/branches?per_page=100", token)
    if status != 200:
        print(f"[问题] 读取分支列表失败（HTTP {status}）。")
        return 1
    existing = {b["name"] for b in (branches or [])}

    status, open_prs = api("GET", f"{API}/repos/{repo}/pulls?state=open&per_page=100", token)
    if status != 200:
        print(f"[问题] 读取打开的 PR 失败（HTTP {status}）。")
        return 1
    protected = {pr["base"]["ref"] for pr in (open_prs or [])}
    protected.add(default_branch)

    status, closed_prs = api(
        "GET",
        f"{API}/repos/{repo}/pulls?state=closed&per_page={MAX_PRS}&sort=updated&direction=desc",
        token,
    )
    if status != 200:
        print(f"[问题] 读取已关闭的 PR 失败（HTTP {status}）。")
        return 1

    # 只比对名字会误删：某个已合并 PR 的 head 分支被删后，用户可能用同名重建
    # 了一个新分支（内容完全不同）。所以必须再比对 tip commit —— 只有分支
    # 当前指向的提交与 PR 的 head sha 一致，才说明它就是那个已完成使命的分支。
    candidates: list[tuple[str, str]] = []   # (ref, head_sha)
    seen: set[str] = set()
    for pr in closed_prs or []:
        if not pr.get("merged_at"):
            continue
        head = pr.get("head") or {}
        ref, head_sha = head.get("ref"), head.get("sha")
        if not ref or not head_sha:
            continue
        if ref not in existing or ref in protected or ref in seen:
            continue

        status, branch = api(
            "GET", f"{API}/repos/{repo}/git/ref/heads/{ref}", token
        )
        tip = ((branch or {}).get("object") or {}).get("sha") if status == 200 else None
        if tip != head_sha:
            # 分支要么已被新内容覆盖，要么读不到 —— 两种情况都不动它
            print(f"[跳过] {ref}：当前 tip 与已合并 PR 的 head 不一致（可能已被重建）")
            seen.add(ref)
            continue
        seen.add(ref)
        candidates.append((ref, head_sha))

    mode = "试运行（只打印）" if dry_run else "实际删除"
    print(f"仓库 {repo} · 模式：{mode} · 默认分支 {default_branch}")
    print(f"已有分支 {len(existing)} 个，扫描最近 {len(closed_prs or [])} 个已关闭 PR")
    print(f"保留：{', '.join(sorted(protected))}")
    print()

    if not candidates:
        print("没有可清理的分支。")
        return 0

    failed: list[str] = []
    for ref, _ in sorted(candidates):
        if dry_run:
            print(f"[试运行] 将删除 {ref}")
            continue
        # 分支名可能含 `#` 等字符，拼进 URL 前要编码
        status, _ = api(
            "DELETE",
            f"{API}/repos/{repo}/git/refs/heads/{urllib.parse.quote(ref)}",
            token,
        )
        if status in (204, 200):
            print(f"已删除 {ref}")
        else:
            failed.append(f"{ref}（HTTP {status}）")
            print(f"[告警] 删除 {ref} 失败：HTTP {status}")

    for f in failed:
        print(f"[问题] {f}")

    print()
    action = "将删除" if dry_run else "已删除"
    print(f"清理完成：{action} {len(candidates)} 个分支，失败 {len(failed)} 个。")
    # 删除失败必须让工作流变红，否则失败被静默吞掉
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
