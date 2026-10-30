// DirCleaner 内核版（C++17）
//
// 版本：A1_II_Φ8_Cpp_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <set>
#include <string>
#include <vector>

namespace fs = std::filesystem;

constexpr int MAX_RECURSION_DEPTH = 20;
constexpr int MAX_FILE_COUNT = 10000;
constexpr int MAX_SCAN_FOR_EXE = 2000;
const char* WHITELIST_MARKER_FILENAME = ".dircleaner_whitelist";

const std::set<std::string> CRITICAL_DIR_NAMES = {
    "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
    "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
    "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
};

struct Stats {
    int deletedFiles = 0;
    int deletedDirs = 0;
    unsigned long long totalBytes = 0;
    std::vector<std::string> errors;
};

std::string formatBytes(unsigned long long bytes) {
    if (bytes == 0) return "0 B";
    const char* units[] = {"B", "KB", "MB", "GB", "TB"};
    double v = static_cast<double>(bytes);
    int i = 0;
    while (v >= 1024.0 && i < 4) { v /= 1024.0; ++i; }
    char buf[64];
    if (i == 0) std::snprintf(buf, sizeof(buf), "%.0f %s", v, units[i]);
    else std::snprintf(buf, sizeof(buf), "%.2f %s", v, units[i]);
    return std::string(buf);
}

bool containsExecutables(const fs::path& dir, int depth, int& counter) {
    if (depth > 10 || counter >= MAX_SCAN_FOR_EXE) return false;
    std::error_code ec;
    fs::directory_iterator it(dir, ec);
    if (ec) return false;
    for (const auto& entry : it) {
        if (counter >= MAX_SCAN_FOR_EXE) break;
        std::error_code ec2;
        if (entry.is_directory(ec2)) {
            if (containsExecutables(entry.path(), depth + 1, counter)) return true;
        } else if (entry.is_regular_file(ec2)) {
            ++counter;
            std::string n = entry.path().filename().string();
            std::transform(n.begin(), n.end(), n.begin(), ::tolower);
            if (n.size() >= 4 &&
                (n.compare(n.size() - 4, 4, ".exe") == 0 || n.compare(n.size() - 4, 4, ".dll") == 0)) {
                return true;
            }
        }
    }
    return false;
}

void clearDirectory(const fs::path& dir, int depth, int& fileCount,
                    bool keepMarker, bool dryRun, Stats& stats) {
    if (depth > MAX_RECURSION_DEPTH) {
        throw std::runtime_error("已达到最大目录深度限制 (" + std::to_string(MAX_RECURSION_DEPTH) + ")");
    }
    std::error_code ec;
    fs::directory_iterator it(dir, ec);
    if (ec) throw std::runtime_error("无法读取 " + dir.string() + ": " + ec.message());

    for (const auto& entry : it) {
        const std::string name = entry.path().filename().string();
        std::error_code e;
        if (entry.is_directory(e)) {
            clearDirectory(entry.path(), depth + 1, fileCount, keepMarker, dryRun, stats);
            if (dryRun) {
                std::cout << "[dry-run] 将删除目录: " << name << "\n";
                ++stats.deletedDirs;
            } else {
                std::error_code re;
                fs::remove(entry.path(), re);
                if (re) {
                    std::string msg = "无法删除目录 " + name + ": " + re.message();
                    stats.errors.push_back(msg);
                    std::cerr << msg << "\n";
                } else {
                    std::cout << "已删除目录: " << name << "\n";
                    ++stats.deletedDirs;
                }
            }
            continue;
        }
        if (fileCount >= MAX_FILE_COUNT) {
            throw std::runtime_error("已达到最大文件数限制 (" + std::to_string(MAX_FILE_COUNT) + ")");
        }
        if (keepMarker && name == WHITELIST_MARKER_FILENAME) {
            std::cout << "跳过白名单标记文件: " << name << "\n";
            continue;
        }
        unsigned long long size = 0;
        std::error_code se;
        auto sz = fs::file_size(entry.path(), se);
        if (!se) size = sz;

        if (dryRun) {
            std::cout << "[dry-run] 将删除文件: " << name << " (" << formatBytes(size) << ")\n";
        } else {
            std::error_code re;
            fs::remove(entry.path(), re);
            if (re) {
                std::string msg = "无法删除 " + name + ": " + re.message();
                stats.errors.push_back(msg);
                std::cerr << msg << "\n";
                continue;
            }
            std::cout << "已删除文件: " << name << " (" << formatBytes(size) << ")\n";
        }
        ++stats.deletedFiles;
        stats.totalBytes += size;
        ++fileCount;
    }
}

void usage() {
    std::cout << "DirCleaner 内核版（C++）\n";
    std::cout << "用法: dircleaner <目录> [选项]\n\n";
    std::cout << "选项:\n";
    std::cout << "  --dry-run          只列出将删除的内容，不实际删除\n";
    std::cout << "  --whitelist        该目录在白名单中（保留标记文件，跳过名称确认）\n";
    std::cout << "  --confirm <名称>   确认待清空目录的名称（非白名单目录必须提供且一致）\n";
    std::cout << "  -h, --help         显示本帮助\n";
}

int main(int argc, char** argv) {
    std::string target;
    bool dryRun = false, inWhitelist = false;
    std::string confirm;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--dry-run") dryRun = true;
        else if (a == "--whitelist") inWhitelist = true;
        else if (a == "--confirm") { if (i + 1 < argc) confirm = argv[++i]; }
        else if (a == "-h" || a == "--help") { usage(); return 0; }
        else if (!a.empty() && a[0] != '-' && target.empty()) target = a;
    }

    if (target.empty()) { usage(); return 1; }

    std::error_code ec;
    if (!fs::is_directory(target, ec)) {
        std::cerr << "错误：" << target << " 不是目录\n";
        return 1;
    }

    const std::string dirName = fs::path(target).filename().string();
    if (CRITICAL_DIR_NAMES.count(dirName)) {
        std::cerr << "错误：" << dirName << " 是受保护的关键目录，禁止清空\n";
        return 1;
    }
    if (!inWhitelist) {
        if (confirm.empty()) {
            std::cerr << "错误：非白名单目录必须用 --confirm \"" << dirName << "\" 确认\n";
            return 1;
        }
        if (confirm != dirName) {
            std::cerr << "错误：确认名称 \"" << confirm << "\" 与目录名 \"" << dirName << "\" 不一致\n";
            return 1;
        }
    }

    int counter = 0;
    if (containsExecutables(target, 0, counter)) {
        std::cout << "⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。\n";
        std::cout << "确认继续？输入 yes: " << std::flush;
        std::string ans;
        std::getline(std::cin, ans);
        if (ans != "yes") { std::cout << "已取消。\n"; return 1; }
    }

    std::cout << "===== 开始清空操作 =====\n";
    std::cout << "目标目录: " << target << "\n";
    if (dryRun) std::cout << "模式: 试运行（不实际删除）\n";

    Stats stats;
    int fileCount = 0;
    try {
        clearDirectory(target, 0, fileCount, inWhitelist, dryRun, stats);
    } catch (const std::exception& e) {
        std::cerr << "操作中止: " << e.what() << "\n";
        std::cout << "已删除文件: " << stats.deletedFiles << "，目录: " << stats.deletedDirs
                  << "，释放空间: " << formatBytes(stats.totalBytes) << "\n";
        return 1;
    }

    std::cout << "===== 清空完成 =====\n";
    std::cout << "本次删除文件: " << stats.deletedFiles << "\n";
    std::cout << "本次删除目录: " << stats.deletedDirs << "\n";
    std::cout << "本次释放空间: " << formatBytes(stats.totalBytes) << "\n";
    if (!stats.errors.empty()) {
        std::cout << "错误数: " << stats.errors.size() << "\n";
        for (const auto& e : stats.errors) std::cout << "  " << e << "\n";
        return 1;
    }
    return 0;
}
