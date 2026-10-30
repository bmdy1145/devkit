// SubMerge Pro 全功能版（C++ / Win32 API）
//
// 版本：A1_II_Φ10_Cpp_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 图形界面版：加载字幕、条目列表、粘贴译文并应用、双语拆分预览、导出 SRT。
// 纯 Win32 API，无第三方依赖。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>

#include <algorithm>
#include <fstream>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "comdlg32.lib")

#define ID_OPEN      5001
#define ID_APPLY     5002
#define ID_PREVIEW   5003
#define ID_EXPORT    5004
#define ID_LIST      5005
#define ID_TRANS     5006
#define ID_OUT       5007
#define ID_LANG      5008
#define ID_MAX       5009
#define ID_MODE      5010

struct Entry {
    int index;
    std::wstring start, end, text, translated;
};

static std::vector<Entry> g_entries;
static std::wstring g_filename;
static HWND g_list, g_trans, g_out, g_status, g_lang, g_maxBox, g_mode;

static bool isCjk(wchar_t c) { return c >= 0x4E00 && c <= 0x9FFF; }

// 仅 ASCII 字母数字。不能用 iswalnum：它把汉字也算作字母，会让 addBoundary
// 在「中中」之间也插空格。
static bool isAsciiAlnum(wchar_t c) {
    return (c >= L'0' && c <= L'9') || (c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z');
}
static bool isAsciiAlpha(wchar_t c) {
    return (c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z');
}

static std::wstring trimW(const std::wstring& s) {
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return L"";
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::string W2U8(const std::wstring& w) {
    if (w.empty()) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

static std::wstring U82W(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &w[0], n);
    return w;
}

static std::vector<std::wstring> tokenize(const std::wstring& text) {
    std::vector<std::wstring> tokens;
    size_t i = 0;
    while (i < text.size()) {
        if (isCjk(text[i])) {
            size_t j = i;
            while (j < text.size() && isCjk(text[j])) ++j;
            for (size_t k = i; k < j; k += 2)
                tokens.push_back(text.substr(k, std::min<size_t>(2, j - k)));
            i = j;
        } else if (iswspace(text[i])) {
            ++i;
        } else {
            // 与 HTML 参考实现一致：[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S
            // 字母数字连续段（可带 'xx）整体成一个 token，其余非空白字符各自成 token，
            // 所以 "world," 拆成 "world" 与 ","。
            size_t j = i;
            while (j < text.size() && !isCjk(text[j]) && !iswspace(text[j])) ++j;
            size_t k = i;
            while (k < j) {
                if (isAsciiAlnum(text[k])) {
                    size_t m = k;
                    while (m < j && isAsciiAlnum(text[m])) ++m;
                    if (m < j && text[m] == L'\'') {
                        size_t a = m + 1, b = a;
                        while (b < j && isAsciiAlpha(text[b])) ++b;
                        if (b > a) m = b;
                    }
                    tokens.push_back(text.substr(k, m - k));
                    k = m;
                } else {
                    tokens.push_back(text.substr(k, 1));
                    ++k;
                }
            }
            i = j;
        }
    }
    return tokens;
}

static std::wstring joinTokens(const std::vector<std::wstring>& tokens) {
    std::wstring out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0 && !isCjk(tokens[i - 1].back()) && !isCjk(tokens[i].front())) out += L' ';
        out += tokens[i];
    }
    return out;
}

static std::wstring addBoundary(const std::wstring& s) {
    std::wstring out;
    for (size_t i = 0; i < s.size(); ++i) {
        if (i > 0) {
            wchar_t p = s[i - 1], c = s[i];
            if ((isAsciiAlnum(p) && isCjk(c)) || (isCjk(p) && isAsciiAlnum(c))) out += L' ';
        }
        out += s[i];
    }
    return out;
}

static std::vector<std::pair<std::wstring, std::wstring>>
splitPaired(const std::wstring& orig, const std::wstring& trans, int maxWords) {
    auto o = tokenize(orig);
    auto t = tokenize(trans);
    std::vector<std::pair<std::wstring, std::wstring>> chunks;
    size_t oi = 0, ti = 0;
    while (oi < o.size() || ti < t.size()) {
        std::vector<std::wstring> oc, tc;
        int words = 0;
        while ((oi < o.size() || ti < t.size()) && words < maxWords) {
            bool canO = oi < o.size(), canT = ti < t.size();
            if (canO && canT) {
                if (words + 2 <= maxWords) { oc.push_back(o[oi++]); tc.push_back(t[ti++]); words += 2; }
                else break;
            } else if (canO) {
                if (words + 1 <= maxWords) { oc.push_back(o[oi++]); words++; } else break;
            } else if (canT) {
                if (words + 1 <= maxWords) { tc.push_back(t[ti++]); words++; } else break;
            }
        }
        chunks.push_back({ addBoundary(joinTokens(oc)), addBoundary(joinTokens(tc)) });
    }
    if (chunks.empty()) chunks.push_back({ orig, trans });
    return chunks;
}

static long long timeToMs(const std::wstring& s) {
    size_t p1 = s.find(L':');
    if (p1 == std::wstring::npos) return 0;
    size_t p2 = s.find(L':', p1 + 1);
    if (p2 == std::wstring::npos) return 0;
    long long h = _wtoi64(s.substr(0, p1).c_str());
    long long m = _wtoi64(s.substr(p1 + 1, p2 - p1 - 1).c_str());
    std::wstring sp = s.substr(p2 + 1);
    long long sec = 0, ms = 0;
    auto comma = sp.find(L',');
    auto dot = sp.find(L'.');
    if (comma != std::wstring::npos) {
        sec = _wtoi64(sp.substr(0, comma).c_str());
        std::wstring frac = sp.substr(comma + 1);
        while (frac.size() < 3) frac += L'0';
        ms = _wtoi64(frac.substr(0, 3).c_str());
    } else if (dot != std::wstring::npos) {
        sec = _wtoi64(sp.substr(0, dot).c_str());
        std::wstring frac = sp.substr(dot + 1);
        while (frac.size() < 2) frac += L'0';
        double frames = _wtof(frac.substr(0, 2).c_str());
        ms = (long long)(frames * 40.0 + 0.5);
    } else {
        sec = _wtoi64(sp.c_str());
    }
    return (h * 3600 + m * 60 + sec) * 1000 + ms;
}

static std::wstring msToTime(long long ms) {
    long long h = ms / 3600000; ms %= 3600000;
    long long m = ms / 60000; ms %= 60000;
    long long s = ms / 1000;
    wchar_t buf[32];
    swprintf(buf, 32, L"%02lld:%02lld:%02lld,%03lld", h, m, s, ms % 1000);
    return buf;
}

static std::vector<Entry> parseSubtitle(const std::wstring& content) {
    static const std::wregex timeRe(
        L"^(\\d{1,2}:\\d{2}:\\d{2}[,.]\\d{1,3})\\s*-->\\s*(\\d{1,2}:\\d{2}:\\d{2}[,.]\\d{1,3})$");

    std::wstring clean = content;
    if (clean.rfind(L"\uFEFF", 0) == 0) clean = clean.substr(1);
    std::wstring norm;
    for (size_t i = 0; i < clean.size(); ++i) {
        if (clean[i] == L'\r') { if (i + 1 < clean.size() && clean[i + 1] == L'\n') continue; norm += L'\n'; }
        else norm += clean[i];
    }

    std::vector<std::wstring> blocks;
    std::wstring cur;
    for (wchar_t ch : norm) {
        if (ch == L'\n') {
            if (trimW(cur).empty()) {
                if (!cur.empty()) { blocks.push_back(cur); cur.clear(); }
            } else cur += L'\n';
        } else cur += ch;
    }
    if (!cur.empty() && !trimW(cur).empty()) blocks.push_back(cur);

    std::vector<Entry> entries;
    std::set<int> seen;
    for (const auto& block : blocks) {
        std::vector<std::wstring> lines;
        std::wstringstream ss(block);
        std::wstring line;
        while (std::getline(ss, line)) {
            auto t = trimW(line);
            if (!t.empty()) lines.push_back(t);
        }
        if (lines.size() < 3) continue;
        if (lines[0].find_first_not_of(L"0123456789") != std::wstring::npos) continue;
        std::wsmatch m;
        if (!std::regex_match(lines[1], m, timeRe)) continue;
        int index = _wtoi(lines[0].c_str());
        if (seen.count(index)) continue;
        seen.insert(index);

        std::wstring start = m[1].str(), end = m[2].str();
        std::replace(start.begin(), start.end(), L'.', L',');
        std::replace(end.begin(), end.end(), L'.', L',');
        long long sm = timeToMs(start);
        if (sm >= timeToMs(end)) end = msToTime(sm + 1);

        std::wstring text;
        for (size_t i = 2; i < lines.size(); ++i) {
            if (!text.empty()) text += L'\n';
            text += lines[i];
        }
        if (trimW(text).empty()) continue;

        Entry e;
        e.index = index; e.start = start; e.end = end; e.text = text;
        entries.push_back(e);
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& a, const Entry& b) { return a.index < b.index; });
    return entries;
}

static int applyTranslation(std::vector<Entry>& entries, const std::wstring& trans) {
    std::map<int, std::wstring> mapping;
    std::wstringstream ss(trans);
    std::wstring line;
    int cur = -1;
    std::wstring buf;
    auto flush = [&]() { if (cur >= 0) mapping[cur] = trimW(buf); };

    while (std::getline(ss, line)) {
        auto t = trimW(line);
        if (!t.empty() && t[0] == L'[') {
            auto close = t.find(L']');
            if (close != std::wstring::npos) {
                std::wstring num = t.substr(1, close - 1);
                if (num.find_first_not_of(L"0123456789") == std::wstring::npos) {
                    flush();
                    cur = _wtoi(num.c_str());
                    buf = trimW(t.substr(close + 1));
                    continue;
                }
            }
        }
        if (cur >= 0 && !t.empty()) {
            if (!buf.empty()) buf += L'\n';
            buf += t;
        }
    }
    flush();

    int applied = 0;
    for (auto& e : entries) {
        auto it = mapping.find(e.index);
        if (it != mapping.end()) { e.translated = it->second; ++applied; }
    }
    return applied;
}

static void refreshList() {
    SendMessageW(g_list, LB_RESETCONTENT, 0, 0);
    for (const auto& e : g_entries) {
        std::wstring line = std::to_wstring(e.index) + L"  " + e.start + L" --> " + e.end + L"  " + e.text.substr(0, 40);
        if (!e.translated.empty()) line += L"  |  " + e.translated.substr(0, 30);
        SendMessageW(g_list, LB_ADDSTRING, 0, (LPARAM)line.c_str());
    }
}

static void doOpen() {
    OPENFILENAMEW ofn = { 0 };
    wchar_t path[MAX_PATH] = { 0 };
    ofn.lStructSize = sizeof(ofn);
    ofn.lpstrFilter = L"字幕文件\0*.srt;*.bcc;*.txt\0所有文件\0*.*\0";
    ofn.lpstrFile = path;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&ofn)) return;

    std::ifstream f(W2U8(path), std::ios::binary);
    if (!f) { SetWindowTextW(g_status, L"无法读取文件"); return; }
    std::ostringstream ss;
    ss << f.rdbuf();
    g_entries = parseSubtitle(U82W(ss.str()));
    if (g_entries.empty()) { SetWindowTextW(g_status, L"解析失败：未找到字幕条目"); return; }

    g_filename = path;
    wchar_t buf[256];
    swprintf(buf, 256, L"%zu 条", g_entries.size());
    SetWindowTextW(g_status, buf);
    refreshList();
}

static void doApply() {
    if (g_entries.empty()) { SetWindowTextW(g_status, L"请先加载字幕文件"); return; }
    int len = GetWindowTextLengthW(g_trans);
    std::wstring text(len + 1, L'\0');
    GetWindowTextW(g_trans, &text[0], len + 1);
    text.resize(len);
    int n = applyTranslation(g_entries, text);
    wchar_t buf[128];
    if (n == 0) swprintf(buf, 128, L"未检测到 [编号] 格式");
    else swprintf(buf, 128, L"已应用 %d 条译文", n);
    SetWindowTextW(g_status, buf);
    refreshList();
}

static void doPreview() {
    if (g_entries.empty()) return;
    wchar_t mbuf[16] = { 0 };
    GetWindowTextW(g_maxBox, mbuf, 16);
    int mw = _wtoi(mbuf);
    if (mw < 2) mw = 10;

    std::wstring out;
    for (const auto& e : g_entries) {
        for (const auto& c : splitPaired(e.text, e.translated, mw)) {
            std::wstring body = c.second.empty() ? c.first : c.first + L"\r\n" + c.second;
            out += L"[" + std::to_wstring(e.index) + L"] " + trimW(body) + L"\r\n";
        }
    }
    SetWindowTextW(g_out, out.c_str());
}

static void doExport() {
    if (g_entries.empty()) { SetWindowTextW(g_status, L"请先加载字幕文件"); return; }

    wchar_t lang[64] = { 0 };
    GetWindowTextW(g_lang, lang, 64);
    int mode = (int)SendMessageW(g_mode, CB_GETCURSEL, 0, 0);

    OPENFILENAMEW ofn = { 0 };
    wchar_t path[MAX_PATH] = { 0 };
    swprintf(path, MAX_PATH, L"【已翻译-%s】export.srt", lang);
    ofn.lStructSize = sizeof(ofn);
    ofn.lpstrFilter = L"SRT\0*.srt\0";
    ofn.lpstrFile = path;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST;
    if (!GetSaveFileNameW(&ofn)) return;

    std::wstring out;
    for (const auto& e : g_entries) {
        std::wstring text;
        if (mode == 1) text = e.text;
        else if (mode == 2) text = e.translated;
        else {
            if (!e.translated.empty() && !e.text.empty()) text = e.text + L"\n" + e.translated;
            else if (!e.translated.empty()) text = e.translated;
            else text = e.text;
        }
        out += std::to_wstring(e.index) + L"\n" + e.start + L" --> " + e.end + L"\n" + text + L"\n\n";
    }
    std::ofstream f(W2U8(path), std::ios::binary);
    auto u8 = W2U8(out);
    f.write(u8.data(), (std::streamsize)u8.size());
    SetWindowTextW(g_status, L"已导出");
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        int y = 10;
        CreateWindowW(L"BUTTON", L"打开字幕文件…", WS_CHILD | WS_VISIBLE,
                      10, y, 130, 30, hwnd, (HMENU)ID_OPEN, NULL, NULL);
        g_status = CreateWindowW(L"STATIC", L"就绪", WS_CHILD | WS_VISIBLE,
                                 150, y + 7, 500, 22, hwnd, NULL, NULL, NULL);
        y += 40;

        CreateWindowW(L"STATIC", L"目标语言：", WS_CHILD | WS_VISIBLE, 10, y, 70, 22, hwnd, NULL, NULL, NULL);
        g_lang = CreateWindowW(L"EDIT", L"中文", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                               85, y, 90, 22, hwnd, (HMENU)ID_LANG, NULL, NULL);
        CreateWindowW(L"STATIC", L"最多词数：", WS_CHILD | WS_VISIBLE, 190, y, 70, 22, hwnd, NULL, NULL, NULL);
        g_maxBox = CreateWindowW(L"EDIT", L"10", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_NUMBER,
                                 265, y, 50, 22, hwnd, (HMENU)ID_MAX, NULL, NULL);
        CreateWindowW(L"STATIC", L"导出内容：", WS_CHILD | WS_VISIBLE, 330, y, 70, 22, hwnd, NULL, NULL, NULL);
        g_mode = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
                               405, y, 110, 100, hwnd, (HMENU)ID_MODE, NULL, NULL);
        SendMessageW(g_mode, CB_ADDSTRING, 0, (LPARAM)L"双语");
        SendMessageW(g_mode, CB_ADDSTRING, 0, (LPARAM)L"仅原文");
        SendMessageW(g_mode, CB_ADDSTRING, 0, (LPARAM)L"仅译文");
        SendMessageW(g_mode, CB_SETCURSEL, 0, 0);
        y += 34;

        CreateWindowW(L"BUTTON", L"应用译文", WS_CHILD | WS_VISIBLE,
                      10, y, 100, 28, hwnd, (HMENU)ID_APPLY, NULL, NULL);
        CreateWindowW(L"BUTTON", L"预览双语拆分", WS_CHILD | WS_VISIBLE,
                      118, y, 120, 28, hwnd, (HMENU)ID_PREVIEW, NULL, NULL);
        CreateWindowW(L"BUTTON", L"导出 SRT", WS_CHILD | WS_VISIBLE,
                      246, y, 100, 28, hwnd, (HMENU)ID_EXPORT, NULL, NULL);
        y += 36;

        CreateWindowW(L"STATIC", L"条目列表", WS_CHILD | WS_VISIBLE, 10, y, 100, 20, hwnd, NULL, NULL, NULL);
        y += 22;
        g_list = CreateWindowW(L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_BORDER |
                               WS_VSCROLL | LBS_NOINTEGRALHEIGHT,
                               10, y, 740, 200, hwnd, (HMENU)ID_LIST, NULL, NULL);
        y += 210;

        CreateWindowW(L"STATIC", L"译文（[编号] 文本）", WS_CHILD | WS_VISIBLE,
                      10, y, 200, 20, hwnd, NULL, NULL, NULL);
        y += 22;
        g_trans = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_BORDER |
                                WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL,
                                10, y, 740, 100, hwnd, (HMENU)ID_TRANS, NULL, NULL);
        y += 110;

        CreateWindowW(L"STATIC", L"输出", WS_CHILD | WS_VISIBLE, 10, y, 60, 20, hwnd, NULL, NULL, NULL);
        y += 22;
        g_out = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_BORDER |
                              WS_VSCROLL | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL,
                              10, y, 740, 150, hwnd, (HMENU)ID_OUT, NULL, NULL);
        return 0;
    }
    case WM_SIZE: {
        int w = LOWORD(lp), h = HIWORD(lp);
        if (g_list) {
            MoveWindow(g_list, 10, 170, w - 30, 200, TRUE);
            MoveWindow(g_trans, 10, 400, w - 30, 100, TRUE);
            MoveWindow(g_out, 10, 530, w - 30, h - 550, TRUE);
        }
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case ID_OPEN: doOpen(); break;
        case ID_APPLY: doApply(); break;
        case ID_PREVIEW: doPreview(); break;
        case ID_EXPORT: doExport(); break;
        }
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE, LPSTR, int) {
    INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_STANDARD_CLASSES };
    InitCommonControlsEx(&icc);

    WNDCLASSW wc = { 0 };
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"SubMergeGui";
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowW(L"SubMergeGui", L"SubMerge Pro（C++ Win32 版）",
                              WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                              800, 760, NULL, NULL, hInst, NULL);
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
