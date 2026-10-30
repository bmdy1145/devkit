// SubMerge Pro 内核版（C++17）
//
// 版本：A1_II_Φ10_Cpp_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <vector>

struct Entry {
    int index;
    std::string start;
    std::string end;
    std::string text;
    std::string translated;
    bool hasTrans = false;
};

static bool isCjk(unsigned int cp) { return cp >= 0x4E00 && cp <= 0x9FFF; }

static std::vector<unsigned int> decodeUtf8(const std::string& s) {
    std::vector<unsigned int> out;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = s[i];
        unsigned int cp = 0;
        int extra = 0;
        if (c < 0x80) { cp = c; }
        else if ((c & 0xE0) == 0xC0) { cp = c & 0x1F; extra = 1; }
        else if ((c & 0xF0) == 0xE0) { cp = c & 0x0F; extra = 2; }
        else if ((c & 0xF8) == 0xF0) { cp = c & 0x07; extra = 3; }
        else { ++i; continue; }
        for (int k = 0; k < extra && i + 1 < s.size(); ++k) {
            ++i;
            cp = (cp << 6) | (s[i] & 0x3F);
        }
        out.push_back(cp);
        ++i;
    }
    return out;
}

static std::string encodeUtf8(unsigned int cp) {
    std::string s;
    if (cp < 0x80) s += static_cast<char>(cp);
    else if (cp < 0x800) {
        s += static_cast<char>(0xC0 | (cp >> 6));
        s += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        s += static_cast<char>(0xE0 | (cp >> 12));
        s += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        s += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        s += static_cast<char>(0xF0 | (cp >> 18));
        s += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        s += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        s += static_cast<char>(0x80 | (cp & 0x3F));
    }
    return s;
}

static bool isAlnum(unsigned int cp) {
    return (cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z');
}
static bool isSpace(unsigned int cp) {
    return cp == ' ' || cp == '\t' || cp == '\n' || cp == '\r';
}

static int countWords(const std::string& text) {
    auto cps = decodeUtf8(text);
    int total = 0;
    size_t i = 0;
    while (i < cps.size()) {
        if (isCjk(cps[i])) {
            size_t j = i;
            while (j < cps.size() && isCjk(cps[j])) ++j;
            total += static_cast<int>((j - i + 1) / 2);
            i = j;
        } else {
            // 与 HTML 参考实现一致：非 CJK 段按 [A-Za-z0-9]+(?:'[A-Za-z]+)? 计数，
            // 所以 "don't" 记 1 个词、"A1_V_Φ10" 记 3 个（A1 / V / 10）。
            size_t k = i;
            while (k < cps.size() && !isCjk(cps[k])) {
                if (isAlnum(cps[k])) {
                    size_t m = k;
                    while (m < cps.size() && !isCjk(cps[m]) && isAlnum(cps[m])) ++m;
                    if (m < cps.size() && cps[m] == '\'') {
                        size_t a = m + 1;
                        size_t b = a;
                        while (b < cps.size() && !isCjk(cps[b]) && isAlnum(cps[b])) ++b;
                        if (b > a) m = b;
                    }
                    ++total;
                    k = m;
                } else {
                    ++k;
                }
            }
            i = k;
        }
    }
    return total;
}

static std::vector<std::string> tokenize(const std::string& text) {
    auto cps = decodeUtf8(text);
    std::vector<std::string> tokens;
    size_t i = 0;
    while (i < cps.size()) {
        if (isCjk(cps[i])) {
            size_t j = i;
            while (j < cps.size() && isCjk(cps[j])) ++j;
            for (size_t k = i; k < j; k += 2) {
                std::string tok;
                tok += encodeUtf8(cps[k]);
                if (k + 1 < j) tok += encodeUtf8(cps[k + 1]);
                tokens.push_back(tok);
            }
            i = j;
        } else if (isSpace(cps[i])) {
            ++i;
        } else {
            // 与 HTML 参考实现一致：[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S
            // 字母数字连续段（可带 'xx）整体成一个 token，其余非空白字符各自成 token，
            // 所以 "world," 拆成 "world" 与 ","。
            size_t j = i;
            while (j < cps.size() && !isCjk(cps[j]) && !isSpace(cps[j])) ++j;
            size_t k = i;
            while (k < j) {
                if (isAlnum(cps[k])) {
                    size_t m = k;
                    while (m < j && isAlnum(cps[m])) ++m;
                    if (m < j && cps[m] == '\'') {
                        size_t a = m + 1;
                        size_t b = a;
                        while (b < j && isAlnum(cps[b])) ++b;
                        if (b > a) m = b;
                    }
                    std::string word;
                    for (size_t t = k; t < m; ++t) word += encodeUtf8(cps[t]);
                    tokens.push_back(word);
                    k = m;
                } else {
                    tokens.push_back(encodeUtf8(cps[k]));
                    ++k;
                }
            }
            i = j;
        }
    }
    return tokens;
}

static std::string joinTokens(const std::vector<std::string>& tokens) {
    std::string out;
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (i > 0) {
            auto prevCps = decodeUtf8(tokens[i - 1]);
            auto curCps = decodeUtf8(tokens[i]);
            if (!prevCps.empty() && !curCps.empty() &&
                !isCjk(prevCps.back()) && !isCjk(curCps.front())) {
                out += ' ';
            }
        }
        out += tokens[i];
    }
    return out;
}

static std::string addBoundarySpaces(const std::string& s) {
    // 在「字母数字」与「CJK」交界处补一个空格。
    // 不用 std::regex：GCC 的 <regex> 不支持 \x{4e00} 这类码点转义，
    // 构造时会抛异常（静态局部初始化抛异常 → 进程直接终止）。
    std::string out;
    unsigned int prev = 0;
    bool hasPrev = false;
    for (auto cp : decodeUtf8(s)) {
        if (hasPrev && ((isAlnum(prev) && isCjk(cp)) || (isCjk(prev) && isAlnum(cp))))
            out += ' ';
        out += encodeUtf8(cp);
        prev = cp;
        hasPrev = true;
    }
    return out;
}

static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

static std::vector<std::pair<std::string, std::string>>
splitPaired(const std::string& orig, const std::string& trans, int maxWords) {
    if (orig.empty() && trans.empty()) return { { "", "" } };
    auto o = tokenize(orig);
    auto t = tokenize(trans);
    std::vector<std::pair<std::string, std::string>> chunks;
    size_t oi = 0, ti = 0;
    while (oi < o.size() || ti < t.size()) {
        std::vector<std::string> oc, tc;
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
        chunks.push_back({ trim(addBoundarySpaces(joinTokens(oc))),
                           trim(addBoundarySpaces(joinTokens(tc))) });
    }
    if (chunks.empty()) chunks.push_back({ orig, trans });
    return chunks;
}

static long long timeToMs(const std::string& s) {
    auto p1 = s.find(':');
    if (p1 == std::string::npos) return 0;
    auto p2 = s.find(':', p1 + 1);
    if (p2 == std::string::npos) return 0;
    long long h = std::atoll(s.substr(0, p1).c_str());
    long long m = std::atoll(s.substr(p1 + 1, p2 - p1 - 1).c_str());
    std::string secPart = s.substr(p2 + 1);
    long long sec = 0, ms = 0;
    auto comma = secPart.find(',');
    auto dot = secPart.find('.');
    if (comma != std::string::npos) {
        sec = std::atoll(secPart.substr(0, comma).c_str());
        std::string frac = secPart.substr(comma + 1);
        while (frac.size() < 3) frac += '0';
        ms = std::atoll(frac.substr(0, 3).c_str());
    } else if (dot != std::string::npos) {
        sec = std::atoll(secPart.substr(0, dot).c_str());
        std::string frac = secPart.substr(dot + 1);
        while (frac.size() < 2) frac += '0';
        double frames = std::atof(frac.substr(0, 2).c_str());
        ms = static_cast<long long>(frames * 40.0 + 0.5);
    } else {
        sec = std::atoll(secPart.c_str());
    }
    return (h * 3600 + m * 60 + sec) * 1000 + ms;
}

static std::string msToTime(long long ms) {
    long long h = ms / 3600000; ms %= 3600000;
    long long m = ms / 60000; ms %= 60000;
    long long s = ms / 1000;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%02lld:%02lld:%02lld,%03lld", h, m, s, ms % 1000);
    return buf;
}

static std::vector<Entry> parseSubtitle(const std::string& content) {
    static const std::regex timeRe(
        "^([0-9]{1,2}:[0-9]{2}:[0-9]{2}[,.][0-9]{1,3})\\s*-->\\s*"
        "([0-9]{1,2}:[0-9]{2}:[0-9]{2}[,.][0-9]{1,3})$");
    std::string clean = content;
    if (clean.rfind("\xEF\xBB\xBF", 0) == 0) clean = clean.substr(3);

    std::string norm;
    for (size_t i = 0; i < clean.size(); ++i) {
        if (clean[i] == '\r') { if (i + 1 < clean.size() && clean[i + 1] == '\n') continue; norm += '\n'; }
        else norm += clean[i];
    }

    std::vector<std::string> blocks;
    std::string cur;
    std::istringstream iss(norm);
    std::string line;
    while (std::getline(iss, line)) {
        if (trim(line).empty()) {
            if (!cur.empty()) { blocks.push_back(cur); cur.clear(); }
        } else {
            if (!cur.empty()) cur += '\n';
            cur += line;
        }
    }
    if (!cur.empty()) blocks.push_back(cur);

    std::vector<Entry> entries;
    std::set<int> seen;
    for (const auto& block : blocks) {
        std::vector<std::string> lines;
        std::istringstream bs(block);
        std::string l;
        while (std::getline(bs, l)) {
            auto t = trim(l);
            if (!t.empty()) lines.push_back(t);
        }
        if (lines.size() < 3) continue;
        if (!std::all_of(lines[0].begin(), lines[0].end(), ::isdigit)) continue;
        std::smatch m;
        if (!std::regex_match(lines[1], m, timeRe)) continue;
        int index = std::atoi(lines[0].c_str());
        if (seen.count(index)) continue;
        seen.insert(index);

        std::string start = m[1].str(), end = m[2].str();
        std::replace(start.begin(), start.end(), '.', ',');
        std::replace(end.begin(), end.end(), '.', ',');
        long long sm = timeToMs(start);
        if (sm >= timeToMs(end)) end = msToTime(sm + 1);

        std::string text;
        for (size_t i = 2; i < lines.size(); ++i) {
            if (!text.empty()) text += '\n';
            text += lines[i];
        }
        if (trim(text).empty()) continue;

        Entry e;
        e.index = index; e.start = start; e.end = end; e.text = text;
        entries.push_back(e);
    }
    std::sort(entries.begin(), entries.end(), [](const Entry& a, const Entry& b) { return a.index < b.index; });
    return entries;
}

static void applyTimeFix(std::vector<Entry>& entries, const std::string& strategy) {
    if (strategy == "keep" || strategy.empty()) return;
    if (strategy == "delete") {
        std::vector<Entry> out;
        for (const auto& e : entries)
            if (timeToMs(e.end) - timeToMs(e.start) >= 10) out.push_back(e);
        entries = out;
        return;
    }
    if (strategy == "extend") {
        for (size_t i = 0; i < entries.size(); ++i) {
            long long s = timeToMs(entries[i].start);
            long long e = timeToMs(entries[i].end);
            if (e - s < 10) {
                long long newEnd = s + 10;
                entries[i].end = msToTime(newEnd);
                long long shift = newEnd - e;
                for (size_t j = i + 1; j < entries.size(); ++j) {
                    entries[j].start = msToTime(timeToMs(entries[j].start) + shift);
                    entries[j].end = msToTime(timeToMs(entries[j].end) + shift);
                }
            }
        }
    }
}

static int applyTranslation(std::vector<Entry>& entries, const std::string& transStr) {
    static const std::regex idxRe("^\\[([0-9]+)\\]\\s*(.*)$");
    std::map<int, std::string> mapping;
    std::istringstream iss(transStr);
    std::string line;
    int cur = -1;
    std::string buf;
    auto flush = [&]() { if (cur >= 0) mapping[cur] = trim(buf); };
    while (std::getline(iss, line)) {
        auto t = trim(line);
        std::smatch m;
        if (std::regex_match(t, m, idxRe)) {
            flush();
            cur = std::atoi(m[1].str().c_str());
            buf = trim(m[2].str());
            continue;
        }
        if (cur >= 0 && !t.empty()) {
            if (!buf.empty()) buf += '\n';
            buf += t;
        }
    }
    flush();

    int applied = 0;
    for (auto& e : entries) {
        auto it = mapping.find(e.index);
        if (it != mapping.end()) {
            e.translated = it->second;
            e.hasTrans = true;
            ++applied;
        }
    }
    return applied;
}

static std::string exportSrt(const std::vector<Entry>& entries, const std::string& mode) {
    std::string out;
    for (const auto& e : entries) {
        std::string text;
        if (mode == "orig") text = e.text;
        else if (mode == "trans") text = e.translated;
        else {
            if (e.hasTrans && !e.text.empty()) text = e.text + "\n" + e.translated;
            else if (e.hasTrans) text = e.translated;
            else text = e.text;
        }
        out += std::to_string(e.index) + "\n" + e.start + " --> " + e.end + "\n" + text + "\n\n";
    }
    return out;
}

static void usage() {
    std::cout << "SubMerge Pro 内核版（C++）\n"
              << "用法:\n"
              << "  submerge parse <字幕文件>\n"
              << "  submerge export <字幕文件> [--trans 译文] [--mode both|orig|trans] [--time-fix keep|delete|extend]\n"
              << "  submerge merge-prompt <字幕文件> [--trans 译文] [--max N]\n";
}

static bool readFile(const std::string& path, std::string& out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::ostringstream ss;
    ss << f.rdbuf();
    out = ss.str();
    return true;
}

int main(int argc, char** argv) {
    if (argc < 2) { usage(); return 1; }
    std::string cmd = argv[1];
    if (cmd == "-h" || cmd == "--help") { usage(); return 0; }

    std::string file, transFile, mode = "both", timeFix = "keep";
    int maxWords = 10;

    for (int i = 2; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--trans" && i + 1 < argc) transFile = argv[++i];
        else if (a == "--mode" && i + 1 < argc) mode = argv[++i];
        else if (a == "--time-fix" && i + 1 < argc) timeFix = argv[++i];
        else if (a == "--max" && i + 1 < argc) maxWords = std::atoi(argv[++i]);
        else if (a.rfind("--", 0) != 0 && file.empty()) file = a;
    }

    if (file.empty()) { std::cerr << "错误：未指定字幕文件\n"; return 1; }

    std::string content;
    if (!readFile(file, content)) { std::cerr << "无法读取 " << file << "\n"; return 1; }

    auto entries = parseSubtitle(content);
    if (entries.empty()) { std::cerr << "解析失败：未找到字幕条目\n"; return 1; }
    applyTimeFix(entries, timeFix);

    if (!transFile.empty()) {
        std::string trans;
        if (!readFile(transFile, trans)) { std::cerr << "无法读取 " << transFile << "\n"; return 1; }
        std::cout << "已应用 " << applyTranslation(entries, trans) << " 条译文\n";
    }

    if (cmd == "parse") {
        int total = 0;
        for (const auto& e : entries) total += countWords(e.text);
        std::cout << "条目数: " << entries.size() << "\n总词数: " << total << "\n";
        const auto& f = entries.front();
        const auto& l = entries.back();
        std::cout << "首条: [" << f.index << "] " << f.start << " --> " << f.end << " | " << f.text << "\n";
        std::cout << "末条: [" << l.index << "] " << l.start << " --> " << l.end << " | " << l.text << "\n";
    } else if (cmd == "export") {
        std::cout << exportSrt(entries, mode);
    } else if (cmd == "merge-prompt") {
        for (const auto& e : entries) {
            for (const auto& c : splitPaired(e.text, e.translated, maxWords)) {
                std::string body = c.second.empty() ? c.first : (c.first + "\n" + c.second);
                std::cout << "[" << e.index << "] " << trim(body) << "\n";
            }
        }
    } else {
        std::cerr << "错误：未知子命令 " << cmd << "\n";
        usage();
        return 1;
    }
    return 0;
}
