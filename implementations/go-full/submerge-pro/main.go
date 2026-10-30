// SubMerge Pro 全功能版（Go / Fyne）
//
// 版本：A1_II_Φ10_Go_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 图形界面版：加载字幕、条目预览、粘贴译文并应用、双语拆分预览、导出 SRT。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"fmt"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/widget"
)

type Entry struct {
	Index      int
	Start      string
	End        string
	Text       string
	Translated string
}

var reCjkSplit = regexp.MustCompile(`([\x{4e00}-\x{9fff}]+)`)
var reCjkTest = regexp.MustCompile(`[\x{4e00}-\x{9fff}]`)
var reWord = regexp.MustCompile(`[A-Za-z0-9]+(?:'[A-Za-z]+)?`)
var reToken = regexp.MustCompile(`[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S`)
var reTime = regexp.MustCompile(`^(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})$`)
var reIdx = regexp.MustCompile(`^\[(\d+)\]\s*(.*)$`)

func isCJK(r rune) bool { return r >= 0x4e00 && r <= 0x9fff }

func tokenize(text string) []string {
	var tokens []string
	for _, seg := range reCjkSplit.Split(text, -1) {
		if seg == "" {
			continue
		}
		if reCjkTest.MatchString(seg) {
			r := []rune(seg)
			for i := 0; i < len(r); i += 2 {
				end := i + 2
				if end > len(r) {
					end = len(r)
				}
				tokens = append(tokens, string(r[i:end]))
			}
		} else {
			// 与 HTML 参考实现一致：[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S
			tokens = append(tokens, reToken.FindAllString(seg, -1)...)
		}
	}
	return tokens
}

func joinTokens(tokens []string) string {
	var b strings.Builder
	for i, tok := range tokens {
		if i > 0 {
			prev := []rune(tokens[i-1])
			cur := []rune(tok)
			if len(prev) > 0 && len(cur) > 0 && !isCJK(prev[len(prev)-1]) && !isCJK(cur[0]) {
				b.WriteRune(' ')
			}
		}
		b.WriteString(tok)
	}
	return b.String()
}

var reB1 = regexp.MustCompile(`([a-zA-Z0-9])([\x{4e00}-\x{9fff}])`)
var reB2 = regexp.MustCompile(`([\x{4e00}-\x{9fff}])([a-zA-Z0-9])`)

func addBoundary(s string) string {
	s = reB1.ReplaceAllString(s, "$1 $2")
	return reB2.ReplaceAllString(s, "$1 $2")
}

func splitPaired(orig, trans string, maxWords int) [][2]string {
	o := tokenize(orig)
	t := tokenize(trans)
	var chunks [][2]string
	oi, ti := 0, 0
	for oi < len(o) || ti < len(t) {
		var oc, tc []string
		words := 0
		for (oi < len(o) || ti < len(t)) && words < maxWords {
			canO, canT := oi < len(o), ti < len(t)
			if canO && canT {
				if words+2 <= maxWords {
					oc = append(oc, o[oi]); oi++
					tc = append(tc, t[ti]); ti++
					words += 2
				} else { break }
			} else if canO {
				if words+1 <= maxWords { oc = append(oc, o[oi]); oi++; words++ } else { break }
			} else if canT {
				if words+1 <= maxWords { tc = append(tc, t[ti]); ti++; words++ } else { break }
			}
		}
		chunks = append(chunks, [2]string{
			strings.TrimSpace(addBoundary(joinTokens(oc))),
			strings.TrimSpace(addBoundary(joinTokens(tc))),
		})
	}
	if len(chunks) == 0 {
		chunks = append(chunks, [2]string{orig, trans})
	}
	return chunks
}

func timeToMs(s string) int64 {
	parts := strings.Split(s, ":")
	if len(parts) != 3 { return 0 }
	h, _ := strconv.ParseInt(strings.TrimSpace(parts[0]), 10, 64)
	m, _ := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64)
	sp := strings.TrimSpace(parts[2])
	var sec, ms int64
	if i := strings.Index(sp, ","); i >= 0 {
		sec, _ = strconv.ParseInt(sp[:i], 10, 64)
		frac := sp[i+1:]
		for len(frac) < 3 { frac += "0" }
		ms, _ = strconv.ParseInt(frac[:3], 10, 64)
	} else if i := strings.Index(sp, "."); i >= 0 {
		sec, _ = strconv.ParseInt(sp[:i], 10, 64)
		frac := sp[i+1:]
		for len(frac) < 2 { frac += "0" }
		fr, _ := strconv.ParseFloat(frac[:2], 64)
		ms = int64(fr*40 + 0.5)
	} else {
		sec, _ = strconv.ParseInt(sp, 10, 64)
	}
	return (h*3600+m*60+sec)*1000 + ms
}

func msToTime(ms int64) string {
	h := ms / 3600000; ms %= 3600000
	m := ms / 60000; ms %= 60000
	s := ms / 1000
	return fmt.Sprintf("%02d:%02d:%02d,%03d", h, m, s, ms%1000)
}

func parseSubtitle(content string) []Entry {
	clean := strings.TrimPrefix(content, "\ufeff")
	clean = strings.ReplaceAll(clean, "\r\n", "\n")
	clean = strings.ReplaceAll(clean, "\r", "\n")
	var entries []Entry
	seen := map[int]bool{}
	for _, block := range strings.Split(clean, "\n\n") {
		var lines []string
		for _, l := range strings.Split(block, "\n") {
			if t := strings.TrimSpace(l); t != "" { lines = append(lines, t) }
		}
		if len(lines) < 3 { continue }
		if _, err := strconv.Atoi(lines[0]); err != nil { continue }
		m := reTime.FindStringSubmatch(lines[1])
		if m == nil { continue }
		idx, _ := strconv.Atoi(lines[0])
		if seen[idx] { continue }
		seen[idx] = true
		start := strings.Replace(m[1], ".", ",", 1)
		end := strings.Replace(m[2], ".", ",", 1)
		if timeToMs(start) >= timeToMs(end) { end = msToTime(timeToMs(start) + 1) }
		text := strings.TrimSpace(strings.Join(lines[2:], "\n"))
		if text == "" { continue }
		entries = append(entries, Entry{Index: idx, Start: start, End: end, Text: text})
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Index < entries[j].Index })
	return entries
}

func applyTranslation(entries []Entry, trans string) int {
	m := map[int]string{}
	cur := -1
	var buf []string
	flush := func() { if cur >= 0 { m[cur] = strings.TrimSpace(strings.Join(buf, "\n")) } }
	for _, line := range strings.Split(trans, "\n") {
		t := strings.TrimSpace(line)
		if mm := reIdx.FindStringSubmatch(t); mm != nil {
			flush()
			cur, _ = strconv.Atoi(mm[1])
			buf = nil
			if r := strings.TrimSpace(mm[2]); r != "" { buf = append(buf, r) }
			continue
		}
		if cur >= 0 && t != "" { buf = append(buf, t) }
	}
	flush()
	applied := 0
	for i := range entries {
		if v, ok := m[entries[i].Index]; ok {
			entries[i].Translated = v
			applied++
		}
	}
	return applied
}

func exportSrt(entries []Entry, mode string) string {
	var b strings.Builder
	for _, e := range entries {
		var text string
		switch mode {
		case "仅原文":
			text = e.Text
		case "仅译文":
			text = e.Translated
		default:
			if e.Translated != "" && e.Text != "" {
				text = e.Text + "\n" + e.Translated
			} else if e.Translated != "" {
				text = e.Translated
			} else {
				text = e.Text
			}
		}
		fmt.Fprintf(&b, "%d\n%s --> %s\n%s\n\n", e.Index, e.Start, e.End, text)
	}
	return b.String()
}

func main() {
	a := app.New()
	w := a.NewWindow("SubMerge Pro（Go / Fyne 版）")
	w.Resize(fyne.NewSize(1000, 760))

	var entries []Entry
	var filename string

	status := widget.NewLabel("就绪")
	transInput := widget.NewMultiLineEntry()
	transInput.SetPlaceHolder("译文：[编号] 文本")
	langEntry := widget.NewEntry()
	langEntry.SetText("中文")
	maxWords := widget.NewEntry()
	maxWords.SetText("10")
	modeSel := widget.NewSelect([]string{"双语", "仅原文", "仅译文"}, nil)
	modeSel.SetSelected("双语")

	table := widget.NewMultiLineEntry()
	table.SetMinRowsVisible(14)
	table.Disable()
	output := widget.NewMultiLineEntry()
	output.SetMinRowsVisible(8)
	output.Disable()

	refresh := func() {
		var b strings.Builder
		for _, e := range entries {
			fmt.Fprintf(&b, "%d\t%s --> %s\t%s\t%s\n", e.Index, e.Start, e.End, e.Text, e.Translated)
		}
		table.SetText(b.String())
	}

	openBtn := widget.NewButton("打开字幕文件…", func() {
		d := dialog.NewFileOpen(func(rc fyne.URIReadCloser, err error) {
			if err != nil || rc == nil { return }
			defer rc.Close()
			data := make([]byte, 0)
			buf := make([]byte, 4096)
			for {
				n, e := rc.Read(buf)
				if n > 0 { data = append(data, buf[:n]...) }
				if e != nil { break }
			}
			entries = parseSubtitle(string(data))
			if len(entries) == 0 {
				status.SetText("解析失败：未找到字幕条目")
				return
			}
			filename = rc.URI().Name()
			status.SetText(fmt.Sprintf("%s · %d 条", filename, len(entries)))
			refresh()
		}, w)
		d.SetFilter(storage.NewExtensionFileFilter([]string{".srt", ".bcc", ".txt"}))
		d.Show()
	})

	applyBtn := widget.NewButton("应用译文", func() {
		if len(entries) == 0 { status.SetText("请先加载字幕文件"); return }
		n := applyTranslation(entries, transInput.Text)
		if n == 0 { status.SetText("未检测到 [编号] 格式") } else { status.SetText(fmt.Sprintf("已应用 %d 条译文", n)) }
		refresh()
	})

	previewBtn := widget.NewButton("预览拆分", func() {
		mw, _ := strconv.Atoi(strings.TrimSpace(maxWords.Text))
		if mw < 2 { mw = 10 }
		var b strings.Builder
		for _, e := range entries {
			for _, c := range splitPaired(e.Text, e.Translated, mw) {
				body := c[0]
				if c[1] != "" { body = c[0] + "\n" + c[1] }
				fmt.Fprintf(&b, "[%d] %s\n", e.Index, strings.TrimSpace(body))
			}
		}
		output.SetText(b.String())
	})

	exportBtn := widget.NewButton("导出 SRT", func() {
		if len(entries) == 0 { status.SetText("请先加载字幕文件"); return }
		d := dialog.NewFileSave(func(wc fyne.URIWriteCloser, err error) {
			if err != nil || wc == nil { return }
			defer wc.Close()
			wc.Write([]byte(exportSrt(entries, modeSel.Selected)))
			status.SetText("已导出")
		}, w)
		base := strings.TrimSuffix(filename, ".srt")
		d.SetFileName(fmt.Sprintf("【已翻译-%s】%s.srt", langEntry.Text, base))
		d.Show()
	})

	top := container.NewBorder(nil, nil,
		container.NewHBox(openBtn, status), nil)
	opts := container.NewHBox(
		widget.NewLabel("目标语言："), container.NewMax(langEntry),
		widget.NewLabel("最多词数："), container.NewMax(maxWords),
		modeSel,
	)
	actions := container.NewHBox(previewBtn, exportBtn)

	right := container.NewBorder(
		container.NewVBox(
			widget.NewLabelWithStyle("译文", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
			widget.NewLabel("格式：[编号] 文本"),
			transInput, applyBtn,
		),
		nil, nil, nil,
	)

	content := container.NewBorder(
		container.NewVBox(top, opts, widget.NewSeparator()),
		container.NewVBox(widget.NewSeparator(), actions),
		nil, right,
		container.NewVSplit(
			container.NewVScroll(table),
			container.NewVScroll(output),
		),
	)

	w.SetContent(content)
	w.ShowAndRun()
}

var _ = os.Exit
