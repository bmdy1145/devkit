#!/usr/bin/env node
// Writer 全功能版（TypeScript / Node）
//
// 版本：A1_I_Φ3_TypeScript_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//
// Node 无内置 GUI（Electron 会让体积涨到 100MB+），本版用交互式终端
// 管理界面，覆盖书籍/卷/章节的增删、正文编辑、字数统计、资料库与提示词。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');
const readline = require('readline');

const C = { reset:'\x1b[0m', bold:'\x1b[1m', dim:'\x1b[2m',
  red:'\x1b[31m', green:'\x1b[32m', yellow:'\x1b[33m', blue:'\x1b[34m', cyan:'\x1b[36m' };

let counter = 0;
const genId = (p) => `${p}_${Date.now()}_${++counter}`;
const nowTs = () => Date.now();

const RE_CJK = /[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\uF900-\uFAFF]/g;
const RE_WORD = /[A-Za-z0-9]+(?:['\u2019-][A-Za-z0-9]+)*/g;
function countWords(text) {
  if (!text) return 0;
  const cjk = text.match(RE_CJK), words = text.match(RE_WORD);
  return (cjk ? cjk.length : 0) + (words ? words.length : 0);
}

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise((r) => rl.question(q, (a) => r(a.trim())));

const empty = () => ({ books: [], volumes: [], chapters: [], entities: [] });
function load(p) {
  if (!fs.existsSync(p)) return empty();
  const raw = fs.readFileSync(p, 'utf8').trim();
  if (!raw) return empty();
  const d = JSON.parse(raw);
  return { books: d.books||[], volumes: d.volumes||[], chapters: d.chapters||[], entities: d.entities||[] };
}
const save = (p, lib) => fs.writeFileSync(p, JSON.stringify(lib, null, 2), 'utf8');

function showTree(lib) {
  for (const v of lib.volumes.sort((a,b)=>a.order-b.order)) {
    console.log(`  ${C.bold}卷：${v.title}${C.reset}`);
    for (const c of lib.chapters.filter(x=>x.volume_id===v.id).sort((a,b)=>a.order-b.order))
      console.log(`    - [${c.order}] ${c.title} · ${c.word_count||0} 字`);
  }
}

async function main() {
  console.log(`\n${C.cyan}${C.bold}Writer 全功能版（TypeScript）${C.reset}\n`);
  const path = await ask('库文件路径（回车默认 writer.json）：') || 'writer.json';
  const lib = load(path);

  while (true) {
    console.log(`\n${C.bold}当前结构${C.reset}`);
    if (!lib.volumes.length) console.log(`  ${C.dim}（空）${C.reset}`);
    showTree(lib);

    console.log(`\n${C.bold}操作${C.reset}  1=新增卷 2=新增章节 3=编辑章节 4=改卷名 5=新增资料 6=生成提示词 7=统计 0=退出`);
    const op = await ask('选择：');

    if (op === '0') break;

    if (op === '1') {
      const bookId = lib.books[0] ? lib.books[0].id : (lib.books.push({id:genId('book'),title:'默认书',author:'',updated_at:nowTs()}), lib.books[0].id);
      const title = await ask('卷名：');
      if (!title) continue;
      const order = lib.volumes.filter(v=>v.book_id===bookId).length;
      lib.volumes.push({ id: genId('vol'), book_id: bookId, title, order });
      console.log(`${C.green}✓${C.reset} 已新增卷`);
    } else if (op === '2') {
      if (!lib.volumes.length) { console.log(`${C.yellow}⚠${C.reset} 请先新增卷`); continue; }
      const title = await ask('章节名：');
      if (!title) continue;
      const vol = lib.volumes[lib.volumes.length-1];
      const order = lib.chapters.filter(c=>c.volume_id===vol.id).length;
      lib.chapters.push({ id: genId('ch'), book_id: vol.book_id, volume_id: vol.id,
        title, order, word_count: 0, updated_at: nowTs(), text: '' });
      console.log(`${C.green}✓${C.reset} 已新增章节「${title}」`);
    } else if (op === '3') {
      if (!lib.chapters.length) { console.log(`${C.yellow}⚠${C.reset} 没有章节`); continue; }
      lib.chapters.forEach((c,i)=>console.log(`  ${i+1}. ${c.title}（${c.word_count||0} 字）`));
      const idx = parseInt(await ask('选择章节编号：'), 10) - 1;
      const ch = lib.chapters[idx];
      if (!ch) { console.log(`${C.red}无效编号${C.reset}`); continue; }
      console.log(ch.text || '（空）');
      console.log(`\n${C.dim}输入正文内容（单行，空行结束）${C.reset}`);
      const lines = [];
      while (true) {
        const line = await ask('');
        if (!line) break;
        lines.push(line);
      }
      if (lines.length) {
        ch.text = lines.join('\n');
        ch.word_count = countWords(ch.text);
        ch.updated_at = nowTs();
        console.log(`${C.green}✓${C.reset} 已更新 · ${ch.word_count} 字`);
      }
    } else if (op === '4') {
      if (!lib.volumes.length) continue;
      lib.volumes.forEach((v,i)=>console.log(`  ${i+1}. ${v.title}`));
      const idx = parseInt(await ask('选择卷编号：'), 10) - 1;
      if (lib.volumes[idx]) {
        const t = await ask('新卷名：');
        if (t) lib.volumes[idx].title = t;
      }
    } else if (op === '5') {
      const name = await ask('资料名称：');
      if (!name) continue;
      const kind = await ask('类型（人物/地点等）：') || '其他';
      const desc = await ask('描述：') || '';
      const bookId = lib.books[0] ? lib.books[0].id : null;
      lib.entities.push({ id: genId('ent'), book_id: bookId, name, kind, description: desc });
      console.log(`${C.green}✓${C.reset} 已添加资料`);
    } else if (op === '6') {
      if (!lib.chapters.length) continue;
      lib.chapters.forEach((c,i)=>console.log(`  ${i+1}. ${c.title}`));
      const idx = parseInt(await ask('选择章节编号：'), 10) - 1;
      const ch = lib.chapters[idx];
      if (!ch) continue;
      const lst = lib.chapters.filter(c=>c.volume_id===ch.volume_id).sort((a,b)=>a.order-b.order);
      const pos = lst.findIndex(c=>c.id===ch.id);
      const prev = pos > 0 ? (lst[pos-1].text||'').slice(-500) : '（本章为卷首，无上一章）';
      const ents = lib.entities.filter(e=>e.book_id===ch.book_id);
      const chars = ents.length ? ents.map(e=>`- ${e.name}（${e.kind}）：${e.description}`).join('\n') : '（未填写）';
      console.log(`\n${C.cyan}──── 提示词 ────${C.reset}`);
      console.log(`你是一位与作者合写的小说作者。请续写下一段情节。\n\n【设定】\n${chars}\n\n【上一章结尾】\n${prev}\n\n【本章已有正文】\n${ch.text || '（当前章为空）'}`);
    } else if (op === '7') {
      const chapters = lib.chapters;
      console.log(`章节数: ${chapters.length}`);
      console.log(`总字数: ${chapters.reduce((s,c)=>s+(c.word_count||0),0)}`);
      console.log(`总字符: ${chapters.reduce((s,c)=>s+[...(c.text||'')].length,0)}`);
    }

    save(path, lib);
  }

  rl.close();
  console.log(`\n已保存至 ${path}`);
}

main();
