// Writer 内核版（C++17）
//
// 版本：A1_I_Φ5_Cpp_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html
//
// 只实现纯逻辑内核：书籍 / 卷 / 章节结构、字数统计、章节排序、
// 跨卷移动、引用管理、提示词模板合成。
//
// 存储格式：JSON（与 Python / TypeScript / Go / Rust 版一致，库文件可互通）。
//   { "books": [...], "volumes": [...], "chapters": [...], "entities": [...] }
//   字段名用 snake_case：book_id / volume_id / word_count / updated_at。
//
// 为不引入第三方依赖，本文件自带最小 JSON 读写实现（只覆盖用到的类型：
// 对象、数组、字符串、整数、bool、null）。
//
// 兼容旧版：若读到旧 TSV 格式（B/V/C/E + TAB 开头），先备份成
// <库文件>.tsv.bak，再按 JSON 重写。两种格式都解析失败时直接报错退出，
// 绝不写回 —— 避免把用户手稿覆盖成空库。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#endif

struct Book { std::string id, title; long long updatedAt = 0; };
struct Volume { std::string id, bookId, title; int order = 0; };
struct Chapter {
    std::string id, bookId, volumeId, title;
    int order = 0;
    long long wordCount = 0;
    std::string text;
};
struct Entity { std::string id, bookId, name, kind, description; };

struct Library {
    std::vector<Book> books;
    std::vector<Volume> volumes;
    std::vector<Chapter> chapters;
    std::vector<Entity> entities;
};

static long long g_counter = 0;

static long long nowTs() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

static std::string genId(const std::string& prefix) {
    return prefix + "_" + std::to_string(nowTs()) + "_" + std::to_string(++g_counter);
}

static bool isCjk(unsigned int cp) {
    return (cp >= 0x3400 && cp <= 0x4DBF) || (cp >= 0x4E00 && cp <= 0x9FFF) ||
           (cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0xAC00 && cp <= 0xD7AF) ||
           (cp >= 0xF900 && cp <= 0xFAFF);
}

static std::vector<unsigned int> decodeUtf8(const std::string& s) {
    std::vector<unsigned int> out;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = s[i];
        unsigned int cp = 0; int extra = 0;
        if (c < 0x80) { cp = c; }
        else if ((c & 0xE0) == 0xC0) { cp = c & 0x1F; extra = 1; }
        else if ((c & 0xF0) == 0xE0) { cp = c & 0x0F; extra = 2; }
        else if ((c & 0xF8) == 0xF0) { cp = c & 0x07; extra = 3; }
        else { ++i; continue; }
        for (int k = 0; k < extra && i + 1 < s.size(); ++k) { ++i; cp = (cp << 6) | (s[i] & 0x3F); }
        out.push_back(cp);
        ++i;
    }
    return out;
}

// 与浏览器版一致：CJK 每字算 1 词，拉丁词按整词算。
static long long countWords(const std::string& text) {
    long long total = 0;
    bool inLatin = false;
    for (unsigned int cp : decodeUtf8(text)) {
        if (isCjk(cp)) { ++total; inLatin = false; }
        else if ((cp >= '0' && cp <= '9') || (cp >= 'a' && cp <= 'z') || (cp >= 'A' && cp <= 'Z')) {
            if (!inLatin) { ++total; inLatin = true; }
        } else inLatin = false;
    }
    return total;
}

static std::string escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '\\') out += "\\\\";
        else if (c == '\t') out += "\\t";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') continue;
        else out += c;
    }
    return out;
}

static std::string unescape(const std::string& s) {
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == '\\' && i + 1 < s.size()) {
            char n = s[++i];
            if (n == 't') out += '\t';
            else if (n == 'n') out += '\n';
            else out += n;
        } else out += s[i];
    }
    return out;
}

static std::vector<std::string> split(const std::string& s, char sep) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == sep) { out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    out.push_back(cur);
    return out;
}

/* ---------------- 最小 JSON 实现 ---------------- */

static std::string jsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        default:
            if (c < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                out += buf;
            } else {
                out += static_cast<char>(c);
            }
        }
    }
    return out;
}

/* 极简 JSON 解析：只支持本程序写出的形状。解析失败返回 false，调用方据此
   报错并拒绝写回 —— 这是防止「格式不符被当成空库再覆盖」的关键。 */
class JsonReader {
public:
    explicit JsonReader(const std::string& s) : s_(s), i_(0), ok_(true) {}

    bool ok() const { return ok_; }
    bool atEnd() {
        skipWs();
        return i_ >= s_.size();
    }

    bool expect(char c) {
        skipWs();
        if (i_ < s_.size() && s_[i_] == c) { ++i_; return true; }
        ok_ = false;
        return false;
    }

    bool peekIs(char c) {
        skipWs();
        return i_ < s_.size() && s_[i_] == c;
    }

    bool readString(std::string& out) {
        skipWs();
        if (i_ >= s_.size() || s_[i_] != '"') { ok_ = false; return false; }
        ++i_;
        out.clear();
        while (i_ < s_.size()) {
            char c = s_[i_++];
            if (c == '"') return true;
            if (c != '\\') { out += c; continue; }
            if (i_ >= s_.size()) break;
            char e = s_[i_++];
            switch (e) {
            case '"': out += '"'; break;
            case '\\': out += '\\'; break;
            case '/': out += '/'; break;
            case 'n': out += '\n'; break;
            case 'r': out += '\r'; break;
            case 't': out += '\t'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'u': {
                if (i_ + 4 > s_.size()) { ok_ = false; return false; }
                unsigned cp = 0;
                for (int k = 0; k < 4; ++k) {
                    char h = s_[i_ + k];
                    cp <<= 4;
                    if (h >= '0' && h <= '9') cp |= (unsigned)(h - '0');
                    else if (h >= 'a' && h <= 'f') cp |= (unsigned)(h - 'a' + 10);
                    else if (h >= 'A' && h <= 'F') cp |= (unsigned)(h - 'A' + 10);
                    else { ok_ = false; return false; }
                }
                i_ += 4;
                // 只处理 BMP；代理对尚未在本程序中产生，遇到按替换字符处理
                if (cp >= 0xD800 && cp <= 0xDFFF) out += '?';
                else if (cp < 0x80) out += (char)cp;
                else if (cp < 0x800) {
                    out += (char)(0xC0 | (cp >> 6));
                    out += (char)(0x80 | (cp & 0x3F));
                } else {
                    out += (char)(0xE0 | (cp >> 12));
                    out += (char)(0x80 | ((cp >> 6) & 0x3F));
                    out += (char)(0x80 | (cp & 0x3F));
                }
                break;
            }
            default: ok_ = false; return false;
            }
        }
        ok_ = false;
        return false;
    }

    bool readInt(long long& out) {
        skipWs();
        size_t start = i_;
        if (i_ < s_.size() && (s_[i_] == '-' || s_[i_] == '+')) ++i_;
        while (i_ < s_.size() && s_[i_] >= '0' && s_[i_] <= '9') ++i_;
        if (i_ == start) { ok_ = false; return false; }
        try { out = std::stoll(s_.substr(start, i_ - start)); }
        catch (...) { ok_ = false; return false; }
        return true;
    }

    bool skipValue() {
        skipWs();
        if (i_ >= s_.size()) { ok_ = false; return false; }
        char c = s_[i_];
        if (c == '"') { std::string tmp; return readString(tmp); }
        if (c == '{') {
            ++i_;
            if (peekIs('}')) { expect('}'); return true; }
            while (true) {
                std::string k;
                if (!readString(k)) return false;
                if (!expect(':')) return false;
                if (!skipValue()) return false;
                if (peekIs(',')) { expect(','); continue; }
                return expect('}');
            }
        }
        if (c == '[') {
            ++i_;
            if (peekIs(']')) { expect(']'); return true; }
            while (true) {
                if (!skipValue()) return false;
                if (peekIs(',')) { expect(','); continue; }
                return expect(']');
            }
        }
        if (s_.compare(i_, 4, "true") == 0) { i_ += 4; return true; }
        if (s_.compare(i_, 5, "false") == 0) { i_ += 5; return true; }
        if (s_.compare(i_, 4, "null") == 0) { i_ += 4; return true; }
        long long tmp;
        return readInt(tmp);
    }

private:
    void skipWs() {
        while (i_ < s_.size()) {
            char c = s_[i_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++i_;
            else break;
        }
    }

    const std::string& s_;
    size_t i_;
    bool ok_;
};

/* 逐字段读一个对象，回调按 key 取值。未识别的键跳过。 */
template <typename Fn>
static bool readObject(JsonReader& r, Fn onKey) {
    if (!r.expect('{')) return false;
    if (r.peekIs('}')) { r.expect('}'); return true; }
    while (true) {
        std::string key;
        if (!r.readString(key)) return false;
        if (!r.expect(':')) return false;
        if (!onKey(key, r)) return false;
        // 注意：判断「还有没有下一个键」必须用 peek，不能直接 expect——后者
        // 在没匹配时会置 ok_=false，把正常的结束当成语法错误。
        if (r.peekIs(',')) { r.expect(','); continue; }
        return r.expect('}');
    }
}

/* 读一个数组，对每个元素调用 onItem。 */
template <typename Fn>
static bool readArray(JsonReader& r, Fn onItem) {
    if (!r.expect('[')) return false;
    if (r.peekIs(']')) { r.expect(']'); return true; }
    while (true) {
        if (!onItem()) return false;
        if (r.peekIs(',')) { r.expect(','); continue; }
        return r.expect(']');
    }
}

static bool parseJsonLibrary(const std::string& text, Library& lib) {
    JsonReader r(text);
    bool sawRoot = false;
    bool ok = readObject(r, [&](const std::string& key, JsonReader& rr) -> bool {
        if (key == "books") {
            sawRoot = true;
            return readArray(rr, [&]() -> bool {
                Book b;
                bool okItem = readObject(rr, [&](const std::string& k, JsonReader& r3) -> bool {
                    if (k == "id") return r3.readString(b.id);
                    if (k == "title") return r3.readString(b.title);
                    if (k == "updated_at") return r3.readInt(b.updatedAt);
                    return r3.skipValue();
                });
                if (okItem) lib.books.push_back(b);
                return okItem;
            });
        }
        if (key == "volumes") {
            sawRoot = true;
            return readArray(rr, [&]() -> bool {
                Volume v;
                bool okItem = readObject(rr, [&](const std::string& k, JsonReader& r3) -> bool {
                    if (k == "id") return r3.readString(v.id);
                    if (k == "book_id") return r3.readString(v.bookId);
                    if (k == "title") return r3.readString(v.title);
                    if (k == "order") { long long n = 0; if (!r3.readInt(n)) return false; v.order = (int)n; return true; }
                    return r3.skipValue();
                });
                if (okItem) lib.volumes.push_back(v);
                return okItem;
            });
        }
        if (key == "chapters") {
            sawRoot = true;
            return readArray(rr, [&]() -> bool {
                Chapter c;
                bool okItem = readObject(rr, [&](const std::string& k, JsonReader& r3) -> bool {
                    if (k == "id") return r3.readString(c.id);
                    if (k == "book_id") return r3.readString(c.bookId);
                    if (k == "volume_id") return r3.readString(c.volumeId);
                    if (k == "title") return r3.readString(c.title);
                    if (k == "text") return r3.readString(c.text);
                    if (k == "order") { long long n = 0; if (!r3.readInt(n)) return false; c.order = (int)n; return true; }
                    if (k == "word_count") return r3.readInt(c.wordCount);
                    return r3.skipValue();
                });
                if (okItem) lib.chapters.push_back(c);
                return okItem;
            });
        }
        if (key == "entities") {
            sawRoot = true;
            return readArray(rr, [&]() -> bool {
                Entity e;
                bool okItem = readObject(rr, [&](const std::string& k, JsonReader& r3) -> bool {
                    if (k == "id") return r3.readString(e.id);
                    if (k == "book_id") return r3.readString(e.bookId);
                    if (k == "name") return r3.readString(e.name);
                    if (k == "kind") return r3.readString(e.kind);
                    if (k == "description") return r3.readString(e.description);
                    return r3.skipValue();
                });
                if (okItem) lib.entities.push_back(e);
                return okItem;
            });
        }
        return rr.skipValue();
    });
    if (!ok || !r.ok() || !sawRoot) return false;
    if (!r.atEnd()) return false;
    return true;
}

static std::string serializeJson(const Library& lib) {
    std::ostringstream o;
    o << "{\n  \"books\": [";
    for (size_t i = 0; i < lib.books.size(); ++i) {
        const auto& b = lib.books[i];
        if (i) o << ",";
        o << "\n    {\"id\": \"" << jsonEscape(b.id) << "\", \"title\": \"" << jsonEscape(b.title)
          << "\", \"author\": \"\", \"updated_at\": " << b.updatedAt << "}";
    }
    o << (lib.books.empty() ? "" : "\n  ") << "],\n  \"volumes\": [";
    for (size_t i = 0; i < lib.volumes.size(); ++i) {
        const auto& v = lib.volumes[i];
        if (i) o << ",";
        o << "\n    {\"id\": \"" << jsonEscape(v.id) << "\", \"book_id\": \"" << jsonEscape(v.bookId)
          << "\", \"title\": \"" << jsonEscape(v.title) << "\", \"order\": " << v.order << "}";
    }
    o << (lib.volumes.empty() ? "" : "\n  ") << "],\n  \"chapters\": [";
    for (size_t i = 0; i < lib.chapters.size(); ++i) {
        const auto& c = lib.chapters[i];
        if (i) o << ",";
        o << "\n    {\"id\": \"" << jsonEscape(c.id) << "\", \"book_id\": \"" << jsonEscape(c.bookId)
          << "\", \"volume_id\": \"" << jsonEscape(c.volumeId) << "\", \"title\": \"" << jsonEscape(c.title)
          << "\", \"order\": " << c.order << ", \"word_count\": " << c.wordCount
          << ", \"updated_at\": 0, \"text\": \"" << jsonEscape(c.text) << "\"}";
    }
    o << (lib.chapters.empty() ? "" : "\n  ") << "],\n  \"entities\": [";
    for (size_t i = 0; i < lib.entities.size(); ++i) {
        const auto& e = lib.entities[i];
        if (i) o << ",";
        o << "\n    {\"id\": \"" << jsonEscape(e.id) << "\", \"book_id\": \"" << jsonEscape(e.bookId)
          << "\", \"name\": \"" << jsonEscape(e.name) << "\", \"kind\": \"" << jsonEscape(e.kind)
          << "\", \"description\": \"" << jsonEscape(e.description) << "\"}";
    }
    o << (lib.entities.empty() ? "" : "\n  ") << "]\n}\n";
    return o.str();
}

/* 旧 TSV 解析（仅用于迁移）。 */
static bool parseTsvLibrary(const std::string& text, Library& lib) {
    bool any = false;
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        auto parts = split(line, '\t');
        if (parts.empty()) continue;
        if (parts[0] == "B" && parts.size() >= 4) {
            lib.books.push_back({ parts[1], unescape(parts[2]), std::stoll(parts[3]) });
            any = true;
        } else if (parts[0] == "V" && parts.size() >= 5) {
            lib.volumes.push_back({ parts[1], parts[2], unescape(parts[3]), std::stoi(parts[4]) });
            any = true;
        } else if (parts[0] == "C" && parts.size() >= 8) {
            Chapter c;
            c.id = parts[1]; c.bookId = parts[2]; c.volumeId = parts[3];
            c.title = unescape(parts[4]); c.order = std::stoi(parts[5]);
            c.wordCount = std::stoll(parts[6]); c.text = unescape(parts[7]);
            lib.chapters.push_back(c);
            any = true;
        } else if (parts[0] == "E" && parts.size() >= 6) {
            lib.entities.push_back({ parts[1], parts[2], unescape(parts[3]),
                                     unescape(parts[4]), unescape(parts[5]) });
            any = true;
        }
    }
    return any;
}

/* 读取结果：区分「文件不存在」「内容为空」「格式错误」。 */
enum class LoadStatus { Missing, Empty, Ok, BadFormat };

static LoadStatus loadLibrary(const std::string& path, Library& lib, bool& migrated) {
    migrated = false;
    std::ifstream f(path, std::ios::binary);
    if (!f) return LoadStatus::Missing;
    std::string text((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    f.close();

    size_t start = text.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return LoadStatus::Empty;

    if (text[start] == '{') {
        if (parseJsonLibrary(text.substr(start), lib)) return LoadStatus::Ok;
        return LoadStatus::BadFormat;
    }

    // 旧 TSV：先备份，再按 JSON 重写
    Library legacy;
    if (!parseTsvLibrary(text, legacy)) return LoadStatus::BadFormat;
    std::string bak = path + ".tsv.bak";
    std::rename(path.c_str(), bak.c_str());
    lib = legacy;
    migrated = true;
    return LoadStatus::Ok;
}

static bool save(const std::string& path, const Library& lib) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    f << serializeJson(lib);
    return static_cast<bool>(f);
}

static std::vector<Chapter*> chaptersOf(Library& lib, const std::string& volId) {
    std::vector<Chapter*> list;
    for (auto& c : lib.chapters) if (c.volumeId == volId) list.push_back(&c);
    std::sort(list.begin(), list.end(), [](Chapter* a, Chapter* b) { return a->order < b->order; });
    return list;
}

static void reorderVolume(Library& lib, const std::string& volId) {
    auto list = chaptersOf(lib, volId);
    for (size_t i = 0; i < list.size(); ++i) list[i]->order = (int)i;
}

// 人称转换的目标人称。key 与 --target 取值、HTML 版 A1_I_Φ5_CN 的
// #povTarget option value 一一对应。
static std::string povTarget(const std::string& key) {
    if (key == "first") return "第一人称（我）";
    if (key == "second") return "第二人称（你）";
    if (key == "third") return "第三人称（他 / 她 / 它）";
    return "";
}

// 合成「人称转换」提示词，与 HTML 版 A1_I_Φ5_CN 的 pov 模板一致。
static std::string buildPovPrompt(const std::string& body, const std::string& chars,
                                  const std::string& target, bool keepInner) {
    std::string inner = keepInner
        ? "保留：原视角的内心活动改写为目标视角可知的部分"
          "（用表情、动作、语气或外部观察替代直接叙述他人内心）"
        : "不保留：删去目标视角无法感知的心理描写，只保留外在可见的行为与对白";
    std::ostringstream o;
    o << "你是一位精通叙述视角的小说编辑。请把下面的正文转换为【" << target
      << "】，情节、人物、场景与对白内容一律不变，只换叙述人称与视角。\n\n"
      << "【目标人称】" << target << "\n\n"
      << "【心理描写处理】" << inner << "\n\n"
      << "【相关设定】\n" << chars << "\n\n"
      << "【需要转换的正文】\n" << body << "\n\n"
      << "【转换规则】\n"
      << "1) 只改人称代词与由此引起的视角变化，不增删情节、不改变人物性格与说话方式；\n"
      << "2) 第一人称：叙述者用「我」，只能写出「我」能感知到的内容"
         "（看到、听到、想到），不能直接叙述旁人心里在想什么；\n"
      << "3) 第二人称：叙述者用「你」，把读者带入场景，动作与感受都落在「你」身上；\n"
      << "4) 第三人称：叙述者用「他 / 她 / 它」或人物姓名，"
         "人物之间用姓名或称谓区分，避免代词指向不明；\n"
      << "5) 时间线、场景顺序、对白内容保持原样，"
         "对白中人物自称按其在故事中的实际人称调整；\n"
      << "6) 转换后通读一遍，确保没有残留的原人称代词、"
         "没有视角越界、没有半途切换人称。\n\n"
      << "【输出要求】直接输出转换后的完整正文，不要加解释、不要加标题、"
         "不要用「以下是」之类的开场白，便于直接替换当前章。";
    return o.str();
}

static void usage() {
    printf("Writer 内核版（C++）\n用法: writer <库文件> <子命令> [参数]\n\n");
    printf("子命令:\n  init <书名>\n  add-volume <书籍ID> <卷名>\n"
           "  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]\n  list <书籍ID>\n"
           "  stats <书籍ID>\n  move-chapter <章节ID> <目标卷ID>\n"
           "  add-entity <书籍ID> <名称> [类型] [描述]\n  prompt <书籍ID> <章节ID>\n"
           "  pov <书籍ID> <章节ID> [--target first|second|third] [--no-inner]\n"
           "  reindex <书籍ID>\n");
}

int main(int argc, char** argv) {
    // 库文件是 UTF-8 JSON（与其它语言实现互通）。Windows 下 argv 是 ANSI
    // 代码页，需转成 UTF-8，否则中文书名会以 GBK 字节写进 JSON，别的语言读不出来。
    std::vector<std::string> argvUtf8;
    argvUtf8.reserve(static_cast<size_t>(argc));
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    for (int i = 0; i < argc; ++i) {
        int wlen = MultiByteToWideChar(CP_ACP, 0, argv[i], -1, nullptr, 0);
        std::wstring w(static_cast<size_t>(wlen), L'\0');
        MultiByteToWideChar(CP_ACP, 0, argv[i], -1, &w[0], wlen);
        int ulen = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, nullptr, 0, nullptr, nullptr);
        std::string u(static_cast<size_t>(ulen), '\0');
        WideCharToMultiByte(CP_UTF8, 0, w.c_str(), -1, &u[0], ulen, nullptr, nullptr);
        if (!u.empty() && u.back() == '\0') u.pop_back();
        argvUtf8.push_back(u);
    }
    std::vector<char*> argvRaw;
    argvRaw.reserve(argvUtf8.size());
    for (auto& a : argvUtf8) argvRaw.push_back(&a[0]);
    argc = static_cast<int>(argvRaw.size());
    argv = argvRaw.data();
#endif
    if (argc < 3) { usage(); return 1; }
    std::string libPath = argv[1];
    std::string cmd = argv[2];
    std::vector<std::string> args(argv + 3, argv + argc);
    Library lib;
    bool migrated = false;
    LoadStatus st = loadLibrary(libPath, lib, migrated);
    if (st == LoadStatus::BadFormat) {
        fprintf(stderr, "错误：库文件格式无法识别（既不是 JSON 也不是旧版 TSV）\n");
        fprintf(stderr, "      为避免覆盖，本次不做任何写入：%s\n", libPath.c_str());
        return 1;
    }
    if (migrated) {
        fprintf(stderr, "提示：已把旧版 TSV 库迁移为 JSON，原文件备份为 %s.tsv.bak\n", libPath.c_str());
    }

    if (cmd == "init") {
        if (args.empty()) { fprintf(stderr, "缺少书名\n"); return 1; }
        Book b{ genId("book"), args[0], nowTs() };
        printf("已创建书籍: %s (%s)\n", b.title.c_str(), b.id.c_str());
        lib.books.push_back(b);
    } else if (cmd == "add-volume") {
        if (args.size() < 2) { fprintf(stderr, "缺少参数\n"); return 1; }
        bool found = false;
        for (auto& b : lib.books) if (b.id == args[0]) found = true;
        if (!found) { fprintf(stderr, "找不到书籍 %s\n", args[0].c_str()); return 1; }
        int order = 0;
        for (auto& v : lib.volumes) if (v.bookId == args[0]) order++;
        Volume v{ genId("vol"), args[0], args[1], order };
        printf("已新增卷: %s (%s)\n", v.title.c_str(), v.id.c_str());
        lib.volumes.push_back(v);
    } else if (cmd == "add-chapter") {
        if (args.size() < 3) { fprintf(stderr, "缺少参数\n"); return 1; }
        std::string text;
        if (args.size() >= 4) {
            std::ifstream f(args[3], std::ios::binary);
            if (f) { std::ostringstream ss; ss << f.rdbuf(); text = ss.str(); }
        }
        bool ok = false;
        for (auto& v : lib.volumes) if (v.id == args[1]) ok = true;
        if (!ok) { fprintf(stderr, "找不到卷 %s\n", args[1].c_str()); return 1; }
        int order = 0;
        for (auto& c : lib.chapters) if (c.volumeId == args[1]) order++;
        Chapter ch;
        ch.id = genId("ch"); ch.bookId = args[0]; ch.volumeId = args[1];
        ch.title = args[2]; ch.order = order;
        ch.wordCount = countWords(text); ch.text = text;
        printf("已新增章节: %s (%s) · %lld 字\n", ch.title.c_str(), ch.id.c_str(), ch.wordCount);
        lib.chapters.push_back(ch);
    } else if (cmd == "list") {
        if (args.empty()) { fprintf(stderr, "缺少书籍ID\n"); return 1; }
        Book* book = nullptr;
        for (auto& b : lib.books) if (b.id == args[0]) book = &b;
        if (!book) { fprintf(stderr, "找不到书籍\n"); return 1; }
        printf("书籍: %s (%s)\n", book->title.c_str(), book->id.c_str());
        std::vector<Volume*> vols;
        for (auto& v : lib.volumes) if (v.bookId == args[0]) vols.push_back(&v);
        std::sort(vols.begin(), vols.end(), [](Volume* a, Volume* b) { return a->order < b->order; });
        for (auto* v : vols) {
            printf("  卷: %s (order %d)\n", v->title.c_str(), v->order);
            for (auto* c : chaptersOf(lib, v->id))
                printf("    - [%d] %s · %lld 字\n", c->order, c->title.c_str(), c->wordCount);
        }
    } else if (cmd == "stats") {
        if (args.empty()) { fprintf(stderr, "缺少书籍ID\n"); return 1; }
        int n = 0; long long total = 0, chars = 0;
        for (auto& c : lib.chapters) {
            if (c.bookId == args[0]) {
                n++; total += c.wordCount;
                chars += (long long)decodeUtf8(c.text).size();
            }
        }
        printf("章节数: %d\n总字数: %lld\n总字符: %lld\n", n, total, chars);
    } else if (cmd == "move-chapter") {
        if (args.size() < 2) { fprintf(stderr, "缺少参数\n"); return 1; }
        Chapter* ch = nullptr;
        for (auto& c : lib.chapters) if (c.id == args[0]) ch = &c;
        if (!ch) { fprintf(stderr, "找不到章节\n"); return 1; }
        bool ok = false;
        for (auto& v : lib.volumes) if (v.id == args[1]) ok = true;
        if (!ok) { fprintf(stderr, "找不到目标卷 %s\n", args[1].c_str()); return 1; }
        std::string sourceVol = ch->volumeId;
        int newOrder = 0;
        for (auto& c : lib.chapters) if (c.volumeId == args[1]) newOrder++;
        ch->volumeId = args[1];
        ch->order = newOrder;
        reorderVolume(lib, args[1]);
        reorderVolume(lib, sourceVol);
        printf("已将章节移至目标卷，并重排源卷与目标卷的顺序\n");
    } else if (cmd == "add-entity") {
        if (args.size() < 2) { fprintf(stderr, "缺少参数\n"); return 1; }
        Entity e;
        e.id = genId("ent"); e.bookId = args[0]; e.name = args[1];
        e.kind = args.size() >= 3 ? args[2] : "其他";
        e.description = args.size() >= 4 ? args[3] : "";
        printf("已添加资料: %s (%s)\n", e.name.c_str(), e.id.c_str());
        lib.entities.push_back(e);
    } else if (cmd == "prompt") {
        if (args.size() < 2) { fprintf(stderr, "缺少参数\n"); return 1; }
        Chapter* ch = nullptr;
        for (auto& c : lib.chapters) if (c.id == args[1]) ch = &c;
        if (!ch) { fprintf(stderr, "找不到章节\n"); return 1; }
        auto list = chaptersOf(lib, ch->volumeId);
        int pos = 0;
        for (size_t i = 0; i < list.size(); ++i) if (list[i]->id == args[1]) pos = (int)i;
        std::string prev = "（本章为卷首，无上一章）";
        if (pos > 0) {
            auto cps = decodeUtf8(list[pos - 1]->text);
            if (cps.size() > 500) cps.erase(cps.begin(), cps.end() - 500);
            prev.clear();
            for (unsigned int cp : cps) {
                char buf[4]; int n = 0;
                if (cp < 0x80) buf[n++] = (char)cp;
                else if (cp < 0x800) { buf[n++] = 0xC0 | (cp >> 6); buf[n++] = 0x80 | (cp & 0x3F); }
                else { buf[n++] = 0xE0 | (cp >> 12); buf[n++] = 0x80 | ((cp >> 6) & 0x3F); buf[n++] = 0x80 | (cp & 0x3F); }
                prev.append(buf, n);
            }
        }
        std::string chars;
        for (auto& e : lib.entities) {
            if (e.bookId == args[0]) {
                chars += "- " + e.name + "（" + e.kind + "）：" + e.description + "\n";
            }
        }
        if (chars.empty()) chars = "（未填写）";
        printf("你是一位与作者合写的小说作者。请续写下一段情节。\n\n【设定】\n%s\n【上一章结尾】\n%s\n\n【本章已有正文】\n%s\n",
               chars.c_str(), prev.c_str(), ch->text.empty() ? "（当前章为空）" : ch->text.c_str());
    } else if (cmd == "pov") {
        if (args.size() < 2) { fprintf(stderr, "缺少参数\n"); return 1; }
        std::string targetKey = "third";
        bool keepInner = true;
        for (size_t i = 2; i < args.size(); ++i) {
            if (args[i] == "--target") {
                if (i + 1 >= args.size()) { fprintf(stderr, "--target 缺少取值\n"); return 1; }
                targetKey = args[i + 1];
                ++i;
            } else if (args[i] == "--no-inner") {
                keepInner = false;
            } else {
                fprintf(stderr, "无法识别的参数: %s\n", args[i].c_str());
                return 1;
            }
        }
        std::string target = povTarget(targetKey);
        if (target.empty()) {
            fprintf(stderr, "目标人称无效：%s（可选 first / second / third）\n", targetKey.c_str());
            return 1;
        }
        Chapter* ch = nullptr;
        for (auto& c : lib.chapters) if (c.id == args[1]) ch = &c;
        if (!ch) { fprintf(stderr, "找不到章节\n"); return 1; }
        std::vector<std::string> charsList;
        for (auto& e : lib.entities) {
            if (e.bookId == args[0]) {
                charsList.push_back("- " + e.name + "（" + e.kind + "）：" + e.description);
            }
        }
        std::string chars = "（未填写）";
        if (!charsList.empty()) {
            std::ostringstream co;
            for (size_t ci = 0; ci < charsList.size(); ++ci) {
                if (ci) co << "\n";
                co << charsList[ci];
            }
            chars = co.str();
        }
        std::string body = ch->text.empty() ? "（当前章为空）" : ch->text;
        printf("%s\n", buildPovPrompt(body, chars, target, keepInner).c_str());
    } else if (cmd == "reindex") {
        if (args.empty()) { fprintf(stderr, "缺少书籍ID\n"); return 1; }
        std::vector<std::string> ids;
        for (auto& v : lib.volumes) if (v.bookId == args[0]) ids.push_back(v.id);
        for (auto& id : ids) reorderVolume(lib, id);
        printf("已重排全部卷的章节顺序\n");
    } else {
        fprintf(stderr, "未知子命令: %s\n", cmd.c_str());
        return 1;
    }

    if (!save(libPath, lib)) {
        fprintf(stderr, "错误：写入库文件失败：%s\n", libPath.c_str());
        return 1;
    }
    return 0;
}
