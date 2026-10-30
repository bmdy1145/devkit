// Writer 全功能版（Go / Fyne）
//
// 版本：A1_I_Φ3_Go_CN
// 对应 HTML 版：projects/writer/code/A1_I_Φ3/deepseek_A1_I_Φ3_CN.html
//
// 图形界面版：左侧章节树、中间正文编辑、右侧资料与提示词、字数统计。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"sync/atomic"
	"time"
	"unicode"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/widget"
)

type Book struct{ ID, Title string }

type Volume struct {
	ID, BookID, Title string
	Order             int
}

type Chapter struct {
	ID, BookID, VolumeID, Title, Text string
	Order                             int
	WordCount                         int64
}

type Entity struct{ ID, BookID, Name, Kind, Description string }

type Library struct {
	Books    []Book    `json:"books"`
	Volumes  []Volume  `json:"volumes"`
	Chapters []Chapter `json:"chapters"`
	Entities []Entity  `json:"entities"`
}

var ctr uint64

func genID(p string) string {
	n := atomic.AddUint64(&ctr, 1)
	return fmt.Sprintf("%s_%d_%d", p, time.Now().UnixMilli(), n)
}

func countWords(text string) int64 {
	var total int64
	inLatin := false
	for _, r := range text {
		cp := int(r)
		cjk := (cp >= 0x3400 && cp <= 0x4DBF) || (cp >= 0x4E00 && cp <= 0x9FFF) ||
			(cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0xAC00 && cp <= 0xD7AF) ||
			(cp >= 0xF900 && cp <= 0xFAFF)
		if cjk {
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

func main() {
	a := app.New()
	w := a.NewWindow("Writer（Go / Fyne 版）")
	w.Resize(fyne.NewSize(1200, 800))

	lib := &Library{}
	var path string
	var selID string

	status := widget.NewLabel("就绪")
	treeBox := container.NewVBox()
	titleEntry := widget.NewEntry()
	textArea := widget.NewMultiLineEntry()
	textArea.SetMinRowsVisible(20)
	promptArea := widget.NewMultiLineEntry()
	promptArea.SetMinRowsVisible(10)
	promptArea.Disable()
	entList := widget.NewLabel("（空）")

	saveLib := func() {
		if path == "" {
			return
		}
		if selID != "" {
			for i := range lib.Chapters {
				if lib.Chapters[i].ID == selID {
					lib.Chapters[i].Title = titleEntry.Text
					lib.Chapters[i].Text = textArea.Text
					lib.Chapters[i].WordCount = countWords(textArea.Text)
				}
			}
		}
		data, _ := json.MarshalIndent(lib, "", "  ")
		os.WriteFile(path, data, 0644)
		status.SetText("已保存")
	}

	refresh := func() {
		treeBox.RemoveAll()
		vols := append([]Volume{}, lib.Volumes...)
		sort.Slice(vols, func(i, j int) bool { return vols[i].Order < vols[j].Order })
		for _, v := range vols {
			treeBox.Add(widget.NewLabelWithStyle("卷："+v.Title, fyne.TextAlignLeading, fyne.TextStyle{Bold: true}))
			var chs []Chapter
			for _, c := range lib.Chapters {
				if c.VolumeID == v.ID {
					chs = append(chs, c)
				}
			}
			sort.Slice(chs, func(i, j int) bool { return chs[i].Order < chs[j].Order })
			for _, c := range chs {
				cid := c.ID
				btn := widget.NewButton(fmt.Sprintf("  %s · %d 字", c.Title, c.WordCount), func() {
					for _, x := range lib.Chapters {
						if x.ID == cid {
							selID = cid
							titleEntry.SetText(x.Title)
							textArea.SetText(x.Text)
						}
					}
				})
				treeBox.Add(btn)
			}
		}
		var ents []string
		for _, e := range lib.Entities {
			ents = append(ents, fmt.Sprintf("• %s（%s）", e.Name, e.Kind))
		}
		if len(ents) == 0 {
			entList.SetText("（空）")
		} else {
			s := ""
			for _, e := range ents {
				s += e + "\n"
			}
			entList.SetText(s)
		}
		treeBox.Refresh()
	}

	openBtn := widget.NewButton("打开库…", func() {
		d := dialog.NewFileOpen(func(rc fyne.URIReadCloser, err error) {
			if err != nil || rc == nil {
				return
			}
			defer rc.Close()
			p := rc.URI().Path()
			data, _ := os.ReadFile(p)
			if len(data) > 0 {
				json.Unmarshal(data, lib)
			}
			path = p
			status.SetText("已打开: " + p)
			refresh()
		}, w)
		d.SetFilter(storage.NewExtensionFileFilter([]string{".json"}))
		d.Show()
	})

	saveBtn := widget.NewButton("保存", saveLib)

	addVol := widget.NewEntry()
	addVol.SetPlaceHolder("新卷名")
	addVolBtn := widget.NewButton("+卷", func() {
		if addVol.Text == "" {
			return
		}
		bookID := ""
		if len(lib.Books) > 0 {
			bookID = lib.Books[0].ID
		} else {
			lib.Books = append(lib.Books, Book{ID: genID("book"), Title: "默认书"})
			bookID = lib.Books[0].ID
		}
		lib.Volumes = append(lib.Volumes, Volume{ID: genID("vol"), BookID: bookID, Title: addVol.Text, Order: len(lib.Volumes)})
		addVol.SetText("")
		refresh()
		saveLib()
	})

	addCh := widget.NewEntry()
	addCh.SetPlaceHolder("新章节名")
	addChBtn := widget.NewButton("+章", func() {
		if addCh.Text == "" || len(lib.Volumes) == 0 {
			return
		}
		vol := lib.Volumes[len(lib.Volumes)-1]
		n := 0
		for _, c := range lib.Chapters {
			if c.VolumeID == vol.ID {
				n++
			}
		}
		lib.Chapters = append(lib.Chapters, Chapter{ID: genID("ch"), BookID: vol.BookID, VolumeID: vol.ID,
			Title: addCh.Text, Order: n})
		addCh.SetText("")
		refresh()
		saveLib()
	})

	entName := widget.NewEntry()
	entName.SetPlaceHolder("名称")
	entKind := widget.NewEntry()
	entKind.SetPlaceHolder("类型")
	entDesc := widget.NewEntry()
	entDesc.SetPlaceHolder("描述")
	addEntBtn := widget.NewButton("添加资料", func() {
		if entName.Text == "" {
			return
		}
		bookID := ""
		if len(lib.Books) > 0 {
			bookID = lib.Books[0].ID
		}
		kind := entKind.Text
		if kind == "" {
			kind = "其他"
		}
		lib.Entities = append(lib.Entities, Entity{ID: genID("ent"), BookID: bookID,
			Name: entName.Text, Kind: kind, Description: entDesc.Text})
		entName.SetText("")
		entKind.SetText("")
		entDesc.SetText("")
		refresh()
		saveLib()
	})

	promptBtn := widget.NewButton("生成续写提示词", func() {
		if selID == "" {
			return
		}
		var ch *Chapter
		for i := range lib.Chapters {
			if lib.Chapters[i].ID == selID {
				ch = &lib.Chapters[i]
			}
		}
		if ch == nil {
			return
		}
		var list []Chapter
		for _, c := range lib.Chapters {
			if c.VolumeID == ch.VolumeID {
				list = append(list, c)
			}
		}
		sort.Slice(list, func(i, j int) bool { return list[i].Order < list[j].Order })
		pos := 0
		for i, c := range list {
			if c.ID == selID {
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
		chars := "（未填写）"
		var es []string
		for _, e := range lib.Entities {
			if e.BookID == ch.BookID {
				es = append(es, fmt.Sprintf("- %s（%s）：%s", e.Name, e.Kind, e.Description))
			}
		}
		if len(es) > 0 {
			chars = ""
			for _, e := range es {
				chars += e + "\n"
			}
		}
		body := ch.Text
		if body == "" {
			body = "（当前章为空）"
		}
		promptArea.SetText(fmt.Sprintf("你是一位与作者合写的小说作者。请续写下一段情节。\n\n【设定】\n%s\n\n【上一章结尾】\n%s\n\n【本章已有正文】\n%s", chars, prev, body))
	})

	textArea.OnChanged = func(string) {
		n := countWords(textArea.Text)
		status.SetText(fmt.Sprintf("本章 %d 字 · %d 字符", n, len([]rune(textArea.Text))))
	}

	left := container.NewBorder(
		container.NewVBox(widget.NewLabelWithStyle("章节树", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})),
		container.NewVBox(widget.NewSeparator(), addVol, addVolBtn, addCh, addChBtn),
		nil, nil,
		container.NewVScroll(treeBox),
	)
	right := container.NewBorder(
		container.NewVBox(widget.NewLabelWithStyle("资料", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}), entList,
			widget.NewSeparator(), entName, entKind, entDesc, addEntBtn,
			widget.NewSeparator(), promptBtn),
		nil, nil, nil,
		container.NewVScroll(promptArea),
	)
	center := container.NewBorder(
		container.NewVBox(container.NewHBox(openBtn, saveBtn, status), widget.NewSeparator(), titleEntry),
		nil, nil, nil,
		textArea,
	)

	split := container.NewHSplit(container.NewHSplit(left, center), right)
	split.SetOffset(0.2)
	w.SetContent(split)
	w.ShowAndRun()
}
