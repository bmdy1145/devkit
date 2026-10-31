#!/usr/bin/env node
// Writer 内核版（TypeScript / Node）
//
// 版本：A1_I_Φ5_TypeScript_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html
//
// 只实现纯逻辑内核：书籍 / 卷 / 章节结构的 JSON 持久化、字数统计、
// 章节排序、跨卷移动、引用管理、提示词模板合成。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');

let counter = 0;
const genId = (prefix) => `${prefix}_${Date.now()}_${++counter}`;
const nowTs = () => Date.now();

// 与浏览器版一致：CJK 每字算 1 词，拉丁词按整词算。
const RE_CJK = /[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\uF900-\uFAFF]/g;
const RE_WORD = /[A-Za-z0-9]+(?:['\u2019-][A-Za-z0-9]+)*/g;

function countWords(text) {
  if (!text) return 0;
  const cjk = text.match(RE_CJK);
  const words = text.match(RE_WORD);
  return (cjk ? cjk.length : 0) + (words ? words.length : 0);
}

function load(p) {
  const empty = { books: [], volumes: [], chapters: [], entities: [] };
  if (!fs.existsSync(p)) return empty;
  const raw = fs.readFileSync(p, 'utf8').trim();
  if (!raw) return empty;
  const data = JSON.parse(raw);
  return {
    books: data.books || [],
    volumes: data.volumes || [],
    chapters: data.chapters || [],
    entities: data.entities || [],
  };
}

const save = (p, lib) => fs.writeFileSync(p, JSON.stringify(lib, null, 2), 'utf8');

const chaptersOf = (lib, volId) =>
  lib.chapters.filter((c) => c.volume_id === volId).sort((a, b) => a.order - b.order);

function reorderVolume(lib, volId) {
  chaptersOf(lib, volId).forEach((c, i) => { c.order = i; });
}

// 人称转换的目标人称。key 与 --target 取值、HTML 版 A1_I_Φ5_CN 的
// #povTarget option value 一一对应。
const POV_TARGETS = {
  first: '第一人称（我）',
  second: '第二人称（你）',
  third: '第三人称（他 / 她 / 它）',
};

// 合成「人称转换」提示词，与 HTML 版 A1_I_Φ5_CN 的 pov 模板一致。
function buildPovPrompt(body, chars, target, keepInner) {
  const inner = keepInner
    ? '保留：原视角的内心活动改写为目标视角可知的部分（用表情、动作、语气或外部观察替代直接叙述他人内心）'
    : '不保留：删去目标视角无法感知的心理描写，只保留外在可见的行为与对白';
  return [
    `你是一位精通叙述视角的小说编辑。请把下面的正文转换为【${target}】，情节、人物、场景与对白内容一律不变，只换叙述人称与视角。`,
    '',
    `【目标人称】${target}`,
    '',
    `【心理描写处理】${inner}`,
    '',
    '【相关设定】',
    chars,
    '',
    '【需要转换的正文】',
    body,
    '',
    '【转换规则】',
    '1) 只改人称代词与由此引起的视角变化，不增删情节、不改变人物性格与说话方式；',
    '2) 第一人称：叙述者用「我」，只能写出「我」能感知到的内容（看到、听到、想到），不能直接叙述旁人心里在想什么；',
    '3) 第二人称：叙述者用「你」，把读者带入场景，动作与感受都落在「你」身上；',
    '4) 第三人称：叙述者用「他 / 她 / 它」或人物姓名，人物之间用姓名或称谓区分，避免代词指向不明；',
    '5) 时间线、场景顺序、对白内容保持原样，对白中人物自称按其在故事中的实际人称调整；',
    '6) 转换后通读一遍，确保没有残留的原人称代词、没有视角越界、没有半途切换人称。',
    '',
    '【输出要求】直接输出转换后的完整正文，不要加解释、不要加标题、不要用「以下是」之类的开场白，便于直接替换当前章。',
  ].join('\n');
}

function usage() {
  console.log('Writer 内核版（TypeScript / Node）');
  console.log('用法: writer.js <库文件.json> <子命令> [参数]');
  console.log('');
  console.log('子命令:');
  console.log('  init <书名>');
  console.log('  add-volume <书籍ID> <卷名>');
  console.log('  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]');
  console.log('  list <书籍ID>');
  console.log('  stats <书籍ID>');
  console.log('  move-chapter <章节ID> <目标卷ID>');
  console.log('  add-entity <书籍ID> <名称> [类型] [描述]');
  console.log('  prompt <书籍ID> <章节ID>');
  console.log('  pov <书籍ID> <章节ID> [--target first|second|third] [--no-inner]');
  console.log('  reindex <书籍ID>');
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.length < 2) { usage(); return 1; }

  const libPath = argv[0];
  const cmd = argv[1];
  const args = argv.slice(2);
  const lib = load(libPath);

  switch (cmd) {
    case 'init': {
      if (!args.length) { console.error('缺少书名'); return 1; }
      const b = { id: genId('book'), title: args[0], author: '', updated_at: nowTs() };
      console.log(`已创建书籍: ${b.title} (${b.id})`);
      lib.books.push(b);
      break;
    }
    case 'add-volume': {
      if (args.length < 2) { console.error('缺少参数'); return 1; }
      const [bookId, title] = args;
      if (!lib.books.some((b) => b.id === bookId)) { console.error(`找不到书籍 ${bookId}`); return 1; }
      const order = lib.volumes.filter((v) => v.book_id === bookId).length;
      const v = { id: genId('vol'), book_id: bookId, title, order };
      console.log(`已新增卷: ${v.title} (${v.id})`);
      lib.volumes.push(v);
      break;
    }
    case 'add-chapter': {
      if (args.length < 3) { console.error('缺少参数'); return 1; }
      const [bookId, volId, title] = args;
      let text = '';
      if (args[3] && fs.existsSync(args[3])) text = fs.readFileSync(args[3], 'utf8');
      if (!lib.volumes.some((v) => v.id === volId)) { console.error(`找不到卷 ${volId}`); return 1; }
      const order = lib.chapters.filter((c) => c.volume_id === volId).length;
      const wc = countWords(text);
      const ch = {
        id: genId('ch'), book_id: bookId, volume_id: volId,
        title, order, word_count: wc, updated_at: nowTs(), text,
      };
      console.log(`已新增章节: ${ch.title} (${ch.id}) · ${wc} 字`);
      lib.chapters.push(ch);
      break;
    }
    case 'list': {
      if (!args.length) { console.error('缺少书籍ID'); return 1; }
      const book = lib.books.find((b) => b.id === args[0]);
      if (!book) { console.error('找不到书籍'); return 1; }
      console.log(`书籍: ${book.title} (${book.id})`);
      lib.volumes.filter((v) => v.book_id === book.id)
        .sort((a, b) => a.order - b.order)
        .forEach((v) => {
          console.log(`  卷: ${v.title} (order ${v.order})`);
          chaptersOf(lib, v.id).forEach((c) => {
            console.log(`    - [${c.order}] ${c.title} · ${c.word_count} 字`);
          });
        });
      break;
    }
    case 'stats': {
      if (!args.length) { console.error('缺少书籍ID'); return 1; }
      const chs = lib.chapters.filter((c) => c.book_id === args[0]);
      console.log(`章节数: ${chs.length}`);
      console.log(`总字数: ${chs.reduce((s, c) => s + (c.word_count || 0), 0)}`);
      console.log(`总字符: ${chs.reduce((s, c) => s + [...(c.text || '')].length, 0)}`);
      break;
    }
    case 'move-chapter': {
      if (args.length < 2) { console.error('缺少参数'); return 1; }
      const [chId, targetVol] = args;
      const ch = lib.chapters.find((c) => c.id === chId);
      if (!ch) { console.error('找不到章节'); return 1; }
      if (!lib.volumes.some((v) => v.id === targetVol)) { console.error(`找不到目标卷 ${targetVol}`); return 1; }
      const sourceVol = ch.volume_id;
      ch.volume_id = targetVol;
      ch.order = lib.chapters.filter((c) => c.volume_id === targetVol).length;
      reorderVolume(lib, targetVol);
      reorderVolume(lib, sourceVol);
      console.log('已将章节移至目标卷，并重排源卷与目标卷的顺序');
      break;
    }
    case 'add-entity': {
      if (args.length < 2) { console.error('缺少参数'); return 1; }
      const [bookId, name] = args;
      const e = {
        id: genId('ent'), book_id: bookId, name,
        kind: args[2] || '其他', description: args[3] || '',
      };
      console.log(`已添加资料: ${e.name} (${e.id})`);
      lib.entities.push(e);
      break;
    }
    case 'prompt': {
      if (args.length < 2) { console.error('缺少参数'); return 1; }
      const [bookId, chId] = args;
      const ch = lib.chapters.find((c) => c.id === chId);
      if (!ch) { console.error('找不到章节'); return 1; }
      const lst = chaptersOf(lib, ch.volume_id);
      const pos = lst.findIndex((c) => c.id === chId);
      const prev = pos > 0 ? (lst[pos - 1].text || '').slice(-500) : '（本章为卷首，无上一章）';
      const ents = lib.entities.filter((e) => e.book_id === bookId);
      const chars = ents.length
        ? ents.map((e) => `- ${e.name}（${e.kind}）：${e.description}`).join('\n')
        : '（未填写）';
      console.log('你是一位与作者合写的小说作者。请续写下一段情节。');
      console.log('');
      console.log('【设定】');
      console.log(chars);
      console.log('【上一章结尾】');
      console.log(prev);
      console.log('');
      console.log('【本章已有正文】');
      console.log(ch.text || '（当前章为空）');
      break;
    }
    case 'pov': {
      if (args.length < 2) { console.error('缺少参数'); return 1; }
      const [bookId, chId] = args;
      let targetKey = 'third';
      let keepInner = true;
      for (let i = 2; i < args.length; i += 1) {
        const a = args[i];
        if (a === '--target') {
          if (i + 1 >= args.length) { console.error('--target 缺少取值'); return 1; }
          targetKey = args[i + 1];
          i += 1;
        } else if (a === '--no-inner') {
          keepInner = false;
        } else {
          console.error(`无法识别的参数: ${a}`);
          return 1;
        }
      }
      const target = POV_TARGETS[targetKey];
      if (!target) {
        console.error(`目标人称无效：${targetKey}（可选 first / second / third）`);
        return 1;
      }
      const ch = lib.chapters.find((c) => c.id === chId);
      if (!ch) { console.error('找不到章节'); return 1; }
      const ents = lib.entities.filter((e) => e.book_id === bookId);
      const chars = ents.length
        ? ents.map((e) => `- ${e.name}（${e.kind}）：${e.description}`).join('\n')
        : '（未填写）';
      console.log(buildPovPrompt(ch.text || '（当前章为空）', chars, target, keepInner));
      break;
    }
    case 'reindex': {
      if (!args.length) { console.error('缺少书籍ID'); return 1; }
      lib.volumes.filter((v) => v.book_id === args[0]).forEach((v) => reorderVolume(lib, v.id));
      console.log('已重排全部卷的章节顺序');
      break;
    }
    default:
      console.error(`未知子命令: ${cmd}`);
      return 1;
  }

  save(libPath, lib);
  return 0;
}

process.exit(main());
