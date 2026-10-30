//! SubMerge Pro 全功能版（Rust / egui）
//!
//! 版本：A1_II_Φ10_Rust_CN
//! 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//!
//! 图形界面版：加载字幕、条目预览、粘贴译文并应用、双语拆分预览、导出 SRT。
//! 逻辑部分与 core 版一致，界面用 egui。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use eframe::egui;
use std::fs;
use std::path::PathBuf;

#[derive(Clone, Default)]
struct Entry {
    index: u32,
    start: String,
    end: String,
    text: String,
    translated: String,
}

fn is_cjk(c: char) -> bool { matches!(c as u32, 0x4E00..=0x9FFF) }

fn tokenize(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut cjk: Vec<char> = Vec::new();
    let mut latin = String::new();

    fn flush_cjk(cjk: &mut Vec<char>, tokens: &mut Vec<String>) {
        let mut i = 0;
        while i < cjk.len() {
            let end = (i + 2).min(cjk.len());
            tokens.push(cjk[i..end].iter().collect());
            i = end;
        }
        cjk.clear();
    }
    fn flush_latin(latin: &mut String, tokens: &mut Vec<String>) {
        push_latin_tokens(latin, tokens);
        latin.clear();
    }

    for ch in text.chars() {
        if is_cjk(ch) { flush_latin(&mut latin, &mut tokens); cjk.push(ch); }
        else if ch.is_whitespace() {
            flush_cjk(&mut cjk, &mut tokens);
            if !latin.is_empty() { latin.push(' '); }
        } else {
            flush_cjk(&mut cjk, &mut tokens);
            latin.push(ch);
        }
    }
    flush_cjk(&mut cjk, &mut tokens);
    flush_latin(&mut latin, &mut tokens);
    tokens
}

fn is_ascii_alnum(c: char) -> bool { c.is_ascii_alphanumeric() }

/// 与 HTML 参考实现一致：拉丁段按 [A-Za-z0-9]+(?:'[A-Za-z]+)?|\S 切分。
/// 即 "world," 拆成 "world" 与 ","，而 "don't" 保持为一个 token。
fn push_latin_tokens(run: &str, tokens: &mut Vec<String>) {
    let chars: Vec<char> = run.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if is_ascii_alnum(c) {
            let mut j = i;
            while j < chars.len() && is_ascii_alnum(chars[j]) { j += 1; }
            // 允许词内一个撇号：don't → 仍是 1 个 token
            if j < chars.len() && chars[j] == '\'' {
                let a = j + 1;
                let mut b = a;
                while b < chars.len() && chars[b].is_ascii_alphabetic() { b += 1; }
                if b > a { j = b; }
            }
            tokens.push(chars[i..j].iter().collect());
            i = j;
        } else if c.is_whitespace() {
            i += 1;
        } else {
            tokens.push(c.to_string());
            i += 1;
        }
    }
}

fn join_tokens(tokens: &[String]) -> String {
    let mut out = String::new();
    for (i, tok) in tokens.iter().enumerate() {
        if i > 0 {
            let p = tokens[i - 1].chars().last().unwrap_or(' ');
            let c = tok.chars().next().unwrap_or(' ');
            if !is_cjk(p) && !is_cjk(c) { out.push(' '); }
        }
        out.push_str(tok);
    }
    out
}

fn add_boundary(s: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::new();
    for i in 0..chars.len() {
        if i > 0 {
            let p = chars[i - 1];
            let c = chars[i];
            if (is_ascii_alnum(p) && is_cjk(c)) || (is_cjk(p) && is_ascii_alnum(c)) {
                out.push(' ');
            }
        }
        out.push(chars[i]);
    }
    out
}

fn split_paired(orig: &str, trans: &str, max_words: usize) -> Vec<(String, String)> {
    let o = tokenize(orig);
    let t = tokenize(trans);
    let mut chunks = Vec::new();
    let (mut oi, mut ti) = (0usize, 0usize);
    while oi < o.len() || ti < t.len() {
        let (mut oc, mut tc) = (Vec::new(), Vec::new());
        let mut words = 0usize;
        while (oi < o.len() || ti < t.len()) && words < max_words {
            let (can_o, can_t) = (oi < o.len(), ti < t.len());
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
        chunks.push((add_boundary(&join_tokens(&oc)).trim().to_string(),
                     add_boundary(&join_tokens(&tc)).trim().to_string()));
    }
    if chunks.is_empty() { chunks.push((orig.to_string(), trans.to_string())); }
    chunks
}

fn time_to_ms(s: &str) -> i64 {
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() != 3 { return 0; }
    let h: i64 = parts[0].trim().parse().unwrap_or(0);
    let m: i64 = parts[1].trim().parse().unwrap_or(0);
    let sp = parts[2];
    let (sec, ms) = if let Some((a, b)) = sp.split_once(',') {
        let mut f = b.to_string();
        while f.len() < 3 { f.push('0'); }
        (a.parse::<i64>().unwrap_or(0), f[..3].parse::<i64>().unwrap_or(0))
    } else if let Some((a, b)) = sp.split_once('.') {
        let mut f = b.to_string();
        while f.len() < 2 { f.push('0'); }
        let frames: f64 = f[..2].parse().unwrap_or(0.0);
        (a.parse::<i64>().unwrap_or(0), (frames * 40.0).round() as i64)
    } else {
        (sp.parse().unwrap_or(0), 0)
    };
    (h * 3600 + m * 60 + sec) * 1000 + ms
}

fn ms_to_time(ms: i64) -> String {
    let h = ms / 3_600_000;
    let rem = ms % 3_600_000;
    let m = rem / 60_000;
    let rem = rem % 60_000;
    format!("{:02}:{:02}:{:02},{:03}", h, m, rem / 1000, rem % 1000)
}

fn parse_subtitle(content: &str) -> Vec<Entry> {
    let clean = content.trim_start_matches('\u{FEFF}').replace("\r\n", "\n").replace('\r', "\n");
    let mut entries = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for block in clean.split("\n\n") {
        let lines: Vec<&str> = block.lines().map(|l| l.trim()).filter(|l| !l.is_empty()).collect();
        if lines.len() < 3 || !lines[0].chars().all(|c| c.is_ascii_digit()) { continue; }
        let parts: Vec<&str> = lines[1].split("-->").collect();
        if parts.len() != 2 { continue; }
        let start_raw = parts[0].trim();
        let end_raw = parts[1].trim();
        if start_raw.split(':').count() != 3 || end_raw.split(':').count() != 3 { continue; }
        let index: u32 = match lines[0].parse() { Ok(v) => v, Err(_) => continue };
        if !seen.insert(index) { continue; }
        let start = start_raw.replace('.', ",");
        let mut end = end_raw.replace('.', ",");
        let sm = time_to_ms(&start);
        if sm >= time_to_ms(&end) { end = ms_to_time(sm + 1); }
        let text = lines[2..].join("\n").trim().to_string();
        if text.is_empty() { continue; }
        entries.push(Entry { index, start, end, text, translated: String::new() });
    }
    entries.sort_by_key(|e| e.index);
    entries
}

fn apply_translation(entries: &mut [Entry], trans: &str) -> usize {
    let mut map = std::collections::HashMap::new();
    let mut cur: Option<u32> = None;
    let mut buf: Vec<String> = Vec::new();
    let flush = |c: &Option<u32>, b: &Vec<String>, m: &mut std::collections::HashMap<u32, String>| {
        if let Some(i) = c { m.insert(*i, b.join("\n").trim().to_string()); }
    };
    for line in trans.lines() {
        let t = line.trim();
        if t.starts_with('[') {
            if let Some(end) = t.find(']') {
                if let Ok(idx) = t[1..end].trim().parse::<u32>() {
                    flush(&cur, &buf, &mut map);
                    cur = Some(idx);
                    buf.clear();
                    let rest = t[end + 1..].trim();
                    if !rest.is_empty() { buf.push(rest.to_string()); }
                    continue;
                }
            }
        }
        if cur.is_some() && !t.is_empty() { buf.push(t.to_string()); }
    }
    flush(&cur, &buf, &mut map);

    let mut applied = 0;
    for e in entries.iter_mut() {
        if let Some(v) = map.get(&e.index) { e.translated = v.clone(); applied += 1; }
    }
    applied
}

fn export_srt(entries: &[Entry], mode: usize) -> String {
    let mut out = String::new();
    for e in entries {
        let text = match mode {
            1 => e.text.clone(),
            2 => e.translated.clone(),
            _ => {
                if !e.translated.is_empty() && !e.text.is_empty() {
                    format!("{}\n{}", e.text, e.translated)
                } else if !e.translated.is_empty() { e.translated.clone() }
                else { e.text.clone() }
            }
        };
        out.push_str(&format!("{}\n{} --> {}\n{}\n\n", e.index, e.start, e.end, text));
    }
    out
}

struct App {
    entries: Vec<Entry>,
    filename: String,
    trans_input: String,
    lang: String,
    max_words: usize,
    mode: usize,
    output: String,
    status: String,
}

impl Default for App {
    fn default() -> Self {
        Self {
            entries: Vec::new(), filename: String::new(), trans_input: String::new(),
            lang: "中文".to_string(), max_words: 10, mode: 0,
            output: String::new(), status: "就绪".to_string(),
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                if ui.button("打开字幕文件…").clicked() {
                    if let Some(p) = rfd::FileDialog::new()
                        .add_filter("字幕", &["srt", "bcc", "txt"]).pick_file() {
                        match fs::read_to_string(&p) {
                            Ok(c) => {
                                self.entries = parse_subtitle(&c);
                                if self.entries.is_empty() {
                                    self.status = "解析失败：未找到字幕条目".to_string();
                                } else {
                                    self.filename = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                                    self.status = format!("{} · {} 条", self.filename, self.entries.len());
                                }
                            }
                            Err(e) => self.status = format!("读取失败: {}", e),
                        }
                    }
                }
                ui.label(&self.status);
            });
        });

        egui::TopBottomPanel::bottom("bottom").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("目标语言：");
                ui.text_edit_singleline(&mut self.lang);
                ui.label("最多词数：");
                ui.add(egui::DragValue::new(&mut self.max_words).clamp_range(2..=50));
                ui.separator();
                ui.radio_value(&mut self.mode, 0, "双语");
                ui.radio_value(&mut self.mode, 1, "仅原文");
                ui.radio_value(&mut self.mode, 2, "仅译文");
                ui.separator();
                if ui.button("预览拆分").clicked() {
                    let mut lines = Vec::new();
                    for e in &self.entries {
                        for (o, t) in split_paired(&e.text, &e.translated, self.max_words) {
                            let body = if t.is_empty() { o } else { format!("{}\n{}", o, t) };
                            lines.push(format!("[{}] {}", e.index, body.trim()));
                        }
                    }
                    self.output = lines.join("\n");
                }
                if ui.button("导出 SRT").clicked() {
                    if self.entries.is_empty() {
                        self.status = "请先加载字幕文件".to_string();
                    } else if let Some(p) = rfd::FileDialog::new()
                        .set_file_name(format!("【已翻译-{}】{}.srt", self.lang,
                            self.filename.rsplit_once('.').map(|(a, _)| a).unwrap_or(&self.filename)))
                        .add_filter("SRT", &["srt"]).save_file() {
                        let out = export_srt(&self.entries, self.mode);
                        match fs::write(&p, out) {
                            Ok(()) => self.status = format!("已导出：{}", p.display()),
                            Err(e) => self.status = format!("导出失败: {}", e),
                        }
                    }
                }
            });
        });

        egui::SidePanel::right("trans").default_width(320.0).show(ctx, |ui| {
            ui.heading("译文");
            ui.label("格式：[编号] 文本");
            ui.add(egui::TextEdit::multiline(&mut self.trans_input)
                .desired_rows(12).desired_width(f32::INFINITY));
            if ui.button("应用译文").clicked() {
                if self.entries.is_empty() {
                    self.status = "请先加载字幕文件".to_string();
                } else {
                    let n = apply_translation(&mut self.entries, &self.trans_input);
                    self.status = if n > 0 { format!("已应用 {} 条译文", n) }
                                  else { "未检测到 [编号] 格式".to_string() };
                }
            }
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::vertical().show(ui, |ui| {
                egui::Grid::new("entries").striped(true).show(ui, |ui| {
                    ui.strong("#"); ui.strong("开始"); ui.strong("结束");
                    ui.strong("原文"); ui.strong("译文"); ui.end_row();
                    for e in &self.entries {
                        ui.label(e.index.to_string());
                        ui.label(&e.start);
                        ui.label(&e.end);
                        ui.label(&e.text);
                        ui.label(&e.translated);
                        ui.end_row();
                    }
                });
                if !self.output.is_empty() {
                    ui.separator();
                    ui.heading("双语拆分预览");
                    ui.monospace(&self.output);
                }
            });
        });
    }
}

fn main() -> eframe::Result<()> {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([980.0, 720.0]),
        ..Default::default()
    };
    eframe::run_native("SubMerge Pro（Rust egui 版）", opts,
        Box::new(|_| Ok(Box::new(App::default()))))
}
