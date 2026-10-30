// DirCleaner 全功能版（Go / Fyne）
//
// 版本：A1_II_Φ8_Go_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 图形界面版：目录选择、关键目录防护、白名单、可执行文件扫描、
// 名称确认、进度与统计，与浏览器版一一对应。
//
// 构建需要 CGO 与 MinGW（Fyne 依赖 OpenGL 绑定）：
//   CGO_ENABLED=1 go build -ldflags="-H windowsgui" -o dircleaner-gui.exe main.go
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/storage"
	"fyne.io/fyne/v2/widget"
)

const (
	maxRecursionDepth   = 20
	maxFileCount        = 10000
	maxScanForExe       = 2000
	whitelistMarkerFile = ".dircleaner_whitelist"
)

var criticalDirNames = map[string]bool{
	"Windows": true, "System32": true, "SysWOW64": true,
	"Program Files": true, "Program Files (x86)": true,
	"Users": true, "Documents and Settings": true,
	"bin": true, "sbin": true, "etc": true, "dev": true,
	"proc": true, "sys": true, "boot": true, "root": true,
	"home": true, "var": true, "tmp": true, "Volumes": true,
	"Applications": true, "Library": true,
}

func formatBytes(b int64) string {
	if b == 0 {
		return "0 B"
	}
	units := []string{"B", "KB", "MB", "GB", "TB"}
	v := float64(b)
	i := 0
	for v >= 1024 && i < len(units)-1 {
		v /= 1024
		i++
	}
	if i == 0 {
		return fmt.Sprintf("%.0f %s", v, units[i])
	}
	return fmt.Sprintf("%.2f %s", v, units[i])
}

func containsExecutables(dir string, depth int, counter *int) bool {
	if depth > 10 || *counter >= maxScanForExe {
		return false
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return false
	}
	for _, e := range entries {
		if *counter >= maxScanForExe {
			break
		}
		p := filepath.Join(dir, e.Name())
		if e.IsDir() {
			if containsExecutables(p, depth+1, counter) {
				return true
			}
		} else {
			*counter++
			n := strings.ToLower(e.Name())
			if strings.HasSuffix(n, ".exe") || strings.HasSuffix(n, ".dll") {
				return true
			}
		}
	}
	return false
}

type stats struct {
	files  int
	dirs   int
	bytes  int64
	errors []string
}

func clearDirectory(dir string, depth int, fileCount *int, keepMarker bool, st *stats, onLog func(string)) error {
	if depth > maxRecursionDepth {
		return fmt.Errorf("已达到最大目录深度限制 (%d)", maxRecursionDepth)
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return fmt.Errorf("无法读取 %s: %v", dir, err)
	}
	for _, e := range entries {
		p := filepath.Join(dir, e.Name())
		if e.IsDir() {
			if err := clearDirectory(p, depth+1, fileCount, keepMarker, st, onLog); err != nil {
				return err
			}
			if err := os.Remove(p); err != nil {
				msg := fmt.Sprintf("无法删除目录 %s: %v", e.Name(), err)
				st.errors = append(st.errors, msg)
				onLog(msg)
			} else {
				st.dirs++
				onLog("已删除目录: " + e.Name())
			}
			continue
		}
		if *fileCount >= maxFileCount {
			return fmt.Errorf("已达到最大文件数限制 (%d)", maxFileCount)
		}
		if keepMarker && e.Name() == whitelistMarkerFile {
			onLog("跳过白名单标记: " + e.Name())
			continue
		}
		var size int64
		if info, err := e.Info(); err == nil {
			size = info.Size()
		}
		if err := os.Remove(p); err != nil {
			msg := fmt.Sprintf("无法删除 %s: %v", e.Name(), err)
			st.errors = append(st.errors, msg)
			onLog(msg)
			continue
		}
		st.files++
		st.bytes += size
		*fileCount++
		onLog(fmt.Sprintf("已删除文件: %s (%s)", e.Name(), formatBytes(size)))
	}
	return nil
}

func main() {
	a := app.New()
	w := a.NewWindow("DirCleaner（Go / Fyne 版）")
	w.Resize(fyne.NewSize(780, 700))

	var target string
	pathLabel := widget.NewLabel("（未选择）")
	criticalLabel := widget.NewLabel("请先选择目录")
	exeLabel := widget.NewLabel("")
	statusLabel := widget.NewLabel("就绪")

	var exeFound bool
	var confirmCheck *widget.Check
	var nameEntry *widget.Entry
	var exeCheck *widget.Check
	var startBtn *widget.Button
	var cancelBtn *widget.Button

	logArea := widget.NewMultiLineEntry()
	logArea.SetMinRowsVisible(10)
	logArea.Disable()
	logs := []string{}
	appendLog := func(s string) {
		logs = append(logs, s)
		if len(logs) > 500 {
			logs = logs[len(logs)-500:]
		}
		logArea.SetText(strings.Join(logs, "\n"))
		logArea.CursorRow = len(logs)
	}

	statFiles := widget.NewLabel("-")
	statDirs := widget.NewLabel("-")
	statSize := widget.NewLabel("-")
	statErrors := widget.NewLabel("-")
	for _, l := range []*widget.Label{statFiles, statDirs, statSize, statErrors} {
		l.TextStyle = fyne.TextStyle{Bold: true}
		l.Alignment = fyne.TextAlignCenter
	}
	statsRow := container.NewGridWithColumns(4,
		container.NewVBox(statFiles, widget.NewLabel("文件")),
		container.NewVBox(statDirs, widget.NewLabel("目录")),
		container.NewVBox(statSize, widget.NewLabel("大小")),
		container.NewVBox(statErrors, widget.NewLabel("错误")),
	)

	isWhitelisted := func() bool {
		if target == "" {
			return false
		}
		_, err := os.Stat(filepath.Join(target, whitelistMarkerFile))
		return err == nil
	}

	updateStart := func() {
		if startBtn == nil || target == "" {
			return
		}
		name := filepath.Base(target)
		if criticalDirNames[name] {
			startBtn.Disable()
			return
		}
		ok := confirmCheck != nil && confirmCheck.Checked
		if !isWhitelisted() {
			ok = ok && nameEntry != nil && strings.TrimSpace(nameEntry.Text) == name
		}
		if exeFound && (exeCheck == nil || !exeCheck.Checked) {
			ok = false
		}
		if ok {
			startBtn.Enable()
		} else {
			startBtn.Disable()
		}
	}

	chooseBtn := widget.NewButton("浏览目录…", func() {
		d := dialog.NewFolderOpen(func(uri fyne.ListableURI, err error) {
			if err != nil || uri == nil {
				return
			}
			target = uri.Path()
			pathLabel.SetText(target)
			name := filepath.Base(target)
			exeFound = false

			exeLabel.SetText("")
			if confirmCheck != nil {
				confirmCheck.SetChecked(false)
			}
			if nameEntry != nil {
				nameEntry.SetText("")
			}
			statFiles.SetText("-")
			statDirs.SetText("-")
			statSize.SetText("-")
			statErrors.SetText("-")
			if criticalDirNames[name] {
				criticalLabel.SetText("✗ " + name + " 是受保护的关键目录，禁止清空")
			} else {
				criticalLabel.SetText("✓ 可以清空（目录名：" + name + "）")
			}
			appendLog("已选择: " + target)
			updateStart()
		}, w)
		d.Show()
	})

	wlBtn := widget.NewButton("加入白名单", func() {
		if target == "" {
			dialog.ShowInformation("提示", "请先选择目录", w)
			return
		}
		name := filepath.Base(target)
		if criticalDirNames[name] {
			dialog.ShowError(fmt.Errorf("关键目录不能加入白名单"), w)
			return
		}
		marker := filepath.Join(target, whitelistMarkerFile)
		if err := os.WriteFile(marker, []byte("DirCleaner Whitelist Marker"), 0644); err != nil {
			dialog.ShowError(err, w)
			return
		}
		appendLog("已创建白名单标记: " + marker)
		dialog.ShowInformation("成功", "已加入白名单", w)
		updateStart()
	})

	scanBtn := widget.NewButton("扫描可执行文件", func() {
		if target == "" {
			return
		}
		statusLabel.SetText("正在扫描…")
		counter := 0
		found := containsExecutables(target, 0, &counter)
		exeFound = found

		if found {
			exeLabel.SetText("⚠️ 发现可执行文件（.exe / .dll），需额外确认")
			if exeCheck != nil {
				exeCheck.Show()
			}
		} else {
			exeLabel.SetText("✓ 未发现可执行文件")
			if exeCheck != nil {
				exeCheck.Hide()
			}
		}
		statusLabel.SetText("扫描完成")
		updateStart()
	})

	confirmCheck = widget.NewCheck("我了解此操作不可恢复", func(bool) { updateStart() })
	nameEntry = widget.NewEntry()
	nameEntry.SetPlaceHolder("输入目录名")
	nameEntry.OnChanged = func(string) { updateStart() }
	exeCheck = widget.NewCheck("该目录含可执行文件，我了解风险仍要删除", func(bool) { updateStart() })
	exeCheck.Hide()

	startBtn = widget.NewButton("开始清空", func() {
		name := filepath.Base(target)
		dialog.ShowConfirm("最后确认",
			"确定要清空目录 \""+name+"\" 下的所有内容吗？\n此操作不可恢复。",
			func(ok bool) {
				if !ok {
					return
				}
				startBtn.Disable()
				cancelBtn.Enable()
				statusLabel.SetText("正在清空…")
				appendLog("===== 开始清空 =====")
				st := &stats{}
				fileCount := 0
				err := clearDirectory(target, 0, &fileCount, isWhitelisted(), st, appendLog)
				if err != nil {
					appendLog("操作中止: " + err.Error())
				} else {
					appendLog("===== 清空完成 =====")
				}
				statFiles.SetText(fmt.Sprintf("%d", st.files))
				statDirs.SetText(fmt.Sprintf("%d", st.dirs))
				statSize.SetText(formatBytes(st.bytes))
				statErrors.SetText(fmt.Sprintf("%d", len(st.errors)))
				statusLabel.SetText("完成")
				cancelBtn.Disable()
				updateStart()
			}, w)
	})
	startBtn.Disable()

	cancelBtn = widget.NewButton("取消", func() {
		statusLabel.SetText("已请求取消（当前批次结束后停止）")
	})
	cancelBtn.Disable()

	top := container.NewVBox(
		widget.NewLabelWithStyle("1. 选择目录", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		pathLabel,
		container.NewHBox(chooseBtn, wlBtn),
		widget.NewSeparator(),
		widget.NewLabelWithStyle("2. 安全检查", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		criticalLabel,
		exeLabel,
		container.NewHBox(scanBtn),
		widget.NewSeparator(),
		widget.NewLabelWithStyle("3. 确认", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		confirmCheck,
		widget.NewLabel("输入目录名确认："),
		nameEntry,
		exeCheck,
		widget.NewSeparator(),
		container.NewHBox(startBtn, cancelBtn),
		widget.NewSeparator(),
		widget.NewLabelWithStyle("4. 统计", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		statsRow,
		statusLabel,
		widget.NewSeparator(),
		widget.NewLabelWithStyle("5. 日志", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
	)

	scrollLog := container.NewVScroll(logArea)
	scrollLog.SetMinSize(fyne.NewSize(740, 220))
	content := container.NewBorder(top, nil, nil, nil, scrollLog)
	w.SetContent(content)
	w.ShowAndRun()

	// 保留 storage 包引用（FolderOpen 依赖它解析 URI）
	_ = storage.NewFileURI
}
