//! DirCleaner 内核版（Rust）
//!
//! 版本：A1_II_Φ8_Rust_CN
//! 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//!
//! 只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。
//! 不含图形界面——浏览器版靠 showDirectoryPicker 选目录，这里靠命令行参数。
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

/// 与浏览器版一致的受保护目录名单。
const CRITICAL_DIR_NAMES: &[&str] = &[
    "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
    "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
    "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
];

#[derive(Default)]
struct Stats {
    deleted_files: usize,
    deleted_dirs: usize,
    total_bytes: u64,
    errors: Vec<String>,
}

fn format_bytes(bytes: u64) -> String {
    if bytes == 0 {
        return "0 B".to_string();
    }
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut value = bytes as f64;
    let mut i = 0;
    while value >= 1024.0 && i < UNITS.len() - 1 {
        value /= 1024.0;
        i += 1;
    }
    if i == 0 {
        format!("{:.0} {}", value, UNITS[i])
    } else {
        format!("{:.2} {}", value, UNITS[i])
    }
}

fn is_critical(name: &str) -> bool {
    CRITICAL_DIR_NAMES.iter().any(|n| *n == name)
}

/// 与浏览器版 containsExecutables 等价：递归检查是否含 .exe / .dll。
fn contains_executables(dir: &Path, depth: usize, counter: &mut usize) -> bool {
    if depth > 10 || *counter >= MAX_SCAN_FOR_EXE {
        return false;
    }
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return false,
    };
    for entry in entries.flatten() {
        if *counter >= MAX_SCAN_FOR_EXE {
            break;
        }
        let path = entry.path();
        match entry.file_type() {
            Ok(ft) if ft.is_file() => {
                *counter += 1;
                let name = entry.file_name().to_string_lossy().to_lowercase();
                if name.ends_with(".exe") || name.ends_with(".dll") {
                    return true;
                }
            }
            Ok(ft) if ft.is_dir() => {
                if contains_executables(&path, depth + 1, counter) {
                    return true;
                }
            }
            _ => {}
        }
    }
    false
}

/// 递归清空。行为与浏览器版保持一致：
/// · 白名单标记模式下保留 .dircleaner_whitelist 文件
/// · 达到深度 / 文件数上限时中止并报错
fn clear_directory(
    dir: &Path,
    depth: usize,
    file_count: &mut usize,
    keep_marker: bool,
    dry_run: bool,
    stats: &mut Stats,
) -> Result<(), String> {
    if depth > MAX_RECURSION_DEPTH {
        return Err(format!("已达到最大目录深度限制 ({})", MAX_RECURSION_DEPTH));
    }
    let entries = fs::read_dir(dir).map_err(|e| format!("无法读取 {}: {}", dir.display(), e))?;

    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        let ft = match entry.file_type() {
            Ok(t) => t,
            Err(e) => {
                stats.errors.push(format!("无法读取 {}: {}", path.display(), e));
                continue;
            }
        };

        if ft.is_file() {
            if *file_count >= MAX_FILE_COUNT {
                return Err(format!("已达到最大文件数限制 ({})", MAX_FILE_COUNT));
            }
            if keep_marker && name == WHITELIST_MARKER_FILENAME {
                println!("跳过白名单标记文件: {}", name);
                continue;
            }
            let size = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
            let result = if dry_run {
                Ok(())
            } else {
                fs::remove_file(&path)
            };
            match result {
                Ok(()) => {
                    stats.deleted_files += 1;
                    stats.total_bytes += size;
                    *file_count += 1;
                    println!("{}: {} ({})", if dry_run { "[dry-run] 将删除文件" } else { "已删除文件" }, name, format_bytes(size));
                }
                Err(e) => {
                    let msg = format!("无法删除 {}: {}", name, e);
                    stats.errors.push(msg.clone());
                    eprintln!("{}", msg);
                }
            }
        } else if ft.is_dir() {
            clear_directory(&path, depth + 1, file_count, keep_marker, dry_run, stats)?;
            let result = if dry_run {
                Ok(())
            } else {
                fs::remove_dir(&path)
            };
            match result {
                Ok(()) => {
                    stats.deleted_dirs += 1;
                    println!("{}: {}", if dry_run { "[dry-run] 将删除目录" } else { "已删除目录" }, name);
                }
                Err(e) => {
                    let msg = format!("无法删除目录 {}: {}", name, e);
                    stats.errors.push(msg.clone());
                    eprintln!("{}", msg);
                }
            }
        }
    }
    Ok(())
}

fn usage() {
    println!("DirCleaner 内核版（Rust）");
    println!("用法: dircleaner <目录> [选项]");
    println!();
    println!("选项:");
    println!("  --dry-run            只列出将删除的内容，不实际删除");
    println!("  --whitelist          该目录在白名单中（保留标记文件，跳过名称确认）");
    println!("  --confirm <名称>     确认待清空目录的名称（非白名单目录必须提供且一致）");
    println!("  -h, --help           显示本帮助");
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() || args.iter().any(|a| a == "-h" || a == "--help") {
        usage();
        return if args.is_empty() { ExitCode::FAILURE } else { ExitCode::SUCCESS };
    }

    let mut target: Option<PathBuf> = None;
    let mut dry_run = false;
    let mut in_whitelist = false;
    let mut confirm_name: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--dry-run" => dry_run = true,
            "--whitelist" => in_whitelist = true,
            "--confirm" => {
                i += 1;
                if i < args.len() {
                    confirm_name = Some(args[i].clone());
                } else {
                    eprintln!("错误：--confirm 需要一个参数");
                    return ExitCode::FAILURE;
                }
            }
            other if !other.starts_with("--") && target.is_none() => {
                target = Some(PathBuf::from(other));
            }
            other => {
                eprintln!("错误：无法识别的参数 {}", other);
                return ExitCode::FAILURE;
            }
        }
        i += 1;
    }

    let target = match target {
        Some(t) => t,
        None => {
            eprintln!("错误：未指定目录");
            return ExitCode::FAILURE;
        }
    };

    if !target.is_dir() {
        eprintln!("错误：{} 不是目录", target.display());
        return ExitCode::FAILURE;
    }

    let dir_name = target
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();

    // 关键目录防护（与浏览器版一致）
    if is_critical(&dir_name) {
        eprintln!("错误：{} 是受保护的关键目录，禁止清空", dir_name);
        return ExitCode::FAILURE;
    }

    // 非白名单目录必须显式确认名称
    if !in_whitelist {
        match &confirm_name {
            Some(c) if c == &dir_name => {}
            Some(c) => {
                eprintln!("错误：确认名称 \"{}\" 与目录名 \"{}\" 不一致", c, dir_name);
                return ExitCode::FAILURE;
            }
            None => {
                eprintln!("错误：非白名单目录必须用 --confirm \"{}\" 确认", dir_name);
                return ExitCode::FAILURE;
            }
        }
    }

    // 可执行文件检测
    let mut counter = 0usize;
    let has_exe = contains_executables(&target, 0, &mut counter);
    if has_exe {
        println!("⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。");
        print!("确认继续？输入 yes: ");
        io::stdout().flush().ok();
        let mut ans = String::new();
        io::stdin().read_line(&mut ans).ok();
        if ans.trim() != "yes" {
            println!("已取消。");
            return ExitCode::FAILURE;
        }
    }

    println!("===== 开始清空操作 =====");
    println!("目标目录: {}", target.display());
    if dry_run {
        println!("模式: 试运行（不实际删除）");
    }

    let keep_marker = in_whitelist;
    let mut stats = Stats::default();
    let mut file_count = 0usize;

    match clear_directory(&target, 0, &mut file_count, keep_marker, dry_run, &mut stats) {
        Ok(()) => {
            println!("===== 清空完成 =====");
            println!("本次删除文件: {}", stats.deleted_files);
            println!("本次删除目录: {}", stats.deleted_dirs);
            println!("本次释放空间: {}", format_bytes(stats.total_bytes));
            if !stats.errors.is_empty() {
                println!("错误数: {}", stats.errors.len());
                for e in &stats.errors {
                    println!("  {}", e);
                }
                return ExitCode::FAILURE;
            }
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("操作中止: {}", e);
            println!("已删除文件: {}，目录: {}，释放空间: {}",
                     stats.deleted_files, stats.deleted_dirs, format_bytes(stats.total_bytes));
            ExitCode::FAILURE
        }
    }
}

#[allow(dead_code)]
fn _unused_hashset_hint() -> HashSet<String> {
    HashSet::new()
}
