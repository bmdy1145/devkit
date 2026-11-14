#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persona Φ13 分享图与人设姓名来源的运行时单测。

## 为什么需要这个脚本

`smoke_test.py` 只查控制台报错 / body 类名 / title 非空，验不到「排版算得对不对」；
`snapshot_other_test.py` 覆盖的是快照字段存取。Φ13 新增两块逻辑：

  1. 卡片显示名 = 「姓名来源世界」的角色姓名（`cardDisplayName`）
  2. 分享为图片：比例 / 分辨率映射 / 换行 / 分页 / 单张适配 / 调色板 / 画布输出

其中前五类是纯函数，可以在页面里直接断言；画布输出只能靠真实浏览器，
断言尺寸、PNG 类型、字节数与非空像素。

## 机制

沿用 `snapshot_other_test.py` 已验证的做法：

  · 把产品文件复制到临时目录，作为 index.html
  · 只在副本里把 #selftest 测试缝多暴露几个内部对象（产品文件的缝不动）
  · 注入驱动脚本：轮询等 boot 完成 → 跑断言 → 结果写进 document.title → POST /done
  · 本地 HTTP 服务托管副本，/gate 挂住 load 事件直到断言跑完
  · chrome --headless=new --dump-dom，从导出的 DOM 里取 <title> 判成败

用法：
    本地： python3 .github/scripts/share_image_test.py
          浏览器不在 PATH 时用 CHROME_BIN 指定
    CI  ： 由 .github/workflows/repo-checks.yml 的 persona-logic 之外独立 job 调用

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

DEFAULT_TARGET = ROOT / "projects" / "persona" / "code" / "A1_II_Φ15" / "deepseek_A1_II_Φ15_CN.html"
TARGET = Path(os.environ.get("PERSONA_TEST_TARGET") or DEFAULT_TARGET)

SUBPROCESS_TIMEOUT_SECONDS = 180
GATE_TIMEOUT_SECONDS = 150
MAX_ATTEMPTS = 2
RESULT_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)

GATE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# 测试缝锚点：Φ13 的 selftest 对象里最后一个键
SEAM_ANCHOR = "            memoryKey: memoryKey\n        };"

SEAM_EXTRA = """            memoryKey: memoryKey,
            /* 以下由 share_image_test.py 注入，仅测试用 */
            fillEditor: fillEditor,
            saveSharePrefs: saveSharePrefs,
            generateShareBlobs: generateShareBlobs
        };"""

DRIVER = r"""
<script>
/* 由 share_image_test.py 注入：跑完断言把结果写进 <title>。 */
(function () {
    var CONFIRM_ANSWER = true;
    window.confirm = function () { return CONFIRM_ANSWER; };
    window.alert = function () {};

    var failures = [];
    function ok(cond, name, extra) {
        if (!cond) failures.push(name + (extra ? ' (' + extra + ')' : ''));
    }
    function near(a, b, eps) { return Math.abs(a - b) <= (eps == null ? 0.01 : eps); }

    /* WCAG 相对亮度与对比度：检查分享图的文字与强调色在渐变底色上是否可读。 */
    function relLum(hex) {
        var h = String(hex).replace('#', '');
        if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
        var ch = [0, 2, 4].map(function (i) {
            var c = parseInt(h.substr(i, 2), 16) / 255;
            return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
    }
    function contrast(a, b) {
        var l1 = relLum(a), l2 = relLum(b);
        var hi = Math.max(l1, l2), lo = Math.min(l1, l2);
        return (hi + 0.05) / (lo + 0.05);
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
            run(T).catch(function (e) { failures.push('异常：' + (e && e.message ? e.message : e)); finish(); });
            return;
        }
        if (waited > 40000) { failures.push('boot 超时（40s 内未就绪）'); finish(); return; }
        waited += 100;
        setTimeout(waitReady, 100);
    }

    async function run(T) {
        var L = T.ShareLayout;
        var card = T.PersonaService.current();
        var world = T.WorldService.current();
        ok(!!card && !!world, '应存在当前卡片与世界');
        if (!card || !world) { finish(); return; }

        /* ---------- 1. 比例解析 ---------- */
        ok(near(L.parseRatio(4, 5), 0.8), 'parseRatio(4,5) 应为 0.8', String(L.parseRatio(4, 5)));
        ok(L.parseRatio(0, 5) === null, 'parseRatio(0,5) 应为 null');
        ok(L.parseRatio(-1, 5) === null, 'parseRatio(-1,5) 应为 null');
        ok(L.parseRatio(33, 1) === null, 'parseRatio(33,1) 应为 null（超出 32 上限）');
        ok(near(L.parseRatio('16', '9'), 16 / 9), 'parseRatio 应接受字符串数字');
        // 回归：21:9 是界面预设，绝不能被上限拒绝后静默回落成别的比例
        ok(near(L.parseRatio(21, 9), 21 / 9, 0.0001), '21:9 预设必须被接受',
           String(L.parseRatio(21, 9)));

        /* ---------- 1b. 文字缩放随长边等比 ---------- */
        ok(near(L.autoTextScale(1080), 1.0, 1e-6), '1080 长边文字应为 100%',
           String(L.autoTextScale(1080)));
        ok(near(L.autoTextScale(2160), 2.0, 1e-6), '2160 长边文字应为 200%',
           String(L.autoTextScale(2160)));
        ok(near(L.autoTextScale(3240), 3.0, 1e-6), '3240 长边应达 300%',
           String(L.autoTextScale(3240)));
        ok(near(L.autoTextScale(7680), 3.0, 1e-6), '8K 应被封顶在 300%',
           String(L.autoTextScale(7680)));
        ok(near(L.autoTextScale(480), 0.5, 1e-6), '低于 540 应被夹在 50%',
           String(L.autoTextScale(480)));
        ok(L.pageSize(1080, 1).w === 1080 && L.pageSize(1080, 1).h === 1080,
           '缩放不得改变画布尺寸');
        ok(L.simplifyRatio(1280, 720).w === 16 && L.simplifyRatio(1280, 720).h === 9,
           '1280×720 应约分为 16:9', JSON.stringify(L.simplifyRatio(1280, 720)));
        ok(L.simplifyRatio(1000, 700).w === 10 && L.simplifyRatio(1000, 700).h === 7,
           '1000×700 应约分为 10:7', JSON.stringify(L.simplifyRatio(1000, 700)));

        /* ---------- 2. 分辨率滑条往返 ---------- */
        ok(L.RES_STEPS.length === 6, '应有 6 个分辨率档位');
        for (var i = 0; i < L.RES_STEPS.length; i++) {
            var v = L.RES_STEPS[i];
            var back = L.sliderToRes(L.resToSlider(v));
            ok(near(back, v, 11), '档位往返应精确：' + v + ' → ' + back);
            ok(near(L.resToSlider(v), i, 0.001), '档位索引应对齐：' + v);
        }
        // 非档位值：960 应落在 0..1 之间
        var mid = L.resToSlider(1300);
        ok(mid > 0 && mid < 1, '1300 应落在 1080 与 1620 之间', String(mid));
        ok(L.sliderToRes(mid) > 1000 && L.sliderToRes(mid) < 1700, '反向映射应落在合理区间');

        /* ---------- 3. 尺寸钳制 ---------- */
        var s1 = L.clampResolution(7680, 16 / 9);
        ok(s1.w === 7680 && s1.h === 4320, '8K 16:9 应为 7680×4320', s1.w + '×' + s1.h);
        ok(s1.clamped === false, '8K 16:9 不应被收缩');
        var s2 = L.clampResolution(20000, 1);
        ok(s2.w <= 16384 && s2.h <= 16384, '超大尺寸应被钳到上限', s2.w + '×' + s2.h);
        ok(s2.clamped === true, '超大尺寸应标记 clamped');
        var s3 = L.pageSize(1080, 9 / 16);
        ok(s3.w === 608 && s3.h === 1080, '9:16 竖版 1080 应为 608×1080', s3.w + '×' + s3.h);

        /* ---------- 4. 换行 ---------- */
        var mono = function (s) { return s.length * 10; };
        var lines = L.wrap('一二三四五', 30, mono);
        ok(lines.length === 2 && lines[0] === '一二三' && lines[1] === '四五',
           '中文应按字折行', JSON.stringify(lines));
        var noStart = L.wrap('你好，世界', 30, mono);
        ok(noStart.length > 0, '断行结果不应为空');
        ok(noStart.every(function (ln) { return L.NO_LINE_START.indexOf(ln[0]) < 0; }),
           '行首不应是禁则标点', JSON.stringify(noStart));
        var latin = L.wrap('hello world', 55, mono);
        ok(latin.every(function (ln) { return ln.indexOf('hello') >= 0 || ln.indexOf('world') >= 0
            || ln.trim() === ''; }), '拉丁词不应被拆断', JSON.stringify(latin));

        /* ---------- 5. 分页：页尾不是标题 ---------- */
        var items = [];
        for (var k = 0; k < 12; k++) {
            items.push({ type: k % 3 === 0 ? 'h2' : 'para', font: 36,
                         lineHeight: 63, lines: ['行'], h: 63 });
        }
        var pages = L.paginate(items, 200);
        ok(pages.length > 1, '内容应跨页', 'pages=' + pages.length);
        pages.forEach(function (pg, idx) {
            if (!pg.length) return;
            var last = pg[pg.length - 1];
            ok(last.type !== 'h2' && last.type !== 'h1',
               '第 ' + (idx + 1) + ' 页页尾不应是标题', last.type);
        });

        /* ---------- 5b. 超长单块必须按行切开，不能画到画布外 ---------- */
        var tallLines = [];
        for (var t = 0; t < 200; t++) tallLines.push('第 ' + t + ' 行内容');
        var tall = [{ type: 'h2', font: 44, lineHeight: 77, lines: ['标题'], h: 77 },
                    { type: 'para', font: 36, lineHeight: 63, lines: tallLines, h: 63 * tallLines.length }];
        var tPages = L.paginate(tall, 400);
        ok(tPages.length >= 20, '超长单块应被切成多页', 'pages=' + tPages.length);
        tPages.forEach(function (pg, idx) {
            var used = 0;
            pg.forEach(function (it) { used += it.h; });
            ok(used <= 400 + 80, '第 ' + (idx + 1) + ' 页高度不应明显超出可用高',
               'used=' + used);
            // 每一页的正文块累计行数应守恒（不丢行）
        });
        var totalLines = 0;
        tPages.forEach(function (pg) {
            pg.forEach(function (it) { if (it.lines) totalLines += it.lines.length; });
        });
        ok(totalLines === tallLines.length + 1, '切页后总行数应守恒（不丢内容）',
           'got=' + totalLines + ' want=' + (tallLines.length + 1));

        /* ---------- 6. 单张适配 ---------- */
        var small = [{ type: 'para', font: 36, lineHeight: 63, lines: ['a'], h: 63 }];
        ok(L.fitCheck(small, 300).fit === true, '小内容应能装进单页');
        var huge = [];
        for (var j = 0; j < 40; j++) {
            huge.push({ type: 'para', font: 36, lineHeight: 63, lines: ['x'], h: 63 });
        }
        ok(L.fitCheck(huge, 300).fit === false, '超量内容应判定装不下');

        /* ---------- 7. 分块：取消记忆勾选后无 memory 块 ---------- */
        // 先把 world 固定成有内容的状态，避免受前面用例（会清空字段）影响
        world.name = '分块测试';
        world.role = '测试身份';
        world.summary = '测试概括';
        world.detail = '测试详述';
        await T.WorldService.save(world);
        var all = await T.collectShareContent(card, world, { name: true, mem: true, wv: true });
        var noMem = await T.collectShareContent(card, world, { name: true, mem: false, wv: true });
        var hasMemAll = all.blocks.some(function (b) { return b.text && b.text.indexOf('聊天记忆') >= 0; });
        var hasMemNone = noMem.blocks.some(function (b) { return b.text && b.text.indexOf('聊天记忆') >= 0; });
        ok(!hasMemNone, '取消记忆勾选后不应有记忆块');
        // 只断言「多勾选不会更少」，两个开关都关掉时必然不含记忆块
        ok(all.blocks.length >= noMem.blocks.length, '勾选越多块数不应减少',
           'all=' + all.blocks.length + ' noMem=' + noMem.blocks.length +
           ' memTurns=' + all.memTurns);
        var noneAtAll = await T.collectShareContent(card, world, { name: false, mem: false, wv: false });
        ok(noneAtAll.blocks.length === 0, '全部取消勾选应得空内容', String(noneAtAll.blocks.length));
        ok(typeof all.name === 'string' && all.name.length > 0, '应得出分享用的姓名');

        /* ---------- 8. cardDisplayName ---------- */
        var saved = card.nameWorldId;
        card.nameWorldId = world.id;
        world.name = '测试角色名';
        ok(T.cardDisplayName(card) === '测试角色名', '指定世界有名应取该名', T.cardDisplayName(card));
        world.name = '   ';
        ok(T.cardDisplayName(card) === T.UNNAMED_PERSONA, '指定世界名空白应回退未命名',
           T.cardDisplayName(card));
        world.name = '恢复名';
        card.nameWorldId = 'wld_not_exist';
        ok(T.cardDisplayName(card) === T.UNNAMED_PERSONA, '指定世界不存在应回退未命名',
           T.cardDisplayName(card));
        card.nameWorldId = 12345;
        ok(T.cardDisplayName(card) === T.UNNAMED_PERSONA, '非字符串 nameWorldId 应回退未命名',
           T.cardDisplayName(card));
        card.nameWorldId = null;
        ok(T.cardDisplayName(card) === T.UNNAMED_PERSONA, '未指定应回退未命名');
        card.nameWorldId = saved;

        /* ---------- 9. 真实画布渲染 ---------- */
        world.name = '分享测试';
        await T.WorldService.save(world);

        var r1 = await T.renderShareImages({
            name: true, mem: true, wv: true,
            ratio: 4 / 3, longEdge: 1080, mode: 'strict', dark: true
        });
        ok(!r1.error, '1080 渲染不应报错', r1.error);
        if (r1.pages && r1.pages.length) {
            ok(r1.pages.length === 1, '严格单张应只产出 1 页', 'pages=' + r1.pages.length);
            var cv1 = r1.pages[0];
            ok(cv1.width === 1080 && cv1.height === 810, '1080 4:3 应为 1080×810',
               cv1.width + '×' + cv1.height);
            var b1 = await T.canvasToBlob(cv1);
            ok(!!b1, 'toBlob 应返回数据');
            ok(b1.type === 'image/png', 'Blob 类型应为 image/png', b1.type);
            ok(b1.size > 1000, 'PNG 字节数应大于 1000', String(b1.size));
            // 背景像素应为深色底
            var g1 = cv1.getContext('2d');
            var px = g1.getImageData(2, 2, 1, 1).data;
            ok(px[0] < 60 && px[1] < 60 && px[2] < 80, '深色背景采样应偏暗',
               px[0] + ',' + px[1] + ',' + px[2]);
            // 正文区域应有非背景像素
            var nonBg = 0;
            for (var yy = 200; yy < Math.min(cv1.height, 700); yy += 17) {
                for (var xx = 100; xx < cv1.width - 100; xx += 17) {
                    var d = g1.getImageData(xx, yy, 1, 1).data;
                    if (d[0] > 80 || d[1] > 80 || d[2] > 80) nonBg++;
                }
            }
            ok(nonBg > 10, '正文区域应有可见的文字像素', 'nonBg=' + nonBg);
        }

        var r2 = await T.renderShareImages({
            name: true, mem: true, wv: true,
            ratio: 16 / 9, longEdge: 3840, mode: 'strict', dark: false
        });
        ok(!r2.error, '4K 渲染不应报错', r2.error);
        if (r2.pages && r2.pages.length) {
            ok(r2.pages[0].width === 3840 && r2.pages[0].height === 2160,
               '4K 16:9 应为 3840×2160',
               r2.pages[0].width + '×' + r2.pages[0].height);
            var g2 = r2.pages[0].getContext('2d');
            var pd = g2.getImageData(2, 2, 1, 1).data;
            ok(pd[0] > 200 && pd[1] > 200 && pd[2] > 200, '浅色背景采样应偏亮',
               pd[0] + ',' + pd[1] + ',' + pd[2]);
        }

        /* ---------- 9b. 字号随分辨率等比（planShare 层） ---------- */
        var pa = await T.planShare({
            name: true, mem: true, wv: true,
            ratio: 4 / 3, longEdge: 1080, mode: 'strict', dark: true
        });
        var pb = await T.planShare({
            name: true, mem: true, wv: true,
            ratio: 4 / 3, longEdge: 2160, mode: 'strict', dark: true
        });
        ok(!pa.error && !pb.error, '等比对照不应报错', (pa.error || '') + (pb.error || ''));
        if (!pa.error && !pb.error) {
            ok(near(pa.meta.scale, 1.0, 0.01), '1080 应使用 100% 文字缩放',
               String(pa.meta.scale));
            ok(near(pb.meta.scale, 2.0, 0.01), '2160 应使用 200% 文字缩放',
               String(pb.meta.scale));
            ok(pb.meta.scale > pa.meta.scale * 1.9, '字号应随分辨率等比放大');
            // 相对占比恒定：正文像素高 / 画布高 在两种分辨率下应基本一致
            var relA = (36 * pa.meta.scale) / pa.size.h;
            var relB = (36 * pb.meta.scale) / pb.size.h;
            ok(Math.abs(relA - relB) < 0.01,
               '1080 与 2160 的正文相对占比应一致',
               'relA=' + relA.toFixed(4) + ' relB=' + relB.toFixed(4));
            // 1080 下字号与旧版一致（36px 正文），但不再自动缩字：
            // 内容多时允许 fit=false，由界面提示并给建议值，导出不被禁止。
            ok(typeof pa.meta.fit === 'boolean', '应返回 fit 标记',
               String(pa.meta.fit));
            if (pa.meta.fit === false) {
                ok(pa.meta.suggestScale === null ||
                   (pa.meta.suggestScale >= 0.5 && pa.meta.suggestScale < 1.0),
                   '溢出时应给出 50%–100% 的建议缩放或 null',
                   String(pa.meta.suggestScale));
            }
        }
        // 显式 textScale 应覆盖自动值
        var pc = await T.planShare({
            name: true, mem: true, wv: true,
            ratio: 4 / 3, longEdge: 2160, mode: 'strict', dark: true, textScale: 1.25
        });
        ok(!pc.error && near(pc.meta.scale, 1.25, 0.001), '显式 textScale 应被采用',
           pc.error || String(pc.meta && pc.meta.scale));

        /* ---------- 9c. 严格单张放不下：不报错、给建议 ---------- */
        // 用一段很长的记忆把单页塞爆，但仍要保证 planShare 返回可绘制的一页
        var hugeText = '';
        for (var hq = 0; hq < 400; hq++) hugeText += '第' + hq + '段：这是一段用于测试单页溢出的超长文本。\n';
        var fakeHuge = { id: 'mem_h', personaId: T.memoryKey(card, world), raw: hugeText,
            turns: [{ role: 'other', text: hugeText }], importedAt: Date.now() };
        var origLoad2 = T.MemoryService.load;
        T.MemoryService.load = async function () { return fakeHuge; };
        var pd2;
        try {
            pd2 = await T.planShare({
                name: true, mem: true, wv: true,
                ratio: 4 / 3, longEdge: 1080, mode: 'strict', dark: true
            });
        } finally {
            T.MemoryService.load = origLoad2;
        }
        ok(!pd2.error, '严格单张放不下时不应禁止导出（不得返回 error）', pd2.error);
        if (!pd2.error) {
            ok(pd2.pages.length === 1, '严格单张仍应只排一页', 'pages=' + pd2.pages.length);
            ok(pd2.meta.fit === false, '应标记 fit=false', String(pd2.meta.fit));
            ok(pd2.meta.suggestScale === null ||
               (pd2.meta.suggestScale >= 0.5 && pd2.meta.suggestScale < 1.0),
               '建议缩放应落在 50%–100% 之间或为 null', String(pd2.meta.suggestScale));
        }

        /* ---------- 10. 自动多张 ---------- */
        // 造一段足够长的记忆，逼出多页
        var longText = '';
        for (var q = 0; q < 220; q++) longText += '第' + q + '段：这是一段用于测试自动多张分页的长文本。\n';
        var fakeMem = { id: 'mem_x', personaId: T.memoryKey(card, world), raw: longText,
            turns: [{ role: 'other', text: longText }], importedAt: Date.now() };
        var origLoad = T.MemoryService.load;
        T.MemoryService.load = async function () { return fakeMem; };
        var r3;
        try {
            r3 = await T.renderShareImages({
                name: true, mem: true, wv: false,
                ratio: 1, longEdge: 1080, mode: 'multi', dark: true
            });
        } finally {
            T.MemoryService.load = origLoad;
        }
        ok(!r3.error, '多页渲染不应报错', r3.error);
        ok(r3.pages && r3.pages.length > 1, '长内容应切成多页', 'pages=' + (r3.pages ? r3.pages.length : 0));
        if (r3.pages && r3.pages.length) {
            r3.pages.forEach(function (cv) {
                ok(cv.width === 1080 && cv.height === 1080, '每页应保持 1:1 比例',
                   cv.width + '×' + cv.height);
            });
            // 回归：一段超长记忆必须真正落到多页上，而不是只画在最后一页的顶部
            ok(r3.pages.length >= 3, '8000 字记忆应至少切成 3 页',
               'pages=' + r3.pages.length);
            // 除最后一页外，每页底部区域都应有内容（说明内容真的被摊到了各页）。
            // 最后一页允许只有一两行：分页按整行切，剩多少就画多少；
            // 字体宽度随皮肤而变，末页内容量本来就会浮动。
            // 但至少要检查一页——只有一页时下面的循环会一次都不跑，
            // 那等于这条断言被悄悄关掉了。
            ok(r3.pages.length >= 2, '长内容应切成多页（多页断言的前提）',
               'pages=' + r3.pages.length);
            var lastFull = Math.max(1, r3.pages.length - 1);
            for (var pi = 0; pi < lastFull; pi++) {
                var cv = r3.pages[pi];
                var g = cv.getContext('2d');
                var ink = 0;
                var y0 = Math.round(cv.height * 0.75);
                for (var yy = y0; yy < cv.height - 60; yy += 9) {
                    for (var xx = 100; xx < cv.width - 100; xx += 9) {
                        var d = g.getImageData(xx, yy, 1, 1).data;
                        if (d[0] > 80 || d[1] > 80 || d[2] > 80) ink++;
                    }
                }
                ok(ink > 3, '第 ' + (pi + 1) + ' 页下部应有内容（不应只堆在首页）', 'ink=' + ink);
            }
            var names = [];
            for (var z = 1; z <= r3.pages.length; z++) names.push(T.shareFilename(z, r3.pages.length));
            ok(names[0].indexOf('-1.png') >= 0, '多页文件名应带 -1 序号', names[0]);
            ok(names[1].indexOf('-2.png') >= 0, '多页文件名应带 -2 序号', names[1]);
        }

        /* ---------- 11. 背景配色预设 ---------- */
        ok(Array.isArray(T.SHARE_BG_PRESETS) && T.SHARE_BG_PRESETS.length >= 4,
           '应有至少 4 套背景预设', String(T.SHARE_BG_PRESETS && T.SHARE_BG_PRESETS.length));
        ok(T.shareBgGradient('auto', true) === null, 'auto 预设应为纯色（返回 null）');
        ok(T.shareBgGradient('nonexistent', true) === null, '未知预设应回落纯色');
        var jadeDark = T.shareBgGradient('jade', true);
        var jadeLight = T.shareBgGradient('jade', false);
        ok(Array.isArray(jadeDark) && jadeDark.length === 2, 'jade 深色应返回两个颜色');
        ok(Array.isArray(jadeLight) && jadeLight.length === 2, 'jade 浅色应返回两个颜色');
        ok(jadeDark[0] !== jadeLight[0], '同一预设的深/浅色应不同');

        // 渐变必须真的画进图里：左上与右下角的像素应不同（纯色时两者相同）
        world.name = '渐变测试';
        world.role = '测试身份';
        world.summary = '用于渐变渲染';
        world.detail = '正文内容';
        await T.WorldService.save(world);
        T.fillEditor(world);
        var rGrad = await T.renderShareImages({
            name: true, mem: false, wv: false,
            ratio: 1, longEdge: 1080, mode: 'strict', dark: true, bg: 'jade'
        });
        ok(!rGrad.error, '渐变渲染不应报错', rGrad.error);
        if (rGrad.pages && rGrad.pages.length) {
            var gcv = rGrad.pages[0];
            var gg = gcv.getContext('2d');
            var tl = gg.getImageData(1, 1, 1, 1).data;
            var br = gg.getImageData(gcv.width - 2, gcv.height - 2, 1, 1).data;
            var diff = Math.abs(tl[0] - br[0]) + Math.abs(tl[1] - br[1]) + Math.abs(tl[2] - br[2]);
            ok(diff > 2, '渐变背景：左上与右下像素应有差异', 'tl=' + tl[0] + ',' + tl[1] + ',' + tl[2] +
               ' br=' + br[0] + ',' + br[1] + ',' + br[2] + ' diff=' + diff);
        }
        var rFlat = await T.renderShareImages({
            name: true, mem: false, wv: false,
            ratio: 1, longEdge: 1080, mode: 'strict', dark: true, bg: 'auto'
        });
        if (rFlat.pages && rFlat.pages.length) {
            var fcv = rFlat.pages[0];
            var fg = fcv.getContext('2d');
            var f1 = fg.getImageData(1, 1, 1, 1).data;
            var f2 = fg.getImageData(fcv.width - 2, fcv.height - 2, 1, 1).data;
            var fdiff = Math.abs(f1[0] - f2[0]) + Math.abs(f1[1] - f2[1]) + Math.abs(f1[2] - f2[2]);
            ok(fdiff === 0, 'auto 预设应为纯色（两角像素相同）', 'diff=' + fdiff);
        }

        /* ---------- 11b. 配色与文字的可读性（WCAG 对比度） ---------- */
        // 浅色渐变底色在 #e0e4f5–#fdf2e6 之间，强调色与正文都必须够深。
        // 非文本 UI 元素门槛 3.0，正文门槛 4.5。
        var palLight = T.sharePalette(false);
        var palDark = T.sharePalette(true);
        var gradPresets = T.SHARE_BG_PRESETS.filter(function (p) { return p.grad; });
        ok(gradPresets.length >= 5, '应有至少 5 套渐变预设', String(gradPresets.length));

        gradPresets.forEach(function (p) {
            var stops = [];
            (p.grad || []).forEach(function (c) { stops.push({ mode: 'dark', bg: c }); });
            (p.light || []).forEach(function (c) { stops.push({ mode: 'light', bg: c }); });
            stops.forEach(function (s) {
                var pal = s.mode === 'dark' ? palDark : palLight;
                var rc = contrast(s.bg, pal.accent);
                ok(rc >= 3.0, s.mode + '/' + p.key + ' 强调色对比度应 ≥ 3.0',
                   'bg=' + s.bg + ' accent=' + pal.accent + ' ratio=' + rc.toFixed(2));
                var rt = contrast(s.bg, pal.text);
                ok(rt >= 4.5, s.mode + '/' + p.key + ' 正文对比度应 ≥ 4.5',
                   'bg=' + s.bg + ' text=' + pal.text + ' ratio=' + rt.toFixed(2));
            });
        });

        /* ---------- 11b2. 皮肤令牌覆盖完整性 ---------- */
        // 换肤最容易漏的是「某些硬编码颜色 / 字号没被覆盖」：
        // 视觉上看不出来，直到某套皮肤用完全不同的主色才露馅。
        // 这里直接读计算样式，断言关键令牌都被覆盖成了非基版值。
        var cs0 = getComputedStyle(document.documentElement);
        var accentV = (cs0.getPropertyValue('--accent') || '').trim();
        ok(!!accentV, '必须能取到 --accent');

        // 1) 页面上不应残留基版的青绿 / 金色硬编码边框。
        //    做法：找世界列表的选中项与新增按钮，读它们的实际边框色，
        //    断言它与 --accent 同色系（而不是基版固定的金色）。
        var onItem = document.querySelector('.world-item.on');
        if (onItem) {
            var bc = getComputedStyle(onItem).borderColor || '';
            ok(bc.indexOf('224, 164, 88') < 0 && bc.indexOf('224,164,88') < 0,
               '选中态边框不应是基版金色', bc);
        } else {
            ok(true, '当前没有选中项，跳过边框色检查');
        }

        // 2) 尺寸令牌必须全部有值（缺一个就会退回浏览器默认或被继承）
        var needTokens = ['--fs-100', '--fs-110', '--fs-120', '--fs-130', '--fs-140',
                          '--fs-150', '--fs-160', '--fs-170', '--fs-180', '--fs-190',
                          '--fs-200', '--fs-220', '--fs-240', '--fs-260', '--fs-280',
                          '--fs-300', '--fs-320',
                          '--sp-0', '--sp-1', '--sp-2', '--sp-3', '--sp-4', '--sp-5',
                          '--sp-6', '--sp-7', '--sp-8', '--sp-9', '--sp-10',
                          '--radius', '--radius-sm', '--pad-panel', '--pad-form', '--pad-head'];
        var missing = [];
        needTokens.forEach(function (t) {
            if (!(cs0.getPropertyValue(t) || '').trim()) missing.push(t);
        });
        ok(missing.length === 0, '尺寸令牌不应有缺值', missing.join(','));

        // 3) 正文与品牌标记的字号必须真的取到令牌（而不是被写死），
        //    并且若本文件是皮肤（--skin-scale 有值），基准字号必须与基版不同。
        var skinScale = (cs0.getPropertyValue('--skin-scale') || '').trim();
        // 令牌可能写成 px 也可能写成 rem，统一换算成 px 再比较
        function toPx(v) {
            v = String(v || '').trim();
            if (v.indexOf('rem') > 0) return parseFloat(v) * 16;
            return parseFloat(v) || 0;
        }
        if (skinScale) {
            var fs320 = toPx(cs0.getPropertyValue('--fs-320'));
            var fs300 = toPx(cs0.getPropertyValue('--fs-300'));
            ok(Math.abs(fs320 - 14 * parseFloat(skinScale)) < 0.5,
               '皮肤应覆盖 --fs-320 到基准值 × 缩放', 'fs320=' + fs320 + 'px scale=' + skinScale);
            ok(Math.abs(fs300 - 13 * parseFloat(skinScale)) < 0.5,
               '皮肤应覆盖 --fs-300 到基准值 × 缩放', 'fs300=' + fs300 + 'px scale=' + skinScale);
        }

        var bodyFs = toPx(getComputedStyle(document.body).fontSize);
        var fs320px = toPx(cs0.getPropertyValue('--fs-320'));
        ok(Math.abs(bodyFs - fs320px) < 0.5,
           'body 字号应来自 --fs-320', 'body=' + bodyFs + 'px token=' + fs320px + 'px');
        var bm = document.querySelector('.brand-mark');
        if (bm) {
            var bmFs = toPx(getComputedStyle(bm).fontSize);
            var fs300px = toPx(cs0.getPropertyValue('--fs-300'));
            ok(Math.abs(bmFs - fs300px) < 0.5,
               '品牌标记字号应来自 --fs-300', 'mark=' + bmFs + 'px token=' + fs300px + 'px');
        }

        /* ---------- 11c. 浅色渐变下标题确实画得出来（像素级） ---------- */
        var rLight = await T.renderShareImages({
            name: true, mem: false, wv: false,
            ratio: 1, longEdge: 1080, mode: 'strict', dark: false, bg: 'jade'
        });
        ok(!rLight.error, '浅色渐变渲染不应报错', rLight.error);
        if (rLight.pages && rLight.pages.length) {
            var lcv = rLight.pages[0];
            var lg = lcv.getContext('2d');
            // 背景基准色（左上角）
            var bgPx = lg.getImageData(2, 2, 1, 1).data;
            var bgLum = relLum('#' + [bgPx[0], bgPx[1], bgPx[2]].map(function (v) {
                return ('0' + v.toString(16)).slice(-2);
            }).join(''));
            // 采样标题行区域，找最暗像素
            var darkest = 1;
            for (var yy = 60; yy < 260; yy += 6) {
                for (var xx = 80; xx < lcv.width - 80; xx += 6) {
                    var d = lg.getImageData(xx, yy, 1, 1).data;
                    var lum = relLum('#' + [d[0], d[1], d[2]].map(function (v) {
                        return ('0' + v.toString(16)).slice(-2);
                    }).join(''));
                    if (lum < darkest) darkest = lum;
                }
            }
            // 浅底上的深色文字：最暗像素应明显低于背景亮度
            ok(darkest < bgLum * 0.5, '浅色渐变上应能画出明显更暗的文字',
               'bgLum=' + bgLum.toFixed(3) + ' darkest=' + darkest.toFixed(3));
            var inkRatio = (bgLum + 0.05) / (darkest + 0.05);
            ok(inkRatio >= 4.5, '浅色渐变上文字与背景对比度应 ≥ 4.5',
               'ratio=' + inkRatio.toFixed(2));
        }

        /* ---------- 12. 布局：分享图按钮已在底部按钮排，不再悬浮 ---------- */
        var fab = document.querySelector('#shareFab');
        ok(!!fab, '分享图按钮应存在');
        ok(!fab.classList.contains('fab'), '分享图按钮不应再是悬浮样式（.fab）');
        ok(!!fab.closest('.promptbar'), '分享图按钮应在底部提示词条内');
        var fabPos = getComputedStyle(fab).position;
        ok(fabPos !== 'fixed', '分享图按钮不应固定定位', fabPos);

        /* ---------- 13. 布局：滑条不被输入框遮挡，可拖到 8K ---------- */
        T.openShareModal();
        var range = document.querySelector('#resRange');
        var num = document.querySelector('#resInput');
        var rr = range.getBoundingClientRect();
        var nr = num.getBoundingClientRect();
        ok(rr.right <= nr.left + 1, '滑条右沿不应与输入框重叠',
           'range.right=' + Math.round(rr.right) + ' input.left=' + Math.round(nr.left));
        ok(rr.width > 0 && nr.width > 0, '滑条与输入框都应有宽度');
        // 滑条必须占满剩余空间（而不是被输入框挤成一小段）：
        // 以一个窄容器为基准，滑条宽度应至少是输入框宽度的 2 倍
        ok(rr.width >= nr.width * 2, '滑条宽度应明显大于输入框（否则拖不满全程）',
           'range.w=' + Math.round(rr.width) + ' input.w=' + Math.round(nr.width));
        // 滑条能拖到最右（value = max）
        range.value = range.max;
        range.dispatchEvent(new Event('input'));
        var resAtMax = Number(document.querySelector('#resInput').value);
        ok(resAtMax >= 7000, '滑条拉到最右应达到 8K 档（≥7000）', String(resAtMax));
        // 尺寸文案已下移，不与滑条同行
        var label = document.querySelector('#resLabel');
        var lr = label.getBoundingClientRect();
        ok(lr.top >= rr.bottom - 1, '尺寸文案应在滑条下方',
           'label.top=' + Math.round(lr.top) + ' range.bottom=' + Math.round(rr.bottom));

        // 窄容器下也不能遮挡：把弹窗盒子压窄，重新量两者是否重叠
        var box = document.querySelector('#shareModal .modal-box');
        var origW = box.style.width;
        box.style.width = '380px';
        // 触发一次重排后再量
        void box.offsetWidth;
        var rr2 = range.getBoundingClientRect();
        var nr2 = num.getBoundingClientRect();
        ok(rr2.right <= nr2.left + 1, '窄容器下滑条右沿仍不应与输入框重叠',
           'range.right=' + Math.round(rr2.right) + ' input.left=' + Math.round(nr2.left));
        ok(rr2.width >= 60, '窄容器下滑条仍应保有可拖动宽度',
           'width=' + Math.round(rr2.width));
        box.style.width = origW;

        /* ---------- 14. 滑条只停在档位 ---------- */
        range.value = '3.7';
        range.dispatchEvent(new Event('input'));
        ok(Number(range.value) === Math.round(Number(range.value)),
           '滑条应吸附到整数档位', 'value=' + range.value);
        ok(Number(num.value) === L.RES_STEPS[Number(range.value)],
           '吸附后长边应等于该档位像素',
           num.value + ' vs ' + L.RES_STEPS[Number(range.value)]);
        // 输入框仍可停档间值，不被滑条吸附回去
        num.value = '1300';
        num.dispatchEvent(new Event('change'));
        ok(Number(num.value) === 1300, '输入框应保留非档位值', num.value);
        ok(Number(range.value) > 0 && Number(range.value) < 1,
           '非档位值时滑条应停在档间', 'slider=' + range.value);
        ok(document.querySelector('#resLabel').textContent.indexOf('1300') === 0,
           '尺寸文案应显示输入的长边', document.querySelector('#resLabel').textContent);

        /* ---------- 15. 像素宽高联动 ---------- */
        var pxW = document.querySelector('#pxW');
        var pxH = document.querySelector('#pxH');
        var rwBox = document.querySelector('#ratioW');
        var rhBox = document.querySelector('#ratioH');
        // 先固定成 4:3
        rwBox.value = '4'; rhBox.value = '3';
        rwBox.dispatchEvent(new Event('change'));
        num.value = '2160'; num.dispatchEvent(new Event('change'));
        ok(Number(pxW.value) === 2160 && Number(pxH.value) === 1620,
           '选比例后像素框应同步为 2160×1620', pxW.value + '×' + pxH.value);
        // 改宽 → 高自动算
        pxW.value = '3000';
        pxW.dispatchEvent(new Event('change'));
        ok(Number(pxW.value) === 3000, '宽度应保留输入值', pxW.value);
        ok(Number(pxH.value) === 2250, '4:3 下 3000 宽应得 2250 高', pxH.value);
        // 改高 → 宽自动算；4:3 仍是最简比，比例框保持不变
        pxH.value = '2000';
        pxH.dispatchEvent(new Event('change'));
        ok(Number(pxW.value) === 2667, '4:3 下 2000 高应得 2667 宽', pxW.value);
        ok(Number(rwBox.value) === 4 && Number(rhBox.value) === 3,
           '4:3 像素改动后比例框应保持 4:3', rwBox.value + ':' + rhBox.value);
        // 4:3 下 1280 宽 → 960 高，约分仍是 4:3，比例框保持并可被约分识别
        pxW.value = '1280'; pxW.dispatchEvent(new Event('change'));
        ok(Number(pxH.value) === 960, '4:3 下 1280 宽应得 960 高', pxH.value);
        ok(Number(rwBox.value) === 4 && Number(rhBox.value) === 3,
           '1280×960 应回填为最简 4:3', rwBox.value + ':' + rhBox.value);
        // 直接给一组 16:9 的像素：宽 3840 时若比例为 16:9 才成立，这里改为先选 16:9
        rwBox.value = '16'; rhBox.value = '9';
        rwBox.dispatchEvent(new Event('change'));
        pxW.value = '3840'; pxW.dispatchEvent(new Event('change'));
        ok(Number(pxH.value) === 2160, '16:9 下 3840 宽应得 2160 高', pxH.value);
        ok(Number(rwBox.value) === 16 && Number(rhBox.value) === 9,
           '16:9 像素改动后比例框应保持 16:9', rwBox.value + ':' + rhBox.value);
        ok(document.querySelector('#ratioBtn').textContent.indexOf('自定义') < 0,
           '命中预设时不应显示「自定义」', document.querySelector('#ratioBtn').textContent);
        // 自定义比例：不能约进 32 的比例不应写进比例框（避免被上限拒绝后退回旧值）
        pxH.value = '1000'; pxH.dispatchEvent(new Event('change'));
        ok(Number(rwBox.value) === 16 && Number(rhBox.value) === 9,
           '约不进 32 的像素比不应改写比例框', rwBox.value + ':' + rhBox.value);

        /* ---------- 16. 文字缩放框与自动值 ---------- */
        num.value = '1080'; num.dispatchEvent(new Event('change'));
        var ts = document.querySelector('#textScaleInput');
        ok(Number(ts.value) === 100, '1080 时文字缩放应为 100%', ts.value);
        num.value = '2160'; num.dispatchEvent(new Event('change'));
        ok(Number(ts.value) === 200, '2160 时文字缩放应为 200%', ts.value);
        num.value = '7680'; num.dispatchEvent(new Event('change'));
        ok(Number(ts.value) === 300, '8K 时文字缩放应封顶 300%', ts.value);
        // 手改百分比 → 不再跟随
        ts.value = '70'; ts.dispatchEvent(new Event('change'));
        num.value = '2160'; num.dispatchEvent(new Event('change'));
        ok(Number(ts.value) === 70, '手动值不应被分辨率覆盖', ts.value);
        ok(document.querySelector('#textScaleHint').textContent.indexOf('手动') >= 0,
           '手动模式下应标注「手动」', document.querySelector('#textScaleHint').textContent);
        // 点「跟随分辨率」恢复自动
        document.querySelector('#textScaleAutoBtn').click();
        ok(Number(ts.value) === 200, '恢复跟随后应回到 200%', ts.value);

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
            "找不到测试缝锚点。如果人设应用的 selftest 对象末尾改过，"
            "请同步更新本脚本的 SEAM_ANCHOR。"
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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

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
    title = (m.group(1).strip() if m else "")

    if title.startswith("PASS"):
        return True, "PASS"
    if title.startswith("FAIL:"):
        return False, title[len("FAIL:"):].strip()

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
            build_temp_copy(tmp)
            try:
                passed, detail = run_one(browser, tmp)
            except subprocess.TimeoutExpired:
                passed, detail = False, f"打开超时（超过 {SUBPROCESS_TIMEOUT_SECONDS} 秒）"
        if passed:
            print()
            print(f"分享图逻辑单测完成：全部断言通过（第 {attempt} 次运行）。")
            return 0
        last_detail = detail
        if attempt < MAX_ATTEMPTS:
            print(f"[重试] 第 {attempt} 次未通过：{detail}")

    print()
    print(f"[问题] 分享图逻辑单测失败：{last_detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
