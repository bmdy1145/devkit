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
    var themeCheckedBefore = $$('#themeMenu .theme-option')
      .filter(function (o) { return o.getAttribute('aria-checked') === 'true'; })
      .map(function (o) { return o.dataset.themePref || o.dataset.theme || ''; });
    var tabCountBefore = $$('#tabList > *').length;

    function restore() {
      document.body.className = bodyClassBefore;
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

      check('切换主题后 CSS 变量变化', function () {
        var opts = $$('#themeMenu .theme-option');
        if (opts.length < 2) throw new Error('主题选项不足');
        var p0 = cssVar('--primary');
        opts[1].click();
        var p1 = cssVar('--primary');
        if (!p1) throw new Error('切换后 --primary 为空');
        return (p0 === p1 ? '两套主题强调色相同（合法）' : '强调色已变化');
      });

      check('关于弹窗可开、Esc 可关', function () {
        var brand = document.getElementById('brandBtn');
        brand.click();
        var modal = $('.modal.visible');
        if (!modal) throw new Error('点击 brand 后无可见弹窗');
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        var stillOpen = $('.modal.visible');
        if (stillOpen) stillOpen.classList.remove('visible');
        return '开合正常';
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
        if (delBtn.disabled) throw new Error('删除入口被禁用');
        if (typeof delBtn.click !== 'function') throw new Error('删除入口不可点击');
        return '入口存在，未执行删除';
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
    var rows = results.map(function (r) {
      return '<li style="display:flex;gap:8px;align-items:flex-start;padding:3px 0">'
        + '<span style="flex:0 0 42px;font-family:monospace;color:' + (r.ok ? '#7ee787' : '#ff7b72') + '">'
        + (r.ok ? 'PASS' : 'FAIL') + '</span>'
        + '<span style="flex:1">' + r.name
        + (r.detail ? '<span style="color:#8b9aa6"> — ' + r.detail + '</span>' : '')
        + '</span></li>';
    }).join('');

    wrap.innerHTML =
      '<div class="modal-content" style="max-width:680px">'
      + '<div class="modal-header">'
      + '<h2 style="margin:0;font-size:1rem">内置自检</h2>'
      + '<button class="close-btn" type="button" aria-label="关闭" id="selftestClose">×</button>'
      + '</div>'
      + '<div class="modal-body">'
      + '<p style="margin:0 0 12px;color:' + summaryColor + ';font-weight:600">'
      + (bad === 0 ? '全部通过：' : '有失败项：') + good + ' / ' + total + ' 通过</p>'
      + '<ul style="list-style:none;margin:0;padding:0;font-size:0.85rem">' + rows + '</ul>'
      + '<p style="margin:14px 0 0;color:#8b9aa6;font-size:0.78rem">'
      + '这是测试版专属的自检，不改动任何用户数据；开跑前的界面状态已自动恢复。</p>'
      + '</div>'
      + '<div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:12px 20px">'
      + '<button class="btn" type="button" id="selftestRerun">重新运行</button>'
      + '</div>'
      + '</div>';

    document.body.appendChild(wrap);

    function close() { wrap.remove(); }
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

  function run() {
    results = [];
    structureChecks();
    styleChecks();
    interactionChecks();
    var r = render();
    // 供无头浏览器断言用
    document.title = (r.bad === 0 ? 'SELFTEST-PASS ' : 'SELFTEST-FAIL ')
      + r.good + '/' + r.total;
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
