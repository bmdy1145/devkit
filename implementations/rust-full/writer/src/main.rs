//! Writer 全功能版（Rust / egui）
//!
//! 版本：A1_I_Φ3_Rust_CN
//! 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//!
//! 图形界面版：左侧章节树、中间正文编辑、右侧资料与提示词、字数统计、自动保存。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use eframe::egui;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone, Default)]
struct Book { id: String, title: String, #[serde(default)] author: String, #[serde(default)] updated_at: i64 }
#[derive(Serialize, Deserialize, Clone, Default)]
struct Volume { id: String, book_id: String, title: String, #[serde(default)] order: i32 }
#[derive(Serialize, Deserialize, Clone, Default)]
struct Chapter {
    id: String, book_id: String, volume_id: String, title: String,
    #[serde(default)] order: i32, #[serde(default)] word_count: i64,
    #[serde(default)] updated_at: i64, #[serde(default)] text: String,
}
#[derive(Serialize, Deserialize, Clone, Default)]
struct Entity { id: String, book_id: String, name: String, #[serde(default)] kind: String, #[serde(default)] description: String }

#[derive(Serialize, Deserialize, Default, Clone)]
struct Library {
    #[serde(default)] books: Vec<Book>,
    #[serde(default)] volumes: Vec<Volume>,
    #[serde(default)] chapters: Vec<Chapter>,
    #[serde(default)] entities: Vec<Entity>,
}

fn count_words(text: &str) -> i64 {
    let mut total = 0i64;
    let mut in_latin = false;
    for ch in text.chars() {
        let cp = ch as u32;
        let cjk = (0x3400..=0x4DBF).contains(&cp) || (0x4E00..=0x9FFF).contains(&cp)
            || (0x3040..=0x30FF).contains(&cp) || (0xAC00..=0xD7AF).contains(&cp)
            || (0xF900..=0xFAFF).contains(&cp);
        if cjk { total += 1; in_latin = false; }
        else if ch.is_alphanumeric() { if !in_latin { total += 1; in_latin = true; } }
        else { in_latin = false; }
    }
    total
}

fn now_ts() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64).unwrap_or(0)
}

static ID_CTR: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
fn gen_id(p: &str) -> String {
    let n = ID_CTR.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    format!("{}_{}_{}", p, now_ts(), n)
}

struct App {
    lib: Library,
    path: Option<PathBuf>,
    sel_chapter: Option<String>,
    edit_title: String,
    edit_text: String,
    input: String,
    prompt: String,
    status: String,
    dirty: bool,
    new_volume: String,
    new_chapter: String,
    ent_name: String,
    ent_kind: String,
    ent_desc: String,
}

impl Default for App {
    fn default() -> Self {
        Self {
            lib: Library::default(), path: None, sel_chapter: None,
            edit_title: String::new(), edit_text: String::new(),
            input: String::new(), prompt: String::new(), status: "就绪".to_string(),
            dirty: false, new_volume: String::new(), new_chapter: String::new(),
            ent_name: String::new(), ent_kind: String::new(), ent_desc: String::new(),
        }
    }
}

impl App {
    fn open(&mut self) {
        if let Some(p) = rfd::FileDialog::new().add_filter("JSON", &["json"]).pick_file() {
            self.lib = fs::read_to_string(&p).ok()
                .and_then(|s| if s.trim().is_empty() { None } else { serde_json::from_str(&s).ok() })
                .unwrap_or_default();
            if self.lib.books.is_empty() {
                self.lib.books.push(Book { id: gen_id("book"), title: "未命名".into(), author: String::new(), updated_at: now_ts() });
            }
            self.path = Some(p);
            self.status = "已打开".to_string();
        }
    }

    fn save(&mut self) {
        let Some(p) = self.path.clone() else { return; };
        {
            self.sync_current();
            if let Ok(json) = serde_json::to_string_pretty(&self.lib) {
                if fs::write(&p, json).is_ok() {
                    self.dirty = false;
                    self.status = "已保存".to_string();
                }
            }
        }
    }

    fn sync_current(&mut self) {
        if let Some(id) = &self.sel_chapter {
            if let Some(ch) = self.lib.chapters.iter_mut().find(|c| &c.id == id) {
                ch.title = self.edit_title.clone();
                ch.text = self.edit_text.clone();
                ch.word_count = count_words(&ch.text);
                ch.updated_at = now_ts();
            }
        }
    }

    fn select_chapter(&mut self, id: &str) {
        self.sync_current();
        if let Some(ch) = self.lib.chapters.iter().find(|c| c.id == id) {
            self.sel_chapter = Some(id.to_string());
            self.edit_title = ch.title.clone();
            self.edit_text = ch.text.clone();
        }
    }

    fn build_prompt(&mut self) {
        let Some(id) = self.sel_chapter.clone() else { return; };
        let Some(ch) = self.lib.chapters.iter().find(|c| c.id == id) else { return; };
        let mut list: Vec<&Chapter> = self.lib.chapters.iter().filter(|c| c.volume_id == ch.volume_id).collect();
        list.sort_by_key(|c| c.order);
        let pos = list.iter().position(|c| c.id == id).unwrap_or(0);
        let prev = if pos > 0 {
            let t = &list[pos - 1].text;
            let chars: Vec<char> = t.chars().collect();
            if chars.len() > 500 { chars[chars.len() - 500..].iter().collect() } else { t.clone() }
        } else { "（本章为卷首，无上一章）".to_string() };
        let chars = self.lib.entities.iter().filter(|e| e.book_id == ch.book_id)
            .map(|e| format!("- {}（{}）：{}", e.name, e.kind, e.description))
            .collect::<Vec<_>>();
        let chars = if chars.is_empty() { "（未填写）".to_string() } else { chars.join("\n") };
        let body = if ch.text.is_empty() { "（当前章为空）".to_string() } else { ch.text.clone() };
        self.prompt = format!("你是一位与作者合写的小说作者。请续写下一段情节。\n\n【设定】\n{}\n\n【上一章结尾】\n{}\n\n【本章已有正文】\n{}", chars, prev, body);
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                if ui.button("打开库…").clicked() { self.open(); }
                if ui.button("保存").clicked() { self.save(); }
                ui.label(&self.status);
                if self.dirty { ui.colored_label(egui::Color32::from_rgb(200, 140, 0), "● 未保存"); }
            });
        });

        egui::SidePanel::left("tree").default_width(240.0).show(ctx, |ui| {
            ui.heading("章节树");
            egui::ScrollArea::vertical().max_height(420.0).show(ui, |ui| {
                let vols: Vec<(String, String, i32)> = {
                    let mut v: Vec<&Volume> = self.lib.volumes.iter().collect();
                    v.sort_by_key(|x| x.order);
                    v.iter().map(|x| (x.id.clone(), x.title.clone(), x.order)).collect()
                };
                for (vid, vtitle, _) in vols {
                    ui.label(egui::RichText::new(format!("卷：{}", vtitle)).strong());
                    let mut chs: Vec<(String, String, i32, i64)> = self.lib.chapters.iter()
                        .filter(|c| c.volume_id == vid)
                        .map(|c| (c.id.clone(), c.title.clone(), c.order, c.word_count))
                        .collect();
                    chs.sort_by_key(|x| x.2);
                    for (cid, ctitle, _, wc) in chs {
                        let selected = self.sel_chapter.as_deref() == Some(&cid);
                        if ui.selectable_label(selected, format!("  {} · {} 字", ctitle, wc)).clicked() {
                            self.select_chapter(&cid);
                        }
                    }
                }
            });
            ui.separator();
            ui.label("新增卷：");
            ui.horizontal(|ui| {
                ui.text_edit_singleline(&mut self.new_volume);
                if ui.button("+").clicked() && !self.new_volume.is_empty() {
                    let book_id = self.lib.books.first().map(|b| b.id.clone()).unwrap_or_default();
                    let order = self.lib.volumes.iter().filter(|v| v.book_id == book_id).count() as i32;
                    self.lib.volumes.push(Volume { id: gen_id("vol"), book_id, title: self.new_volume.clone(), order });
                    self.new_volume.clear();
                    self.dirty = true;
                }
            });
            ui.label("新增章节：");
            ui.horizontal(|ui| {
                ui.text_edit_singleline(&mut self.new_chapter);
                if ui.button("+").clicked() && !self.new_chapter.is_empty() {
                    if let Some(vol) = self.lib.volumes.last() {
                        let vol_id = vol.id.clone();
                        let book_id = vol.book_id.clone();
                        let order = self.lib.chapters.iter().filter(|c| c.volume_id == vol_id).count() as i32;
                        let ch = Chapter { id: gen_id("ch"), book_id, volume_id: vol_id, title: self.new_chapter.clone(),
                            order, word_count: 0, updated_at: now_ts(), text: String::new() };
                        let id = ch.id.clone();
                        self.lib.chapters.push(ch);
                        self.new_chapter.clear();
                        self.select_chapter(&id);
                        self.dirty = true;
                    }
                }
            });
        });

        egui::SidePanel::right("right").default_width(300.0).show(ctx, |ui| {
            ui.heading("资料");
            egui::ScrollArea::vertical().max_height(200.0).show(ui, |ui| {
                for e in &self.lib.entities {
                    ui.label(format!("• {}（{}）", e.name, e.kind));
                }
            });
            ui.separator();
            ui.text_edit_singleline(&mut self.ent_name);
            ui.text_edit_singleline(&mut self.ent_kind);
            ui.text_edit_singleline(&mut self.ent_desc);
            if ui.button("添加资料").clicked() && !self.ent_name.is_empty() {
                let book_id = self.lib.books.first().map(|b| b.id.clone()).unwrap_or_default();
                self.lib.entities.push(Entity { id: gen_id("ent"), book_id, name: self.ent_name.clone(),
                    kind: if self.ent_kind.is_empty() { "其他".into() } else { self.ent_kind.clone() },
                    description: self.ent_desc.clone() });
                self.ent_name.clear(); self.ent_kind.clear(); self.ent_desc.clear();
                self.dirty = true;
            }
            ui.separator();
            if ui.button("生成续写提示词").clicked() { self.build_prompt(); }
            ui.add(egui::TextEdit::multiline(&mut self.prompt).desired_rows(10).desired_width(f32::INFINITY));
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("标题：");
                if ui.text_edit_singleline(&mut self.edit_title).changed() { self.dirty = true; }
            });
            let resp = ui.add(egui::TextEdit::multiline(&mut self.edit_text)
                .desired_width(f32::INFINITY)
                .desired_rows(24));
            if resp.changed() { self.dirty = true; }
            ui.label(format!("本章 {} 字 · {} 字符", count_words(&self.edit_text), self.edit_text.chars().count()));
        });
    }
}

fn main() -> eframe::Result<()> {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1200.0, 800.0]),
        ..Default::default()
    };
    eframe::run_native("Writer（Rust egui 版）", opts, Box::new(|_| Ok(Box::new(App::default()))))
}
