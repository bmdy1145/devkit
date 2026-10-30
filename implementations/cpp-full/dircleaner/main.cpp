// DirCleaner 全功能版（C++ / Win32 API）
//
// 版本：A1_II_Φ8_Cpp_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 图形界面版：目录选择、关键目录防护、白名单、可执行文件扫描、
// 名称确认、进度与统计，与浏览器版一一对应。纯 Win32 API，无第三方依赖。
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
#include <shlobj.h>

#include <algorithm>
#include <filesystem>
#include <set>
#include <string>
#include <vector>
#include <fstream>
#include <stdexcept>

namespace fs = std::filesystem;

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")

constexpr int MAX_RECURSION_DEPTH = 20;
constexpr int MAX_FILE_COUNT = 10000;
constexpr int MAX_SCAN_FOR_EXE = 2000;
const wchar_t* WHITELIST_MARKER = L".dircleaner_whitelist";

#define ID_BROWSE   1001
#define ID_WHITELIST 1002
#define ID_SCAN     1003
#define ID_START    1004
#define ID_CONFIRM  1005
#define ID_NAME     1006
#define ID_EXECHECK 1007

const std::set<std::wstring> CRITICAL_NAMES = {
    L"Windows", L"System32", L"SysWOW64", L"Program Files", L"Program Files (x86)",
    L"Users", L"Documents and Settings", L"bin", L"sbin", L"etc", L"dev", L"proc", L"sys",
    L"boot", L"root", L"home", L"var", L"tmp", L"Volumes", L"Applications", L"Library",
};

static HWND g_pathLabel, g_criticalLabel, g_exeLabel, g_statusLabel;
static HWND g_confirmCheck, g_nameEdit, g_exeCheck;
static HWND g_startBtn, g_cancelBtn, g_logEdit;
static HWND g_statFiles, g_statDirs, g_statSize, g_statErrors;
static std::wstring g_target;
static bool g_exeFound = false;

struct Stats {
    int files = 0;
    int dirs = 0;
    unsigned long long bytes = 0;
    std::vector<std::wstring> errors;
};

static std::wstring FormatBytes(unsigned long long bytes) {
    if (bytes == 0) return L"0 B";
    const wchar_t* units[] = { L"B", L"KB", L"MB", L"GB", L"TB" };
    double v = static_cast<double>(bytes);
    int i = 0;
    while (v >= 1024.0 && i < 4) { v /= 1024.0; ++i; }
    wchar_t buf[64];
    if (i == 0) swprintf(buf, 64, L"%.0f %s", v, units[i]);
    else swprintf(buf, 64, L"%.2f %s", v, units[i]);
    return buf;
}

static void Log(const std::wstring& msg) {
    int len = GetWindowTextLengthW(g_logEdit);
    SendMessageW(g_logEdit, EM_SETSEL, len, len);
    std::wstring line = msg + L"\r\n";
    SendMessageW(g_logEdit, EM_REPLACESEL, FALSE, (LPARAM)line.c_str());
}

static bool IsWhitelisted() {
    if (g_target.empty()) return false;
    std::error_code ec;
    return fs::is_regular_file(fs::path(g_target) / WHITELIST_MARKER, ec);
}

static std::wstring BaseName(const std::wstring& path) {
    fs::path p(path);
    return p.filename().wstring();
}

static bool ContainsExecutables(const fs::path& dir, int depth, int& counter) {
    if (depth > 10 || counter >= MAX_SCAN_FOR_EXE) return false;
    std::error_code ec;
    fs::directory_iterator it(dir, ec);
    if (ec) return false;
    for (const auto& e : it) {
        if (counter >= MAX_SCAN_FOR_EXE) break;
        std::error_code e2;
        if (e.is_directory(e2)) {
            if (ContainsExecutables(e.path(), depth + 1, counter)) return true;
        } else if (e.is_regular_file(e2)) {
            ++counter;
            std::wstring n = e.path().filename().wstring();
            std::transform(n.begin(), n.end(), n.begin(), ::towlower);
            if (n.size() >= 4 && (n.compare(n.size() - 4, 4, L".exe") == 0 ||
                                  n.compare(n.size() - 4, 4, L".dll") == 0)) return true;
        }
    }
    return false;
}

static void ClearDirectory(const fs::path& dir, int depth, int& fileCount,
                           bool keepMarker, Stats& st) {
    if (depth > MAX_RECURSION_DEPTH)
        throw std::runtime_error("已达到最大目录深度限制");
    std::error_code ec;
    fs::directory_iterator it(dir, ec);
    if (ec) throw std::runtime_error("无法读取目录");

    for (const auto& e : it) {
        auto name = e.path().filename().wstring();
        std::error_code e2;
        if (e.is_directory(e2)) {
            ClearDirectory(e.path(), depth + 1, fileCount, keepMarker, st);
            std::error_code re;
            fs::remove(e.path(), re);
            if (re) { st.errors.push_back(L"无法删除目录 " + name); Log(L"  ✗ 无法删除目录 " + name); }
            else { st.dirs++; Log(L"已删除目录: " + name); }
            continue;
        }
        if (fileCount >= MAX_FILE_COUNT) throw std::runtime_error("已达到最大文件数限制");
        if (keepMarker && name == WHITELIST_MARKER) { Log(L"跳过白名单标记: " + name); continue; }
        std::error_code se;
        auto sz = fs::file_size(e.path(), se);
        unsigned long long size = se ? 0 : sz;
        std::error_code re;
        fs::remove(e.path(), re);
        if (re) { st.errors.push_back(L"无法删除 " + name); Log(L"  ✗ 无法删除 " + name); continue; }
        st.files++;
        st.bytes += size;
        fileCount++;
        Log(L"已删除文件: " + name + L" (" + FormatBytes(size) + L")");
    }
}

static bool IsCritical(const std::wstring& name) {
    return CRITICAL_NAMES.count(name) > 0;
}

static void UpdateStartState() {
    if (g_target.empty()) { EnableWindow(g_startBtn, FALSE); return; }
    std::wstring name = BaseName(g_target);
    if (IsCritical(name)) { EnableWindow(g_startBtn, FALSE); return; }
    bool ok = SendMessageW(g_confirmCheck, BM_GETCHECK, 0, 0) == BST_CHECKED;
    if (!IsWhitelisted()) {
        wchar_t buf[512] = { 0 };
        GetWindowTextW(g_nameEdit, buf, 512);
        ok = ok && (std::wstring(buf) == name);
    }
    if (g_exeFound && SendMessageW(g_exeCheck, BM_GETCHECK, 0, 0) != BST_CHECKED) ok = false;
    EnableWindow(g_startBtn, ok ? TRUE : FALSE);
}

static void Browse() {
    BROWSEINFOW bi = { 0 };
    bi.lpszTitle = L"选择要清空的目录";
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    LPITEMIDLIST pidl = SHBrowseForFolderW(&bi);
    if (!pidl) return;
    wchar_t path[MAX_PATH] = { 0 };
    if (SHGetPathFromIDListW(pidl, path)) {
        g_target = path;
        SetWindowTextW(g_pathLabel, path);
        std::wstring name = BaseName(g_target);
        g_exeFound = false;
        SetWindowTextW(g_exeLabel, L"");
        ShowWindow(g_exeCheck, SW_HIDE);
        SendMessageW(g_confirmCheck, BM_SETCHECK, BST_UNCHECKED, 0);
        SetWindowTextW(g_nameEdit, L"");
        SetWindowTextW(g_statFiles, L"-");
        SetWindowTextW(g_statDirs, L"-");
        SetWindowTextW(g_statSize, L"-");
        SetWindowTextW(g_statErrors, L"-");
        if (IsCritical(name)) {
            SetWindowTextW(g_criticalLabel, (L"✗ " + name + L" 是受保护的关键目录，禁止清空").c_str());
        } else {
            SetWindowTextW(g_criticalLabel, (L"✓ 可以清空（目录名：" + name + L"）").c_str());
            Log(L"已选择: " + g_target);
        }
        UpdateStartState();
    }
    CoTaskMemFree(pidl);
}

static void AddWhitelist() {
    if (g_target.empty()) { MessageBoxW(NULL, L"请先选择目录", L"提示", MB_OK); return; }
    std::wstring name = BaseName(g_target);
    if (IsCritical(name)) { MessageBoxW(NULL, L"关键目录不能加入白名单", L"拒绝", MB_OK | MB_ICONERROR); return; }
    std::ofstream out(fs::path(g_target) / WHITELIST_MARKER);
    if (!out) { MessageBoxW(NULL, L"创建标记失败", L"失败", MB_OK | MB_ICONERROR); return; }
    out << "DirCleaner Whitelist Marker";
    out.close();
    Log(L"已创建白名单标记");
    MessageBoxW(NULL, L"已加入白名单", L"成功", MB_OK);
    UpdateStartState();
}

static void ScanExe() {
    if (g_target.empty()) return;
    SetWindowTextW(g_statusLabel, L"正在扫描…");
    int counter = 0;
    g_exeFound = ContainsExecutables(fs::path(g_target), 0, counter);
    if (g_exeFound) {
        SetWindowTextW(g_exeLabel, L"⚠️ 发现可执行文件（.exe / .dll），需额外确认");
        ShowWindow(g_exeCheck, SW_SHOW);
    } else {
        SetWindowTextW(g_exeLabel, L"✓ 未发现可执行文件");
        ShowWindow(g_exeCheck, SW_HIDE);
    }
    SetWindowTextW(g_statusLabel, L"扫描完成");
    UpdateStartState();
}

static void StartClear() {
    std::wstring name = BaseName(g_target);
    std::wstring msg = L"确定要清空目录 \"" + name + L"\" 下的所有内容吗？\r\n此操作不可恢复。";
    if (MessageBoxW(NULL, msg.c_str(), L"最后确认", MB_YESNO | MB_ICONWARNING) != IDYES) return;

    EnableWindow(g_startBtn, FALSE);
    SetWindowTextW(g_statusLabel, L"正在清空…");
    Log(L"===== 开始清空 =====");

    Stats st;
    int fileCount = 0;
    try {
        ClearDirectory(fs::path(g_target), 0, fileCount, IsWhitelisted(), st);
        Log(L"===== 清空完成 =====");
    } catch (const std::exception&) {
        Log(L"操作中止");
    }

    SetWindowTextW(g_statFiles, std::to_wstring(st.files).c_str());
    SetWindowTextW(g_statDirs, std::to_wstring(st.dirs).c_str());
    SetWindowTextW(g_statSize, FormatBytes(st.bytes).c_str());
    SetWindowTextW(g_statErrors, std::to_wstring(st.errors.size()).c_str());
    SetWindowTextW(g_statusLabel, st.errors.empty() ? L"完成" : L"完成（有错误）");
    for (const auto& e : st.errors) Log(L"  " + e);
    UpdateStartState();
}

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        int y = 10;
        auto section = [&](const wchar_t* text) {
            CreateWindowW(L"STATIC", text, WS_CHILD | WS_VISIBLE,
                          10, y, 700, 20, hwnd, NULL, NULL, NULL);
            y += 24;
        };
        section(L"1. 选择目录");
        g_pathLabel = CreateWindowW(L"STATIC", L"（未选择）", WS_CHILD | WS_VISIBLE,
                                    10, y, 740, 20, hwnd, NULL, NULL, NULL);
        y += 26;
        CreateWindowW(L"BUTTON", L"浏览目录…", WS_CHILD | WS_VISIBLE,
                      10, y, 110, 28, hwnd, (HMENU)ID_BROWSE, NULL, NULL);
        CreateWindowW(L"BUTTON", L"加入白名单", WS_CHILD | WS_VISIBLE,
                      130, y, 110, 28, hwnd, (HMENU)ID_WHITELIST, NULL, NULL);
        y += 38;

        section(L"2. 安全检查");
        g_criticalLabel = CreateWindowW(L"STATIC", L"请先选择目录", WS_CHILD | WS_VISIBLE,
                                        10, y, 740, 20, hwnd, NULL, NULL, NULL);
        y += 24;
        g_exeLabel = CreateWindowW(L"STATIC", L"", WS_CHILD | WS_VISIBLE,
                                   10, y, 740, 20, hwnd, NULL, NULL, NULL);
        y += 24;
        CreateWindowW(L"BUTTON", L"扫描可执行文件", WS_CHILD | WS_VISIBLE,
                      10, y, 130, 28, hwnd, (HMENU)ID_SCAN, NULL, NULL);
        y += 38;

        section(L"3. 确认");
        g_confirmCheck = CreateWindowW(L"BUTTON", L"我了解此操作不可恢复",
                                       WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX,
                                       10, y, 300, 24, hwnd, (HMENU)ID_CONFIRM, NULL, NULL);
        y += 28;
        CreateWindowW(L"STATIC", L"输入目录名确认：", WS_CHILD | WS_VISIBLE,
                      10, y, 130, 24, hwnd, NULL, NULL, NULL);
        g_nameEdit = CreateWindowW(L"EDIT", L"", WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                                   145, y, 260, 24, hwnd, (HMENU)ID_NAME, NULL, NULL);
        y += 30;
        g_exeCheck = CreateWindowW(L"BUTTON", L"该目录含可执行文件，我了解风险仍要删除",
                                   WS_CHILD | BS_AUTOCHECKBOX,
                                   10, y, 380, 24, hwnd, (HMENU)ID_EXECHECK, NULL, NULL);
        y += 30;
        g_startBtn = CreateWindowW(L"BUTTON", L"开始清空", WS_CHILD | WS_VISIBLE,
                                   10, y, 110, 30, hwnd, (HMENU)ID_START, NULL, NULL);
        g_cancelBtn = CreateWindowW(L"BUTTON", L"取消", WS_CHILD | WS_VISIBLE,
                                    130, y, 90, 30, hwnd, NULL, NULL, NULL);
        EnableWindow(g_startBtn, FALSE);
        EnableWindow(g_cancelBtn, FALSE);
        y += 40;

        section(L"4. 统计");
        g_statFiles = CreateWindowW(L"STATIC", L"-", WS_CHILD | WS_VISIBLE,
                                    10, y, 120, 24, hwnd, NULL, NULL, NULL);
        g_statDirs = CreateWindowW(L"STATIC", L"-", WS_CHILD | WS_VISIBLE,
                                   140, y, 120, 24, hwnd, NULL, NULL, NULL);
        g_statSize = CreateWindowW(L"STATIC", L"-", WS_CHILD | WS_VISIBLE,
                                   270, y, 160, 24, hwnd, NULL, NULL, NULL);
        g_statErrors = CreateWindowW(L"STATIC", L"-", WS_CHILD | WS_VISIBLE,
                                     440, y, 120, 24, hwnd, NULL, NULL, NULL);
        y += 30;
        g_statusLabel = CreateWindowW(L"STATIC", L"就绪", WS_CHILD | WS_VISIBLE,
                                      10, y, 740, 20, hwnd, NULL, NULL, NULL);
        y += 28;

        section(L"5. 日志");
        g_logEdit = CreateWindowW(L"EDIT", L"",
                                  WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL |
                                  ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL,
                                  10, y, 740, 200, hwnd, NULL, NULL, NULL);
        return 0;
    }
    case WM_COMMAND: {
        int id = LOWORD(wp);
        int code = HIWORD(wp);
        if (id == ID_BROWSE) Browse();
        else if (id == ID_WHITELIST) AddWhitelist();
        else if (id == ID_SCAN) ScanExe();
        else if (id == ID_START) StartClear();
        else if (id == ID_CONFIRM || id == ID_EXECHECK) UpdateStartState();
        else if (id == ID_NAME && code == EN_CHANGE) UpdateStartState();
        return 0;
    }
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
    wc.lpszClassName = L"DirCleanerGui";
    RegisterClassW(&wc);

    HWND hwnd = CreateWindowW(L"DirCleanerGui", L"DirCleaner（C++ Win32 版）",
                              WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                              800, 700, NULL, NULL, hInst, NULL);
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
