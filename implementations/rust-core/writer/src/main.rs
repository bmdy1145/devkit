//! Writer 内核版（Rust）
//!
//! 版本：A1_I_Φ5_Rust_CN
//! 对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html
//!
//! 只实现纯逻辑内核：书籍 / 卷 / 章节结构的 JSON 持久化、字数统计、
//! 章节排序、跨卷移动、引用（人物/地点等）管理、提示词模板合成。
//! 不含 UI——浏览器版用 IndexedDB + DOM，这里用 JSON 文件 + CLI。
//!
//! 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
//! 许可证：GPLv3

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Book {
    id: String,
    title: String,
    #[serde(default)]
    author: String,
    #[serde(default)]
    updated_at: i64,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Volume {
    id: String,
    book_id: String,
    title: String,
    order: i32,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Chapter {
    id: String,
    book_id: String,
    volume_id: String,
    title: String,
    order: i32,
    #[serde(default)]
    word_count: i64,
    #[serde(default)]
    updated_at: i64,
    #[serde(default)]
    text: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Entity {
    id: String,
    book_id: String,
    name: String,
    #[serde(default)]
    kind: String,
    #[serde(default)]
    description: String,
}

#[derive(Serialize, Deserialize, Default, Clone, Debug)]
struct Library {
    #[serde(default)]
    books: Vec<Book>,
    #[serde(default)]
    volumes: Vec<Volume>,
    #[serde(default)]
    chapters: Vec<Chapter>,
    #[serde(default)]
    entities: Vec<Entity>,
}

/// 与浏览器版一致的词数统计：CJK 每字算 1 词，拉丁词按整词算。
fn count_words(text: &str) -> i64 {
    let mut total = 0i64;
    let mut in_latin = false;

    for ch in text.chars() {
        let cp = ch as u32;
        let is_cjk = (0x3400..=0x4DBF).contains(&cp)
            || (0x4E00..=0x9FFF).contains(&cp)
            || (0x3040..=0x30FF).contains(&cp)
            || (0xAC00..=0xD7AF).contains(&cp)
            || (0xF900..=0xFAFF).contains(&cp);

        if is_cjk {
            total += 1;
            in_latin = false;
        } else if ch.is_ascii_alphanumeric() {
            if !in_latin {
                total += 1;
                in_latin = true;
            }
        } else {
            in_latin = false;
        }
    }
    total
}

fn now_ts() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

fn gen_id(prefix: &str) -> String {
    // 浏览器版用 crypto.randomUUID；内核版用时间戳 + 计数器足够唯一
    static COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let n = COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    format!("{}_{}_{}", prefix, now_ts(), n)
}

fn load(path: &Path) -> Result<Library, String> {
    if !path.exists() {
        return Ok(Library::default());
    }
    let raw = fs::read_to_string(path).map_err(|e| format!("读取 {} 失败: {}", path.display(), e))?;
    if raw.trim().is_empty() {
        return Ok(Library::default());
    }
    serde_json::from_str(&raw).map_err(|e| format!("解析 {} 失败: {}", path.display(), e))
}

fn save(path: &Path, lib: &Library) -> Result<(), String> {
    let json = serde_json::to_string_pretty(lib).map_err(|e| format!("序列化失败: {}", e))?;
    fs::write(path, json).map_err(|e| format!("写入 {} 失败: {}", path.display(), e))
}

fn chapters_of<'a>(lib: &'a Library, volume_id: &str) -> Vec<&'a Chapter> {
    let mut list: Vec<&Chapter> = lib.chapters.iter().filter(|c| c.volume_id == volume_id).collect();
    list.sort_by_key(|c| c.order);
    list
}

fn reorder_volume(lib: &mut Library, volume_id: &str) {
    let mut ids: Vec<String> = lib
        .chapters
        .iter()
        .filter(|c| c.volume_id == volume_id)
        .map(|c| c.id.clone())
        .collect();
    // 按现有 order 排序后重排为 0..n-1
    ids.sort_by_key(|id| {
        lib.chapters
            .iter()
            .find(|c| &c.id == id)
            .map(|c| c.order)
            .unwrap_or(0)
    });
    for (i, id) in ids.iter().enumerate() {
        if let Some(ch) = lib.chapters.iter_mut().find(|c| &c.id == id) {
            ch.order = i as i32;
        }
    }
}

fn usage() {
    println!("Writer 内核版（Rust）");
    println!("用法: writer <库文件.json> <子命令> [参数]");
    println!();
    println!("子命令:");
    println!("  init <书名>                       创建书籍");
    println!("  add-volume <书籍ID> <卷名>        新增卷");
    println!("  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]  新增章节");
    println!("  list <书籍ID>                     列出卷与章节（含字数）");
    println!("  stats <书籍ID>                    统计总字数");
    println!("  move-chapter <章节ID> <目标卷ID>   跨卷移动并重排顺序");
    println!("  add-entity <书籍ID> <名称> [类型] [描述]  添加资料条目");
    println!("  prompt <书籍ID> <章节ID> [模板]    生成提示词（默认续写模板）");
    println!("  pov <书籍ID> <章节ID> [--target first|second|third] [--no-inner]");
    println!("                                    人称转换提示词");
    println!("  reindex <书籍ID>                  重排所有卷的章节 order");
}

/// 人称转换的目标人称。key 与 --target 取值、HTML 版 A1_I_Φ5_CN 的
/// #povTarget option value 一一对应。
fn pov_target(key: &str) -> Option<&'static str> {
    match key {
        "first" => Some("第一人称（我）"),
        "second" => Some("第二人称（你）"),
        "third" => Some("第三人称（他 / 她 / 它）"),
        _ => None,
    }
}

/// 合成「人称转换」提示词，与 HTML 版 A1_I_Φ5_CN 的 pov 模板一致。
fn build_pov_prompt(body: &str, chars: &str, target: &str, keep_inner: bool) -> String {
    let inner = if keep_inner {
        "保留：原视角的内心活动改写为目标视角可知的部分（用表情、动作、语气或外部观察替代直接叙述他人内心）"
    } else {
        "不保留：删去目标视角无法感知的心理描写，只保留外在可见的行为与对白"
    };
    let lines = [
        format!("你是一位精通叙述视角的小说编辑。请把下面的正文转换为【{}】，情节、人物、场景与对白内容一律不变，只换叙述人称与视角。", target),
        String::new(),
        format!("【目标人称】{}", target),
        String::new(),
        format!("【心理描写处理】{}", inner),
        String::new(),
        "【相关设定】".to_string(),
        chars.to_string(),
        String::new(),
        "【需要转换的正文】".to_string(),
        body.to_string(),
        String::new(),
        "【转换规则】".to_string(),
        "1) 只改人称代词与由此引起的视角变化，不增删情节、不改变人物性格与说话方式；".to_string(),
        "2) 第一人称：叙述者用「我」，只能写出「我」能感知到的内容（看到、听到、想到），不能直接叙述旁人心里在想什么；".to_string(),
        "3) 第二人称：叙述者用「你」，把读者带入场景，动作与感受都落在「你」身上；".to_string(),
        "4) 第三人称：叙述者用「他 / 她 / 它」或人物姓名，人物之间用姓名或称谓区分，避免代词指向不明；".to_string(),
        "5) 时间线、场景顺序、对白内容保持原样，对白中人物自称按其在故事中的实际人称调整；".to_string(),
        "6) 转换后通读一遍，确保没有残留的原人称代词、没有视角越界、没有半途切换人称。".to_string(),
        String::new(),
        "【输出要求】直接输出转换后的完整正文，不要加解释、不要加标题、不要用「以下是」之类的开场白，便于直接替换当前章。".to_string(),
    ];
    lines.join("\n")
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 2 {
        usage();
        return ExitCode::FAILURE;
    }
    let lib_path = PathBuf::from(&args[0]);
    let cmd = args[1].as_str();

    let mut lib = match load(&lib_path) {
        Ok(l) => l,
        Err(e) => { eprintln!("{}", e); return ExitCode::FAILURE; }
    };

    let result: Result<(), String> = (|| {
        match cmd {
            "init" => {
                let title = args.get(2).ok_or("缺少书名")?.clone();
                let book = Book {
                    id: gen_id("book"),
                    title,
                    author: String::new(),
                    updated_at: now_ts(),
                };
                println!("已创建书籍: {} ({})", book.title, book.id);
                lib.books.push(book);
            }
            "add-volume" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let title = args.get(3).ok_or("缺少卷名")?.clone();
                if !lib.books.iter().any(|b| b.id == book_id) {
                    return Err(format!("找不到书籍 {}", book_id));
                }
                let order = lib.volumes.iter().filter(|v| v.book_id == book_id).count() as i32;
                let vol = Volume { id: gen_id("vol"), book_id, title, order };
                println!("已新增卷: {} ({})", vol.title, vol.id);
                lib.volumes.push(vol);
            }
            "add-chapter" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let vol_id = args.get(3).ok_or("缺少卷ID")?.clone();
                let title = args.get(4).ok_or("缺少章节名")?.clone();
                let text = match args.get(5) {
                    Some(p) => fs::read_to_string(p).map_err(|e| format!("读取正文失败: {}", e))?,
                    None => String::new(),
                };
                if !lib.volumes.iter().any(|v| v.id == vol_id) {
                    return Err(format!("找不到卷 {}", vol_id));
                }
                let order = lib.chapters.iter().filter(|c| c.volume_id == vol_id).count() as i32;
                let wc = count_words(&text);
                let ch = Chapter {
                    id: gen_id("ch"),
                    book_id,
                    volume_id: vol_id,
                    title,
                    order,
                    word_count: wc,
                    updated_at: now_ts(),
                    text,
                };
                println!("已新增章节: {} ({}) · {} 字", ch.title, ch.id, wc);
                lib.chapters.push(ch);
            }
            "list" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?;
                let book = lib.books.iter().find(|b| &b.id == book_id).ok_or("找不到书籍")?;
                println!("书籍: {} ({})", book.title, book.id);
                let mut vols: Vec<&Volume> = lib.volumes.iter().filter(|v| &v.book_id == book_id).collect();
                vols.sort_by_key(|v| v.order);
                for v in vols {
                    println!("  卷: {} (order {})", v.title, v.order);
                    for c in chapters_of(&lib, &v.id) {
                        println!("    - [{}] {} · {} 字", c.order, c.title, c.word_count);
                    }
                }
            }
            "stats" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?;
                let chapters: Vec<&Chapter> = lib.chapters.iter().filter(|c| &c.book_id == book_id).collect();
                let total: i64 = chapters.iter().map(|c| c.word_count).sum();
                println!("章节数: {}", chapters.len());
                println!("总字数: {}", total);
                println!("总字符: {}", chapters.iter().map(|c| c.text.chars().count() as i64).sum::<i64>());
            }
            "move-chapter" => {
                let ch_id = args.get(2).ok_or("缺少章节ID")?.clone();
                let target_vol = args.get(3).ok_or("缺少目标卷ID")?.clone();
                let idx = lib.chapters.iter().position(|c| c.id == ch_id).ok_or("找不到章节")?;
                if !lib.volumes.iter().any(|v| v.id == target_vol) {
                    return Err(format!("找不到目标卷 {}", target_vol));
                }
                let source_vol = lib.chapters[idx].volume_id.clone();
                let new_order = lib.chapters.iter().filter(|c| c.volume_id == target_vol).count() as i32;
                lib.chapters[idx].volume_id = target_vol.clone();
                lib.chapters[idx].order = new_order;
                // 与浏览器版一致：目标卷与源卷都要重排
                reorder_volume(&mut lib, &target_vol);
                reorder_volume(&mut lib, &source_vol);
                println!("已将章节移至目标卷，并重排源卷与目标卷的顺序");
            }
            "add-entity" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let name = args.get(3).ok_or("缺少名称")?.clone();
                let kind = args.get(4).cloned().unwrap_or_else(|| "其他".to_string());
                let desc = args.get(5).cloned().unwrap_or_default();
                let e = Entity { id: gen_id("ent"), book_id, name: name.clone(), kind, description: desc };
                println!("已添加资料: {} ({})", e.name, e.id);
                lib.entities.push(e);
            }
            "prompt" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let ch_id = args.get(3).ok_or("缺少章节ID")?.clone();
                let ch = lib.chapters.iter().find(|c| c.id == ch_id).ok_or("找不到章节")?;
                let list = chapters_of(&lib, &ch.volume_id);
                let pos = list.iter().position(|c| c.id == ch_id).unwrap_or(0);
                let prev_text = if pos > 0 {
                    let p = list[pos - 1];
                    let t = &p.text;
                    let tail: String = t.chars().rev().take(500).collect::<Vec<_>>().into_iter().rev().collect();
                    tail
                } else {
                    "（本章为卷首，无上一章）".to_string()
                };
                let chars: String = lib
                    .entities
                    .iter()
                    .filter(|e| e.book_id == book_id)
                    .map(|e| format!("- {}（{}）：{}", e.name, e.kind, e.description))
                    .collect::<Vec<_>>()
                    .join("\n");
                println!("你是一位与作者合写的小说作者。请续写下一段情节。");
                println!();
                println!("【设定】");
                println!("{}", if chars.is_empty() { "（未填写）" } else { &chars });
                println!();
                println!("【上一章结尾】");
                println!("{}", prev_text);
                println!();
                println!("【本章已有正文】");
                println!("{}", if ch.text.is_empty() { "（当前章为空）" } else { &ch.text });
            }
            "pov" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let ch_id = args.get(3).ok_or("缺少章节ID")?.clone();
                let mut target_key = "third".to_string();
                let mut keep_inner = true;
                let mut i = 4;
                while i < args.len() {
                    match args[i].as_str() {
                        "--target" => {
                            target_key = args.get(i + 1).ok_or("--target 缺少取值")?.clone();
                            i += 2;
                        }
                        "--no-inner" => { keep_inner = false; i += 1; }
                        other => return Err(format!("无法识别的参数: {}", other)),
                    }
                }
                let target = pov_target(&target_key)
                    .ok_or(format!("目标人称无效：{}（可选 first / second / third）", target_key))?;
                let ch = lib.chapters.iter().find(|c| c.id == ch_id).ok_or("找不到章节")?;
                let body = if ch.text.is_empty() { "（当前章为空）" } else { &ch.text };
                let chars_list: Vec<String> = lib
                    .entities
                    .iter()
                    .filter(|e| e.book_id == book_id)
                    .map(|e| format!("- {}（{}）：{}", e.name, e.kind, e.description))
                    .collect();
                let chars: String = if chars_list.is_empty() {
                    "（未填写）".to_string()
                } else {
                    chars_list.join("\n")
                };
                println!("{}", build_pov_prompt(body, &chars, target, keep_inner));
            }
            "reindex" => {
                let book_id = args.get(2).ok_or("缺少书籍ID")?.clone();
                let vol_ids: Vec<String> = lib.volumes.iter().filter(|v| v.book_id == book_id).map(|v| v.id.clone()).collect();
                for vid in vol_ids {
                    reorder_volume(&mut lib, &vid);
                }
                println!("已重排全部卷的章节顺序");
            }
            other => return Err(format!("未知子命令: {}", other)),
        }
        Ok(())
    })();

    if let Err(e) = result {
        eprintln!("错误: {}", e);
        return ExitCode::FAILURE;
    }

    if let Err(e) = save(&lib_path, &lib) {
        eprintln!("{}", e);
        return ExitCode::FAILURE;
    }
    ExitCode::SUCCESS
}
