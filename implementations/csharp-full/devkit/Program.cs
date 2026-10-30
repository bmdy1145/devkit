// DevKit 全功能版（C# / WinForms）
//
// 版本：A1_V_Φ9_Fix_CSharp_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 图形界面版：项目/页签、灵感、组合预览与复制、代码与结果编辑、
// 九款主题切换、配置导入导出。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;

namespace DevKitGui;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class Tab
{
    public string Id { get; set; } = "";
    public string Type { get; set; } = "";
    public string Inspiration { get; set; } = "";
}

internal sealed class Project
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public List<Tab> Tabs { get; set; } = new();
    public string Code { get; set; } = "";
    public string Result { get; set; } = "";
}

internal sealed class Settings
{
    public string Theme { get; set; } = "Clean";
}

internal sealed class State
{
    public string Version { get; set; } = "";
    public string ActiveProjectId { get; set; } = "";
    public List<Project> Projects { get; set; } = new();
    public Settings Settings { get; set; } = new();
}

internal sealed class MainForm : Form
{
    private const string CurrentVersion = "A1_V_Φ9_Fix_CSharp_CN";

    private static readonly (string Name, Color Bg, Color Fg, Color Accent)[] Themes =
    {
        ("Clean", Color.FromArgb(249,250,251), Color.FromArgb(17,24,39), Color.FromArgb(59,130,246)),
        ("Glass", Color.FromArgb(18,20,26), Color.FromArgb(232,236,244), Color.FromArgb(110,168,255)),
        ("Neon", Color.FromArgb(8,9,13), Color.FromArgb(233,242,236), Color.FromArgb(187,243,81)),
        ("Mono", Color.FromArgb(10,10,10), Color.FromArgb(230,230,230), Color.FromArgb(0,255,65)),
        ("Material", Color.FromArgb(20,18,24), Color.FromArgb(230,224,233), Color.FromArgb(208,188,255)),
        ("Minimal", Color.FromArgb(244,244,241), Color.FromArgb(12,12,9), Color.FromArgb(49,44,133)),
        ("Premium", Color.FromArgb(28,28,30), Color.FromArgb(245,245,247), Color.FromArgb(37,99,235)),
        ("Shadcn", Color.White, Color.FromArgb(9,9,11), Color.FromArgb(24,24,27)),
        ("Baseline", Color.FromArgb(30,30,30), Color.FromArgb(204,204,204), Color.FromArgb(86,156,214)),
    };

    private static readonly (string Name, string Head)[] Templates =
    {
        ("版本规划", "你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。"),
        ("需求分析", "你是一位资深系统分析师。请对下面需求做全面分析。"),
        ("安全审计", "你是一位持有 OSCP 认证的安全专家。请审计下面的代码。"),
        ("性能审计", "你是一位性能优化专家。请审计下面的代码。"),
        ("结构重构", "你是一位资深架构师。请重构下面的代码。"),
        ("单元测试", "请为下面的代码编写单元测试。"),
        ("空白", ""),
    };

    private static long _ctr;
    private static string GenId(string p) => $"{p}_{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}_{++_ctr}";

    private State _state = new();
    private string? _path;
    private int _tabIdx;

    private readonly ListBox _tabs = new() { Dock = DockStyle.Fill };
    private readonly TextBox _insp = new() { Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Top, Height = 100 };
    private readonly TextBox _preview = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
    private readonly TextBox _code = new() { Multiline = true, ScrollBars = ScrollBars.Both, Dock = DockStyle.Fill, WordWrap = false };
    private readonly TextBox _result = new() { Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
    private readonly Label _status = new() { AutoSize = true, Text = "就绪" };
    private readonly Label _count = new() { AutoSize = true };
    private readonly ComboBox _theme = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 120 };

    public MainForm()
    {
        Text = "DevKit（C# WinForms 版）";
        Width = 1240;
        Height = 840;
        StartPosition = FormStartPosition.CenterScreen;
        _state = DefaultState();

        foreach (var t in Themes) _theme.Items.Add(t.Name);
        _theme.SelectedIndex = 0;
        _theme.SelectedIndexChanged += (_, _) => ApplyTheme();

        var top = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8) };
        top.Controls.Add(new Label { Text = "主题：", AutoSize = true });
        top.Controls.Add(_theme);
        var newProj = new Button { Text = "新建项目", AutoSize = true };
        newProj.Click += (_, _) => NewProject();
        var openCfg = new Button { Text = "打开配置…", AutoSize = true };
        openCfg.Click += (_, _) => OpenConfig();
        var exportCfg = new Button { Text = "导出配置", AutoSize = true };
        exportCfg.Click += (_, _) => ExportConfig();
        top.Controls.AddRange(new Control[] { newProj, openCfg, exportCfg, _status });

        _tabs.SelectedIndexChanged += (_, _) => { if (_tabs.SelectedIndex >= 0) { SaveTab(); LoadTab(_tabs.SelectedIndex); } };

        var sideTop = new Panel { Dock = DockStyle.Top, Height = 30 };
        sideTop.Controls.Add(new Label { Text = "工作流步骤", Dock = DockStyle.Fill, Font = new Font("Segoe UI", 9, FontStyle.Bold) });

        var inspLabel = new Label { Text = "灵感", Dock = DockStyle.Top, AutoSize = false, Height = 22 };
        var previewLabel = new Label { Text = "组合预览", Dock = DockStyle.Top, AutoSize = false, Height = 22 };
        var copyBtn = new Button { Text = "复制预览", Dock = DockStyle.Bottom, Height = 30 };
        copyBtn.Click += (_, _) => { Clipboard.SetText(Compose()); _status.Text = "已复制"; };

        var side = new Panel { Dock = DockStyle.Fill };
        side.Controls.Add(_preview);
        side.Controls.Add(copyBtn);
        side.Controls.Add(previewLabel);
        side.Controls.Add(_preview);
        side.Controls.Add(_insp);
        side.Controls.Add(inspLabel);
        side.Controls.Add(_tabs);
        side.Controls.Add(sideTop);

        var codeLabel = new Label { Text = "代码编辑区", Dock = DockStyle.Top, AutoSize = false, Height = 22 };
        var resultLabel = new Label { Text = "AI 处理结果", Dock = DockStyle.Top, AutoSize = false, Height = 22 };
        var overwrite = new Button { Text = "用结果覆盖代码区", Dock = DockStyle.Bottom, Height = 30 };
        overwrite.Click += (_, _) =>
        {
            if (_result.Text.Length > 0)
            {
                _code.Text = _result.Text;
                _result.Text = "";
            }
        };

        var resultPanel = new Panel { Dock = DockStyle.Bottom, Height = 200 };
        resultPanel.Controls.Add(_result);
        resultPanel.Controls.Add(resultLabel);
        resultPanel.Controls.Add(overwrite);

        var centerPanel = new Panel { Dock = DockStyle.Fill };
        centerPanel.Controls.Add(_code);
        centerPanel.Controls.Add(resultPanel);
        centerPanel.Controls.Add(codeLabel);
        centerPanel.Controls.Add(_count);

        var split = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Vertical, SplitterDistance = 380 };
        split.Panel1.Controls.Add(side);
        split.Panel2.Controls.Add(centerPanel);

        Controls.Add(split);
        Controls.Add(top);

        _code.TextChanged += (_, _) =>
        {
            SaveTab();
            RefreshPreview();
            _count.Text = $"{_code.Text.Length} 字符";
        };
        _insp.TextChanged += (_, _) => { SaveTab(); RefreshPreview(); };

        RefreshTabs();
        LoadTab(0);
        ApplyTheme();
    }

    private static State DefaultState()
    {
        var tabs = Templates.Select(t => new Tab { Id = GenId("tab"), Type = t.Name }).ToList();
        return new State
        {
            Version = CurrentVersion,
            ActiveProjectId = "proj_1",
            Projects = new List<Project>
            {
                new() { Id = "proj_1", Name = "默认项目", Tabs = tabs },
            },
            Settings = new Settings { Theme = "Clean" },
        };
    }

    private Project P => _state.Projects[0];

    private void ApplyTheme()
    {
        var name = _theme.SelectedItem?.ToString() ?? "Clean";
        var t = Themes.FirstOrDefault(x => x.Name == name);
        if (t.Name is null) t = Themes[8];
        _state.Settings.Theme = name;
        BackColor = t.Bg;
        foreach (var c in new Control[] { _specify(_insp), _preview, _code, _result })
        {
            c.BackColor = t.Bg == Color.White ? Color.FromArgb(244, 244, 245) : ControlPaint.Dark(t.Bg, 0.05f);
            c.ForeColor = t.Fg;
        }
        _tabs.BackColor = t.Bg;
        _tabs.ForeColor = t.Fg;
    }

    private static TextBox _specify(TextBox t) => t;

    private string Compose()
    {
        if (_tabIdx >= P.Tabs.Count) return "";
        var tab = P.Tabs[_tabIdx];
        var head = Templates.FirstOrDefault(x => x.Name == tab.Type).Head ?? "";
        var insp = string.IsNullOrEmpty(tab.Inspiration) ? "（无需求）" : tab.Inspiration;
        var code = string.IsNullOrEmpty(P.Code) ? "（无代码）" : P.Code;
        return string.IsNullOrEmpty(head)
            ? $"需求：{insp}\n\n代码：\n{code}"
            : $"{head}\n\n需求：{insp}\n\n代码：\n{code}";
    }

    private void RefreshPreview() => _preview.Text = Compose();

    private void RefreshTabs()
    {
        _tabs.Items.Clear();
        foreach (var t in P.Tabs) _tabs.Items.Add(t.Type);
        if (P.Tabs.Count > 0) _tabs.SelectedIndex = Math.Min(_tabIdx, P.Tabs.Count - 1);
    }

    private void LoadTab(int idx)
    {
        if (idx < 0 || idx >= P.Tabs.Count) return;
        _tabIdx = idx;
        _insp.Text = P.Tabs[idx].Inspiration;
        _code.Text = P.Code;
        _result.Text = P.Result;
        RefreshPreview();
        _count.Text = $"{P.Code.Length} 字符";
    }

    private void SaveTab()
    {
        if (_tabIdx >= P.Tabs.Count) return;
        P.Tabs[_tabIdx].Inspiration = _insp.Text;
        P.Code = _code.Text;
        P.Result = _result.Text;
    }

    private void NewProject()
    {
        SaveTab();
        var tabs = Templates.Select(t => new Tab { Id = GenId("tab"), Type = t.Name }).ToList();
        var np = new Project { Id = GenId("proj"), Name = "新项目", Tabs = tabs };
        _state.Projects.Add(np);
        _state.ActiveProjectId = np.Id;
        _tabIdx = 0;
        RefreshTabs();
        LoadTab(0);
        _status.Text = "已新建项目";
    }

    private void OpenConfig()
    {
        using var dlg = new OpenFileDialog { Filter = "JSON|*.json|全部|*.*" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        try
        {
            var st = JsonSerializer.Deserialize<State>(File.ReadAllText(dlg.FileName, Encoding.UTF8));
            if (st is null || st.Projects.Count == 0) { MessageBox.Show("配置为空"); return; }
            _state = st;
            _path = dlg.FileName;
            _tabIdx = 0;
            var themeName = _state.Settings.Theme;
            var ti = Array.FindIndex(Themes, x => x.Name == themeName);
            if (ti >= 0) _theme.SelectedIndex = ti;
            RefreshTabs();
            LoadTab(0);
            _status.Text = $"已导入 {st.Projects.Count} 个项目";
        }
        catch (Exception e) { MessageBox.Show($"读取失败：{e.Message}"); }
    }

    private void ExportConfig()
    {
        SaveTab();
        using var dlg = new SaveFileDialog { Filter = "JSON|*.json", FileName = "devkit_config.json" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        _state.Version = CurrentVersion;
        File.WriteAllText(dlg.FileName, JsonSerializer.Serialize(_state, new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
        _path = dlg.FileName;
        _status.Text = "已导出配置";
    }
}
