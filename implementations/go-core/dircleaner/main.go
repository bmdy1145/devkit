// DirCleaner 内核版（Go）
//
// 版本：A1_II_Φ8_Go_CN
// 对应 HTML 版：projects/dircleaner/code/A1_II_Φ8/deepseek_html_20261005_ada08c.html
//
// 只实现纯逻辑内核：递归清空、白名单、关键目录防护、可执行文件检测。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	maxRecursionDepth    = 20
	maxFileCount         = 10000
	maxScanForExe        = 2000
	whitelistMarkerFile  = ".dircleaner_whitelist"
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

type stats struct {
	deletedFiles int
	deletedDirs  int
	totalBytes   int64
	errors       []string
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

func clearDirectory(dir string, depth int, fileCount *int, keepMarker, dryRun bool, st *stats) error {
	if depth > maxRecursionDepth {
		return fmt.Errorf("已达到最大目录深度限制 (%d)", maxRecursionDepth)
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return fmt.Errorf("无法读取 %s: %v", dir, err)
	}
	for _, e := range entries {
		p := filepath.Join(dir, e.Name())
		name := e.Name()
		if e.IsDir() {
			if err := clearDirectory(p, depth+1, fileCount, keepMarker, dryRun, st); err != nil {
				return err
			}
			if dryRun {
				fmt.Printf("[dry-run] 将删除目录: %s\n", name)
				st.deletedDirs++
			} else if err := os.Remove(p); err != nil {
				msg := fmt.Sprintf("无法删除目录 %s: %v", name, err)
				st.errors = append(st.errors, msg)
				fmt.Fprintln(os.Stderr, msg)
			} else {
				fmt.Printf("已删除目录: %s\n", name)
				st.deletedDirs++
			}
			continue
		}
		if *fileCount >= maxFileCount {
			return fmt.Errorf("已达到最大文件数限制 (%d)", maxFileCount)
		}
		if keepMarker && name == whitelistMarkerFile {
			fmt.Printf("跳过白名单标记文件: %s\n", name)
			continue
		}
		var size int64
		if info, err := e.Info(); err == nil {
			size = info.Size()
		}
		if dryRun {
			fmt.Printf("[dry-run] 将删除文件: %s (%s)\n", name, formatBytes(size))
			st.deletedFiles++
			st.totalBytes += size
			*fileCount++
			continue
		}
		if err := os.Remove(p); err != nil {
			msg := fmt.Sprintf("无法删除 %s: %v", name, err)
			st.errors = append(st.errors, msg)
			fmt.Fprintln(os.Stderr, msg)
			continue
		}
		fmt.Printf("已删除文件: %s (%s)\n", name, formatBytes(size))
		st.deletedFiles++
		st.totalBytes += size
		*fileCount++
	}
	return nil
}

func main() {
	dryRun := flag.Bool("dry-run", false, "只列出将删除的内容，不实际删除")
	inWhitelist := flag.Bool("whitelist", false, "该目录在白名单中（保留标记文件，跳过名称确认）")
	confirm := flag.String("confirm", "", "确认待清空目录的名称（非白名单目录必须提供且一致）")
	flag.Usage = func() {
		fmt.Println("DirCleaner 内核版（Go）")
		fmt.Println("用法: dircleaner <目录> [选项]")
		fmt.Println()
		fmt.Println("选项:")
		flag.PrintDefaults()
	}
	flag.Parse()

	// Go 的 flag 遇到第一个非选项参数就停止解析，因此
	// `dircleaner _t --confirm _t` 这种「目录在前」的写法会让
	// --confirm 落到 flag.Args() 里。这里显式兜一遍：把位置参数
	// 之后的内容重新当作 flags 解析。
	rest := flag.Args()
	var positional []string
	for i := 0; i < len(rest); i++ {
		a := rest[i]
		switch a {
		case "--dry-run":
			*dryRun = true
		case "--whitelist":
			*inWhitelist = true
		case "--confirm":
			if i+1 < len(rest) {
				*confirm = rest[i+1]
				i++
			}
		default:
			if !strings.HasPrefix(a, "--") {
				positional = append(positional, a)
			}
		}
	}

	if len(positional) < 1 {
		flag.Usage()
		os.Exit(1)
	}
	target := positional[0]
	info, err := os.Stat(target)
	if err != nil || !info.IsDir() {
		fmt.Fprintf(os.Stderr, "错误：%s 不是目录\n", target)
		os.Exit(1)
	}

	dirName := filepath.Base(filepath.Clean(target))
	if criticalDirNames[dirName] {
		fmt.Fprintf(os.Stderr, "错误：%s 是受保护的关键目录，禁止清空\n", dirName)
		os.Exit(1)
	}
	if !*inWhitelist {
		if *confirm == "" {
			fmt.Fprintf(os.Stderr, "错误：非白名单目录必须用 --confirm \"%s\" 确认\n", dirName)
			os.Exit(1)
		}
		if *confirm != dirName {
			fmt.Fprintf(os.Stderr, "错误：确认名称 \"%s\" 与目录名 \"%s\" 不一致\n", *confirm, dirName)
			os.Exit(1)
		}
	}

	counter := 0
	if containsExecutables(target, 0, &counter) {
		fmt.Println("⚠️  该目录包含可执行文件（.exe / .dll），删除后可能影响程序运行。")
		fmt.Print("确认继续？输入 yes: ")
		reader := bufio.NewReader(os.Stdin)
		ans, _ := reader.ReadString('\n')
		if strings.TrimSpace(ans) != "yes" {
			fmt.Println("已取消。")
			os.Exit(1)
		}
	}

	fmt.Println("===== 开始清空操作 =====")
	fmt.Printf("目标目录: %s\n", target)
	if *dryRun {
		fmt.Println("模式: 试运行（不实际删除）")
	}

	st := &stats{}
	fileCount := 0
	if err := clearDirectory(target, 0, &fileCount, *inWhitelist, *dryRun, st); err != nil {
		fmt.Fprintf(os.Stderr, "操作中止: %v\n", err)
		fmt.Printf("已删除文件: %d，目录: %d，释放空间: %s\n", st.deletedFiles, st.deletedDirs, formatBytes(st.totalBytes))
		os.Exit(1)
	}

	fmt.Println("===== 清空完成 =====")
	fmt.Printf("本次删除文件: %d\n", st.deletedFiles)
	fmt.Printf("本次删除目录: %d\n", st.deletedDirs)
	fmt.Printf("本次释放空间: %s\n", formatBytes(st.totalBytes))
	if len(st.errors) > 0 {
		fmt.Printf("错误数: %d\n", len(st.errors))
		for _, e := range st.errors {
			fmt.Printf("  %s\n", e)
		}
		os.Exit(1)
	}
}
