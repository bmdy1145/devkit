# 多语言实现规范

本仓库的主交付物是纯 HTML 单文件应用（`projects/<项目>/code/`）。本目录存放
**同一功能在其他编程语言下的实现**，用于学习与技术对比。

> **维护边界**：多语言实现交付后**只做安全修复，不跟进功能迭代**。功能演进
> 一律只发生在 `projects/` 下的 HTML 版。不要把新功能同步到这里。

---

## 目录结构

```
implementations/
├── <语言>-core/<项目>/      # 内核版：纯逻辑，CLI 输入输出
└── <语言>-full/<项目>/      # 全功能版：含图形界面，可替代原产品
```

- **语言**：`rust` / `go` / `python` / `typescript` / `csharp` / `cpp`
- **层次**：`core`（只做逻辑内核）/ `full`（完整功能重写）
- **项目**：`devkit` / `submerge-pro` / `dircleaner` / `writer`

两层用**目录**区分，**版本号相同**——这样 `version_guard.py` 无需改动。

---

## 版本号规则

在现有版本号最后一层追加语言名，语言变体后缀 `_CN` 保持在最末：

```
A1_V_Φ9_Fix_Rust_CN        # DevKit Φ9 的 Rust 实现（中文版）
A1_II_Φ8_Go_CN             # DirCleaner Φ8 的 Go 实现
A1_I_Φ3_Python_CN          # Writer Φ3 的 Python 实现
```

### 形态区分：靠文件扩展名

同一语言的 EXE 版与 Web 版**版本号相同**，靠扩展名区分：

| 形态 | 文件名 |
|---|---|
| 原生 EXE | `deepseek_A1_V_Φ9_Fix_Rust_CN.exe` |
| 浏览器版 | `deepseek_A1_V_Φ9_Fix_Rust_CN.html` |

### 皮肤变体：靠文件名后缀

DevKit 有 9 个皮肤，另有 1 个「九皮肤合一」版本：

| 变体 | 文件名 |
|---|---|
| 基准皮肤 | `deepseek_A1_V_Φ9_Fix_Rust_CN.html` |
| Clean 皮肤 | `deepseek_A1_V_Φ9_Clean_Fix_Rust_CN.html` |
| 九皮肤合并版 | `deepseek_A1_V_Φ9_Fix_Rust_CN_All.html` |

合并版把 9 套 CSS 用类名命名空间包起来，运行时切换 `<body>` 上的类，
与现有 `themePref` / `theme` 机制一致。体积约为单皮肤的 2.3 倍（约 525 KB）。

---

## 构建

每种语言在 `<语言>-core/` 与 `<语言>-full/` 根下各有一个构建脚本：

| 语言 | 构建脚本 | 产物 |
|---|---|---|
| Rust | `build.sh` | `target/release/*.exe` |
| Go | `build.sh` | `*.exe` |
| Python | `build.sh`（调 PyInstaller） | `dist/*.exe` |
| TypeScript | `build.sh`（调 Node SEA） | `*.exe` |
| C# | `build.sh`（调 dotnet publish） | `publish/*.exe` |
| C++ | `build.sh`（调 MinGW g++） | `*.exe` |

工具链不在系统 PATH，构建脚本内部自行定位（见 `toolchains.env`）。

---

## Release 附件命名

`.github/workflows/build-implementations.yml` 在 windows-latest 上构建全部产物，
合并进 `main` 后自动发布为 Release 附件。命名规则：

```
<项目>_<语言>_<层次>.exe
```

| 段 | 取值 | 说明 |
|---|---|---|
| 项目 | `dircleaner` / `submerge-pro` / `writer` / `devkit` | |
| 语言 | `cpp` / `csharp` / `go` / `python` / `rust` / `typescript` | |
| 层次 | `cli` / `gui` | `cli` = 源码目录的 `core`；`gui` = 源码目录的 `full` |

例：`submerge-pro_rust_gui.exe`、`dircleaner_cpp_cli.exe`。

- **用下划线分隔**：项目名 `submerge-pro` 自带连字符，再用连字符作分隔符会歧义。
- **对外叫 `cli` / `gui`**：`core` / `full` 是源码目录名，对使用者不如
  「命令行 / 图形界面」直观；`full` 层原本还额外带 `-gui` 后缀，信息重复。
- **项目名排在最前**：附件列表按文件名排序，这样同一项目的各语言实现相邻。

> 源码目录名与附件层次名不同（`core` ↔ `cli`、`full` ↔ `gui`），改命名时两处要一起看。

---

## 检查脚本

现有 `version_guard.py`、`size_guard.py`、`smoke_test.py`、`auto_release.py`
**均不扫描 `implementations/`**，理由：

- `version_guard` 只校验 HTML 交付物的版本号与结构块；
- `size_guard` 的阈值（380/520 KB）针对单文件 HTML，对 EXE 无意义；
- `smoke_test` 依赖无头浏览器，对原生程序无意义；
- `auto_release` 按项目发布 HTML 交付物，多语言实现不参与自动发布。

因此新增本目录**不会触发任何现有检查**，也不会产生 Release。
