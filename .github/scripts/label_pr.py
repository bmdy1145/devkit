#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按改动路径给 PR 自动打标签。

标签不存在时由本脚本自动创建，因此不需要事先在网页端手工建标签。

权限说明：本脚本必须由 `pull_request_target` 触发。来自 fork 的 PR 在
`pull_request` 事件下只能拿到只读令牌，打不上标签；`pull_request_target`
在 base 仓库上下文里运行，令牌可写。这里**不检出 PR 的代码**，只读改动
文件列表，因此不存在执行不可信代码的风险。

用法：
    CI：由 .github/workflows/pr-labeler.yml 调用

退出码：0 = 成功（含无匹配）；1 = 出错。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"

# (路径前缀或精确路径, 标签)
#
# 注意：交付物已迁入项目层（PR #16），路径从 code/ 变成了
# projects/<项目>/code/。旧规则还写着裸的 "code/"，迁移后**所有** PR 都匹配
# 不上，一律落进 area:other，标签等于失效。
#
# 顺序有意义：先匹配更具体的前缀，命中即停。
RULES: list[tuple[str, str]] = [
    ("projects/devkit/code/", "area:devkit"),
    ("projects/writer/code/", "area:writer"),
    ("projects/dircleaner/code/", "area:dircleaner"),
    ("projects/submerge-pro/code/", "area:submerge-pro"),
    ("projects/persona/code/", "area:persona"),
    ("projects/", "area:projects"),
    (".github/", "area:ci"),
    ("docs/", "area:docs"),
    ("README.md", "area:docs"),
    ("README.en.md", "area:docs"),
    ("CLAUDE.md", "area:docs"),
    ("SECURITY.md", "area:docs"),
    ("SECURITY.en.md", "area:docs"),
    ("LICENSE", "area:docs"),
]

LABEL_META = {
    "area:devkit": ("1f77b4", "DevKit 交付物"),
    "area:writer": ("e0a458", "Writer（小说编辑器）交付物"),
    "area:dircleaner": ("0e8a8a", "DirCleaner 交付物"),
    "area:submerge-pro": ("8250df", "SubMerge Pro 交付物"),
    "area:persona": ("7fd1c1", "Persona（人设编辑器）交付物"),
    "area:projects": ("bfd4f2", "项目层页面（projects/ 下的索引与落地页）"),
    "area:ci": ("6f42c1", "仓库自动化与配置"),
    "area:docs": ("0e8a16", "文档与约定"),
    "area:other": ("808080", "未归类路径，出现时说明有新目录需要纳入规则"),
}

FALLBACK_LABEL = "area:other"


def api(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "devkit-label-pr")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def ensure_label(repo: str, token: str, label: str) -> None:
    color, description = LABEL_META.get(label, ("808080", ""))
    status, _ = api(
        "POST",
        f"{API}/repos/{repo}/labels",
        token,
        {"name": label, "color": color, "description": description},
    )
    # 201 新建成功；422 表示已存在，都算正常
    if status not in (201, 422):
        print(f"[告警] 创建标签 {label} 返回 HTTP {status}（若已存在可忽略）")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    pr_number = os.environ.get("PR_NUMBER", "")

    if not repo or not token or not pr_number:
        print("[问题] 需要 GITHUB_REPOSITORY、GITHUB_TOKEN、PR_NUMBER 环境变量。")
        return 1

    status, files = api(
        "GET", f"{API}/repos/{repo}/pulls/{pr_number}/files?per_page=100", token
    )
    if status != 200 or files is None:
        print(f"[问题] 读取 PR 改动文件失败（HTTP {status}）。")
        return 1

    paths = [f.get("filename", "") for f in files]
    if not paths:
        print("该 PR 没有改动文件，跳过。")
        return 0

    labels: list[str] = []
    for path in paths:
        for prefix, label in RULES:
            if path == prefix or path.startswith(prefix):
                if label not in labels:
                    labels.append(label)
                break

    if not labels:
        labels.append(FALLBACK_LABEL)

    for label in labels:
        ensure_label(repo, token, label)

    status, _ = api(
        "POST", f"{API}/repos/{repo}/issues/{pr_number}/labels", token, {"labels": labels}
    )
    if status not in (200, 201):
        print(f"[问题] 应用标签失败（HTTP {status}）。")
        return 1

    print(f"已为 PR #{pr_number} 打上：{', '.join(labels)}")
    print(f"（依据 {len(paths)} 个改动文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
