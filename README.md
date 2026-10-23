[中文](README.md) | [English](README.en.md)

# AI 开发快捷工具箱（DevKit · 中文版）

在线预览：https://bmdy1145.github.io/devkit/
仓库：https://github.com/bmdy1145/devkit

## 简介

DevKit 是一个**纯 HTML 单文件**的本地开发辅助工具，直接用浏览器打开即可使用，无需安装、无需构建、无后端依赖。所有数据保存在浏览器内存中，不联网、不上传。

工具以「工作流步骤」为核心组织协作过程：为每个步骤填写灵感（需求）并粘贴当前代码，工具会把步骤内置的提示词模板与你的内容组合成一段完整指令，一键复制后发送给任意 AI 对话工具。

## 功能要点

- **工作流页签**：内置版本规划、需求分析、安全审计、性能审计、结构重构、单元测试、集成测试、版本号推导、多语言适配、部署运维、性能监控、数据分析、无障碍审计、架构设计、安全合规、完全重写等 22 个提示词模板，另有空白页签
- **多项目管理**：项目标签栏，可新建/切换/关闭项目，每个项目独立维护页签与编辑区
- **灵感同步**：同项目内页签灵感可一键同步，关闭时清空其他页签
- **组合预览**：实时预览将要发送给 AI 的完整指令，支持复制、仅复制需求、下载并复制
- **规范提示词**：内置本项目的《规范提示词》，可整体复制
- **代码编辑区**：行号同步滚动、粘贴、复制、清空、上传/拖拽导入、导出代码（多后缀）、「演化」载入自身源码
- **AI 处理结果区**：粘贴 AI 返回内容，一键覆盖到代码区
- **版本历史**：树形折叠展示，默认只展开里程碑节点，支持展开/折叠全部并保持视口位置
- **全站视觉皮肤**：功能逻辑九套皮肤完全一致，仅视觉层不同，见下方「视觉皮肤」
- **主题切换**：入口在左上角，首次运行引导内选择一次并记住；具体可选维度随皮肤而定
- **性能模式**：切换后降低预览刷新频率（从每秒同步改为按需）
- **配置导入/导出**：导出 `devkit_config.json`，支持整包覆盖还原
- **文件快捷命名**：选择目录后按 `Deepseek_ + 自定义内容 + 原后缀` 重命名
- **快捷键**：`Esc` 关闭当前弹窗

## 视觉皮肤

同一份功能代码配了九套皮肤，各自是一个独立的单文件版本，互不影响：

| 版本 | 皮肤 | 主题维度 |
|------|------|----------|
| `A1_V_Φ9_Clean_CN` | 简约：Roboto / Poppins / Inconsolata，8pt 基线网格，圆角 6/8px，克制的柔和阴影 | 暗色简约 / 亮色简约 / 跟随系统 |
| `A1_V_Φ9_Material_CN` | 材料设计（MD3）：Roboto + Fira Code，五级分层表面、色调调色板、状态层叠加、elev-1~5 高程，圆角 4/8/12/28px | 暗色 / 亮色 / 跟随系统 |
| `A1_V_Φ9_Minimal_CN` | 极简：Open Sans / Inter / Inconsolata，近乎单色 + 单一靛蓝强调，无投影，留白 + 1px 分隔线分区 | 暗色极简 / 亮色极简 / 跟随系统 |
| `A1_V_Φ9_Premium_CN` | 高级质感：Inter + JetBrains Mono，精准间距节奏、柔和阴影层次、精细字距行高 | 暗色高级 / 亮色高级 / 跟随系统 |
| `A1_V_Φ9_Shadcn_CN` | Shadcn：Geist + Fira Code，黑白灰单色系 + hsl() 语义令牌，1px 边框分层、扁平无投影 | Shadcn 暗色 / 亮色 / 跟随系统 |
| `A1_V_Φ9_Mono_CN` | 全等宽：Space Mono + JetBrains Mono，去辉光、1px 硬描边、小圆角 | 明暗（dark / light / auto）× 强调色（matrix 矩阵绿 / cold 冷白 / amber 琥珀），共 6 套 |
| `A1_V_Φ9_Neon_CN` | 电光霓虹：近实心面板 + 彩色描边 + 多层外发光，无背景模糊 | 暗色霓虹 / 亮色霓虹 / 跟随系统 |
| `A1_V_Φ9_Glass_CN` | 毛玻璃：半透明叠层 + 背景模糊 + 发光描边 | 暗色玻璃 / 亮色玻璃 / 跟随系统 |
| `A1_V_Φ9_CN` | 基准皮肤（无皮肤，数字主题体系） | 原 theme 主题体系 |

九者同属主干 `A1_V_Φ9`。Φ9 的增量改动是**「关于 DevKit」弹窗（点击左上角 DevKit 字样打开）新增 Pages 站点首页链接**，并同步改造站点项目页：顶部新增「九款皮肤 · 直接打开」区块，从站点首页进入应用由三次点击降为两次。功能逻辑、提示词与模板正文与 Φ8 的 Fix_Fix 完全一致。

Φ8 的增量改动是**全站响应式、多比例与触屏适配**：viewport 增加 `viewport-fit=cover`，高度改用 `100dvh` 并接入 `env(safe-area-inset-*)` 安全区；新增宽度断点 ≥1800 / ≤1024 / ≤820 / ≤560 与高度断点 ≤520；窄屏改为纵向堆叠、步骤列表横滑、顶栏两行图标化；触屏下放大热区；分栏拖拽由 mouse 事件改为 pointer 事件。九款皮肤共用同一套适配层。

其中八款皮肤（除基准皮肤）的主题维度统一为 `themePref` 三态——暗色 / 亮色 / 跟随系统，首次运行引导内选择一次并以 `devkit_theme_pref` 记住，`auto` 下实时跟随系统深浅色；基准皮肤仍保留原有的数字 `theme` 主题体系。

版本号中 `Glass` / `Neon` / `Mono` / `Clean` / `Material` / `Minimal` / `Premium` / `Shadcn` 是**变体标识**（不占层级）。

上一代 `A1_V_Φ8` 与 Φ9 **并行可选**，保留在 `projects/devkit/code/A1_V_Φ8/`，含九套皮肤，迭代层为 `Fix_Fix`；更早的 `A1_V_Φ7`（四套皮肤）与 `A1_V_Φ5`（两个版本）、`A1_V_Φ4`（一个版本）也一并保留在 `projects/devkit/code/` 下供历史参照——Φ7 之后才有皮肤变体，Φ5 / Φ4 两代没有。

## 使用方式

1. **最省事：直接下 Release。** 每次 `main` 更新都会自动发布一版，按主干打包附上该代全部皮肤，点一下就下载，不必逐层点进目录。入口见 https://github.com/bmdy1145/devkit/releases
2. **在线阅读：**从站点首页进入 https://bmdy1145.github.io/devkit/projects/devkit/ ，顶部「九款皮肤 · 直接打开」点一下即用；也可以直接下载 `projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Clean_CN.html`
3. 双击用浏览器打开（Chrome / Edge 等现代浏览器）
4. 在「工作流步骤」中选择步骤 → 填写灵感、粘贴代码 → 点击「复制」→ 粘贴到 AI 对话工具

> 提示：目录选择、原文件删除等能力依赖浏览器的文件系统访问 API（Chromium 内核支持最佳）。

## 版本命名体系

项目采用「四层基础 + 循环扩展」的版本命名：

| 层级 | 标识符 | 说明 |
|------|--------|------|
| 第1层 | 分支代号（A1、A2） | 由使用者指定 |
| 第2层 | 罗马数字（I、II、III…） | 推翻重做或重大升级时递增，后续层级重置 |
| 第3层 | Φ + 阿拉伯数字（Φ1、Φ2…） | 同一罗马数字版本上的增量修改 |
| 第4层 | 英文标识（Fix、Perf、Doc…） | 微调或小修；幅度不到增量级时追加，Φ 数字不递增。**皮肤名不属于此层**，见下方变体标识说明 |

第 4 层之后按 `B1 → I → Ψ1 → 英文标识 → C1 …` 循环扩展，例如 `A1_I_Φ1_Fix_B1_I_Ψ1_Fix_C1`。

**变体标识不占层级**：皮肤名（Glass / Neon / Mono / Clean / Material / Minimal / Premium / Shadcn）表示"同一版本的并行皮肤"，属于变体标记而非迭代层，缀在 Φ 层之后、语言后缀之前。因此 `A1_V_Φ8_Glass_Fix_CN` 中 `Glass` 是变体标识、`Fix` 才是第四层英文标识，该版本号合规；`A1_V_Φ9_Glass_CN` 同理由此成立。变体标识不得用于表达迭代语义（如 `Glass2`）。

项目并行维护两个语言变体，共享同一主干版本号，仅末尾追加后缀区分：`_CN`（中文版）、`_GLOBAL`（多语言版）。本仓库为**中文版**。

## 目录结构

```
devkit/                              # 仓库根（GitHub Pages 发布目录）
├── README.md / README.en.md        # 项目说明（必须留在根目录，GitHub 首页据此渲染）
├── SECURITY.md / SECURITY.en.md    # 安全策略（必须留在根目录，Security 选项卡据此显示）
├── LICENSE                          # GPLv3 许可证全文（必须留在根目录）
├── index.html                       # GitHub Pages 落地页（项目选择台）
├── 404.html                         # 旧路径兜底：把迁移前的 /code/** 跳到新位置
├── .nojekyll                        # 关掉 Jekyll 处理（纯静态站点，避免下划线目录被忽略）
├── .github/                         # PR 模板、CODEOWNERS、工作流、Dependabot
│   ├── workflows/                   # 版本结构校验、仓库体检、自动发布、分支清理、PR 标签
│   └── scripts/                     # 各工作流调用的检查脚本，本地可同命令运行
├── docs/                            # 仓库级协作约定（跨项目通用）
│   ├── .gitkeep                     # 仅占位（git 无法跟踪空目录）
│   ├── branching.md                 # 分支与 PR 约定（由 CLAUDE.md 用 @ 导入）
│   └── github-settings.md           # GitHub 仓库设置手册（分支保护、Actions 等网页端配置）
├── projects/                        # 各项目各占一个目录，目录内自带落地页
│   ├── index.html                   # /projects/ 目录索引
│   ├── devkit/                      # 项目：AI 开发快捷工具箱
│   │   ├── index.html               # 项目落地页（皮肤直达 + 下载直达 + 分支卡片）
│   │   └── code/
│   │       ├── index.html                   # 分支目录索引
│   │       ├── A1_V_Φ9/                     # 当前主干
│   │       │   ├── index.html                              # 本分支版本列表
│   │       │   ├── deepseek_A1_V_Φ9_Clean_CN.html          # 简约
│   │       │   ├── deepseek_A1_V_Φ9_Material_CN.html       # 材料设计（MD3）
│   │       │   ├── deepseek_A1_V_Φ9_Minimal_CN.html        # 极简
│   │       │   ├── deepseek_A1_V_Φ9_Premium_CN.html        # 高级质感
│   │       │   ├── deepseek_A1_V_Φ9_Shadcn_CN.html         # Shadcn
│   │       │   ├── deepseek_A1_V_Φ9_Mono_CN.html           # 全等宽 + 双轴主题
│   │       │   ├── deepseek_A1_V_Φ9_Neon_CN.html           # 电光霓虹
│   │       │   ├── deepseek_A1_V_Φ9_Glass_CN.html          # 毛玻璃
│   │       │   └── deepseek_A1_V_Φ9_CN.html                # 基准皮肤
│   │       ├── A1_V_Φ8/                     # 上一代主干（与 Φ9 并行可选）
│   │       │   ├── index.html                                    # 本分支版本列表
│   │       │   ├── deepseek_A1_V_Φ8_Clean_Fix_Fix_CN.html        # 简约
│   │       │   ├── deepseek_A1_V_Φ8_Material_Fix_Fix_CN.html     # 材料设计（MD3）
│   │       │   ├── deepseek_A1_V_Φ8_Minimal_Fix_Fix_CN.html      # 极简
│   │       │   ├── deepseek_A1_V_Φ8_Premium_Fix_Fix_CN.html      # 高级质感
│   │       │   ├── deepseek_A1_V_Φ8_Shadcn_Fix_Fix_CN.html       # Shadcn
│   │       │   ├── deepseek_A1_V_Φ8_Mono_Fix_Fix_CN.html         # 全等宽 + 双轴主题
│   │       │   ├── deepseek_A1_V_Φ8_Neon_Fix_Fix_CN.html         # 电光霓虹
│   │       │   ├── deepseek_A1_V_Φ8_Glass_Fix_Fix_CN.html        # 毛玻璃
│   │       │   └── deepseek_A1_V_Φ8_Fix_Fix_CN.html              # 基准皮肤
│   │       ├── A1_V_Φ8_fix-archive/         # Φ8 的 Fix 层历史归档
│   │       │   └── index.html                              # 归档页（九款 Fix）
│   │       ├── A1_V_Φ7/                     # 更早的历史主干
│   │       │   ├── index.html
│   │       │   ├── deepseek_A1_V_Φ7_Mono_CN.html
│   │       │   ├── deepseek_A1_V_Φ7_Neon_CN.html
│   │       │   ├── deepseek_A1_V_Φ7_Glass_CN.html
│   │       │   └── deepseek_A1_V_Φ7_CN.html
│   │       ├── A1_V_Φ5/                     # 早期主干（历史参照）
│   │       │   ├── index.html
│   │       │   ├── deepseek_A1_V_Φ5_Fix_CN.html          # 图标字体本地内嵌 + 规范新增版本红线
│   │       │   └── deepseek_A1_V_Φ5_CN.html              # 修复 Φ4 遗留 9 项 + 追加 4 项复核修正
│   │       └── A1_V_Φ4/                     # 早期主干（历史参照）
│   │           ├── index.html
│   │           └── deepseek_A1_V_Φ4_CN.html              # 全面修复 15 项缺陷
│   ├── submerge-pro/                # 项目：双语字幕翻译拆分工具
│   │   ├── index.html
│   │   └── code/
│   │       ├── index.html
│   │       └── A1_II_Φ10/
│   │           ├── index.html
│   │           ├── deepseek_html_20260705_d1ca99.html     # 原始归档
│   │           └── deepseek_html_20261006_d1ca99_Fix.html # 文件名安全渲染修复
│   ├── dircleaner/                  # 项目：自动清空指定目录工具
│   │   ├── index.html
│   │   └── code/
│   │       ├── index.html
│   │       └── A1_II_Φ8/
│   │           ├── index.html
│   │           └── deepseek_html_20261005_ada08c.html
│   └── writer/                      # 项目：小说编辑器
│       ├── index.html               # 项目落地页（打开入口 + 数据安全提示）
│       └── code/
│           ├── index.html           # 代码 / 分支索引
│           ├── A1_I_Φ2/             # 当前版本（左侧单列四页签）
│           │   ├── index.html
│           │   └── deepseek_A1_I_Φ2_CN.html
│           └── A1_I_Φ1/             # 首版（历史参照）
│               ├── index.html
│               └── deepseek_A1_I_Φ1_CN.html
└── .claude/skills/devkit-spec/      # Claude Code 技能（版本与协作规范 + 版本相关模板）
```

> 只有 `projects/<项目>/` 下的内容是项目产物。仓库根的三份文档、`index.html`、`404.html`、`docs/`、`.claude/` 以及 `.github/` 都是**仓库级**的，不属于任何一个项目的版本架构、不参与任何项目的版本号体系。

### 多项目结构

本仓库按 `projects/<项目名>/` 组织，每个项目独占一个目录：

- 每个项目自带一个 `index.html` 作为该项目落地页；项目内部的目录结构与版本号规则**由该项目自定**，仓库不为它们设统一规范。
- 仓库根 `index.html` 是**项目选择台**，只负责列出全部项目入口。
- `docs/`（协作约定）与 `.github/`（自动化）是**跨项目通用**的；其中 `version_guard.py`、`size_guard.py`、`smoke_test.py`、`auto_release.py` 等脚本目前**只作用于 DevKit**，路径常量写死指向 `projects/devkit/code/`。新增项目若要复用这些检查，需相应改造。
- 当前托管 `devkit`、`submerge-pro`、`dircleaner` 与 `writer` 四个项目；新增项目放入 `projects/<名称>/`，并更新根目录项目选择台和 `projects/index.html`。

### Pages 部署说明

站点入口在仓库**根目录**的 `index.html`，它是一个**项目选择台**；进入某个项目后才是该项目自己的版本选择台。站点可逐层浏览：

| 路径 | 内容 |
|------|------|
| `/` | 项目选择台：列出本仓库托管的全部项目 |
| `/projects/` | 项目目录索引 |
| `/projects/devkit/` | DevKit 项目落地页：九款皮肤直达 + 下载直达 + 分支卡片 |
| `/projects/devkit/code/` | DevKit 分支目录（Φ9 / Φ8 / Φ7 / Φ5 / Φ4） |
| `/projects/devkit/code/A1_V_Φ9/` | 当前主干的版本列表（九套皮肤） |
| `/projects/devkit/code/A1_V_Φ8/` | 上一代主干的版本列表（九套皮肤，Fix_Fix，与 Φ9 并行可选） |
| `/projects/devkit/code/A1_V_Φ8_fix-archive/` | Φ8 的 Fix 层历史归档（九款，追溯保留） |
| `/projects/devkit/code/A1_V_Φ7/` | 更早的历史主干版本列表（四套皮肤） |
| `/projects/devkit/code/A1_V_Φ5/` | 早期主干（两个版本，历史参照） |
| `/projects/devkit/code/A1_V_Φ4/` | 早期主干（一个版本，历史参照） |
| `/projects/submerge-pro/` | SubMerge Pro 项目页 |
| `/projects/submerge-pro/code/` | SubMerge Pro 代码分支索引 |
| `/projects/submerge-pro/code/A1_II_Φ10/` | 原始归档与 A1_II_Φ10_Fix 安全修订版 |
| `/projects/dircleaner/` | DirCleaner 项目页 |
| `/projects/dircleaner/code/` | DirCleaner 代码分支索引 |
| `/projects/dircleaner/code/A1_II_Φ8/` | A1_II_Φ8 应用文件 |
| `/projects/writer/` | Writer 小说编辑器项目页 |
| `/projects/writer/code/` | Writer 代码分支索引 |
| `/projects/writer/code/A1_I_Φ2/` | A1_I_Φ2 应用文件（当前版本） |
| `/projects/writer/code/A1_I_Φ1/` | A1_I_Φ1 应用文件（历史参照） |

Pages 之外还有一个**下载入口**：仓库的 Releases 页（`/releases`）由 `.github/workflows/release-on-main.yml` 自动维护——每次 `main` 更新就按主干打一个包，附上该代全部交付物。想拿文件下载走这里最省事，想在线阅读走 Pages。

因此 GitHub Pages 的发布目录必须为 **`/ (root)`**：

> Settings → Pages → Deploy from a branch → Branch: `main` → 目录选 **`/ (root)`** → Save

**不要**把发布目录设为 `/docs`。GitHub Pages 在发布目录为 `/docs` 时，**只会发布 `docs/` 目录内的文件**：根目录的 `index.html` 与整个 `projects/` 都不会上线，站点直接 404。

> 补充一：GitHub Pages **不会自动生成目录列表**。访问一个没有 `index.html` 的目录一律 404，所以 `/projects/`、`/projects/devkit/`、`/projects/devkit/code/` 与各主干目录下都放了显式的 `index.html` 作为索引。

> 补充二：**旧链接的兜底**。2026-10-03 引入项目层之前，DevKit 直接放在仓库根的 `code/` 下；迁移后这些地址失效。根目录的 `404.html` 会把 `/devkit/code/**` 重定向到 `/devkit/projects/devkit/code/**`，任意深度（含单个文件的深链）一次覆盖。若日后仓库改名，需同步修改该文件里的 `BASE` 常量。

## 许可证

AI 开发快捷工具箱 Copyright (C) 2026-至今 北冥的鱼, DeepSeek

本程序是自由软件，基于 GPLv3 发布，无任何担保。您应该已收到一份 GNU 通用公共许可证的副本。
