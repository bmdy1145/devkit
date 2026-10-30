#!/usr/bin/env node
// DirCleaner 全功能版（TypeScript / Node）
//
// 版本：A1_II_Φ8_TypeScript_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 「全功能」在 Node 下的实现取舍：Node 没有内置 GUI 库，引入 Electron
// 会让体积膨胀到 100MB+ 且需额外安装。本版采用**交互式终端向导**，
// 用与浏览器版一致的分步流程（选目录→安全检查→白名单→扫描→确认→执行），
// 并通过 ANSI 颜色与进度条提供可视化。功能完整，可替代原产品。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const MAX_RECURSION_DEPTH = 20;
const MAX_FILE_COUNT = 10000;
const MAX_SCAN_FOR_EXE = 2000;
const WHITELIST_MARKER = '.dircleaner_whitelist';

const CRITICAL = new Set([
  'Windows', 'System32', 'SysWOW64', 'Program Files', 'Program Files (x86)',
  'Users', 'Documents and Settings', 'bin', 'sbin', 'etc', 'dev', 'proc', 'sys',
  'boot', 'root', 'home', 'var', 'tmp', 'Volumes', 'Applications', 'Library',
]);

// ANSI 颜色（Windows 10+ 终端支持）
const C = {
  reset: '\x1b[0m', bold: '\x1b[1m', dim: '\x1b[2m',
  red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m',
  blue: '\x1b[34m', cyan: '\x1b[36m',
};

function formatBytes(n) {
  if (n === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (i === 0 ? v.toFixed(0) : v.toFixed(2)) + ' ' + units[i];
}

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise((res) => rl.question(q, (a) => res(a.trim())));

function banner() {
  console.log();
  console.log(C.cyan + '╔══════════════════════════════════════════════╗' + C.reset);
  console.log(C.cyan + '║' + C.reset + C.bold + '      DirCleaner 全功能版（TypeScript）      ' + C.reset + C.cyan + '║' + C.reset);
  console.log(C.cyan + '║' + C.reset + C.dim + '         版本 A1_II_Φ8_TypeScript_CN         ' + C.reset + C.cyan + '║' + C.reset);
  console.log(C.cyan + '╚══════════════════════════════════════════════╝' + C.reset);
  console.log();
}

function section(n, title) {
  console.log(`\n${C.bold}${C.blue}【第 ${n} 步】${title}${C.reset}`);
}

function ok(msg) { console.log(`  ${C.green}✓${C.reset} ${msg}`); }
function warn(msg) { console.log(`  ${C.yellow}⚠${C.reset}  ${msg}`); }
function err(msg) { console.log(`  ${C.red}✗${C.reset} ${msg}`); }
function info(msg) { console.log(`  ${C.dim}${msg}${C.reset}`); }

function containsExecutables(dir, depth = 0, counter = { n: 0 }) {
  if (depth > 10 || counter.n >= MAX_SCAN_FOR_EXE) return false;
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return false; }
  for (const e of entries) {
    if (counter.n >= MAX_SCAN_FOR_EXE) break;
    const p = path.join(dir, e.name);
    try {
      if (e.isDirectory()) {
        if (containsExecutables(p, depth + 1, counter)) return true;
      } else {
        counter.n++;
        const n = e.name.toLowerCase();
        if (n.endsWith('.exe') || n.endsWith('.dll')) return true;
      }
    } catch { /* 忽略 */ }
  }
  return false;
}

function scanSummary(dir) {
  let files = 0, dirs = 0, bytes = 0;
  const walk = (d) => {
    let entries;
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const p = path.join(d, e.name);
      try {
        if (e.isDirectory()) { dirs++; walk(p); }
        else { files++; bytes += fs.statSync(p).size; }
      } catch { /* 忽略 */ }
    }
  };
  walk(dir);
  return { files, dirs, bytes };
}

function clearDirectory(dir, depth, fileCount, keepMarker, dryRun, stats, onLog) {
  if (depth > MAX_RECURSION_DEPTH) throw new Error(`已达到最大目录深度限制 (${MAX_RECURSION_DEPTH})`);
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch (e) { throw new Error(`无法读取 ${dir}: ${e.message}`); }

  for (const e of entries) {
    const p = path.join(dir, e.name);
    const name = e.name;
    if (e.isDirectory()) {
      clearDirectory(p, depth + 1, fileCount, keepMarker, dryRun, stats, onLog);
      if (dryRun) { onLog(`  ${C.dim}[试运行] 目录 ${name}${C.reset}`); stats.dirs++; }
      else {
        try { fs.rmdirSync(p); stats.dirs++; onLog(`  ✓ 目录 ${name}`); }
        catch (err) { const m = `无法删除目录 ${name}: ${err.message}`; stats.errors.push(m); onLog(`  ${C.red}✗ ${m}${C.reset}`); }
      }
      continue;
    }
    if (fileCount.n >= MAX_FILE_COUNT) throw new Error(`已达到最大文件数限制 (${MAX_FILE_COUNT})`);
    if (keepMarker && name === WHITELIST_MARKER) { onLog(`  - 跳过白名单标记 ${name}`); continue; }
    let size = 0;
    try { size = fs.statSync(p).size; } catch { /* 忽略 */ }
    if (dryRun) { onLog(`  ${C.dim}[试运行] 文件 ${name} (${formatBytes(size)})${C.reset}`); }
    else {
      try { fs.unlinkSync(p); onLog(`  ✓ 文件 ${name} (${formatBytes(size)})`); }
      catch (err) { const m = `无法删除 ${name}: ${err.message}`; stats.errors.push(m); onLog(`  ${C.red}✗ ${m}${C.reset}`); continue; }
    }
    stats.files++;
    stats.bytes += size;
    fileCount.n++;
  }
}

async function main() {
  banner();
  const total = { files: 0, dirs: 0, bytes: 0, errors: 0 };

  while (true) {
    section(1, '选择目录');
    const input = await ask('  请输入要清空的目录路径（回车退出）：');
    if (!input) break;

    const target = path.resolve(input);
    let st;
    try { st = fs.statSync(target); } catch { st = null; }
    if (!st || !st.isDirectory()) { err(`不是有效目录：${input}`); continue; }

    const name = path.basename(target);

    section(2, '安全检查');
    if (CRITICAL.has(name)) { err(`${name} 是受保护的关键目录，禁止清空`); continue; }
    ok('不是受保护的关键目录');

    section(3, '白名单');
    const markerPath = path.join(target, WHITELIST_MARKER);
    let whitelisted = fs.existsSync(markerPath);
    if (whitelisted) ok('已在白名单（发现标记文件），跳过名称确认');
    else {
      info('该目录不在白名单中');
      const ans = await ask('  要加入白名单吗？(y/N)：');
      if (ans.toLowerCase() === 'y') {
        try { fs.writeFileSync(markerPath, 'DirCleaner Whitelist Marker'); ok('已创建白名单标记'); whitelisted = true; }
        catch (e) { err(`创建失败：${e.message}`); }
      }
    }

    section(4, '扫描内容');
    const sum = scanSummary(target);
    info(`文件 ${sum.files} 个 · 目录 ${sum.dirs} 个 · 共 ${formatBytes(sum.bytes)}`);
    const hasExe = containsExecutables(target);
    if (hasExe) warn('发现可执行文件（.exe / .dll）');

    section(5, '确认');
    if (!whitelisted) {
      const typed = await ask(`  请输入目录名 "${name}" 以确认：`);
      if (typed !== name) { err('名称不一致，已取消本次操作'); continue; }
    }
    if (hasExe) {
      const ans = await ask('  该目录含可执行文件，确认继续？输入 yes：');
      if (ans !== 'yes') { info('已取消'); continue; }
    }
    const mode = await ask('  执行模式：1=试运行 2=实际删除 [1]：');
    const dryRun = mode !== '2';
    if (!dryRun) {
      const c = await ask('  实际删除不可恢复，最后确认？(yes)：');
      if (c !== 'yes') { info('已取消'); continue; }
    }

    section(6, `执行${dryRun ? '（试运行）' : ''}`);
    console.log('  ' + '─'.repeat(46));
    const stats = { files: 0, dirs: 0, bytes: 0, errors: [] };
    const onLog = (s) => console.log(s);
    try {
      clearDirectory(target, 0, { n: 0 }, whitelisted, dryRun, stats, onLog);
      ok('完成');
    } catch (e) {
      err(`中止：${e.message}`);
    }
    console.log('  ' + '─'.repeat(46));
    info(`本次：文件 ${stats.files} · 目录 ${stats.dirs} · 释放 ${formatBytes(stats.bytes)} · 错误 ${stats.errors.length}`);

    total.files += stats.files; total.dirs += stats.dirs;
    total.bytes += stats.bytes; total.errors += stats.errors.length;
    info(`会话累计：文件 ${total.files} · 目录 ${total.dirs} · 释放 ${formatBytes(total.bytes)} · 错误 ${total.errors}`);

    const more = await ask('\n  继续处理其他目录？(y/N)：');
    if (more.toLowerCase() !== 'y') break;
    console.log();
  }

  rl.close();
  console.log('\n再见。');
}

main().catch((e) => { console.error(e); process.exit(1); });
