#!/usr/bin/env node
// DevKit 内核版（TypeScript / Node）
//
// 版本：A1_V_Φ9_Fix_TypeScript_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
// 提示词模板拼接。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
'use strict';

const fs = require('fs');

const CURRENT_VERSION = 'A1_V_Φ9_Fix_TypeScript_CN';

const SPECS = [
  { key: 'performanceMode', kind: 'boolean', def: false },
  { key: 'shortcutsEnabled', kind: 'boolean', def: true },
  { key: 'hideBtnText', kind: 'boolean', def: false },
  { key: 'promptActionsAlways', kind: 'boolean', def: true },
  { key: 'specPromptEnabled', kind: 'boolean', def: true },
  { key: 'inspirationSyncEnabled', kind: 'boolean', def: true },
  { key: 'themePref', kind: 'enum', def: 'light', values: ['dark', 'light', 'auto'] },
];

// 与浏览器版一致：分支代号 + 结构段 + 语言后缀
function parseVersion(v) {
  if (typeof v !== 'string') return null;
  const t = v.trim();
  if (!t || t.length > 100) return null;

  let core = t;
  let suffix = null;
  if (t.endsWith('_CN')) { core = t.slice(0, -3); suffix = 'CN'; }
  else if (t.endsWith('_GLOBAL')) { core = t.slice(0, -7); suffix = 'GLOBAL'; }

  const parts = core.split('_');
  if (!parts.length) return null;
  const branch = parts[0];
  if (!branch.startsWith('A')) return null;
  if (branch.length > 1 && !/^\d+$/.test(branch.slice(1))) return null;

  return { branch, structure: parts.slice(1).join('_'), suffix };
}

function isCompatible(v) {
  const p = parseVersion(v);
  if (!p) return false;
  if (/^A2\d*$/.test(p.branch)) return false;
  if (p.structure.split('_').includes('A2')) return false;
  return true;
}

function normalizeSettings(src) {
  const out = {};
  for (const spec of SPECS) {
    const val = src[spec.key];
    if (spec.kind === 'boolean') out[spec.key] = typeof val === 'boolean' ? val : spec.def;
    else if (spec.kind === 'enum') out[spec.key] = (typeof val === 'string' && spec.values.includes(val)) ? val : spec.def;
  }
  return out;
}

function validateImport(data) {
  if (!data || typeof data !== 'object') return { n: 0, err: '格式错误：不是有效对象' };
  if (data.projects === undefined) {
    if (data.project !== undefined) return { n: 1, err: null };
    return { n: 0, err: '格式错误：不是有效对象' };
  }
  if (!Array.isArray(data.projects)) return { n: 0, err: '格式错误：projects 不是数组' };
  if (data.projects.length > 20) return { n: 0, err: `项目数 ${data.projects.length} 超过上限 20` };

  for (let i = 0; i < data.projects.length; i++) {
    const p = data.projects[i];
    if (!p || typeof p !== 'object') return { n: 0, err: `第 ${i + 1} 个项目不是对象` };
    if (typeof p.id !== 'string' || !p.id) return { n: 0, err: `第 ${i + 1} 个项目缺少 id` };
    if (typeof p.name !== 'string' || !p.name) return { n: 0, err: `第 ${i + 1} 个项目缺少 name` };
    if (!Array.isArray(p.tabs)) return { n: 0, err: `第 ${i + 1} 个项目缺少 tabs` };
    if (p.tabs.length > 50) return { n: 0, err: `第 ${i + 1} 个项目页签超过 50` };
    for (let j = 0; j < p.tabs.length; j++) {
      const t = p.tabs[j];
      if (!t || typeof t !== 'object' || typeof t.id !== 'string' || !t.id || typeof t.name !== 'string' || !t.name)
        return { n: 0, err: `第 ${i + 1} 个项目第 ${j + 1} 个页签字段不完整` };
    }
  }
  return { n: data.projects.length, err: null };
}

function usage() {
  console.log('DevKit 内核版（TypeScript / Node）');
  console.log('用法: devkit.js <子命令> [参数]');
  console.log('');
  console.log('子命令:');
  console.log('  version');
  console.log('  parse-version <版本号>');
  console.log('  check-version <版本号>');
  console.log('  validate-config <配置文件>');
  console.log('  normalize <设置JSON>');
  console.log('  compose <模板文件> <灵感> [代码文件]');
}

function main() {
  const args = process.argv.slice(2);
  if (!args.length) { usage(); return 1; }

  switch (args[0]) {
    case 'version':
      console.log(CURRENT_VERSION);
      return 0;

    case 'parse-version': {
      if (!args[1]) { console.error('缺少版本号'); return 1; }
      const p = parseVersion(args[1]);
      if (!p) { console.error('版本号不合规'); return 1; }
      console.log(`分支: ${p.branch}`);
      console.log(`结构段: ${p.structure || '（无）'}`);
      console.log(`语言后缀: ${p.suffix || '（无）'}`);
      return 0;
    }

    case 'check-version': {
      if (!args[1]) { console.error('缺少版本号'); return 1; }
      const ok = isCompatible(args[1]);
      console.log(ok ? '兼容' : '不兼容');
      return ok ? 0 : 1;
    }

    case 'validate-config': {
      if (!args[1]) { console.error('缺少配置文件路径'); return 1; }
      let data;
      try { data = JSON.parse(fs.readFileSync(args[1], 'utf8')); }
      catch (e) { console.error(`读取或解析失败: ${e.message}`); return 1; }
      if (typeof data.version === 'string' && !isCompatible(data.version)) {
        console.error(`配置文件版本不兼容: ${data.version}`);
        return 1;
      }
      const { n, err } = validateImport(data);
      if (err) { console.error(err); return 1; }
      console.log(`校验通过，项目数: ${n}`);
      return 0;
    }

    case 'normalize': {
      if (!args[1]) { console.error('缺少设置 JSON'); return 1; }
      let src;
      try { src = JSON.parse(args[1]); }
      catch (e) { console.error(`JSON 解析失败: ${e.message}`); return 1; }
      console.log(JSON.stringify(normalizeSettings(src), null, 2));
      return 0;
    }

    case 'compose': {
      if (!args[1] || !args[2]) { console.error('用法: compose <模板文件> <灵感> [代码文件]'); return 1; }
      let tpl;
      try { tpl = fs.readFileSync(args[1], 'utf8'); }
      catch (e) { console.error(`读取模板失败: ${e.message}`); return 1; }
      let code = '（无代码）';
      if (args[3]) { try { code = fs.readFileSync(args[3], 'utf8'); } catch (e) { /* 忽略 */ } }
      process.stdout.write(tpl.replace(/\{inspiration\}/g, args[2]).replace(/\{code\}/g, code));
      return 0;
    }

    default:
      console.error(`未知子命令: ${args[0]}`);
      usage();
      return 1;
  }
}

process.exit(main());
