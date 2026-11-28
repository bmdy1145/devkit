/* ============================================================================
 * Writer 内置自检（仅存在于测试版产品文件，正式版没有）
 * ----------------------------------------------------------------------------
 * 由 build_test_version.py 注入到 body 结束标签之前，包在 TEST_SELFTEST_START/END 之间。
 *
 * 注意：本文件会被内联进 HTML 的 script 块，源码里不得出现
 * 「小于号 + 斜杠 + 字母」序列（含 script/body 等标签名），否则 HTML
 * 解析器会提前结束脚本。构造成对标签请一律用 DOM API。
 *
 * 设计约束：
 *   · 黑盒：只操作 DOM 与公开事件，不读产品闭包里的对象。
 *   · 无污染：开跑前快照页签 / 弹窗 / 正文内容，finally 复原；
 *     只写临时探针键。
 *   · 不自动运行：必须用户点「自检」按钮。
 *   · 每项独立 try / catch：单项异常不影响其余项。
 * ========================================================================== */
(function () {
  'use strict';

  var PROBE_KEY = '__writer_selftest_probe__';
  var results = [];

  function pass(name, detail) { results.push({ ok: true, name: name, detail: detail || '' }); }
  function fail(name, detail) { results.push({ ok: false, name: name, detail: detail || '' }); }

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function check(name, fn) {
    try {
      var out = fn();
      if (out && typeof out.then === 'function') {
        return out.then(function (v) {
          if (v === false) fail(name, '返回 false');
          else pass(name, typeof v === 'string' ? v : '');
        }, function (e) {
          fail(name, (e && e.message) ? e.message : String(e));
        });
      }
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
        var ids = ['brandBtn', 'bookSelect', 'newBookBtn', 'manuscript', 'chapterTree',
                   'tabChapters', 'tabPrompt', 'countStatus', 'aboutModal', 'toast'];
        var missing = ids.filter(function (id) { return !document.getElementById(id); });
        if (missing.length) throw new Error('缺少：' + missing.join(', '));
        return ids.length + ' 个 id 全部存在';
      }),
      check('初始书籍与章节已渲染', function () {
        var sel = document.getElementById('bookSelect');
        if (!sel || !sel.options.length) throw new Error('书籍下拉为空');
        var tree = document.getElementById('chapterTree');
        if (!tree || !tree.children.length) throw new Error('章节树为空');
        return sel.options.length + ' 本书 / 树节点 ' + tree.children.length;
      }),
      check('关于弹窗含版本与许可证', function () {
        var txt = (document.getElementById('aboutModal') || document.body).textContent || '';
        if (txt.indexOf('A1_I_') < 0) throw new Error('关于弹窗未显示版本号');
        if (txt.indexOf('本程序是自由软件') < 0) throw new Error('未找到 GPLv3 声明');
        return '版本与 GPLv3 声明存在';
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
      check('body 主题类名就绪', function () {
        if ((document.body.className || '').indexOf('app-body') < 0) {
          throw new Error('body 类名为 ' + JSON.stringify(document.body.className));
        }
        return 'app-body';
      }),
      check('弹窗打开时 display 为 flex', function () {
        var modal = document.getElementById('aboutModal');
        if (!modal) throw new Error('aboutModal 不存在');
        var wasOpen = modal.classList.contains('open');
        modal.classList.add('open');
        var d = getComputedStyle(modal).display;
        if (!wasOpen) modal.classList.remove('open');
        if (d !== 'flex') throw new Error('打开时 display = ' + d);
        return 'display: ' + d;
      })
    ]);
  }

  /* ---------------- 交互 ---------------- */

  function interactionChecks() {
    var errCount = 0;
    function onErr() { errCount++; }
    window.addEventListener('error', onErr);
    window.addEventListener('unhandledrejection', onErr);

    var paneBefore = $$('.pane-tab').filter(function (t) {
      return t.getAttribute('aria-selected') === 'true';
    }).map(function (t) { return t.getAttribute('data-pane'); })[0] || 'chapters';
    var openModalsBefore = $$('.modal.open').map(function (m) { return m.id; });

    function restore() {
      // 页签
      var tab = $$('.pane-tab').filter(function (t) {
        return t.getAttribute('data-pane') === paneBefore;
      })[0];
      if (tab) tab.click();
      // 弹窗：关掉自检打开的，重新打开自检前就开着的（首启的「关于」常驻）。
      // 正文一律不碰：写入测试文本会触发 900ms 自动保存，可能污染用户的书。
      $$('.modal.open').forEach(function (m) {
        if (openModalsBefore.indexOf(m.id) < 0) m.classList.remove('open');
      });
      openModalsBefore.forEach(function (id) {
        var m = document.getElementById(id);
        if (m && !m.classList.contains('open')) m.classList.add('open');
      });
      window.removeEventListener('error', onErr);
      window.removeEventListener('unhandledrejection', onErr);
    }

    return (async function () {
      try {
        await check('面板页签切换', function () {
          var tab = document.getElementById('tabPrompt');
          tab.click();
          var pane = document.getElementById('panePrompt');
          if (tab.getAttribute('aria-selected') !== 'true') throw new Error('aria-selected 未同步');
          if (!pane.classList.contains('active')) throw new Error('目标面板未激活');
          return '章节 → 提示词';
        });

        await check('关于弹窗可开、data-close 可关', function () {
          var modal = document.getElementById('aboutModal');
          document.getElementById('brandBtn').click();
          if (!modal.classList.contains('open')) throw new Error('点击 brand 后未打开');
          var closer = modal.querySelector('[data-close]');
          if (!closer) throw new Error('缺少 data-close 关闭入口');
          closer.click();
          if (modal.classList.contains('open')) throw new Error('data-close 未关闭');
          return '开合正常';
        });

        await check('Esc 关闭最上层弹窗', function () {
          document.getElementById('settingsBtn').click();
          var modal = document.getElementById('settingsModal');
          if (!modal.classList.contains('open')) throw new Error('设置弹窗未打开');
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          if (modal.classList.contains('open')) throw new Error('Esc 未关闭');
          return 'OK';
        });

        await check('新建章弹窗可打开', function () {
          document.getElementById('newChapterBtn').click();
          var modal = document.getElementById('chapterModal');
          if (!modal.classList.contains('open')) throw new Error('chapterModal 未打开');
          var closer = modal.querySelector('[data-close]');
          if (closer) closer.click();
          return 'OK';
        });

        await check('状态栏统计就绪（行数 / 段数）', function () {
          // 只读断言：Φ6 新增的行数与段数必须出现在启动后的统计串里。
          // 不往正文框写测试文本——那会触发产品的 900ms 自动保存，
          // 可能把测试内容写进用户当前章节。
          var txt = (document.getElementById('countStatus').textContent || '');
          if (!/本章 \d+ 字 · \d+ 字符 · \d+ 行 · \d+ 段/.test(txt)) {
            throw new Error('统计串不符合预期：' + txt);
          }
          return txt.slice(0, 40);
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
      'justify-content:center;background:rgba(0,0,0,.55);padding:20px}' +
      '#selftestModal .st-box{width:100%;max-width:680px;max-height:86vh;overflow:auto;' +
      'background:var(--surface,#151922);color:var(--text,#e6e9ef);border:1px solid var(--border,#2a3040);' +
      'border-radius:12px;padding:18px 20px;box-shadow:0 18px 60px rgba(0,0,0,.5)}' +
      '#selftestModal h2{margin:0 0 10px;font-size:1.05rem}' +
      '#selftestModal ul{list-style:none;margin:0;padding:0;font-size:.85rem}' +
      '#selftestModal li{display:flex;gap:8px;align-items:flex-start;padding:3px 0}' +
      '#selftestModal .st-tag{flex:0 0 42px;font-family:monospace}' +
      '#selftestModal .st-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}' +
      '#selftestModal button{cursor:pointer;padding:6px 12px;border-radius:8px;' +
      'border:1px solid var(--border,#2a3040);background:var(--surface-2,#1b202b);color:inherit}' +
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
      (bad === 0 ? '#7ee787' : '#ff8a3d');
    summary.textContent = (bad === 0 ? '全部通过：' : '有失败项：') + good + ' / ' + total + ' 通过';
    box.appendChild(summary);

    var ul = document.createElement('ul');
    results.forEach(function (r) {
      var li = document.createElement('li');
      var tag = document.createElement('span');
      tag.className = 'st-tag';
      tag.style.color = r.ok ? '#7ee787' : '#ff7b72';
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
    note.style.cssText = 'margin:14px 0 0;color:#8b9aa6;font-size:.78rem';
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

  // 产品 boot 是异步的（Storage.init → 读库 → 没有书就新建一本），
  // 页面刚打开时点「自检」会看到空的下拉与统计。先等它落定再跑。
  function waitReady(timeoutMs) {
    var started = Date.now();
    function ready() {
      var sel = document.getElementById('bookSelect');
      var cnt = document.getElementById('countStatus');
      return !!(sel && sel.options.length > 0 &&
                cnt && /字/.test(cnt.textContent || ''));
    }
    return new Promise(function (resolve) {
      (function tick() {
        if (ready()) return resolve(true);
        if (Date.now() - started > timeoutMs) return resolve(false);
        setTimeout(tick, 100);
      })();
    });
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

  async function runChecks() {
    // 产品 boot 未就绪时不要硬跑：后面的断言会对着空 DOM 报一堆假失败，
    // 反而掩盖真正的原因（例如受限环境里 IndexedDB 只读/不可用）。
    var ready = await waitReady(12000);
    if (!ready) {
      fail('产品启动就绪', '12s 内未见首屏数据（可能是存储不可用）');
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
    var brand = document.querySelector('.brand');
    if (brand && !document.getElementById('testBadge')) {
      var badge = document.createElement('span');
      badge.id = 'testBadge';
      badge.textContent = 'TEST';
      brand.appendChild(badge);
    }
    var anchor = document.getElementById('settingsBtn');
    if (anchor && !document.getElementById('selftestBtn')) {
      var btn = document.createElement('button');
      btn.id = 'selftestBtn';
      btn.className = 'btn ghost focus-hide';
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
