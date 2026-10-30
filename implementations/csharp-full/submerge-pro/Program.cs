// SubMerge Pro 全功能版（C# / WinForms）
//
// 版本：A1_II_Φ10_CSharp_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 图形界面版：加载字幕、条目列表、粘贴译文并应用、双语拆分预览、导出 SRT。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace SubMergeGui;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class Entry
{
    public int Index;
    public string Start = "";
    public string End = "";
    public string Text = "";
    public string Translated = "";
}

internal sealed class MainForm : Form
{
    private static readonly Regex CjkSplit = new(@"([\u4e00-\u9fff]+)", RegexOptions.Compiled);
    private static readonly Regex CjkTest = new(@"[\u4e00-\u9fff]", RegexOptions.Compiled);
    private static readonly Regex WordRe = new(@"[A-Za-z0-9]+(?:'[A-Za-z]+)?", RegexOptions.Compiled);
    private static readonly Regex TokenRe = new(@"[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S", RegexOptions.Compiled);
    private static readonly Regex TimeRe = new(
        @"^(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})$",
        RegexOptions.Compiled);
    private static readonly Regex IdxRe = new(@"^\[(\d+)\]\s*(.*)$", RegexOptions.Compiled);

    private List<Entry> _entries = new();
    private string _filename = "";

    private readonly DataGridView _grid = new();
    private readonly TextBox _transInput = new() { Multiline = true, ScrollBars = ScrollBars.Vertical };
    private readonly TextBox _output = new() { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical };
    private readonly Label _status = new() { Text = "就绪", AutoSize = true };
    private readonly TextBox _lang = new() { Text = "中文", Width = 100 };
    private readonly NumericUpDown _maxWords = new() { Minimum = 2, Maximum = 50, Value = 10, Width = 60 };
    private readonly ComboBox _mode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 100 };

    public MainForm()
    {
        Text = "SubMerge Pro（C# WinForms 版）";
        Width = 1040;
        Height = 800;
        StartPosition = FormStartPosition.CenterScreen;

        _mode.Items.AddRange(new object[] { "双语", "仅原文", "仅译文" });
        _mode.SelectedIndex = 0;

        _grid.Dock = DockStyle.Fill;
        _grid.ReadOnly = true;
        _grid.AllowUserToAddRows = false;
        _grid.RowHeadersVisible = false;
        _grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        foreach (var (name, prop, weight) in new[]
                 {
                     ("#", nameof(Entry.Index), 40),
                     ("开始", nameof(Entry.Start), 110),
                     ("结束", nameof(Entry.End), 110),
                     ("原文", nameof(Entry.Text), 250),
                     ("译文", nameof(Entry.Translated), 250),
                 })
        {
            _grid.Columns.Add(new DataGridViewTextBoxColumn
            {
                HeaderText = name,
                DataPropertyName = prop,
                FillWeight = weight,
            });
        }

        var openBtn = new Button { Text = "打开字幕文件…", AutoSize = true };
        openBtn.Click += (_, _) => OpenFile();
        var applyBtn = new Button { Text = "应用译文", AutoSize = true };
        applyBtn.Click += (_, _) => ApplyTranslation();
        var previewBtn = new Button { Text = "预览双语拆分", AutoSize = true };
        previewBtn.Click += (_, _) => PreviewSplit();
        var exportBtn = new Button { Text = "导出 SRT", AutoSize = true };
        exportBtn.Click += (_, _) => ExportSrt();

        var top = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8) };
        top.Controls.AddRange(new Control[] { openBtn, _status });

        var opts = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8) };
        opts.Controls.Add(new Label { Text = "目标语言：", AutoSize = true });
        opts.Controls.Add(_lang);
        opts.Controls.Add(new Label { Text = "  最多词数：", AutoSize = true });
        opts.Controls.Add(_maxWords);
        opts.Controls.Add(new Label { Text = "  导出内容：", AutoSize = true });
        opts.Controls.Add(_mode);

        var actions = new FlowLayoutPanel { Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(8) };
        actions.Controls.AddRange(new Control[] { previewBtn, exportBtn });

        var transPanel = new Panel { Dock = DockStyle.Right, Width = 340, Padding = new Padding(8) };
        var transHeader = new Label
        {
            Text = "译文（[编号] 文本）",
            Dock = DockStyle.Top,
            Height = 24,
            Font = new Font("Segoe UI", 9, FontStyle.Bold),
        };
        _transInput.Dock = DockStyle.Top;
        _transInput.Height = 160;
        var applyHolder = new Panel { Dock = DockStyle.Top, Height = 40 };
        applyBtn.Dock = DockStyle.Left;
        applyHolder.Controls.Add(applyBtn);
        transPanel.Controls.Add(_transInput);
        transPanel.Controls.Add(applyHolder);
        transPanel.Controls.Add(transHeader);

        _output.Dock = DockStyle.Bottom;
        _output.Height = 180;

        var center = new Panel { Dock = DockStyle.Fill };
        center.Controls.Add(_grid);
        center.Controls.Add(_output);

        Controls.Add(center);
        Controls.Add(transPanel);
        Controls.Add(actions);
        Controls.Add(opts);
        Controls.Add(top);
    }

    private static bool IsCjk(char c) => c >= '\u4e00' && c <= '\u9fff';

    // 仅 ASCII 字母数字。不能直接用 char.IsLetterOrDigit：它把汉字也算作字母，
    // 会让 AddBoundary 在「中中」之间也插空格。
    private static bool IsAsciiAlnum(char c) =>
        (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');

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
                tokens.AddRange(TokenRe.Matches(seg).Select(m => m.Value));
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

    private void OpenFile()
    {
        using var dlg = new OpenFileDialog { Filter = "字幕|*.srt;*.bcc;*.txt|全部|*.*" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        try
        {
            _entries = ParseSubtitle(File.ReadAllText(dlg.FileName, Encoding.UTF8));
        }
        catch (Exception e)
        {
            MessageBox.Show($"读取失败：{e.Message}");
            return;
        }
        if (_entries.Count == 0) { MessageBox.Show("解析失败：未找到任何字幕条目"); return; }
        _filename = Path.GetFileName(dlg.FileName);
        _status.Text = $"{_filename} · {_entries.Count} 条";
        RefreshGrid();
    }

    private void RefreshGrid()
    {
        _grid.DataSource = null;
        _grid.DataSource = _entries.Select(e => new
        {
            e.Index, e.Start, e.End, e.Text, e.Translated,
        }).ToList();
    }

    private void ApplyTranslation()
    {
        if (_entries.Count == 0) { MessageBox.Show("请先加载字幕文件"); return; }
        var map = new Dictionary<int, string>();
        int? cur = null;
        var buf = new List<string>();

        void Flush() { if (cur is not null) map[cur.Value] = string.Join("\n", buf).Trim(); }

        foreach (var line in _transInput.Text.Split('\n'))
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

        if (map.Count == 0) { MessageBox.Show("未检测到 [编号] 格式的译文"); return; }

        var applied = 0;
        foreach (var e in _entries)
        {
            if (map.TryGetValue(e.Index, out var tr))
            {
                e.Translated = tr;
                applied++;
            }
        }
        RefreshGrid();
        MessageBox.Show($"已应用 {applied} 条译文");
    }

    private void PreviewSplit()
    {
        if (_entries.Count == 0) return;
        var mw = (int)_maxWords.Value;
        var sb = new StringBuilder();
        foreach (var e in _entries)
        {
            foreach (var (o, t) in SplitPaired(e.Text, e.Translated, mw))
            {
                var body = string.IsNullOrEmpty(t) ? o : o + "\n" + t;
                sb.AppendLine($"[{e.Index}] {body.Trim()}");
            }
        }
        _output.Text = sb.ToString();
    }

    private void ExportSrt()
    {
        if (_entries.Count == 0) { MessageBox.Show("请先加载字幕文件"); return; }
        var baseName = Path.GetFileNameWithoutExtension(_filename);
        using var dlg = new SaveFileDialog
        {
            Filter = "SRT|*.srt",
            FileName = $"【已翻译-{_lang.Text}】{baseName}.srt",
        };
        if (dlg.ShowDialog() != DialogResult.OK) return;

        var sb = new StringBuilder();
        foreach (var e in _entries)
        {
            string text;
            switch (_mode.SelectedIndex)
            {
                case 1: text = e.Text; break;
                case 2: text = e.Translated; break;
                default:
                    if (e.Translated.Length > 0 && e.Text.Length > 0) text = e.Text + "\n" + e.Translated;
                    else if (e.Translated.Length > 0) text = e.Translated;
                    else text = e.Text;
                    break;
            }
            sb.Append($"{e.Index}\n{e.Start} --> {e.End}\n{text}\n\n");
        }
        File.WriteAllText(dlg.FileName, sb.ToString(), Encoding.UTF8);
        MessageBox.Show("已导出");
    }
}
