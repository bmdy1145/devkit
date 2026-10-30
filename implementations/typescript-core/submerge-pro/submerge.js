#!/usr/bin/env node
// SubMerge Pro 内核版（TypeScript / Node）
//
// 版本：A1_II_Φ10_TypeScript_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');

const CJK_SPLIT = /([\u4e00-\u9fff]+)/;
const CJK_TEST = /[\u4e00-\u9fff]/;
const TIME_RE = /^(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})$/;
const IDX_RE = /^\[(\d+)\]\s*(.*)$/;

const isCjk = (ch) => ch >= '\u4e00' && ch <= '\u9fff';

function countWords(text) {
  if (!text) return 0;
  let total = 0;
  for (const seg of text.split(CJK_SPLIT)) {
    if (!seg) continue;
    if (CJK_TEST.test(seg)) total += Math.ceil(seg.length / 2);
    else total += (seg.match(/[A-Za-z0-9]+(?:'[A-Za-z]+)?/g) || []).length;
  }
  return total;
}

function tokenize(text) {
  const tokens = [];
  for (const seg of text.split(CJK_SPLIT)) {
    if (!seg) continue;
    if (CJK_TEST.test(seg)) {
      for (let i = 0; i < seg.length; i += 2) tokens.push(seg.substring(i, i + 2));
    } else {
      tokens.push(...(seg.match(/[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S/g) || []));
    }
  }
  return tokens;
}

function joinTokens(tokens) {
  let out = '';
  tokens.forEach((tok, i) => {
    if (i > 0) {
      const p = tokens[i - 1][tokens[i - 1].length - 1];
      const c = tok[0];
      if (!isCjk(p) && !isCjk(c)) out += ' ';
    }
    out += tok;
  });
  return out;
}

function addBoundary(s) {
  return s
    .replace(/([a-zA-Z0-9])([\u4e00-\u9fff])/g, '$1 $2')
    .replace(/([\u4e00-\u9fff])([a-zA-Z0-9])/g, '$1 $2');
}

function splitPaired(orig, trans, maxWords = 10) {
  if (!orig && !trans) return [{ orig: '', trans: '' }];
  const o = tokenize(orig);
  const t = tokenize(trans);
  const chunks = [];
  let oi = 0, ti = 0;
  while (oi < o.length || ti < t.length) {
    const oc = [], tc = [];
    let words = 0;
    while ((oi < o.length || ti < t.length) && words < maxWords) {
      const canO = oi < o.length, canT = ti < t.length;
      if (canO && canT) {
        if (words + 2 <= maxWords) { oc.push(o[oi++]); tc.push(t[ti++]); words += 2; }
        else break;
      } else if (canO) {
        if (words + 1 <= maxWords) { oc.push(o[oi++]); words++; } else break;
      } else if (canT) {
        if (words + 1 <= maxWords) { tc.push(t[ti++]); words++; } else break;
      }
    }
    chunks.push({
      orig: addBoundary(joinTokens(oc)).trim(),
      trans: addBoundary(joinTokens(tc)).trim(),
    });
  }
  return chunks.length ? chunks : [{ orig, trans }];
}

function timeToMs(s, fps = 25) {
  const parts = s.split(':');
  if (parts.length !== 3) return 0;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const sp = parts[2];
  let sec, ms;
  if (sp.includes(',')) {
    const [a, b] = sp.split(',');
    sec = parseInt(a, 10);
    ms = parseInt((b + '000').slice(0, 3), 10);
  } else if (sp.includes('.')) {
    const [a, b] = sp.split('.');
    sec = parseInt(a, 10);
    ms = Math.round(parseInt((b + '00').slice(0, 2), 10) * (1000 / fps));
  } else {
    sec = parseInt(sp, 10);
    ms = 0;
  }
  return (h * 3600 + m * 60 + sec) * 1000 + ms;
}

function msToTime(ms) {
  const h = Math.floor(ms / 3600000); ms %= 3600000;
  const m = Math.floor(ms / 60000); ms %= 60000;
  const s = Math.floor(ms / 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`;
}

function parseSubtitle(content) {
  const clean = content.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const entries = [];
  const seen = new Set();
  for (const raw of clean.split(/\n\s*\n/)) {
    const lines = raw.split('\n').map((l) => l.trim()).filter((l) => l);
    if (lines.length < 3 || !/^\d+$/.test(lines[0])) continue;
    const m = lines[1].match(TIME_RE);
    if (!m) continue;
    const index = parseInt(lines[0], 10);
    if (seen.has(index)) continue;
    seen.add(index);
    const start = m[1].replace('.', ',');
    let end = m[2].replace('.', ',');
    if (timeToMs(start) >= timeToMs(end)) end = msToTime(timeToMs(start) + 1);
    const text = lines.slice(2).join('\n').trim();
    if (!text) continue;
    entries.push({ index, start, end, text, translated: null });
  }
  entries.sort((a, b) => a.index - b.index);
  return entries;
}

function applyTimeFix(entries, strategy) {
  if (strategy === 'keep') return entries;
  if (strategy === 'delete') {
    return entries.filter((e) => timeToMs(e.end) - timeToMs(e.start) >= 10);
  }
  if (strategy === 'extend') {
    for (let i = 0; i < entries.length; i++) {
      const s = timeToMs(entries[i].start);
      const e = timeToMs(entries[i].end);
      if (e - s < 10) {
        const newEnd = s + 10;
        entries[i].end = msToTime(newEnd);
        const shift = newEnd - e;
        for (let j = i + 1; j < entries.length; j++) {
          entries[j].start = msToTime(timeToMs(entries[j].start) + shift);
          entries[j].end = msToTime(timeToMs(entries[j].end) + shift);
        }
      }
    }
  }
  return entries;
}

function applyTranslation(entries, transStr) {
  const map = new Map();
  let cur = null, buf = [];
  const flush = () => { if (cur !== null) map.set(cur, buf.join('\n').trim()); };
  for (const line of transStr.split('\n')) {
    const t = line.trim();
    const m = t.match(IDX_RE);
    if (m) {
      flush();
      cur = parseInt(m[1], 10);
      buf = m[2].trim() ? [m[2].trim()] : [];
      continue;
    }
    if (cur !== null && t) buf.push(t);
  }
  flush();
  let applied = 0;
  for (const e of entries) {
    if (map.has(e.index)) { e.translated = map.get(e.index); applied++; }
  }
  return applied;
}

function exportSrt(entries, mode) {
  let out = '';
  for (const e of entries) {
    let text;
    if (mode === 'orig') text = e.text;
    else if (mode === 'trans') text = e.translated || '';
    else {
      if (e.translated && e.text) text = `${e.text}\n${e.translated}`;
      else if (e.translated) text = e.translated;
      else text = e.text;
    }
    out += `${e.index}\n${e.start} --> ${e.end}\n${text}\n\n`;
  }
  return out;
}

function usage() {
  console.log('SubMerge Pro 内核版（TypeScript / Node）');
  console.log('用法:');
  console.log('  submerge parse <字幕文件>');
  console.log('  submerge export <字幕文件> [--trans 译文] [--mode both|orig|trans] [--time-fix keep|delete|extend]');
  console.log('  submerge merge-prompt <字幕文件> [--trans 译文] [--max N]');
}

function main() {
  const argv = process.argv.slice(2);
  if (!argv.length || argv[0] === '-h' || argv[0] === '--help') {
    usage();
    return argv.length ? 0 : 1;
  }
  const cmd = argv[0];
  let file = null, transFile = null, mode = 'both', timeFix = 'keep', maxWords = 10;

  for (let i = 1; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--trans') transFile = argv[++i];
    else if (a === '--mode') mode = argv[++i];
    else if (a === '--time-fix') timeFix = argv[++i];
    else if (a === '--max') maxWords = parseInt(argv[++i], 10) || 10;
    else if (!a.startsWith('--') && !file) file = a;
  }

  if (!file) { console.error('错误：未指定字幕文件'); return 1; }

  let content;
  try { content = fs.readFileSync(file, 'utf8'); }
  catch (e) { console.error(`无法读取 ${file}: ${e.message}`); return 1; }

  let entries = parseSubtitle(content);
  if (!entries.length) { console.error('解析失败：未找到字幕条目'); return 1; }
  entries = applyTimeFix(entries, timeFix);

  if (transFile) {
    try {
      const n = applyTranslation(entries, fs.readFileSync(transFile, 'utf8'));
      console.log(`已应用 ${n} 条译文`);
    } catch (e) { console.error(`无法读取 ${transFile}: ${e.message}`); return 1; }
  }

  if (cmd === 'parse') {
    const total = entries.reduce((s, e) => s + countWords(e.text), 0);
    console.log(`条目数: ${entries.length}`);
    console.log(`总词数: ${total}`);
    const f = entries[0], l = entries[entries.length - 1];
    console.log(`首条: [${f.index}] ${f.start} --> ${f.end} | ${f.text}`);
    console.log(`末条: [${l.index}] ${l.start} --> ${l.end} | ${l.text}`);
  } else if (cmd === 'export') {
    process.stdout.write(exportSrt(entries, mode));
  } else if (cmd === 'merge-prompt') {
    for (const e of entries) {
      for (const c of splitPaired(e.text, e.translated || '', maxWords)) {
        const body = c.trans ? `${c.orig}\n${c.trans}` : c.orig;
        console.log(`[${e.index}] ${body.trim()}`);
      }
    }
  } else {
    console.error(`错误：未知子命令 ${cmd}`);
    usage();
    return 1;
  }
  return 0;
}

process.exit(main());
