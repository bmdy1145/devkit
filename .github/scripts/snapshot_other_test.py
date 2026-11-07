#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persona 快照字段的运行时逻辑单测（PR #70 审查发现项）。

## 为什么需要这个脚本

`smoke_test.py` 只断言：控制台没有 Uncaught / SyntaxError / TypeError / ReferenceError、
`<body>` 带主题类名、`<title>` 非空。它抓不到「`await Storage.init()` 之后 boot 抛异常」——
实测这种副本**完全不产生 CONSOLE 行**（异常发生在异步链路里，`window.onerror` 的
console.error 落在 `--dump-dom` 已经退出之后）。

`version_guard.py` 只做静态检查（版本号一致、`node --check`）。所以本文件里
「快照存不存 `other`、恢复时回不回写 `other`」这件事，此前没有任何自动化保护。

## 验证什么

| # | 用例 | 断言 |
|---|---|---|
| 1 | 存快照 | 快照 persona 对象含 `other`，且值等于当时的输入 |
| 2 | 快照有 other → 改值 → 恢复 | world.other 与 #otherInput 都回到快照值 |
| 3 | 快照 other 为空串 → 填了值 → 恢复 | world.other 变回空串（区分 `??` 与 `\\|\\|`） |
| 4 | 旧快照无 other 字段（模拟 Φ11 备份） | 恢复后保持当前值，不抛异常 |
| 5 | changeScope 取消 | card.memoryScope 与 #scopeSelect 均保持原值 |

`deleteWorld` 的 `rest` 越界守卫不做自动断言：正常路径下 guard 不触发，要触发得
monkeypatch `WorldService.worldsOf` 连续返回不同数组，属刻意造作。那一项靠代码审阅。

## 机制

因为全在一个 IIFE 里，外部拿不到 `SnapshotService` 等内部对象，所以：

1. 把 Φ12 的 HTML 复制到临时目录，作为 `index.html`；
2. **只在临时副本里**把已有的 `#selftest` 测试缝多暴露几个内部对象（产品文件的测试缝不动）；
3. 在副本里注入驱动脚本：打桩 `window.confirm`，轮询等 boot 完成，跑断言，
   把 `PASS` / `FAIL:…` 写进 `document.title`，最后 POST `/done`；
4. 起本地 HTTP 服务托管临时目录。`/gate` 挂住直到收到 `/done` —— 页面里挂一张
   同源图片把 `load` 事件拖住，否则 `--dump-dom` 会在异步 IndexedDB 启动完成前就导出 DOM；
5. `chrome --headless=new --dump-dom`，从导出的 DOM 里取 `<title>` 判成败。

必须走 HTTP 而不是 `file://`：应用带了 CSP `img-src 'self' data:`，`file://` 下同源判定
不可靠，闸门图会被拦。走 HTTP 也让每次随机端口成为一个全新 origin，IndexedDB 天然干净。

`window.confirm` 必须在断言前打桩：`--headless=new --dump-dom` 下 `confirm` 会挂死渲染进程
（不返回、不弹窗），而 `restoreSnapshot` 与 `changeScope` 都会调它。

用法：
    本地： python3 .github/scripts/snapshot_other_test.py
          浏览器不在 PATH 时用 CHROME_BIN 指定，例如：
          CHROME_BIN="/c/Program Files/Google/Chrome/Application/chrome.exe" \
            python3 .github/scripts/snapshot_other_test.py
    CI  ： 由 .github/workflows/repo-checks.yml 的 persona-logic job 调用

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

# 允许指向别的版本文件，主要用途是「反向对照」：拿修复前的版本跑一遍，确认本脚本
# 会红。若哪天改完仍然绿，说明断言本身失效了。
TARGET = Path(os.environ.get("PERSONA_TEST_TARGET") or DEFAULT_TARGET)

SUBPROCESS_TIMEOUT_SECONDS = 120
GATE_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 2
RESULT_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)

# 1x1 透明 PNG：闸门图只需要「返回得晚」，内容无所谓。
GATE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# 测试缝锚点：selftest 分支里 personaTest 对象最后一个键。
SEAM_ANCHOR = "            buildBundlePrompt: buildBundlePrompt"

SEAM_EXTRA = """            buildBundlePrompt: buildBundlePrompt,
            /* 以下由 snapshot_other_test.py 注入到临时副本，仅测试用 */
            SnapshotService: SnapshotService,
            WorldService: WorldService,
            PersonaService: PersonaService,
            MemoryService: MemoryService,
            State: State,
            memoryKey: memoryKey,
            restoreSnapshot: restoreSnapshot,
            changeScope: changeScope,
            deleteWorld: deleteWorld,
            flushSave: flushSave,
            readEditorInto: readEditorInto,
            fillEditor: fillEditor,
            syncScopeUI: syncScopeUI,
            loadScopeData: loadScopeData,
            renderSnapshots: renderSnapshots"""

DRIVER = r"""
<script>
/* 由 snapshot_other_test.py 注入：跑完断言把结果写进 <title>。 */
(function () {
    /* confirm 必须在 boot 之前打桩：--dump-dom 下真的弹窗会挂死渲染进程，
       而 restoreSnapshot / changeScope 都会调它。 */
    var CONFIRM_ANSWER = true;
    window.confirm = function () { return CONFIRM_ANSWER; };
    window.alert = function () {};
    window.__confirmAnswer = function (v) { CONFIRM_ANSWER = v; };

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

    function val(sel) { return document.querySelector(sel).value; }
    function setVal(sel, v) { document.querySelector(sel).value = v; }

    var waited = 0;
    function waitReady() {
        var T = window.__personaTest;
        if (T && T.State && T.State.personas.length) {
            var w = T.WorldService.current();
            if (w) { run(T).catch(function (e) { failures.push('异常：' + (e && e.message ? e.message : e)); finish(); }); return; }
        }
        if (waited > 30000) { failures.push('boot 超时（30s 内未就绪）'); finish(); return; }
        waited += 100;
        setTimeout(waitReady, 100);
    }

    async function run(T) {
        var card = T.PersonaService.current();
        var w = T.WorldService.current();
        ok(!!card, '应存在当前人物卡片');
        ok(!!w, '应存在当前平行世界');
        if (!card || !w) { finish(); return; }

        var key = T.memoryKey(card, w);

        /* ---------- 用例 1：capture 是否带上 other ---------- */
        setVal('#otherInput', 'SENTINEL-A');
        setVal('#nameInput', '名字A');
        await T.flushSave();
        var snapA = await T.SnapshotService.capture(w, key, 'manual');
        ok(snapA && snapA.persona, '快照应有 persona 对象');
        ok(snapA.persona && 'other' in snapA.persona, '快照 persona 应含 other 键',
           '实际键：' + Object.keys(snapA.persona || {}).join('/'));
        ok(snapA.persona && snapA.persona.other === 'SENTINEL-A',
           '快照 other 应等于存快照时的值', '实际=' + (snapA.persona || {}).other);

        /* ---------- 用例 2：恢复应把 other 一起写回 ---------- */
        setVal('#otherInput', 'SENTINEL-B');
        await T.flushSave();
        ok(w.other === 'SENTINEL-B', '改值后 world.other 应为 B', '实际=' + w.other);
        await T.restoreSnapshot(snapA);
        ok(w.other === 'SENTINEL-A', '恢复后 world.other 应回到 A', '实际=' + w.other);
        ok(val('#otherInput') === 'SENTINEL-A', '恢复后输入框应显示 A', '实际=' + val('#otherInput'));

        /* ---------- 用例 3：快照里 other 为空串，恢复应清空 ---------- */
        setVal('#otherInput', '');
        await T.flushSave();
        var snapEmpty = await T.SnapshotService.capture(w, key, 'manual');
        ok(snapEmpty.persona && snapEmpty.persona.other === '',
           '空串也应原样存进快照', '实际=' + (snapEmpty.persona || {}).other);
        setVal('#otherInput', 'SENTINEL-C');
        await T.flushSave();
        await T.restoreSnapshot(snapEmpty);
        ok(w.other === '', '恢复空串快照后 world.other 应为空', '实际=' + JSON.stringify(w.other));
        ok(val('#otherInput') === '', '恢复后输入框应为空', '实际=' + JSON.stringify(val('#otherInput')));

        /* ---------- 用例 4：旧快照没有 other 字段（Φ11 及更早的备份） ---------- */
        setVal('#otherInput', 'SENTINEL-KEEP');
        await T.flushSave();
        var legacy = JSON.parse(JSON.stringify(snapA));
        delete legacy.persona.other;
        legacy.id = legacy.id + '-legacy';
        var threw = null;
        try { await T.restoreSnapshot(legacy); } catch (e) { threw = e; }
        ok(threw === null, '恢复旧快照不应抛异常', threw && threw.message);
        ok(w.other === 'SENTINEL-KEEP', '旧快照无 other 时应保留当前值', '实际=' + JSON.stringify(w.other));

        /* ---------- 用例 5：changeScope 取消应保持原值 ---------- */
        var beforeScope = card.memoryScope === 'shared' ? 'shared' : 'per-world';
        var targetScope = beforeScope === 'shared' ? 'per-world' : 'shared';
        setVal('#scopeSelect', targetScope);          // 模拟用户改了下拉框
        window.__confirmAnswer(false);
        await T.changeScope(targetScope);
        window.__confirmAnswer(true);
        ok((card.memoryScope === 'shared' ? 'shared' : 'per-world') === beforeScope,
           '取消切换后 memoryScope 应保持原值', '期望=' + beforeScope + ' 实际=' + card.memoryScope);
        ok(val('#scopeSelect') === beforeScope, '取消切换后下拉框应还原', '实际=' + val('#scopeSelect'));

        finish();
    }

    /* 闸门：同源图片挂住 load 事件，直到驱动把结果 POST 给服务端。 */
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

        def log_message(self, fmt, *args):  # 静音，避免淹没输出
            pass

        def do_GET(self):
            if self.path.startswith("/gate"):
                # 挂住直到驱动跑完；超时也放行，避免浏览器卡死。
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
    """把产品文件复制成临时副本，并只往副本里注入测试缝扩展与驱动脚本。"""
    html = TARGET.read_text(encoding="utf-8")

    if SEAM_ANCHOR not in html:
        raise SystemExit(
            "找不到测试缝锚点 `buildBundlePrompt: buildBundlePrompt`。"
            "如果人设应用改过测试缝，请同步更新本脚本的 SEAM_ANCHOR。"
        )
    html = html.replace(SEAM_ANCHOR, SEAM_EXTRA, 1)

    if "</body>" not in html:
        raise SystemExit("找不到 </body>，无法注入驱动脚本。")
    html = html.replace("</body>", DRIVER + "</body>", 1)

    (dest / "index.html").write_text(html, encoding="utf-8")


def run_one(browser: str, tmp: Path) -> tuple[bool, str]:
    """跑一次浏览器。返回 (是否通过, 说明)。"""
    done = threading.Event()
    server = _GateServer(("127.0.0.1", 0), make_handler(tmp, done))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # 独立 profile：每次全新，IndexedDB / localStorage 不串。
    profile = tmp / "profile"
    profile.mkdir(exist_ok=True)

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
                    # 不设 --virtual-time-budget：虚拟时间会让 IndexedDB 的异步回调
                    # 迟迟不落地。由 /gate 闸门把 load 事件拖到断言跑完为止。
                    "--dump-dom",
                    "--enable-logging=stderr",
                    url,
                ],
                stdout=df,
                stderr=ef,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        # Windows 上 chrome.exe 是启动器，可能先于真实进程返回；轮询等输出落地。
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

    # 取不到结果：把最有用的线索带回去。
    hint = []
    if not dom_text.strip():
        hint.append("dom 为空")
    else:
        hint.append("title=" + (title or "（空）"))
    if returncode:
        hint.append(f"chrome 退出码 {returncode}")
    err_lines = [
        ln for ln in stderr_text.splitlines()
        if re.search(r"Uncaught|SyntaxError|TypeError|ReferenceError|ERROR", ln)
    ]
    if err_lines:
        hint.append("stderr: " + err_lines[0][:200])
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
            build_temp_copy(tmp)
            try:
                passed, detail = run_one(browser, tmp)
            except subprocess.TimeoutExpired:
                passed, detail = False, f"打开超时（超过 {SUBPROCESS_TIMEOUT_SECONDS} 秒）"
        if passed:
            print()
            print(f"人设逻辑单测完成：5 组断言全部通过（第 {attempt} 次运行）。")
            return 0
        last_detail = detail
        if attempt < MAX_ATTEMPTS:
            print(f"[重试] 第 {attempt} 次未通过：{detail}")

    print()
    print(f"[问题] 人设逻辑单测失败：{last_detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
