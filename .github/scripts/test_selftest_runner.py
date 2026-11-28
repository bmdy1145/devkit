#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在无头 Chrome 里跑全部测试版的内置自检。

测试版页面注入的自检是给用户点的，不是给 CI 看的。本脚本把它们
在真实浏览器里跑一遍，从结果弹窗逐项读 PASS / FAIL，避免「自检脚本
本身写坏了却没人知道」——自检的断言错误不会让任何现有守卫变红。

机制沿用 devkit_logic_test.py 的做法：本地 HTTP 服务托管文件、
`chrome --headless=new --dump-dom` 导出 DOM 后解析 `#selftestModal`。

用法：
    python3 .github/scripts/test_selftest_runner.py
    CHROME_BIN=... python3 .github/scripts/test_selftest_runner.py
    python3 .github/scripts/test_selftest_runner.py --only writer

退出码：0 = 全部 PASS；1 = 有 FAIL 或自检根本跑不起来。
"""

from __future__ import annotations

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
PROJECTS = ROOT / "projects"

# 单个项目的总预算。浏览器正常时每个项目 10-25 秒就能跑完；给到 90 秒
# 是留给 CI 上冷启动 / 无 GPU 的余量。旧值 180 秒会让一个卡住的项目
# 独吞掉整条 job 的时间。
SUBPROCESS_TIMEOUT = 120
# 每个项目最多尝试几次。自检里有若干与产品异步 boot 竞速的步骤，CI 上
# 偶发一次超时不足以判定回归；连续失败才算真问题。
MAX_ATTEMPTS = 2
SUMMARY_RE = re.compile(r"(全部通过|有失败项)：(\d+)\s*/\s*(\d+)\s*通过")

# (项目, 测试版目录, 产品文件)
# 所有自检按钮都直接挂在可见工具栏上，统一用 window.__selftest() 触发
# （与用户点按钮走同一个 run()，避免测试专用入口与真实入口分叉）。
FILES = [
    ("devkit", "A1_VI_Φ1_Test1", "deepseek_A1_VI_Φ1_Test1_CN.html"),
    ("writer", "A1_I_Φ6_Test1", "deepseek_A1_I_Φ6_Test1_CN.html"),
    ("persona", "A1_II_Φ15_Test1", "deepseek_A1_II_Φ15_Test1_CN.html"),
    ("dircleaner", "A1_II_Φ9_Test1", "deepseek_A1_II_Φ9_Test1.html"),
    ("submerge-pro", "A1_II_Φ11_Test1", "deepseek_A1_II_Φ11_Test1_CN.html"),
]


GATE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360606060000000050001a5f64540"
    "0000000049454e44ae426082"
)
# 闸门最多拖这么久就放行。/gate 是在 DOMContentLoaded 挂上的，若自检
# 一直不写结果，Chrome 会等到 subprocess 超时；把这里设得比
# SUBPROCESS_TIMEOUT 小，服务端线程不会比浏览器活得更久。
GATE_TIMEOUT = 90


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(directory: Path, done: threading.Event):
    """托管单页，并用 /gate 挂住 load——自检是异步的，不挂住的话
    Chrome 可能在 run() 的 await 期间就 dump-dom 了（devkit_logic_test
    用的是同一套办法）。"""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/gate"):
                done.wait(GATE_TIMEOUT)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(GATE_PNG)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(GATE_PNG)
                return
            super().do_GET()

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
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


HARNESS = r"""
<script>
/* 由 test_selftest_runner.py 注入：触发自检，跑完通知本地服务放行 load。
   自检本身会把结论写进 <title>。

   必须最先给 window.confirm / window.alert 打桩：在
   `--headless=new --dump-dom` 下这两个原生对话框没有可交互的窗口，
   渲染进程会永久阻塞（本项目此前在 devkit 行为测试里踩过同一个坑）。
   persona 在 IndexedDB 降级后会走 Storage.onConflict → window.confirm
   的路径，不打桩会让整页挂死、CI 只看到「浏览器超时」。 */
(function () {
    try { window.confirm = function () { return true; }; } catch (e) {}
    try { window.alert = function () {}; } catch (e) {}
    try { window.prompt = function (_msg, def) { return def == null ? '' : def; }; } catch (e) {}
    function gate() {
        var img = document.createElement('img');
        img.style.display = 'none';
        img.src = '/gate?ts=' + Date.now();
        (document.body || document.documentElement).appendChild(img);
    }
    function done() {
        try { fetch('/done', { method: 'POST', body: document.title }); } catch (e) {}
    }
    function report(msg) { document.title = 'SELFTEST-ERROR ' + msg; done(); }

    var waited = 0;
    function tick() {
        var fn = window.__selftest || window.__devkitSelftest;
        if (typeof fn === 'function') {
            try {
                var p = fn();
                if (p && typeof p.then === 'function') p.then(done, function (e) {
                    report(e && e.message ? e.message : String(e));
                });
                else done();
            } catch (e) {
                report(e && e.message ? e.message : String(e));
            }
            return;
        }
        if (waited > 20000) { report('入口未就绪'); return; }
        waited += 100;
        setTimeout(tick, 100);
    }
    // 1) DOMContentLoaded 即挂闸门图拖住真实 load，否则异步自检还没跑完，
    //    Chrome 的 --dump-dom 就把页面导出走了。
    // 2) dircleaner 把初始化排在 window.load 上，真实 load 被拖住会让它
    //    永远不就绪。这里补发一个合成的 load 事件把它的启动逻辑叫起来；
    //    合成事件不会让浏览器认为页面已加载，闸门照旧有效。
    // 3) 真实 load 在自检跑完、/done 放行后才触发；此后即便 dircleaner
    //    的启动逻辑再跑一次，结果弹窗也已渲染，不影响取数。
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            gate();
            setTimeout(function () {
                try { window.dispatchEvent(new Event('load')); } catch (e) {}
                setTimeout(tick, 50);
            }, 0);
        });
    } else {
        gate();
        try { window.dispatchEvent(new Event('load')); } catch (e) {}
        setTimeout(tick, 50);
    }
})();
</script>
"""


def run_one(browser: str, project: str, ver: str, fname: str) -> tuple[bool, str, list[str]]:
    src = PROJECTS / project / "test" / ver / fname
    if not src.exists():
        return False, f"找不到文件 {src.relative_to(ROOT)}", []

    tmp = Path(tempfile.mkdtemp())
    html = src.read_text(encoding="utf-8")
    if "</body>" not in html:
        return False, "找不到 </body>，无法注入驱动脚本", []
    (tmp / "index.html").write_text(
        html.replace("</body>", HARNESS + "</body>", 1), encoding="utf-8"
    )

    done = threading.Event()
    server = _Server(("127.0.0.1", 0), make_handler(tmp, done))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    profile = Path(tempfile.mkdtemp())
    dom_file = tmp / "dom.html"
    try:
        with open(dom_file, "w", encoding="utf-8") as df:
            proc = subprocess.run(
                [
                    browser,
                    "--headless=new",
                    # 默认 headless 窗口只有 800×600：persona 在这个宽度下
                    # 已经切到窄屏页签模式（侧栏 display:none），三栏检查
                    # 会误报。固定成常见桌面尺寸，贴近真实使用。
                    "--window-size=1440,900",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--user-data-dir=" + str(profile),
                    "--dump-dom",
                    f"http://127.0.0.1:{port}/index.html",
                ],
                stdout=df,
                stderr=subprocess.DEVNULL,
                timeout=SUBPROCESS_TIMEOUT,
            )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if dom_file.stat().st_size > 0:
                    break
            except OSError:
                pass
            time.sleep(0.2)
        dom = dom_file.read_text(encoding="utf-8", errors="replace")
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT", []
    finally:
        # 放行仍阻塞在 /gate 上的 handler 线程：超时返回时自检没写结果，
        # done 不会被 set，那个线程会一直等到 GATE_TIMEOUT（90s）才放行，
        # 重试时就会同时挂着两个。这里主动置位，让它们立刻结束。
        done.set()
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)

    # 结果弹窗追加在 body 末尾：从 id 出现处截到文末即可覆盖整个弹窗，
    # 不依赖各项目不同的模态框嵌套层级（devkit 用 .modal-content，
    # 其余项目自建 .st-box）。
    idx = dom.find('id="selftestModal"')
    if idx < 0:
        title = re.search(r"<title>(.*?)</title>", dom, re.S)
        return False, f"未找到自检结果弹窗（title={title.group(1).strip() if title else '空'}，rc={rc}）", []

    text = dom[idx:]
    # 结果同时写在 <html data-selftest> 里。自检关闭弹窗时会还原
    # document.title（那是用户可见的标签页），所以不能只靠 title 取结论。
    attr = re.search(r'data-selftest="([^"]*)"', dom)
    attr_result = attr.group(1).strip() if attr else ''
    m = SUMMARY_RE.search(text)
    # 逐项名称 + PASS/FAIL：结果行形如 <span ...>PASS</span><span ...>名称 — 详情</span>
    # devkit 的结果行是 <span>PASS</span><span>名称<span> — 详情</span></span>，
    # 其余四个是 <span>PASS</span><span>名称 — 详情</span>。用更宽松的匹配：
    # 只取 PASS/FAIL 之后到下一个尖括号之间的文本，不强求 span 嵌套层级。
    rows = re.findall(
        r">(PASS|FAIL)</span>\s*<span[^>]*>([^<]*)", text, re.S
    )
    fail_names = [name.strip() for tag, name in rows if tag == "FAIL"]
    if not m:
        return False, "结果弹窗里没有汇总行", fail_names
    good, total = int(m.group(2)), int(m.group(3))
    ok = m.group(1) == "全部通过" and good == total and not fail_names
    if attr_result and not attr_result.startswith(("SELFTEST-PASS", "SELFTEST-FAIL")):
        return False, f"data-selftest 内容异常：{attr_result[:40]}", fail_names
    return ok, f"{good}/{total}", fail_names


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    only = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only = sys.argv[idx + 1]

    browser = find_browser()
    if browser is None:
        print("[问题] 找不到 Chrome / Chromium。用 CHROME_BIN 指定浏览器路径后重试。")
        return 1

    print(f"使用浏览器：{browser}")
    bad = 0
    ran = 0
    for project, ver, fname in FILES:
        if only and project != only:
            continue
        ran += 1
        rel = f"projects/{project}/test/{ver}/{fname}"
        ok = False
        detail, fails = "", []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ok, detail, fails = run_one(browser, project, ver, fname)
            # 只有「超时」才值得重试：断言失败是确定性的，重跑只会浪费
            # 两倍时间并输出重复的失败项。
            if ok or detail != "TIMEOUT":
                break
            if attempt < MAX_ATTEMPTS:
                print(f"[重试] {rel}：浏览器超时，第 {attempt + 1} 次尝试")
        if ok:
            print(f"[通过] {rel}：{detail}")
        else:
            bad += 1
            label = "浏览器超时（已重试）" if detail == "TIMEOUT" else detail
            print(f"[失败] {rel}：{label}")
            for name in fails:
                print(f"        - {name}")

    print()
    suffix = "（--only 只跑了部分项目）" if only else ""
    print(f"自检实测完成：{ran - bad} / {ran} 个通过，{bad} 个失败{suffix}。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
