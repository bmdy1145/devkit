// DevKit 内核版（C# / .NET 8）
//
// 版本：A1_V_Φ9_Fix_CSharp_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
// 提示词模板拼接。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace DevKit;

internal static class Program
{
    private const string CurrentVersion = "A1_V_Φ9_Fix_CSharp_CN";

    private sealed record Spec(string Key, string Kind, bool DefBool, string DefStr, string[]? Values);

    private static readonly Spec[] Specs =
    {
        new("performanceMode", "boolean", false, "", null),
        new("shortcutsEnabled", "boolean", true, "", null),
        new("hideBtnText", "boolean", false, "", null),
        new("promptActionsAlways", "boolean", true, "", null),
        new("specPromptEnabled", "boolean", true, "", null),
        new("inspirationSyncEnabled", "boolean", true, "", null),
        new("themePref", "enum", false, "light", new[] { "dark", "light", "auto" }),
    };

    /// 与浏览器版一致：分支代号 + 结构段 + 语言后缀
    private static (string Branch, string Structure, string? Suffix)? ParseVersion(string v)
    {
        if (string.IsNullOrWhiteSpace(v) || v.Length > 100) return null;
        var t = v.Trim();

        var core = t;
        string? suffix = null;
        if (t.EndsWith("_CN")) { core = t[..^3]; suffix = "CN"; }
        else if (t.EndsWith("_GLOBAL")) { core = t[..^7]; suffix = "GLOBAL"; }

        var parts = core.Split('_');
        if (parts.Length == 0) return null;
        var branch = parts[0];
        if (branch.Length == 0 || branch[0] != 'A') return null;
        if (branch.Length > 1 && !branch[1..].All(char.IsDigit)) return null;

        return (branch, string.Join("_", parts.Skip(1)), suffix);
    }

    private static bool IsCompatible(string v)
    {
        var p = ParseVersion(v);
        if (p is null) return false;
        var (branch, structure, _) = p.Value;
        if (branch.StartsWith("A2")) return false;
        if (structure.Split('_').Contains("A2")) return false;
        return true;
    }

    private static Dictionary<string, object> NormalizeSettings(JsonElement src)
    {
        var outDict = new Dictionary<string, object>();
        foreach (var s in Specs)
        {
            JsonElement val = default;
            var has = src.ValueKind == JsonValueKind.Object && src.TryGetProperty(s.Key, out val);
            if (s.Kind == "boolean")
            {
                if (has && (val.ValueKind == JsonValueKind.True || val.ValueKind == JsonValueKind.False))
                    outDict[s.Key] = val.GetBoolean();
                else outDict[s.Key] = s.DefBool;
            }
            else if (s.Kind == "enum")
            {
                if (has && val.ValueKind == JsonValueKind.String && s.Values!.Contains(val.GetString()))
                    outDict[s.Key] = val.GetString()!;
                else outDict[s.Key] = s.DefStr;
            }
        }
        return outDict;
    }

    private static (int Count, string? Error) ValidateImport(JsonElement data)
    {
        if (data.ValueKind != JsonValueKind.Object) return (0, "格式错误：不是有效对象");
        if (!data.TryGetProperty("projects", out var projects))
        {
            if (data.TryGetProperty("project", out _)) return (1, null);
            return (0, "格式错误：不是有效对象");
        }
        if (projects.ValueKind != JsonValueKind.Array) return (0, "格式错误：projects 不是数组");
        if (projects.GetArrayLength() > 20) return (0, $"项目数 {projects.GetArrayLength()} 超过上限 20");

        var i = 0;
        foreach (var p in projects.EnumerateArray())
        {
            i++;
            if (p.ValueKind != JsonValueKind.Object) return (0, $"第 {i} 个项目不是对象");
            if (!p.TryGetProperty("id", out var id) || id.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(id.GetString()))
                return (0, $"第 {i} 个项目缺少 id");
            if (!p.TryGetProperty("name", out var name) || name.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(name.GetString()))
                return (0, $"第 {i} 个项目缺少 name");
            if (!p.TryGetProperty("tabs", out var tabs) || tabs.ValueKind != JsonValueKind.Array)
                return (0, $"第 {i} 个项目缺少 tabs");
            if (tabs.GetArrayLength() > 50) return (0, $"第 {i} 个项目页签超过 50");

            var j = 0;
            foreach (var t in tabs.EnumerateArray())
            {
                j++;
                if (t.ValueKind != JsonValueKind.Object) return (0, $"第 {i} 个项目第 {j} 个页签不是对象");
                if (!t.TryGetProperty("id", out var tid) || tid.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(tid.GetString()))
                    return (0, $"第 {i} 个项目第 {j} 个页签字段不完整");
                if (!t.TryGetProperty("name", out var tname) || tname.ValueKind != JsonValueKind.String || string.IsNullOrEmpty(tname.GetString()))
                    return (0, $"第 {i} 个项目第 {j} 个页签字段不完整");
            }
        }
        return (projects.GetArrayLength(), null);
    }

    private static void Usage()
    {
        Console.WriteLine("DevKit 内核版（C#）");
        Console.WriteLine("用法: devkit <子命令> [参数]");
        Console.WriteLine();
        Console.WriteLine("子命令:");
        Console.WriteLine("  version");
        Console.WriteLine("  parse-version <版本号>");
        Console.WriteLine("  check-version <版本号>");
        Console.WriteLine("  validate-config <配置文件>");
        Console.WriteLine("  normalize <设置JSON>");
        Console.WriteLine("  compose <模板文件> <灵感> [代码文件]");
    }

    private static int Main(string[] args)
    {
        if (args.Length == 0) { Usage(); return 1; }

        switch (args[0])
        {
            case "version":
                Console.WriteLine(CurrentVersion);
                return 0;

            case "parse-version":
            {
                if (args.Length < 2) { Console.Error.WriteLine("缺少版本号"); return 1; }
                var p = ParseVersion(args[1]);
                if (p is null) { Console.Error.WriteLine("版本号不合规"); return 1; }
                var (branch, structure, suffix) = p.Value;
                Console.WriteLine($"分支: {branch}");
                Console.WriteLine($"结构段: {(structure.Length == 0 ? "（无）" : structure)}");
                Console.WriteLine($"语言后缀: {suffix ?? "（无）"}");
                return 0;
            }

            case "check-version":
            {
                if (args.Length < 2) { Console.Error.WriteLine("缺少版本号"); return 1; }
                var ok = IsCompatible(args[1]);
                Console.WriteLine(ok ? "兼容" : "不兼容");
                return ok ? 0 : 1;
            }

            case "validate-config":
            {
                if (args.Length < 2) { Console.Error.WriteLine("缺少配置文件路径"); return 1; }
                JsonElement data;
                try
                {
                    using var doc = JsonDocument.Parse(File.ReadAllText(args[1], Encoding.UTF8));
                    data = doc.RootElement.Clone();
                }
                catch (Exception e) { Console.Error.WriteLine($"读取或解析失败: {e.Message}"); return 1; }

                if (data.TryGetProperty("version", out var ver) && ver.ValueKind == JsonValueKind.String)
                {
                    var v = ver.GetString()!;
                    if (!IsCompatible(v)) { Console.Error.WriteLine($"配置文件版本不兼容: {v}"); return 1; }
                }
                var (n, err) = ValidateImport(data);
                if (err is not null) { Console.Error.WriteLine(err); return 1; }
                Console.WriteLine($"校验通过，项目数: {n}");
                return 0;
            }

            case "normalize":
            {
                if (args.Length < 2) { Console.Error.WriteLine("缺少设置 JSON"); return 1; }
                JsonElement src;
                try
                {
                    using var doc = JsonDocument.Parse(args[1]);
                    src = doc.RootElement.Clone();
                }
                catch (Exception e) { Console.Error.WriteLine($"JSON 解析失败: {e.Message}"); return 1; }
                var outDict = NormalizeSettings(src);
                Console.WriteLine(JsonSerializer.Serialize(outDict, new JsonSerializerOptions { WriteIndented = true }));
                return 0;
            }

            case "compose":
            {
                if (args.Length < 3) { Console.Error.WriteLine("用法: compose <模板文件> <灵感> [代码文件]"); return 1; }
                string tpl;
                try { tpl = File.ReadAllText(args[1], Encoding.UTF8); }
                catch (Exception e) { Console.Error.WriteLine($"读取模板失败: {e.Message}"); return 1; }
                var code = "（无代码）";
                if (args.Length >= 4 && File.Exists(args[3])) code = File.ReadAllText(args[3], Encoding.UTF8);
                Console.Write(tpl.Replace("{inspiration}", args[2]).Replace("{code}", code));
                return 0;
            }

            default:
                Console.Error.WriteLine($"未知子命令: {args[0]}");
                Usage();
                return 1;
        }
    }
}
