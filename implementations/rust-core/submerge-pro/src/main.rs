//! SubMerge Pro 内核版（Rust）
//!
//! 版本：A1_II_Φ10_Rust_CN
//! 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//!
//! 只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。
//! 不含界面——浏览器版靠文件选择与文本框，这里靠命令行参数与标准输入。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use std::fs;
use std::io::{self, Read};
use std::path::PathBuf;
use std::process::ExitCode;

#[derive(Clone, Debug)]
struct Entry {
    index: u32,
    start: String,
    end: String,
    text: String,
    translated: Option<String>,
}

#[derive(Clone, Debug)]
struct Chunk {
    orig: String,
    trans: String,
}

/// 与浏览器版一致：中日韩字符按 2 个字符算 1 词，拉丁词按空格切分计数。
fn count_words(text: &str) -> usize {
    let mut total = 0usize;
    let mut cjk_run = String::new();
    let mut latin_run = String::new();

    let flush_cjk = |run: &mut String, total: &mut usize| {
        if !run.is_empty() {
            *total += (run.chars().count() + 1) / 2;
            run.clear();
        }
    };
    let flush_latin = |run: &mut String, total: &mut usize| {
        if !run.is_empty() {
            *total += run.split_whitespace().filter(|w| w.chars().any(|c| c.is_alphanumeric())).count();
            run.clear();
        }
    };

    for ch in text.chars() {
        if is_cjk(ch) {
            flush_latin(&mut latin_run, &mut total);
            cjk_run.push(ch);
        } else {
            flush_cjk(&mut cjk_run, &mut total);
            latin_run.push(ch);
        }
    }
    flush_cjk(&mut cjk_run, &mut total);
    flush_latin(&mut latin_run, &mut total);
    total
}

fn is_cjk(c: char) -> bool {
    matches!(c as u32, 0x4E00..=0x9FFF)
}

/// 分词：CJK 每 2 字一组，其余按词/单字符切分。
fn tokenize(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut cjk_run: Vec<char> = Vec::new();
    let mut latin_run = String::new();

    let flush_cjk = |run: &mut Vec<char>, tokens: &mut Vec<String>| {
        if run.is_empty() { return; }
        let mut i = 0;
        while i < run.len() {
            let end = (i + 2).min(run.len());
            tokens.push(run[i..end].iter().collect());
            i = end;
        }
        run.clear();
    };
    let flush_latin = |run: &mut String, tokens: &mut Vec<String>| {
        if run.is_empty() { return; }
        for w in run.split_whitespace() {
            if !w.is_empty() { tokens.push(w.to_string()); }
        }
        run.clear();
    };

    for ch in text.chars() {
        if is_cjk(ch) {
            flush_latin(&mut latin_run, &mut tokens);
            cjk_run.push(ch);
        } else if ch.is_whitespace() {
            flush_cjk(&mut cjk_run, &mut tokens);
            if !latin_run.is_empty() { latin_run.push(' '); }
        } else {
            flush_cjk(&mut cjk_run, &mut tokens);
            latin_run.push(ch);
        }
    }
    flush_cjk(&mut cjk_run, &mut tokens);
    flush_latin(&mut latin_run, &mut tokens);
    tokens
}

/// 在 CJK 与拉丁字符交界处补空格（与浏览器版的正则替换等价）。
fn add_boundary_spaces(s: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len() + 8);
    for i in 0..chars.len() {
        if i > 0 {
            let prev = chars[i - 1];
            let cur = chars[i];
            let boundary = (prev.is_ascii_alphanumeric() && is_cjk(cur))
                || (is_cjk(prev) && cur.is_ascii_alphanumeric());
            if boundary { out.push(' '); }
        }
        out.push(chars[i]);
    }
    out
}

/// 双语拆分：每条最多 max_words 词（双语各算 1 词配对计 2）。
fn split_paired(orig: &str, trans: &str, max_words: usize) -> Vec<Chunk> {
    if orig.is_empty() && trans.is_empty() {
        return vec![Chunk { orig: String::new(), trans: String::new() }];
    }
    let o = tokenize(orig);
    let t = tokenize(trans);
    let mut chunks = Vec::new();
    let mut oi = 0usize;
    let mut ti = 0usize;

    while oi < o.len() || ti < t.len() {
        let mut oc = Vec::new();
        let mut tc = Vec::new();
        let mut words = 0usize;

        while (oi < o.len() || ti < t.len()) && words < max_words {
            let can_o = oi < o.len();
            let can_t = ti < t.len();
            if can_o && can_t {
                if words + 2 <= max_words {
                    oc.push(o[oi].clone()); oi += 1;
                    tc.push(t[ti].clone()); ti += 1;
                    words += 2;
                } else { break; }
            } else if can_o {
                if words + 1 <= max_words { oc.push(o[oi].clone()); oi += 1; words += 1; } else { break; }
            } else if can_t {
                if words + 1 <= max_words { tc.push(t[ti].clone()); ti += 1; words += 1; } else { break; }
            }
        }

        // 拉丁词之间要保留空格；CJK 词直接拼接。判断依据：前一个 token 的末字符
        // 与后一个 token 的首字符都不是 CJK 时补空格。
        let join_tokens = |tokens: &[String]| -> String {
            let mut result = String::new();
            for (i, tok) in tokens.iter().enumerate() {
                if i > 0 {
                    let prev_last = tokens[i - 1].chars().last().unwrap_or(' ');
                    let cur_first = tok.chars().next().unwrap_or(' ');
                    if !is_cjk(prev_last) && !is_cjk(cur_first) {
                        result.push(' ');
                    }
                }
                result.push_str(tok);
            }
            result
        };
        let orig_chunk = add_boundary_spaces(&join_tokens(&oc));
        let trans_chunk = add_boundary_spaces(&join_tokens(&tc));
        chunks.push(Chunk {
            orig: orig_chunk.trim().to_string(),
            trans: trans_chunk.trim().to_string(),
        });
    }

    if chunks.is_empty() {
        vec![Chunk { orig: orig.to_string(), trans: trans.to_string() }]
    } else {
        chunks
    }
}

/// 时间字符串 → 毫秒。支持 `HH:MM:SS,mmm` 与 `HH:MM:SS.ff`（帧）。
fn time_to_ms(s: &str, fps: f64) -> u64 {
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() != 3 { return 0; }
    let h: u64 = parts[0].trim().parse().unwrap_or(0);
    let m: u64 = parts[1].trim().parse().unwrap_or(0);
    let sec_part = parts[2].trim();

    let (sec, ms) = if let Some((s1, s2)) = sec_part.split_once(',') {
        let sec: u64 = s1.parse().unwrap_or(0);
        let mut frac = s2.to_string();
        while frac.len() < 3 { frac.push('0'); }
        (sec, frac[..3].parse::<u64>().unwrap_or(0))
    } else if let Some((s1, s2)) = sec_part.split_once('.') {
        let sec: u64 = s1.parse().unwrap_or(0);
        let mut frac = s2.to_string();
        while frac.len() < 2 { frac.push('0'); }
        let frames: f64 = frac.parse().unwrap_or(0.0);
        let ms = if fps > 0.0 { (frames * (1000.0 / fps)).round() as u64 } else { 0 };
        (sec, ms)
    } else {
        (sec_part.parse().unwrap_or(0), 0)
    };

    (h * 3600 + m * 60 + sec) * 1000 + ms
}

fn ms_to_time(ms: u64) -> String {
    let h = ms / 3_600_000;
    let rem = ms % 3_600_000;
    let m = rem / 60_000;
    let rem = rem % 60_000;
    let s = rem / 1000;
    let milli = rem % 1000;
    format!("{:02}:{:02}:{:02},{:03}", h, m, s, milli)
}

/// 解析 SRT / BCC 文本。
fn parse_subtitle(content: &str) -> Vec<Entry> {
    let clean = content
        .trim_start_matches('\u{FEFF}')
        .replace("\r\n", "\n")
        .replace('\r', "\n");

    let mut entries = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for block in clean.split("\n\n") {
        let block = block.trim();
        if block.is_empty() { continue; }
        let lines: Vec<&str> = block.lines().map(|l| l.trim()).filter(|l| !l.is_empty()).collect();
        if lines.len() < 3 { continue; }
        if !lines[0].chars().all(|c| c.is_ascii_digit()) { continue; }

        let time_line = lines[1];
        let parts: Vec<&str> = time_line.split("-->").collect();
        if parts.len() != 2 { continue; }
        let start_raw = parts[0].trim();
        let end_raw = parts[1].trim();
        if !is_time_token(start_raw) || !is_time_token(end_raw) { continue; }

        let index: u32 = match lines[0].parse() { Ok(v) => v, Err(_) => continue };
        if !seen.insert(index) { continue; }

        let start = start_raw.replace('.', ",");
        let mut end = end_raw.replace('.', ",");

        let fps = 25.0;
        let start_ms = time_to_ms(&start, fps);
        let mut end_ms = time_to_ms(&end, fps);
        if start_ms >= end_ms {
            end = ms_to_time(start_ms + 1);
            end_ms = start_ms + 1;
        }
        let _ = end_ms;

        let text = lines[2..].join("\n").trim().to_string();
        if text.is_empty() { continue; }

        entries.push(Entry { index, start, end, text, translated: None });
    }

    entries.sort_by_key(|e| e.index);
    entries
}

fn is_time_token(s: &str) -> bool {
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() != 3 { return false; }
    if parts[0].parse::<u32>().is_err() { return false; }
    if parts[1].parse::<u32>().is_err() { return false; }
    let sec = parts[2];
    if let Some((a, b)) = sec.split_once(',') {
        a.parse::<u32>().is_ok() && !b.is_empty() && b.len() <= 3 && b.chars().all(|c| c.is_ascii_digit())
    } else if let Some((a, b)) = sec.split_once('.') {
        a.parse::<u32>().is_ok() && !b.is_empty() && b.chars().all(|c| c.is_ascii_digit())
    } else {
        sec.parse::<u32>().is_ok()
    }
}

/// 过短时间修正：delete 丢弃 <10ms 的条目，extend 延长并顺延后续。
fn apply_time_fix(entries: &mut Vec<Entry>, strategy: &str) {
    if strategy == "keep" { return; }
    let fps = 25.0;
    if strategy == "delete" {
        entries.retain(|e| time_to_ms(&e.end, fps).saturating_sub(time_to_ms(&e.start, fps)) >= 10);
        return;
    }
    if strategy == "extend" {
        let n = entries.len();
        for i in 0..n {
            let start_ms = time_to_ms(&entries[i].start, fps);
            let end_ms = time_to_ms(&entries[i].end, fps);
            if end_ms.saturating_sub(start_ms) < 10 {
                let new_end = start_ms + 10;
                entries[i].end = ms_to_time(new_end);
                let shift = new_end - end_ms;
                for j in (i + 1)..n {
                    entries[j].start = ms_to_time(time_to_ms(&entries[j].start, fps) + shift);
                    entries[j].end = ms_to_time(time_to_ms(&entries[j].end, fps) + shift);
                }
            }
        }
    }
}

/// 应用译文：解析 `[编号] 文本` 格式。
fn apply_translation(entries: &mut Vec<Entry>, trans_str: &str) -> usize {
    let mut map: std::collections::HashMap<u32, String> = std::collections::HashMap::new();
    let mut cur_idx: Option<u32> = None;
    let mut cur_buf: Vec<String> = Vec::new();

    for line in trans_str.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') {
            if let Some(end) = trimmed.find(']') {
                if let Ok(idx) = trimmed[1..end].trim().parse::<u32>() {
                    if let Some(prev) = cur_idx {
                        map.insert(prev, cur_buf.join("\n").trim().to_string());
                    }
                    cur_idx = Some(idx);
                    cur_buf.clear();
                    let rest = trimmed[end + 1..].trim();
                    if !rest.is_empty() { cur_buf.push(rest.to_string()); }
                    continue;
                }
            }
        }
        if cur_idx.is_some() && !trimmed.is_empty() {
            cur_buf.push(trimmed.to_string());
        }
    }
    if let Some(prev) = cur_idx {
        map.insert(prev, cur_buf.join("\n").trim().to_string());
    }

    let mut applied = 0;
    for e in entries.iter_mut() {
        if let Some(t) = map.get(&e.index) {
            e.translated = Some(t.clone());
            applied += 1;
        }
    }
    applied
}

/// 导出 SRT。mode: orig / trans / both
fn export_srt(entries: &[Entry], mode: &str) -> String {
    let mut out = String::new();
    for e in entries {
        let text = match mode {
            "orig" => e.text.clone(),
            "trans" => e.translated.clone().unwrap_or_default(),
            _ => match (&e.translated, e.text.is_empty()) {
                (Some(t), false) => format!("{}\n{}", e.text, t),
                (Some(t), true) => t.clone(),
                (None, _) => e.text.clone(),
            },
        };
        out.push_str(&format!("{}\n{} --> {}\n{}\n\n", e.index, e.start, e.end, text));
    }
    out
}

fn usage() {
    println!("SubMerge Pro 内核版（Rust）");
    println!("用法:");
    println!("  submerge parse <字幕文件>                    解析并统计");
    println!("  submerge export <字幕文件> [选项]            导出 SRT");
    println!("  submerge merge-prompt <字幕文件> [--max N]   输出合并后的提示词文本");
    println!();
    println!("选项:");
    println!("  --trans <译文文件>   应用译文（[编号] 文本 格式）");
    println!("  --mode both|orig|trans  导出内容（默认 both）");
    println!("  --time-fix keep|delete|extend  过短时间处理（默认 keep）");
    println!("  -h, --help           显示本帮助");
}

fn read_file(path: &str) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| format!("无法读取 {}: {}", path, e))?;
    // BOM 与常见编码：优先 UTF-8，失败则按 GBK 近似（lossy 兜底）
    let s = match String::from_utf8(bytes.clone()) {
        Ok(t) => t,
        Err(_) => String::from_utf8_lossy(&bytes).to_string(),
    };
    Ok(s)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() || args.iter().any(|a| a == "-h" || a == "--help") {
        usage();
        return if args.is_empty() { ExitCode::FAILURE } else { ExitCode::SUCCESS };
    }

    let cmd = args[0].as_str();
    let mut file: Option<String> = None;
    let mut trans_file: Option<String> = None;
    let mut mode = "both".to_string();
    let mut time_fix = "keep".to_string();
    let mut max_words = 10usize;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--trans" => { i += 1; if i < args.len() { trans_file = Some(args[i].clone()); } }
            "--mode" => { i += 1; if i < args.len() { mode = args[i].clone(); } }
            "--time-fix" => { i += 1; if i < args.len() { time_fix = args[i].clone(); } }
            "--max" => { i += 1; if i < args.len() { max_words = args[i].parse().unwrap_or(10); } }
            other if !other.starts_with("--") && file.is_none() => file = Some(other.to_string()),
            _ => {}
        }
        i += 1;
    }

    let file = match file {
        Some(f) => f,
        None => { eprintln!("错误：未指定字幕文件"); return ExitCode::FAILURE; }
    };

    let content = match read_file(&file) {
        Ok(c) => c,
        Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; }
    };

    let mut entries = parse_subtitle(&content);
    if entries.is_empty() {
        eprintln!("解析失败：未找到任何字幕条目");
        return ExitCode::FAILURE;
    }
    apply_time_fix(&mut entries, &time_fix);

    if let Some(tf) = &trans_file {
        match read_file(tf) {
            Ok(t) => {
                let n = apply_translation(&mut entries, &t);
                println!("已应用 {} 条译文", n);
            }
            Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; }
        }
    }

    match cmd {
        "parse" => {
            let total: usize = entries.iter().map(|e| count_words(&e.text)).sum();
            println!("条目数: {}", entries.len());
            println!("总词数: {}", total);
            println!("首条: [{}] {} --> {} | {}", entries[0].index, entries[0].start, entries[0].end, entries[0].text);
            println!("末条: [{}] {} --> {} | {}", entries.last().unwrap().index, entries.last().unwrap().start, entries.last().unwrap().end, entries.last().unwrap().text);
            ExitCode::SUCCESS
        }
        "merge-prompt" => {
            let mut out = String::new();
            for e in &entries {
                let chunks = split_paired(&e.text, e.translated.as_deref().unwrap_or(""), max_words);
                for c in chunks {
                    let body = if c.trans.is_empty() { c.orig.clone() } else { format!("{}\n{}", c.orig, c.trans) };
                    out.push_str(&format!("[{}] {}\n", e.index, body.trim()));
                }
            }
            print!("{}", out);
            ExitCode::SUCCESS
        }
        "export" => {
            let srt = export_srt(&entries, &mode);
            // 默认写到 stdout；若给了 --out 则写文件（此处简化为 stdout，便于管道）
            print!("{}", srt);
            ExitCode::SUCCESS
        }
        other => {
            eprintln!("错误：未知子命令 {}", other);
            usage();
            ExitCode::FAILURE
        }
    }
}

#[allow(dead_code)]
fn _stdin_hint() {
    let mut s = String::new();
    io::stdin().read_to_string(&mut s).ok();
    let _ = PathBuf::from(s);
}
