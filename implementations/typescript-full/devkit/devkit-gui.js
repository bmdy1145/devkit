#!/usr/bin/env node
// DevKit 全功能版（TypeScript / Node）
//
// 版本：A1_V_Φ9_Fix_TypeScript_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// Node 无内置 GUI，本版用交互式终端界面：项目/页签、灵感与代码、预览复制、
// 配置导入导出、九款主题切换（与合并版 HTML 的主题切换等价）。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');
const readline = require('readline');

const C = { reset:'\x1b[0m', bold:'\x1b[1m', dim:'\x1b[2m',
  red:'\x1b[31m', green:'\x1b[32m', yellow:'\x1b[33m', blue:'\x1b[34m', cyan:'\x1b[36m' };

const CURRENT_VERSION = 'A1_V_Φ9_Fix_TypeScript_CN';

const THEMES = ['Clean','Glass','Neon','Mono','Material','Minimal','Premium','Shadcn','Baseline'];

const TEMPLATES = [
  ['版本规划','你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。'],
  ['需求分析','你是一位资深系统分析师。请对下面需求做全面分析。'],
  ['安全审计','你是一位持有 OSCP 认证的安全专家。请审计下面的代码。'],
  ['性能审计','你是一位性能优化专家。请审计下面的代码。'],
  ['结构重构','你是一位资深架构师。请重构下面的代码。'],
  ['单元测试','请为下面的代码编写单元测试。'],
  ['空白',''],
];

let ctr = 0;
const genId = (p) => `${p}_${Date.now()}_${++ctr}`;

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise((r) => rl.question(q, (a) => r(a.trim())));

function defaultState() {
  return {
    version: CURRENT_VERSION,
    activeProjectId: 'proj_1',
    projects: [{
      id: 'proj_1', name: '默认项目',
      tabs: TEMPLATES.map(([n]) => ({ id: genId('tab'), type: n, inspiration: '' })),
      code: '', result: '',
    }],
    settings: { theme: 'Clean' },
  };
}

function compose(state, tabIdx) {
  const proj = state.projects.find((p) => p.id === state.activeProjectId);
  if (!proj) return '';
  const tab = proj.tabs[tabIdx];
  if (!tab) return '';
  const tpl = TEMPLATES.find(([n]) => n === tab.type);
  const head = tpl && tpl[1] ? tpl[1] + '\n\n' : '';
  return `${head}需求：${tab.inspiration || '（无需求）'}\n\n代码：\n${proj.code || '（无代码）'}`;
}

async function main() {
  console.log(`\n${C.cyan}${C.bold}DevKit 全功能版（TypeScript）${C.reset}`);
  const path = await ask('配置文件路径（回车默认 devkit_config.json）：') || 'devkit_config.json';

  let state;
  if (fs.existsSync(path)) {
    try { state = JSON.parse(fs.readFileSync(path, 'utf8')); }
    catch (e) { state = defaultState(); }
    if (!state.projects) state = defaultState();
  } else {
    state = defaultState();
  }

  let tabIdx = 0;

  while (true) {
    const proj = state.projects.find((p) => p.id === state.activeProjectId);
    console.log(`\n${C.bold}项目：${proj.name}${C.reset} · 主题：${state.settings.theme}`);
    console.log(`${C.dim}页签：${proj.tabs.map((t, i) => `${i + 1}.${t.type}`).join('  ')}${C.reset}`);
    console.log(`${C.dim}当前：${proj.tabs[tabIdx].type} · 灵感 ${proj.tabs[tabIdx].inspiration.length} 字 · 代码 ${proj.code.length} 字符${C.reset}`);

    console.log(`\n${C.bold}操作${C.reset}  1=切页签 2=编辑灵感 3=编辑代码 4=预览 5=复制 6=切主题 7=新建项目 8=导出配置 9=导入配置 0=退出`);
    const op = await ask('选择：');

    if (op === '0') break;

    if (op === '1') {
      const i = parseInt(await ask('页签编号：'), 10) - 1;
      if (proj.tabs[i]) { tabIdx = i; console.log(`${C.green}✓${C.reset} 已切到 ${proj.tabs[i].type}`); }
    } else if (op === '2') {
      const text = await ask('灵感内容：');
      proj.tabs[tabIdx].inspiration = text;
      console.log(`${C.green}✓${C.reset} 已更新`);
    } else if (op === '3') {
      console.log(`${C.dim}输入代码（单行，空行结束）${C.reset}`);
      const lines = [];
      while (true) { const l = await ask(''); if (!l) break; lines.push(l); }
      if (lines.length) { proj.code = lines.join('\n'); console.log(`${C.green}✓${C.reset} 已更新 ${proj.code.length} 字符`); }
    } else if (op === '4') {
      console.log(`\n${C.cyan}──── 组合预览 ────${C.reset}`);
      console.log(compose(state, tabIdx));
    } else if (op === '5') {
      // 终端无法直接写剪贴板，改为写到临时文件并提示
      const tmp = `_clip_${Date.now()}.txt`;
      fs.writeFileSync(tmp, compose(state, tabIdx), 'utf8');
      console.log(`${C.green}✓${C.reset} 已写入 ${tmp}（可复制其内容）`);
    } else if (op === '6') {
      console.log(THEMES.map((t, i) => `${i + 1}.${t}`).join('  '));
      const i = parseInt(await ask('主题编号：'), 10) - 1;
      if (THEMES[i]) { state.settings.theme = THEMES[i]; console.log(`${C.green}✓${C.reset} 已切换到 ${THEMES[i]}`); }
    } else if (op === '7') {
      const name = await ask('项目名称：');
      if (name) {
        const np = { id: genId('proj'), name,
          tabs: TEMPLATES.map(([n]) => ({ id: genId('tab'), type: n, inspiration: '' })),
          code: '', result: '' };
        state.projects.push(np);
        state.activeProjectId = np.id;
        tabIdx = 0;
        console.log(`${C.green}✓${C.reset} 已新建 ${name}`);
      }
    } else if (op === '8') {
      state.version = CURRENT_VERSION;
      fs.writeFileSync(path, JSON.stringify(state, null, 2), 'utf8');
      console.log(`${C.green}✓${C.reset} 已导出到 ${path}`);
    } else if (op === '9') {
      const p = await ask('导入路径：');
      if (p && fs.existsSync(p)) {
        try {
          const d = JSON.parse(fs.readFileSync(p, 'utf8'));
          if (d.projects) {
            state = d;
            tabIdx = 0;
            console.log(`${C.green}✓${C.reset} 已导入 ${d.projects.length} 个项目`);
          } else console.log(`${C.red}格式错误：缺少 projects${C.reset}`);
        } catch (e) { console.log(`${C.red}读取失败：${e.message}${C.reset}`); }
      }
    }

    fs.writeFileSync(path, JSON.stringify(state, null, 2), 'utf8');
  }

  rl.close();
  fs.writeFileSync(path, JSON.stringify(state, null, 2), 'utf8');
  console.log(`\n已保存至 ${path}`);
}

main();
