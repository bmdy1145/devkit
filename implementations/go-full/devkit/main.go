// DevKit 全功能版（Go / Fyne）
//
// 版本：A1_V_Φ9_Fix_Go_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 图形界面版：项目/页签、灵感、组合预览与复制、代码与结果编辑、
// 九款主题切换、配置导入导出。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sync/atomic"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/widget"
)

const currentVersion = "A1_V_Φ9_Fix_Go_CN"

var themes = []string{"Clean", "Glass", "Neon", "Mono", "Material", "Minimal", "Premium", "Shadcn", "Baseline"}

var templates = [][2]string{
	{"版本规划", "你是一位资深的软件版本管理专家。请为下面的项目制定版本规划。"},
	{"需求分析", "你是一位资深系统分析师。请对下面需求做全面分析。"},
	{"安全审计", "你是一位持有 OSCP 认证的安全专家。请审计下面的代码。"},
	{"性能审计", "你是一位性能优化专家。请审计下面的代码。"},
	{"结构重构", "你是一位资深架构师。请重构下面的代码。"},
	{"单元测试", "请为下面的代码编写单元测试。"},
	{"空白", ""},
}

type Tab struct {
	ID          string `json:"id"`
	Type        string `json:"type"`
	Inspiration string `json:"inspiration"`
}

type Project struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Tabs   []Tab  `json:"tabs"`
	Code   string `json:"code"`
	Result string `json:"result"`
}

type Settings struct {
	Theme string `json:"theme"`
}

type State struct {
	Version         string    `json:"version"`
	ActiveProjectID string    `json:"activeProjectId"`
	Projects        []Project `json:"projects"`
	Settings        Settings  `json:"settings"`
}

var ctr uint64

func genID(p string) string {
	n := atomic.AddUint64(&ctr, 1)
	return fmt.Sprintf("%s_%d_%d", p, time.Now().UnixMilli(), n)
}

func defaultState() *State {
	tabs := make([]Tab, 0, len(templates))
	for _, t := range templates {
		tabs = append(tabs, Tab{ID: genID("tab"), Type: t[0], Inspiration: ""})
	}
	return &State{
		Version:         currentVersion,
		ActiveProjectID: "proj_1",
		Projects: []Project{{
			ID: "proj_1", Name: "默认项目", Tabs: tabs,
		}},
		Settings: Settings{Theme: "Clean"},
	}
}

func main() {
	a := app.New()
	w := a.NewWindow("DevKit（Go / Fyne 版）")
	w.Resize(fyne.NewSize(1200, 820))

	state := defaultState()
	var path string
	tabIdx := 0

	status := widget.NewLabel("就绪")
	themeSel := widget.NewSelect(themes, nil)
	themeSel.SetSelected("Clean")

	tabList := widget.NewList(
		func() int {
			p := state.Projects[0]
			return len(p.Tabs)
		},
		func() fyne.CanvasObject { return widget.NewLabel("") },
		func(i widget.ListItemID, o fyne.CanvasObject) {
			p := state.Projects[0]
			if i < len(p.Tabs) {
				o.(*widget.Label).SetText(p.Tabs[i].Type)
			}
		},
	)
	tabList.OnSelected = func(i widget.ListItemID) { tabIdx = i }

	inspEntry := widget.NewMultiLineEntry()
	inspEntry.SetMinRowsVisible(4)
	previewBox := widget.NewMultiLineEntry()
	previewBox.SetMinRowsVisible(10)
	previewBox.Disable()
	codeEntry := widget.NewMultiLineEntry()
	codeEntry.SetMinRowsVisible(16)
	resultEntry := widget.NewMultiLineEntry()
	resultEntry.SetMinRowsVisible(6)
	countLabel := widget.NewLabel("")

	compose := func() string {
		p := state.Projects[0]
		if tabIdx >= len(p.Tabs) {
			return ""
		}
		tab := p.Tabs[tabIdx]
		head := ""
		for _, t := range templates {
			if t[0] == tab.Type {
				head = t[1]
				break
			}
		}
		insp := tab.Inspiration
		if insp == "" {
			insp = "（无需求）"
		}
		code := p.Code
		if code == "" {
			code = "（无代码）"
		}
		if head == "" {
			return fmt.Sprintf("需求：%s\n\n代码：\n%s", insp, code)
		}
		return fmt.Sprintf("%s\n\n需求：%s\n\n代码：\n%s", head, insp, code)
	}

	refresh := func() {
		previewBox.SetText(compose())
		p := state.Projects[0]
		if tabIdx < len(p.Tabs) {
			inspEntry.SetText(p.Tabs[tabIdx].Inspiration)
		}
		codeEntry.SetText(p.Code)
		resultEntry.SetText(p.Result)
		countLabel.SetText(fmt.Sprintf("%d 字符", len(p.Code)))
		tabList.Refresh()
	}

	syncFromUI := func() {
		p := &state.Projects[0]
		if tabIdx < len(p.Tabs) {
			p.Tabs[tabIdx].Inspiration = inspEntry.Text
		}
		p.Code = codeEntry.Text
		p.Result = resultEntry.Text
	}

	inspEntry.OnChanged = func(string) {
		syncFromUI()
		previewBox.SetText(compose())
	}
	codeEntry.OnChanged = func(string) {
		syncFromUI()
		previewBox.SetText(compose())
		countLabel.SetText(fmt.Sprintf("%d 字符", len(codeEntry.Text)))
	}
	themeSel.OnChanged = func(s string) { state.Settings.Theme = s }

	save := func() {
		if path == "" {
			return
		}
		syncFromUI()
		state.Version = currentVersion
		data, _ := json.MarshalIndent(state, "", "  ")
		os.WriteFile(path, data, 0644)
		status.SetText("已保存")
	}

	top := container.NewHBox(
		widget.NewLabel("主题："), themeSel,
		widget.NewButton("新建项目", func() {
			var tabs []Tab
			for _, t := range templates {
				tabs = append(tabs, Tab{ID: genID("tab"), Type: t[0]})
			}
			state.Projects = append(state.Projects, Project{
				ID: genID("proj"), Name: "新项目", Tabs: tabs,
			})
			tabIdx = 0
			refresh()
		}),
		widget.NewButton("打开配置…", func() {
			d := dialog.NewFileOpen(func(rc fyne.URIReadCloser, err error) {
				if err != nil || rc == nil {
					return
				}
				defer rc.Close()
				p := rc.URI().Path()
				data, _ := os.ReadFile(p)
				var st State
				if json.Unmarshal(data, &st) == nil && len(st.Projects) > 0 {
					*state = st
					path = p
					tabIdx = 0
					refresh()
					status.SetText("已导入")
				}
			}, w)
			d.SetFilter(storage.NewExtensionFileFilter([]string{".json"}))
			d.Show()
		}),
		widget.NewButton("导出配置", func() {
			d := dialog.NewFileSave(func(wc fyne.URIWriteCloser, err error) {
				if err != nil || wc == nil {
					return
				}
				defer wc.Close()
				path = wc.URI().Path()
				save()
			}, w)
			d.SetFileName("devkit_config.json")
			d.Show()
		}),
		status,
	)

	side := container.NewBorder(
		container.NewVBox(
			widget.NewLabelWithStyle("工作流步骤", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		),
		container.NewVBox(
			widget.NewSeparator(),
			widget.NewLabel("灵感"),
			inspEntry,
			widget.NewLabel("组合预览"),
			widget.NewButton("复制预览", func() {
				w.Clipboard().SetContent(compose())
				status.SetText("已复制")
			}),
		),
		nil, nil,
		container.NewVScroll(tabList),
	)

	center := container.NewBorder(
		container.NewVBox(widget.NewLabelWithStyle("代码编辑区", fyne.TextAlignLeading, fyne.TextStyle{Bold: true})),
		container.NewVBox(countLabel, widget.NewButton("用结果覆盖代码区", func() {
			if resultEntry.Text != "" {
				codeEntry.SetText(resultEntry.Text)
				resultEntry.SetText("")
				syncFromUI()
			}
		})),
		nil, nil,
		container.NewVSplit(codeEntry, container.NewBorder(
			widget.NewLabel("AI 处理结果"), nil, nil, nil, resultEntry)),
	)

	split := container.NewHSplit(side, center)
	split.SetOffset(0.32)
	previewWrap := container.NewBorder(nil, nil, nil, nil, previewBox)
	leftWrap := container.NewVSplit(side, previewWrap)
	leftWrap.SetOffset(0.55)

	content := container.NewBorder(top, nil, nil, nil, container.NewHSplit(leftWrap, center))
	w.SetContent(content)
	refresh()
	w.ShowAndRun()
}
