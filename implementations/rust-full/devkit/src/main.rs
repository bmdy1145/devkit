//! DevKit 全功能版（Rust / egui）
//!
//! 版本：A1_V_Φ9_Fix_Rust_CN
//! 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//!
//! 图形界面版：项目/页签、灵感、组合预览、代码与结果编辑、九款主题切换、
//! 配置导入导出。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use eframe::egui;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

const CURRENT_VERSION: &str = "A1_V_Φ9_Fix_Rust_CN";

const THEMES: &[(&str, egui::Color32, egui::Color32, egui::Color32)] = &[
    ("Clean", egui::Color32::from_rgb(249, 250, 251), egui::Color32::from_rgb(17, 24, 39), egui::Color32::from_rgb(59, 130, 246)),
    ("Glass", egui::Color32::from_rgb(18, 20, 26), egui::Color32::from_rgb(232, 236, 244), egui::Color32::from_rgb(110, 168, 255)),
    ("Neon", egui::Color32::from_rgb(8, 9, 13), egui::Color32::from_rgb(233, 242, 236), egui::Color32::from_rgb(187, 243, 81)),
    ("Mono", egui::Color32::from_rgb(10, 10, 10), egui::Color32::from_rgb(230, 230, 230), egui::Color32::from_rgb(0, 255, 65)),
    ("Material", egui::Color32::from_rgb(20, 18, 24), egui::Color32::from_rgb(230, 224, 233), egui::Color32::from_rgb(208, 188, 255)),
    ("Minimal", egui::Color32::from_rgb(244, 244, 241), egui::Color32::from_rgb(12, 12, 9), egui::Color32::from_rgb(49, 44, 133)),
    ("Premium", egui::Color32::from_rgb(28, 28, 30), egui::Color32::from_rgb(245, 245, 247), egui::Color32::from_rgb(37, 99, 235)),
    ("Shadcn", egui::Color32::from_rgb(255, 255, 255), egui::Color32::from_rgb(9, 9, 11), egui::Color32::from_rgb(24, 24, 27)),
    ("Baseline", egui::Color32::from_rgb(30, 30, 30), egui::Color32::from_rgb(204, 204, 204), egui::Color32::from_rgb(86, 156, 214)),
];

const TEMPLATES: &[(&str, &str)] = &[
    ("版本规划", "你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。"),
    ("需求分析", "你是一位资深系统分析师。请对下面需求做全面分析。"),
    ("安全审计", "你是一位持有 OSCP 认证的安全专家。请审计下面的代码。"),
    ("性能审计", "你是一位性能优化专家。请审计下面的代码。"),
    ("结构重构", "你是一位资深架构师。请重构下面的代码。"),
    ("单元测试", "请为下面的代码编写单元测试。"),
    ("空白", ""),
];

#[derive(Serialize, Deserialize, Clone, Default)]
struct Tab {
    id: String,
    #[serde(rename = "type")] kind: String,
    #[serde(default)] inspiration: String,
}

#[derive(Serialize, Deserialize, Clone, Default)]
struct Project {
    id: String,
    name: String,
    #[serde(default)] tabs: Vec<Tab>,
    #[serde(default)] code: String,
    #[serde(default)] result: String,
}

#[derive(Serialize, Deserialize, Clone, Default)]
struct Settings {
    #[serde(default = "default_theme")] theme: String,
}
fn default_theme() -> String { "Clean".to_string() }

#[derive(Serialize, Deserialize, Clone, Default)]
struct State {
    #[serde(default = "default_version")] version: String,
    #[serde(rename = "activeProjectId", default)] active_project_id: String,
    #[serde(default)] projects: Vec<Project>,
    #[serde(default)] settings: Settings,
}
fn default_version() -> String { CURRENT_VERSION.to_string() }

static ID_CTR: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
fn gen_id(p: &str) -> String {
    let n = ID_CTR.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis()).unwrap_or(0);
    format!("{}_{}_{}", p, t, n)
}

fn default_state() -> State {
    let tabs = TEMPLATES.iter().map(|(n, _)| Tab {
        id: gen_id("tab"), kind: n.to_string(), inspiration: String::new(),
    }).collect();
    State {
        version: CURRENT_VERSION.to_string(),
        active_project_id: "proj_1".to_string(),
        projects: vec![Project {
            id: "proj_1".to_string(), name: "默认项目".to_string(),
            tabs, code: String::new(), result: String::new(),
        }],
        settings: Settings { theme: "Clean".to_string() },
    }
}

struct App {
    state: State,
    path: Option<PathBuf>,
    tab_idx: usize,
    status: String,
}

impl Default for App {
    fn default() -> Self {
        Self { state: default_state(), path: None, tab_idx: 0, status: "就绪".to_string() }
    }
}

impl App {
    fn project(&self) -> Option<&Project> {
        self.state.projects.iter().find(|p| p.id == self.state.active_project_id)
    }
    fn project_mut(&mut self) -> Option<&mut Project> {
        let id = self.state.active_project_id.clone();
        self.state.projects.iter_mut().find(|p| p.id == id)
    }

    fn compose(&self) -> String {
        let Some(p) = self.project() else { return String::new(); };
        let Some(t) = p.tabs.get(self.tab_idx) else { return String::new(); };
        let head = TEMPLATES.iter().find(|(n, _)| *n == t.kind).map(|(_, h)| *h).unwrap_or("");
        let insp = if t.inspiration.is_empty() { "（无需求）" } else { &t.inspiration };
        let code = if p.code.is_empty() { "（无代码）" } else { &p.code };
        if head.is_empty() {
            format!("需求：{}\n\n代码：\n{}", insp, code)
        } else {
            format!("{}\n\n需求：{}\n\n代码：\n{}", head, insp, code)
        }
    }

    fn save(&mut self) {
        if let Some(p) = self.path.clone() {
            self.state.version = CURRENT_VERSION.to_string();
            if let Ok(json) = serde_json::to_string_pretty(&self.state) {
                if fs::write(&p, json).is_ok() { self.status = "已保存".to_string(); }
            }
        }
    }

    fn apply_theme(&self, ctx: &egui::Context) {
        let name = &self.state.settings.theme;
        let (_, bg, fg, accent) = THEMES.iter().find(|(n, _, _, _)| n == name)
            .copied().unwrap_or(THEMES[8]);
        let mut visuals = if bg.r() as u32 + bg.g() as u32 + bg.b() as u32 > 380 {
            egui::Visuals::light()
        } else {
            egui::Visuals::dark()
        };
        visuals.override_text_color = Some(fg);
        visuals.widgets.noninteractive.bg_fill = bg;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.selection.bg_fill = accent.gamma_multiply(0.5);
        ctx.set_visuals(visuals);
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        self.apply_theme(ctx);
        self.draw_top(ctx);
        self.draw_side(ctx);
        self.draw_center(ctx);
    }
}

impl App {
    fn draw_top(&mut self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("top").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("主题：");
                let mut chosen = self.state.settings.theme.clone();
                egui::ComboBox::from_id_salt("theme")
                    .selected_text(&chosen)
                    .show_ui(ui, |ui| {
                        for (name, _, _, _) in THEMES {
                            ui.selectable_value(&mut chosen, name.to_string(), *name);
                        }
                    });
                self.state.settings.theme = chosen;

                if ui.button("新建项目").clicked() {
                    let tabs: Vec<Tab> = TEMPLATES.iter().map(|(n, _)| Tab {
                        id: gen_id("tab"),
                        kind: n.to_string(),
                        inspiration: String::new(),
                    }).collect();
                    let np = Project {
                        id: gen_id("proj"),
                        name: "新项目".to_string(),
                        tabs,
                        code: String::new(),
                        result: String::new(),
                    };
                    self.state.active_project_id = np.id.clone();
                    self.state.projects.push(np);
                    self.tab_idx = 0;
                }
                if ui.button("打开配置…").clicked() {
                    if let Some(path) = rfd::FileDialog::new().add_filter("JSON", &["json"]).pick_file() {
                        if let Ok(txt) = fs::read_to_string(&path) {
                            if let Ok(st) = serde_json::from_str::<State>(&txt) {
                                if !st.projects.is_empty() {
                                    self.state = st;
                                    self.path = Some(path);
                                    self.tab_idx = 0;
                                    self.status = "已导入".to_string();
                                }
                            }
                        }
                    }
                }
                if ui.button("导出配置").clicked() {
                    let picked = rfd::FileDialog::new()
                        .set_file_name("devkit_config.json")
                        .add_filter("JSON", &["json"])
                        .save_file();
                    if let Some(path) = picked {
                        self.path = Some(path);
                        self.save();
                    }
                }
                ui.label(&self.status);
            });
        });
    }

    fn draw_side(&mut self, ctx: &egui::Context) {
        egui::SidePanel::left("side").default_width(300.0).show(ctx, |ui| {
            ui.heading("工作流步骤");
            let names: Vec<String> = match self.project() {
                Some(p) => p.tabs.iter().map(|t| t.kind.clone()).collect(),
                None => Vec::new(),
            };
            for (i, name) in names.iter().enumerate() {
                if ui.selectable_label(self.tab_idx == i, name).clicked() {
                    self.tab_idx = i;
                }
            }
            ui.separator();
            ui.label("灵感");
            let mut insp = match self.project().and_then(|p| p.tabs.get(self.tab_idx)) {
                Some(t) => t.inspiration.clone(),
                None => String::new(),
            };
            let changed = ui
                .add(egui::TextEdit::multiline(&mut insp).desired_rows(4).desired_width(f32::INFINITY))
                .changed();
            if changed {
                let idx = self.tab_idx;
                if let Some(p) = self.project_mut() {
                    if let Some(t) = p.tabs.get_mut(idx) {
                        t.inspiration = insp;
                    }
                }
            }
            ui.separator();
            ui.label("组合预览");
            let preview = self.compose();
            let mut preview_view = preview.clone();
            ui.add(egui::TextEdit::multiline(&mut preview_view).desired_rows(10).desired_width(f32::INFINITY));
            if ui.button("复制").clicked() {
                ctx.copy_text(preview);
                self.status = "已复制".to_string();
            }
        });
    }

    fn draw_center(&mut self, ctx: &egui::Context) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.label("代码编辑区");
            let mut code = match self.project() {
                Some(p) => p.code.clone(),
                None => String::new(),
            };
            if ui
                .add(egui::TextEdit::multiline(&mut code).desired_rows(16).desired_width(f32::INFINITY))
                .changed()
            {
                if let Some(p) = self.project_mut() {
                    p.code = code;
                }
            }
            ui.label("AI 处理结果");
            let mut res = match self.project() {
                Some(p) => p.result.clone(),
                None => String::new(),
            };
            if ui
                .add(egui::TextEdit::multiline(&mut res).desired_rows(6).desired_width(f32::INFINITY))
                .changed()
            {
                if let Some(p) = self.project_mut() {
                    p.result = res;
                }
            }
            if ui.button("用结果覆盖代码区").clicked() {
                if let Some(p) = self.project_mut() {
                    if !p.result.is_empty() {
                        p.code = p.result.clone();
                        p.result.clear();
                    }
                }
            }
        });
    }
}

fn main() -> eframe::Result<()> {
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1200.0, 820.0]),
        ..Default::default()
    };
    eframe::run_native("DevKit（Rust egui 版）", opts, Box::new(|_| Ok(Box::new(App::default()))))
}
