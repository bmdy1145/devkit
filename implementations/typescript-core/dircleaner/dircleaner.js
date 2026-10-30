#!/usr/bin/env node
// DirCleaner 内核版（TypeScript / Node）
//
// 版本：A1_II_Φ8_TypeScript_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。
// 本文件是纯 JavaScript（无 TS 编译步骤），便于用 Node SEA 直接打包成 EXE。
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
const WHITELIST_MARKER_FILENAME = '.dircleaner_whitelist';

const CRITICAL_DIR_NAMES = new Set([
  'Windows', 'System32', 'SysWOW64', 'Program Files', 'Program Files (x86)',
  'Users', 'Documents and Settings', 'bin', 'sbin', 'etc', 'dev', 'proc', 'sys',
  'boot', 'root', 'home', 'var', 'tmp', 'Volumes', 'Applications', 'Library',
]);

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (i === 0 ? v.toFixed(0) : v.toFixed(2)) + ' ' + units[i];
}

function containsExecutables(dir, depth = 0, counter = { count: 0 }) {
  if (depth > 10 || counter.count >= MAX_SCAN_FOR_EXE) return false;
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch (e) { return false; }
  for (const e of entries) {
    if (counter.count >= MAX_SCAN_FOR_EXE) break;
    const p = path.join(dir, e.name);
    try {
      if (e.isDirectory()) {
        if (containsExecutables(p, depth + 1, counter)) return true;
      } else {
        counter.count++;
        const n = e.name.toLowerCase();
        if (n.endsWith('.exe') || n.endsWith('.dll')) return true;
      }
    } catch (err) { /* 忽略无法访问的条目 */ }
  }
  return false;
}

function clearDirectory(dir, depth, fileCount, keepMarker, dryRun, stats) {
  if (depth > MAX_RECURSION_DEPTH) {
    throw new Error(`已达到最大目录深度限制 (${MAX_RECURSION_DEPTH})`);
  }
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch (e) { throw new Error(`无法读取 ${dir}: ${e.message}`); }

  for (const e of entries) {
    const p = path.join(dir, e.name);
    const name = e.name;
    if (e.isDirectory()) {
      clearDirectory(p, depth + 1, fileCount, keepMarker, dryRun, stats);
      if (dryRun) {
        console.log(`[dry-run] 将删除目录: ${name}`);
        stats.deletedDirs++;
      } else {
        try {
          fs.rmdirSync(p);
          console.log(`已删除目录: ${name}`);
          stats.deletedDirs++;
        } catch (err) {
          const msg = `无法删除目录 ${name}: ${err.message}`;
          stats.errors.push(msg);
          console.error(msg);
        }
      }
      continue;
    }
    if (fileCount.count >= MAX_FILE_COUNT) {
      throw new Error(`已达到最大文件数限制 (${MAX_FILE_COUNT})`);
    }
    if (keepMarker && name === WHITELIST_MARKER_FILENAME) {
      console.log(`跳过白名单标记文件: ${name}`);
      continue;
    }
    let size = 0;
    try { size = fs.statSync(p).size; } catch (err) { /* 忽略 */ }
    if (dryRun) {
      console.log(`[dry-run] 将删除文件: ${name} (${formatBytes(size)})`);
    } else {
      try {
        fs.unlinkSync(p);
        console.log(`已删除文件: ${name} (${formatBytes(size)})`);
      } catch (err) {
        const msg = `无法删除 ${name}: ${err.message}`;
        stats.errors.push(msg);
        console.error(msg);
        continue;
      }
    }
    stats.deletedFiles++;
    stats.totalBytes += size;
    fileCount.count++;
  }
}

function parseArgs(argv) {
  const opts = { target: null, dryRun: false, whitelist: false, confirm: '' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--whitelist') opts.whitelist = true;
    else if (a === '--confirm') { opts.confirm = argv[++i] || ''; }
    else if (a === '-h' || a === '--help') { opts.help = true; }
    else if (!a.startsWith('-') && !opts.target) opts.target = a;
  }
  return opts;
}

function usage() {
  console.log('DirCleaner 内核版（TypeScript / Node）');
  console.log('用法: dircleaner <目录> [选项]');
  console.log('');
  console.log('选项:');
  console.log('  --dry-run          只列出将删除的内容，不实际删除');
  console.log('  --whitelist        该目录在白名单中（保留标记文件，跳过名称确认）');
  console.log('  --confirm <名称>   确认待清空目录的名称（非白名单目录必须提供且一致）');
  console.log('  -h, --help         显示本帮助');
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help || !opts.target) { usage(); return opts.help ? 0 : 1; }

  const target = opts.target;
  let st;
  try { st = fs.statSync(target); } catch (e) { st = null; }
  if (!st || !st.isDirectory()) {
    console.error(`错误：${target} 不是目录`);
    return 1;
  }

  const dirName = path.basename(path.resolve(target));
  if (CRITICAL_DIR_NAMES.has(dirName)) {
    console.error(`错误：${dirName} 是受保护的关键目录，禁止清空`);
    return 1;
  }
  if (!opts.whitelist) {
    if (!opts.confirm) {
      console.error(`错误：非白名单目录必须用 --confirm "${dirName}" 确认`);
      return 1;
    }
    if (opts.confirm !== dirName) {
      console.error(`错误：确认名称 "${opts.confirm}" 与目录名 "${dirName}" 不一致`);
      return 1;
    }
  }

  if (containsExecutables(target)) {
    console.log('⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。');
    const ans = await new Promise((resolve) => {
      const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
      rl.question('确认继续？输入 yes: ', (a) => { rl.close(); resolve(a); });
    });
    if (ans.trim() !== 'yes') { console.log('已取消。'); return 1; }
  }

  console.log('===== 开始清空操作 =====');
  console.log(`目标目录: ${target}`);
  if (opts.dryRun) console.log('模式: 试运行（不实际删除）');

  const stats = { deletedFiles: 0, deletedDirs: 0, totalBytes: 0, errors: [] };
  try {
    clearDirectory(target, 0, { count: 0 }, opts.whitelist, opts.dryRun, stats);
  } catch (e) {
    console.error(`操作中止: ${e.message}`);
    console.log(`已删除文件: ${stats.deletedFiles}，目录: ${stats.deletedDirs}，释放空间: ${formatBytes(stats.totalBytes)}`);
    return 1;
  }

  console.log('===== 清空完成 =====');
  console.log(`本次删除文件: ${stats.deletedFiles}`);
  console.log(`本次删除目录: ${stats.deletedDirs}`);
  console.log(`本次释放空间: ${formatBytes(stats.totalBytes)}`);
  if (stats.errors.length) {
    console.log(`错误数: ${stats.errors.length}`);
    stats.errors.forEach((e) => console.log('  ' + e));
    return 1;
  }
  return 0;
}

main().then((code) => process.exit(code));
