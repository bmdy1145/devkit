// Writer 全功能版（C++ / Win32 API）
//
// 版本：A1_I_Φ3_Cpp_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//
// 图形界面版：左侧章节树、正文编辑、资料与提示词、字数统计。
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
#include <chrono>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "comdlg32.lib")

#define ID_TREE     3001
#define ID_TITLE    3002
#define ID_BODY     3003
#define ID_ENTS     3004
#define ID_PROMPT   3005
#define ID_OPEN     3006
#define ID_SAVE     3007
#define ID_ADDVOL   3008
#define ID_ADDCH    3009
#define ID_DELCH    3010
#define ID_ADDENT   3011
#define ID_GENPROMPT 3012

struct Chapter { std::wstring id, bookId, volumeId, title, text; int order = 0; long long wc = 0; };
struct Volume { std::wstring id, bookId, title; int order = 0; };
struct Entity { std::wstring id, bookId, name, kind, desc; };

static std::vector<Volume> g_vols;
static std::vector<Chapter> g_chs;
static std::vector<Entity> g_ents;
static std::wstring g_bookId, g_path, g_selId;
static HWND g_tree, g_title, g_body, g_entList, g_prompt, g_status;
static long long g_ctr = 0;

static long long nowTs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

static std::wstring genId(const wchar_t* p) {
    return std::wstring(p) + L"_" + std::to_wstring(nowTs()) + L"_" + std::to_wstring(++g_ctr);
}

static bool isCjk(unsigned int cp) {
    return (cp >= 0x3400 && cp <= 0x4DBF) || (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0xAC00 && cp <= 0xD7AF) ||
           (cp >= 0xF900 && cp <= 0xFAFF);
}

static long long countWords(const std::wstring& text) {
    long long total = 0;
    bool inLatin = false;
    for (wchar_t c : text) {
        if (isCjk((unsigned int)c)) { ++total; inLatin = false; }
        else if (iswalnum(c)) { if (!inLatin) { ++total; inLatin = true; } }
        else inLatin = false;
    }
    return total;
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

static std::wstring esc(const std::wstring& s) {
    std::wstring o;
    for (wchar_t c : s) {
        if (c == L'\\') o += L"\\\\";
        else if (c == L'\t') o += L"\\t";
        else if (c == L'\n') o += L"\\n";
        else if (c == L'\r') continue;
        else o += c;
    }
    return o;
}

static std::wstring unesc(const std::wstring& s) {
    std::wstring o;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == L'\\' && i + 1 < s.size()) {
            wchar_t n = s[++i];
            if (n == L't') o += L'\t';
            else if (n == L'n') o += L'\n';
            else o += n;
        } else o += s[i];
    }
    return o;
}

static std::vector<std::wstring> splitTab(const std::wstring& s) {
    std::vector<std::wstring> out;
    std::wstring cur;
    for (wchar_t c : s) {
        if (c == L'\t') { out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    out.push_back(cur);
    return out;
}

static void loadLib(const std::wstring& path) {
    g_vols.clear(); g_chs.clear(); g_ents.clear(); g_bookId.clear();
    std::ifstream f(W2U8(path), std::ios::binary);
    if (!f) return;
    std::stringstream ss; ss << f.rdbuf();
    std::wstring all = U82W(ss.str());
    std::wstringstream ls(all);
    std::wstring line;
    while (std::getline(ls, line)) {
        if (line.empty()) continue;
        auto p = splitTab(line);
        if (p.empty()) continue;
        if (p[0] == L"B" && p.size() >= 2) g_bookId = p[1];
        else if (p[0] == L"V" && p.size() >= 5)
            g_vols.push_back({ p[1], p[2], unesc(p[3]), _wtoi(p[4].c_str()) });
        else if (p[0] == L"C" && p.size() >= 8) {
            Chapter c;
            c.id = p[1]; c.bookId = p[2]; c.volumeId = p[3];
            c.title = unesc(p[4]); c.order = _wtoi(p[5].c_str());
            c.wc = _wtoi64(p[6].c_str()); c.text = unesc(p[7]);
            g_chs.push_back(c);
        } else if (p[0] == L"E" && p.size() >= 6)
            g_ents.push_back({ p[1], p[2], unesc(p[3]), unesc(p[4]), unesc(p[5]) });
    }
}

static void saveLib() {
    if (g_path.empty()) return;
    std::wstring out;
    if (!g_bookId.empty()) out += L"B\t" + g_bookId + L"\tbook\t0\n";
    for (auto& v : g_vols)
        out += L"V\t" + v.id + L"\t" + v.bookId + L"\t" + esc(v.title) + L"\t" + std::to_wstring(v.order) + L"\n";
    for (auto& c : g_chs)
        out += L"C\t" + c.id + L"\t" + c.bookId + L"\t" + c.volumeId + L"\t" + esc(c.title) + L"\t" +
               std::to_wstring(c.order) + L"\t" + std::to_wstring(c.wc) + L"\t" + esc(c.text) + L"\n";
    for (auto& e : g_ents)
        out += L"E\t" + e.id + L"\t" + e.bookId + L"\t" + esc(e.name) + L"\t" + esc(e.kind) + L"\t" + esc(e.desc) + L"\n";
    std::ofstream f(W2U8(g_path), std::ios::binary);
    auto u8 = W2U8(out);
    f.write(u8.data(), (std::streamsize)u8.size());
}

static void refreshTree() {
    TreeView_DeleteAllItems(g_tree);
    std::vector<size_t> order(g_vols.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = i;
    std::sort(order.begin(), order.end(), [](size_t a, size_t b) { return g_vols[a].order < g_vols[b].order; });
    for (size_t vi : order) {
        TVINSERTSTRUCTW tv = { 0 };
        tv.hParent = TVI_ROOT;
        tv.hInsertAfter = TVI_LAST;
        tv.item.mask = TVIF_TEXT;
        tv.item.pszText = (LPWSTR)g_vols[vi].title.c_str();
        HTREEITEM vnode = TreeView_InsertItem(g_tree, &tv);
        std::vector<size_t> co;
        for (size_t i = 0; i < g_chs.size(); ++i) if (g_chs[i].volumeId == g_vols[vi].id) co.push_back(i);
        std::sort(co.begin(), co.end(), [](size_t a, size_t b) { return g_chs[a].order < g_chs[b].order; });
        for (size_t ci : co) {
            std::wstring label = g_chs[ci].title + L"（" + std::to_wstring(g_chs[ci].wc) + L" 字）";
            TVINSERTSTRUCTW cv = { 0 };
            cv.hParent = vnode;
            cv.hInsertAfter = TVI_LAST;
            cv.item.mask = TVIF_TEXT;
            cv.item.pszText = (LPWSTR)label.c_str();
            TreeView_InsertItem(g_tree, &cv);
        }
    }
    TreeView_Expand(g_tree, TVI_ROOT, TVE_EXPAND);
}

static void refreshEnts() {
    SendMessageW(g_entList, LB_RESETCONTENT, 0, 0);
    for (auto& e : g_ents) {
        std::wstring s = e.name + L"（" + e.kind + L"）";
        SendMessageW(g_entList, LB_ADDSTRING, 0, (LPARAM)s.c_str());
    }
}

static Chapter* findChapter(const std::wstring& id) {
    for (auto& c : g_chs) if (c.id == id) return &c;
    return nullptr;
}

static void syncCurrent() {
    if (g_selId.empty()) return;
    Chapter* c = findChapter(g_selId);
    if (!c) return;
    int tl = GetWindowTextLengthW(g_title);
    std::wstring t(tl, L'\0');
    GetWindowTextW(g_title, &t[0], tl + 1);
    c->title = t;

    int bl = GetWindowTextLengthW(g_body);
    std::wstring b(bl, L'\0');
    GetWindowTextW(g_body, &b[0], bl + 1);
    c->text = b;
    c->wc = countWords(b);
}

static void selectChapter(const std::wstring& id) {
    syncCurrent();
    Chapter* c = findChapter(id);
    if (!c) return;
    g_selId = id;
    SetWindowTextW(g_title, c->title.c_str());
    SetWindowTextW(g_body, c->text.c_str());
    std::wstring st = L"本章 " + std::to_wstring(countWords(c->text)) + L" 字 · " +
                      std::to_wstring(c->text.size()) + L" 字符";
    SetWindowTextW(g_status, st.c_str());
}

static void doOpen() {
    OPENFILENAMEW ofn = { 0 };
    wchar_t path[MAX_PATH] = { 0 };
    ofn.lStructSize = sizeof(ofn);
    ofn.lpstrFilter = L"数据文件\0*.txt;*.json\0所有文件\0*.*\0";
    ofn.lpstrFile = path;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&ofn)) return;
    g_path = path;
    loadLib(g_path);
    if (g_bookId.empty()) g_bookId = genId(L"book");
    refreshTree();
    refreshEnts();
    SetWindowTextW(g_status, g_path.c_str());
}

static void doAddVol() {
    wchar_t buf[256] = { 0 };
    GetWindowTextW(g_status, buf, 0);
    // 用输入框收集卷名：复用 g_title 作为输入
    int tl = GetWindowTextLengthW(g_title);
    if (tl == 0) { SetWindowTextW(g_status, L"请在标题框输入卷名后再点 +卷"); return; }
    std::wstring name(tl + 1, L'\0');
    GetWindowTextW(g_title, &name[0], tl + 1);
    name = trimW(name);
    if (name.empty()) return;
    g_vols.push_back({ genId(L"vol"), g_bookId, name, (int)g_vols.size() });
    SetWindowTextW(g_title, L"");
    refreshTree();
    saveLib();
}

static void doAddCh() {
    if (g_vols.empty()) { SetWindowTextW(g_status, L"请先新增一卷"); return; }
    int tl = GetWindowTextLengthW(g_title);
    if (tl == 0) { SetWindowTextW(g_status, L"请在标题框输入章节名后再点 +章"); return; }
    std::wstring name(tl + 1, L'\0');
    GetWindowTextW(g_title, &name[0], tl + 1);
    name = trimW(name);
    if (name.empty()) return;
    auto& vol = g_vols.back();
    int order = 0;
    for (auto& c : g_chs) if (c.volumeId == vol.id) order++;
    Chapter c;
    c.id = genId(L"ch"); c.bookId = vol.bookId; c.volumeId = vol.id;
    c.title = name; c.order = order;
    g_chs.push_back(c);
    SetWindowTextW(g_title, L"");
    refreshTree();
    saveLib();
}

static void doGenPrompt() {
    if (g_selId.empty()) { SetWindowTextW(g_status, L"请先选择章节"); return; }
    Chapter* ch = findChapter(g_selId);
    if (!ch) return;
    std::vector<Chapter*> list;
    for (auto& c : g_chs) if (c.volumeId == ch->volumeId) list.push_back(&c);
    std::sort(list.begin(), list.end(), [](Chapter* a, Chapter* b) { return a->order < b->order; });
    int pos = 0;
    for (size_t i = 0; i < list.size(); ++i) if (list[i]->id == g_selId) pos = (int)i;
    std::wstring prev = L"（本章为卷首，无上一章）";
    if (pos > 0) {
        auto& t = list[pos - 1]->text;
        prev = t.size() > 500 ? t.substr(t.size() - 500) : t;
    }
    std::wstring chars;
    for (auto& e : g_ents)
        if (e.bookId == ch->bookId)
            chars += L"- " + e.name + L"（" + e.kind + L"）：" + e.desc + L"\r\n";
    if (chars.empty()) chars = L"（未填写）";
    std::wstring body = ch->text.empty() ? L"（当前章为空）" : ch->text;
    std::wstring out = L"你是一位与作者合写的小说作者。请续写下一段情节。\r\n\r\n【设定】\r\n" + chars +
                       L"\r\n【上一章结尾】\r\n" + prev + L"\r\n\r\n【本章已有正文】\r\n" + body;
    SetWindowTextW(g_prompt, out.c_str());
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        int y = 8;
        CreateWindowW(L"BUTTON", L"打开库…", WS_CHILD | WS_VISIBLE, 8, y, 90, 28, hwnd, (HMENU)ID_OPEN, NULL, NULL);
        CreateWindowW(L"BUTTON", L"保存", WS_CHILD | WS_VISIBLE, 104, y, 70, 28, hwnd, (HMENU)ID_SAVE, NULL, NULL);
        g_status = CreateWindowW(L"STATIC", L"就绪", WS_CHILD | WS_VISIBLE, 184, y + 6, 700, 20, hwnd, NULL, NULL, NULL);
        y += 36;

        g_tree = CreateWindowExW(WS_EX_CLIENTEDGE, WC_TREEVIEWW, L"",
                                 WS_CHILD | WS_VISIBLE | TVS_HASLINES | TVS_HASBUTTONS | TVS_LINESATROOT,
                                 8, y, 260, 500, hwnd, (HMENU)ID_TREE, NULL, NULL);
        CreateWindowW(L"BUTTON", L"+卷", WS_CHILD | WS_VISIBLE, 8, y + 506, 60, 26, hwnd, (HMENU)ID_ADDVOL, NULL, NULL);
        CreateWindowW(L"BUTTON", L"+章", WS_CHILD | WS_VISIBLE, 72, y + 506, 60, 26, hwnd, (HMENU)ID_ADDCH, NULL, NULL);
        CreateWindowW(L"BUTTON", L"删章", WS_CHILD | WS_VISIBLE, 136, y + 506, 60, 26, hwnd, (HMENU)ID_DELCH, NULL, NULL);

        g_title = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                                276, y, 450, 26, hwnd, (HMENU)ID_TITLE, NULL, NULL);
        g_body = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                 WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL,
                                 276, y + 32, 450, 500, hwnd, (HMENU)ID_BODY, NULL, NULL);

        g_entList = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"",
                                 WS_CHILD | WS_VISIBLE | WS_VSCROLL,
                                 736, y, 240, 180, hwnd, (HMENU)ID_ENTS, NULL, NULL);
        CreateWindowW(L"BUTTON", L"+ 资料", WS_CHILD | WS_VISIBLE, 736, y + 186, 80, 26, hwnd, (HMENU)ID_ADDENT, NULL, NULL);
        CreateWindowW(L"BUTTON", L"生成提示词", WS_CHILD | WS_VISIBLE, 820, y + 186, 110, 26, hwnd, (HMENU)ID_GENPROMPT, NULL, NULL);
        g_prompt = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                   WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | WS_VSCROLL,
                                   736, y + 218, 240, 314, hwnd, (HMENU)ID_PROMPT, NULL, NULL);
        return 0;
    }
    case WM_SIZE: {
        int w = LOWORD(lp), h = HIWORD(lp);
        if (g_tree) {
            MoveWindow(g_tree, 8, 44, 260, h - 130, TRUE);
            MoveWindow(g_title, 276, 44, w - 540, 26, TRUE);
            MoveWindow(g_body, 276, 76, w - 540, h - 156, TRUE);
            MoveWindow(g_entList, w - 256, 44, 248, 180, TRUE);
            MoveWindow(g_prompt, w - 256, 258, 248, h - 338, TRUE);
            MoveWindow(g_status, 184, 14, w - 200, 20, TRUE);
        }
        return 0;
    }
    case WM_NOTIFY: {
        auto nm = (LPNMHDR)lp;
        if (nm->idFrom == ID_TREE && nm->code == TVN_SELCHANGEDW) {
            auto tv = (LPNMTREEVIEWW)lp;
            wchar_t buf[512] = { 0 };
            TVITEMW item = { 0 };
            item.mask = TVIF_TEXT;
            item.hItem = tv->itemNew.hItem;
            item.pszText = buf;
            item.cchTextMax = 512;
            SendMessageW(g_tree, TVM_GETITEMW, 0, (LPARAM)&item);
            std::wstring label = buf;
            // 从标签反查章节（标签形如「标题（N 字）」）
            for (auto& c : g_chs) {
                std::wstring expect = c.title + L"（" + std::to_wstring(c.wc) + L" 字）";
                if (expect == label) { selectChapter(c.id); break; }
            }
        }
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case ID_OPEN: doOpen(); break;
        case ID_SAVE: syncCurrent(); saveLib(); SetWindowTextW(g_status, L"已保存"); break;
        case ID_ADDVOL: doAddVol(); break;
        case ID_ADDCH: doAddCh(); break;
        case ID_DELCH:
            if (!g_selId.empty()) {
                syncCurrent();
                g_chs.erase(std::remove_if(g_chs.begin(), g_chs.end(),
                    [](const Chapter& c) { return c.id == g_selId; }), g_chs.end());
                g_selId.clear();
                SetWindowTextW(g_title, L"");
                SetWindowTextW(g_body, L"");
                refreshTree();
                saveLib();
            }
            break;
        case ID_ADDENT: {
            int tl = GetWindowTextLengthW(g_title);
            if (tl == 0) { SetWindowTextW(g_status, L"请在标题框输入资料名称"); break; }
            std::wstring name(tl + 1, L'\0');
            GetWindowTextW(g_title, &name[0], tl + 1);
            g_ents.push_back({ genId(L"ent"), g_bookId, trimW(name), L"其他", L"" });
            SetWindowTextW(g_title, L"");
            refreshEnts();
            saveLib();
            break;
        }
        case ID_GENPROMPT: doGenPrompt(); break;
        }
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE, LPSTR, int) {
    INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_TREEVIEW_CLASSES | ICC_STANDARD_CLASSES };
    InitCommonControlsEx(&icc);

    WNDCLASSW wc = { 0 };
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"WriterGui";
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowW(L"WriterGui", L"Writer（C++ Win32 版）",
                              WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                              1020, 700, NULL, NULL, hInst, NULL);
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
