// DevKit 内核版（Go）
//
// 版本：A1_V_Φ9_Fix_Go_CN
// 对应 HTML 版：projects/devkit/code/A1_V_Φ9/deepseek_A1_V_Φ9_Fix_CN.html
//
// 只实现纯逻辑内核：版本号解析与兼容性判断、配置导入校验、设置规范化、
// 提示词模板拼接。
//
// 版权：Copyright (C) 2026-至今 北冥的鱼, DeepSeek
// 许可证：GPLv3
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

const currentVersion = "A1_V_Φ9_Fix_Go_CN"

// 与浏览器版一致：分支代号 + 结构段 + 语言后缀
func parseVersion(v string) (branch, structure string, suffix *string, ok bool) {
	t := strings.TrimSpace(v)
	if t == "" || len(t) > 100 {
		return "", "", nil, false
	}
	core := t
	if strings.HasSuffix(t, "_CN") {
		core = t[:len(t)-3]
		s := "CN"
		suffix = &s
	} else if strings.HasSuffix(t, "_GLOBAL") {
		core = t[:len(t)-7]
		s := "GLOBAL"
		suffix = &s
	}
	parts := strings.Split(core, "_")
	if len(parts) == 0 {
		return "", "", nil, false
	}
	branch = parts[0]
	if !strings.HasPrefix(branch, "A") {
		return "", "", nil, false
	}
	rest := branch[1:]
	for _, c := range rest {
		if c < '0' || c > '9' {
			return "", "", nil, false
		}
	}
	structure = strings.Join(parts[1:], "_")
	return branch, structure, suffix, true
}

func isCompatible(v string) bool {
	branch, structure, _, ok := parseVersion(v)
	if !ok {
		return false
	}
	if strings.HasPrefix(branch, "A2") {
		return false
	}
	for _, s := range strings.Split(structure, "_") {
		if s == "A2" {
			return false
		}
	}
	return true
}

type spec struct {
	key       string
	kind      string
	defBool   bool
	defStr    string
	values    []string
}

var specs = []spec{
	{"performanceMode", "boolean", false, "", nil},
	{"shortcutsEnabled", "boolean", true, "", nil},
	{"hideBtnText", "boolean", false, "", nil},
	{"promptActionsAlways", "boolean", true, "", nil},
	{"specPromptEnabled", "boolean", true, "", nil},
	{"inspirationSyncEnabled", "boolean", true, "", nil},
	{"themePref", "enum", false, "light", []string{"dark", "light", "auto"}},
}

func normalizeSettings(src map[string]any) map[string]any {
	out := map[string]any{}
	for _, s := range specs {
		v, has := src[s.key]
		switch s.kind {
		case "boolean":
			if has {
				if b, ok := v.(bool); ok {
					out[s.key] = b
					continue
				}
			}
			out[s.key] = s.defBool
		case "enum":
			if has {
				if str, ok := v.(string); ok {
					valid := false
					for _, x := range s.values {
						if x == str {
							valid = true
						}
					}
					if valid {
						out[s.key] = str
						continue
					}
				}
			}
			out[s.key] = s.defStr
		}
	}
	return out
}

func validateImport(data map[string]any) (int, error) {
	raw, hasProjects := data["projects"]
	if !hasProjects {
		if _, hasOne := data["project"]; hasOne {
			return 1, nil
		}
		return 0, fmt.Errorf("格式错误：不是有效对象")
	}
	projects, ok := raw.([]any)
	if !ok {
		return 0, fmt.Errorf("格式错误：projects 不是数组")
	}
	if len(projects) > 20 {
		return 0, fmt.Errorf("项目数 %d 超过上限 20", len(projects))
	}
	for i, p := range projects {
		obj, ok := p.(map[string]any)
		if !ok {
			return 0, fmt.Errorf("第 %d 个项目不是对象", i+1)
		}
		id, _ := obj["id"].(string)
		name, _ := obj["name"].(string)
		if id == "" {
			return 0, fmt.Errorf("第 %d 个项目缺少 id", i+1)
		}
		if name == "" {
			return 0, fmt.Errorf("第 %d 个项目缺少 name", i+1)
		}
		tabsRaw, ok := obj["tabs"].([]any)
		if !ok {
			return 0, fmt.Errorf("第 %d 个项目缺少 tabs", i+1)
		}
		if len(tabsRaw) > 50 {
			return 0, fmt.Errorf("第 %d 个项目页签超过 50", i+1)
		}
		for j, t := range tabsRaw {
			to, ok := t.(map[string]any)
			if !ok {
				return 0, fmt.Errorf("第 %d 个项目第 %d 个页签不是对象", i+1, j+1)
			}
			tid, _ := to["id"].(string)
			tname, _ := to["name"].(string)
			if tid == "" || tname == "" {
				return 0, fmt.Errorf("第 %d 个项目第 %d 个页签字段不完整", i+1, j+1)
			}
		}
	}
	return len(projects), nil
}

func usage() {
	fmt.Println("DevKit 内核版（Go）")
	fmt.Println("用法: devkit <子命令> [参数]")
	fmt.Println()
	fmt.Println("子命令:")
	fmt.Println("  version")
	fmt.Println("  parse-version <版本号>")
	fmt.Println("  check-version <版本号>")
	fmt.Println("  validate-config <配置文件>")
	fmt.Println("  normalize <设置JSON>")
	fmt.Println("  compose <模板文件> <灵感> [代码文件]")
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		usage()
		os.Exit(1)
	}

	switch args[0] {
	case "version":
		fmt.Println(currentVersion)

	case "parse-version":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "缺少版本号")
			os.Exit(1)
		}
		branch, structure, suffix, ok := parseVersion(args[1])
		if !ok {
			fmt.Fprintln(os.Stderr, "版本号不合规")
			os.Exit(1)
		}
		fmt.Printf("分支: %s\n", branch)
		if structure == "" {
			fmt.Println("结构段: （无）")
		} else {
			fmt.Printf("结构段: %s\n", structure)
		}
		if suffix == nil {
			fmt.Println("语言后缀: （无）")
		} else {
			fmt.Printf("语言后缀: %s\n", *suffix)
		}

	case "check-version":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "缺少版本号")
			os.Exit(1)
		}
		if isCompatible(args[1]) {
			fmt.Println("兼容")
		} else {
			fmt.Println("不兼容")
			os.Exit(1)
		}

	case "validate-config":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "缺少配置文件路径")
			os.Exit(1)
		}
		data, err := os.ReadFile(args[1])
		if err != nil {
			fmt.Fprintf(os.Stderr, "读取失败: %v\n", err)
			os.Exit(1)
		}
		var parsed map[string]any
		if err := json.Unmarshal(data, &parsed); err != nil {
			fmt.Fprintf(os.Stderr, "JSON 解析失败: %v\n", err)
			os.Exit(1)
		}
		if ver, ok := parsed["version"].(string); ok {
			if !isCompatible(ver) {
				fmt.Fprintf(os.Stderr, "配置文件版本不兼容: %s\n", ver)
				os.Exit(1)
			}
		}
		n, err := validateImport(parsed)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		fmt.Printf("校验通过，项目数: %d\n", n)

	case "normalize":
		if len(args) < 2 {
			fmt.Fprintln(os.Stderr, "缺少设置 JSON")
			os.Exit(1)
		}
		var src map[string]any
		if err := json.Unmarshal([]byte(args[1]), &src); err != nil {
			fmt.Fprintf(os.Stderr, "JSON 解析失败: %v\n", err)
			os.Exit(1)
		}
		out := normalizeSettings(src)
		b, _ := json.MarshalIndent(out, "", "  ")
		fmt.Println(string(b))

	case "compose":
		if len(args) < 3 {
			fmt.Fprintln(os.Stderr, "用法: compose <模板文件> <灵感> [代码文件]")
			os.Exit(1)
		}
		tpl, err := os.ReadFile(args[1])
		if err != nil {
			fmt.Fprintf(os.Stderr, "读取模板失败: %v\n", err)
			os.Exit(1)
		}
		code := "（无代码）"
		if len(args) >= 4 {
			if b, err := os.ReadFile(args[3]); err == nil {
				code = string(b)
			}
		}
		s := strings.ReplaceAll(string(tpl), "{inspiration}", args[2])
		s = strings.ReplaceAll(s, "{code}", code)
		fmt.Print(s)

	default:
		fmt.Fprintf(os.Stderr, "未知子命令: %s\n", args[0])
		usage()
		os.Exit(1)
	}
}
