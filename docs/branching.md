# 分支与 PR 约定

> 本文件由项目根 `CLAUDE.md` 与 `.repo-git/CLAUDE.md` 通过 `@` 导入，会话启动时自动加载。
> 规则只维护在这一处，改这里即两处同时生效，不要在两份 CLAUDE.md 里各写一份。

## 流程

改动不直推 `main`。流程为：

1. 在 `.repo-git/` 建 feature 分支
2. 推送到**两个远端**（缺一不可，原因见「堆叠 PR」）：

   ```
   git push -u kun <分支>
   git push -u origin <分支>
   ```

3. 提 PR：`head = KunOcean:<分支>`，`base = bmdy1145:main`
4. 由仓库主在网页版审阅并合并
5. 合并后清理两个远端上的该分支——GitHub 的「自动删除头部分支」只删同仓分支，来自 fork 的 PR 不会删 fork 上的分支，上游那份更不会自动删

## 两个远端

| 远端 | 仓库 | 职责 |
|------|------|------|
| `kun` | https://github.com/KunOcean/devkit.git | 下游 fork，PR 的 `head` 分支所在地 |
| `origin` | https://github.com/bmdy1145/devkit.git | 权威仓，Pages 站点 https://bmdy1145.github.io/devkit/ 挂在它名下，也是 `main` 的跟踪上游。**feature 分支也要在这里放一份**，否则堆叠 PR 无法指定 base |

## 堆叠 PR

**前提：feature 分支必须同时推到两个远端。**

跨仓 PR 的 `base` 必须是**上游（bmdy1145/devkit）里真实存在的分支**。只推到 fork 的分支，上游看不到，无法充当 base——GitHub 会直接拒绝创建 PR，报 `PullRequest.base (invalid)`（2026-10-03 实测踩到过）。

若上一个 PR 尚未合并而下一版已经开始：

- 新分支基于**上一个未合并的分支**；
- 新旧两个分支**都要推到 `kun` 与 `origin`**；
- 提 PR 时 `base` 填**上一个分支的名字**（上游已有同名分支，可以指定），不是 `main`；
- **上一个 PR 合并后，必须手动把下一个 PR 的 `base` 改回 `main`**；
- **禁止**让两个分支都从 `main` 分叉——那样第二个 PR 会把第一批改动再算一遍，或直接回退已审查过的内容。

### 为什么必须手动改 base

合并一个堆叠 PR 时，GitHub 把它合进的是**它的 base 分支**，不是 `main`。而 GitHub 只在 base 分支被**删除**时才自动改子 PR 的 base；「合并」这个动作本身不会触发自动改。

偏偏来自 fork 的 PR 分支不受仓库「自动删除头部分支」约束（那一项只对同仓分支生效），中间分支会一直留着，子 PR 的 base 也就一直指着它。结果是：**子 PR 被合进中间分支，内容永远进不了 `main`**。

> 2026-10-03 实测踩到：PR #6 与 #7 分别在 base 为 `ci/trigger-scope`、`docs/stacking-fix` 时被合并，两个 PR 的内容全部滞留在这两条中间分支上，`main` 只拿到了 PR #5。事后只能另开一个 PR 把内容 cherry-pick 到 `main` 上抢救。

所以合并顺序应为：**合并父 PR → 立刻把子 PR 的 base 改回 `main` → 再合并子 PR**。父 PR 合并后若发现子 PR 的 base 仍指向中间分支，先停下来改 base，不要直接点合并。

若两批改动确实互不重叠，也可以不堆叠、各自从 `main` 分叉，只要各自的新分支都推两个远端即可；但一旦有重叠，必须走上面的堆叠路径。

## 长期分支 `test`

`test` 是仓库**唯一**的长期分支，用于承载测试版：

| 项 | 约定 |
|---|---|
| 用途 | 测试版（带内置自检）的集成分支；`feature` → `test` → `main` |
| 内容位置 | `projects/<项目>/test/<测试版本>/`——**不在** `code/` 下 |
| 与 `code/` 的关系 | `test` 分支上**不改** `code/` 下的正式交付物；正式版改动仍走 feature → `main` |
| 发布 | push 到 `test` 会触发 `release-on-main.yml`，但只发 `test/` 桶：标签前缀 `test/<项目>/`、Release 标记为 **prerelease**、标题与正文带【test】 |
| Pages | Pages 只从 `main` 发布。**测试版页面必须在 main 上才可见**，所以要让用户访问到测试版，需把 `test` 合入 `main` |
| 分支清理 | `cleanup_branches.py` 把 `test` 列入 `LONG_LIVED_BRANCHES`，不会被自动删除 |
| 直推 | 推 `test` 到 `origin` 与推 `main` 同属「共享状态变更」，**同样需要逐次授权** |

从一个测试版转为正式版时：在 `main` 上按正常版本规则产出正式版本，测试版目录保留作为历史（或按需删除）。

## 红线

- 不得 approve 自己提出的 PR（GitHub 硬性禁止）；合并权始终在仓库主手上。
- 直推 `main`（含推送 `origin`）仍需逐次明确授权；未获授权不得推送。
- 两个远端的推送权限均已证实可用（`kun` 与 `origin` 各推过 feature 分支）。若某次推送意外被拒，立即告知，**不得改推另一个远端绕过**。

## 为什么不用仓库设置解决

GitHub 仓库设置里没有"上一版未合并就不许开下一版"这类开关：

- **Merge queue** 只管把**已批准**的 PR 依次合并，未批准的进不了队列；
- **Branch protection / Rulesets** 只管能否直推 `main` 与合并门槛；
- **Auto-merge** 管单个 PR 在条件满足后自动合并；
- **Update branch** 方向相反，是把 base 合进 head。

堆叠关系只能靠建分支时选对 `base` 来管，属协作约定，不属仓库设置。
