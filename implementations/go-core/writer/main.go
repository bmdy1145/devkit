// Writer 内核版（Go）
//
// 版本：A1_I_Φ5_Go_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ5/deepseek_A1_I_Φ5_CN.html
//
// 只实现纯逻辑内核：书籍 / 卷 / 章节结构的 JSON 持久化、字数统计、
// 章节排序、跨卷移动、引用管理、提示词模板合成。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync/atomic"
	"time"
	"unicode"
)

type Book struct {
	ID        string `json:"id"`
	Title     string `json:"title"`
	Author    string `json:"author,omitempty"`
	UpdatedAt int64  `json:"updated_at,omitempty"`
}

type Volume struct {
	ID     string `json:"id"`
	BookID string `json:"book_id"`
	Title  string `json:"title"`
	Order  int    `json:"order"`
}

type Chapter struct {
	ID        string `json:"id"`
	BookID    string `json:"book_id"`
	VolumeID  string `json:"volume_id"`
	Title     string `json:"title"`
	Order     int    `json:"order"`
	WordCount int64  `json:"word_count,omitempty"`
	UpdatedAt int64  `json:"updated_at,omitempty"`
	Text      string `json:"text,omitempty"`
}

type Entity struct {
	ID          string `json:"id"`
	BookID      string `json:"book_id"`
	Name        string `json:"name"`
	Kind        string `json:"kind,omitempty"`
	Description string `json:"description,omitempty"`
}

type Library struct {
	Books    []Book    `json:"books"`
	Volumes  []Volume  `json:"volumes"`
	Chapters []Chapter `json:"chapters"`
	Entities []Entity  `json:"entities"`
}

var counter uint64

func genID(prefix string) string {
	n := atomic.AddUint64(&counter, 1)
	return fmt.Sprintf("%s_%d_%d", prefix, time.Now().UnixMilli(), n)
}

func nowTs() int64 { return time.Now().UnixMilli() }

// 与浏览器版一致：CJK 每字算 1 词，拉丁词按整词算。
func countWords(text string) int64 {
	var total int64
	inLatin := false
	for _, r := range text {
		cp := int(r)
		isCJK := (cp >= 0x3400 && cp <= 0x4DBF) ||
			(cp >= 0x4E00 && cp <= 0x9FFF) ||
			(cp >= 0x3040 && cp <= 0x30FF) ||
			(cp >= 0xAC00 && cp <= 0xD7AF) ||
			(cp >= 0xF900 && cp <= 0xFAFF)
		if isCJK {
			total++
			inLatin = false
		} else if unicode.IsLetter(r) || unicode.IsDigit(r) {
			if !inLatin {
				total++
				inLatin = true
			}
		} else {
			inLatin = false
		}
	}
	return total
}

func load(path string) (*Library, error) {
	lib := &Library{}
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return lib, nil
		}
		return nil, err
	}
	if len(data) == 0 {
		return lib, nil
	}
	if err := json.Unmarshal(data, lib); err != nil {
		return nil, err
	}
	return lib, nil
}

func save(path string, lib *Library) error {
	data, err := json.MarshalIndent(lib, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}

func chaptersOf(lib *Library, volID string) []*Chapter {
	var list []*Chapter
	for i := range lib.Chapters {
		if lib.Chapters[i].VolumeID == volID {
			list = append(list, &lib.Chapters[i])
		}
	}
	sort.Slice(list, func(a, b int) bool { return list[a].Order < list[b].Order })
	return list
}

func reorderVolume(lib *Library, volID string) {
	list := chaptersOf(lib, volID)
	for i, ch := range list {
		ch.Order = i
	}
}

// 人称转换的目标人称。key 与 --target 取值、HTML 版 A1_I_Φ5_CN 的
// #povTarget option value 一一对应。
var povTargets = map[string]string{
	"first":  "第一人称（我）",
	"second": "第二人称（你）",
	"third":  "第三人称（他 / 她 / 它）",
}

// 合成「人称转换」提示词，与 HTML 版 A1_I_Φ5_CN 的 pov 模板一致。
func buildPovPrompt(body, chars, target string, keepInner bool) string {
	inner := "不保留：删去目标视角无法感知的心理描写，只保留外在可见的行为与对白"
	if keepInner {
		inner = "保留：原视角的内心活动改写为目标视角可知的部分" +
			"（用表情、动作、语气或外部观察替代直接叙述他人内心）"
	}
	lines := []string{
		"你是一位精通叙述视角的小说编辑。请把下面的正文转换为【" + target + "】，" +
			"情节、人物、场景与对白内容一律不变，只换叙述人称与视角。",
		"",
		"【目标人称】" + target,
		"",
		"【心理描写处理】" + inner,
		"",
		"【相关设定】",
		chars,
		"",
		"【需要转换的正文】",
		body,
		"",
		"【转换规则】",
		"1) 只改人称代词与由此引起的视角变化，不增删情节、不改变人物性格与说话方式；",
		"2) 第一人称：叙述者用「我」，只能写出「我」能感知到的内容" +
			"（看到、听到、想到），不能直接叙述旁人心里在想什么；",
		"3) 第二人称：叙述者用「你」，把读者带入场景，动作与感受都落在「你」身上；",
		"4) 第三人称：叙述者用「他 / 她 / 它」或人物姓名，" +
			"人物之间用姓名或称谓区分，避免代词指向不明；",
		"5) 时间线、场景顺序、对白内容保持原样，" +
			"对白中人物自称按其在故事中的实际人称调整；",
		"6) 转换后通读一遍，确保没有残留的原人称代词、" +
			"没有视角越界、没有半途切换人称。",
		"",
		"【输出要求】直接输出转换后的完整正文，不要加解释、不要加标题、" +
			"不要用「以下是」之类的开场白，便于直接替换当前章。",
	}
	return strings.Join(lines, "\n")
}

func usage() {
	fmt.Println("Writer 内核版（Go）")
	fmt.Println("用法: writer <库文件.json> <子命令> [参数]")
	fmt.Println()
	fmt.Println("子命令:")
	fmt.Println("  init <书名>")
	fmt.Println("  add-volume <书籍ID> <卷名>")
	fmt.Println("  add-chapter <书籍ID> <卷ID> <章节名> [正文文件]")
	fmt.Println("  list <书籍ID>")
	fmt.Println("  stats <书籍ID>")
	fmt.Println("  move-chapter <章节ID> <目标卷ID>")
	fmt.Println("  add-entity <书籍ID> <名称> [类型] [描述]")
	fmt.Println("  prompt <书籍ID> <章节ID>")
	fmt.Println("  pov <书籍ID> <章节ID> [--target first|second|third] [--no-inner]")
	fmt.Println("  reindex <书籍ID>")
}

func main() {
	args := os.Args[1:]
	if len(args) < 2 {
		usage()
		os.Exit(1)
	}
	libPath := args[0]
	cmd := args[1]

	lib, err := load(libPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "读取失败: %v\n", err)
		os.Exit(1)
	}

	fail := func(format string, a ...any) {
		fmt.Fprintf(os.Stderr, format+"\n", a...)
		os.Exit(1)
	}

	switch cmd {
	case "init":
		if len(args) < 3 {
			fail("缺少书名")
		}
		b := Book{ID: genID("book"), Title: args[2], UpdatedAt: nowTs()}
		fmt.Printf("已创建书籍: %s (%s)\n", b.Title, b.ID)
		lib.Books = append(lib.Books, b)

	case "add-volume":
		if len(args) < 4 {
			fail("缺少参数")
		}
		bookID, title := args[2], args[3]
		found := false
		for _, b := range lib.Books {
			if b.ID == bookID {
				found = true
			}
		}
		if !found {
			fail("找不到书籍 %s", bookID)
		}
		order := 0
		for _, v := range lib.Volumes {
			if v.BookID == bookID {
				order++
			}
		}
		v := Volume{ID: genID("vol"), BookID: bookID, Title: title, Order: order}
		fmt.Printf("已新增卷: %s (%s)\n", v.Title, v.ID)
		lib.Volumes = append(lib.Volumes, v)

	case "add-chapter":
		if len(args) < 5 {
			fail("缺少参数")
		}
		bookID, volID, title := args[2], args[3], args[4]
		text := ""
		if len(args) >= 6 {
			if d, err := os.ReadFile(args[5]); err == nil {
				text = string(d)
			}
		}
		ok := false
		for _, v := range lib.Volumes {
			if v.ID == volID {
				ok = true
			}
		}
		if !ok {
			fail("找不到卷 %s", volID)
		}
		order := 0
		for _, c := range lib.Chapters {
			if c.VolumeID == volID {
				order++
			}
		}
		wc := countWords(text)
		ch := Chapter{ID: genID("ch"), BookID: bookID, VolumeID: volID,
			Title: title, Order: order, WordCount: wc, UpdatedAt: nowTs(), Text: text}
		fmt.Printf("已新增章节: %s (%s) · %d 字\n", ch.Title, ch.ID, wc)
		lib.Chapters = append(lib.Chapters, ch)

	case "list":
		if len(args) < 3 {
			fail("缺少书籍ID")
		}
		bookID := args[2]
		var book *Book
		for i := range lib.Books {
			if lib.Books[i].ID == bookID {
				book = &lib.Books[i]
			}
		}
		if book == nil {
			fail("找不到书籍")
		}
		fmt.Printf("书籍: %s (%s)\n", book.Title, book.ID)
		var vols []Volume
		for _, v := range lib.Volumes {
			if v.BookID == bookID {
				vols = append(vols, v)
			}
		}
		sort.Slice(vols, func(a, b int) bool { return vols[a].Order < vols[b].Order })
		for _, v := range vols {
			fmt.Printf("  卷: %s (order %d)\n", v.Title, v.Order)
			for _, c := range chaptersOf(lib, v.ID) {
				fmt.Printf("    - [%d] %s · %d 字\n", c.Order, c.Title, c.WordCount)
			}
		}

	case "stats":
		if len(args) < 3 {
			fail("缺少书籍ID")
		}
		bookID := args[2]
		var n int
		var total, chars int64
		for _, c := range lib.Chapters {
			if c.BookID == bookID {
				n++
				total += c.WordCount
				chars += int64(len([]rune(c.Text)))
			}
		}
		fmt.Printf("章节数: %d\n总字数: %d\n总字符: %d\n", n, total, chars)

	case "move-chapter":
		if len(args) < 4 {
			fail("缺少参数")
		}
		chID, targetVol := args[2], args[3]
		idx := -1
		for i := range lib.Chapters {
			if lib.Chapters[i].ID == chID {
				idx = i
			}
		}
		if idx < 0 {
			fail("找不到章节")
		}
		ok := false
		for _, v := range lib.Volumes {
			if v.ID == targetVol {
				ok = true
			}
		}
		if !ok {
			fail("找不到目标卷 %s", targetVol)
		}
		sourceVol := lib.Chapters[idx].VolumeID
		newOrder := 0
		for _, c := range lib.Chapters {
			if c.VolumeID == targetVol {
				newOrder++
			}
		}
		lib.Chapters[idx].VolumeID = targetVol
		lib.Chapters[idx].Order = newOrder
		reorderVolume(lib, targetVol)
		reorderVolume(lib, sourceVol)
		fmt.Println("已将章节移至目标卷，并重排源卷与目标卷的顺序")

	case "add-entity":
		if len(args) < 4 {
			fail("缺少参数")
		}
		bookID, name := args[2], args[3]
		kind, desc := "其他", ""
		if len(args) >= 5 {
			kind = args[4]
		}
		if len(args) >= 6 {
			desc = args[5]
		}
		e := Entity{ID: genID("ent"), BookID: bookID, Name: name, Kind: kind, Description: desc}
		fmt.Printf("已添加资料: %s (%s)\n", e.Name, e.ID)
		lib.Entities = append(lib.Entities, e)

	case "prompt":
		if len(args) < 4 {
			fail("缺少参数")
		}
		bookID, chID := args[2], args[3]
		var ch *Chapter
		for i := range lib.Chapters {
			if lib.Chapters[i].ID == chID {
				ch = &lib.Chapters[i]
			}
		}
		if ch == nil {
			fail("找不到章节")
		}
		list := chaptersOf(lib, ch.VolumeID)
		pos := 0
		for i, c := range list {
			if c.ID == chID {
				pos = i
			}
		}
		prev := "（本章为卷首，无上一章）"
		if pos > 0 {
			r := []rune(list[pos-1].Text)
			if len(r) > 500 {
				r = r[len(r)-500:]
			}
			prev = string(r)
		}
		var entities []Entity
		for _, e := range lib.Entities {
			if e.BookID == bookID {
				entities = append(entities, e)
			}
		}
		chars := "（未填写）"
		if len(entities) > 0 {
			chars = ""
			for _, e := range entities {
				chars += fmt.Sprintf("- %s（%s）：%s\n", e.Name, e.Kind, e.Description)
			}
		}
		body := ch.Text
		if body == "" {
			body = "（当前章为空）"
		}
		fmt.Println("你是一位与作者合写的小说作者。请续写下一段情节。")
		fmt.Println()
		fmt.Println("【设定】")
		fmt.Println(chars)
		fmt.Println("【上一章结尾】")
		fmt.Println(prev)
		fmt.Println()
		fmt.Println("【本章已有正文】")
		fmt.Println(body)

	case "pov":
		if len(args) < 4 {
			fail("缺少参数")
		}
		bookID, chID := args[2], args[3]
		targetKey := "third"
		keepInner := true
		rest := args[4:]
		for i := 0; i < len(rest); i++ {
			switch rest[i] {
			case "--target":
				if i+1 >= len(rest) {
					fail("--target 缺少取值")
				}
				targetKey = rest[i+1]
				i++
			case "--no-inner":
				keepInner = false
			default:
				fail("无法识别的参数: %s", rest[i])
			}
		}
		target, ok := povTargets[targetKey]
		if !ok {
			fail("目标人称无效：%s（可选 first / second / third）", targetKey)
		}
		var ch *Chapter
		for i := range lib.Chapters {
			if lib.Chapters[i].ID == chID {
				ch = &lib.Chapters[i]
			}
		}
		if ch == nil {
			fail("找不到章节")
		}
		var entities []Entity
		for _, e := range lib.Entities {
			if e.BookID == bookID {
				entities = append(entities, e)
			}
		}
		chars := "（未填写）"
		if len(entities) > 0 {
			parts := make([]string, 0, len(entities))
			for _, e := range entities {
				parts = append(parts, fmt.Sprintf("- %s（%s）：%s", e.Name, e.Kind, e.Description))
			}
			chars = strings.Join(parts, "\n")
		}
		body := ch.Text
		if body == "" {
			body = "（当前章为空）"
		}
		fmt.Println(buildPovPrompt(body, chars, target, keepInner))

	case "reindex":
		if len(args) < 3 {
			fail("缺少书籍ID")
		}
		bookID := args[2]
		for _, v := range lib.Volumes {
			if v.BookID == bookID {
				reorderVolume(lib, v.ID)
			}
		}
		fmt.Println("已重排全部卷的章节顺序")

	default:
		fail("未知子命令: %s", cmd)
	}

	if err := save(libPath, lib); err != nil {
		fmt.Fprintf(os.Stderr, "保存失败: %v\n", err)
		os.Exit(1)
	}
}
