//! DirCleaner 全功能版（Rust）
//!
//! 版本：A1_II_Φ8_Rust_CN
//! 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//!
//! 与内核版的区别：本版是**交互式终端界面**，模拟原 HTML 版的操作流：
//! 选目录 → 关键目录检查 → 白名单管理 → 可执行文件扫描与二次确认
//! → 输入目录名确认 → 执行清空 → 进度与统计。
//!
//! 不引入 GUI 依赖（避免 Tauri/egui 的构建复杂度），用终端交互替代。
//! 这是「全功能」的一种实现取舍：功能完整、可替代原产品，但不是图形界面。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use std::collections::HashSet;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const MAX_RECURSION_DEPTH: usize = 20;
const MAX_FILE_COUNT: usize = 10_000;
const MAX_SCAN_FOR_EXE: usize = 2_000;
const WHITELIST_MARKER_FILENAME: &str = ".dircleaner_whitelist";

const CRITICAL_DIR_NAMES: &[&str] = &[
    "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
    "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
    "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
];

#[derive(Default, Clone)]
struct Stats {
    deleted_files: usize,
    deleted_dirs: usize,
    total_bytes: u64,
    errors: Vec<String>,
}

/// 会话级累计统计（对应 HTML 版的 totalStats）
#[derive(Default)]
struct TotalStats {
    files: usize,
    dirs: usize,
    bytes: u64,
    errors: usize,
}

fn format_bytes(bytes: u64) -> String {
    if bytes == 0 { return "0 B".to_string(); }
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut v = bytes as f64;
    let mut i = 0;
    while v >= 1024.0 && i < UNITS.len() - 1 { v /= 1024.0; i += 1; }
    if i == 0 { format!("{:.0} {}", v, UNITS[i]) } else { format!("{:.2} {}", v, UNITS[i]) }
}

fn is_critical(name: &str) -> bool { CRITICAL_DIR_NAMES.iter().any(|n| *n == name) }

fn prompt(msg: &str) -> String {
    print!("{}", msg);
    io::stdout().flush().ok();
    let mut s = String::new();
    io::stdin().read_line(&mut s).ok();
    s.trim().to_string()
}

fn contains_executables(dir: &Path, depth: usize, counter: &mut usize) -> bool {
    if depth > 10 || *counter >= MAX_SCAN_FOR_EXE { return false; }
    let entries = match fs::read_dir(dir) { Ok(e) => e, Err(_) => return false };
    for entry in entries.flatten() {
        if *counter >= MAX_SCAN_FOR_EXE { break; }
        let path = entry.path();
        if let Ok(ft) = entry.file_type() {
            if ft.is_dir() {
                if contains_executables(&path, depth + 1, counter) { return true; }
            } else if ft.is_file() {
                *counter += 1;
                let n = entry.file_name().to_string_lossy().to_lowercase();
                if n.ends_with(".exe") || n.ends_with(".dll") { return true; }
            }
        }
    }
    false
}

/// 白名单：marker 模式下目录内的 .dircleaner_whitelist 即为凭证
fn is_whitelisted(dir: &Path) -> bool {
    dir.join(WHITELIST_MARKER_FILENAME).is_file()
}

fn add_to_whitelist(dir: &Path) -> Result<(), String> {
    let marker = dir.join(WHITELIST_MARKER_FILENAME);
    fs::write(&marker, "DirCleaner Whitelist Marker")
        .map_err(|e| format!("创建标记文件失败：{}", e))?;
    Ok(())
}

fn remove_from_whitelist(dir: &Path) -> Result<(), String> {
    let marker = dir.join(WHITELIST_MARKER_FILENAME);
    if !marker.exists() { return Ok(()); }
    fs::remove_file(&marker).map_err(|e| format!("删除标记文件失败：{}", e))
}

fn scan_summary(dir: &Path) -> (usize, usize, u64) {
    let mut files = 0; let mut dirs = 0; let mut bytes = 0u64;
    if let Ok(entries) = fs::read_dir(dir) {
        for e in entries.flatten() {
            if let Ok(ft) = e.file_type() {
                if ft.is_dir() {
                    dirs += 1;
                    let (f, d, b) = scan_summary(&e.path());
                    files += f; dirs += d; bytes += b;
                } else {
                    files += 1;
                    bytes += fs::metadata(e.path()).map(|m| m.len()).unwrap_or(0);
                }
            }
        }
    }
    (files, dirs, bytes)
}

fn clear_directory(dir: &Path, depth: usize, file_count: &mut usize,
                   keep_marker: bool, dry_run: bool, stats: &mut Stats) -> Result<(), String> {
    if depth > MAX_RECURSION_DEPTH {
        return Err(format!("已达到最大目录深度限制 ({})", MAX_RECURSION_DEPTH));
    }
    let entries = fs::read_dir(dir).map_err(|e| format!("无法读取 {}: {}", dir.display(), e))?;
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        let ft = match entry.file_type() {
            Ok(t) => t,
            Err(e) => { stats.errors.push(format!("无法读取 {}: {}", path.display(), e)); continue; }
        };
        if ft.is_dir() {
            clear_directory(&path, depth + 1, file_count, keep_marker, dry_run, stats)?;
            let r = if dry_run { Ok(()) } else { fs::remove_dir(&path) };
            match r {
                Ok(()) => {
                    stats.deleted_dirs += 1;
                    println!("  {} {}", if dry_run { "[试运行] 目录" } else { "✓ 目录" }, name);
                }
                Err(e) => {
                    let msg = format!("无法删除目录 {}: {}", name, e);
                    stats.errors.push(msg.clone());
                    println!("  ✗ {}", msg);
                }
            }
            continue;
        }
        if *file_count >= MAX_FILE_COUNT {
            return Err(format!("已达到最大文件数限制 ({})", MAX_FILE_COUNT));
        }
        if keep_marker && name == WHITELIST_MARKER_FILENAME {
            println!("  - 跳过白名单标记文件: {}", name);
            continue;
        }
        let size = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
        let r = if dry_run { Ok(()) } else { fs::remove_file(&path) };
        match r {
            Ok(()) => {
                stats.deleted_files += 1;
                stats.total_bytes += size;
                *file_count += 1;
                if stats.deleted_files % 20 == 0 || stats.deleted_files < 5 {
                    println!("  {} {} ({})", if dry_run { "[试运行] 文件" } else { "✓ 文件" }, name, format_bytes(size));
                }
            }
            Err(e) => {
                let msg = format!("无法删除 {}: {}", name, e);
                stats.errors.push(msg.clone());
                println!("  ✗ {}", msg);
            }
        }
    }
    Ok(())
}

fn print_banner() {
    println!();
    println!("╔══════════════════════════════════════════════╗");
    println!("║        DirCleaner 全功能版（Rust）           ║");
    println!("║        版本 A1_II_Φ8_Rust_CN                 ║");
    println!("╚══════════════════════════════════════════════╝");
    println!();
}

fn main() -> ExitCode {
    print_banner();

    let mut total = TotalStats::default();

    loop {
        // 1. 选择目录
        println!("【第 1 步】选择目录");
        let input = prompt("请输入要清空的目录路径（直接回车退出）：");
        if input.is_empty() {
            println!("已退出。");
            break;
        }
        let target = PathBuf::from(&input);
        if !target.is_dir() {
            println!("✗ 不是有效目录：{}\n", input);
            continue;
        }
        let dir_name = target.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();

        // 2. 关键目录检查
        println!("\n【第 2 步】安全检查");
        if is_critical(&dir_name) {
            println!("✗ {} 是受保护的关键目录，禁止清空。\n", dir_name);
            continue;
        }
        println!("✓ 不是受保护的关键目录");

        // 3. 白名单
        let whitelisted = is_whitelisted(&target);
        println!("\n【第 3 步】白名单");
        if whitelisted {
            println!("✓ 该目录已在白名单中（发现标记文件），跳过名称确认");
        } else {
            println!("  该目录不在白名单中。");
            let ans = prompt("  要加入白名单吗？(y/N)：");
            if ans.eq_ignore_ascii_case("y") {
                match add_to_whitelist(&target) {
                    Ok(()) => println!("✓ 已创建白名单标记文件"),
                    Err(e) => println!("✗ {}", e),
                }
            }
        }
        let whitelisted = is_whitelisted(&target);

        // 4. 扫描
        println!("\n【第 4 步】扫描内容");
        let (files, dirs, bytes) = scan_summary(&target);
        println!("  文件 {} 个 · 目录 {} 个 · 共 {}", files, dirs, format_bytes(bytes));
        let mut counter = 0;
        let has_exe = contains_executables(&target, 0, &mut counter);
        if has_exe {
            println!("  ⚠️  发现可执行文件（.exe / .dll）");
        }

        // 5. 确认
        println!("\n【第 5 步】确认");
        if !whitelisted {
            let typed = prompt(&format!("  请输入目录名 \"{}\" 以确认：", dir_name));
            if typed != dir_name {
                println!("✗ 名称不一致，已取消本次操作。\n");
                continue;
            }
        }
        if has_exe {
            println!("  ⚠️  该目录含可执行文件，删除后可能影响程序运行。");
            let ans = prompt("  确认继续？输入 yes：");
            if ans != "yes" {
                println!("  已取消。\n");
                continue;
            }
        }
        let mode = prompt("  执行模式：1=试运行（不删除） 2=实际删除 [默认 1]：");
        let dry_run = mode != "2";
        if !dry_run {
            let ans = prompt("  实际删除不可恢复，最后确认？(yes)：");
            if ans != "yes" {
                println!("  已取消。\n");
                continue;
            }
        }

        // 6. 执行
        println!("\n【第 6 步】执行{}", if dry_run { "（试运行）" } else { "" });
        println!("──────────────────────────────────────────────");
        let mut stats = Stats::default();
        let mut file_count = 0usize;
        let result = clear_directory(&target, 0, &mut file_count, whitelisted, dry_run, &mut stats);
        println!("──────────────────────────────────────────────");

        match result {
            Ok(()) => println!("✓ 完成"),
            Err(e) => println!("✗ 中止：{}", e),
        }
        println!("  本次：文件 {} · 目录 {} · 释放 {} · 错误 {}",
                 stats.deleted_files, stats.deleted_dirs,
                 format_bytes(stats.total_bytes), stats.errors.len());

        total.files += stats.deleted_files;
        total.dirs += stats.deleted_dirs;
        total.bytes += stats.total_bytes;
        total.errors += stats.errors.len();

        println!("\n  会话累计：文件 {} · 目录 {} · 释放 {} · 错误 {}",
                 total.files, total.dirs, format_bytes(total.bytes), total.errors);

        let more = prompt("\n继续处理其他目录？(y/N)：");
        if !more.eq_ignore_ascii_case("y") {
            break;
        }
        println!();
    }

    println!("\n再见。");
    ExitCode::SUCCESS
}
