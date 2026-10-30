// SubMerge Pro 内核版（Go）
//
// 版本：A1_II_Φ10_Go_CN
// 对应 HTML 版：projects/submerge-pro/code/A1_II_Φ10/deepseek_html_20261006_d1ca99_Fix.html
//
// 只实现纯逻辑内核：SRT/BCC 解析、双语拆分、时间轴修正、译文合并、SRT 导出。
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
	"unicode"
)

type Entry struct {
	Index      int
	Start      string
	End        string
	Text       string
	Translated string
	HasTrans   bool
}

func isCJK(r rune) bool { return r >= 0x4e00 && r <= 0x9fff }

func countWords(text string) int {
	total := 0
	var cjk []rune
	var latin []rune
	flushCJK := func() {
		if len(cjk) > 0 {
			total += (len(cjk) + 1) / 2
			cjk = cjk[:0]
		}
	}
	flushLatin := func() {
		// 与 HTML 参考实现一致：非 CJK 段按 [A-Za-z0-9]+(?:'[A-Za-z]+)? 计数，
		// 所以 "don't" 记 1 个词、"A1_V_Φ10" 记 3 个（A1 / V / 10）。
		if len(latin) > 0 {
			total += len(reWord.FindAllString(string(latin), -1))
			latin = latin[:0]
		}
	}
	for _, r := range text {
		if isCJK(r) {
			flushLatin()
			cjk = append(cjk, r)
		} else {
			flushCJK()
			latin = append(latin, r)
		}
	}
	flushCJK()
	flushLatin()
	return total
}

func tokenize(text string) []string {
	var tokens []string
	var cjk []rune
	var latin []rune
	flushCJK := func() {
		for i := 0; i < len(cjk); i += 2 {
			end := i + 2
			if end > len(cjk) {
				end = len(cjk)
			}
			tokens = append(tokens, string(cjk[i:end]))
		}
		cjk = cjk[:0]
	}
	flushLatin := func() {
		// 与 HTML 参考实现一致：[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S
		// 单词整体作为一个 token，其余非空白字符各自成 token（逗号、句号不并入相邻单词）
		for _, w := range reToken.FindAllString(string(latin), -1) {
			tokens = append(tokens, w)
		}
		latin = latin[:0]
	}
	for _, r := range text {
		if isCJK(r) {
			flushLatin()
			cjk = append(cjk, r)
		} else if unicode.IsSpace(r) {
			flushCJK()
			if len(latin) > 0 {
				latin = append(latin, ' ')
			}
		} else {
			flushCJK()
			latin = append(latin, r)
		}
	}
	flushCJK()
	flushLatin()
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

var reWord = regexp.MustCompile(`[A-Za-z0-9]+(?:'[A-Za-z]+)?`)
var reToken = regexp.MustCompile(`[A-Za-z0-9]+(?:'[A-Za-z]+)?|\S`)
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
					oc = append(oc, o[oi])
					oi++
					tc = append(tc, t[ti])
					ti++
					words += 2
				} else {
					break
				}
			} else if canO {
				if words+1 <= maxWords {
					oc = append(oc, o[oi])
					oi++
					words++
				} else {
					break
				}
			} else if canT {
				if words+1 <= maxWords {
					tc = append(tc, t[ti])
					ti++
					words++
				} else {
					break
				}
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
	if len(parts) != 3 {
		return 0
	}
	h, _ := strconv.ParseInt(strings.TrimSpace(parts[0]), 10, 64)
	m, _ := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64)
	sp := strings.TrimSpace(parts[2])
	var sec, ms int64
	if i := strings.Index(sp, ","); i >= 0 {
		sec, _ = strconv.ParseInt(sp[:i], 10, 64)
		frac := sp[i+1:]
		for len(frac) < 3 {
			frac += "0"
		}
		ms, _ = strconv.ParseInt(frac[:3], 10, 64)
	} else if i := strings.Index(sp, "."); i >= 0 {
		sec, _ = strconv.ParseInt(sp[:i], 10, 64)
		frac := sp[i+1:]
		for len(frac) < 2 {
			frac += "0"
		}
		fr, _ := strconv.ParseFloat(frac[:2], 64)
		ms = int64(fr*40 + 0.5)
	} else {
		sec, _ = strconv.ParseInt(sp, 10, 64)
	}
	return (h*3600+m*60+sec)*1000 + ms
}

func msToTime(ms int64) string {
	h := ms / 3600000
	ms %= 3600000
	m := ms / 60000
	ms %= 60000
	s := ms / 1000
	return fmt.Sprintf("%02d:%02d:%02d,%03d", h, m, s, ms%1000)
}

var reTime = regexp.MustCompile(`^(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})$`)
var reIdx = regexp.MustCompile(`^\[(\d+)\]\s*(.*)$`)

func parseSubtitle(content string) []Entry {
	clean := strings.TrimPrefix(content, "\ufeff")
	clean = strings.ReplaceAll(clean, "\r\n", "\n")
	clean = strings.ReplaceAll(clean, "\r", "\n")
	var entries []Entry
	seen := map[int]bool{}
	for _, block := range strings.Split(clean, "\n\n") {
		var lines []string
		for _, l := range strings.Split(block, "\n") {
			if t := strings.TrimSpace(l); t != "" {
				lines = append(lines, t)
			}
		}
		if len(lines) < 3 {
			continue
		}
		if _, err := strconv.Atoi(lines[0]); err != nil {
			continue
		}
		m := reTime.FindStringSubmatch(lines[1])
		if m == nil {
			continue
		}
		idx, _ := strconv.Atoi(lines[0])
		if seen[idx] {
			continue
		}
		seen[idx] = true
		start := strings.Replace(m[1], ".", ",", 1)
		end := strings.Replace(m[2], ".", ",", 1)
		if timeToMs(start) >= timeToMs(end) {
			end = msToTime(timeToMs(start) + 1)
		}
		text := strings.TrimSpace(strings.Join(lines[2:], "\n"))
		if text == "" {
			continue
		}
		entries = append(entries, Entry{Index: idx, Start: start, End: end, Text: text})
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Index < entries[j].Index })
	return entries
}

func applyTranslation(entries []Entry, trans string) int {
	m := map[int]string{}
	cur := -1
	var buf []string
	flush := func() {
		if cur >= 0 {
			m[cur] = strings.TrimSpace(strings.Join(buf, "\n"))
		}
	}
	for _, line := range strings.Split(trans, "\n") {
		t := strings.TrimSpace(line)
		if mm := reIdx.FindStringSubmatch(t); mm != nil {
			flush()
			cur, _ = strconv.Atoi(mm[1])
			buf = nil
			if r := strings.TrimSpace(mm[2]); r != "" {
				buf = append(buf, r)
			}
			continue
		}
		if cur >= 0 && t != "" {
			buf = append(buf, t)
		}
	}
	flush()
	applied := 0
	for i := range entries {
		if v, ok := m[entries[i].Index]; ok {
			entries[i].Translated = v
			entries[i].HasTrans = true
			applied++
		}
	}
	return applied
}

func applyTimeFix(entries []Entry, strategy string) []Entry {
	if strategy == "keep" || strategy == "" {
		return entries
	}
	if strategy == "delete" {
		var out []Entry
		for _, e := range entries {
			if timeToMs(e.End)-timeToMs(e.Start) >= 10 {
				out = append(out, e)
			}
		}
		return out
	}
	if strategy == "extend" {
		for i := range entries {
			s := timeToMs(entries[i].Start)
			e := timeToMs(entries[i].End)
			if e-s < 10 {
				newEnd := s + 10
				entries[i].End = msToTime(newEnd)
				shift := newEnd - e
				for j := i + 1; j < len(entries); j++ {
					entries[j].Start = msToTime(timeToMs(entries[j].Start) + shift)
					entries[j].End = msToTime(timeToMs(entries[j].End) + shift)
				}
			}
		}
	}
	return entries
}

func exportSRT(entries []Entry, mode string) string {
	var b strings.Builder
	for _, e := range entries {
		var text string
		switch mode {
		case "orig":
			text = e.Text
		case "trans":
			text = e.Translated
		default:
			if e.HasTrans && e.Text != "" {
				text = e.Text + "\n" + e.Translated
			} else if e.HasTrans {
				text = e.Translated
			} else {
				text = e.Text
			}
		}
		fmt.Fprintf(&b, "%d\n%s --> %s\n%s\n\n", e.Index, e.Start, e.End, text)
	}
	return b.String()
}

func usage() {
	fmt.Println("SubMerge Pro 内核版（Go）")
	fmt.Println("用法:")
	fmt.Println("  submerge parse <字幕文件>")
	fmt.Println("  submerge export <字幕文件> [--trans 译文] [--mode both|orig|trans] [--time-fix keep|delete|extend]")
	fmt.Println("  submerge merge-prompt <字幕文件> [--trans 译文] [--max N]")
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		usage()
		if len(args) == 0 {
			os.Exit(1)
		}
		return
	}
	cmd := args[0]
	var file, transFile, mode, timeFix string
	mode = "both"
	timeFix = "keep"
	maxWords := 10
	for i := 1; i < len(args); i++ {
		switch args[i] {
		case "--trans":
			i++
			if i < len(args) {
				transFile = args[i]
			}
		case "--mode":
			i++
			if i < len(args) {
				mode = args[i]
			}
		case "--time-fix":
			i++
			if i < len(args) {
				timeFix = args[i]
			}
		case "--max":
			i++
			if i < len(args) {
				maxWords, _ = strconv.Atoi(args[i])
			}
		default:
			if !strings.HasPrefix(args[i], "--") && file == "" {
				file = args[i]
			}
		}
	}
	if file == "" {
		fmt.Fprintln(os.Stderr, "错误：未指定字幕文件")
		os.Exit(1)
	}
	data, err := os.ReadFile(file)
	if err != nil {
		fmt.Fprintf(os.Stderr, "无法读取 %s: %v\n", file, err)
		os.Exit(1)
	}
	entries := parseSubtitle(string(data))
	if len(entries) == 0 {
		fmt.Fprintln(os.Stderr, "解析失败：未找到字幕条目")
		os.Exit(1)
	}
	entries = applyTimeFix(entries, timeFix)

	if transFile != "" {
		td, err := os.ReadFile(transFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "无法读取 %s: %v\n", transFile, err)
			os.Exit(1)
		}
		n := applyTranslation(entries, string(td))
		fmt.Printf("已应用 %d 条译文\n", n)
	}

	switch cmd {
	case "parse":
		total := 0
		for _, e := range entries {
			total += countWords(e.Text)
		}
		fmt.Printf("条目数: %d\n总词数: %d\n", len(entries), total)
		fmt.Printf("首条: [%d] %s --> %s | %s\n", entries[0].Index, entries[0].Start, entries[0].End, entries[0].Text)
		last := entries[len(entries)-1]
		fmt.Printf("末条: [%d] %s --> %s | %s\n", last.Index, last.Start, last.End, last.Text)
	case "export":
		fmt.Print(exportSRT(entries, mode))
	case "merge-prompt":
		for _, e := range entries {
			for _, c := range splitPaired(e.Text, e.Translated, maxWords) {
				body := c[0]
				if c[1] != "" {
					body = c[0] + "\n" + c[1]
				}
				fmt.Printf("[%d] %s\n", e.Index, strings.TrimSpace(body))
			}
		}
	default:
		fmt.Fprintf(os.Stderr, "错误：未知子命令 %s\n", cmd)
		usage()
		os.Exit(1)
	}
}
