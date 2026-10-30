// Writer 内核版（C# / .NET 8）
//
// 版本：A1_I_Φ3_CSharp_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//
// 只实现纯逻辑内核：书籍 / 卷 / 章节结构、字数统计、章节排序、
// 跨卷移动、引用管理、提示词模板合成。
//
// 存储格式与 C++ 版一致（TAB 分隔的纯文本，字段与浏览器版一一对应）。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace Writer;

internal sealed class Book { public string Id = "", Title = ""; public long UpdatedAt; }
internal sealed class Volume { public string Id = "", BookId = "", Title = ""; public int Order; }
internal sealed class Chapter
{
    public string Id = "", BookId = "", VolumeId = "", Title = "", Text = "";
    public int Order;
    public long WordCount;
}
internal sealed class Entity { public string Id = "", BookId = "", Name = "", Kind = "", Description = ""; }

internal sealed class Library
{
    public List<Book> Books = new();
    public List<Volume> Volumes = new();
    public List<Chapter> Chapters = new();
    public List<Entity> Entities = new();
}

internal static class Program
{
    private static long _counter;

    private static long NowTs() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    private static string GenId(string prefix) => $"{prefix}_{NowTs()}_{++_counter}";

    private static bool IsCjk(int cp) =>
        (cp >= 0x3400 && cp <= 0x4DBF) || (cp >= 0x4E00 && cp <= 0x9FFF) ||
        (cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0xAC00 && cp <= 0xD7AF) ||
        (cp >= 0xF900 && cp <= 0xFAFF);

    /// 与浏览器版一致：CJK 每字算 1 词，拉丁词按整词算。
    private static long CountWords(string text)
    {
        if (string.IsNullOrEmpty(text)) return 0;
        long total = 0;
        var inLatin = false;
        foreach (var ch in text)
        {
            if (IsCjk(ch)) { total++; inLatin = false; }
            else if (char.IsLetterOrDigit(ch))
            {
                if (!inLatin) { total++; inLatin = true; }
            }
            else inLatin = false;
        }
        return total;
    }

    private static string Escape(string s) =>
        s.Replace("\\", "\\\\").Replace("\t", "\\t").Replace("\n", "\\n").Replace("\r", "");

    private static string Unescape(string s)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < s.Length; i++)
        {
            if (s[i] == '\\' && i + 1 < s.Length)
            {
                var n = s[++i];
                sb.Append(n switch { 't' => '\t', 'n' => '\n', _ => n });
            }
            else sb.Append(s[i]);
        }
        return sb.ToString();
    }

    private static Library Load(string path)
    {
        var lib = new Library();
        if (!File.Exists(path)) return lib;
        foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
        {
            if (line.Length == 0) continue;
            var p = line.Split('\t');
            switch (p[0])
            {
                case "B" when p.Length >= 4:
                    lib.Books.Add(new Book { Id = p[1], Title = Unescape(p[2]), UpdatedAt = long.Parse(p[3], CultureInfo.InvariantCulture) });
                    break;
                case "V" when p.Length >= 5:
                    lib.Volumes.Add(new Volume { Id = p[1], BookId = p[2], Title = Unescape(p[3]), Order = int.Parse(p[4], CultureInfo.InvariantCulture) });
                    break;
                case "C" when p.Length >= 8:
                    lib.Chapters.Add(new Chapter
                    {
                        Id = p[1], BookId = p[2], VolumeId = p[3], Title = Unescape(p[4]),
                        Order = int.Parse(p[5], CultureInfo.InvariantCulture),
                        WordCount = long.Parse(p[6], CultureInfo.InvariantCulture),
                        Text = Unescape(p[7]),
                    });
                    break;
                case "E" when p.Length >= 6:
                    lib.Entities.Add(new Entity
                    {
                        Id = p[1], BookId = p[2], Name = Unescape(p[3]),
                        Kind = Unescape(p[4]), Description = Unescape(p[5]),
                    });
                    break;
            }
        }
        return lib;
    }

    private static void Save(string path, Library lib)
    {
        var sb = new StringBuilder();
        foreach (var b in lib.Books)
            sb.Append($"B\t{b.Id}\t{Escape(b.Title)}\t{b.UpdatedAt}\n");
        foreach (var v in lib.Volumes)
            sb.Append($"V\t{v.Id}\t{v.BookId}\t{Escape(v.Title)}\t{v.Order}\n");
        foreach (var c in lib.Chapters)
            sb.Append($"C\t{c.Id}\t{c.BookId}\t{c.VolumeId}\t{Escape(c.Title)}\t{c.Order}\t{c.WordCount}\t{Escape(c.Text)}\n");
        foreach (var e in lib.Entities)
            sb.Append($"E\t{e.Id}\t{e.BookId}\t{Escape(e.Name)}\t{Escape(e.Kind)}\t{Escape(e.Description)}\n");
        File.WriteAllText(path, sb.ToString(), new UTF8Encoding(false));
    }

    private static List<Chapter> ChaptersOf(Library lib, string volId) =>
        lib.Chapters.Where(c => c.VolumeId == volId).OrderBy(c => c.Order).ToList();

    private static void ReorderVolume(Library lib, string volId)
    {
        var list = ChaptersOf(lib, volId);
        for (var i = 0; i < list.Count; i++) list[i].Order = i;
    }

    private static void Usage()
    {
        Console.WriteLine("Writer 内核版（C#）");
        Console.WriteLine("用法: writer <库文件> <子命令> [参数]");
        Console.WriteLine();
        Console.WriteLine("子命令:");
        Console.WriteLine("  init <书名>");
        Console.WriteLine("  add-volume <书籍ID> <卷名>");
        Console.WriteLine("  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]");
        Console.WriteLine("  list <书籍ID>");
        Console.WriteLine("  stats <书籍ID>");
        Console.WriteLine("  move-chapter <章节ID> <目标卷ID>");
        Console.WriteLine("  add-entity <书籍ID> <名称> [类型] [描述]");
        Console.WriteLine("  prompt <书籍ID> <章节ID>");
        Console.WriteLine("  reindex <书籍ID>");
    }

    private static int Main(string[] args)
    {
        if (args.Length < 2) { Usage(); return 1; }
        var libPath = args[0];
        var cmd = args[1];
        var rest = args.Skip(2).ToArray();
        var lib = Load(libPath);

        switch (cmd)
        {
            case "init":
                if (rest.Length < 1) { Console.Error.WriteLine("缺少书名"); return 1; }
                {
                    var b = new Book { Id = GenId("book"), Title = rest[0], UpdatedAt = NowTs() };
                    Console.WriteLine($"已创建书籍: {b.Title} ({b.Id})");
                    lib.Books.Add(b);
                }
                break;

            case "add-volume":
                if (rest.Length < 2) { Console.Error.WriteLine("缺少参数"); return 1; }
                if (!lib.Books.Any(b => b.Id == rest[0])) { Console.Error.WriteLine($"找不到书籍 {rest[0]}"); return 1; }
                {
                    var order = lib.Volumes.Count(v => v.BookId == rest[0]);
                    var v = new Volume { Id = GenId("vol"), BookId = rest[0], Title = rest[1], Order = order };
                    Console.WriteLine($"已新增卷: {v.Title} ({v.Id})");
                    lib.Volumes.Add(v);
                }
                break;

            case "add-chapter":
                if (rest.Length < 3) { Console.Error.WriteLine("缺少参数"); return 1; }
                {
                    var text = rest.Length >= 4 && File.Exists(rest[3])
                        ? File.ReadAllText(rest[3], Encoding.UTF8) : "";
                    if (!lib.Volumes.Any(v => v.Id == rest[1])) { Console.Error.WriteLine($"找不到卷 {rest[1]}"); return 1; }
                    var order = lib.Chapters.Count(c => c.VolumeId == rest[1]);
                    var wc = CountWords(text);
                    var ch = new Chapter
                    {
                        Id = GenId("ch"), BookId = rest[0], VolumeId = rest[1],
                        Title = rest[2], Order = order, WordCount = wc, Text = text,
                    };
                    Console.WriteLine($"已新增章节: {ch.Title} ({ch.Id}) · {wc} 字");
                    lib.Chapters.Add(ch);
                }
                break;

            case "list":
                if (rest.Length < 1) { Console.Error.WriteLine("缺少书籍ID"); return 1; }
                {
                    var book = lib.Books.FirstOrDefault(b => b.Id == rest[0]);
                    if (book is null) { Console.Error.WriteLine("找不到书籍"); return 1; }
                    Console.WriteLine($"书籍: {book.Title} ({book.Id})");
                    foreach (var v in lib.Volumes.Where(v => v.BookId == book.Id).OrderBy(v => v.Order))
                    {
                        Console.WriteLine($"  卷: {v.Title} (order {v.Order})");
                        foreach (var c in ChaptersOf(lib, v.Id))
                            Console.WriteLine($"    - [{c.Order}] {c.Title} · {c.WordCount} 字");
                    }
                }
                break;

            case "stats":
                if (rest.Length < 1) { Console.Error.WriteLine("缺少书籍ID"); return 1; }
                {
                    var chs = lib.Chapters.Where(c => c.BookId == rest[0]).ToList();
                    Console.WriteLine($"章节数: {chs.Count}");
                    Console.WriteLine($"总字数: {chs.Sum(c => c.WordCount)}");
                    Console.WriteLine($"总字符: {chs.Sum(c => (long)c.Text.Length)}");
                }
                break;

            case "move-chapter":
                if (rest.Length < 2) { Console.Error.WriteLine("缺少参数"); return 1; }
                {
                    var ch = lib.Chapters.FirstOrDefault(c => c.Id == rest[0]);
                    if (ch is null) { Console.Error.WriteLine("找不到章节"); return 1; }
                    if (!lib.Volumes.Any(v => v.Id == rest[1])) { Console.Error.WriteLine($"找不到目标卷 {rest[1]}"); return 1; }
                    var sourceVol = ch.VolumeId;
                    ch.VolumeId = rest[1];
                    ch.Order = lib.Chapters.Count(c => c.VolumeId == rest[1]);
                    ReorderVolume(lib, rest[1]);
                    ReorderVolume(lib, sourceVol);
                    Console.WriteLine("已将章节移至目标卷，并重排源卷与目标卷的顺序");
                }
                break;

            case "add-entity":
                if (rest.Length < 2) { Console.Error.WriteLine("缺少参数"); return 1; }
                {
                    var e = new Entity
                    {
                        Id = GenId("ent"), BookId = rest[0], Name = rest[1],
                        Kind = rest.Length >= 3 ? rest[2] : "其他",
                        Description = rest.Length >= 4 ? rest[3] : "",
                    };
                    Console.WriteLine($"已添加资料: {e.Name} ({e.Id})");
                    lib.Entities.Add(e);
                }
                break;

            case "prompt":
                if (rest.Length < 2) { Console.Error.WriteLine("缺少参数"); return 1; }
                {
                    var ch = lib.Chapters.FirstOrDefault(c => c.Id == rest[1]);
                    if (ch is null) { Console.Error.WriteLine("找不到章节"); return 1; }
                    var list = ChaptersOf(lib, ch.VolumeId);
                    var pos = list.FindIndex(c => c.Id == rest[1]);
                    var prev = pos > 0
                        ? (list[pos - 1].Text.Length > 500 ? list[pos - 1].Text[^500..] : list[pos - 1].Text)
                        : "（本章为卷首，无上一章）";
                    var ents = lib.Entities.Where(e => e.BookId == rest[0]).ToList();
                    var chars = ents.Count > 0
                        ? string.Join("\n", ents.Select(e => $"- {e.Name}（{e.Kind}）：{e.Description}"))
                        : "（未填写）";
                    Console.WriteLine("你是一位与作者合写的小说作者。请续写下一段情节。");
                    Console.WriteLine();
                    Console.WriteLine("【设定】");
                    Console.WriteLine(chars);
                    Console.WriteLine("【上一章结尾】");
                    Console.WriteLine(prev);
                    Console.WriteLine();
                    Console.WriteLine("【本章已有正文】");
                    Console.WriteLine(string.IsNullOrEmpty(ch.Text) ? "（当前章为空）" : ch.Text);
                }
                break;

            case "reindex":
                if (rest.Length < 1) { Console.Error.WriteLine("缺少书籍ID"); return 1; }
                foreach (var v in lib.Volumes.Where(v => v.BookId == rest[0]).ToList())
                    ReorderVolume(lib, v.Id);
                Console.WriteLine("已重排全部卷的章节顺序");
                break;

            default:
                Console.Error.WriteLine($"未知子命令: {cmd}");
                return 1;
        }

        Save(libPath, lib);
        return 0;
    }
}
