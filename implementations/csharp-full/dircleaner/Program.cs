// DirCleaner 全功能版（C# / WinForms）
//
// 版本：A1_II_Φ8_CSharp_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 图形界面版：目录选择、关键目录防护、白名单、可执行文件扫描、
// 名称确认、进度与统计，与浏览器版一一对应。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace DirCleanerGui;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private const int MaxRecursionDepth = 20;
    private const int MaxFileCount = 10_000;
    private const int MaxScanForExe = 2_000;
    private const string WhitelistMarker = ".dircleaner_whitelist";

    private static readonly HashSet<string> CriticalNames = new(StringComparer.Ordinal)
    {
        "Windows", "System32", "SysWOW64", "Program Files", "Program Files (x86)",
        "Users", "Documents and Settings", "bin", "sbin", "etc", "dev", "proc", "sys",
        "boot", "root", "home", "var", "tmp", "Volumes", "Applications", "Library",
    };

    private string? _target;
    private bool _exeFound;
    private bool _cancelled;

    private readonly Label _pathLabel = new() { Text = "（未选择）", AutoSize = true, ForeColor = Color.DimGray };
    private readonly Label _criticalLabel = new() { Text = "请先选择目录", AutoSize = true };
    private readonly Label _exeLabel = new() { Text = "", AutoSize = true, ForeColor = Color.DarkOrange };
    private readonly Label _statusLabel = new() { Text = "就绪", AutoSize = true };
    private readonly CheckBox _confirmCheck = new() { Text = "我了解此操作不可恢复", AutoSize = true };
    private readonly TextBox _nameBox = new() { Width = 240, Enabled = false };
    private readonly CheckBox _exeCheck = new() { Text = "该目录含可执行文件，我了解风险仍要删除", AutoSize = true, Visible = false };
    private readonly Button _startBtn = new() { Text = "开始清空", Enabled = false, AutoSize = true };
    private readonly Button _cancelBtn = new() { Text = "取消", Enabled = false, AutoSize = true };
    private readonly ProgressBar _progress = new() { Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 0, Height = 18 };
    private readonly TextBox _log = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Height = 160 };
    private readonly Label _statFiles = new() { Text = "-", AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold) };
    private readonly Label _statDirs = new() { Text = "-", AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold) };
    private readonly Label _statSize = new() { Text = "-", AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold) };
    private readonly Label _statErrors = new() { Text = "-", AutoSize = true, Font = new Font("Segoe UI", 14, FontStyle.Bold) };
    private readonly Label _wlLabel = new() { Text = "", AutoSize = true, ForeColor = Color.SeaGreen };

    public MainForm()
    {
        Text = "DirCleaner（C# WinForms 版）";
        Width = 820;
        Height = 760;
        StartPosition = FormStartPosition.CenterScreen;

        var chooseBtn = new Button { Text = "浏览目录…", AutoSize = true };
        chooseBtn.Click += (_, _) => ChooseDir();
        var wlBtn = new Button { Text = "加入白名单", AutoSize = true };
        wlBtn.Click += (_, _) => AddWhitelist();
        var scanBtn = new Button { Text = "扫描可执行文件", AutoSize = true };
        scanBtn.Click += (_, _) => ScanExe();

        _confirmCheck.CheckedChanged += (_, _) => UpdateStart();
        _exeCheck.CheckedChanged += (_, _) => UpdateStart();
        _nameBox.TextChanged += (_, _) => UpdateStart();
        _startBtn.Click += (_, _) => StartClear();
        _cancelBtn.Click += (_, _) => { _cancelled = true; _statusLabel.Text = "正在取消…"; };

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            AutoScroll = true,
            Padding = new Padding(10),
        };

        root.Controls.Add(Section("1. 选择目录"));
        root.Controls.Add(_pathLabel);
        var row1 = new FlowLayoutPanel { AutoSize = true };
        row1.Controls.AddRange(new Control[] { chooseBtn, wlBtn, _wlLabel });
        root.Controls.Add(row1);

        root.Controls.Add(Section("2. 安全检查"));
        root.Controls.Add(_criticalLabel);
        root.Controls.Add(_exeLabel);
        root.Controls.Add(scanBtn);

        root.Controls.Add(Section("3. 确认"));
        root.Controls.Add(_confirmCheck);
        var nameRow = new FlowLayoutPanel { AutoSize = true };
        nameRow.Controls.Add(new Label { Text = "输入目录名确认：", AutoSize = true });
        nameRow.Controls.Add(_nameBox);
        root.Controls.Add(nameRow);
        root.Controls.Add(_exeCheck);

        var actionRow = new FlowLayoutPanel { AutoSize = true };
        actionRow.Controls.AddRange(new Control[] { _startBtn, _cancelBtn });
        root.Controls.Add(actionRow);
        root.Controls.Add(_progress);

        root.Controls.Add(Section("4. 统计"));
        var statsRow = new TableLayoutPanel { ColumnCount = 4, AutoSize = true, Dock = DockStyle.Top };
        statsRow.Controls.Add(WrapStat(_statFiles, "文件"), 0, 0);
        statsRow.Controls.Add(WrapStat(_statDirs, "目录"), 1, 0);
        statsRow.Controls.Add(WrapStat(_statSize, "大小"), 2, 0);
        statsRow.Controls.Add(WrapStat(_statErrors, "错误"), 3, 0);
        root.Controls.Add(statsRow);
        root.Controls.Add(_statusLabel);

        root.Controls.Add(Section("5. 日志"));
        _log.Dock = DockStyle.Fill;
        root.Controls.Add(_log);

        Controls.Add(root);
    }

    private static Label Section(string text) => new()
    {
        Text = text,
        AutoSize = true,
        Font = new Font("Segoe UI", 9, FontStyle.Bold),
        Margin = new Padding(0, 10, 0, 2),
    };

    private static Control WrapStat(Label value, string caption)
    {
        var panel = new FlowLayoutPanel { FlowDirection = FlowDirection.TopDown, AutoSize = true };
        panel.Controls.Add(value);
        panel.Controls.Add(new Label { Text = caption, AutoSize = true, ForeColor = Color.Gray });
        return panel;
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

    private void Log(string msg)
    {
        if (_log.InvokeRequired) { _log.Invoke(new Action(() => Log(msg))); return; }
        _log.AppendText(msg + Environment.NewLine);
    }

    private void ChooseDir()
    {
        using var dlg = new FolderBrowserDialog { Description = "选择要清空的目录" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        _target = dlg.SelectedPath;
        _pathLabel.Text = _target;
        var name = Path.GetFileName(_target.TrimEnd(Path.DirectorySeparatorChar));

        _exeFound = false;
        _exeLabel.Text = "";
        _exeCheck.Visible = false;
        _confirmCheck.Checked = false;
        _nameBox.Text = "";
        foreach (var l in new[] { _statFiles, _statDirs, _statSize, _statErrors }) l.Text = "-";

        if (CriticalNames.Contains(name))
        {
            _criticalLabel.Text = $"✗ {name} 是受保护的关键目录，禁止清空";
            _criticalLabel.ForeColor = Color.Firebrick;
        }
        else
        {
            _criticalLabel.Text = $"✓ 可以清空（目录名：{name}）";
            _criticalLabel.ForeColor = Color.SeaGreen;
            Log($"已选择: {_target}");
        }

        UpdateWhitelistLabel();
        UpdateStart();
    }

    private bool IsWhitelisted() =>
        _target is not null && File.Exists(Path.Combine(_target, WhitelistMarker));

    private void UpdateWhitelistLabel()
    {
        if (IsWhitelisted())
        {
            _wlLabel.Text = "✓ 已在白名单（跳过名称确认）";
            _nameBox.Enabled = false;
        }
        else
        {
            _wlLabel.Text = "";
            _nameBox.Enabled = true;
        }
    }

    private void AddWhitelist()
    {
        if (_target is null) { MessageBox.Show("请先选择目录"); return; }
        var name = Path.GetFileName(_target.TrimEnd(Path.DirectorySeparatorChar));
        if (CriticalNames.Contains(name)) { MessageBox.Show("关键目录不能加入白名单", "拒绝", MessageBoxButtons.OK, MessageBoxIcon.Error); return; }
        try
        {
            File.WriteAllText(Path.Combine(_target, WhitelistMarker), "DirCleaner Whitelist Marker");
            Log("已创建白名单标记");
            MessageBox.Show("已加入白名单");
        }
        catch (Exception e)
        {
            MessageBox.Show($"创建标记失败：{e.Message}", "失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        UpdateWhitelistLabel();
        UpdateStart();
    }

    private async void ScanExe()
    {
        if (_target is null) return;
        _statusLabel.Text = "正在扫描…";
        var path = _target;
        _exeFound = await Task.Run(() =>
        {
            var counter = 0;
            return ContainsExecutables(path, 0, ref counter);
        });
        if (_exeFound)
        {
            _exeLabel.Text = "⚠️ 发现可执行文件（.exe / .dll），需额外确认";
            _exeCheck.Visible = true;
        }
        else
        {
            _exeLabel.Text = "✓ 未发现可执行文件";
            _exeLabel.ForeColor = Color.SeaGreen;
            _exeCheck.Visible = false;
        }
        _statusLabel.Text = "扫描完成";
        UpdateStart();
    }

    private static bool ContainsExecutables(string dir, int depth, ref int counter)
    {
        if (depth > 10 || counter >= MaxScanForExe) return false;
        IEnumerable<string> entries;
        try { entries = Directory.EnumerateFileSystemEntries(dir); } catch { return false; }
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
            catch { /* 忽略 */ }
        }
        return false;
    }

    private void UpdateStart()
    {
        if (_target is null) { _startBtn.Enabled = false; return; }
        var name = Path.GetFileName(_target.TrimEnd(Path.DirectorySeparatorChar));
        if (CriticalNames.Contains(name)) { _startBtn.Enabled = false; return; }
        var ok = _confirmCheck.Checked;
        if (!IsWhitelisted()) ok = ok && _nameBox.Text.Trim() == name;
        if (_exeFound && !_exeCheck.Checked) ok = false;
        _startBtn.Enabled = ok;
    }

    private async void StartClear()
    {
        var name = Path.GetFileName(_target!.TrimEnd(Path.DirectorySeparatorChar));
        if (MessageBox.Show($"确定要清空目录 \"{name}\" 下的所有内容吗？\n此操作不可恢复。", "最后确认",
                MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;

        _cancelled = false;
        _startBtn.Enabled = false;
        _cancelBtn.Enabled = true;
        _progress.Style = ProgressBarStyle.Marquee;
        _progress.MarqueeAnimationSpeed = 30;
        _statusLabel.Text = "正在清空…";
        Log("===== 开始清空 =====");

        var path = _target!;
        var keepMarker = IsWhitelisted();
        var result = await Task.Run(() =>
        {
            var st = new Stats();
            try { ClearDirectory(path, 0, 0, keepMarker, st); }
            catch (Exception e) { st.Errors.Add(e.Message); }
            return st;
        });

        _progress.MarqueeAnimationSpeed = 0;
        _cancelBtn.Enabled = false;
        _statFiles.Text = result.Files.ToString();
        _statDirs.Text = result.Dirs.ToString();
        _statSize.Text = FormatBytes(result.Bytes);
        _statErrors.Text = result.Errors.Count.ToString();
        _statusLabel.Text = result.Errors.Count == 0 ? "完成" : $"完成，{result.Errors.Count} 个错误";
        Log("===== 清空完成 =====");
        foreach (var e in result.Errors) Log("  " + e);
        UpdateStart();
    }

    private sealed class Stats
    {
        public int Files;
        public int Dirs;
        public long Bytes;
        public readonly List<string> Errors = new();
    }

    private void ClearDirectory(string dir, int depth, int fileCount, bool keepMarker, Stats st)
    {
        if (_cancelled) throw new InvalidOperationException("操作已取消");
        if (depth > MaxRecursionDepth) throw new InvalidOperationException($"已达到最大目录深度限制 ({MaxRecursionDepth})");
        IEnumerable<string> entries;
        try { entries = Directory.EnumerateFileSystemEntries(dir); }
        catch (Exception e) { throw new InvalidOperationException($"无法读取 {dir}: {e.Message}"); }

        foreach (var path in entries)
        {
            if (_cancelled) throw new InvalidOperationException("操作已取消");
            var name = Path.GetFileName(path);
            try
            {
                if (Directory.Exists(path))
                {
                    ClearDirectory(path, depth + 1, fileCount, keepMarker, st);
                    Directory.Delete(path);
                    st.Dirs++;
                    Log($"已删除目录: {name}");
                }
                else
                {
                    if (fileCount >= MaxFileCount) throw new InvalidOperationException($"已达到最大文件数限制 ({MaxFileCount})");
                    if (keepMarker && name == WhitelistMarker) { Log($"跳过白名单标记: {name}"); continue; }
                    long size = 0;
                    try { size = new FileInfo(path).Length; } catch { }
                    File.Delete(path);
                    st.Files++;
                    st.Bytes += size;
                    fileCount++;
                    Log($"已删除文件: {name} ({FormatBytes(size)})");
                }
            }
            catch (InvalidOperationException) { throw; }
            catch (Exception e)
            {
                st.Errors.Add($"无法删除 {name}: {e.Message}");
                Log($"  ✗ 无法删除 {name}: {e.Message}");
            }
        }
    }
}
