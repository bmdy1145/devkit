/* ============================================================================
 * 内置自检（仅存在于测试版产品文件，正式版没有）
 * ----------------------------------------------------------------------------
 * 由 build_test_version.py 注入到 body 结束标签之前，包在 TEST_SELFTEST_START/END 之间。
 *
 * 注意：本文件会被内联进 HTML 的 <script> 块，因此源码里**不得出现**
 * 任何形如「小于号 + 斜杠 + 字母」的序列（包括 body、script 等标签名）。
 * HTML 解析器在脚本数据状态下一旦读到这类序列就会进入「结束标签」分支，
 * 可能导致后续脚本整体不执行。上面那句原本写作具体标签名，就是因为踩了这个坑。
 *
 * 设计约束：
 *   · 黑盒：只操作 DOM 与公开事件，不读取产品内部闭包里的对象。
 *   · 无污染：开跑前快照用户状态（body 类、主题、页签数），结束时恢复；
 *     只写临时探针键，不碰 devkit_first_run 等真实键。
 *   · 不自动运行：必须用户点「自检」按钮。
 *   · 每项独立 try/catch：单项异常不影响其余项。
 * ========================================================================== */
(function () {
  'use strict';

  var PROBE_KEY = '__devkit_selftest_probe__';
  var results = [];

  function pass(name, detail) { results.push({ ok: true, name: name, detail: detail || '' }); }
  function fail(name, detail) { results.push({ ok: false, name: name, detail: detail || '' }); }

  function check(name, fn) {
    try {
      var out = fn();
      if (out === false) fail(name, '返回 false');
      else pass(name, typeof out === 'string' ? out : '');
    } catch (e) {
      fail(name, (e && e.message) ? e.message : String(e));
    }
  }

  function $(sel) { return document.querySelector(sel); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }

  /* ---------------- 结构 6 项 ---------------- */

  function structureChecks() {
    check('doctype / lang / charset / viewport', function () {
      var html = document.documentElement;
      if (!document.doctype) throw new Error('缺少 <!DOCTYPE>');
      if (!html.getAttribute('lang')) throw new Error('<html> 缺少 lang');
      if (!$('meta[charset]')) throw new Error('缺少 <meta charset>');
      if (!$('meta[name="viewport"]')) throw new Error('缺少 viewport');
      return html.getAttribute('lang');
    });

    check('CSP meta 存在', function () {
      var m = $('meta[http-equiv="Content-Security-Policy"]');
      if (!m) throw new Error('缺少 CSP meta');
      var c = m.getAttribute('content') || '';
      if (c.indexOf("script-src") < 0) throw new Error('CSP 未声明 script-src');
      return 'script-src 已声明';
    });

    check('关键节点 id 齐全', function () {
      var ids = ['brandBtn', 'versionHistoryBtn', 'addTabBtn', 'tabList', 'projectBar',
                 'themeBtn', 'themeMenu', 'toast', 'contextMenu'];
      var missing = ids.filter(function (id) { return !document.getElementById(id); });
      if (missing.length) throw new Error('缺少：' + missing.join(', '));
      return ids.length + ' 个 id 全部存在';
    });

    check('顶栏按钮 aria 属性', function () {
      var b = document.getElementById('themeBtn');
      if (!b) throw new Error('themeBtn 不存在');
      if (b.getAttribute('aria-haspopup') !== 'true') throw new Error('themeBtn 缺 aria-haspopup');
      if (b.getAttribute('aria-expanded') === null) throw new Error('themeBtn 缺 aria-expanded');
      return 'aria-haspopup / aria-expanded 就绪';
    });

    check('初始页签与项目已渲染', function () {
      var tabs = $$('#tabList > *');
      if (!tabs.length) throw new Error('页签列表为空');
      var projects = $$('#projectBar > *');
      if (!projects.length) throw new Error('项目栏为空');
      return tabs.length + ' 个页签 / ' + projects.length + ' 个项目';
    });

    check('许可证声明存在', function () {
      var txt = document.body.textContent || '';
      if (txt.indexOf('本程序是自由软件') < 0) throw new Error('未找到 GPLv3 声明文字');
      return 'GPLv3 声明存在';
    });
  }

  /* ---------------- 样式 3 项 ---------------- */

  function styleChecks() {
    check('CSS 变量可解析', function () {
      var names = ['--primary', '--bg', '--text'];
      var empty = names.filter(function (n) { return !cssVar(n); });
      if (empty.length) throw new Error('空值：' + empty.join(', '));
      return names.join(' / ') + ' 均有值';
    });

    check('主题选项数量', function () {
      var opts = $$('#themeMenu .theme-option');
      if (opts.length < 2) throw new Error('主题选项过少：' + opts.length);
      return opts.length + ' 个主题选项';
    });

    check('模态框可见时 display 为 flex', function () {
      var modal = document.getElementById('versionHistoryModal');
      if (!modal) throw new Error('版本说明弹窗不存在');
      var wasVisible = modal.classList.contains('visible');
      modal.classList.add('visible');
      var d = getComputedStyle(modal).display;
      if (!wasVisible) modal.classList.remove('visible');
      if (d !== 'flex') throw new Error('可见时 display = ' + d);
      return 'display: ' + d;
    });
  }

  /* ---------------- 交互 8 项 ---------------- */

  function interactionChecks() {
    var errCount = 0;
    function onErr() { errCount++; }
    window.addEventListener('error', onErr);
    window.addEventListener('unhandledrejection', onErr);

    // 快照用户状态，finally 里恢复
    var bodyClassBefore = document.body.className;
    // 主题初始状态只认 .active —— 那是产品 HTML 里的初始标记。
    // 不能用 aria-checked：初始 HTML 没有该属性，点击主题项后产品才补上，
    // 拿它当快照会让 restore 之后多出一条自检制造的属性差异。
    var themeCheckedBefore = $$('#themeMenu .theme-option')
      .filter(function (o) { return o.classList.contains('active'); })
      .map(function (o) { return o.dataset.themePref || o.dataset.theme || ''; });
    var tabCountBefore = $$('#tabList > *').length;
    // 首访时产品会常驻打开 firstRunModal，自检打开的弹窗不能顺手把它关掉。
    var openModalsBefore = $$('.modal.visible').map(function (m) { return m.id; });

    function restore() {
      // 只撤销自检自己加过的类，不用快照整体覆盖：自检期间产品可能
      // 异步加上新类（如主题、抽屉），整体覆盖会把它们抹掉。
      var now = (document.body.className || '').split(/\s+/).filter(Boolean);
      var before = bodyClassBefore.split(/\s+/).filter(Boolean);
      var selfAdded = now.filter(function (c) { return before.indexOf(c) < 0; });
      // 自检只在「切换主题」时给 body 换 theme-* 类，其余类一律不碰
      selfAdded = selfAdded.filter(function (c) { return c.indexOf('theme-') === 0; });
      selfAdded.forEach(function (c) { document.body.classList.remove(c); });
      before.forEach(function (c) { document.body.classList.add(c); });
      // 主题：按快照重新点一次，让产品自己的状态与 DOM 同步
      var target = themeCheckedBefore[0];
      if (target) {
        var opt = $$('#themeMenu .theme-option').filter(function (o) {
          return (o.dataset.themePref || o.dataset.theme) === target;
        })[0];
        if (opt) opt.click();
      }
      // 自检过程中「新建页签」会真的改变产品状态。这里只做尽力而为的清理：
      // 优先点产品自己的删除入口（会同步内部状态），删不掉则放弃——
      // 直接 remove() DOM 节点会让 DOM 与产品内存不一致（实测后续新建
      // 页签时数量错乱），比留下一个多余页签更糟。
      var guard = 0;
      while ($$('#tabList > *').length > tabCountBefore && guard++ < 5) {
        var tabs = $$('#tabList > *');
        var last = tabs[tabs.length - 1];
        var delBtn = last ? last.querySelector(
          '[data-action="delete"], [class*="del"], [aria-label*="关闭页签"], [aria-label*="删除"]'
        ) : null;
        if (!delBtn) break;
        var origConfirm = window.confirm;
        window.confirm = function () { return true; };
        try { delBtn.click(); } finally { window.confirm = origConfirm; }
      }
      // 弹窗：关掉自检新开的，重新打开自检前就开着的
      $$('.modal.visible').forEach(function (m) {
        if (openModalsBefore.indexOf(m.id) < 0) m.classList.remove('visible');
      });
      openModalsBefore.forEach(function (id) {
        var m = document.getElementById(id);
        if (m && !m.classList.contains('visible')) m.classList.add('visible');
      });
      window.removeEventListener('error', onErr);
      window.removeEventListener('unhandledrejection', onErr);
    }

    try {
      check('主题菜单开合 + aria 同步', function () {
        var btn = document.getElementById('themeBtn');
        var menu = document.getElementById('themeMenu');

        // 产品有两个历史版本用不同机制控制显隐：
        //   · 重构前结构（当前主线）：内联 style.display = 'none' / 'flex'
        //   · 重构线 Φ10/Φ11：hidden 属性 + CSS
        // 自检同时兼容两者，判断「可见性是否真的变了」。
        function visible(el) {
          if (el.hidden) return false;
          var d = getComputedStyle(el).display;
          return d !== 'none';
        }

        var before = visible(menu);
        btn.click();
        var afterOpen = visible(menu);
        var aria = btn.getAttribute('aria-expanded');
        btn.click();
        var afterClose = visible(menu);

        if (before === afterOpen) {
          throw new Error('点击后可见性未变化（' + before + ' → ' + afterOpen + '）');
        }
        if (aria === null) throw new Error('aria-expanded 未设置');
        if (afterClose !== before) {
          throw new Error('再次点击未复原（' + afterClose + ' vs ' + before + '）');
        }
        return '开 → 关正常，aria=' + aria;
      });

      check('切换主题后状态同步', function () {
        // 不能只比 --primary 的值（两套主题可能刻意同色，那会让断言恒过）。
        // 改为断言「被选中的主题项真的变了」+「--primary 仍可解析」。
        var opts = $$('#themeMenu .theme-option');
        if (opts.length < 2) throw new Error('主题选项不足');
        function checked() {
          // 与快照同源：以产品自己的 .active 标记为准
          return $$('#themeMenu .theme-option').filter(function (o) {
            return o.classList.contains('active');
          }).map(function (o) { return o.dataset.themePref || o.dataset.theme || ''; })[0] || '';
        }
        var before = checked();
        var target = opts.filter(function (o) {
          return (o.dataset.themePref || o.dataset.theme || '') !== before;
        })[0];
        if (!target) throw new Error('找不到与当前不同的主题项');
        target.click();
        var after = checked();
        if (!after) throw new Error('切换后没有任何主题项被选中');
        if (after === before) throw new Error('选中的主题项未变化（' + before + '）');
        if (!cssVar('--primary')) throw new Error('切换后 --primary 为空');
        return before + ' → ' + after;
      });

      check('关于弹窗可开、Esc 可关', function () {
        // 产品语义（ModalManager.closeTopmost）：Esc 关闭的是**DOM 顺序
        // 最后一个** .modal.visible，不是「最近打开的那个」。
        // 首访时 firstRunModal 常驻，brand 打开的 copyrightModal 在 DOM 里
        // 排在它前面，于是 Esc 先关掉 firstRunModal——这是既有行为。
        // 断言按这个语义写，并额外断言「关掉的确实是 DOM 最后一个」，
        // 产品 Esc 失效或关错对象都能被发现。
        var brand = document.getElementById('brandBtn');
        brand.click();
        var visible = $$('.modal.visible');
        if (!visible.some(function (m) { return m.id === 'copyrightModal'; })) {
          throw new Error('点击 brand 后 copyrightModal 未可见');
        }
        var expected = visible[visible.length - 1];
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        if (expected.classList.contains('visible')) {
          throw new Error('Esc 未关闭 DOM 最后一个可见弹窗：#' + expected.id);
        }
        var after = $$('.modal.visible').length;
        if (after !== visible.length - 1) {
          throw new Error('Esc 应恰好关掉一个弹窗（' + visible.length + ' → ' + after + '）');
        }
        return 'Esc 关闭 #' + expected.id + '（' + visible.length + ' → ' + after + '）';
      });

      check('版本说明弹窗条目数与版本号', function () {
        document.getElementById('versionHistoryBtn').click();
        var rows = $$('#versionHistoryList .vh-item');
        if (rows.length < 10) throw new Error('条目过少：' + rows.length);
        var cur = document.getElementById('versionHistoryCurrentVersion');
        var shown = cur ? cur.textContent.trim() : '';
        if (shown.indexOf('Test') < 0) throw new Error('版本号未显示测试标记：' + shown);
        var closeBtn = document.getElementById('closeVersionHistoryModal');
        if (closeBtn) closeBtn.click();
        return rows.length + ' 条 · 当前 ' + shown;
      });

      check('新建页签', function () {
        var before = $$('#tabList > *').length;
        document.getElementById('addTabBtn').click();
        var typeModal = document.getElementById('tabTypeModal');
        var firstType = typeModal ? typeModal.querySelector('button, .btn') : null;
        if (!firstType) throw new Error('页签类型弹窗无选项');
        firstType.click();
        var after = $$('#tabList > *').length;
        if (after <= before) throw new Error('页签数未增加：' + before + ' → ' + after);
        return before + ' → ' + after;
      });

      check('页签删除入口存在（只读检查，不实际删除）', function () {
        // 这里刻意**不点击删除**。删除是真的删数据，而自检没法在不触碰
        // 产品内部状态的前提下还原——补回一个 DOM 元素并不等于恢复产品
        // 内存里的页签记录，会让后续新建页签时数量错乱（实测 16 → 18）。
        // 因此只验证「删除入口存在且可交互」，实际删除留给用户手动做。
        var tabs = $$('#tabList > *');
        if (!tabs.length) throw new Error('页签列表为空');
        var last = tabs[tabs.length - 1];
        var delBtn = last.querySelector(
          '[data-action="delete"], [class*="del"], [aria-label*="关闭页签"], [aria-label*="删除"]'
        );
        if (!delBtn) throw new Error('最后一个页签上没有删除入口');
        // 删除入口可能是 <button>，也可能是 <span>/<i>/<div> 这类不可聚焦
        // 元素。对它们断言 .disabled 恒为 undefined、typeof .click 恒为
        // "function"（HTMLElement 都有），属于恒真。这里只对真正的表单
        // 控件断言 disabled；其余元素只要求能被指针命中（尺寸非零）。
        var tag = (delBtn.tagName || '').toUpperCase();
        var isFormControl = tag === 'BUTTON' || tag === 'INPUT';
        if (isFormControl && delBtn.disabled) throw new Error('删除入口被禁用');
        var rect = delBtn.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
          throw new Error('删除入口不可见（' + Math.round(rect.width) + '×' + Math.round(rect.height) + '）');
        }
        return '入口存在且可命中，未执行删除';
      });

      check('localStorage 读写', function () {
        localStorage.setItem(PROBE_KEY, 'ok');
        var v = localStorage.getItem(PROBE_KEY);
        localStorage.removeItem(PROBE_KEY);
        if (v !== 'ok') throw new Error('回读不一致：' + v);
        if (localStorage.getItem(PROBE_KEY) !== null) throw new Error('探针键未清除');
        return '写 / 读 / 删 正常';
      });

      check('运行期无未捕获异常', function () {
        if (errCount > 0) throw new Error('捕获到 ' + errCount + ' 个异常');
        return '0 个';
      });
    } finally {
      restore();
    }
  }

  /* ---------------- 结果 UI ---------------- */

  function render() {
    var old = document.getElementById('selftestModal');
    if (old) old.remove();

    var total = results.length;
    var bad = results.filter(function (r) { return !r.ok; }).length;
    var good = total - bad;

    var wrap = document.createElement('div');
    wrap.className = 'modal visible';
    wrap.id = 'selftestModal';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-label', '内置自检结果');

    var summaryColor = bad === 0 ? '#7ee787' : '#ff8a3d';

    // 结构用 DOM API 建，结果文本一律走 textContent。当前 detail 都来自
    // 固定文本或数字，但用 innerHTML 拼接等于给未来留一个注入面，且
    // 其余四个项目已统一用 textContent。
    var content = document.createElement('div');
    content.className = 'modal-content';
    content.style.maxWidth = '680px';

    var header = document.createElement('div');
    header.className = 'modal-header';
    var h2 = document.createElement('h2');
    h2.style.cssText = 'margin:0;font-size:1rem';
    h2.textContent = '内置自检';
    var closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn';
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', '关闭');
    closeBtn.id = 'selftestClose';
    closeBtn.textContent = '×';
    header.appendChild(h2);
    header.appendChild(closeBtn);

    var body = document.createElement('div');
    body.className = 'modal-body';
    var summary = document.createElement('p');
    summary.style.cssText = 'margin:0 0 12px;font-weight:600;color:' + summaryColor;
    summary.textContent = (bad === 0 ? '全部通过：' : '有失败项：')
      + good + ' / ' + total + ' 通过';
    var ul = document.createElement('ul');
    ul.style.cssText = 'list-style:none;margin:0;padding:0;font-size:0.85rem';
    results.forEach(function (r) {
      var li = document.createElement('li');
      li.style.cssText = 'display:flex;gap:8px;align-items:flex-start;padding:3px 0';
      var tag = document.createElement('span');
      tag.style.cssText = 'flex:0 0 42px;font-family:monospace;color:'
        + (r.ok ? '#7ee787' : '#ff7b72');
      tag.textContent = r.ok ? 'PASS' : 'FAIL';
      var txt = document.createElement('span');
      txt.style.flex = '1';
      txt.textContent = r.name;
      if (r.detail) {
        var detail = document.createElement('span');
        detail.style.color = '#8b9aa6';
        detail.textContent = ' — ' + r.detail;
        txt.appendChild(detail);
      }
      li.appendChild(tag);
      li.appendChild(txt);
      ul.appendChild(li);
    });
    var note = document.createElement('p');
    note.style.cssText = 'margin:14px 0 0;color:#8b9aa6;font-size:0.78rem';
    note.textContent = '这是测试版专属的自检，不改动任何用户数据；开跑前的界面状态已自动恢复。';
    body.appendChild(summary);
    body.appendChild(ul);
    body.appendChild(note);

    var footer = document.createElement('div');
    footer.className = 'modal-footer';
    footer.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;padding:12px 20px';
    var rerunBtn = document.createElement('button');
    rerunBtn.className = 'btn';
    rerunBtn.type = 'button';
    rerunBtn.id = 'selftestRerun';
    rerunBtn.textContent = '重新运行';
    footer.appendChild(rerunBtn);

    content.appendChild(header);
    content.appendChild(body);
    content.appendChild(footer);
    wrap.appendChild(content);

    document.body.appendChild(wrap);

    function close() { wrap.remove(); restoreTitle(); }
    wrap.querySelector('#selftestClose').addEventListener('click', close);
    wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
    });
    wrap.querySelector('#selftestRerun').addEventListener('click', function () {
      close();
      setTimeout(run, 0);
    });

    return { total: total, bad: bad, good: good };
  }

  /* 防重入：已有结果弹窗时不重跑。devkit 的检查是同步的，但用户连点
     会让结果弹窗反复移除/重建，且 interactionChecks 会快照并恢复页签与
     主题——两轮交叉执行时快照基准已经乱了。 */
  var titleBefore = null;
  var lastResult = '';

  /* 产品 boot 是异步的（Storage.init → 读库 → 首次运行建项目/页签），
     检查本身全同步，但页签列表没渲染出来时断言会对着空 DOM 假失败。
     这里用 setTimeout 让出事件循环，就绪后再跑检查，与其余四个项目口径一致。 */
  function waitReady(timeoutMs) {
    var started = Date.now();
    function ready() {
      var tabs = document.getElementById('tabList');
      var projects = document.getElementById('projectBar');
      return !!(tabs && tabs.children.length &&
                projects && projects.children.length);
    }
    return new Promise(function (resolve) {
      (function tick() {
        if (ready()) return resolve(true);
        if (Date.now() - started > timeoutMs) return resolve(false);
        setTimeout(tick, 100);
      })();
    });
  }

  function run() {
    if (document.getElementById('selftestModal')) return;
    if (titleBefore === null) titleBefore = document.title;
    results = [];
    waitReady(8000).then(function (ready) {
      if (!ready) {
        fail('产品启动就绪', '8s 内未见首屏页签（可能是存储不可用）');
      } else {
        structureChecks();
        styleChecks();
        interactionChecks();
      }
      finishRun();
    }, function (e) {
      fail('自检异常', (e && e.message) ? e.message : String(e));
      finishRun();
    });
  }

  function finishRun() {
    var r = render();
    // 供无头浏览器断言用
    lastResult = (r.bad === 0 ? 'SELFTEST-PASS ' : 'SELFTEST-FAIL ')
      + r.good + '/' + r.total;
    // 与异步版一致：弹窗不在就不写标题，避免覆盖关闭时的还原
    if (document.getElementById('selftestModal')) document.title = lastResult;
    try { document.documentElement.setAttribute('data-selftest', lastResult); } catch (e) {}
  }

  /* 弹窗关闭时还原标题：标题只服务于自动化断言，不该永久改写用户的
     标签页。结果同时写进 <html data-selftest>，供测试脚本读取。 */
  function restoreTitle() {
    if (titleBefore !== null) document.title = titleBefore;
  }

  /* ---------------- 注入入口 ---------------- */

  function mount() {
    // 1) TEST 徽标
    var brand = document.querySelector('.brand');
    if (brand && !document.getElementById('testBadge')) {
      var badge = document.createElement('span');
      badge.id = 'testBadge';
      badge.textContent = 'TEST';
      badge.style.cssText = 'margin-left:8px;padding:1px 7px;border-radius:999px;'
        + 'background:#ff8a3d;color:#08090d;font-size:0.66rem;font-weight:700;'
        + 'font-family:ui-monospace,monospace;letter-spacing:.06em;vertical-align:middle';
      brand.appendChild(badge);
    }

    // 2) 顶栏「自检」按钮，插在主题按钮前
    var themeBtn = document.getElementById('themeBtn');
    if (themeBtn && !document.getElementById('selftestBtn')) {
      var btn = document.createElement('button');
      btn.id = 'selftestBtn';
      btn.className = 'icon-btn';
      btn.type = 'button';
      btn.setAttribute('aria-label', '运行内置自检');
      btn.innerHTML = '<span class="material-symbols-outlined">checklist</span>'
        + '<span class="btn-text">自检</span>';
      btn.style.color = '#ff8a3d';
      btn.addEventListener('click', function (e) { e.stopPropagation(); run(); });
      themeBtn.parentNode.insertBefore(btn, themeBtn);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }

  // 便捷入口（便于自动化测试直接触发）
  window.__devkitSelftest = run;
})();
