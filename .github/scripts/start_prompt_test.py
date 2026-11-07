#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persona Φ14「以角色形象开始对话 / 开始小说」的运行时单测。

## 验证什么

| # | 用例 |
|---|---|
| 1 | 12 个「类型 × 场景」组合生成的提示词两两不同，且各自含对应场景关键词 |
| 2 | 人设版含四段内容；空字段显示「（未填）」；other 非空时一并出现 |
| 3 | 起始提示词**不包含** FINALIZE_HINT 的收尾说明 |
| 4 | 对话类要求「以角色的第一句话开场」；小说/故事类要求「只写正文」 |
| 5 | 补充要求非空时出现在文中，为空时不产生空段 |
| 6 | 世界观版含世界观正文，且不含聊天记忆 |
| 7 | 主按钮文案随模式切换，三项文案同步切换 |
| 8 | 菜单向上展开（菜单底边不高于按钮上沿）且在视口内 |
| 9 | 点「开始对话」弹窗标题与场景数量正确；世界观下场景集不同 |
| 10 | 原「总结记忆进人设」仍生成含 FINALIZE_HINT 的提示词 |

## 机制

沿用 snapshot_other_test.py / share_image_test.py 已验证的做法：
临时副本 + 测试缝扩展 + 注入驱动 + 本地 HTTP 闸门 + --dump-dom 取 <title>。

用法：
    本地： python3 .github/scripts/start_prompt_test.py
    CI  ： 由 .github/workflows/repo-checks.yml 调用
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

DEFAULT_TARGET = ROOT / "projects" / "persona" / "code" / "A1_II_Φ14" / "deepseek_A1_II_Φ14_CN.html"
TARGET = Path(os.environ.get("PERSONA_TEST_TARGET") or DEFAULT_TARGET)

SUBPROCESS_TIMEOUT_SECONDS = 180
GATE_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 2
RESULT_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)

GATE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# 测试缝锚点：Φ14 selftest 对象里 StartUI 那一行
SEAM_ANCHOR = "            StartUI: StartUI,"

SEAM_EXTRA = """            StartUI: StartUI,
            /* 以下由 start_prompt_test.py 注入，仅测试用 */
            FINALIZE_HINT: FINALIZE_HINT,
            openStartMenu: openStartMenu,
            closeStartMenu: closeStartMenu,
            renderStartScenes: renderStartScenes,
            startMenuNode: startMenuNode,
            readEditorInto: readEditorInto,
            currentPrompt: currentPrompt,
            fillEditor: fillEditor,"""

DRIVER = r"""
<script>
(function () {
    window.confirm = function () { return true; };
    window.alert = function () {};

    var failures = [];
    function ok(cond, name, extra) {
        if (!cond) failures.push(name + (extra ? ' (' + extra + ')' : ''));
    }

    function finish() {
        var title = failures.length ? 'FAIL: ' + failures.join(' | ') : 'PASS';
        document.title = title;
        var box = document.createElement('div');
        box.id = '__logic_result';
        box.textContent = title;
        (document.body || document.documentElement).appendChild(box);
        try { fetch('/done', { method: 'POST', body: title }); } catch (e) { }
    }

    var waited = 0;
    function waitReady() {
        var T = window.__personaTest;
        if (T && T.State && T.State.personas.length && T.WorldService.current()) {
            run(T).catch(function (e) {
                var where = (e && e.stack) ? String(e.stack).split(String.fromCharCode(10)).slice(1, 3).join(' / ') : '';
                failures.push('异常：' + (e && e.message ? e.message : e) + ' @ ' + where);
                finish();
            });
            return;
        }
        if (waited > 40000) { failures.push('boot 超时（40s 内未就绪）'); finish(); return; }
        waited += 100;
        setTimeout(waitReady, 100);
    }

    async function run(T) {
        var world = T.WorldService.current();
        var card = T.PersonaService.current();
        var wv = T.WorldviewService.current();
        ok(!!world && !!card, '应存在当前卡片与世界');
        if (!world || !card) { finish(); return; }

        // 给角色与世界填上可辨识的内容
        world.name = '林照';
        world.role = '夜班图书管理员';
        world.summary = '话少，记性极好';
        world.detail = '在旧城区图书馆值夜班，能记住每一本书被谁借走过。';
        world.other = '怕火';
        await T.WorldService.save(world);
        if (wv) {
            wv.name = '雾港';
            wv.detail = '常年有雾的港口城市，航运由三个商会把持。';
            await T.WorldviewService.save(wv);
        }

        var KINDS = ['persona-chat', 'persona-novel', 'world-story', 'world-novel'];
        var subjectFor = function (k) {
            return k.indexOf('world-') === 0 ? T.WorldviewService.current() : T.WorldService.current();
        };

        /* ---------- 1. 12 个组合两两不同 ---------- */
        var texts = {};
        var allTexts = [];
        KINDS.forEach(function (k) {
            T.StartPrompt.scenes(k).forEach(function (s) {
                var t = T.StartPrompt.build(k, s.key, '', subjectFor(k));
                ok(!!t, '生成失败：' + k + '/' + s.key);
                texts[k + '/' + s.key] = t;
                allTexts.push(t);
            });
        });
        ok(allTexts.length === 12, '应有 12 个组合（4 类型 × 3 场景）', 'got=' + allTexts.length);
        var uniq = {};
        allTexts.forEach(function (t) { uniq[t] = 1; });
        ok(Object.keys(uniq).length === allTexts.length, '12 个组合的提示词应两两不同',
           'unique=' + Object.keys(uniq).length);
        // 每个组合都应含自己的场景描述文本
        KINDS.forEach(function (k) {
            T.StartPrompt.scenes(k).forEach(function (s) {
                var t = texts[k + '/' + s.key] || '';
                ok(t.indexOf(s.brief) >= 0, '提示词应含场景描述：' + k + '/' + s.key);
                ok(t.indexOf(s.label) >= 0, '提示词应含场景名：' + k + '/' + s.key);
            });
        });

        /* ---------- 2. 人设正文四段 ---------- */
        var pc = texts['persona-chat/daily'];
        ok(typeof pc === 'string' && pc.length > 0, 'persona-chat/daily 应有内容',
           'type=' + (typeof pc) + ' keys=' + Object.keys(texts).join(','));
        pc = pc || '';
        ok(pc.indexOf('姓名：林照') >= 0, '应含姓名');
        ok(pc.indexOf('身份：夜班图书管理员') >= 0, '应含身份');
        ok(pc.indexOf('一句话概括：话少，记性极好') >= 0, '应含概括');
        ok(pc.indexOf('旧城区图书馆') >= 0, '应含详述');
        ok(pc.indexOf('怕火') >= 0, 'other 非空时应出现');
        // 空字段显示（未填）
        var hollow = { name: '', role: '', summary: '', detail: '', other: '' };
        var hc = T.StartPrompt.build('persona-chat', 'daily', '', hollow);
        ok((hc.match(/（未填）/g) || []).length >= 4, '空字段应显示（未填）',
           'count=' + (hc.match(/（未填）/g) || []).length);
        ok(hc.indexOf('其他设定') < 0, 'other 为空时不应出现「其他设定」小节');

        /* ---------- 3. 不含 FINALIZE_HINT ---------- */
        var fhMarker = '【收尾说明】';
        ok(T.FINALIZE_HINT.indexOf(fhMarker) >= 0, 'FINALIZE_HINT 应含收尾说明（前提检查）');
        allTexts.forEach(function (t) {
            ok(t.indexOf(fhMarker) < 0, '起始提示词不应包含收尾说明');
            ok(t.indexOf('只输出最终人设') < 0, '起始提示词不应要求输出四段设定');
        });

        /* ---------- 4. 对话 / 叙事 各自的输出要求 ---------- */
        ok(texts['persona-chat/daily'].indexOf('以角色的第一句话开场') >= 0,
           '对话类要求以第一句话开场');
        ['persona-novel/cold-open', 'world-story/slice', 'world-novel/cold-open'].forEach(function (key) {
            ok(texts[key].indexOf('只写正文') >= 0, '叙事类要求只写正文：' + key);
        });
        ok(texts['persona-chat/daily'].indexOf('不要替用户写台词') >= 0,
           '对话类应保留用户台词的余地');

        /* ---------- 5. 补充要求 ---------- */
        var withExtra = T.StartPrompt.build('persona-chat', 'daily', '在雨夜的便利店', subjectFor('persona-chat'));
        ok(withExtra.indexOf('在雨夜的便利店') >= 0, '补充要求应出现在提示词里');
        ok(withExtra.indexOf('【补充要求】') >= 0, '补充要求应带小标题');
        var noExtra = T.StartPrompt.build('persona-chat', 'daily', '   ', subjectFor('persona-chat'));
        ok(noExtra.indexOf('【补充要求】') < 0, '补充要求为空时不应出现空小节');

        /* ---------- 6. 世界观版 ---------- */
        var ws = texts['world-story/slice'];
        ok(ws.indexOf('雾港') >= 0, '世界观版应含世界观名称');
        ok(ws.indexOf('三个商会') >= 0, '世界观版应含世界观详述');
        ok(ws.indexOf('用户：') < 0 && ws.indexOf('AI：') < 0, '世界观版不应含聊天记忆');
        ok(ws.indexOf('林照') < 0, '世界观版不应含人物姓名');

        /* ---------- 7. 主按钮与三项文案随模式切换 ---------- */
        var startBtn = Utils_('#startBtn');
        T.ModeService.switchTo('persona', { silent: true });
        ok(startBtn.textContent.indexOf('开始此人物形象') >= 0, '人设模式主按钮文案',
           startBtn.textContent);
        var itemsP = itemLabels();
        ok(itemsP.join('/') === '开始对话/开始小说/总结记忆进人设', '人设模式三项文案', itemsP.join('/'));
        T.ModeService.switchTo('worldview', { silent: true });
        ok(startBtn.textContent.indexOf('开始此世界') >= 0, '世界观模式主按钮文案', startBtn.textContent);
        var itemsW = itemLabels();
        ok(itemsW.join('/') === '开始故事/开始小说/完善世界设定', '世界观模式三项文案', itemsW.join('/'));

        /* ---------- 8. 向上展开且在视口内 ---------- */
        T.closeStartMenu();
        T.openStartMenu();
        var menu = T.startMenuNode();
        ok(menu.hidden === false, '菜单应展开');
        var mr = menu.getBoundingClientRect();
        var br = startBtn.getBoundingClientRect();
        ok(mr.bottom <= br.top + 1, '菜单应向上展开（底边不高于按钮上沿）',
           'menu.bottom=' + Math.round(mr.bottom) + ' btn.top=' + Math.round(br.top));
        ok(mr.top >= -1, '菜单不应超出视口上沿', 'top=' + Math.round(mr.top));
        ok(mr.left >= -1 && mr.right <= window.innerWidth + 1, '菜单不应超出视口左右',
           'l=' + Math.round(mr.left) + ' r=' + Math.round(mr.right));
        T.closeStartMenu();
        ok(menu.hidden === true, '关闭后菜单应隐藏');

        /* ---------- 8b. 切换模式应把菜单收起 ---------- */
        // switchTo 在「目标模式与当前一致」时会提前返回；确保真的发生切换
        T.ModeService.switchTo('persona', { silent: true });
        T.openStartMenu();
        ok(menu.hidden === false, '再次展开（前提检查）');
        T.ModeService.switchTo('worldview', { silent: true });
        ok(menu.hidden === true, '切换模式后菜单应收起');

        /* ---------- 8b2. 切换模式应清掉结果区来源提示 ---------- */
        T.State.resultOrigin = 'start';
        T.renderResultHint();
        ok(Utils_('#resultHint').hidden === false, '来源为 start 时应显示提示（前提检查）');
        T.ModeService.switchTo('persona', { silent: true });
        ok(T.State.resultOrigin === undefined, '切换模式后来源应被清掉',
           String(T.State.resultOrigin));
        ok(Utils_('#resultHint').hidden === true, '切换模式后提示应隐藏');

        /* ---------- 8c. 结果区来源提示 ---------- */
        T.State.resultOrigin = 'start';
        T.renderResultHint();
        var hint = Utils_('#resultHint');
        ok(hint.hidden === false, '扮演 / 叙事来源应显示提示');
        ok(hint.textContent.indexOf('不必写回人设') >= 0, '提示文案应说明不必写回',
           hint.textContent);
        T.State.resultOrigin = 'maintain';
        T.renderResultHint();
        ok(hint.hidden === true, '维护来源不应显示提示');
        T.State.resultOrigin = undefined;
        T.renderResultHint();
        ok(hint.hidden === true, '来源未设置时不应显示提示');

        /* ---------- 8c2. 发送路径必须把来源标记为 start ---------- */
        // 直接走 sendStartPrompt 的入口逻辑：无 API Key 时它会提前返回，
        // 所以这里只验证「进入请求前」就被标记为 start 的行为，用打桩的 AIClient。
        if (T.AIClient) {
            var origConfig = T.AIClient.config;
            var origStream = T.AIClient.stream;
            T.AIClient.config = function () { return { apiKey: 'x', baseUrl: 'https://x' }; };
            T.AIClient.stream = async function () { /* 不产出任何 chunk */ };
            try {
                await T.sendStartPrompt('dummy');
                ok(T.State.resultOrigin === 'start', '发送起始提示后来源应为 start',
                   String(T.State.resultOrigin));
                ok(Utils_('#resultHint').hidden === false, '发送起始提示后应显示提示');
            } finally {
                T.AIClient.config = origConfig;
                T.AIClient.stream = origStream;
            }
        } else {
            ok(false, '测试缝未暴露 AIClient，无法验证来源标记');
        }
        T.State.resultOrigin = undefined;
        T.renderResultHint();

        /* ---------- 8d. 请求进行中应禁用所有发送入口 ---------- */
        T.State.resultOrigin = undefined;
        T.renderResultHint();
        T.openStartMenu();
        var startBtnEl = Utils_('#startBtn');
        ok(startBtnEl.disabled === false, '空闲时主按钮应可用（前提检查）');
        T.AiSendServiceForTest.begin();
        ok(startBtnEl.disabled === true, '请求中主按钮应禁用');
        ok(Utils_('#startSendBtn').disabled === true, '请求中场景弹窗发送应禁用');
        ok(Utils_('#sendAiBtn').disabled === true, '请求中菜单第三项应禁用');
        var menuItems = Utils_$$('#startMenu .start-item');
        ok(menuItems.every(function (b) { return b.disabled; }), '请求中所有菜单项应禁用');
        T.AiSendServiceForTest.end();
        ok(startBtnEl.disabled === false, '结束后主按钮应恢复');
        T.closeStartMenu();

        /* ---------- 9. 场景弹窗 ---------- */
        T.ModeService.switchTo('persona', { silent: true });
        T.openStartModal('chat');
        ok(Utils_('#startTitle').textContent === '开始对话', '人设 chat 标题',
           Utils_('#startTitle').textContent);
        ok(Utils_$$('#startScenes input[name="startScene"]').length === 3,
           '人设对话应有 3 个场景',
           String(Utils_$$('#startScenes input[name="startScene"]').length));
        ok(Utils_('#startDesc').textContent.indexOf('角色') >= 0, '人设模式的说明应提到角色');
        document.querySelector('#startModal').classList.remove('open');

        T.ModeService.switchTo('worldview', { silent: true });
        T.openStartModal('chat');
        ok(Utils_('#startTitle').textContent === '开始故事', '世界观 chat 标题',
           Utils_('#startTitle').textContent);
        var wvScenes = Utils_$$('#startScenes input[name="startScene"]').map(function (r) { return r.value; });
        ok(wvScenes.join('/') === 'slice/moment/clash', '世界观故事场景集',
           wvScenes.join('/'));
        ok(Utils_('#startDesc').textContent.indexOf('世界观') >= 0, '世界观模式说明应提到世界观');
        document.querySelector('#startModal').classList.remove('open');

        T.ModeService.switchTo('persona', { silent: true });
        T.openStartModal('novel');
        var novelScenes = Utils_$$('#startScenes input[name="startScene"]').map(function (r) { return r.value; });
        ok(novelScenes.join('/') === 'cold-open/scene/memory', '小说场景集', novelScenes.join('/'));
        document.querySelector('#startModal').classList.remove('open');

        /* ---------- 9b. 世界观「小说」入口必须落到 world-novel ---------- */
        T.ModeService.switchTo('worldview', { silent: true });
        ok(T.startKindFor('novel') === 'world-novel', '世界观 novel 槽位应解析为 world-novel',
           T.startKindFor('novel'));
        ok(T.startKindFor('chat') === 'world-story', '世界观 chat 槽位应解析为 world-story',
           T.startKindFor('chat'));
        T.openStartModal('novel');
        ok(Utils_('#startTitle').textContent === '开始小说', '世界观 novel 标题',
           Utils_('#startTitle').textContent);
        var wnvScenes = Utils_$$('#startScenes input[name="startScene"]').map(function (r) { return r.value; });
        ok(wnvScenes.join('/') === 'cold-open/scene/memory', '世界观小说场景集', wnvScenes.join('/'));
        document.querySelector('#startModal').classList.remove('open');
        T.ModeService.switchTo('persona', { silent: true });
        ok(T.startKindFor('chat') === 'persona-chat', '人设 chat 槽位应解析为 persona-chat');
        ok(T.startKindFor('novel') === 'persona-novel', '人设 novel 槽位应解析为 persona-novel');

        /* ---------- 9c. 用户选中的场景必须真的被采用 ---------- */
        T.openStartModal('chat');
        var radios = Utils_$$('#startScenes input[name="startScene"]');
        radios[radios.length - 1].checked = true;      // 选「冲突对峙」
        var pickedKey = radios[radios.length - 1].value;
        var pickedText = T.buildStartText();
        var pickedScene = T.StartPrompt.scenes('persona-chat')
            .filter(function (s) { return s.key === pickedKey; })[0];
        ok(!!pickedScene, '应能取到被选中的场景');
        ok(pickedText.indexOf(pickedScene.brief) >= 0, '生成结果应采用用户选中的场景',
           'picked=' + pickedKey);
        document.querySelector('#startModal').classList.remove('open');

        /* ---------- 9d. 预览必须压在场景弹窗之上 ---------- */
        T.openStartModal('chat');
        T.startPreview();
        var pm = Utils_('#previewModal');
        var sm = Utils_('#startModal');
        ok(pm.classList.contains('open'), '预览弹窗应打开');
        ok(sm.classList.contains('open'), '场景弹窗仍开着（前提检查）');
        var pz = parseInt(pm.style.zIndex || '0', 10);
        var sz = parseInt(sm.style.zIndex || '0', 10);
        ok(pz > sz, '预览弹窗层级应高于场景弹窗（否则会被盖住）',
           'preview=' + pz + ' start=' + sz);
        // 用命中测试再确认一次：预览框中心点应落在预览弹窗内
        var box = pm.querySelector('.modal-box').getBoundingClientRect();
        var hit = document.elementFromPoint(box.left + box.width / 2, box.top + 20);
        ok(!!hit && pm.contains(hit), '预览框中心点应命中预览弹窗',
           hit ? (hit.id || hit.className) : 'null');
        T.UI.closeModal('previewModal');
        T.UI.closeModal('startModal');

        /* ---------- 10. 原「总结记忆进人设」路径未受影响 ---------- */
        T.ModeService.switchTo('persona', { silent: true });
        T.fillEditor(T.WorldService.current());
        Utils_('#requestInput').value = '把怕火这条淡一点';
        var maint = T.currentPrompt(false);
        ok(!!maint && maint.text.indexOf(fhMarker) >= 0,
           '维护路径应保留 FINALIZE_HINT 收尾说明');
        ok(!!maint && maint.text.indexOf('【第 4 段') >= 0, '维护路径应仍是四段式提示词');
        Utils_('#requestInput').value = '';

        finish();

        function Utils_(sel) { return document.querySelector(sel); }
        function Utils_$$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
        function itemLabels() {
            return Utils_$$('#startMenu .start-item').map(function (b) { return b.textContent.trim(); });
        }
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
            if self.path in ("/", "/index.html", "/index.html#selftest"):
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


def build_temp_copy(dest: Path) -> None:
    html = TARGET.read_text(encoding="utf-8")
    if SEAM_ANCHOR not in html:
        raise SystemExit(
            "找不到测试缝锚点 `StartUI: StartUI,`。"
            "如果人设应用的 selftest 对象改过，请同步更新本脚本的 SEAM_ANCHOR。"
        )
    html = html.replace(SEAM_ANCHOR, SEAM_EXTRA, 1)
    if "</body>" not in html:
        raise SystemExit("找不到 </body>，无法注入驱动脚本。")
    html = html.replace("</body>", DRIVER + "</body>", 1)
    (dest / "index.html").write_text(html, encoding="utf-8")


def run_one(browser: str, tmp: Path) -> tuple[bool, str]:
    done = threading.Event()
    server = _GateServer(("127.0.0.1", 0), make_handler(tmp, done))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    profile = tmp / "profile"
    profile.mkdir(exist_ok=True)
    dom_file = tmp / "dom.html"
    err_file = tmp / "err.txt"
    url = f"http://127.0.0.1:{port}/index.html#selftest"

    try:
        with open(dom_file, "w", encoding="utf-8") as df, open(err_file, "w", encoding="utf-8") as ef:
            proc = subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--disable-dev-shm-usage", "--user-data-dir=" + str(profile),
                 "--dump-dom", "--enable-logging=stderr", url],
                stdout=df, stderr=ef, timeout=SUBPROCESS_TIMEOUT_SECONDS,
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
    title = (m.group(1).strip() if m else "")
    if title.startswith("PASS"):
        return True, "PASS"
    if title.startswith("FAIL:"):
        return False, title[len("FAIL:"):].strip()

    hint = ["dom 为空"] if not dom_text.strip() else ["title=" + (title or "（空）")]
    if returncode:
        hint.append(f"chrome 退出码 {returncode}")
    err_lines = [ln for ln in stderr_text.splitlines()
                 if re.search(r"Uncaught|SyntaxError|TypeError|ReferenceError|ERROR", ln)]
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

    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp = Path(tmpdir)
            build_temp_copy(tmp)
            try:
                passed, detail = run_one(browser, tmp)
            except subprocess.TimeoutExpired:
                passed, detail = False, f"打开超时（超过 {SUBPROCESS_TIMEOUT_SECONDS} 秒）"
        if passed:
            print()
            print(f"起始提示词单测完成：全部断言通过（第 {attempt} 次运行）。")
            return 0
        last = detail
        if attempt < MAX_ATTEMPTS:
            print(f"[重试] 第 {attempt} 次未通过：{detail}")

    print()
    print(f"[问题] 起始提示词单测失败：{last}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
