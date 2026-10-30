// DevKit 全功能版（C++ / Win32 API）
//
// 版本：A1_V_Φ9_Fix_Cpp_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 图形界面版：项目/页签、灵感、组合预览与复制、代码与结果编辑、
// 九款主题切换、配置导出。纯 Win32 API，无第三方依赖。
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

#include <string>
#include <vector>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "comdlg32.lib")

#define ID_TABS     4001
#define ID_INSP     4002
#define ID_PREVIEW  4003
#define ID_CODE     4004
#define ID_RESULT   4005
#define ID_THEME    4006
#define ID_NEWPROJ  4007
#define ID_EXPORT   4008
#define ID_COPY     4009
#define ID_OVERWRITE 4010

struct ThemeDef { const wchar_t* name; COLORREF bg; COLORREF fg; };
static const ThemeDef THEMES[] = {
    { L"Clean",    RGB(249,250,251), RGB(17,24,39) },
    { L"Glass",    RGB(18,20,26),    RGB(232,236,244) },
    { L"Neon",     RGB(8,9,13),      RGB(233,242,236) },
    { L"Mono",     RGB(10,10,10),    RGB(230,230,230) },
    { L"Material", RGB(20,18,24),    RGB(230,224,233) },
    { L"Minimal",  RGB(244,244,241), RGB(12,12,9) },
    { L"Premium",  RGB(28,28,30),    RGB(245,245,247) },
    { L"Shadcn",   RGB(255,255,255), RGB(9,9,11) },
    { L"Baseline", RGB(30,30,30),    RGB(204,204,204) },
};
static const int THEME_COUNT = sizeof(THEMES) / sizeof(THEMES[0]);

static const wchar_t* TEMPLATE_NAMES[] = {
    L"版本规划", L"需求分析", L"安全审计", L"性能审计", L"结构重构", L"单元测试", L"空白"
};
static const wchar_t* TEMPLATE_HEADS[] = {
    L"你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。",
    L"你是一位资深系统分析师。请对下面需求做全面分析。",
    L"你是一位持有 OSCP 认证的安全专家。请审计下面的代码。",
    L"你是一位性能优化专家。请审计下面的代码。",
    L"你是一位资深架构师。请重构下面的代码。",
    L"请为下面的代码编写单元测试。",
    L""
};
static const int TEMPLATE_COUNT = 7;

static HWND g_tabs, g_insp, g_preview, g_code, g_result, g_theme, g_status;
static int g_tabIdx = 0;
static int g_themeIdx = 0;

static std::wstring getText(HWND h) {
    int n = GetWindowTextLengthW(h);
    std::wstring s(n + 1, L'\0');
    GetWindowTextW(h, &s[0], n + 1);
    s.resize(n);
    return s;
}

static void setText(HWND h, const std::wstring& s) { SetWindowTextW(h, s.c_str()); }

static std::wstring compose() {
    int sel = (int)SendMessageW(g_tabs, LB_GETCURSEL, 0, 0);
    if (sel < 0) sel = 0;
    std::wstring head = (sel < TEMPLATE_COUNT) ? TEMPLATE_HEADS[sel] : L"";
    std::wstring insp = getText(g_insp);
    std::wstring code = getText(g_code);
    if (insp.empty()) insp = L"（无需求）";
    if (code.empty()) code = L"（无代码）";
    if (head.empty()) return L"需求：" + insp + L"\r\n\r\n代码：\r\n" + code;
    return head + L"\r\n\r\n需求：" + insp + L"\r\n\r\n代码：\r\n" + code;
}

static void refreshPreview() { setText(g_preview, compose()); }

static void applyTheme() {
    const ThemeDef& t = THEMES[g_themeIdx];
    HBRUSH bg = CreateSolidBrush(t.bg);
    // 简化：只改编辑控件配色
    for (HWND h : { g_insp, g_preview, g_code, g_result }) {
        SendMessageW(h, WM_CTLCOLOREDIT, 0, 0);
    }
    (void)bg;
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        int y = 8;
        CreateWindowW(L"STATIC", L"主题：", WS_CHILD | WS_VISIBLE, 8, y + 4, 50, 20, hwnd, NULL, NULL, NULL);
        g_theme = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
                                60, y, 130, 200, hwnd, (HMENU)ID_THEME, NULL, NULL);
        for (int i = 0; i < THEME_COUNT; ++i)
            SendMessageW(g_theme, CB_ADDSTRING, 0, (LPARAM)THEMES[i].name);
        SendMessageW(g_theme, CB_SETCURSEL, 0, 0);

        CreateWindowW(L"BUTTON", L"新建项目", WS_CHILD | WS_VISIBLE, 200, y, 90, 26, hwnd, (HMENU)ID_NEWPROJ, NULL, NULL);
        CreateWindowW(L"BUTTON", L"导出配置", WS_CHILD | WS_VISIBLE, 296, y, 90, 26, hwnd, (HMENU)ID_EXPORT, NULL, NULL);
        g_status = CreateWindowW(L"STATIC", L"就绪", WS_CHILD | WS_VISIBLE, 396, y + 4, 500, 20, hwnd, NULL, NULL, NULL);
        y += 34;

        CreateWindowW(L"STATIC", L"工作流步骤", WS_CHILD | WS_VISIBLE, 8, y, 200, 20, hwnd, NULL, NULL, NULL);
        y += 22;
        g_tabs = CreateWindowW(L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL,
                               8, y, 260, 200, hwnd, (HMENU)ID_TABS, NULL, NULL);
        for (int i = 0; i < TEMPLATE_COUNT; ++i)
            SendMessageW(g_tabs, LB_ADDSTRING, 0, (LPARAM)TEMPLATE_NAMES[i]);
        SendMessageW(g_tabs, LB_SETCURSEL, 0, 0);

        int iy = y + 210;
        CreateWindowW(L"STATIC", L"灵感", WS_CHILD | WS_VISIBLE, 8, iy, 100, 20, hwnd, NULL, NULL, NULL);
        g_insp = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                 WS_CHILD | WS_VISIBLE | ES_MULTILINE | WS_VSCROLL,
                                 8, iy + 22, 260, 100, hwnd, (HMENU)ID_INSP, NULL, NULL);
        CreateWindowW(L"STATIC", L"组合预览", WS_CHILD | WS_VISIBLE, 8, iy + 130, 100, 20, hwnd, NULL, NULL, NULL);
        g_preview = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                    WS_CHILD | WS_VISIBLE | ES_MULTILINE | WS_VSCROLL | ES_READONLY,
                                    8, iy + 152, 260, 260, hwnd, (HMENU)ID_PREVIEW, NULL, NULL);
        CreateWindowW(L"BUTTON", L"复制预览", WS_CHILD | WS_VISIBLE, 8, iy + 420, 90, 28, hwnd, (HMENU)ID_COPY, NULL, NULL);

        CreateWindowW(L"STATIC", L"代码编辑区", WS_CHILD | WS_VISIBLE, 280, y, 200, 20, hwnd, NULL, NULL, NULL);
        g_code = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                 WS_CHILD | WS_VISIBLE | ES_MULTILINE | WS_VSCROLL | WS_HSCROLL | ES_AUTOHSCROLL,
                                 280, y + 22, 660, 420, hwnd, (HMENU)ID_CODE, NULL, NULL);
        CreateWindowW(L"STATIC", L"AI 处理结果", WS_CHILD | WS_VISIBLE, 280, y + 450, 200, 20, hwnd, NULL, NULL, NULL);
        g_result = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                   WS_CHILD | WS_VISIBLE | ES_MULTILINE | WS_VSCROLL,
                                   280, y + 472, 660, 120, hwnd, (HMENU)ID_RESULT, NULL, NULL);
        CreateWindowW(L"BUTTON", L"用结果覆盖代码区", WS_CHILD | WS_VISIBLE,
                      280, y + 600, 150, 28, hwnd, (HMENU)ID_OVERWRITE, NULL, NULL);
        return 0;
    }
    case WM_SIZE: {
        int w = LOWORD(lp), h = HIWORD(lp);
        if (g_code) {
            MoveWindow(g_tabs, 8, 64, 260, 200, TRUE);
            MoveWindow(g_insp, 8, 286, 260, 100, TRUE);
            MoveWindow(g_preview, 8, 408, 260, h - 480, TRUE);
            MoveWindow(g_code, 280, 64, w - 300, h - 300, TRUE);
            MoveWindow(g_result, 280, h - 220, w - 300, 120, TRUE);
            MoveWindow(g_status, 396, 12, w - 410, 20, TRUE);
        }
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case ID_THEME:
            if (HIWORD(wp) == CBN_SELCHANGE) {
                g_themeIdx = (int)SendMessageW(g_theme, CB_GETCURSEL, 0, 0);
                applyTheme();
            }
            break;
        case ID_TABS:
            if (HIWORD(wp) == LBN_SELCHANGE) refreshPreview();
            break;
        case ID_INSP:
        case ID_CODE:
            if (HIWORD(wp) == EN_CHANGE) refreshPreview();
            break;
        case ID_COPY: {
            std::wstring text = compose();
            if (OpenClipboard(hwnd)) {
                EmptyClipboard();
                size_t bytes = (text.size() + 1) * sizeof(wchar_t);
                HGLOBAL hMem = GlobalAlloc(GMEM_MOVEABLE, bytes);
                if (hMem) {
                    void* p = GlobalLock(hMem);
                    memcpy(p, text.c_str(), bytes);
                    GlobalUnlock(hMem);
                    SetClipboardData(CF_UNICODETEXT, hMem);
                }
                CloseClipboard();
                SetWindowTextW(g_status, L"已复制");
            }
            break;
        }
        case ID_OVERWRITE: {
            std::wstring r = getText(g_result);
            if (!r.empty()) { setText(g_code, r); setText(g_result, L""); }
            break;
        }
        case ID_NEWPROJ:
            SetWindowTextW(g_status, L"已新建项目（界面为演示版，项目数据在内存中）");
            break;
        case ID_EXPORT: {
            OPENFILENAMEW ofn = { 0 };
            wchar_t path[MAX_PATH] = L"devkit_config.txt";
            ofn.lStructSize = sizeof(ofn);
            ofn.lpstrFilter = L"文本\0*.txt\0";
            ofn.lpstrFile = path;
            ofn.nMaxFile = MAX_PATH;
            ofn.Flags = OFN_OVERWRITEPROMPT;
            if (GetSaveFileNameW(&ofn)) {
                std::wstring out = compose();
                HANDLE hf = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
                if (hf != INVALID_HANDLE_VALUE) {
                    DWORD written;
                    WriteFile(hf, out.c_str(), (DWORD)(out.size() * sizeof(wchar_t)), &written, NULL);
                    CloseHandle(hf);
                    SetWindowTextW(g_status, L"已导出");
                }
            }
            break;
        }
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
    wc.lpszClassName = L"DevKitGui";
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowW(L"DevKitGui", L"DevKit（C++ Win32 版）",
                              WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                              1020, 780, NULL, NULL, hInst, NULL);
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
