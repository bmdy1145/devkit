// SubMerge Pro 内核版（C# / .NET 8）
//
// 版本：A1_II_Φ10_CSharp_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace SubMerge;

internal sealed class Entry
{
    public int Index { get; set; }
    public string Start { get; set; } = "";
    public string End { get; set; } = "";
    public string Text { get; set; } = "";
    public string? Translated { get; set; }
}

internal static class Program
{
    private static readonly Regex CjkSplit = new(@"([\u4e00-\u9fff]+)", RegexOptions.Compiled);
    private static readonly Regex CjkTest = new(@"[\u4e00-\u9fff]", RegexOptions.Compiled);
    private static readonly Regex WordRe = new(@"[A-Za-z0-9]+(?:'[A-Za-z]+)?", RegexOptions.Compiled);
    private static readonly Regex TokenRe = new(@"[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S", RegexOptions.Compiled);
    private static readonly Regex TimeRe = new(
        @"^(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})$",
        RegexOptions.Compiled);
    private static readonly Regex IdxRe = new(@"^\[(\d+)\]\s*(.*)$", RegexOptions.Compiled);

    private static bool IsCjk(char c) => c >= '\u4e00' && c <= '\u9fff';

    // 仅 ASCII 字母数字。不能直接用 char.IsLetterOrDigit：它把汉字也算作字母，
    // 会让 AddBoundary 在「中中」之间也插空格。
    private static bool IsAsciiAlnum(char c) =>
        (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');

    private static int CountWords(string text)
    {
        if (string.IsNullOrEmpty(text)) return 0;
        var total = 0;
        foreach (var seg in CjkSplit.Split(text))
        {
            if (seg.Length == 0) continue;
            if (CjkTest.IsMatch(seg)) total += (seg.Length + 1) / 2;
            else total += WordRe.Matches(seg).Count;
        }
        return total;
    }

    private static List<string> Tokenize(string text)
    {
        var tokens = new List<string>();
        foreach (var seg in CjkSplit.Split(text))
        {
            if (seg.Length == 0) continue;
            if (CjkTest.IsMatch(seg))
            {
                for (var i = 0; i < seg.Length; i += 2)
                    tokens.Add(seg.Substring(i, Math.Min(2, seg.Length - i)));
            }
            else
            {
                // 与 HTML 参考实现一致：[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S
                var matches = TokenRe.Matches(seg);
                tokens.AddRange(matches.Select(m => m.Value));
            }
        }
        return tokens;
    }

    private static string JoinTokens(List<string> tokens)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < tokens.Count; i++)
        {
            if (i > 0 && !IsCjk(tokens[i - 1][^1]) && !IsCjk(tokens[i][0])) sb.Append(' ');
            sb.Append(tokens[i]);
        }
        return sb.ToString();
    }

    private static string AddBoundary(string s)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < s.Length; i++)
        {
            if (i > 0)
            {
                var p = s[i - 1];
                var c = s[i];
                if ((IsAsciiAlnum(p) && IsCjk(c)) || (IsCjk(p) && IsAsciiAlnum(c)))
                    sb.Append(' ');
            }
            sb.Append(s[i]);
        }
        return sb.ToString();
    }

    private static List<(string Orig, string Trans)> SplitPaired(string orig, string trans, int maxWords)
    {
        var o = Tokenize(orig);
        var t = Tokenize(trans);
        var chunks = new List<(string, string)>();
        var oi = 0;
        var ti = 0;
        while (oi < o.Count || ti < t.Count)
        {
            var oc = new List<string>();
            var tc = new List<string>();
            var words = 0;
            while ((oi < o.Count || ti < t.Count) && words < maxWords)
            {
                var canO = oi < o.Count;
                var canT = ti < t.Count;
                if (canO && canT)
                {
                    if (words + 2 <= maxWords) { oc.Add(o[oi++]); tc.Add(t[ti++]); words += 2; }
                    else break;
                }
                else if (canO)
                {
                    if (words + 1 <= maxWords) { oc.Add(o[oi++]); words++; } else break;
                }
                else if (canT)
                {
                    if (words + 1 <= maxWords) { tc.Add(t[ti++]); words++; } else break;
                }
            }
            chunks.Add((AddBoundary(JoinTokens(oc)).Trim(), AddBoundary(JoinTokens(tc)).Trim()));
        }
        if (chunks.Count == 0) chunks.Add((orig, trans));
        return chunks;
    }

    private static long TimeToMs(string s)
    {
        var parts = s.Split(':');
        if (parts.Length != 3) return 0;
        var h = long.Parse(parts[0], CultureInfo.InvariantCulture);
        var m = long.Parse(parts[1], CultureInfo.InvariantCulture);
        var sp = parts[2];
        long sec, ms;
        var comma = sp.IndexOf(',');
        var dot = sp.IndexOf('.');
        if (comma >= 0)
        {
            sec = long.Parse(sp[..comma], CultureInfo.InvariantCulture);
            ms = long.Parse(sp[(comma + 1)..].PadRight(3, '0')[..3], CultureInfo.InvariantCulture);
        }
        else if (dot >= 0)
        {
            sec = long.Parse(sp[..dot], CultureInfo.InvariantCulture);
            var frames = double.Parse(sp[(dot + 1)..].PadRight(2, '0')[..2], CultureInfo.InvariantCulture);
            ms = (long)Math.Round(frames * 40);
        }
        else
        {
            sec = long.Parse(sp, CultureInfo.InvariantCulture);
            ms = 0;
        }
        return (h * 3600 + m * 60 + sec) * 1000 + ms;
    }

    private static string MsToTime(long ms)
    {
        var h = ms / 3_600_000; ms %= 3_600_000;
        var m = ms / 60_000; ms %= 60_000;
        var s = ms / 1000;
        return $"{h:00}:{m:00}:{s:00},{ms % 1000:000}";
    }

    private static List<Entry> ParseSubtitle(string content)
    {
        var clean = content.TrimStart('\uFEFF').Replace("\r\n", "\n").Replace('\r', '\n');
        var entries = new List<Entry>();
        var seen = new HashSet<int>();
        foreach (var raw in Regex.Split(clean, @"\n\s*\n"))
        {
            var lines = raw.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).ToList();
            if (lines.Count < 3 || !lines[0].All(char.IsDigit)) continue;
            var m = TimeRe.Match(lines[1]);
            if (!m.Success) continue;
            var idx = int.Parse(lines[0], CultureInfo.InvariantCulture);
            if (!seen.Add(idx)) continue;
            var start = m.Groups[1].Value.Replace('.', ',');
            var end = m.Groups[2].Value.Replace('.', ',');
            if (TimeToMs(start) >= TimeToMs(end)) end = MsToTime(TimeToMs(start) + 1);
            var text = string.Join("\n", lines.Skip(2)).Trim();
            if (text.Length == 0) continue;
            entries.Add(new Entry { Index = idx, Start = start, End = end, Text = text });
        }
        return entries.OrderBy(e => e.Index).ToList();
    }

    private static List<Entry> ApplyTimeFix(List<Entry> entries, string strategy)
    {
        if (strategy == "keep" || strategy.Length == 0) return entries;
        if (strategy == "delete")
            return entries.Where(e => TimeToMs(e.End) - TimeToMs(e.Start) >= 10).ToList();
        if (strategy == "extend")
        {
            for (var i = 0; i < entries.Count; i++)
            {
                var s = TimeToMs(entries[i].Start);
                var e = TimeToMs(entries[i].End);
                if (e - s < 10)
                {
                    var newEnd = s + 10;
                    entries[i].End = MsToTime(newEnd);
                    var shift = newEnd - e;
                    for (var j = i + 1; j < entries.Count; j++)
                    {
                        entries[j].Start = MsToTime(TimeToMs(entries[j].Start) + shift);
                        entries[j].End = MsToTime(TimeToMs(entries[j].End) + shift);
                    }
                }
            }
        }
        return entries;
    }

    private static int ApplyTranslation(List<Entry> entries, string transStr)
    {
        var map = new Dictionary<int, string>();
        int? cur = null;
        var buf = new List<string>();

        void Flush() { if (cur is not null) map[cur.Value] = string.Join("\n", buf).Trim(); }

        foreach (var line in transStr.Split('\n'))
        {
            var t = line.Trim();
            var m = IdxRe.Match(t);
            if (m.Success)
            {
                Flush();
                cur = int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
                buf.Clear();
                var rest = m.Groups[2].Value.Trim();
                if (rest.Length > 0) buf.Add(rest);
                continue;
            }
            if (cur is not null && t.Length > 0) buf.Add(t);
        }
        Flush();

        var applied = 0;
        foreach (var e in entries)
        {
            if (map.TryGetValue(e.Index, out var tr)) { e.Translated = tr; applied++; }
        }
        return applied;
    }

    private static string ExportSrt(List<Entry> entries, string mode)
    {
        var sb = new StringBuilder();
        foreach (var e in entries)
        {
            string text;
            if (mode == "orig") text = e.Text;
            else if (mode == "trans") text = e.Translated ?? "";
            else
            {
                if (e.Translated is not null && e.Text.Length > 0) text = e.Text + "\n" + e.Translated;
                else if (e.Translated is not null) text = e.Translated;
                else text = e.Text;
            }
            sb.Append($"{e.Index}\n{e.Start} --> {e.End}\n{text}\n\n");
        }
        return sb.ToString();
    }

    private static void Usage()
    {
        Console.WriteLine("SubMerge Pro 内核版（C#）");
        Console.WriteLine("用法:");
        Console.WriteLine("  submerge parse <字幕文件>");
        Console.WriteLine("  submerge export <字幕文件> [--trans 译文] [--mode both|orig|trans] [--time-fix keep|delete|extend]");
        Console.WriteLine("  submerge merge-prompt <字幕文件> [--trans 译文] [--max N]");
    }

    private static int Main(string[] args)
    {
        if (args.Length == 0) { Usage(); return 1; }
        var cmd = args[0];
        if (cmd is "-h" or "--help") { Usage(); return 0; }

        string? file = null, transFile = null;
        var mode = "both";
        var timeFix = "keep";
        var maxWords = 10;

        for (var i = 1; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--trans" when i + 1 < args.Length: transFile = args[++i]; break;
                case "--mode" when i + 1 < args.Length: mode = args[++i]; break;
                case "--time-fix" when i + 1 < args.Length: timeFix = args[++i]; break;
                case "--max" when i + 1 < args.Length:
                    maxWords = int.Parse(args[++i], CultureInfo.InvariantCulture); break;
                default:
                    if (!args[i].StartsWith("--") && file is null) file = args[i];
                    break;
            }
        }

        if (file is null) { Console.Error.WriteLine("错误：未指定字幕文件"); return 1; }
        if (!File.Exists(file)) { Console.Error.WriteLine($"无法读取 {file}"); return 1; }

        var entries = ParseSubtitle(File.ReadAllText(file, Encoding.UTF8));
        if (entries.Count == 0) { Console.Error.WriteLine("解析失败：未找到字幕条目"); return 1; }
        entries = ApplyTimeFix(entries, timeFix);

        if (transFile is not null)
        {
            if (!File.Exists(transFile)) { Console.Error.WriteLine($"无法读取 {transFile}"); return 1; }
            var n = ApplyTranslation(entries, File.ReadAllText(transFile, Encoding.UTF8));
            Console.WriteLine($"已应用 {n} 条译文");
        }

        switch (cmd)
        {
            case "parse":
                var total = entries.Sum(e => CountWords(e.Text));
                Console.WriteLine($"条目数: {entries.Count}");
                Console.WriteLine($"总词数: {total}");
                var f = entries[0];
                var l = entries[^1];
                Console.WriteLine($"首条: [{f.Index}] {f.Start} --> {f.End} | {f.Text}");
                Console.WriteLine($"末条: [{l.Index}] {l.Start} --> {l.End} | {l.Text}");
                return 0;
            case "export":
                Console.Write(ExportSrt(entries, mode));
                return 0;
            case "merge-prompt":
                foreach (var e in entries)
                {
                    foreach (var (o, t) in SplitPaired(e.Text, e.Translated ?? "", maxWords))
                    {
                        var body = t.Length == 0 ? o : o + "\n" + t;
                        Console.WriteLine($"[{e.Index}] {body.Trim()}");
                    }
                }
                return 0;
            default:
                Console.Error.WriteLine($"错误：未知子命令 {cmd}");
                Usage();
                return 1;
        }
    }
}
