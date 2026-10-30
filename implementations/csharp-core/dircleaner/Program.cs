// DirCleaner 内核版（C# / .NET 8）
//
// 版本：A1_II_Φ8_CSharp_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace DirCleaner;

internal static class Program
{
    private const int MaxRecursionDepth = 20;
    private const int MaxFileCount = 10_000;
    private const int MaxScanForExe = 2_000;
    private const string WhitelistMarkerFilename = ".dircleaner_whitelist";

    private static readonly HashSet<string> CriticalDirNames = new(StringComparer.Ordinal)
    {
        "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
        "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
        "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
    };

    private sealed class Stats
    {
        public int DeletedFiles;
        public int DeletedDirs;
        public long TotalBytes;
        public readonly List<string> Errors = new();
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes == 0) return "0 B";
        string[] units = { "B", "KB", "MB", "GB", "TB" };
        double v = bytes;
        int i = 0;
        while (v >= 1024 && i < units.Length - 1) { v /= 1024; i++; }
        return i == 0 ? $"{v:F0} {units[i]}" : $"{v:F2} {units[i]}";
    }

    private static bool ContainsExecutables(string dir, int depth, ref int counter)
    {
        if (depth > 10 || counter >= MaxScanForExe) return false;
        IEnumerable<string> entries;
        try { entries = Directory.EnumerateFileSystemEntries(dir); }
        catch { return false; }

        foreach (var path in entries)
        {
            if (counter >= MaxScanForExe) break;
            try
            {
                if (Directory.Exists(path))
                {
                    if (ContainsExecutables(path, depth + 1, ref counter)) return true;
                }
                else
                {
                    counter++;
                    var n = Path.GetFileName(path).ToLowerInvariant();
                    if (n.EndsWith(".exe") || n.EndsWith(".dll")) return true;
                }
            }
            catch { /* 忽略无法访问的条目 */ }
        }
        return false;
    }

    private static void ClearDirectory(string dir, int depth, ref int fileCount,
                                       bool keepMarker, bool dryRun, Stats stats)
    {
        if (depth > MaxRecursionDepth)
            throw new InvalidOperationException($"已达到最大目录深度限制 ({MaxRecursionDepth})");

        IEnumerable<string> entries;
        try { entries = Directory.EnumerateFileSystemEntries(dir).ToList(); }
        catch (Exception e) { throw new InvalidOperationException($"无法读取 {dir}: {e.Message}"); }

        foreach (var path in entries)
        {
            var name = Path.GetFileName(path);
            if (Directory.Exists(path))
            {
                ClearDirectory(path, depth + 1, ref fileCount, keepMarker, dryRun, stats);
                if (dryRun)
                {
                    Console.WriteLine($"[dry-run] 将删除目录: {name}");
                    stats.DeletedDirs++;
                }
                else
                {
                    try
                    {
                        Directory.Delete(path);
                        Console.WriteLine($"已删除目录: {name}");
                        stats.DeletedDirs++;
                    }
                    catch (Exception e)
                    {
                        var msg = $"无法删除目录 {name}: {e.Message}";
                        stats.Errors.Add(msg);
                        Console.Error.WriteLine(msg);
                    }
                }
                continue;
            }

            if (fileCount >= MaxFileCount)
                throw new InvalidOperationException($"已达到最大文件数限制 ({MaxFileCount})");

            if (keepMarker && name == WhitelistMarkerFilename)
            {
                Console.WriteLine($"跳过白名单标记文件: {name}");
                continue;
            }

            long size = 0;
            try { size = new FileInfo(path).Length; } catch { /* 忽略 */ }

            if (dryRun)
            {
                Console.WriteLine($"[dry-run] 将删除文件: {name} ({FormatBytes(size)})");
            }
            else
            {
                try
                {
                    File.Delete(path);
                    Console.WriteLine($"已删除文件: {name} ({FormatBytes(size)})");
                }
                catch (Exception e)
                {
                    var msg = $"无法删除 {name}: {e.Message}";
                    stats.Errors.Add(msg);
                    Console.Error.WriteLine(msg);
                    continue;
                }
            }
            stats.DeletedFiles++;
            stats.TotalBytes += size;
            fileCount++;
        }
    }

    private static void Usage()
    {
        Console.WriteLine("DirCleaner 内核版（C#）");
        Console.WriteLine("用法: dircleaner <目录> [选项]");
        Console.WriteLine();
        Console.WriteLine("选项:");
        Console.WriteLine("  --dry-run          只列出将删除的内容，不实际删除");
        Console.WriteLine("  --whitelist        该目录在白名单中（保留标记文件，跳过名称确认）");
        Console.WriteLine("  --confirm <名称>   确认待清空目录的名称（非白名单目录必须提供且一致）");
        Console.WriteLine("  -h, --help         显示本帮助");
    }

    private static int Main(string[] args)
    {
        string? target = null;
        var dryRun = false;
        var inWhitelist = false;
        var confirm = "";

        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--dry-run": dryRun = true; break;
                case "--whitelist": inWhitelist = true; break;
                case "--confirm": if (i + 1 < args.Length) confirm = args[++i]; break;
                case "-h":
                case "--help": Usage(); return 0;
                default:
                    if (!args[i].StartsWith("-") && target is null) target = args[i];
                    break;
            }
        }

        if (target is null) { Usage(); return 1; }
        if (!Directory.Exists(target))
        {
            Console.Error.WriteLine($"错误：{target} 不是目录");
            return 1;
        }

        var dirName = Path.GetFileName(Path.GetFullPath(target).TrimEnd(Path.DirectorySeparatorChar));
        if (CriticalDirNames.Contains(dirName))
        {
            Console.Error.WriteLine($"错误：{dirName} 是受保护的关键目录，禁止清空");
            return 1;
        }
        if (!inWhitelist)
        {
            if (string.IsNullOrEmpty(confirm))
            {
                Console.Error.WriteLine($"错误：非白名单目录必须用 --confirm \"{dirName}\" 确认");
                return 1;
            }
            if (confirm != dirName)
            {
                Console.Error.WriteLine($"错误：确认名称 \"{confirm}\" 与目录名 \"{dirName}\" 不一致");
                return 1;
            }
        }

        var counter = 0;
        if (ContainsExecutables(target, 0, ref counter))
        {
            Console.WriteLine("⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。");
            Console.Write("确认继续？输入 yes: ");
            var ans = Console.ReadLine();
            if (ans?.Trim() != "yes") { Console.WriteLine("已取消。"); return 1; }
        }

        Console.WriteLine("===== 开始清空操作 =====");
        Console.WriteLine($"目标目录: {target}");
        if (dryRun) Console.WriteLine("模式: 试运行（不实际删除）");

        var stats = new Stats();
        var fileCount = 0;
        try
        {
            ClearDirectory(target, 0, ref fileCount, inWhitelist, dryRun, stats);
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"操作中止: {e.Message}");
            Console.WriteLine($"已删除文件: {stats.DeletedFiles}，目录: {stats.DeletedDirs}，释放空间: {FormatBytes(stats.TotalBytes)}");
            return 1;
        }

        Console.WriteLine("===== 清空完成 =====");
        Console.WriteLine($"本次删除文件: {stats.DeletedFiles}");
        Console.WriteLine($"本次删除目录: {stats.DeletedDirs}");
        Console.WriteLine($"本次释放空间: {FormatBytes(stats.TotalBytes)}");
        if (stats.Errors.Count > 0)
        {
            Console.WriteLine($"错误数: {stats.Errors.Count}");
            foreach (var e in stats.Errors) Console.WriteLine("  " + e);
            return 1;
        }
        return 0;
    }
}
