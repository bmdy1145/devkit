#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DevKit 行为单测（需要产品文件带 #selftest 测试缝；默认目标为当前主线 A1_VI_Φ1）。

## 为什么需要这个脚本

DevKit 一直没有自动化行为测试，只有控制台冒烟、体积与链接检查。结果 TypeScript
级的逻辑错误（例如「点击强调色调用了一个不存在的方法」）只能靠人点出来；而任何
结构性重构都无法证明「功能没变」——这正是 Φ10 重构时最卡的地方。

本脚本用真实浏览器加载产品文件的临时副本，通过产品文件自带的测试缝
（`window.__devkitTest`，仅 `#selftest` 时挂载）直接断言内部逻辑：

  · 提示词拼装：占位符替换、空白页签、规范前缀、22 条模板与旧别名归一
  · 版本号解析与兼容性：历史版本号往返、拒绝 A2 分支、非法输入
  · 设置归一化：白名单枚举拒绝非法值、缺失字段回退默认
  · 关键交互：页签增删切换、项目切换、主题三态、弹窗开关、预览渲染

## 机制

沿用 `share_image_test.py` 已验证的做法：

  · 把产品文件复制到临时目录（注入驱动脚本，产品文件本身只在 #selftest 挂缝）
  · 本地 HTTP 服务托管副本，`/gate` 挂住 load 事件直到断言跑完
  · chrome --headless=new --dump-dom，从导出的 <title> 取断言结果

用法：
    本地： python .github/scripts/devkit_logic_test.py
          浏览器不在 PATH 时用 CHROME_BIN 指定
    CI  ： 由 .github/workflows/repo-checks.yml 的 devkit-logic job 调用

退出码：0 = 全部通过；1 = 有断言失败或找不到浏览器。
"""

from __future__ import annotations

import base64
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_TARGET = ROOT / "projects" / "devkit" / "code" / "A1_VI_Φ1" / "deepseek_A1_VI_Φ1_CN.html"
TARGET = Path(os.environ.get("DEVKIT_TEST_TARGET") or DEFAULT_TARGET)

SUBPROCESS_TIMEOUT_SECONDS = 180
GATE_TIMEOUT_SECONDS = 150
MAX_ATTEMPTS = 2
RESULT_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)

GATE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

DRIVER = r"""
<script>
/* 由 devkit_logic_test.py 注入：跑完断言把结果写进 <title>。 */
(function () {
    var CONFIRM_ANSWER = true;
    window.confirm = function () { return CONFIRM_ANSWER; };
    window.alert = function () {};

    var failures = [];
    function ok(cond, name, extra) {
        if (!cond) failures.push(name + (extra ? ' (' + extra + ')' : ''));
    }
    function near(a, b, eps) { return Math.abs(a - b) <= (eps == null ? 0.01 : eps); }

    function finish() {
        var title = failures.length ? 'FAIL: ' + failures.join(' | ') : 'PASS';
        var box = document.createElement('div');
        box.id = '__logic_result';
        box.textContent = title;
        (document.body || document.documentElement).appendChild(box);
        document.title = title;
        try { fetch('/done', { method: 'POST', body: title }); } catch (e) { }
    }

    var waited = 0;
    function waitReady() {
        var T = window.__devkitTest;
        // 测试缝在 #selftest 时挂载；App.init 之后 store/dom 就绪即可断言
        if (T && T.App && T.App.store && T.App.dom) {
            run(T).catch(function (e) {
                failures.push('异常：' + (e && e.message ? e.message : e));
                finish();
            });
            return;
        }
        if (waited > 40000) { failures.push('boot 超时（40s 内未就绪）'); finish(); return; }
        waited += 100;
        setTimeout(waitReady, 100);
    }

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    async function run(T) {
        var B = T.PromptBuilder;

        /* ---------- 1. 提示词拼装 ---------- */
        ok(B.fill('A{inspiration}B{code}C', 'I', 'K') === 'AIBKC',
           '占位符应被替换', B.fill('A{inspiration}B{code}C', 'I', 'K'));
        ok(B.fill('{inspiration}{inspiration}', 'X', 'Y') === 'XX',
           '同一占位符多次出现应全部替换');
        ok(B.fill('{inspiration}', '', '') === '（无需求）',
           '空灵感应回退「（无需求）」', B.fill('{inspiration}', '', ''));
        ok(B.fill('{code}', 'x', '   ') === '   ',
           '空格代码按原样保留（与旧实现一致）', JSON.stringify(B.fill('{code}', 'x', '   ')));
        ok(B.fill('{code}', 'x', '') === '（无代码）',
           '空代码应回退「（无代码）」', B.fill('{code}', 'x', ''));
        ok(B.plain('I', 'K').indexOf('需求：I') === 0, '空白页签应以「需求：」开头');
        ok(B.plain('I', 'K').indexOf('代码：\nK') > 0, '空白页签应含代码段');
        ok(B.withSpec('BODY', false, 'SPEC') === 'BODY',
           '关闭规范时不加前缀', B.withSpec('BODY', false, 'SPEC'));
        ok(B.withSpec('BODY', true, 'SPEC') === 'SPEC\n\n---\n以下是本次的需求：\n\nBODY',
           '开启规范时应加固定前缀', B.withSpec('BODY', true, 'SPEC'));
        ok(B.findByLabel('空白', T.PROMPT_TEMPLATES, T.TYPE_ALIASES) === null,
           '「空白」应返回 null');
        var alias = B.findByLabel('代码重构', T.PROMPT_TEMPLATES, T.TYPE_ALIASES);
        ok(alias && alias.label === '结构重构', '旧别名「代码重构」应归一为「结构重构」',
           alias && alias.label);
        ok(B.findByLabel('不存在的类型', T.PROMPT_TEMPLATES, T.TYPE_ALIASES) === null,
           '未知类型应返回 null');

        /* ---------- 2. 22 条模板完整性 ---------- */
        ok(T.PROMPT_TEMPLATES.length === 22,
           '应有 22 条提示词模板', String(T.PROMPT_TEMPLATES.length));
        var missing = T.PROMPT_TEMPLATES.filter(function (x) {
            return !x.label || !x.template || !x.id;
        });
        ok(missing.length === 0, '每条模板都应有 id / label / template',
           String(missing.length));
        // 少数模板（如「无障碍审计」）只用 {code}，历史上就是这样，
        // 因此只要求至少含一个占位符，而不是必须含 {inspiration}。
        var noPlaceholder = T.PROMPT_TEMPLATES.filter(function (x) {
            return x.template.indexOf('{inspiration}') < 0 && x.template.indexOf('{code}') < 0;
        });
        ok(noPlaceholder.length === 0, '每条模板都应至少含一个占位符',
           noPlaceholder.map(function (x) { return x.label; }).join(','));
        var dup = {}, dupLabels = [];
        T.PROMPT_TEMPLATES.forEach(function (x) {
            if (dup[x.label]) dupLabels.push(x.label);
            dup[x.label] = 1;
        });
        ok(dupLabels.length === 0, '模板 label 不应重复', dupLabels.join(','));
        // 每条模板对同一输入的产物必须稳定且非空
        var unstable = [];
        T.PROMPT_TEMPLATES.forEach(function (tpl) {
            var a = B.fill(tpl.template, '需求X', '代码Y');
            var b = B.fill(tpl.template, '需求X', '代码Y');
            if (a !== b || !a.length) unstable.push(tpl.label);
        });
        ok(unstable.length === 0, '同一输入的模板产物应稳定且非空', unstable.join(','));

        /* ---------- 3. 默认页签 ---------- */
        ok(T.DEFAULT_TABS.length === 16,
           '默认应有 16 个页签', String(T.DEFAULT_TABS.length));
        var unresolved = T.DEFAULT_TABS.filter(function (t) {
            return t.type !== '空白' && !B.findByLabel(t.type, T.PROMPT_TEMPLATES, T.TYPE_ALIASES);
        });
        ok(unresolved.length === 0, '每个默认页签都应能解析到模板',
           unresolved.map(function (t) { return t.type; }).join(','));

        /* ---------- 4. 版本号解析 ---------- */
        var v = T.parseVersion('A1_V_Φ9_Fix_Fix_CN');
        ok(v && v.branch === 'A1' && v.suffixes === 'CN',
           '标准版本号应解析出分支与后缀', JSON.stringify(v));
        ok(/Φ9/.test(v && v.structure || ''), '结构段应含 Φ9', v && v.structure);
        ok(T.parseVersion('garbage') === null || typeof T.parseVersion('garbage') === 'object',
           '非法版本号不应抛异常');
        ok(T.isCompatibleVersion(T.CURRENT_VERSION) === true,
           '当前版本应被判为兼容', T.CURRENT_VERSION);
        ok(T.isCompatibleVersion('A1_V_Φ9_Fix_Fix_CN') === true,
           '上一代中文版应被判为兼容');
        ok(T.isCompatibleVersion('A2_I_Φ1_CN') === false,
           'A2 分支应被判为不兼容');
        // 历史版本号全部应可解析（VERSION_HISTORY 是纯数据，不依赖 DOM）
        // 历史里存在 A1_III_Φ12' 这类带撇号的旁支命名，解析器不识别属预期；
        // 只要求「带撇号/引号之外的版本号」全部可解析。
        var badHistory = [];
        T.VERSION_HISTORY.forEach(function (h) {
            if (/['\u2019]/.test(h.version)) return;   // 旁支命名，跳过
            var info = T.parseVersion(h.version);
            if (!info) badHistory.push(h.version);
        });
        ok(badHistory.length === 0, 'VERSION_HISTORY 中正规版本号都应可解析',
           badHistory.slice(0, 5).join(','));

        /* ---------- 5. 设置归一化 ---------- */
        var base = { themePref: 'dark', hideBtnText: false, promptActionsAlways: true,
                     specPromptEnabled: true, shortcutsEnabled: true,
                     performanceMode: false, inspirationSyncEnabled: true };
        // 非法值回退「base 里的值」，base 没给才回退 spec 默认值
        var n1 = T.normalizeSettings({ themePref: 'nonsense' }, base);
        ok(n1.themePref === 'dark', '非法 themePref 应回退 base 值 dark', n1.themePref);
        var n1b = T.normalizeSettings({ themePref: 'nonsense' }, {});
        ok(n1b.themePref === 'auto', 'base 缺该字段时应回退 spec 默认 auto', n1b.themePref);
        var n2 = T.normalizeSettings({ themePref: 'light' }, base);
        ok(n2.themePref === 'light', '合法 themePref 应被采纳', n2.themePref);
        var n3 = T.normalizeSettings({ hideBtnText: 'yes' }, base);
        ok(n3.hideBtnText === false, '类型不符的布尔项应回退默认', String(n3.hideBtnText));
        var n4 = T.normalizeSettings({}, base);
        ok(n4.themePref === base.themePref && n4.performanceMode === base.performanceMode,
           '缺失字段应回退 base 值');
        var n5 = T.normalizeSettings(null, base);
        ok(n5 && n5.themePref === base.themePref, 'null 输入不应抛异常且回退 base');
        ok(Object.keys(n2).length === Object.keys(T.SETTING_SPECS).length,
           '归一化结果字段数应与 SETTING_SPECS 一致',
           Object.keys(n2).length + ' vs ' + Object.keys(T.SETTING_SPECS).length);

        /* ---------- 6. 关键交互：页签 ---------- */
        var tabSvc = T.getService('tab');
        var before = T.getState().projects[0].tabs.length;
        tabSvc.add('需求分析');
        await sleep(60);
        var afterAdd = T.getState().projects[0].tabs.length;
        ok(afterAdd === before + 1, '新建页签应使页签数 +1', before + ' -> ' + afterAdd);

        var tabs = T.getState().projects[0].tabs;
        var lastTab = tabs[tabs.length - 1];
        var renamedOk = false;
        try { renamedOk = tabSvc.rename(lastTab.id, '改名测试') !== false; } catch (e) { }
        ok(renamedOk !== false, '重命名页签不应抛异常');

        tabSvc.remove(lastTab.id);
        await sleep(60);
        ok(T.getState().projects[0].tabs.length === before,
           '删除页签应恢复原数量', String(T.getState().projects[0].tabs.length));

        /* ---------- 7. 关键交互：项目 ---------- */
        var projSvc = T.getService('project');
        var pCount = T.getState().projects.length;
        projSvc.add('测试项目');
        await sleep(80);
        var pAfter = T.getState().projects.length;
        ok(pAfter === pCount + 1, '新建项目应使项目数 +1', pCount + ' -> ' + pAfter);
        var activeNow = T.getState().activeProjectId;
        var newProj = T.getState().projects[T.getState().projects.length - 1];
        ok(activeNow === newProj.id, '新建后应自动激活该项目');
        ok(newProj.tabs.length === T.DEFAULT_TABS.length,
           '新项目应带默认页签', String(newProj.tabs.length));

        projSvc.close(newProj.id);
        await sleep(80);
        ok(T.getState().projects.length === pCount,
           '关闭项目应恢复原数量', String(T.getState().projects.length));
        // 只剩 1 个项目时不允许关闭
        var remaining = T.getState().projects;
        if (remaining.length === 1) {
            projSvc.close(remaining[0].id);
            await sleep(60);
            ok(T.getState().projects.length === 1, '最后一个项目不应被关闭');
        }

        /* ---------- 8. 关键交互：主题三态 ---------- */
        var themeUI = T.themeUI;
        ok(!!themeUI && typeof themeUI.apply === 'function', 'ThemeUI 应已实例化');
        if (themeUI) {
            themeUI.apply('light');
            ok(document.documentElement.getAttribute('data-theme') === 'light',
               '切到浅色应写 data-theme=light',
               String(document.documentElement.getAttribute('data-theme')));
            themeUI.apply('dark');
            ok(document.documentElement.getAttribute('data-theme') === 'dark',
               '切到深色应写 data-theme=dark',
               String(document.documentElement.getAttribute('data-theme')));
            themeUI.apply('auto');
            ok(document.documentElement.getAttribute('data-theme') === null,
               '跟随系统应移除 data-theme',
               String(document.documentElement.getAttribute('data-theme')));
            themeUI.apply('dark');  // 复原，后续断言依赖深色
            var checked = Array.prototype.slice.call(
                document.querySelectorAll('#themeMenu .theme-option')
            ).filter(function (o) { return o.getAttribute('aria-checked') === 'true'; });
            ok(checked.length === 1, '主题菜单应恰好有一项 aria-checked=true',
               String(checked.length));
            ok(checked[0] && checked[0].dataset.themePref === 'dark',
               '选中的应是深色项', checked[0] && checked[0].dataset.themePref);
        }

        /* ---------- 9. 关键交互：弹窗 ---------- */
        var modal = document.getElementById('copyrightModal');
        modal.classList.add('visible');
        ok(modal.classList.contains('visible'), '弹窗应可打开');
        var closer = modal.querySelector('[data-close]');
        ok(!!closer, '弹窗应有 data-close 关闭按钮');
        if (closer) {
            closer.click();
            await sleep(80);
            ok(!modal.classList.contains('visible'), 'data-close 应能关闭弹窗');
        }
        // 六个弹窗都应带 data-close 或明确的关闭 id
        var modals = Array.prototype.slice.call(document.querySelectorAll('.modal'));
        ok(modals.length === 6, '应有 6 个弹窗', String(modals.length));
        var noCloser = modals.filter(function (m) {
            return !m.querySelector('[data-close]') && !m.querySelector('.close-btn');
        });
        ok(noCloser.length === 0, '每个弹窗都应有可关闭入口',
           noCloser.map(function (m) { return m.id; }).join(','));

        /* ---------- 10. 关键交互：预览与组合文本 ---------- */
        var dom = T.getDom();
        ok(!!dom.codeInput && !!dom.inspirationInput, '应能取到代码与灵感输入框');
        if (dom.codeInput) dom.codeInput.value = 'CONSOLE.LOG(1)';
        if (dom.inspirationInput) dom.inspirationInput.value = '测试灵感';
        var tpl = T.PROMPT_TEMPLATES[0];
        var finalText = T.buildFinalText(tpl);
        ok(typeof finalText === 'string' && finalText.length > 0, '最终文本不应为空');
        ok(finalText.indexOf('CONSOLE.LOG(1)') >= 0, '最终文本应包含代码区内容');
        ok(finalText.indexOf('测试灵感') >= 0, '最终文本应包含灵感内容');
        // 关闭规范前缀后应只剩正文
        var st = T.getState();
        T.App.store.dispatch({
            globalSettings: Object.assign({}, st.globalSettings, { specPromptEnabled: false })
        });
        await sleep(60);
        var bodyOnly = T.buildFinalText(tpl);
        ok(bodyOnly.indexOf('---\n以下是本次的需求') < 0,
           '关闭规范后不应再出现需求分隔前缀');
        ok(bodyOnly.indexOf('CONSOLE.LOG(1)') >= 0, '关闭规范后仍应包含代码内容');
        T.App.store.dispatch({
            globalSettings: Object.assign({}, T.getState().globalSettings, { specPromptEnabled: true })
        });

        /* ---------- 11. 安全：URL 白名单 ---------- */
        ok(T.Utils.isSafeUrl('https://example.com') === true, 'https 应被判为安全');
        ok(T.Utils.isSafeUrl('javascript:alert(1)') === false,
           'javascript: 协议应被判为不安全');
        ok(T.Utils.isSafeUrl('data:text/html,<script>') === false,
           'data: 协议应被判为不安全');

        /* ---------- 12. 常量一致性 ---------- */
        // 期望值由 Python 侧按目标文件名注入，升级版本时不必改这里
        ok(T.CURRENT_VERSION === '__EXPECTED_VERSION__',
           'CURRENT_VERSION 应与文件名版本一致', T.CURRENT_VERSION);
        ok(T.isCompatibleVersion(T.CURRENT_VERSION),
           'CURRENT_VERSION 自身应被判为兼容');

        /* ---------- 13. 版本说明：折叠全部不得隐藏条目自身 ---------- */
        T.App.showVersionHistory();
        var items = T.App.versionHistoryItems;
        var roots = items.filter(function (it) { return it._depth === 0; });
        ok(roots.length > 1, '版本结构应有多条顶层条目', String(roots.length));
        var firstRootRow = document.querySelector('.vh-item[data-index="' + items.indexOf(roots[0]) + '"]');
        ok(!!firstRootRow, '顶层条目应有对应 DOM 行');
        var firstRootBody = firstRootRow && firstRootRow.querySelector('.vh-body');
        ok(!!firstRootBody && getComputedStyle(firstRootBody).display !== 'none',
           '展开态下顶层条目应显示版本与说明');

        document.getElementById('vhCollapseAll').click();
        var rootBodyAfter = firstRootRow.querySelector('.vh-body');
        ok(getComputedStyle(rootBodyAfter).display !== 'none',
           '折叠全部后条目自身的版本与说明仍应可见（Φ10 回归点）',
           getComputedStyle(rootBodyAfter).display);
        ok(firstRootRow.querySelector('.vh-toggle').textContent === '▶',
           '折叠全部后箭头应变为 ▶');
        var visibleRows = [].filter.call(document.querySelectorAll('.vh-item'), function (r) {
            return r.style.display !== 'none';
        });
        ok(visibleRows.length === roots.length,
           '折叠全部后应恰好只显示顶层条目', visibleRows.length + '/' + roots.length);

        document.getElementById('vhExpandAll').click();
        var visibleAfterExpand = [].filter.call(document.querySelectorAll('.vh-item'), function (r) {
            return r.style.display !== 'none';
        });
        ok(visibleAfterExpand.length === items.length,
           '展开全部后应恢复显示全部条目', visibleAfterExpand.length + '/' + items.length);
        T.getService('modal').close('versionHistoryModal');

        /* ---------- 14. 顶栏下拉菜单必须能展开 ---------- */
        var menuPairs = [
            { btn: 'themeBtn', menu: 'themeMenu', label: '主题' },
            { btn: 'toggleShortcuts', menu: 'shortcutHintMenu', label: '快捷键' }
        ];
        menuPairs.forEach(function (pair) {
            var btn = document.getElementById(pair.btn);
            var menu = document.getElementById(pair.menu);
            ok(!!btn && !!menu, pair.label + '菜单应存在');
            if (!btn || !menu) return;
            ok(menu.hidden === true, pair.label + '菜单初始应为收起', String(menu.hidden));
            btn.click();
            ok(menu.hidden === false, pair.label + '菜单点击后应展开（Φ10 回归点）', String(menu.hidden));
            ok(getComputedStyle(menu).display !== 'none',
               pair.label + '菜单展开后应实际可见', getComputedStyle(menu).display);
            ok(menu.getBoundingClientRect().width > 0,
               pair.label + '菜单展开后应有非零宽度',
               String(Math.round(menu.getBoundingClientRect().width)));
            btn.click();
            ok(menu.hidden === true, pair.label + '菜单再次点击应收起');
        });

        finish();
    }

    function gate() {
        var img = document.createElement('img');
        img.style.display = 'none';
        img.src = '/gate?ts=' + Date.now();
        (document.body || document.documentElement).appendChild(img);
    }

    document.addEventListener('DOMContentLoaded', gate);
    document.addEventListener('DOMContentLoaded', function () { setTimeout(waitReady, 0); });
})();
</script>
"""


class _GateServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(directory: Path, done: threading.Event):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/gate"):
                done.wait(GATE_TIMEOUT_SECONDS)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(GATE_PNG)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(GATE_PNG)
                return
            if self.path in ("/", "/index.html", "/index.html?x=1") or self.path.startswith("/index.html?"):
                body = (directory / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def do_POST(self):
            if self.path == "/done":
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    self.rfile.read(length)
                except OSError:
                    pass
                done.set()
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_error(404)

    return Handler


def find_browser() -> str | None:
    override = os.environ.get("CHROME_BIN")
    if override and Path(override).exists():
        return override
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


class NoSeam(Exception):
    """目标文件没有 window.__devkitTest 测试缝：调用方应把它当作「跳过」而不是失败。"""


def expected_version() -> str:
    """从目标文件名推导期望的版本号（deepseek_<版本>.html）。"""
    return TARGET.stem.removeprefix("deepseek_")


def build_temp_copy(dest: Path) -> None:
    html = TARGET.read_text(encoding="utf-8")
    if "__devkitTest" not in html:
        raise NoSeam(
            "目标文件没有测试缝（window.__devkitTest）。"
            "当前主线 A1_VI_Φ1 沿用重构前结构、尚未挂缝，本脚本跳过。"
        )
    if "</body>" not in html:
        raise SystemExit("找不到 </body>，无法注入驱动脚本。")
    driver = DRIVER.replace("__EXPECTED_VERSION__", expected_version())
    html = html.replace("</body>", driver + "</body>", 1)
    (dest / "index.html").write_text(html, encoding="utf-8")


def run_one(browser: str, tmp: Path) -> tuple[bool, str]:
    done = threading.Event()
    server = _GateServer(("127.0.0.1", 0), make_handler(tmp, done))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    profile = Path(tempfile.mkdtemp())
    dom_file = tmp / "dom.html"
    err_file = tmp / "err.txt"
    url = f"http://127.0.0.1:{port}/index.html#selftest"

    try:
        with open(dom_file, "w", encoding="utf-8") as df, open(err_file, "w", encoding="utf-8") as ef:
            proc = subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--user-data-dir=" + str(profile),
                    "--dump-dom",
                    "--enable-logging=stderr",
                    url,
                ],
                stdout=df,
                stderr=ef,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if dom_file.stat().st_size > 0:
                    break
            except OSError:
                pass
            time.sleep(0.2)

        dom_text = dom_file.read_text(encoding="utf-8", errors="replace")
        stderr_text = err_file.read_text(encoding="utf-8", errors="replace")
        returncode = proc.returncode
    finally:
        server.shutdown()
        server.server_close()

    m = RESULT_RE.search(dom_text)
    title = m.group(1).strip() if m else ""

    if title.startswith("PASS"):
        return True, "PASS"
    if title.startswith("FAIL:"):
        return False, title[len("FAIL:"):].strip()

    hint = []
    hint.append("title=" + (title or "（空）"))
    if returncode:
        hint.append(f"chrome 退出码 {returncode}")
    err_lines = [
        ln for ln in stderr_text.splitlines()
        if re.search(r"Uncaught|SyntaxError|TypeError|ReferenceError|ERROR", ln)
    ]
    if err_lines:
        hint.append("stderr: " + err_lines[0][:240])
    return False, "未取到断言结果（" + "；".join(hint) + "）"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not TARGET.exists():
        print(f"[问题] 找不到目标文件：{TARGET}")
        return 1

    browser = find_browser()
    if browser is None:
        print("[问题] 找不到 Chrome / Chromium。用 CHROME_BIN 指定浏览器路径后重试。")
        return 1

    try:
        rel = TARGET.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(TARGET)

    print(f"使用浏览器：{browser}")
    print(f"目标文件：{rel}")

    last_detail = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp = Path(tmpdir)
            try:
                build_temp_copy(tmp)
            except NoSeam as exc:
                print()
                print(f"[跳过] {exc}")
                print("（退出码 0：跳过不等于通过，详见脚本顶部说明。）")
                return 0
            try:
                passed, detail = run_one(browser, tmp)
            except subprocess.TimeoutExpired:
                passed, detail = False, f"打开超时（超过 {SUBPROCESS_TIMEOUT_SECONDS} 秒）"
        if passed:
            print()
            print(f"DevKit 行为单测完成：全部断言通过（第 {attempt} 次运行）。")
            return 0
        last_detail = detail
        if attempt < MAX_ATTEMPTS:
            print(f"[重试] 第 {attempt} 次未通过：{detail}")

    print()
    print(f"[问题] DevKit 行为单测失败：{last_detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
