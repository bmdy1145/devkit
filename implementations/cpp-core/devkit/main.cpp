// DevKit 内核版（C++17）
//
// 版本：A1_V_Φ9_Fix_Cpp_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
// 提示词模板拼接。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

static const char* CURRENT_VERSION = "A1_V_Φ9_Fix_Cpp_CN";

struct ParsedVersion {
    std::string branch;
    std::string structure;
    std::string suffix;   // 空表示无后缀
    bool ok = false;
};

static std::vector<std::string> splitU(const std::string& s, char sep) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == sep) { out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    out.push_back(cur);
    return out;
}

static bool endsWith(const std::string& s, const std::string& suf) {
    return s.size() >= suf.size() && s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

static std::string trimS(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

// 与浏览器版一致：分支代号 + 结构段 + 语言后缀
static ParsedVersion parseVersion(const std::string& v) {
    ParsedVersion pv;
    std::string t = trimS(v);
    if (t.empty() || t.size() > 100) return pv;

    std::string core = t;
    if (endsWith(t, "_CN")) { core = t.substr(0, t.size() - 3); pv.suffix = "CN"; }
    else if (endsWith(t, "_GLOBAL")) { core = t.substr(0, t.size() - 7); pv.suffix = "GLOBAL"; }

    auto parts = splitU(core, '_');
    if (parts.empty()) return pv;
    const std::string& branch = parts[0];
    if (branch.empty() || branch[0] != 'A') return pv;
    if (branch.size() > 1) {
        for (size_t i = 1; i < branch.size(); ++i)
            if (!isdigit((unsigned char)branch[i])) return pv;
    }
    pv.branch = branch;
    std::string structure;
    for (size_t i = 1; i < parts.size(); ++i) {
        if (!structure.empty()) structure += '_';
        structure += parts[i];
    }
    pv.structure = structure;
    pv.ok = true;
    return pv;
}

static bool isCompatible(const std::string& v) {
    auto pv = parseVersion(v);
    if (!pv.ok) return false;
    if (pv.branch.size() >= 2 && pv.branch[0] == 'A' && pv.branch[1] == '2') return false;
    for (const auto& s : splitU(pv.structure, '_')) {
        if (s == "A2") return false;
    }
    return true;
}

// 极简 JSON 提取：只用于本工具的固定字段，够用即可
static std::string jsonStr(const std::string& json, const std::string& key) {
    std::string pat = "\"" + key + "\"";
    size_t pos = json.find(pat);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + pat.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos);
    if (pos == std::string::npos) return "";
    size_t end = json.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return json.substr(pos + 1, end - pos - 1);
}

static void printNormalize(const std::string& json) {
    struct S { const char* key; bool isBool; bool defBool; const char* defStr; };
    const S specs[] = {
        { "performanceMode", true, false, nullptr },
        { "shortcutsEnabled", true, true, nullptr },
        { "hideBtnText", true, false, nullptr },
        { "promptActionsAlways", true, true, nullptr },
        { "specPromptEnabled", true, true, nullptr },
        { "inspirationSyncEnabled", true, true, nullptr },
    };
    printf("{\n");
    for (size_t i = 0; i < sizeof(specs) / sizeof(specs[0]); ++i) {
        const auto& s = specs[i];
        std::string pat = std::string("\"") + s.key + "\":";
        size_t pos = json.find(pat);
        bool val = s.defBool;
        if (pos != std::string::npos) {
            size_t vp = json.find_first_not_of(" \t", pos + pat.size());
            if (vp != std::string::npos && json.compare(vp, 4, "true") == 0) val = true;
            else if (vp != std::string::npos && json.compare(vp, 5, "false") == 0) val = false;
        }
        printf("  \"%s\": %s,\n", s.key, val ? "true" : "false");
    }
    // themePref 枚举
    std::string pref = jsonStr(json, "themePref");
    if (pref != "dark" && pref != "light" && pref != "auto") pref = "light";
    printf("  \"themePref\": \"%s\"\n}\n", pref.c_str());
}

static void usage() {
    printf("DevKit 内核版（C++）\n用法: devkit <子命令> [参数]\n\n");
    printf("子命令:\n  version\n  parse-version <版本号>\n  check-version <版本号>\n"
           "  validate-config <配置文件>\n  normalize <设置JSON>\n"
           "  compose <模板文件> <灵感> [代码文件]\n");
}

int main(int argc, char** argv) {
    if (argc < 2) { usage(); return 1; }
    std::string cmd = argv[1];

    if (cmd == "version") {
        printf("%s\n", CURRENT_VERSION);
        return 0;
    }
    if (cmd == "parse-version") {
        if (argc < 3) { fprintf(stderr, "缺少版本号\n"); return 1; }
        auto pv = parseVersion(argv[2]);
        if (!pv.ok) { fprintf(stderr, "版本号不合规\n"); return 1; }
        printf("分支: %s\n", pv.branch.c_str());
        printf("结构段: %s\n", pv.structure.empty() ? "（无）" : pv.structure.c_str());
        printf("语言后缀: %s\n", pv.suffix.empty() ? "（无）" : pv.suffix.c_str());
        return 0;
    }
    if (cmd == "check-version") {
        if (argc < 3) { fprintf(stderr, "缺少版本号\n"); return 1; }
        if (isCompatible(argv[2])) { printf("兼容\n"); return 0; }
        printf("不兼容\n");
        return 1;
    }
    if (cmd == "validate-config") {
        if (argc < 3) { fprintf(stderr, "缺少配置文件路径\n"); return 1; }
        std::ifstream f(argv[2], std::ios::binary);
        if (!f) { fprintf(stderr, "读取失败\n"); return 1; }
        std::ostringstream ss; ss << f.rdbuf();
        std::string json = ss.str();
        std::string ver = jsonStr(json, "version");
        if (!ver.empty() && !isCompatible(ver)) {
            fprintf(stderr, "配置文件版本不兼容: %s\n", ver.c_str());
            return 1;
        }
        printf("校验通过\n");
        return 0;
    }
    if (cmd == "normalize") {
        if (argc < 3) { fprintf(stderr, "缺少设置 JSON\n"); return 1; }
        printNormalize(argv[2]);
        return 0;
    }
    if (cmd == "compose") {
        if (argc < 4) { fprintf(stderr, "用法: compose <模板文件> <灵感> [代码文件]\n"); return 1; }
        std::ifstream f(argv[2], std::ios::binary);
        if (!f) { fprintf(stderr, "读取模板失败\n"); return 1; }
        std::ostringstream ss; ss << f.rdbuf();
        std::string tpl = ss.str();
        std::string code = "（无代码）";
        if (argc >= 5) {
            std::ifstream cf(argv[4], std::ios::binary);
            if (cf) { std::ostringstream cs; cs << cf.rdbuf(); code = cs.str(); }
        }
        // 简单替换
        std::string out;
        for (size_t i = 0; i < tpl.size();) {
            if (tpl.compare(i, 13, "{inspiration}") == 0) { out += argv[3]; i += 13; }
            else if (tpl.compare(i, 6, "{code}") == 0) { out += code; i += 6; }
            else { out += tpl[i]; ++i; }
        }
        printf("%s", out.c_str());
        return 0;
    }

    fprintf(stderr, "未知子命令: %s\n", cmd.c_str());
    usage();
    return 1;
}
