// Writer 全功能版（C# / WinForms）
//
// 版本：A1_I_Φ3_CSharp_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//
// 图形界面版：左侧章节树、中间正文编辑、右侧资料与提示词、字数统计、自动保存。
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
using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace WriterGui;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class Book
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
}

internal sealed class Volume
{
    public string Id { get; set; } = "";
    [JsonPropertyName("book_id")] public string BookId { get; set; } = "";
    public string Title { get; set; } = "";
    public int Order { get; set; }
}

internal sealed class Chapter
{
    public string Id { get; set; } = "";
    [JsonPropertyName("book_id")] public string BookId { get; set; } = "";
    [JsonPropertyName("volume_id")] public string VolumeId { get; set; } = "";
    public string Title { get; set; } = "";
    public int Order { get; set; }
    [JsonPropertyName("word_count")] public long WordCount { get; set; }
    public string Text { get; set; } = "";
}

internal sealed class Entity
{
    public string Id { get; set; } = "";
    [JsonPropertyName("book_id")] public string BookId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Description { get; set; } = "";
}

internal sealed class Library
{
    public List<Book> Books { get; set; } = new();
    public List<Volume> Volumes { get; set; } = new();
    public List<Chapter> Chapters { get; set; } = new();
    public List<Entity> Entities { get; set; } = new();
}

internal sealed class MainForm : Form
{
    private static long _counter;

    private string? _path;
    private Library _lib = new();
    private string? _selChapter;

    private readonly TreeView _tree = new() { Dock = DockStyle.Fill };
    private readonly TextBox _title = new() { Dock = DockStyle.Top };
    private readonly TextBox _body = new() { Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
    private readonly Label _status = new() { Dock = DockStyle.Bottom, AutoSize = false, Height = 22 };
    private readonly ListBox _ents = new() { Dock = DockStyle.Fill };
    private readonly TextBox _prompt = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
    private readonly System.Windows.Forms.Timer _auto = new() { Interval = 1500 };
    private bool _dirty;

    public MainForm()
    {
        Text = "Writer（C# WinForms 版）";
        Width = 1240;
        Height = 820;
        StartPosition = FormStartPosition.CenterScreen;

        var top = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8) };
        var openBtn = new Button { Text = "打开库…", AutoSize = true };
        openBtn.Click += (_, _) => OpenLibrary();
        var saveBtn = new Button { Text = "保存", AutoSize = true };
        saveBtn.Click += (_, _) => SaveLibrary();
        top.Controls.AddRange(new Control[] { openBtn, saveBtn, _status });

        _tree.HideSelection = false;
        _tree.AfterSelect += (_, _) => OnTreeSelect();

        var leftPanel = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Horizontal, SplitterDistance = 460 };
        leftPanel.Panel1.Controls.Add(_tree);
        var leftBtns = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 74 };
        var addVolBtn = new Button { Text = "+ 卷", AutoSize = true };
        addVolBtn.Click += (_, _) => AddVolume();
        var addChBtn = new Button { Text = "+ 章", AutoSize = true };
        addChBtn.Click += (_, _) => AddChapter();
        var delChBtn = new Button { Text = "删章", AutoSize = true };
        delChBtn.Click += (_, _) => DeleteChapter();
        leftBtns.Controls.AddRange(new Control[] { addVolBtn, addChBtn, delChBtn });
        leftPanel.Panel2.Controls.Add(leftBtns);

        var centerPanel = new Panel { Dock = DockStyle.Fill };
        centerPanel.Controls.Add(_body);
        centerPanel.Controls.Add(_title);

        var entPanel = new Panel { Dock = DockStyle.Fill };
        var entBtns = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 80 };
        var addEntBtn = new Button { Text = "+ 资料", AutoSize = true };
        addEntBtn.Click += (_, _) => AddEntity();
        var promptBtn = new Button { Text = "生成提示词", AutoSize = true };
        promptBtn.Click += (_, _) => BuildPrompt();
        entBtns.Controls.AddRange(new Control[] { addEntBtn, promptBtn });
        entPanel.Controls.Add(_prompt);
        entPanel.Controls.Add(_ents);
        entPanel.Controls.Add(entBtns);

        var rightTabs = new TabControl { Dock = DockStyle.Fill };
        var tabEnt = new TabPage("资料");
        tabEnt.Controls.Add(entPanel);
        var tabPrompt = new TabPage("提示词");
        tabPrompt.Controls.Add(_prompt);
        rightTabs.TabPages.Add(tabEnt);
        rightTabs.TabPages.Add(tabPrompt);

        var main = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Vertical, SplitterDistance = 250 };
        main.Panel1.Controls.Add(leftPanel);
        var inner = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Vertical, SplitterDistance = 640 };
        inner.Panel1.Controls.Add(centerPanel);
        inner.Panel2.Controls.Add(rightTabs);
        main.Panel2.Controls.Add(inner);

        Controls.Add(main);
        Controls.Add(top);

        _body.TextChanged += (_, _) => { _dirty = true; UpdateStatus(); };
        _title.TextChanged += (_, _) => _dirty = true;

        _auto.Tick += (_, _) => { if (_dirty && _path is not null) SaveLibrary(); };
        _auto.Start();
    }

    private static bool IsCjk(int cp) =>
        (cp >= 0x3400 && cp <= 0x4DBF) || (cp >= 0x4E00 && cp <= 0x9FFF) ||
        (cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0xAC00 && cp <= 0xD7AF) ||
        (cp >= 0xF900 && cp <= 0xFAFF);

    private static long CountWords(string text)
    {
        long total = 0;
        var inLatin = false;
        foreach (var ch in text)
        {
            if (IsCjk(ch)) { total++; inLatin = false; }
            else if (char.IsLetterOrDigit(ch)) { if (!inLatin) { total++; inLatin = true; } }
            else inLatin = false;
        }
        return total;
    }

    private static string GenId(string p) => $"{p}_{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}_{++_counter}";

    private void OpenLibrary()
    {
        using var dlg = new OpenFileDialog { Filter = "JSON|*.json|全部|*.*" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        _path = dlg.FileName;
        try
        {
            var json = File.Exists(_path) ? File.ReadAllText(_path, Encoding.UTF8) : "";
            _lib = string.IsNullOrWhiteSpace(json)
                ? new Library()
                : JsonSerializer.Deserialize<Library>(json) ?? new Library();
        }
        catch (Exception e)
        {
            MessageBox.Show($"读取失败：{e.Message}");
            return;
        }
        if (_lib.Books.Count == 0)
            _lib.Books.Add(new Book { Id = GenId("book"), Title = "未命名" });
        RefreshTree();
        RefreshEntities();
        _status.Text = _path;
    }

    private void SaveLibrary()
    {
        if (_path is null) return;
        SyncCurrent();
        File.WriteAllText(_path, JsonSerializer.Serialize(_lib, new JsonSerializerOptions { WriteIndented = true }), Encoding.UTF8);
        _dirty = false;
        _status.Text = $"已保存 {DateTime.Now:HH:mm:ss}";
    }

    private void SyncCurrent()
    {
        if (_selChapter is null) return;
        var ch = _lib.Chapters.FirstOrDefault(c => c.Id == _selChapter);
        if (ch is null) return;
        ch.Title = _title.Text;
        ch.Text = _body.Text;
        ch.WordCount = CountWords(ch.Text);
    }

    private void RefreshTree()
    {
        _tree.BeginUpdate();
        _tree.Nodes.Clear();
        foreach (var v in _lib.Volumes.OrderBy(v => v.Order))
        {
            var vn = _tree.Nodes.Add(v.Id, v.Title);
            foreach (var c in _lib.Chapters.Where(c => c.VolumeId == v.Id).OrderBy(c => c.Order))
                vn.Nodes.Add(c.Id, $"{c.Title}（{c.WordCount} 字）");
        }
        _tree.ExpandAll();
        _tree.EndUpdate();
    }

    private void RefreshEntities()
    {
        _ents.Items.Clear();
        foreach (var e in _lib.Entities) _ents.Items.Add($"{e.Name}（{e.Kind}）");
    }

    private void OnTreeSelect()
    {
        if (_tree.SelectedNode is null) return;
        var id = _tree.SelectedNode.Name;
        if (_lib.Chapters.All(c => c.Id != id)) return;
        SyncCurrent();
        var ch = _lib.Chapters.First(c => c.Id == id);
        _selChapter = id;
        _title.Text = ch.Title;
        _body.Text = ch.Text;
        UpdateStatus();
    }

    private void UpdateStatus()
    {
        _status.Text = $"本章 {CountWords(_body.Text)} 字 · {_body.Text.Length} 字符";
    }

    private void AddVolume()
    {
        var name = Prompt("新增卷", "卷名：");
        if (string.IsNullOrWhiteSpace(name)) return;
        var bookId = _lib.Books.Count > 0 ? _lib.Books[0].Id : "";
        _lib.Volumes.Add(new Volume { Id = GenId("vol"), BookId = bookId, Title = name, Order = _lib.Volumes.Count });
        RefreshTree();
        _dirty = true;
    }

    private void AddChapter()
    {
        if (_lib.Volumes.Count == 0) { MessageBox.Show("请先新增一卷"); return; }
        var name = Prompt("新增章节", "章节名：");
        if (string.IsNullOrWhiteSpace(name)) return;
        var vol = _lib.Volumes[^1];
        _lib.Chapters.Add(new Chapter
        {
            Id = GenId("ch"), BookId = vol.BookId, VolumeId = vol.Id,
            Title = name, Order = _lib.Chapters.Count(c => c.VolumeId == vol.Id),
        });
        RefreshTree();
        _dirty = true;
    }

    private void DeleteChapter()
    {
        if (_selChapter is null) return;
        if (MessageBox.Show("删除当前章节？", "确认", MessageBoxButtons.YesNo) != DialogResult.Yes) return;
        _lib.Chapters.RemoveAll(c => c.Id == _selChapter);
        _selChapter = null;
        _title.Text = "";
        _body.Text = "";
        RefreshTree();
        _dirty = true;
    }

    private void AddEntity()
    {
        var name = Prompt("新增资料", "名称：");
        if (string.IsNullOrWhiteSpace(name)) return;
        var kind = Prompt("新增资料", "类型（人物/地点等）：") ?? "其他";
        var desc = Prompt("新增资料", "描述：") ?? "";
        var bookId = _lib.Books.Count > 0 ? _lib.Books[0].Id : "";
        _lib.Entities.Add(new Entity { Id = GenId("ent"), BookId = bookId, Name = name, Kind = kind, Description = desc });
        RefreshEntities();
        _dirty = true;
    }

    private void BuildPrompt()
    {
        if (_selChapter is null) { MessageBox.Show("请先选择章节"); return; }
        var ch = _lib.Chapters.First(c => c.Id == _selChapter);
        var list = _lib.Chapters.Where(c => c.VolumeId == ch.VolumeId).OrderBy(c => c.Order).ToList();
        var pos = list.FindIndex(c => c.Id == _selChapter);
        var prev = pos > 0
            ? (list[pos - 1].Text.Length > 500 ? list[pos - 1].Text[^500..] : list[pos - 1].Text)
            : "（本章为卷首，无上一章）";
        var ents = _lib.Entities.Where(e => e.BookId == ch.BookId).ToList();
        var chars = ents.Count > 0
            ? string.Join("\n", ents.Select(e => $"- {e.Name}（{e.Kind}）：{e.Description}"))
            : "（未填写）";
        _prompt.Text = $"你是一位与作者合写的小说作者。请续写下一段情节。\n\n【设定】\n{chars}\n\n【上一章结尾】\n{prev}\n\n【本章已有正文】\n{(string.IsNullOrEmpty(ch.Text) ? "（当前章为空）" : ch.Text)}";
    }

    private string? Prompt(string title, string label)
    {
        using var f = new Form { Text = title, Width = 420, Height = 160, StartPosition = FormStartPosition.CenterParent };
        var lbl = new Label { Text = label, Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(10, 10, 0, 0) };
        var box = new TextBox { Dock = DockStyle.Top };
        var ok = new Button { Text = "确定", Dock = DockStyle.Bottom, DialogResult = DialogResult.OK };
        f.Controls.Add(box);
        f.Controls.Add(ok);
        f.Controls.Add(lbl);
        f.AcceptButton = ok;
        return f.ShowDialog() == DialogResult.OK ? box.Text : null;
    }
}
