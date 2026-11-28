/* ============================================================================
 * Persona 内置自检（仅存在于测试版产品文件，正式版没有）
 * ----------------------------------------------------------------------------
 * 由 build_test_version.py 注入到 body 结束标签之前，包在 TEST_SELFTEST_START/END 之间。
 *
 * 注意：本文件会被内联进 HTML 的 script 块，源码里不得出现
 * 「小于号 + 斜杠 + 字母」序列（含 script/body 等标签名），否则 HTML
 * 解析器会提前结束脚本。构造成对标签请一律用 DOM API。
 *
 * 设计约束：
 *   · 黑盒：只操作 DOM 与公开事件。
 *   · 无污染：快照编辑对象模式、AI 结果栏折叠态、弹窗；finally 复原。
 *   · 不自动运行；每项独立 try / catch。
 * ========================================================================== */
(function () {
  'use strict';

  var PROBE_KEY = '__persona_selftest_probe__';
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
        var ids = ['brandBtn', 'topMeta', 'exportBtn', 'settingsBtn',
                   'sidePersonas', 'personaList', 'editorTitle', 'editorBody',
                   'resultInput', 'requestInput', 'previewBtn', 'aboutModal'];
        var missing = ids.filter(function (id) { return !document.getElementById(id); });
        if (missing.length) throw new Error('缺少：' + missing.join(', '));
        return ids.length + ' 个 id 全部存在';
      }),
      check('人设卡片与编辑区已渲染', function () {
        var list = document.getElementById('personaList');
        if (!list || !list.children.length) throw new Error('人设列表为空');
        var body = document.getElementById('editorBody');
        if (!body || !body.children.length) throw new Error('编辑区为空');
        return list.children.length + ' 张卡片';
      }),
      check('关于弹窗含版本与许可证', function () {
        var txt = (document.getElementById('aboutModal') || document.body).textContent || '';
        if (txt.indexOf('A1_II_') < 0) throw new Error('关于弹窗未显示版本号');
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
      check('工作区布局就绪', function () {
        // 宽屏是三栏并存；≤699px（以及矮屏）产品切到页签模式，
        // 一次只显示 .is-active 那一栏，另外两栏故意 display:none。
        // 两种布局都要断言，不能只按宽屏写——否则手机用户点「自检」
        // 会看到「.sidebar 宽度为 0」的假失败。
        var narrow = window.matchMedia('(max-width: 699px), (max-height: 480px)').matches;
        var panes = ['sidebar', 'editor', 'result'];
        var nodes = panes.map(function (cls) {
          var n = $('.' + cls);
          if (!n) throw new Error('缺少 .' + cls);
          return n;
        });
        if (narrow) {
          var shown = nodes.filter(function (n) {
            return n.getBoundingClientRect().width > 0;
          });
          if (shown.length !== 1) {
            throw new Error('页签模式下应恰好一栏可见，实际 ' + shown.length);
          }
          var tabs = $$('.mtab');
          if (!tabs.length) throw new Error('页签模式下缺少 .mtab');
          return '页签模式 · ' + shown[0].getAttribute('data-pane') + ' 可见';
        }
        // 宽屏三栏并存，但结果栏可能被用户折叠（持久化偏好
        // resultCollapsed；产品会把 .result.collapsed 的宽度收成 0）。
        // 那是合法用户状态，不能算失败：结果栏折叠时只要求侧栏与编辑区可见。
        var missing = nodes.filter(function (n) {
          if (n.getBoundingClientRect().width > 0) return false;
          var pane = n.getAttribute('data-pane');
          if (pane === 'result' && n.classList.contains('collapsed')) return false;
          return true;
        });
        if (missing.length) {
          throw new Error('宽度为 0：' + missing.map(function (n) {
            return '.' + n.getAttribute('data-pane');
          }).join(', '));
        }
        var collapsed = nodes.filter(function (n) {
          return n.classList.contains('collapsed');
        }).length;
        return collapsed ? '三栏就绪（结果栏折叠，属用户偏好）' : '侧栏 / 编辑 / 结果三栏就绪';
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

    var modeBefore = (function () {
      var sw = $('.mode-switch');
      return sw ? (sw.getAttribute('data-active') || 'persona') : 'persona';
    })();
    var resultCollapsedBefore = (function () {
      var r = $('.result');
      return r ? r.classList.contains('collapsed') : false;
    })();
    var openModalsBefore = $$('.modal.open').map(function (m) { return m.id; });

    function restore() {
      var wanted = modeBefore;
      var btn = $$('.mode-btn').filter(function (b) {
        return b.getAttribute('data-mode') === wanted;
      })[0];
      if (btn) btn.click();
      // 结果栏折叠态：与快照不一致时点一次恢复（每次点击只翻转，不会连点）
      var r = $('.result');
      if (r && r.classList.contains('collapsed') !== resultCollapsedBefore) {
        var t = document.getElementById('resultToggleBtn');
        if (t) t.click();
      }
      // 关掉自检新开的弹窗；再把自检前就开着的弹窗重新打开
      // （首访时 aboutModal 是产品自己常驻打开的，必须还原）。
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
        await check('模式切换：人设 ↔ 世界观', function () {
          var wv = $$('.mode-btn').filter(function (b) {
            return b.getAttribute('data-mode') === 'worldview';
          })[0];
          if (!wv) throw new Error('缺少世界观模式按钮');
          wv.click();
          var sw = $('.mode-switch');
          if (!sw || sw.getAttribute('data-active') !== 'worldview') {
            throw new Error('data-active 未切到 worldview');
          }
          if (!$('#editorPersona').hidden) throw new Error('人设编辑区未隐藏');
          return '人设 → 世界观';
        });

        await check('AI 结果栏折叠 / 展开', function () {
          var r = $('.result');
          if (!r) throw new Error('结果区不存在');
          var before = r.classList.contains('collapsed');
          document.getElementById('resultToggleBtn').click();
          var after = r.classList.contains('collapsed');
          if (before === after) throw new Error('折叠态未变化');
          return before + ' → ' + after;
        });

        await check('提示词预览可生成', function () {
          // 上一步切到了世界观模式；预览按钮按模式分派，世界观分支在没有
          // 当前世界观时只会 toast 后返回。先切回人设模式，让检查对象确定。
          var personaBtn = $$('.mode-btn').filter(function (b) {
            return b.getAttribute('data-mode') === 'persona';
          })[0];
          if (personaBtn) personaBtn.click();
          document.getElementById('previewBtn').click();
          var modal = document.getElementById('previewModal');
          if (!modal || !modal.classList.contains('open')) {
            throw new Error('previewModal 未打开');
          }
          var text = (document.getElementById('promptPreview') || {}).textContent || '';
          if (text.trim().length < 20) throw new Error('预览内容过短：' + text.length);
          var closer = modal.querySelector('[data-close]');
          if (closer) closer.click();
          return text.length + ' 字符';
        });

        await check('关于弹窗可开、Esc 可关', function () {
          document.getElementById('aboutBtn').click();
          var modal = document.getElementById('aboutModal');
          if (!modal.classList.contains('open')) throw new Error('未打开');
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          if (modal.classList.contains('open')) throw new Error('Esc 未关闭');
          return 'OK';
        });

        await check('记忆文档弹窗可打开', function () {
          document.getElementById('memoryBtn').click();
          var modal = document.getElementById('memoryModal');
          if (!modal.classList.contains('open')) throw new Error('memoryModal 未打开');
          var meta = (document.getElementById('memoryMeta') || {}).textContent || '';
          // 产品两个分支的文案都非空（空记忆也写「还没有记忆…」），
          // 只断言非空等于恒过。这里要求能识别出是哪一个分支。
          var hasMem = /已导入\s*\d+\s*条/.test(meta);
          var empty = meta.indexOf('还没有记忆') >= 0;
          if (!hasMem && !empty) throw new Error('记忆元信息不可识别：' + meta.slice(0, 40));
          var preview = (document.getElementById('memoryPreview') || {}).textContent || '';
          if (!preview.trim()) throw new Error('记忆预览为空');
          var closer = modal.querySelector('[data-close]');
          if (closer) closer.click();
          return (hasMem ? '有记忆' : '空记忆') + ' · ' + meta.slice(0, 20);
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

  // 产品 boot 是异步的（三个 loadAll → 没卡片就新建一张），
  // 过早点击「自检」会看到空列表。先等首张卡片渲染出来。
  function waitReady(timeoutMs) {
    var started = Date.now();
    function ready() {
      var list = document.getElementById('personaList');
      var body = document.getElementById('editorBody');
      return !!(list && list.children.length &&
                body && body.children.length);
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
      btn.className = 'btn sm';
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
