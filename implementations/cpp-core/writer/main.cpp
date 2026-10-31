// Writer 内核版（C++17）
//
// 版本：A1_I_Φ5_Cpp_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html
//
// 只实现纯逻辑内核：书籍 / 卷 / 章节结构、字数统计、章节排序、
// 跨卷移动、引用管理、提示词模板合成。
//
// 存储格式：为免引入 JSON 库，采用与浏览器版字段一一对应的文本格式：
//   B<TAB>id<TAB>title<TAB>updated_at
//   V<TAB>id<TAB>book_id<TAB>title<TAB>order
//   C<TAB>id<TAB>book_id<TAB>volume_id<TAB>title<TAB>order<TAB>word_count<TAB>text(转义)
//   E<TAB>id<TAB>book_id<TAB>name<TAB>kind<TAB>description(转义)
// 转义规则：\ -> \\，\t -> \t，\n -> \n
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

static Library load(const std::string& path) {
    Library lib;
    std::ifstream f(path, std::ios::binary);
    if (!f) return lib;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        auto parts = split(line, '\t');
        if (parts.empty()) continue;
        if (parts[0] == "B" && parts.size() >= 4) {
            lib.books.push_back({ parts[1], unescape(parts[2]), std::stoll(parts[3]) });
        } else if (parts[0] == "V" && parts.size() >= 5) {
            lib.volumes.push_back({ parts[1], parts[2], unescape(parts[3]), std::stoi(parts[4]) });
        } else if (parts[0] == "C" && parts.size() >= 8) {
            Chapter c;
            c.id = parts[1]; c.bookId = parts[2]; c.volumeId = parts[3];
            c.title = unescape(parts[4]); c.order = std::stoi(parts[5]);
            c.wordCount = std::stoll(parts[6]); c.text = unescape(parts[7]);
            lib.chapters.push_back(c);
        } else if (parts[0] == "E" && parts.size() >= 6) {
            lib.entities.push_back({ parts[1], parts[2], unescape(parts[3]),
                                     unescape(parts[4]), unescape(parts[5]) });
        }
    }
    return lib;
}

static void save(const std::string& path, const Library& lib) {
    std::ofstream f(path, std::ios::binary);
    for (const auto& b : lib.books)
        f << "B\t" << b.id << "\t" << escape(b.title) << "\t" << b.updatedAt << "\n";
    for (const auto& v : lib.volumes)
        f << "V\t" << v.id << "\t" << v.bookId << "\t" << escape(v.title) << "\t" << v.order << "\n";
    for (const auto& c : lib.chapters)
        f << "C\t" << c.id << "\t" << c.bookId << "\t" << c.volumeId << "\t"
          << escape(c.title) << "\t" << c.order << "\t" << c.wordCount << "\t"
          << escape(c.text) << "\n";
    for (const auto& e : lib.entities)
        f << "E\t" << e.id << "\t" << e.bookId << "\t" << escape(e.name) << "\t"
          << escape(e.kind) << "\t" << escape(e.description) << "\n";
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
    if (argc < 3) { usage(); return 1; }
    std::string libPath = argv[1];
    std::string cmd = argv[2];
    std::vector<std::string> args(argv + 3, argv + argc);
    Library lib = load(libPath);

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

    save(libPath, lib);
    return 0;
}
