# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 本文件有两份副本：仓库内 `.repo-git/CLAUDE.md` 与会话工作区外层 `D:\dai\ccworks\htmls\CLAUDE.md`。除下方 `@` 导入路径外，两份内容保持一致，改动须同步。

## 工作约定

本文件的规则在每次会话启动时自动加载，优先级高于默认行为。

### 记忆

- 未经我在当前对话中明确要求，不得写入长期记忆或持久化载体（记忆文件、MEMORY.md、CLAUDE.md 等）。
- 判定标准：我是否明确说了"记住""记下来""保存到记忆/文档"一类指令。仅凭"这条信息看起来有用""以后可能用得上"不构成写入理由。
- 确有必要写入时，先在回复里说明要写什么、写到哪里，等我确认后再写。
- 我要求遗忘时删除对应条目；不确定删哪一条就先问，不得擅自批量清理。
- 此规则只约束跨会话的长期记忆；代码注释、版本记录、版本结构图等交付物本身的内容不受限。

### 提问

- 遇下列情况主动用提问工具问清，不要替我决定：
  - 需求存在歧义，或有两种以上合理解读
  - 存在多种合理方案，取舍取决于我的偏好（配色、风格、命名、结构、优先级）
  - 选项各有权衡（是否引入依赖、是否扩大改动范围、是否兼容旧版本）
  - 顺带发现了别的问题，要不要一并修
- 选项要写清可感知的后果与代价，不能只写名称。
- 一次把要问的问完，不要挤牙膏式反复打断。
- 拿不准就先问，不要"先做了再说"。
- 无法提问时（如所在模式不支持交互），选最保守的选项，并在回复里写明所选的假设。

### 链接

- 给我 URL 时直接输出可点击的完整链接，不要放进代码框，也不要用反引号包裹。
- 只有链接作为"需要原样复制的技术字符串"出现时（写进命令或配置值）才放进代码框，此时另起一行再给一条可点击版本。
- 不得用"点击这里""见此处"之类文字隐藏 URL；不得把 URL 折行拆断。

### 分支与 PR

@docs/branching.md

### 收尾汇报

每次回复末尾给出三段式汇报，顺序固定、标题独立：

| 段 | 写什么 | 为空时 |
|---|---|---|
| **结果** | 本次实际交付了什么（文件、版本号、验证方式与结论）。只陈述事实，不写过程。 | 写"无" |
| **问题** | 报错、失败、未解决项、缺陷、与预期的偏差、未能验证的部分。如实写，不淡化。 | 写"无" |
| **其他事项** | 需要我拍板的、后续建议、顺带发现的隐患、本次未处理的相关问题。 | 写"无" |

- 某段为空时必须写"无"，不得省略——省略会让人分不清是"没有"还是"漏了"。
- 三段不得互相掺杂：结果里不掺问题，问题里不夹带成果。
- 正文讲过程、汇报给结论，两者不互相替代。
- 纯对话轮次（无改动、无问题、无待办）可只用一行"结果"带过，其余两段省略。

## 仓库形态

- 外层会话工作区 `D:\dai\ccworks\htmls` 与 git 仓库 `.repo-git\` 是两层：git 操作只发生在仓库内；外层的 `cases/`、`videos/`、`tools/`、`releases/` 等不属于仓库。在仓库内打开的会话以仓库根为工作目录，无需 `.repo-git` 前缀。
- 外层 `.claude/skills/devkit-spec/` 是技能的仓库外副本（非符号链接），可独立更新使其立即生效；不要把两份副本混淆，改了要同步。
- 可能有多个会话并行操作同一仓库：**绝不**往 `.repo-git\` 主工作树里复制或覆盖文件，所有改动在独立 worktree（`git worktree add`）内完成，主工作树可能带着他人的未提交改动。
- 本仓库没有 `gh` CLI：调 GitHub API 用 `curl -k`（Windows 证书链问题），token 用 `git credential fill` 取。
- 行尾统一 LF（`.gitattributes` 的 `* text=auto eol=lf`），不要提交 CRLF 版本。

## 常用命令

所有检查脚本在仓库根执行。本地用 `python`（3.14），CI 用 `python3`。

| 命令 | 检查内容 |
|---|---|
| `python .github/scripts/link_check.py` | HTML / Markdown 相对链接是否指向存在的文件 |
| `python .github/scripts/size_guard.py` | 交付物单文件体积（>380 KB 告警，>520 KB 失败） |
| `python .github/scripts/smoke_test.py` | 无头 Chrome 逐个打开全部版本文件，查控制台报错与 `<title>` |
| `python .github/scripts/version_guard.py` | 版本号结构、四处一致性、`node --check` 语法可解析性 |
| `python .github/scripts/devkit_logic_test.py` | DevKit 行为单测（提示词拼装、版本解析、设置归一化、关键交互） |
| `python .github/scripts/snapshot_other_test.py` | Persona 快照字段存取与恢复 |
| `python .github/scripts/share_image_test.py` | Persona 分享图比例映射与画布输出 |
| `python .github/scripts/start_prompt_test.py` | Persona 起始提示词与多轮回复 |
| `python .github/scripts/test_release_planning.py` | 自动发布决策单测 |

- 跑发布决策单测：`python -m unittest discover -s .github/scripts -p 'test_*.py'`。该模式**只匹配 `test_release_planning.py`**；其余四个 `*_test.py` 是独立脚本而非 unittest 用例，需逐个 `python .github/scripts/<名字>.py` 执行。
- 需要浏览器的脚本（`smoke_test` / `devkit_logic_test` / `snapshot_other_test` / `share_image_test` / `start_prompt_test`）：Chrome 不在 PATH 时设 `CHROME_BIN`（Git Bash 下用 Windows 风格路径 `C:/Program Files/Google/Chrome/Application/chrome.exe`；`/c/...` 形式在部分脚本里传不到浏览器）；`version_guard.py` 另需 `node`（v26 已装）。
- 这些检查在 CI 上**只报告、不拦截**（`repo-checks.yml`、`version-guard.yml`）。
- Git Bash 会把 `rev:path` 里的 `/` 当路径转换，含这种参数的 git 命令前先 `export MSYS_NO_PATHCONV=1`。
- 多语言实现（`implementations/`）本地构建前先 `source toolchains.env`；EXE 产物不入库、只作 Release 附件，实际构建由 Actions 完成。

## 架构要点

- **发布根 = 仓库根**。GitHub Pages 从 `main` 根目录发布（`/ (root)` + `.nojekyll`）；根 `index.html` 是项目选择台，逐层进入项目页。Pages 不生成目录列表，`projects/`、各项目、各主干目录都必须有显式 `index.html`。
- **交付物是自包含单文件 HTML**：`projects/<项目>/code/<主干>/deepseek_<版本号>.html`，无构建、无后端；唯一对外**加载**的外部资源是 Google Fonts（CSP 只放行自身脚本与字体域），页面里的 AI 站点地址仅为超链接、不产生请求。新增文件必须同时登记到所在目录的 `index.html`，否则无法从目录页进入（`link_check` 只查「链接指向的文件存在」，不查「文件是否被引用」，漏登记不会报错）。
- **五个项目**：`devkit` / `submerge-pro` / `dircleaner` / `writer` / `persona`，版本号规则各项目自定。`version_guard.py` 只覆盖 `devkit` / `writer` / `persona`——`dircleaner` 与 `submerge-pro` 的产物均没有 `CURRENT_VERSION` 字段（`dircleaner` 的早期文件还是 `deepseek_html_<日期>_<随机>.html` 命名），硬套四处一致性检查全是误报。
- **版本文件四处自洽**：文件名 ⟷ 文件头「版本代号」⟷ `CURRENT_VERSION` ⟷ 版本结构块「当前最新版本」，`version_guard` 强制一致。文件内 `VERSION_HISTORY` 是自动发布说明的唯一来源（`make_release_notes.py` 解析它），改版本时必须同步追加。
- **版本命名规范**：DevKit 的版本架构（层级 / 循环扩展 / 变体标识 / `_CN` / `_GLOBAL` 语言后缀）完整正文在 `.claude/skills/devkit-spec/`（`SKILL.md` + `references/`），README「版本命名体系」是摘要。改版本号前先读技能里的现行规范，不要凭记忆。
- **DevKit 应用内部分层（Φ10 起）**：Constants → Domain（纯逻辑、不碰 DOM：`PromptBuilder` / `VersionService` / `ProjectModel`）→ Store（单一状态树 + `dispatch` / `subscribe`）→ Services（读写 Store，不碰 DOM）→ UI（视图只渲染、事件转 dispatch）→ App（只装配）。新功能按此分层放，不要跨层。
- **浏览器行为测试的机制**：产品文件仅在 URL 带 `#selftest` 时把内部对象挂到 `window.__devkitTest`；测试脚本把产品文件复制到临时目录、注入驱动脚本、用本地 HTTP `/gate` 挂住 load、`chrome --headless=new --dump-dom` 从 `<title>` 读断言结果。新增行为测试沿用此模式，不要改产品文件的非测试路径。
- **推送 `main` 即自动发布**（`auto_release.py`）：按「项目 · 主干」分别建标签发 Release，devkit 用裸主干名（`A1_V_Φ10`），其他项目加前缀（`writer/A1_I_Φ6`）；仓库开启 Immutable Releases，标签名发布后不可重用，脚本必须走「建草稿 → 传附件 → 转正式」顺序。
- **`pull_request_target` 安全前提**：`pr-labeler.yml` 与 `cleanup-merged-branches.yml` 用 `pull_request_target` 拿写权限，**不得检出 PR 的代码**，只通过 API 读改动列表 / 操作分支；改这两个工作流时保持这一点。
- `implementations/` 下的多语言实现**只做安全修复、不跟进功能迭代**，规范见 `docs/multi-language.md`；修改前先读该文件。
