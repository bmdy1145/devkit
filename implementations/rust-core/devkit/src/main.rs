//! DevKit 内核版（Rust）
//!
//! 版本：A1_V_Φ9_Fix_Rust_CN
//! 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//!
//! 只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
//! 提示词模板拼接。不含 UI——浏览器版是整套 DOM 工作台，这里只提供
//! 可在脚本与 CI 中复用的逻辑层。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use serde_json::Value;
use std::process::ExitCode;

const CURRENT_VERSION: &str = "A1_V_Φ9_Fix_Rust_CN";

/// 与浏览器版一致的版本结构解析：分支代号 + 结构段 + 语言后缀。
fn parse_version(v: &str) -> Option<(String, String, Option<String>)> {
    let trimmed = v.trim();
    if trimmed.is_empty() || trimmed.len() > 100 {
        return None;
    }
    let (core, suffix) = if trimmed.ends_with("_CN") {
        (&trimmed[..trimmed.len() - 3], Some("CN".to_string()))
    } else if trimmed.ends_with("_GLOBAL") {
        (&trimmed[..trimmed.len() - 7], Some("GLOBAL".to_string()))
    } else {
        (trimmed, None)
    };

    let mut parts = core.split('_');
    let branch = parts.next()?;
    if branch.is_empty() || !branch.starts_with('A') { return None; }
    if !branch[1..].chars().all(|c| c.is_ascii_digit()) && branch.len() > 1 { return None; }
    let structure = parts.collect::<Vec<_>>().join("_");
    Some((branch.to_string(), structure, suffix))
}

fn is_compatible(v: &str) -> bool {
    match parse_version(v) {
        None => false,
        Some((branch, structure, _)) => {
            // 废弃分支 A2 一律拒收（与浏览器版一致）
            if branch.starts_with("A2") { return false; }
            if structure.split('_').any(|s| s == "A2") { return false; }
            true
        }
    }
}

#[derive(Clone)]
struct Spec {
    key: &'static str,
    kind: &'static str,
    default_bool: bool,
    default_str: &'static str,
    values: &'static [&'static str],
    min: Option<i64>,
    max: Option<i64>,
}

const SPECS: &[Spec] = &[
    Spec { key: "performanceMode", kind: "boolean", default_bool: false, default_str: "", values: &[], min: None, max: None },
    Spec { key: "shortcutsEnabled", kind: "boolean", default_bool: true, default_str: "", values: &[], min: None, max: None },
    Spec { key: "hideBtnText", kind: "boolean", default_bool: false, default_str: "", values: &[], min: None, max: None },
    Spec { key: "promptActionsAlways", kind: "boolean", default_bool: true, default_str: "", values: &[], min: None, max: None },
    Spec { key: "specPromptEnabled", kind: "boolean", default_bool: true, default_str: "", values: &[], min: None, max: None },
    Spec { key: "inspirationSyncEnabled", kind: "boolean", default_bool: true, default_str: "", values: &[], min: None, max: None },
    Spec { key: "themePref", kind: "enum", default_bool: false, default_str: "light", values: &["dark", "light", "auto"], min: None, max: None },
];

fn normalize_settings(src: &Value) -> serde_json::Map<String, Value> {
    let mut out = serde_json::Map::new();
    let empty = serde_json::Map::new();
    let obj = src.as_object().unwrap_or(&empty);

    for spec in SPECS {
        let val = obj.get(spec.key);
        let v = match spec.kind {
            "boolean" => {
                let b = val.and_then(|x| x.as_bool()).unwrap_or(spec.default_bool);
                Value::Bool(b)
            }
            "enum" => {
                let s = val.and_then(|x| x.as_str()).unwrap_or(spec.default_str);
                if spec.values.contains(&s) {
                    Value::String(s.to_string())
                } else {
                    Value::String(spec.default_str.to_string())
                }
            }
            _ => continue,
        };
        out.insert(spec.key.to_string(), v);
    }
    out
}

enum CheckIssue {
    TooLarge(usize),
    NotObject,
    MissingId(usize),
    MissingName(usize),
    TooManyTabs(usize),
    BadTab(usize, usize),
}

fn validate_import(data: &Value) -> Result<usize, CheckIssue> {
    let projects = match data.get("projects").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => {
            if data.get("project").is_some() {
                return Ok(1);
            }
            return Err(CheckIssue::NotObject);
        }
    };
    if projects.len() > 20 {
        return Err(CheckIssue::TooLarge(projects.len()));
    }
    for (i, p) in projects.iter().enumerate() {
        let obj = p.as_object().ok_or(CheckIssue::NotObject)?;
        let id_ok = obj.get("id").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
        if !id_ok { return Err(CheckIssue::MissingId(i)); }
        let name_ok = obj.get("name").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
        if !name_ok { return Err(CheckIssue::MissingName(i)); }
        let tabs = obj.get("tabs").and_then(|v| v.as_array()).ok_or(CheckIssue::NotObject)?;
        if tabs.len() > 50 { return Err(CheckIssue::TooManyTabs(i)); }
        for (j, t) in tabs.iter().enumerate() {
            let to = t.as_object().ok_or(CheckIssue::BadTab(i, j))?;
            let tid = to.get("id").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
            let tname = to.get("name").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false);
            if !tid || !tname { return Err(CheckIssue::BadTab(i, j)); }
        }
    }
    Ok(projects.len())
}

fn compose(template: &str, inspiration: &str, code: &str) -> String {
    template
        .replace("{inspiration}", inspiration)
        .replace("{code}", code)
}

fn usage() {
    println!("DevKit 内核版（Rust）");
    println!("用法: devkit <子命令> [参数]");
    println!();
    println!("子命令:");
    println!("  version                         打印当前版本号");
    println!("  parse-version <版本号>          解析版本号结构");
    println!("  check-version <版本号>          判断是否兼容");
    println!("  validate-config <配置文件>      校验配置导入");
    println!("  normalize <设置JSON>            规范化设置字段");
    println!("  compose <模板文件> <灵感> [代码文件]  拼接提示词");
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        usage();
        return ExitCode::FAILURE;
    }

    match args[0].as_str() {
        "version" => {
            println!("{}", CURRENT_VERSION);
            ExitCode::SUCCESS
        }
        "parse-version" => {
            let Some(v) = args.get(1) else { eprintln!("缺少版本号"); return ExitCode::FAILURE; };
            match parse_version(v) {
                Some((branch, structure, suffix)) => {
                    println!("分支: {}", branch);
                    println!("结构段: {}", if structure.is_empty() { "（无）" } else { &structure });
                    println!("语言后缀: {}", suffix.unwrap_or_else(|| "（无）".to_string()));
                    ExitCode::SUCCESS
                }
                None => { eprintln!("版本号不合规"); ExitCode::FAILURE }
            }
        }
        "check-version" => {
            let Some(v) = args.get(1) else { eprintln!("缺少版本号"); return ExitCode::FAILURE; };
            if is_compatible(v) {
                println!("兼容");
                ExitCode::SUCCESS
            } else {
                println!("不兼容");
                ExitCode::FAILURE
            }
        }
        "validate-config" => {
            let Some(path) = args.get(1) else { eprintln!("缺少配置文件路径"); return ExitCode::FAILURE; };
            let raw = match std::fs::read_to_string(path) {
                Ok(r) => r,
                Err(e) => { eprintln!("读取失败: {}", e); return ExitCode::FAILURE; }
            };
            let data: Value = match serde_json::from_str(&raw) {
                Ok(d) => d,
                Err(e) => { eprintln!("JSON 解析失败: {}", e); return ExitCode::FAILURE; }
            };
            if let Some(ver) = data.get("version").and_then(|v| v.as_str()) {
                if !is_compatible(ver) {
                    eprintln!("配置文件版本不兼容: {}", ver);
                    return ExitCode::FAILURE;
                }
            }
            match validate_import(&data) {
                Ok(n) => { println!("校验通过，项目数: {}", n); ExitCode::SUCCESS }
                Err(CheckIssue::TooLarge(n)) => { eprintln!("项目数 {} 超过上限 20", n); ExitCode::FAILURE }
                Err(CheckIssue::NotObject) => { eprintln!("格式错误：不是有效对象"); ExitCode::FAILURE }
                Err(CheckIssue::MissingId(i)) => { eprintln!("第 {} 个项目缺少 id", i + 1); ExitCode::FAILURE }
                Err(CheckIssue::MissingName(i)) => { eprintln!("第 {} 个项目缺少 name", i + 1); ExitCode::FAILURE }
                Err(CheckIssue::TooManyTabs(i)) => { eprintln!("第 {} 个项目页签超过 50", i + 1); ExitCode::FAILURE }
                Err(CheckIssue::BadTab(i, j)) => { eprintln!("第 {} 个项目第 {} 个页签字段不完整", i + 1, j + 1); ExitCode::FAILURE }
            }
        }
        "normalize" => {
            let Some(raw) = args.get(1) else { eprintln!("缺少设置 JSON"); return ExitCode::FAILURE; };
            let v: Value = match serde_json::from_str(raw) {
                Ok(x) => x,
                Err(e) => { eprintln!("JSON 解析失败: {}", e); return ExitCode::FAILURE; }
            };
            let out = normalize_settings(&v);
            println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
            ExitCode::SUCCESS
        }
        "compose" => {
            let (Some(tpl_path), Some(insp)) = (args.get(1), args.get(2)) else {
                eprintln!("用法: compose <模板文件> <灵感> [代码文件]");
                return ExitCode::FAILURE;
            };
            let tpl = match std::fs::read_to_string(tpl_path) {
                Ok(t) => t,
                Err(e) => { eprintln!("读取模板失败: {}", e); return ExitCode::FAILURE; }
            };
            let code = match args.get(3) {
                Some(p) => std::fs::read_to_string(p).unwrap_or_default(),
                None => "（无代码）".to_string(),
            };
            print!("{}", compose(&tpl, insp, &code));
            ExitCode::SUCCESS
        }
        other => { eprintln!("未知子命令: {}", other); usage(); ExitCode::FAILURE }
    }
}
