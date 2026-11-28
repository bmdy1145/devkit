/* ============================================================================
 * SubMerge Pro 内置自检（仅存在于测试版产品文件，正式版没有）
 * ----------------------------------------------------------------------------
 * 由 build_test_version.py 注入到 body 结束标签之前，包在 TEST_SELFTEST_START/END 之间。
 *
 * 注意：本文件会被内联进 HTML 的 script 块，源码里不得出现
 * 「小于号 + 斜杠 + 字母」序列（含 script/body 等标签名），否则 HTML
 * 解析器会提前结束脚本。构造成对标签请一律用 DOM API。
 *
 * 设计约束：
 *   · 黑盒：只操作 DOM 与公开事件；**不使用剪贴板、不触发下载**。
 *     字幕上传需要真实文件对象，自检不伪造 File，只验证空态与控件联动。
 *   · 无污染：导出模式、目标语言、FPS 下拉在 finally 里复原。
 *   · 不自动运行；每项独立 try / catch。
 * ========================================================================== */
(function () {
  'use strict';

  var PROBE_KEY = '__submerge_selftest_probe__';
  var results = [];

  function pass(name, detail) { results.push({ ok: true, name: name, detail: detail || '' }); }
  function fail(name, detail) { results.push({ ok: false, name: name, detail: detail || '' }); }

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }

  function check(name, fn) {
    try {
      var out = fn();
      if (out === false) fail(name, '返回 false');
      else pass(name, typeof out === 'string' ? out : '');
    } catch (e) {
      fail(name, (e && e.message) ? e.message : String(e));
    }
    return Promise.resolve();
  }

  /* ---------------- 结构 ---------------- */

  function structureChecks() {
    return Promise.all([
      check('doctype / lang / charset / viewport', function () {
        var html = document.documentElement;
        if (!document.doctype) throw new Error('缺少 doctype');
        if (!html.getAttribute('lang')) throw new Error('html 缺少 lang');
        if (!$('meta[charset]')) throw new Error('缺少 meta charset');
        if (!$('meta[name="viewport"]')) throw new Error('缺少 viewport');
        return html.getAttribute('lang');
      }),
      check('CSP meta 存在且关键指令齐全', function () {
        var m = $('meta[http-equiv="Content-Security-Policy"]');
        if (!m) throw new Error('缺少 CSP');
        var c = m.getAttribute('content') || '';
        // 只查子串会让 "script-src" 出现在注释或别的指令里也通过。
        // 按指令名逐条校验，且 object-src 必须是 'none'（否则可嵌入插件）。
        ['default-src', 'script-src', 'object-src'].forEach(function (d) {
          if (!new RegExp('(^|;)\\s*' + d + '\\s').test(c)) {
            throw new Error('CSP 缺少指令：' + d);
          }
        });
        if (!/object-src\s+'none'/.test(c)) throw new Error("object-src 应为 'none'");
        return '3 条关键指令齐全';
      }),
      check('关键节点 id 齐全', function () {
        var ids = ['dropZone', 'fileInput', 'langNameInput', 'presetLangSelect',
                   'fpsRow', 'fpsSelect', 'translationInput', 'mergedTextView',
                   'mergeBtn', 'undoBtn', 'exportBtn', 'resetBtn', 'tableBody',
                   'exportModeGroup', 'entryCountDisplay'];
        var missing = ids.filter(function (id) { return !document.getElementById(id); });
        if (missing.length) throw new Error('缺少：' + missing.join(', '));
        return ids.length + ' 个 id 全部存在';
      }),
      check('状态栏与预览表一致', function () {
        // 不能在自检里假设「一定还没载字幕」：用户在本次会话里传过文件时，
        // 状态栏会是「✅ 原始 N 条 · 拆分后 M 条」。这里按当前状态分支断言，
        // 两种状态都必须自洽。
        var txt = (document.getElementById('entryCountDisplay').textContent || '').trim();
        var rows = document.querySelectorAll('#tableBody tr');
        var empty = txt.indexOf('未加载字幕') >= 0;
        if (empty) {
          if (rows.length !== 1) throw new Error('未载字幕时预览表应只有提示行，实际 ' + rows.length);
          return '空态：未加载字幕';
        }
        var m = txt.match(/原始\s*(\d+)\s*条\s*·\s*拆分后\s*(\d+)\s*条/);
        if (!m) throw new Error('状态栏文案无法识别：' + txt.slice(0, 40));
        if (rows.length < 1) throw new Error('已载字幕但预览表为空');
        return '已载字幕：原始 ' + m[1] + ' 条，表格 ' + rows.length + ' 行';
      }),
      check('许可证声明存在', function () {
        var txt = document.body.textContent || '';
        if (txt.indexOf('本程序是自由软件') < 0) throw new Error('未找到 GPLv3 声明');
        return 'GPLv3 声明存在';
      })
    ]);
  }

  /* ---------------- 样式 ---------------- */

  function styleChecks() {
    return Promise.all([
      check('CSS 变量可解析', function () {
        var names = ['--bg', '--text', '--accent'];
        var empty = names.filter(function (n) { return !cssVar(n); });
        if (empty.length) throw new Error('空值：' + empty.join(', '));
        return names.join(' / ') + ' 均有值';
      }),
      check('body 带皮肤类名', function () {
        var cls = document.body.className || '';
        if (!/\bskin-\w+\b/.test(cls)) throw new Error('body 类名为 ' + JSON.stringify(cls));
        return cls.match(/\bskin-\w+\b/)[0];
      }),
      check('操作按钮可用性随状态变化', function () {
        // 未载字幕时全禁用；已载字幕时至少导出 / 重置应可用。
        var ids = ['mergeBtn', 'undoBtn', 'exportBtn', 'resetBtn', 'copyMergedBtn'];
        var nodes = ids.map(function (id) { return document.getElementById(id); });
        if (nodes.some(function (n) { return !n; })) {
          throw new Error('缺少按钮节点');
        }
        var empty = (document.getElementById('entryCountDisplay').textContent || '')
          .indexOf('未加载字幕') >= 0;
        if (empty) {
          var enabled = nodes.filter(function (n) { return !n.disabled; });
          if (enabled.length) {
            throw new Error('未载字幕时不应有可用按钮：' + enabled.length + ' 个');
          }
          return '空态：5 个按钮均禁用';
        }
        ['exportBtn', 'resetBtn'].forEach(function (id) {
          if (document.getElementById(id).disabled) {
            throw new Error('已载字幕但 ' + id + ' 被禁用');
          }
        });
        return '已载字幕：导出 / 重置可用';
      })
    ]);
  }

  /* ---------------- 交互 ---------------- */

  function interactionChecks() {
    var errCount = 0;
    function onErr() { errCount++; }
    window.addEventListener('error', onErr);
    window.addEventListener('unhandledrejection', onErr);

    var langBefore = (document.getElementById('langNameInput') || {}).value || '';
    var presetBefore = (document.getElementById('presetLangSelect') || {}).value || '';
    var fpsBefore = (document.getElementById('fpsSelect') || {}).value || '25';
    var fpsCustomBefore = (document.getElementById('fpsCustomInput') || {}).value || '25';
    var translationBefore = (document.getElementById('translationInput') || {}).value || '';
    var modeBefore = (function () {
      var on = $('#exportModeGroup .mode-btn.active');
      return on ? on.getAttribute('data-mode') : 'both';
    })();

    function restore() {
      var modeBtn = $$('#exportModeGroup .mode-btn').filter(function (b) {
        return b.getAttribute('data-mode') === modeBefore;
      })[0];
      if (modeBtn) modeBtn.click();
      var lang = document.getElementById('langNameInput');
      if (lang) lang.value = langBefore;
      var preset = document.getElementById('presetLangSelect');
      if (preset) preset.value = presetBefore;
      var fps = document.getElementById('fpsSelect');
      if (fps) {
        fps.value = fpsBefore;
        fps.dispatchEvent(new Event('change', { bubbles: true }));
      }
      var custom = document.getElementById('fpsCustomInput');
      if (custom) custom.value = fpsCustomBefore;
      var ta = document.getElementById('translationInput');
      if (ta) ta.value = translationBefore;
      window.removeEventListener('error', onErr);
      window.removeEventListener('unhandledrejection', onErr);
    }

    return (async function () {
      try {
        await check('预设语言下拉已填充且可联动', function () {
          var sel = document.getElementById('presetLangSelect');
          if (sel.options.length < 10) throw new Error('只有 ' + sel.options.length + ' 项');
          var target = Array.prototype.slice.call(sel.options).filter(function (o) {
            return o.value !== sel.value;
          })[0];
          if (!target) throw new Error('找不到其它语言');
          sel.value = target.value;
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          var input = document.getElementById('langNameInput');
          if (input.value !== target.value) {
            throw new Error('目标语言未联动：' + input.value + ' vs ' + target.value);
          }
          return sel.options.length + ' 个预设 · 联动为 ' + target.value;
        });

        await check('FPS 选择「自定义」显示输入框', function () {
          var sel = document.getElementById('fpsSelect');
          var custom = document.getElementById('fpsCustomInput');
          var row = document.getElementById('fpsRow');
          sel.value = 'custom';
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          if (getComputedStyle(custom).display === 'none') {
            throw new Error('自定义输入框未显示');
          }
          sel.value = '25';
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          if (getComputedStyle(custom).display !== 'none') {
            throw new Error('切回固定帧率后输入框未隐藏');
          }
          // FPS 行是否显示由文件名决定（.bcc 才显示）。自检不改文件名，
          // 因此只断言「切换帧率不应改变该行的显隐」，不假设它一定隐藏。
          if (row.style.display === '') {
            var loaded = !document.getElementById('fileInput').files.length;
            if (loaded) throw new Error('未载文件时 FPS 行不应被打开');
          }
          return '显示 / 隐藏正常';
        });

        await check('导出模式切换', function () {
          var group = document.getElementById('exportModeGroup');
          var btns = $$('#exportModeGroup .mode-btn');
          if (btns.length !== 3) throw new Error('模式按钮 ' + btns.length + ' 个');
          var target = btns.filter(function (b) {
            return !b.classList.contains('active');
          })[0];
          target.click();
          if (!target.classList.contains('active')) throw new Error('点击后未激活');
          var actives = btns.filter(function (b) { return b.classList.contains('active'); });
          if (actives.length !== 1) throw new Error('active 数量 ' + actives.length);
          return modeBefore + ' → ' + target.getAttribute('data-mode');
        });

        await check('粘贴框输入不改写状态栏', function () {
          // 只断言「输入译文不会改变状态栏文案」——状态栏由文件加载与拆分
          // 决定，与翻译输入无关。不能要求它一定是空态文案。
          var ta = document.getElementById('translationInput');
          var before = (document.getElementById('entryCountDisplay').textContent || '').trim();
          var was = ta.value;
          ta.value = '[1] 测试译文';
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          var after = (document.getElementById('entryCountDisplay').textContent || '').trim();
          ta.value = was;
          if (before !== after) throw new Error('状态栏被改写：' + before + ' → ' + after);
          return '输入前后一致';
        });

        await check('localStorage 读写', function () {
          localStorage.setItem(PROBE_KEY, 'ok');
          var v = localStorage.getItem(PROBE_KEY);
          localStorage.removeItem(PROBE_KEY);
          if (v !== 'ok') throw new Error('回读不一致：' + v);
          if (localStorage.getItem(PROBE_KEY) !== null) throw new Error('探针键未清除');
          return '写 / 读 / 删 正常';
        });

        await check('运行期无未捕获异常', function () {
          if (errCount > 0) throw new Error('捕获到 ' + errCount + ' 个异常');
          return '0 个';
        });
      } finally {
        restore();
      }
    })();
  }

  /* ---------------- 结果 UI ---------------- */

  function injectStyle() {
    if (document.getElementById('selftestStyle')) return;
    var st = document.createElement('style');
    st.id = 'selftestStyle';
    st.textContent =
      '#selftestModal{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;' +
      'justify-content:center;background:rgba(0,0,0,.5);padding:20px}' +
      '#selftestModal .st-box{width:100%;max-width:680px;max-height:86vh;overflow:auto;' +
      'background:var(--surface,#fff);color:var(--text,#0f172a);border:1px solid var(--border,#cbd5e1);' +
      'border-radius:12px;padding:18px 20px;box-shadow:0 18px 60px rgba(0,0,0,.35)}' +
      '#selftestModal h2{margin:0 0 10px;font-size:1.05rem}' +
      '#selftestModal ul{list-style:none;margin:0;padding:0;font-size:.85rem}' +
      '#selftestModal li{display:flex;gap:8px;align-items:flex-start;padding:3px 0}' +
      '#selftestModal .st-tag{flex:0 0 42px;font-family:monospace}' +
      '#selftestModal .st-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}' +
      '#selftestModal button{cursor:pointer;padding:6px 12px;border-radius:8px;' +
      'border:1px solid var(--border,#cbd5e1);background:var(--surface-2,#fafcff);color:inherit}' +
      '#testBadge{margin-left:8px;padding:1px 7px;border-radius:999px;background:#ff8a3d;' +
      'color:#08090d;font-size:.66rem;font-weight:700;font-family:ui-monospace,monospace;' +
      'letter-spacing:.06em;vertical-align:middle}';
    document.head.appendChild(st);
  }

  function render() {
    var old = document.getElementById('selftestModal');
    if (old) old.remove();

    var total = results.length;
    var bad = results.filter(function (r) { return !r.ok; }).length;
    var good = total - bad;

    var wrap = document.createElement('div');
    wrap.id = 'selftestModal';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-label', '内置自检结果');

    var box = document.createElement('div');
    box.className = 'st-box';

    var h = document.createElement('h2');
    h.textContent = '内置自检';
    box.appendChild(h);

    var summary = document.createElement('p');
    summary.style.cssText = 'margin:0 0 12px;font-weight:600;color:' +
      (bad === 0 ? '#166534' : '#b91c1c');
    summary.textContent = (bad === 0 ? '全部通过：' : '有失败项：') + good + ' / ' + total + ' 通过';
    box.appendChild(summary);

    var ul = document.createElement('ul');
    results.forEach(function (r) {
      var li = document.createElement('li');
      var tag = document.createElement('span');
      tag.className = 'st-tag';
      tag.style.color = r.ok ? '#166534' : '#b91c1c';
      tag.textContent = r.ok ? 'PASS' : 'FAIL';
      var txt = document.createElement('span');
      txt.style.flex = '1';
      txt.textContent = r.name + (r.detail ? ' — ' + r.detail : '');
      li.appendChild(tag);
      li.appendChild(txt);
      ul.appendChild(li);
    });
    box.appendChild(ul);

    var note = document.createElement('p');
    note.style.cssText = 'margin:14px 0 0;color:var(--text2,#475569);font-size:.78rem';
    note.textContent = '这是测试版专属的自检，不改动任何用户数据；开跑前的界面状态已自动恢复。';
    box.appendChild(note);

    var actions = document.createElement('div');
    actions.className = 'st-actions';
    var rerun = document.createElement('button');
    rerun.type = 'button';
    rerun.textContent = '重新运行';
    var close = document.createElement('button');
    close.type = 'button';
    close.textContent = '关闭';
    actions.appendChild(rerun);
    actions.appendChild(close);
    box.appendChild(actions);
    wrap.appendChild(box);
    document.body.appendChild(wrap);

    function shut() { wrap.remove(); restoreTitle(); }
    close.addEventListener('click', shut);
    rerun.addEventListener('click', function () { shut(); setTimeout(run, 0); });
    wrap.addEventListener('click', function (e) { if (e.target === wrap) shut(); });
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { shut(); document.removeEventListener('keydown', esc); }
    });

    return { total: total, bad: bad, good: good };
  }

  /* 防重入：run() 会 await 一串异步检查，期间用户再点「自检」会让两轮
     检查交叉执行——同一个弹窗被反复移除/重建、产品的模式切换与折叠态
     互相打架。persona 上实测能稳定把渲染进程拖死（快速双点 5/8 复现）。
     已有结果弹窗时直接复用，不重跑。 */
  var running = false;
  var titleBefore = null;
  var lastResult = '';

  // 必须明显短于 test_selftest_runner.py 的单项目预算（120s），
  // 否则自检卡住时来不及输出失败结果，外部只能看到「浏览器超时」。
  var RUN_TIMEOUT_MS = 45000;

  async function run() {
    if (running) return;
    if (document.getElementById('selftestModal')) return;
    running = true;
    if (titleBefore === null) titleBefore = document.title;
    results = [];
    injectStyle();
    // 总超时兜底：产品 boot 或某个 await 在受限环境（如 CI 里 IndexedDB
    // 不可用）下可能永不返回。没有这一层，自检会把整个渲染进程挂住，
    // 用户看到的是页面卡死；CI 看到的是浏览器超时而非一条明确失败。
    var timedOut = false;
    var watchdog = setTimeout(function () {
      if (document.getElementById('selftestModal')) return;
      timedOut = true;
      fail('自检总超时', RUN_TIMEOUT_MS + 'ms 内未完成');
      var w = render();
      lastResult = 'SELFTEST-FAIL ' + w.good + '/' + w.total;
      try { document.documentElement.setAttribute('data-selftest', lastResult); } catch (e) {}
      running = false;
    }, RUN_TIMEOUT_MS);
    try {
      await runChecks();
      // 已经超时并渲染过结果：runChecks 的后续完成不能再渲染一次，
      // 否则用户会看到弹窗闪一下（旧弹窗被移除、新弹窗重建）。
      if (timedOut) return;
    } finally {
      clearTimeout(watchdog);
    }
  }

  // 产品没有异步 boot（纯 DOM 初始化），但保留一个兜底：等 selftestBtn
  // 出现即可，避免 mount 与产品 DOM 构建的顺序问题。
  function waitReady(timeoutMs) {
    var started = Date.now();
    return new Promise(function (resolve) {
      (function tick() {
        if (document.getElementById('selftestBtn')) return resolve(true);
        if (Date.now() - started > timeoutMs) return resolve(false);
        setTimeout(tick, 100);
      })();
    });
  }

  async function runChecks() {
    var ready = await waitReady(8000);
    if (!ready) {
      fail('产品启动就绪', '8s 内未见自检入口');
      return;
    }
    await structureChecks();
    await styleChecks();
    await interactionChecks();
    var r = render();
    // 标题只用于无头浏览器断言；普通用户关掉弹窗后必须还原，
    // 否则标签页会一直停在 SELFTEST-PASS n/m。
    lastResult = (r.bad === 0 ? 'SELFTEST-PASS ' : 'SELFTEST-FAIL ') +
      r.good + '/' + r.total;
    // 弹窗可能已被用户关掉（或已被下一次 run 重建）：只在它仍挂着时写标题，
    // 否则会把关闭时还原过的标题又改回 SELFTEST-PASS。
    if (document.getElementById('selftestModal')) document.title = lastResult;
    // 结果同时写进 <html data-selftest>：自动化在弹窗还开着时就要能读到
    // 结论（用户关掉弹窗后标题会被还原，不能只靠标题）。
    try { document.documentElement.setAttribute('data-selftest', lastResult); } catch (e) {}
    running = false;
  }

  /* 结果 UI 关闭时把标题还原；标题同时通过 data 属性暴露给自动化，
     避免为了断言而永久污染用户的标签页。 */
  function restoreTitle() {
    if (titleBefore !== null) document.title = titleBefore;
  }

  /* ---------------- 注入入口 ---------------- */

  function mount() {
    injectStyle();
    var h1 = document.querySelector('.header-row h1');
    if (h1 && !document.getElementById('testBadge')) {
      var badge = document.createElement('span');
      badge.id = 'testBadge';
      badge.textContent = 'TEST';
      h1.appendChild(badge);
    }
    var anchor = document.getElementById('exportBtn');
    if (anchor && !document.getElementById('selftestBtn')) {
      var btn = document.createElement('button');
      btn.id = 'selftestBtn';
      btn.className = 'btn btn-outline-blue';
      btn.type = 'button';
      btn.textContent = '自检';
      btn.style.color = '#ff8a3d';
      btn.addEventListener('click', function (e) { e.stopPropagation(); run(); });
      anchor.parentNode.insertBefore(btn, anchor);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }

  window.__selftest = run;
})();
